"""竞品发现服务 —— 通过 Amazon 搜索抓取竞品，按尺寸/风格/价格/销量四维过滤，排除自有 ASIN。"""
from __future__ import annotations

import concurrent.futures
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Set

import requests

from LSTA.constants import SCRAPER_PROXY_URL, FETCH_TIMEOUT
from LSTA.models.listingState import (
    CompetitorDiscoveryResponse,
    CompetitorItem,
    ProductData,
)
from LSTA.service.amazonService import amazon_service
from LSTA.service.base import service_logger

logger = service_logger

# ── 维度词典（用于从 title 抽取 color / size / style） ──
# 颜色词：统一归一化为小写英文单词，匹配时大小写不敏感
_COLOR_WORDS = [
    "black", "white", "red", "blue", "green", "yellow", "pink", "purple",
    "gray", "grey", "brown", "orange", "beige", "navy", "gold", "silver",
    "rose", "ivory", "khaki", "burgundy", "teal", "turquoise", "maroon",
    "tan", "cream", "lavender", "mint", "coral", "olive", "charcoal",
    "multicolor", "rainbow",
]
# 尺寸词：优先匹配数字单位（如 12inch/16oz/250ml），再匹配服装码（XS/S/M/L/XL/XXL/3XL）
_SIZE_UNIT_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:-)?\s*(inch|inches|in|\"|ft|feet|cm|mm|oz|ml|l|liter|litre|lb|lbs|kg|g|qt|quart|gal|gallon)\b",
    re.IGNORECASE,
)
_SIZE_LETTER_PATTERN = re.compile(
    r"\b(XS|XXS|S|M|L|XL|XXL|XXXL|2XL|3XL|4XL|5XL|Small|Medium|Large|Mini|Queen|King|Twin|Full)\b",
)
# 款式/花色词
_STYLE_WORDS = [
    "solid", "stripe", "striped", "stripes", "floral", "plaid", "polka",
    "checkered", "check", "leopard", "camouflage", "camo", "geometric",
    "abstract", "vintage", "modern", "classic", "minimalist", "cartoon",
    "gradient", "tie-dye", "ombre", "embroidered", "mesh", "velvet",
    "leather", "knit", "ribbed", "quilted", "pleated", "glossy", "matte",
]


def _extract_color(title: str) -> str:
    """从 title 中抽取主色调（取首个命中的颜色词）。"""
    if not title:
        return ""
    low = title.lower()
    for c in _COLOR_WORDS:
        # 使用单词边界避免部分匹配（如 "reddish" 误中 "red"）
        if re.search(rf"\b{re.escape(c)}\b", low):
            # grey 归一化为 gray
            return "gray" if c == "grey" else c
    return ""


def _extract_size(title: str) -> str:
    """从 title 中抽取尺寸：优先数字+单位，次之服装码。"""
    if not title:
        return ""
    m = _SIZE_UNIT_PATTERN.search(title)
    if m:
        unit = m.group(2).lower()
        if unit == "inches":
            unit = "inch"
        elif unit == '"':
            unit = "inch"
        return f"{m.group(1)}{unit}"
    m2 = _SIZE_LETTER_PATTERN.search(title)
    if m2:
        return m2.group(1).upper() if len(m2.group(1)) <= 4 else m2.group(1).capitalize()
    return ""


def _extract_style(title: str) -> str:
    """从 title 中抽取款式/花色（取首个命中）。"""
    if not title:
        return ""
    low = title.lower()
    for s in _STYLE_WORDS:
        if re.search(rf"\b{re.escape(s)}\b", low):
            # stripe/striped/stripes 归一
            if s in ("stripe", "striped", "stripes"):
                return "stripe"
            if s in ("camouflage", "camo"):
                return "camo"
            if s in ("check", "checkered"):
                return "checkered"
            return s
    return ""


def _get_own_asins() -> Set[str]:
    """从 dim_lingxing_product_info 获取所有自有 ASIN。"""
    try:
        from LDA.service.dbService import db_service
        sql = "SELECT DISTINCT asin FROM dim_lingxing_product_info WHERE asin IS NOT NULL AND asin != ''"
        _, rows = db_service.execute_sql(sql)
        return {r["asin"] for r in rows if r.get("asin")}
    except Exception as e:
        logger.warning("获取自有 ASIN 列表失败（将不做排除过滤）: %s", e)
        return set()


def _search_via_proxy(keywords: str, marketplace: str, max_pages: int = 2) -> List[Dict[str, Any]]:
    """调用虚拟机代理的 /search 端点。"""
    if not SCRAPER_PROXY_URL:
        raise RuntimeError("未配置 SCRAPER_PROXY_URL")
    url = f"{SCRAPER_PROXY_URL.rstrip('/')}/search"
    resp = requests.post(
        url,
        json={"keywords": keywords, "marketplace": marketplace, "max_pages": max_pages},
        timeout=FETCH_TIMEOUT + 60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"搜索代理返回 {resp.status_code}")
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(body.get("error", "搜索失败"))
    return body.get("results", [])


def _extract_numeric_price(price_str: str) -> Optional[float]:
    """从价格字符串中提取数值。"""
    if not price_str:
        return None
    m = re.search(r"[\d,]+\.?\d*", price_str.replace(",", ""))
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None


def _build_search_keywords(product: ProductData, color: str = "") -> str:
    """从产品数据中提取搜索关键词。取标题前几个主要词 + 类目，可选追加颜色维度。

    - color：来自 leang_product_info.colour（或上层显式传入），若 title 中尚未包含
      该颜色词，则将其拼接到关键词最前面，使 Amazon 搜索命中更精确的同色系竞品。
    """
    title = product.title or ""
    title_words = re.findall(r"[A-Za-z\u4e00-\u9fff]+(?:'s)?|\d+(?:\.\d+)?", title)
    keep = [w for w in title_words[:12] if len(w) > 1]
    kw = " ".join(keep)
    if product.category and product.category not in kw:
        kw += f" {product.category}"
    color_norm = (color or "").strip()
    if color_norm and color_norm.lower() not in kw.lower():
        kw = f"{color_norm} {kw}"
    return kw[:200].strip()


def _aggregate_dimensions(items: List[CompetitorItem]) -> Dict[str, List[str]]:
    """统计集合中各维度的出现频次，返回频次倒序的值列表，供前端勾选筛选。"""
    colors = Counter(it.color for it in items if it.color)
    sizes = Counter(it.size for it in items if it.size)
    styles = Counter(it.style for it in items if it.style)
    return {
        "colors": [v for v, _ in colors.most_common()],
        "sizes": [v for v, _ in sizes.most_common()],
        "styles": [v for v, _ in styles.most_common()],
    }


def _fetch_product_details_concurrent(
    items: List[CompetitorItem],
    marketplace: str,
    max_workers: int = 5,
) -> None:
    """并发抓取每条竞品的完整 ProductData，并就地填入 item.product_data。失败忽略。"""
    if not items:
        return

    def _one(it: CompetitorItem):
        try:
            pd = amazon_service.fetch(it.asin, marketplace)
            it.product_data = pd
        except Exception as e:
            logger.warning("竞品详情抓取失败 %s: %s", it.asin, e)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(len(items), max_workers),
    ) as pool:
        list(pool.map(_one, items))


def discover_competitors(
    asin: str,
    marketplace: str = "US",
    date_range: int = 30,
    price_tolerance: float = 0.3,
    max_results: int = 20,
    with_details: bool = False,
    color: Optional[str] = None,
) -> CompetitorDiscoveryResponse:
    """主入口：fetch 本品 → Amazon 搜索 → 过滤 → 排除自有。

    参数：
        with_details: True 时并发 fetch 每条竞品的完整 ProductData（用于大模型
            做竞品差异化对比）。代价是单次请求耗时增加 5-15 秒。
        color: 搜索时附加的颜色维度。None / 空字符串 时自动从 leang_product_info.colour
            按 asin 查询；查不到则不加颜色维度，行为回退到旧版本。
    """

    logger.info("竞品发现: 获取本品 %s (%s)", asin, marketplace)
    try:
        source = amazon_service.fetch(asin, marketplace)
    except Exception as e:
        return CompetitorDiscoveryResponse(
            source_asin=asin,
            error=f"获取本品数据失败: {e}",
        )

    src_price = _extract_numeric_price(source.price)
    if not src_price or src_price <= 0:
        return CompetitorDiscoveryResponse(
            source_asin=asin,
            source_category_2=source.category,
            error="本品无有效价格，无法做价格过滤",
        )

    price_lo = src_price * (1 - price_tolerance)
    price_hi = src_price * (1 + price_tolerance)

    # 颜色维度：上层未显式传入时，后端自动查 leang_product_info.colour
    color_arg = (color or "").strip()
    if not color_arg:
        try:
            from LSTA.service.productDimService import query_product_color
            color_arg = query_product_color(asin)
            if color_arg:
                logger.info("竞品发现: 从 leang_product_info 查到颜色=%s", color_arg)
        except Exception as e:
            logger.warning("竞品发现: 查询产品颜色失败（忽略，不阻塞搜索）: %s", e)
            color_arg = ""

    keywords = _build_search_keywords(source, color=color_arg)
    logger.info(
        "竞品发现: 搜索关键词=%s, 颜色=%s, 价格区间=[%.2f, %.2f]",
        keywords[:80], color_arg or "-", price_lo, price_hi,
    )

    try:
        raw_results = _search_via_proxy(keywords, marketplace, max_pages=2)
    except Exception as e:
        return CompetitorDiscoveryResponse(
            source_asin=asin,
            source_category_2=source.category,
            source_avg_price=src_price,
            error=f"Amazon 搜索失败: {e}",
        )

    logger.info("竞品发现: 搜索返回 %d 个结果", len(raw_results))

    own_asins = _get_own_asins()
    own_asins.add(asin)

    candidates: List[CompetitorItem] = []
    for r in raw_results:
        r_asin = r.get("asin", "")
        if not r_asin or r_asin in own_asins:
            continue
        if r.get("is_sponsored"):
            continue

        r_price = _extract_numeric_price(r.get("price", ""))
        if r_price is None:
            continue
        if not (price_lo <= r_price <= price_hi):
            continue

        r_title = r.get("title", "")
        # 维度抽取：优先使用 proxy 原生字段（若有），否则从 title 解析
        color = (r.get("color") or _extract_color(r_title)).strip().lower()
        size = (r.get("size") or _extract_size(r_title)).strip()
        style = (r.get("style") or r.get("pattern") or _extract_style(r_title)).strip().lower()

        candidates.append(CompetitorItem(
            asin=r_asin,
            title=r_title,
            price=r.get("price", ""),
            currency=r.get("currency", ""),
            rating=r.get("rating", ""),
            review_count=r.get("review_count", ""),
            image=r.get("image", ""),
            avg_price=r_price,
            color=color,
            size=size,
            style=style,
        ))

    candidates.sort(
        key=lambda c: int(c.review_count) if c.review_count.isdigit() else 0,
        reverse=True,
    )
    candidates = candidates[:max_results]

    # 如需大模型做差异化描述，这里并发抓取每条竞品的完整 ProductData
    if with_details and candidates:
        logger.info("竞品发现: 并发抓取 %d 条竞品详情用于差异化", len(candidates))
        _fetch_product_details_concurrent(candidates, marketplace)

    logger.info("竞品发现: 过滤后 %d 条竞品", len(candidates))

    dims = _aggregate_dimensions(candidates)
    return CompetitorDiscoveryResponse(
        source_asin=asin,
        source_category_2=source.category,
        source_avg_price=src_price,
        source_total_volume=None,
        competitors=candidates,
        total_found=len(candidates),
        available_colors=dims["colors"],
        available_sizes=dims["sizes"],
        available_styles=dims["styles"],
    )
