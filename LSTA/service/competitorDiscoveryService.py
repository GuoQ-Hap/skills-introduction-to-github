"""竞品发现服务 —— 通过 Amazon 搜索抓取竞品，按价格/评论数/颜色/尺寸/款式五维过滤，排除自有 ASIN。

五维过滤规则
────────────
① 价格（必选）：竞品价须在本品价 ±price_tolerance 范围内（默认 ±30%）。
② 销量/评论数（可选）：竞品评论数 ≥ min_review_count；0 表示不限（默认不限）。
③ 颜色（可选）：filter_by_color=True 且本品有颜色（color 参数或库中查得）时，仅保留颜色相同或颜色未知的竞品。
④ 尺寸（可选）：filter_by_size=True 且本品有可解析尺寸时，仅保留尺寸相同或尺寸未知的竞品。
⑤ 款式（可选）：filter_by_style=True 且本品有可解析款式时，仅保留款式相同或款式未知的竞品。

⚠  颜色/尺寸/款式过滤均依赖从标题或代理字段抽取的维度词，若抽取结果不准确可关闭对应开关。
"""
from __future__ import annotations

import concurrent.futures
import json
import os
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
from LSTA.service.amazonService import amazon_service, _normalize_price
from LSTA.service.base import service_logger

logger = service_logger

_MARKET_DEFAULT_CURRENCY = {
    "US": "USD", "UK": "GBP", "GB": "GBP", "DE": "EUR", "FR": "EUR",
    "IT": "EUR", "ES": "EUR", "NL": "EUR", "JP": "JPY", "CA": "CAD",
    "AU": "AUD", "MX": "MXN",
}

COMPETITOR_DETAIL_WORKERS = int(os.getenv("LSTA_COMPETITOR_DETAIL_WORKERS", "1"))
COMPETITOR_DETAIL_POOL_MULTIPLIER = int(os.getenv("LSTA_COMPETITOR_DETAIL_POOL_MULTIPLIER", "4"))
COMPETITOR_DETAIL_POOL_MIN = int(os.getenv("LSTA_COMPETITOR_DETAIL_POOL_MIN", "20"))
COMPETITOR_SEARCH_PAGES = int(os.getenv("LSTA_COMPETITOR_SEARCH_PAGES", "2"))

_TITLE_STOPWORDS = {
    "for", "and", "with", "the", "a", "an", "of", "to", "in", "on", "by", "or",
    "from", "as", "at", "is", "are", "new", "pack", "set", "pcs", "piece",
    "pieces", "amazon", "home", "office", "visit", "store",
    # 常见品牌/系列词不应用来搜索竞品，否则会搜回自家货。
    "lahome", "elise",
}

_ZH_SEARCH_TERM_MAP = [
    (("圆形", "地毯"), "round rug"),
    (("可水洗", "地毯"), "washable rug"),
    (("柔软", "地毯"), "soft rug"),
    (("防滑", "地毯"), "non slip rug"),
    (("区域", "地毯"), "area rug"),
    (("桌垫",), "desk mat"),
    (("鼠标垫",), "mouse pad"),
    (("腕托",), "wrist rest"),
]

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
    "moroccan", "boho", "bohemian",
]

_ZH_COLOR_MAP = [
    ("黑色", "black"),
    ("白色", "white"),
    ("红色", "red"),
    ("蓝色", "blue"),
    ("绿色", "green"),
    ("黄色", "yellow"),
    ("粉色", "pink"),
    ("紫色", "purple"),
    ("灰色", "gray"),
    ("棕色", "brown"),
    ("橙色", "orange"),
    ("米色", "beige"),
    ("金色", "gold"),
    ("银色", "silver"),
    ("多色", "multicolor"),
]

_ZH_STYLE_MAP = [
    ("摩洛哥", "moroccan"),
    ("格子", "checkered"),
    ("复古", "vintage"),
    ("波西米亚", "boho"),
    ("几何", "geometric"),
    ("花卉", "floral"),
    ("条纹", "striped"),
    ("纯色", "solid"),
    ("渐变", "gradient"),
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
    for zh, en in _ZH_COLOR_MAP:
        if zh in title:
            return en
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
    for zh, en in _ZH_STYLE_MAP:
        if zh in title:
            return en
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


def _price_and_currency(price: str, currency: str, marketplace: str) -> tuple[Optional[float], str]:
    """归一化价格和币种，避免 CNY/USD 等混在一起直接比较。"""
    norm_price, norm_currency = _normalize_price(price or "", currency or "", marketplace.upper())
    return _extract_numeric_price(norm_price), (norm_currency or "").upper()


def _title_terms(title: str) -> Set[str]:
    terms = set()
    for t in re.findall(r"[A-Za-z][A-Za-z0-9']+|\d+(?:\.\d+)?", title or ""):
        tl = t.lower().strip("'")
        if len(tl) <= 1 or tl in _TITLE_STOPWORDS:
            continue
        terms.add(tl)
    return terms


def _title_similarity(a: str, b: str) -> float:
    aa = _title_terms(a)
    bb = _title_terms(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, len(aa | bb))


def _review_count_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    txt = str(value or "").replace(",", "").replace(".", "").strip()
    return int(txt) if txt.isdigit() else 0


def _build_search_keywords(product: ProductData, color: str = "", include_color: bool = False) -> str:
    """从产品数据中提取更干净的搜索关键词。

    只取英文核心词和尺寸数字，不再把中文类目 breadcrumb 原样塞进搜索框。
    颜色只有明确启用颜色过滤时才加入，避免自动竞品发现被颜色词过度收窄。
    """
    title = product.title or ""
    brand_words = {
        w.lower().strip("'")
        for w in re.findall(r"[A-Za-z][A-Za-z0-9']+", product.brand or "")
        if len(w) > 1
    }
    # Amazon 抓取到的 brand 有时是"访问 XXX 品牌旗舰店"，从 title 开头补一层品牌词排除。
    title_brand = re.match(r"^\s*([A-Za-z][A-Za-z0-9']+)", title)
    if title_brand:
        brand_words.add(title_brand.group(1).lower().strip("'"))
    title_color = _extract_color(title)
    title_style = _extract_style(title)
    keyword_prefix: List[str] = []
    color_norm = (color or title_color or "").strip().lower()
    if color_norm:
        if color_norm == "grey":
            color_norm = "gray"
        keyword_prefix.extend(color_norm.split())
    if title_style:
        keyword_prefix.extend(title_style.split())

    title_words = re.findall(r"[A-Za-z][A-Za-z0-9']+|\d+(?:\.\d+)?", title)
    keep: List[str] = []
    seen: Set[str] = set()
    for w in keyword_prefix:
        wl = w.lower().strip("'")
        if len(wl) > 1 and wl not in _TITLE_STOPWORDS and wl not in brand_words and wl not in seen:
            keep.append(w)
            seen.add(wl)
    for w in title_words:
        wl = w.lower().strip("'")
        if len(wl) <= 1 or wl in _TITLE_STOPWORDS or wl in brand_words or wl in seen:
            continue
        keep.append(w)
        seen.add(wl)
        if len(keep) >= 9:
            break

    for needles, mapped in _ZH_SEARCH_TERM_MAP:
        if all(n in title for n in needles):
            for part in mapped.split():
                if part.lower() not in seen:
                    keep.append(part)
                    seen.add(part.lower())
            if len(keep) >= 8:
                break

    category_tail = (product.category or "").split(">")[-1].strip()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9']+", category_tail):
        wl = w.lower().strip("'")
        if len(wl) > 1 and wl not in _TITLE_STOPWORDS and wl not in brand_words and wl not in seen:
            keep.append(w)
            seen.add(wl)
            if len(keep) >= 10:
                break

    color_norm = (color or "").strip()
    if include_color and color_norm and color_norm.lower() not in seen:
        keep.insert(0, color_norm)
    return " ".join(keep)[:160].strip()


def _extract_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _clean_search_keywords(text: str, product: ProductData) -> str:
    brand_words = {
        w.lower().strip("'")
        for w in re.findall(r"[A-Za-z][A-Za-z0-9']+", product.brand or "")
        if len(w) > 1
    }
    title_brand = re.match(r"^\s*([A-Za-z][A-Za-z0-9']+)", product.title or "")
    if title_brand:
        brand_words.add(title_brand.group(1).lower().strip("'"))

    words: List[str] = []
    seen: Set[str] = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]+|\d+(?:\.\d+)?", text or ""):
        wl = w.lower().strip("'")
        is_number = bool(re.fullmatch(r"\d+(?:\.\d+)?", wl))
        if (len(wl) <= 1 and not is_number) or wl in _TITLE_STOPWORDS or wl in brand_words or wl in seen:
            continue
        words.append(w)
        seen.add(wl)
        if len(words) >= 10:
            break
    return " ".join(words)[:160].strip()


def _build_ai_competitor_search_keywords(product: ProductData, color: str = "") -> str:
    """用主图 + Listing 文本让视觉模型生成更贴近竞品检索的英文关键词。失败返回空串。"""
    image_url = (product.images or [""])[0] if product.images else ""
    bullets = "; ".join((product.bullet_points or [])[:3])
    desc = (product.description or "")[:600]
    prompt = f"""
你是 Amazon 竞品检索专家。请基于商品主图和文本信息，生成一个英文 Amazon 搜索词，用来查找"同类竞品"，不是查找本品牌/本系列。

要求：
1. 输出 JSON，且只能输出 JSON。
2. search_keywords 必须是英文短语，4-10 个词。
3. 必须包含从主图/标题判断出的产品类型、颜色、风格/花色、关键尺寸或形状。
4. 必须排除品牌词、店铺词、系列名、ASIN、营销词，不要出现 Lahome、Elise 等品牌/系列词。
5. 不要使用过窄的长标题；要像真实 Amazon 搜索框关键词。

JSON 格式：
{{
  "search_keywords": "black moroccan round rug washable non slip",
  "product_type": "round rug",
  "color_style": "black moroccan",
  "size_shape": "6 ft round",
  "excluded_brand_terms": ["..."]
}}

商品信息：
- ASIN: {product.asin}
- 品牌: {product.brand or "未知"}
- 标题: {product.title or ""}
- 颜色字段: {color or "未知"}
- 类目: {product.category or ""}
- 五点: {bullets}
- 描述: {desc}
""".strip()

    content: List[Dict[str, Any]] = []
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    content.append({"type": "text", "text": prompt})

    try:
        from admin.model_pool import model_pool

        raw = model_pool.call_llm(
            messages=[
                {"role": "system", "content": "你是严谨的电商视觉识别与竞品检索关键词专家，只输出 JSON。"},
                {"role": "user", "content": content},
            ],
            temperature=0.1,
            max_tokens=500,
            timeout=90,
            _log_module="competitor_keyword_vision",
        )
        data = _extract_json_object(raw)
        kw = _clean_search_keywords(str(data.get("search_keywords") or ""), product)
        if kw:
            return kw
    except Exception as exc:
        logger.warning("竞品发现: 视觉模型生成搜索词失败，回退规则关键词: %s", exc)
    return ""


def _search_item_score(
    item: CompetitorItem,
    source: ProductData,
    source_price: float,
    source_currency: str,
    search_position: int,
) -> float:
    score = 0.0
    score += max(0.0, 30.0 - search_position) * 1.6
    score += _title_similarity(source.title, item.title) * 70.0
    score += min(_review_count_int(item.review_count), 5000) / 250.0
    try:
        rating = float(str(item.rating or "0").replace(",", "."))
        score += max(0.0, rating - 3.5) * 5.0
    except ValueError:
        pass
    if item.avg_price and source_price > 0 and (item.currency or "").upper() == source_currency:
        closeness = max(0.0, 1.0 - abs(item.avg_price - source_price) / source_price)
        score += closeness * 25.0
    return score


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
    max_workers: int = COMPETITOR_DETAIL_WORKERS,
) -> None:
    """并发抓取每条竞品的完整 ProductData，并就地填入 item.product_data。失败忽略。"""
    if not items:
        return

    def _one(it: CompetitorItem):
        try:
            pd = amazon_service.fetch(it.asin, marketplace)
            it.product_data = pd
            # 同步详情中的 BSR 排名到 CompetitorItem，供前端列表与 prompt 直接使用
            if pd and pd.bsr_rank and not it.bsr_rank:
                it.bsr_rank = pd.bsr_rank
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
    product_data: Optional[ProductData] = None,
    color: Optional[str] = None,
    filter_by_color: bool = False,
    filter_by_size: bool = False,
    filter_by_style: bool = False,
    min_review_count: int = 0,
) -> CompetitorDiscoveryResponse:
    """主入口：fetch 本品 → Amazon 搜索 → 五维过滤 → 排除自有。

    过滤维度（按先后顺序执行）：
      ① 排除无 ASIN / 自有 ASIN / 广告位
      ② 价格带：[本品价×(1-price_tolerance), 本品价×(1+price_tolerance)]
      ③ 最低评论数：竞品评论数 ≥ min_review_count（0=不限）
      ④ 颜色匹配：filter_by_color=True 且本品有颜色时生效
      ⑤ 尺寸匹配：filter_by_size=True 且本品有可解析尺寸时生效
      ⑥ 款式匹配：filter_by_style=True 且本品有可解析款式时生效

    额外参数：
        with_details: True 时并发 fetch 每条竞品完整 ProductData，耗时增加 5-15 秒。
        color: 搜索关键词附加的颜色；None/空时自动查 leang_product_info.colour。
              同时作为 filter_by_color=True 时的颜色基准值。
    """

    logger.info("竞品发现: 获取本品 %s (%s)", asin, marketplace)
    if product_data and product_data.title:
        source = product_data
        logger.info("竞品发现: 复用已获取的本品数据 %s: %s", asin, source.title[:80])
    else:
        try:
            source = amazon_service.fetch(asin, marketplace)
        except Exception as e:
            return CompetitorDiscoveryResponse(
                source_asin=asin,
                error=f"获取本品数据失败: {e}",
            )

    # ── 维度①：价格带计算 ──────────────────────────────────────────────
    src_price, src_currency = _price_and_currency(source.price, source.currency, marketplace)
    if (not src_price or src_price <= 0) and product_data and product_data.title:
        logger.warning(
            "竞品发现: 传入本品数据无有效价格，尝试按 ASIN 重新抓取 asin=%s raw_price=%r currency=%r",
            asin,
            source.price,
            source.currency,
        )
        try:
            refreshed = amazon_service.fetch(asin, marketplace)
            if refreshed and refreshed.title:
                source = refreshed
                src_price, src_currency = _price_and_currency(
                    source.price,
                    source.currency,
                    marketplace,
                )
                logger.info(
                    "竞品发现: 本品价格兜底刷新完成 asin=%s price=%r currency=%r parsed=%s",
                    asin,
                    source.price,
                    source.currency,
                    src_price,
                )
        except Exception as e:
            logger.warning("竞品发现: 本品价格兜底刷新失败 asin=%s: %s", asin, e)
    if not src_price or src_price <= 0:
        return CompetitorDiscoveryResponse(
            source_asin=asin,
            source_category_2=source.category,
            error=f"本品无有效价格，无法做价格过滤（price={source.price or '-'}, currency={source.currency or '-'}）",
        )

    market_currency = _MARKET_DEFAULT_CURRENCY.get(marketplace.upper(), "USD")
    if src_currency and src_currency != market_currency:
        logger.warning(
            "竞品发现: 本品币种 %s 与站点 %s 默认币种 %s 不一致，按站点币种纠偏避免误过滤",
            src_currency, marketplace, market_currency,
        )
        src_currency = market_currency

    price_lo = src_price * (1 - price_tolerance)
    price_hi = src_price * (1 + price_tolerance)

    # ── 本品尺寸 / 款式（用于维度④⑤的基准值） ────────────────────────
    src_size = _extract_size(source.title).strip()
    src_style = _extract_style(source.title).strip().lower()

    # ── 颜色：上层未传时自动查库 ──────────────────────────────────────
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

    keywords = _build_ai_competitor_search_keywords(source, color=color_arg)
    keyword_source = "vision_llm"
    if not keywords:
        keywords = _build_search_keywords(source, color=color_arg, include_color=filter_by_color)
        keyword_source = "rules"
    logger.info(
        "竞品发现: 搜索关键词=%s, keyword_source=%s, 颜色=%s, 价格区间=[%.2f, %.2f] %s, "
        "本品尺寸=%s, 本品款式=%s, "
        "filter_by_color=%s, filter_by_size=%s, filter_by_style=%s, min_review_count=%d",
        keywords[:80], keyword_source, color_arg or "-", price_lo, price_hi, src_currency or "-",
        src_size or "-", src_style or "-",
        filter_by_color, filter_by_size, filter_by_style, min_review_count,
    )

    try:
        raw_results = _search_via_proxy(keywords, marketplace, max_pages=COMPETITOR_SEARCH_PAGES)
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

    # 是否真正启用颜色/尺寸/款式过滤（本品必须有可解析值才有意义）
    # 颜色基准值：优先用 color_arg（已含自动查库逻辑），再从本品标题抽取兜底
    src_color = color_arg.lower() if color_arg else _extract_color(source.title)
    color_filter_active = filter_by_color and bool(src_color)
    size_filter_active = filter_by_size and bool(src_size)
    style_filter_active = filter_by_style and bool(src_style)

    # 保留更大的搜索候选池，但详情抓取按 max_results 分批执行；
    # 若首批详情不足 5 条，才继续抓下一批，兼顾速度和兜底能力。
    detail_pool_limit = max(max_results * COMPETITOR_DETAIL_POOL_MULTIPLIER, COMPETITOR_DETAIL_POOL_MIN)
    preliminary: List[tuple[CompetitorItem, int]] = []
    skip_stats = Counter()
    for idx, r in enumerate(raw_results, start=1):
        # ── 维度①：ASIN / 自有 / 广告 ──────────────────────────────
        r_asin = r.get("asin", "")
        if not r_asin:
            skip_stats["no_asin"] += 1
            continue
        if r_asin in own_asins:
            skip_stats["own_asin"] += 1
            continue
        if r.get("is_sponsored"):
            skip_stats["sponsored"] += 1
            continue

        # ── 维度③：最低评论数 ─────────────────────────────────────────
        if min_review_count > 0:
            rc_from_search = _review_count_int(r.get("review_count", ""))
            if rc_from_search and rc_from_search < min_review_count:
                skip_stats["review_low"] += 1
                continue

        r_title = r.get("title", "")
        # 维度抽取：优先使用 proxy 原生字段（若有），否则从 title 解析
        r_color = (r.get("color") or _extract_color(r_title)).strip().lower()
        r_size  = (r.get("size") or _extract_size(r_title)).strip()
        r_style = (r.get("style") or r.get("pattern") or _extract_style(r_title)).strip().lower()

        # ── 维度④：颜色匹配 ──────────────────────────────────────────
        # 竞品无颜色（抽取失败）视为"未知"，不丢弃；有颜色但与本品不同则过滤。
        if color_filter_active and r_color and r_color != src_color:
            continue

        # ── 维度⑤：尺寸匹配 ──────────────────────────────────────────
        # 竞品无尺寸（抽取失败）视为"未知"，不丢弃；有尺寸但与本品不同则过滤。
        if size_filter_active and r_size and r_size != src_size:
            continue

        # ── 维度⑥：款式匹配 ──────────────────────────────────────────
        if style_filter_active and r_style and r_style != src_style:
            continue

        r_price, r_currency = _price_and_currency(r.get("price", ""), r.get("currency", ""), marketplace)
        item = CompetitorItem(
            asin=r_asin,
            title=r_title,
            price=r.get("price", ""),
            currency=r_currency or r.get("currency", ""),
            rating=r.get("rating", ""),
            review_count=r.get("review_count", ""),
            image=r.get("image", ""),
            avg_price=r_price,
            color=r_color,
            size=r_size,
            style=r_style,
        )
        preliminary.append((item, idx))

    if not preliminary:
        logger.info(
            "竞品发现: 搜索返回 %d 个结果但候选为 0，过滤统计=%s",
            len(raw_results), dict(skip_stats),
        )

    preliminary.sort(
        key=lambda pair: _search_item_score(pair[0], source, src_price, src_currency, pair[1]),
        reverse=True,
    )
    preliminary_total = len(preliminary)
    preliminary = preliminary[:detail_pool_limit]
    position_by_asin = {item.asin: pos for item, pos in preliminary}

    def _passes_final_filters(item: CompetitorItem) -> bool:
        title_for_filter = item.title
        price_for_filter = item.avg_price
        currency_for_filter = (item.currency or "").upper()

        if item.product_data:
            pd = item.product_data
            if pd.title:
                title_for_filter = pd.title
                item.title = pd.title
            detail_price, detail_currency = _price_and_currency(pd.price, pd.currency, marketplace)
            if detail_price is not None:
                price_for_filter = detail_price
                item.avg_price = detail_price
                item.price = pd.price or item.price
            if detail_currency:
                currency_for_filter = detail_currency
                item.currency = detail_currency
            if pd.rating:
                item.rating = pd.rating
            if pd.review_count:
                item.review_count = pd.review_count
            if pd.images and not item.image:
                item.image = pd.images[0]

        if price_for_filter is None:
            return False
        if min_review_count > 0 and _review_count_int(item.review_count) < min_review_count:
            return False
        if currency_for_filter and currency_for_filter != market_currency:
            logger.info(
                "竞品发现: 详情币种 %s 与站点默认 %s 不一致，按站点币种纠偏 asin=%s price=%s",
                currency_for_filter, market_currency, item.asin, item.price,
            )
            currency_for_filter = market_currency
            item.currency = market_currency
        if src_currency and currency_for_filter and currency_for_filter != src_currency:
            logger.info(
                "竞品发现: 跳过 %s，币种不一致 source=%s item=%s price=%s",
                item.asin, src_currency, currency_for_filter, item.price,
            )
            return False
        if not (price_lo <= price_for_filter <= price_hi):
            return False

        item.color = (_extract_color(title_for_filter) or item.color).strip().lower()
        item.size = (_extract_size(title_for_filter) or item.size).strip()
        item.style = (_extract_style(title_for_filter) or item.style).strip().lower()
        if color_filter_active and item.color and item.color != src_color:
            return False
        if size_filter_active and item.size and item.size != src_size:
            return False
        if style_filter_active and item.style and item.style != src_style:
            return False

        return True

    candidates: List[CompetitorItem] = []
    if with_details:
        # 分批补抓：每批只抓 max_results 条详情，若有效详情不足 5 条再继续往后补。
        detail_batch_size = max(1, max_results)
        detail_items = [item for item, _ in preliminary]
        fallback_items: List[CompetitorItem] = []
        for start in range(0, len(detail_items), detail_batch_size):
            if len(candidates) >= max_results:
                break
            batch = detail_items[start:start + detail_batch_size]
            logger.info(
                "竞品发现: 搜索候选 %d 条，抓取第 %d-%d 条详情用于最终筛选，workers=%d",
                preliminary_total, start + 1, start + len(batch), COMPETITOR_DETAIL_WORKERS,
            )
            _fetch_product_details_concurrent(batch, marketplace)
            for item in batch:
                if _passes_final_filters(item):
                    if item.product_data and item.product_data.title:
                        candidates.append(item)
                        if len(candidates) >= max_results:
                            break
                    else:
                        fallback_items.append(item)
        if len(candidates) < max_results and fallback_items:
            seen = {item.asin for item in candidates}
            for item in fallback_items:
                if item.asin in seen:
                    continue
                candidates.append(item)
                seen.add(item.asin)
                if len(candidates) >= max_results:
                    break
    else:
        for item, _ in preliminary:
            if _passes_final_filters(item):
                candidates.append(item)
                if len(candidates) >= max_results:
                    break

    candidates.sort(
        key=lambda c: _search_item_score(
            c, source, src_price, src_currency, position_by_asin.get(c.asin, 999)
        ),
        reverse=True,
    )
    candidates = candidates[:max_results]

    logger.info(
        "竞品发现: 最终 %d 条竞品（color_filter=%s/%s, size_filter=%s/%s, style_filter=%s/%s, min_rc=%d）",
        len(candidates),
        color_filter_active, src_color or "-",
        size_filter_active, src_size or "-",
        style_filter_active, src_style or "-",
        min_review_count,
    )

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
