"""
Amazon 抓取代理服务 —— 部署在 Windows 虚拟机上，对外提供 HTTP API。
主服务通过调用本服务实现「虚拟 IP」效果：不同机器出口 IP 不同，降低被封风险。

启动方式：
    pip install -r requirements.txt
    python scraper_server.py            # 默认监听 0.0.0.0:9100
    python scraper_server.py --port 9100 --host 0.0.0.0

API：
    POST /scrape    {"asin": "B0XXXXXXXX", "marketplace": "US"}
    GET  /health    健康检查
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import uvicorn
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════

MARKETPLACE_DOMAINS = {
    "US": "www.amazon.com",
    "UK": "www.amazon.co.uk",
    "DE": "www.amazon.de",
    "JP": "www.amazon.co.jp",
    "CA": "www.amazon.ca",
    "FR": "www.amazon.fr",
    "IT": "www.amazon.it",
    "ES": "www.amazon.es",
    "AU": "www.amazon.com.au",
    "MX": "www.amazon.com.mx",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
]

URL_PATTERNS = [
    "https://{domain}/dp/{asin}",
    "https://{domain}/gp/product/{asin}",
    "https://{domain}/dp/{asin}?th=1&psc=1",
]

FETCH_TIMEOUT = 30
MAX_RETRIES = 4

# ═══════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════

class ScrapeRequest(BaseModel):
    asin: str = Field(..., min_length=10, max_length=10)
    marketplace: str = Field("US")

class SearchRequest(BaseModel):
    keywords: str = Field(..., min_length=1, max_length=500)
    marketplace: str = Field("US")
    max_pages: int = Field(1, ge=1, le=3)

class ReviewItem(BaseModel):
    stars: float = 0
    title: str = ""
    body: str = ""
    date: str = ""

class SearchResultItem(BaseModel):
    asin: str = ""
    title: str = ""
    price: str = ""
    currency: str = ""
    rating: str = ""
    review_count: str = ""
    bsr_rank: str = ""
    image: str = ""
    is_sponsored: bool = False

class SearchResponse(BaseModel):
    success: bool
    query: str = ""
    marketplace: str = ""
    results: List[SearchResultItem] = []
    total_found: int = 0
    error: str = ""

class ProductResult(BaseModel):
    asin: str = ""
    marketplace: str = ""
    title: str = ""
    brand: str = ""
    price: str = ""
    currency: str = ""
    rating: str = ""
    review_count: str = ""
    bullet_points: List[str] = []
    description: str = ""
    category: str = ""
    bsr_rank: str = ""
    images: List[str] = []
    reviews: List[ReviewItem] = []

class ScrapeResponse(BaseModel):
    success: bool
    data: Optional[ProductResult] = None
    error: str = ""
    debug: Dict[str, Any] = {}

# ═══════════════════════════════════════════════
# 抓取引擎
# ═══════════════════════════════════════════════

class Scraper:
    def __init__(self):
        self._session: Optional[requests.Session] = None
        self._warmed: set = set()
        self._last_html: str = ""
        self._last_review_html: str = ""

    def scrape(self, asin: str, marketplace: str) -> ProductResult:
        marketplace = marketplace.upper()
        if marketplace not in MARKETPLACE_DOMAINS:
            raise ValueError(f"不支持的站点: {marketplace}")
        domain = MARKETPLACE_DOMAINS[marketplace]
        last_err: Optional[Exception] = None

        for attempt in range(MAX_RETRIES):
            url = URL_PATTERNS[attempt % len(URL_PATTERNS)].format(domain=domain, asin=asin)

            if attempt > 0:
                wait = min(2 ** attempt + random.uniform(0, 2), 15)
                print(f"[重试 {attempt+1}/{MAX_RETRIES}] 等待 {wait:.1f}s → {url}")
                self._reset_session()
                time.sleep(wait)

            try:
                product = self._do_fetch(url, asin, marketplace, domain, attempt)
                if product.title and product.title.strip():
                    return product
                print(f"[警告] 第 {attempt+1} 次: 页面解析成功但 title 为空")
                last_err = ValueError("title 为空")
            except Exception as e:
                print(f"[失败] 第 {attempt+1}/{MAX_RETRIES} 次: {e}")
                last_err = e

        raise RuntimeError(f"{MAX_RETRIES} 次尝试均失败，最后错误: {last_err}")

    def _fetch_reviews_page(self, asin: str, domain: str) -> List[ReviewItem]:
        """单独请求 Amazon 评论页获取 Top Reviews。"""
        review_url = f"https://{domain}/product-reviews/{asin}?sortBy=recent&pageNumber=1"
        try:
            session = self._get_session(domain)
            delay = random.uniform(1.0, 2.5)
            print(f"[评论] 请求评论页: {review_url} (延迟 {delay:.1f}s)")
            time.sleep(delay)
            resp = session.get(review_url, timeout=FETCH_TIMEOUT, allow_redirects=True)
            self._last_review_html = resp.text
            print(f"[评论] 评论页状态码={resp.status_code} HTML长度={len(resp.text)}")
            if resp.status_code != 200:
                print(f"[评论] 评论页返回 {resp.status_code}")
                return []
            if "captcha" in resp.text.lower()[:2000] or "robot" in resp.text.lower()[:2000]:
                print("[评论] 评论页命中 CAPTCHA")
                return []
            if "RXVM" in resp.text[:5000] or "main-canvas" in resp.text[:5000]:
                print("[评论] 评论页命中 JS 挑战页面")
                return []
            soup = BeautifulSoup(resp.text, "lxml")
            reviews = self._reviews(soup)
            print(f"[评论] 解析到 {len(reviews)} 条评论")
            return reviews
        except Exception as e:
            print(f"[评论] 评论页抓取失败: {e}")
            return []

    def _do_fetch(self, url: str, asin: str, marketplace: str, domain: str, attempt: int) -> ProductResult:
        session = self._get_session(domain)
        self._warmup(session, domain)

        delay = random.uniform(1.5, 4) + attempt * 0.5
        print(f"[抓取] {url} (延迟 {delay:.1f}s)")
        time.sleep(delay)

        resp = session.get(url, timeout=FETCH_TIMEOUT, allow_redirects=True)

        if resp.status_code == 404:
            raise ValueError(f"ASIN {asin} 在 {marketplace} 不存在")
        if resp.status_code == 503:
            raise RuntimeError("Amazon 503 — 反爬触发")
        if resp.status_code == 429:
            raise RuntimeError("Amazon 429 — 请求过于频繁")
        if "captcha" in resp.text.lower() or "robot" in resp.text.lower()[:2000]:
            raise RuntimeError("命中 CAPTCHA 验证码页面")
        if resp.status_code != 200:
            raise RuntimeError(f"异常状态码: {resp.status_code}")

        self._last_html = resp.text
        return self._parse(resp.text, asin, marketplace)

    # ── Session 管理 ──

    def _get_session(self, domain: str) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        ua = random.choice(USER_AGENTS)
        self._session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": f"https://{domain}/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        })
        return self._session

    def _warmup(self, session: requests.Session, domain: str):
        if domain in self._warmed:
            return
        try:
            print(f"[预热] 访问 https://{domain}/ 获取 cookie")
            time.sleep(random.uniform(0.5, 1.5))
            session.get(f"https://{domain}/", timeout=15, allow_redirects=True)
            self._warmed.add(domain)
        except Exception as e:
            print(f"[预热失败] {e}")

    def _reset_session(self):
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
        self._session = None
        self._warmed.clear()

    # ── HTML 解析 ──

    def _parse(self, html: str, asin: str, marketplace: str) -> ProductResult:
        soup = BeautifulSoup(html, "lxml")
        jld = self._json_ld(soup)
        title = self._title(soup, jld)
        brand = self._brand(soup, jld)
        price, currency = self._price(soup, jld)
        rating, reviews = self._rating(soup, jld)
        bullets = self._bullets(soup)
        desc = self._description(soup)
        cat = self._category(soup)
        bsr = self._bsr(soup)
        imgs = self._images(soup, jld)
        review_list = self._reviews(soup)

        return ProductResult(
            asin=asin, marketplace=marketplace,
            title=title, brand=brand, price=price, currency=currency,
            rating=rating, review_count=reviews,
            bullet_points=bullets, description=desc,
            category=cat, bsr_rank=bsr, images=imgs[:5],
            reviews=review_list,
        )

    @staticmethod
    def _json_ld(soup: BeautifulSoup) -> Dict[str, Any]:
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                if isinstance(data, dict) and data.get("@type") == "Product":
                    return data
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Product":
                            return item
            except (json.JSONDecodeError, TypeError):
                continue
        return {}

    @staticmethod
    def _title(soup: BeautifulSoup, jld: Dict) -> str:
        if jld.get("name"):
            return jld["name"].strip()
        for el in [
            soup.find("span", {"id": "productTitle"}),
            soup.find(id="productTitle"),
            soup.find("h1", {"id": "title"}),
            soup.select_one("#title span"),
            soup.find("title"),
        ]:
            if el:
                t = el.get_text(strip=True)
                if t and "Amazon" not in t[:10]:
                    return t
        return ""

    @staticmethod
    def _brand(soup: BeautifulSoup, jld: Dict) -> str:
        b = jld.get("brand")
        if isinstance(b, dict) and b.get("name"):
            return b["name"].strip()
        if isinstance(b, str):
            return b.strip()
        for el in [
            soup.find(id="bylineInfo"),
            soup.find("a", {"id": "bylineInfo"}),
            soup.select_one("a.a-link-normal[href*='brandtextbin']"),
        ]:
            if el:
                t = el.get_text(strip=True)
                for p in ("Brand: ", "Visit the ", "ブランド: ", "Marke: "):
                    if t.startswith(p):
                        t = t[len(p):]
                return t.replace(" Store", "").strip()
        return ""

    @staticmethod
    def _price(soup: BeautifulSoup, jld: Dict) -> Tuple[str, str]:
        _sym_map = {
            "$": "USD", "US$": "USD", "£": "GBP", "€": "EUR",
            "¥": "JPY", "￥": "CNY", "CA$": "CAD", "C$": "CAD",
            "A$": "AUD", "AU$": "AUD", "MX$": "MXN",
            "CNY": "CNY", "RMB": "CNY", "USD": "USD", "GBP": "GBP",
            "EUR": "EUR", "JPY": "JPY", "CAD": "CAD", "AUD": "AUD", "MXN": "MXN",
        }

        def _split(raw: str) -> Tuple[str, str]:
            """从带货币符号的价格文本中分离数字和货币代码。"""
            s = raw.strip()
            if not s:
                return "", ""
            for sym in sorted(_sym_map, key=len, reverse=True):
                if s.upper().startswith(sym.upper()):
                    return re.sub(r"[^\d.,]", "", s[len(sym):]).strip(" ,."), _sym_map[sym]
                if s.upper().endswith(sym.upper()):
                    return re.sub(r"[^\d.,]", "", s[:-len(sym)]).strip(" ,."), _sym_map[sym]
            return re.sub(r"[^\d.,]", "", s).strip(" ,."), ""

        offers = jld.get("offers")
        if isinstance(offers, dict) and offers.get("price"):
            p = str(offers["price"])
            c = offers.get("priceCurrency", "")
            num, emb = _split(p)
            return num or p, emb or c or "USD"
        if isinstance(offers, list) and offers and offers[0].get("price"):
            p = str(offers[0]["price"])
            c = offers[0].get("priceCurrency", "")
            num, emb = _split(p)
            return num or p, emb or c or "USD"

        for el in [
            soup.find("span", {"id": "priceblock_ourprice"}),
            soup.find("span", {"id": "priceblock_dealprice"}),
            soup.select_one("span.a-price .a-offscreen"),
            soup.select_one("#corePrice_feature_div .a-offscreen"),
            soup.select_one("#price_inside_buybox"),
            soup.select_one(".a-price .a-offscreen"),
        ]:
            if el:
                raw = el.get_text(strip=True)
                if raw:
                    num, cur = _split(raw)
                    return num or raw, cur
        return "", ""

    @staticmethod
    def _rating(soup: BeautifulSoup, jld: Dict) -> Tuple[str, str]:
        ar = jld.get("aggregateRating", {})
        if ar:
            return str(ar.get("ratingValue", "")), str(ar.get("reviewCount", ar.get("ratingCount", "")))
        rating_val = ""
        for el in [
            soup.select_one("#acrPopover .a-icon-alt"),
            soup.select_one("i.a-icon-star-small .a-icon-alt"),
            soup.select_one("span.a-icon-alt"),
        ]:
            if el:
                m = re.search(r"[\d.]+", el.get_text(strip=True))
                if m:
                    rating_val = m.group()
                    break
        count_val = ""
        for el in [
            soup.find(id="acrCustomerReviewText"),
            soup.select_one("#acrCustomerReviewLink span"),
        ]:
            if el:
                m = re.search(r"[\d,]+", el.get_text(strip=True))
                if m:
                    count_val = m.group().replace(",", "")
                    break
        return rating_val, count_val

    @staticmethod
    def _bullets(soup: BeautifulSoup) -> List[str]:
        container = soup.find(id="feature-bullets") or soup.find("div", {"id": "feature-bullets"})
        if not container:
            return []
        items = container.select("li .a-list-item") or container.find_all("li")
        return [i.get_text(strip=True) for i in items
                if i.get_text(strip=True) and len(i.get_text(strip=True)) > 5 and "Javascript" not in i.get_text()]

    @staticmethod
    def _description(soup: BeautifulSoup) -> str:
        for el in [soup.find("div", {"id": "productDescription"}), soup.find(id="productDescription")]:
            if el:
                t = el.get_text(" ", strip=True)
                if t:
                    return t
        aplus = soup.find(id="aplus") or soup.find("div", {"id": "aplus_feature_div"})
        if aplus:
            texts = [p.get_text(strip=True) for p in aplus.find_all(["p", "h3", "h4", "span"])]
            r = "\n".join(t for t in texts if t and len(t) > 3)
            if r:
                return r
        return ""

    @staticmethod
    def _category(soup: BeautifulSoup) -> str:
        bc = soup.find(id="wayfinding-breadcrumbs_feature_div")
        if bc:
            parts = [a.get_text(strip=True) for a in bc.select("a") if a.get_text(strip=True)]
            if parts:
                return " > ".join(parts)
        return ""

    @staticmethod
    def _bsr(soup: BeautifulSoup) -> str:
        bsr_keywords = (
            "Best Sellers Rank", "Amazon Bestseller-Rang",
            "Classement des meilleures ventes", "Clasificación en los más vendidos",
            "Bestseller-Rang", "ベストセラーランク", "Best Seller Rank",
            "Amazon Best Sellers Rank",
        )

        # 1) 详情表格 (productDetails_detailBullets_sections1)
        details = soup.find(id="productDetails_detailBullets_sections1")
        if details:
            for row in details.find_all("tr"):
                h = row.find("th")
                if h and any(kw in h.get_text() for kw in bsr_keywords):
                    v = row.find("td")
                    if v:
                        raw = v.get_text(strip=True).split("\n")[0].strip()
                        m = re.search(r"#?([\d,.\s]+)", raw)
                        return m.group(1).replace(",", "").replace(".", "").strip() if m else raw[:200]

        # 2) SalesRank 元素
        for el in [soup.find(id="SalesRank"), soup.find("li", {"id": "SalesRank"})]:
            if el:
                text = el.get_text(strip=True)
                m = re.search(r"#?([\d,.\s]+)", text)
                return m.group(1).replace(",", "").replace(".", "").strip() if m else text[:200]

        # 3) detailBulletsWrapper
        db = soup.find(id="detailBulletsWrapper_feature_div")
        if db:
            for li in db.find_all("li"):
                t = li.get_text(strip=True)
                if any(kw in t for kw in bsr_keywords):
                    m = re.search(r"#?([\d,.\s]+)", t)
                    return m.group(1).replace(",", "").replace(".", "").strip() if m else t[:200]

        # 4) 新版页面: #detailBullets_feature_div
        db2 = soup.find(id="detailBullets_feature_div")
        if db2:
            for span in db2.find_all("span"):
                t = span.get_text(strip=True)
                if any(kw in t for kw in bsr_keywords):
                    m = re.search(r"#?([\d,.\s]+)", t)
                    return m.group(1).replace(",", "").replace(".", "").strip() if m else t[:200]

        # 5) 全文兜底搜索
        body_text = soup.get_text()
        for kw in bsr_keywords:
            idx = body_text.find(kw)
            if idx >= 0:
                after = body_text[idx:idx + 200]
                m = re.search(r"#?([\d,]+)", after)
                if m:
                    return m.group(1).replace(",", "").strip()

        return ""

    @staticmethod
    def _images(soup: BeautifulSoup, jld: Dict) -> List[str]:
        img = jld.get("image")
        if isinstance(img, str):
            return [img]
        if isinstance(img, list) and img:
            return img[:5]
        images: List[str] = []
        for s in soup.find_all("script", string=re.compile(r"colorImages|imageGalleryData")):
            matches = re.findall(r'"hiRes"\s*:\s*"(https://[^"]+)"', s.string or "")
            images.extend(matches)
            if not images:
                matches = re.findall(r'"large"\s*:\s*"(https://[^"]+)"', s.string or "")
                images.extend(matches)
            if images:
                break
        if not images:
            main = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront")
            if main:
                src = main.get("data-old-hires") or main.get("src", "")
                if src:
                    images.append(src)
        return images[:5]

    @staticmethod
    def _reviews(soup: BeautifulSoup) -> List[ReviewItem]:
        """从产品页 HTML 中提取 Top Reviews（通常 8~10 条）。"""
        results: List[ReviewItem] = []

        # 主容器：#cm-cr-dp-review-list（children 为 li）
        container = soup.find(id="cm-cr-dp-review-list") or soup.find(id="cm_cr-review_list")
        if container:
            review_divs = container.find_all(attrs={"data-hook": "review"})
        else:
            review_divs = soup.find_all(attrs={"data-hook": "review"})

        for div in review_divs[:10]:
            # 星级
            stars = 0.0
            star_el = div.find("i", {"data-hook": "review-star-rating"}) or \
                       div.find("i", {"data-hook": "cmps-review-star-rating"}) or \
                       div.select_one("i.a-icon-star span.a-icon-alt") or \
                       div.select_one("span.a-icon-alt")
            if star_el:
                m = re.search(r"([\d.]+)", star_el.get_text(strip=True))
                if m:
                    stars = float(m.group(1))

            # 标题
            title = ""
            title_el = div.find("a", {"data-hook": "review-title"}) or \
                        div.find("span", {"data-hook": "review-title"})
            if title_el:
                title = title_el.get_text(strip=True)

            # 正文
            body = ""
            body_el = div.find("span", {"data-hook": "review-body"})
            if body_el:
                body = body_el.get_text(strip=True)

            # 日期
            date_str = ""
            date_el = div.find("span", {"data-hook": "review-date"})
            if date_el:
                date_str = date_el.get_text(strip=True)

            if title or body:
                results.append(ReviewItem(
                    stars=stars, title=title, body=body, date=date_str,
                ))

        return results


# ═══════════════════════════════════════════════
# FastAPI 应用
# ═══════════════════════════════════════════════

app = FastAPI(title="Amazon Scraper Proxy", version="1.0.0")
scraper = Scraper()

@app.get("/health")
def health():
    return {"status": "ok", "service": "scraper-proxy"}

@app.get("/debug-review-html")
def debug_review_html():
    """返回最近一次抓取的产品页中评论区 HTML 片段（调试用）。"""
    html = scraper._last_html
    if not html:
        return {"error": "还没有抓取过，请先调用 /scrape"}
    soup = BeautifulSoup(html, "lxml")

    snippets = []
    # 找所有 data-hook="review" 元素
    review_els = soup.find_all(attrs={"data-hook": "review"})
    for i, el in enumerate(review_els[:3]):
        snippets.append({
            "index": i,
            "tag": el.name,
            "id": el.get("id", ""),
            "classes": el.get("class", []),
            "html_preview": str(el)[:2000],
        })

    # 找评论区容器
    containers = {}
    for cid in ["cm-cr-dp-review-list", "cm_cr-review_list", "reviewsMedley", "reviews-medley-footer"]:
        c = soup.find(id=cid)
        if c:
            children_tags = [ch.name for ch in c.children if ch.name][:10]
            containers[cid] = {"found": True, "children_tags": children_tags}
        else:
            containers[cid] = {"found": False}

    return {
        "total_review_hooks": len(review_els),
        "containers": containers,
        "review_snippets": snippets,
    }

def _parse_search_results(html: str, marketplace: str) -> List[SearchResultItem]:
    """从 Amazon 搜索结果页 HTML 中提取商品列表。"""
    soup = BeautifulSoup(html, "html.parser")
    items: List[SearchResultItem] = []
    seen: set = set()

    for div in soup.select('[data-component-type="s-search-result"]'):
        asin = div.get("data-asin", "").strip()
        if not asin or len(asin) != 10 or asin in seen:
            continue
        seen.add(asin)

        is_sponsored = bool(
            div.select_one('.s-label-popover-default, [data-component-type="sp-sponsored-result"]')
            or div.find(string=re.compile(r"Sponsored|赞助|广告|スポンサー", re.I))
        )

        title = ""
        h2 = div.select_one("h2")
        if h2:
            a_tag = h2.select_one("a")
            title = (a_tag or h2).get_text(strip=True)
        # h2 有时只含品牌名，用图片 alt 做 fallback（Amazon 图片 alt = 完整标题）
        if len(title) < 25:
            img_el = div.select_one("img.s-image")
            alt = (img_el.get("alt", "") if img_el else "").strip()
            if len(alt) > len(title):
                title = alt

        price_whole = div.select_one(".a-price .a-price-whole")
        price_frac = div.select_one(".a-price .a-price-fraction")
        price_sym = div.select_one(".a-price .a-price-symbol")
        price = ""
        currency = ""
        if price_whole:
            pw = price_whole.get_text(strip=True).rstrip(".")
            pf = price_frac.get_text(strip=True) if price_frac else "00"
            price = f"{pw}.{pf}"
            if price_sym:
                currency = price_sym.get_text(strip=True)

        rating = ""
        for sel in [
            ".a-icon-star-small .a-icon-alt",
            ".a-icon-star .a-icon-alt",
            '[data-cy="reviews-ratings-slot"] .a-icon-alt',
            ".a-icon-star-mini .a-icon-alt",
        ]:
            rating_el = div.select_one(sel)
            if rating_el:
                m = re.search(r"([\d,.]+)", rating_el.get_text())
                if m:
                    rating = m.group(1).replace(",", ".")
                    break
        if not rating:
            for el in div.select("[aria-label]"):
                lbl = el.get("aria-label", "")
                m = re.search(r"([\d,.]+)\s*(?:out of|von|sur|de|つ星)", lbl, re.I)
                if m:
                    rating = m.group(1).replace(",", ".")
                    break
            if not rating:
                for el in div.select("span.a-icon-alt, i.a-icon"):
                    txt = el.get_text(strip=True) or el.get("aria-label", "")
                    m = re.search(r"([\d,.]+)\s*(?:out|von|sur|de|つ|颗星|estrellas)", txt, re.I)
                    if m:
                        rating = m.group(1).replace(",", ".")
                        break

        review_count = ""
        for rc_sel in [
            'a[href*="#customerReviews"] span',
            '.a-size-base.s-underline-text',
            '[data-cy="reviews-ratings-slot"] ~ span a span',
            '.a-link-normal .a-size-base',
        ]:
            rc_el = div.select_one(rc_sel)
            if rc_el:
                rc_text = rc_el.get_text(strip=True).replace(",", "").replace(".", "").replace(" ", "")
                m = re.search(r"(\d+)", rc_text)
                if m:
                    review_count = m.group(1)
                    break

        img_el = div.select_one("img.s-image")
        image = img_el.get("src", "") if img_el else ""

        if title:
            items.append(SearchResultItem(
                asin=asin,
                title=title,
                price=price,
                currency=currency,
                rating=rating,
                review_count=review_count,
                image=image,
                is_sponsored=is_sponsored,
            ))

    return items


@app.post("/search", response_model=SearchResponse)
def search_products(req: SearchRequest):
    """在 Amazon 搜索页抓取商品列表。"""
    marketplace = req.marketplace.upper()
    if marketplace not in MARKETPLACE_DOMAINS:
        return SearchResponse(success=False, error=f"不支持的站点: {marketplace}")
    domain = MARKETPLACE_DOMAINS[marketplace]

    print(f"\n{'='*50}")
    print(f"收到搜索请求: keywords={req.keywords[:80]}, 站点={marketplace}, pages={req.max_pages}")
    print(f"{'='*50}")

    all_items: List[SearchResultItem] = []
    seen_asins: set = set()

    for page in range(1, req.max_pages + 1):
        encoded = requests.utils.quote(req.keywords)
        url = f"https://{domain}/s?k={encoded}&page={page}"
        print(f"[搜索] 页 {page}: {url}")

        try:
            session = scraper._get_session(domain)
            if page > 1:
                time.sleep(random.uniform(1.5, 3.0))
            resp = session.get(url, timeout=FETCH_TIMEOUT, allow_redirects=True)
            print(f"[搜索] 页 {page} 状态码={resp.status_code} HTML长度={len(resp.text)}")

            if resp.status_code != 200:
                print(f"[搜索] 页 {page} 非200: {resp.status_code}")
                break

            if "captcha" in resp.text.lower()[:3000]:
                print(f"[搜索] 页 {page} 命中 CAPTCHA，停止")
                break

            page_items = _parse_search_results(resp.text, marketplace)
            print(f"[搜索] 页 {page} 解析到 {len(page_items)} 个商品")

            for item in page_items:
                if item.asin not in seen_asins:
                    seen_asins.add(item.asin)
                    all_items.append(item)

            if len(page_items) < 5:
                break

        except Exception as e:
            print(f"[搜索] 页 {page} 失败: {e}")
            break

    print(f"[搜索] 共获得 {len(all_items)} 个不重复商品")
    return SearchResponse(
        success=True,
        query=req.keywords,
        marketplace=marketplace,
        results=all_items,
        total_found=len(all_items),
    )


@app.post("/scrape", response_model=ScrapeResponse)
def scrape(req: ScrapeRequest):
    print(f"\n{'='*50}")
    print(f"收到抓取请求: ASIN={req.asin}, 站点={req.marketplace}")
    print(f"{'='*50}")
    try:
        result = scraper.scrape(req.asin, req.marketplace)
        print(f"[成功] {result.title[:60]}... | 评论={len(result.reviews)}条")
        # 调试：分析产品页和评论页中的评论标记
        debug_info: Dict[str, Any] = {}
        for label, html in [("product_page", scraper._last_html), ("review_page", scraper._last_review_html)]:
            if html:
                debug_info[label] = {
                    "html_len": len(html),
                    "has_captcha": "captcha" in html.lower()[:3000],
                    "has_js_challenge": "RXVM" in html[:5000],
                    "review_hook_count": html.count('data-hook="review"'),
                    "review_body_count": html.count("review-body"),
                    "a_icon_star_count": html.count("a-icon-star"),
                    "cr_widget_count": html.count("cr-widget"),
                }
        return ScrapeResponse(success=True, data=result, debug=debug_info)
    except Exception as e:
        print(f"[错误] {e}")
        return ScrapeResponse(success=False, error=str(e))




# ═══════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Amazon Scraper Proxy")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=9100, help="监听端口")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════╗
║   Amazon Scraper Proxy Service               ║
║   监听: {args.host}:{args.port}                       ║
║   接口: POST /scrape                         ║
║   健康: GET  /health                         ║
╚══════════════════════════════════════════════╝
""")
    uvicorn.run(app, host=args.host, port=args.port)
