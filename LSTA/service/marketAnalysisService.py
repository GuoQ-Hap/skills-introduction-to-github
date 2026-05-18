"""市场分析服务 —— 基于 Amazon 搜索样本聚合类目机会。"""
from __future__ import annotations

import concurrent.futures
import json
import re
from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Dict, List, Optional

from LSTA.constants import MARKETPLACE_DOMAINS
from LSTA.models.listingState import (
    MarketAnalysisInsight,
    MarketAnalysisResponse,
    MarketBrandStat,
    MarketPriceBand,
    MarketProductItem,
    ProductData,
)
from LSTA.service.amazonService import amazon_service
from LSTA.service.base import service_logger
from LSTA.service.competitorDiscoveryService import _price_and_currency, _review_count_int

logger = service_logger

_ZH_MARKET_KEYWORDS = {
    "地毯": ["area rug", "washable rug", "living room rug", "boho rug"],
    "桌垫": ["desk mat", "large desk pad", "office desk mat"],
    "鼠标垫": ["mouse pad", "gaming mouse pad", "large mouse pad"],
    "收纳": ["home storage organizer", "closet organizer", "storage bins"],
}


def _marketplace_url(marketplace: str, asin: str) -> str:
    domain = MARKETPLACE_DOMAINS.get((marketplace or "US").upper(), "www.amazon.com")
    return f"https://{domain}/dp/{asin}" if asin else ""


def _num_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).replace(",", ".").strip()
    m = re.search(r"\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _clean_brand(raw: str, title: str = "") -> str:
    brand = (raw or "").strip()
    brand = re.sub(r"^(Visit|Shop)\s+the\s+", "", brand, flags=re.I)
    brand = re.sub(r"\s+(Store|Brand|品牌旗舰店)\s*$", "", brand, flags=re.I).strip(" :-|")
    if brand and brand.lower() not in {"unknown", "none", "n/a", "na"}:
        return brand[:60]
    title = title or ""
    # 英文标题常以品牌开头，如 "DUKINO 6x9 Rug..."；跳过尺寸/营销词，避免把 5x7、8x10 当品牌。
    first = re.match(r"^\s*([A-Za-z][A-Za-z0-9&'_-]{1,32})\b", title)
    if first:
        candidate = first.group(1).strip(" -_'")
        low = candidate.lower()
        blocked = {
            "the", "and", "for", "with", "area", "rug", "rugs", "washable",
            "soft", "modern", "vintage", "boho", "non", "large", "small",
        }
        if low not in blocked and not re.fullmatch(r"\d+(?:x\d+)?", low):
            return candidate[:60]
    # 中文页面可能标题被本地化，搜索卡片又不含品牌；此时留空，避免展示误导性的 Unknown。
    return ""


def _build_search_keywords(keyword: str) -> List[str]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    mapped: List[str] = []
    for zh, terms in _ZH_MARKET_KEYWORDS.items():
        if zh in keyword:
            mapped.extend(terms)
    if re.search(r"[A-Za-z]", keyword):
        mapped.insert(0, keyword)
    elif not mapped:
        mapped.append(keyword)
    seen = set()
    output: List[str] = []
    for item in mapped:
        low = item.lower().strip()
        if low and low not in seen:
            output.append(item.strip())
            seen.add(low)
    return output[:4]


def _item_from_search(row: Dict[str, Any], marketplace: str) -> MarketProductItem:
    price_num, currency = _price_and_currency(row.get("price", ""), row.get("currency", ""), marketplace)
    asin = str(row.get("asin") or "").strip()
    title = str(row.get("title") or "").strip()
    return MarketProductItem(
        asin=asin,
        title=title,
        brand=_clean_brand(str(row.get("brand") or ""), title),
        price=str(row.get("price") or ""),
        currency=currency or str(row.get("currency") or ""),
        rating=str(row.get("rating") or ""),
        review_count=str(row.get("review_count") or ""),
        image=str(row.get("image") or ""),
        avg_price=price_num,
        bsr_rank=str(row.get("bsr_rank") or row.get("bsr") or ""),
        monthly_sales_text=str(row.get("monthly_sales_text") or row.get("monthly_sales") or ""),
        product_url=_marketplace_url(marketplace, asin),
    )


def _merge_detail(item: MarketProductItem, product: ProductData) -> MarketProductItem:
    item.title = product.title or item.title
    item.brand = _clean_brand(product.brand or item.brand, item.title)
    item.price = product.price or item.price
    item.currency = product.currency or item.currency
    item.rating = product.rating or item.rating
    item.review_count = product.review_count or item.review_count
    item.bsr_rank = product.bsr_rank or item.bsr_rank
    item.monthly_sales_text = product.monthly_sales_text or item.monthly_sales_text
    if product.images and not item.image:
        item.image = product.images[0]
    price_num, currency = _price_and_currency(item.price, item.currency, product.marketplace or "US")
    item.avg_price = price_num if price_num is not None else item.avg_price
    if currency:
        item.currency = currency
    return item


def _price_bands(prices: List[float]) -> List[MarketPriceBand]:
    if not prices:
        return []
    lo, hi = min(prices), max(prices)
    if lo == hi:
        return [MarketPriceBand(label=f"{lo:.2f}", count=len(prices), min_price=lo, max_price=hi)]
    step = (hi - lo) / 4
    bands: List[MarketPriceBand] = []
    for i in range(4):
        b_lo = lo + step * i
        b_hi = hi if i == 3 else lo + step * (i + 1)
        count = sum(1 for p in prices if (b_lo <= p <= b_hi if i == 3 else b_lo <= p < b_hi))
        bands.append(MarketPriceBand(
            label=f"{b_lo:.0f}-{b_hi:.0f}",
            count=count,
            min_price=round(b_lo, 2),
            max_price=round(b_hi, 2),
        ))
    return bands


def _extract_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _fallback_insight(keyword: str, products: List[MarketProductItem], brands: List[MarketBrandStat]) -> MarketAnalysisInsight:
    titles = " ".join(p.title.lower() for p in products[:40])
    trend_terms = []
    for term in ("washable", "non slip", "boho", "vintage", "soft", "machine washable", "kids", "outdoor", "modern"):
        if term in titles:
            trend_terms.append(term)
    return MarketAnalysisInsight(
        hot_directions=trend_terms[:8] or [keyword],
        review_pain_points=["需要结合详情评论进一步确认：质量、尺寸、色差、气味、耐用性通常是高频风险点"],
        accessible_markets=["Amazon 搜索结果可进入的细分词： " + " / ".join(t.title() for t in trend_terms[:4])] if trend_terms else [],
        market_capacity=f"搜索样本 {len(products)} 个商品，总评论量 {sum(_review_count_int(p.review_count) for p in products):,}，可作为需求热度粗略参考。",
        leading_brands=[b.brand for b in brands[:8]],
        market_trends=trend_terms[:8],
        top_tk_designers=["需接入 TikTok/达人数据源后识别；当前 Amazon 样本无法直接判定设计师账号"],
        opportunities=["围绕高频趋势词做差异化款式、材质、场景图和评论痛点补强"],
        risks=["当前基于 Amazon 搜索样本估算，市场容量不是平台官方 GMV；需结合 SQR/ABA/广告数据复核"],
        summary=f"{keyword} 市场已有可见需求，建议优先验证头部词、价格带和差评痛点后再立项。",
    )


class MarketAnalysisService:
    """从 Amazon 搜索样本构建市场分析报告。"""

    def analyze(
        self,
        keyword: str,
        marketplace: str = "US",
        max_results: int = 40,
        max_pages: int = 2,
        with_details: bool = True,
        model: str = "",
    ) -> MarketAnalysisResponse:
        marketplace = (marketplace or "US").upper()
        search_keywords = _build_search_keywords(keyword)
        if not search_keywords:
            raise ValueError("统计方向不能为空")

        rows: List[Dict[str, Any]] = []
        seen_asins = set()
        notes: List[str] = []
        for kw in search_keywords:
            try:
                found = amazon_service.search(kw, marketplace=marketplace, max_pages=max_pages)
                notes.append(f"{kw}: 搜索返回 {len(found)} 条")
                for row in found:
                    asin = str(row.get("asin") or "").strip()
                    if not asin or asin in seen_asins or row.get("is_sponsored"):
                        continue
                    rows.append(row)
                    seen_asins.add(asin)
                    if len(rows) >= max_results:
                        break
            except Exception as exc:
                notes.append(f"{kw}: 搜索失败 {exc}")
                logger.warning("市场分析搜索失败 kw=%s: %s", kw, exc)
            if len(rows) >= max_results:
                break

        products = [_item_from_search(row, marketplace) for row in rows[:max_results]]
        detail_products: Dict[str, ProductData] = {}

        if with_details and products:
            # 品牌在 Amazon 搜索卡片里经常缺失，必须尽量补抓详情页；
            # 否则会把真实品牌误显示为 Unknown，影响市场统计。
            top_for_detail = products[: min(max_results, len(products))]

            def _fetch_detail(item: MarketProductItem):
                try:
                    return item.asin, amazon_service.fetch(item.asin, marketplace)
                except Exception as exc:
                    logger.warning("市场分析详情抓取失败 asin=%s: %s", item.asin, exc)
                    return item.asin, None

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                for asin, pd in pool.map(_fetch_detail, top_for_detail):
                    if pd:
                        detail_products[asin] = pd

            for item in products:
                pd = detail_products.get(item.asin)
                if pd:
                    _merge_detail(item, pd)

        prices = [p.avg_price for p in products if p.avg_price is not None]
        ratings = [_num_float(p.rating) for p in products]
        ratings = [r for r in ratings if r is not None]
        total_reviews = sum(_review_count_int(p.review_count) for p in products)

        brand_counts: Dict[str, int] = Counter()
        brand_reviews: Dict[str, int] = defaultdict(int)
        brand_ratings: Dict[str, List[float]] = defaultdict(list)
        brand_asins: Dict[str, List[str]] = defaultdict(list)
        for p in products:
            brand = _clean_brand(p.brand, p.title)
            if not brand or brand == "Unknown":
                continue
            brand_counts[brand] += 1
            brand_reviews[brand] += _review_count_int(p.review_count)
            rating = _num_float(p.rating)
            if rating is not None:
                brand_ratings[brand].append(rating)
            if len(brand_asins[brand]) < 5:
                brand_asins[brand].append(p.asin)

        brands = [
            MarketBrandStat(
                brand=brand,
                count=count,
                avg_rating=round(mean(brand_ratings[brand]), 2) if brand_ratings[brand] else None,
                total_reviews=brand_reviews[brand],
                sample_asins=brand_asins[brand],
                description=(
                    f"样本中出现 {count} 款，累计 {brand_reviews[brand]:,} 条评论"
                    + (f"，平均评分 {round(mean(brand_ratings[brand]), 2)}。" if brand_ratings[brand] else "。")
                ),
            )
            for brand, count in brand_counts.most_common(12)
        ]
        brands.sort(key=lambda b: (b.count, b.total_reviews), reverse=True)
        self._enrich_brand_descriptions(
            keyword=keyword,
            marketplace=marketplace,
            brands=brands,
            products=products,
            detail_products=detail_products,
            model=model,
        )

        insight = self._llm_insight(
            keyword=keyword,
            marketplace=marketplace,
            products=products,
            detail_products=detail_products,
            brands=brands,
            total_reviews=total_reviews,
            avg_price=round(mean(prices), 2) if prices else None,
            model=model,
        ) or _fallback_insight(keyword, products, brands)

        return MarketAnalysisResponse(
            keyword=keyword,
            marketplace=marketplace,
            search_keywords=search_keywords,
            total_found=len(rows),
            analyzed_count=len(products),
            avg_price=round(mean(prices), 2) if prices else None,
            avg_rating=round(mean(ratings), 2) if ratings else None,
            total_reviews=total_reviews,
            top_products=products[:30],
            top_brands=brands,
            price_bands=_price_bands(prices),
            insight=insight,
            raw_notes=notes,
        )

    def _enrich_brand_descriptions(
        self,
        *,
        keyword: str,
        marketplace: str,
        brands: List[MarketBrandStat],
        products: List[MarketProductItem],
        detail_products: Dict[str, ProductData],
        model: str = "",
    ) -> None:
        """给头部品牌补充简介。失败不阻塞主流程。"""
        if not brands:
            return

        brand_payload = []
        for brand in brands[:10]:
            brand_products = [p for p in products if _clean_brand(p.brand, p.title).lower() == brand.brand.lower()]
            samples = []
            for p in brand_products[:5]:
                pd = detail_products.get(p.asin)
                samples.append({
                    "asin": p.asin,
                    "title": p.title[:220],
                    "price": p.avg_price,
                    "rating": p.rating,
                    "review_count": p.review_count,
                    "bsr": p.bsr_rank,
                    "bullets": (pd.bullet_points[:3] if pd else []),
                })
            brand_payload.append({
                "brand": brand.brand,
                "count": brand.count,
                "avg_rating": brand.avg_rating,
                "total_reviews": brand.total_reviews,
                "samples": samples,
            })

        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Amazon 市场品牌分析师。基于样本商品信息，为每个品牌写一句中文简介。"
                    "只描述样本体现出的定位、常见产品方向、价格/评价特征；不要编造品牌历史、官网或公司背景。"
                    "严格输出 JSON 对象，key 为品牌名，value 为 30-70 字中文简介。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "keyword": keyword,
                    "marketplace": marketplace,
                    "brands": brand_payload,
                }, ensure_ascii=False),
            },
        ]
        try:
            from admin.model_pool import model_pool

            kwargs: Dict[str, Any] = {
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 1600,
                "timeout": 90,
                "_log_module": "market_brand_profile",
            }
            if model:
                kwargs["preferred_model"] = model
            data = _extract_json_object(model_pool.call_llm(**kwargs))
            for brand in brands:
                desc = data.get(brand.brand)
                if isinstance(desc, str) and desc.strip():
                    brand.description = desc.strip()[:180]
        except Exception as exc:
            logger.warning("市场分析品牌简介生成失败，使用规则简介: %s", exc)

    def _llm_insight(
        self,
        *,
        keyword: str,
        marketplace: str,
        products: List[MarketProductItem],
        detail_products: Dict[str, ProductData],
        brands: List[MarketBrandStat],
        total_reviews: int,
        avg_price: Optional[float],
        model: str = "",
    ) -> Optional[MarketAnalysisInsight]:
        samples = []
        for p in products[:24]:
            pd = detail_products.get(p.asin)
            reviews = []
            if pd:
                reviews = [
                    {"stars": r.stars, "title": r.title, "body": r.body[:300]}
                    for r in (pd.reviews or [])[:5]
                ]
            samples.append({
                "asin": p.asin,
                "title": p.title[:240],
                "brand": p.brand,
                "price": p.avg_price,
                "rating": p.rating,
                "review_count": p.review_count,
                "bsr": p.bsr_rank,
                "monthly_sales": p.monthly_sales_text,
                "reviews": reviews,
            })

        prompt = {
            "task": "Amazon 市场分析",
            "keyword": keyword,
            "marketplace": marketplace,
            "metrics": {
                "sample_count": len(products),
                "total_reviews": total_reviews,
                "avg_price": avg_price,
            },
            "top_brands": [b.model_dump() for b in brands[:10]],
            "product_samples": samples,
        }
        system = (
            "你是资深跨境电商市场分析师。基于 Amazon 搜索样本做市场方向分析。"
            "不要编造平台官方 GMV；市场容量只能基于样本评论量、价格带、BSR/月销文本做估算说明。"
            "top_tk_designers 如果 Amazon 样本不足以判断，请输出可执行的 TikTok 达人/设计师筛选方向，不要编造真实账号。"
            "严格输出 JSON。"
        )
        schema = {
            "hot_directions": ["最火/最好卖的细分方向"],
            "review_pain_points": ["评论暴露的缺点/差评痛点"],
            "accessible_markets": ["可以切入的细分市场/人群/场景"],
            "market_capacity": "样本级市场容量判断",
            "leading_brands": ["头部品牌"],
            "market_trends": ["市场风向/趋势"],
            "top_tk_designers": ["TikTok 设计师/达人方向或账号线索"],
            "opportunities": ["产品/Listing/供应链机会"],
            "risks": ["进入风险"],
            "summary": "200字以内总结",
        }
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "请按这个 JSON 结构输出：\n" + json.dumps(schema, ensure_ascii=False)},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ]
        try:
            from admin.model_pool import model_pool

            kwargs: Dict[str, Any] = {
                "messages": messages,
                "temperature": 0.25,
                "max_tokens": 4096,
                "timeout": 160,
                "_log_module": "market_analysis",
            }
            if model:
                kwargs["preferred_model"] = model
            raw = model_pool.call_llm(**kwargs)
            data = _extract_json_object(raw)
            if not data:
                return None
            return MarketAnalysisInsight(**data)
        except Exception as exc:
            logger.warning("市场分析 LLM 洞察失败，使用规则兜底: %s", exc)
            return None


market_analysis_service = MarketAnalysisService()
