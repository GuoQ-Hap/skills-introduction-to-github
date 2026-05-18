"""Amazon 产品数据抓取服务。

支持两种数据源（按优先级）：
1. SP-API（Amazon Selling Partner API）—— 需配置 SP_API_* 环境变量
2. 虚拟机代理抓取 —— 需配置 SCRAPER_PROXY_URL
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import requests

from LSTA.constants import (
    FETCH_TIMEOUT,
    MARKETPLACE_DOMAINS,
    SCRAPER_PROXY_URL,
    SP_API_CLIENT_ID,
    SP_API_CLIENT_SECRET,
    SP_API_REFRESH_TOKEN,
)
from LSTA.models.listingState import ProductData, ReviewItem
from LSTA.service.base import service_logger

logger = service_logger

# marketplace → 默认货币代码
_MARKETPLACE_CURRENCY: Dict[str, str] = {
    "US": "USD", "UK": "GBP", "DE": "EUR", "FR": "EUR", "IT": "EUR",
    "ES": "EUR", "JP": "JPY", "CA": "CAD", "AU": "AUD", "MX": "MXN",
}

_CURRENCY_SYMBOLS: Dict[str, str] = {
    "$": "USD", "US$": "USD", "USD": "USD",
    "£": "GBP", "GBP": "GBP",
    "€": "EUR", "EUR": "EUR",
    "¥": "JPY", "￥": "CNY", "JPY": "JPY", "CNY": "CNY", "RMB": "CNY",
    "CA$": "CAD", "C$": "CAD", "CAD": "CAD",
    "A$": "AUD", "AU$": "AUD", "AUD": "AUD",
    "MX$": "MXN", "MXN": "MXN",
}


def _normalize_price(raw_price: str, raw_currency: str, marketplace: str) -> Tuple[str, str]:
    """将原始价格/货币归一化为 (纯数字价格, ISO货币代码)。

    处理诸如 price="CNY286.26" currency="USD" 这类矛盾情况——
    从 price 字符串中提取嵌入的货币符号，优先级高于独立的 currency 字段。
    """
    price_str = (raw_price or "").strip()
    marketplace = (marketplace or "US").upper()
    market_currency = _MARKETPLACE_CURRENCY.get(marketplace, "USD")
    currency = (raw_currency or "").strip()

    if not price_str:
        return "", currency or market_currency

    embedded_cur = ""
    for sym, code in sorted(_CURRENCY_SYMBOLS.items(), key=lambda x: -len(x[0])):
        if price_str.upper().startswith(sym.upper()):
            embedded_cur = code
            price_str = price_str[len(sym):].strip()
            break
        if price_str.upper().endswith(sym.upper()):
            embedded_cur = code
            price_str = price_str[:-len(sym)].strip()
            break

    numeric = re.sub(r"[^\d.,]", "", price_str).strip(" ,.")
    if not numeric:
        return "", currency or embedded_cur or market_currency

    final_currency = embedded_cur or currency or market_currency
    # 代理偶发会在 US 页面把独立 currency 写成 CNY，但价格文本本身没有 CNY/￥ 前缀。
    # 这种情况下按站点默认币种纠偏，避免竞品发现把所有 USD 候选过滤掉。
    if currency and currency.upper() != market_currency and not embedded_cur:
        final_currency = market_currency
    return numeric, final_currency


class AmazonProductService:
    """获取 Amazon 产品详情。优先级：SP-API → 虚拟机代理。"""

    # ==================== 公共入口 ====================

    def fetch(self, asin: str, marketplace: str = "US") -> ProductData:
        """按优先级尝试获取产品数据，返回 ProductData。
        优先级：SP-API → 虚拟机代理
        """
        marketplace = marketplace.upper()
        if marketplace not in MARKETPLACE_DOMAINS:
            raise ValueError(f"不支持的站点: {marketplace}，可选: {list(MARKETPLACE_DOMAINS.keys())}")

        errors: list[str] = []

        if self._sp_api_configured():
            try:
                return self._with_mws_reviews(self._fetch_via_sp_api(asin, marketplace), marketplace)
            except Exception as e:
                errors.append(f"SP-API: {e}")
                logger.warning("SP-API 获取失败，回退到虚拟机代理: %s", e)

        if SCRAPER_PROXY_URL:
            try:
                return self._with_mws_reviews(self._fetch_via_proxy_vm(asin, marketplace), marketplace)
            except Exception as e:
                errors.append(f"虚拟机代理: {e}")
                logger.warning("虚拟机代理抓取失败: %s", e)

        raise RuntimeError(
            f"所有抓取渠道均失败（ASIN={asin}, 站点={marketplace}）。"
            + (" | ".join(errors) if errors else "未配置 SP-API 或虚拟机代理")
        )

    @staticmethod
    def _with_mws_reviews(product: ProductData, marketplace: str) -> ProductData:
        """评论统一优先取领星 MWS 评论表，避免页面/手机端评论抓取不稳定。"""
        try:
            from LSTA.service.mwsReviewService import mws_review_service
            reviews = mws_review_service.query_reviews(
                asin=product.asin,
                marketplace=marketplace or product.marketplace or "US",
                limit=30,
            )
            if reviews:
                product.reviews = reviews
        except Exception as exc:
            logger.warning("MWS 评论补全失败 asin=%s: %s", product.asin, exc)
        return product

    # ==================== 虚拟机代理 ====================

    def _fetch_via_proxy_vm(self, asin: str, marketplace: str) -> ProductData:
        """通过部署在 Windows 虚拟机上的抓取代理服务获取产品数据。"""
        url = f"{SCRAPER_PROXY_URL.rstrip('/')}/scrape"
        logger.info("通过虚拟机代理抓取: %s (ASIN=%s, 站点=%s)", SCRAPER_PROXY_URL, asin, marketplace)
        resp = requests.post(
            url,
            json={"asin": asin, "marketplace": marketplace},
            timeout=FETCH_TIMEOUT + 60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"虚拟机代理返回状态码: {resp.status_code}")
        body = resp.json()
        if not body.get("success"):
            debug = body.get("debug") or {}
            attempts = debug.get("attempts") or []
            attempt_summary = ""
            if attempts:
                parts = []
                for item in attempts[-3:]:
                    parts.append(
                        f"#{item.get('attempt')} status={item.get('status')} "
                        f"len={item.get('html_len')} block={item.get('block_reason') or '-'}"
                    )
                attempt_summary = "；尝试: " + " | ".join(parts)
            parse = debug.get("parse") or {}
            parse_summary = ""
            candidates = parse.get("candidate_titles") or {}
            if candidates:
                preview = " | ".join(f"{k}={str(v)[:60]}" for k, v in list(candidates.items())[:3])
                parse_summary = f"；标题候选: {preview}"
            version = debug.get("version")
            version_summary = f"；代理版本: {version}" if version else ""
            raise RuntimeError(
                f"虚拟机代理抓取失败: {body.get('error', '未知错误')}"
                f"{version_summary}{attempt_summary}{parse_summary}"
            )
        data = body["data"]

        price, currency = _normalize_price(
            data.get("price", ""), data.get("currency", ""), marketplace,
        )

        bsr = data.get("bsr_rank") or data.get("bsr") or data.get("best_sellers_rank") or ""
        if isinstance(bsr, (int, float)):
            bsr = str(int(bsr))

        reviews_raw = data.get("reviews") or []
        reviews = [
            ReviewItem(
                stars=r.get("stars", 0),
                title=r.get("title", ""),
                body=r.get("body", ""),
                date=r.get("date", ""),
            )
            for r in reviews_raw[:10] if isinstance(r, dict)
        ]

        return ProductData(
            asin=data.get("asin", asin),
            marketplace=data.get("marketplace", marketplace),
            title=data.get("title", ""),
            brand=data.get("brand", ""),
            price=price,
            currency=currency,
            rating=data.get("rating", ""),
            review_count=data.get("review_count", ""),
            bullet_points=data.get("bullet_points", []),
            description=data.get("description", ""),
            category=data.get("category", ""),
            bsr_rank=bsr,
            monthly_sales_text=data.get("monthly_sales_text", "") or data.get("monthly_sales", ""),
            images=data.get("images", [])[:5],
            reviews=reviews,
        )

    # ==================== SP-API ====================

    @staticmethod
    def _sp_api_configured() -> bool:
        return bool(SP_API_REFRESH_TOKEN and SP_API_CLIENT_ID and SP_API_CLIENT_SECRET)

    def _fetch_via_sp_api(self, asin: str, marketplace: str) -> ProductData:
        """通过 Amazon SP-API Catalog Items 获取产品数据（需要 python-sp-api）。"""
        try:
            from sp_api.api import CatalogItems
            from sp_api.base import Marketplaces

            mp_map = {
                "US": Marketplaces.US, "UK": Marketplaces.UK,
                "DE": Marketplaces.DE, "JP": Marketplaces.JP,
                "CA": Marketplaces.CA, "FR": Marketplaces.FR,
                "IT": Marketplaces.IT, "ES": Marketplaces.ES,
                "AU": Marketplaces.AU, "MX": Marketplaces.MX,
            }
            mp = mp_map.get(marketplace, Marketplaces.US)

            catalog = CatalogItems(marketplace=mp)
            resp = catalog.get_catalog_item(
                asin=asin,
                includedData=[
                    "summaries", "attributes", "images",
                    "productTypes", "salesRanks",
                ],
            )
            item = resp.payload
            summaries = (item.get("summaries") or [{}])[0]

            images_group = item.get("images") or []
            image_urls: list[str] = []
            for group in images_group:
                for img in group.get("images", []):
                    if img.get("variant") == "MAIN" or not image_urls:
                        image_urls.append(img.get("link", ""))

            # 价格：SP-API summaries 里可能不带价格，给默认货币
            raw_price = ""
            raw_currency = ""
            attrs = item.get("attributes") or {}
            list_price = attrs.get("list_price") or []
            if isinstance(list_price, list) and list_price:
                lp = list_price[0] if isinstance(list_price[0], dict) else {}
                raw_price = str(lp.get("value", ""))
                raw_currency = lp.get("currency_of_preference", "") or lp.get("currency", "")
            price, currency = _normalize_price(raw_price, raw_currency, marketplace)

            # BSR：从 salesRanks 中提取
            bsr = ""
            sales_ranks = item.get("salesRanks") or []
            for sr_group in sales_ranks:
                for rank_item in sr_group.get("displayGroupRanks", sr_group.get("ranks", [])):
                    r = rank_item.get("rank")
                    if r:
                        bsr = str(r)
                        break
                if bsr:
                    break

            return ProductData(
                asin=asin,
                marketplace=marketplace,
                title=summaries.get("itemName", ""),
                brand=summaries.get("brand", ""),
                price=price,
                currency=currency,
                images=image_urls[:5],
                bsr_rank=bsr,
            )
        except ImportError:
            raise RuntimeError("未安装 python-sp-api，请运行: pip install python-sp-api")


    # ==================== Amazon 搜索 ====================

    def search(self, keywords: str, marketplace: str = "US", max_pages: int = 2) -> list[dict]:
        """通过虚拟机代理搜索 Amazon 商品，返回原始结果列表。"""
        if not SCRAPER_PROXY_URL:
            raise RuntimeError("未配置 SCRAPER_PROXY_URL，无法搜索")
        url = f"{SCRAPER_PROXY_URL.rstrip('/')}/search"
        logger.info("Amazon 搜索: keywords=%s, marketplace=%s, pages=%d", keywords[:60], marketplace, max_pages)
        resp = requests.post(
            url,
            json={"keywords": keywords, "marketplace": marketplace, "max_pages": max_pages},
            timeout=FETCH_TIMEOUT + 60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"搜索代理返回状态码: {resp.status_code}")
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(f"搜索失败: {body.get('error', '未知错误')}")
        return body.get("results", [])


amazon_service = AmazonProductService()
