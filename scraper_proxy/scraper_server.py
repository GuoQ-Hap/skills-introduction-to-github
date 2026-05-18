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
import concurrent.futures
import json
import os
import random
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import uvicorn
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

SCRAPER_VERSION = "2026.05.08-browser-threadfix-v3"
LOG_FILE = os.path.join(os.path.dirname(__file__), "scraper_proxy.log")


class TeeOutput:
    def __init__(self, *streams):
        self.streams = streams

    def isatty(self):
        for stream in self.streams:
            try:
                if stream.isatty():
                    return True
            except Exception:
                pass
        return False

    def fileno(self):
        for stream in self.streams:
            try:
                return stream.fileno()
            except Exception:
                pass
        raise OSError("TeeOutput has no file descriptor")

    def write(self, data):
        for stream in self.streams:
            try:
                stream.write(data)
                stream.flush()
            except Exception:
                pass

    def flush(self):
        for stream in self.streams:
            try:
                stream.flush()
            except Exception:
                pass


try:
    _log_fp = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = TeeOutput(sys.stdout, _log_fp)
    sys.stderr = TeeOutput(sys.stderr, _log_fp)
except Exception:
    pass

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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
]

URL_PATTERNS = [
    "https://{domain}/dp/{asin}",
    "https://{domain}/gp/product/{asin}",
    "https://{domain}/dp/{asin}?language=en_US",
    "https://{domain}/dp/{asin}?th=1&psc=1",
    "https://{domain}/exec/obidos/ASIN/{asin}",
]

FETCH_TIMEOUT = int(os.getenv("SCRAPER_FETCH_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("SCRAPER_MAX_RETRIES", "6"))
SCRAPER_HTTP_PROXY = os.getenv("SCRAPER_HTTP_PROXY", "")
SCRAPER_ACCEPT_LANGUAGE = os.getenv("SCRAPER_ACCEPT_LANGUAGE", "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7")
SCRAPER_LOCALE = os.getenv("SCRAPER_LOCALE", "zh_CN")
SCRAPER_CURRENCY = os.getenv("SCRAPER_CURRENCY", "CNY")
SCRAPER_STICKY_SESSION = os.getenv("SCRAPER_STICKY_SESSION", "1").lower() not in ("0", "false", "no")
SCRAPER_BROWSER_MODE = os.getenv("SCRAPER_BROWSER_MODE", "browser_first")  # browser_first / browser_only / requests_only
SCRAPER_BROWSER_CHANNEL = os.getenv("SCRAPER_BROWSER_CHANNEL", "msedge")
SCRAPER_BROWSER_HEADLESS = os.getenv("SCRAPER_BROWSER_HEADLESS", "0").lower() in ("1", "true", "yes")
SCRAPER_BROWSER_TIMEOUT_MS = int(os.getenv("SCRAPER_BROWSER_TIMEOUT_MS", "45000"))
SCRAPER_BROWSER_USER_DATA_DIR = os.getenv("SCRAPER_BROWSER_USER_DATA_DIR", os.path.join(os.path.dirname(__file__), "browser_profile"))
SCRAPER_BROWSER_PAGE_GAP = float(os.getenv("SCRAPER_BROWSER_PAGE_GAP", "2.5"))
SCRAPER_BROWSER_SEARCH = os.getenv("SCRAPER_BROWSER_SEARCH", "1").lower() not in ("0", "false", "no")

DESKTOP_USER_AGENTS = USER_AGENTS
MOBILE_USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S9280) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36",
]

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
    monthly_sales_text: str = ""
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
    monthly_sales_text: str = ""
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

class BrowserEngine:
    def __init__(self):
        self._playwright = None
        self._contexts: Dict[str, Any] = {}
        self._available: Optional[bool] = None
        self._last_error: str = ""
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="amazon-browser",
        )

    @property
    def last_error(self) -> str:
        return self._last_error

    def enabled(self) -> bool:
        return SCRAPER_BROWSER_MODE in ("browser_first", "browser_only")

    def available(self) -> bool:
        future = self._executor.submit(self._available_in_worker)
        return future.result(timeout=60)

    def _available_in_worker(self) -> bool:
        if not self.enabled():
            self._available = False
            return False
        if self._available is not None:
            return self._available
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._available = True
        except Exception as e:
            self._last_error = f"Playwright unavailable: {e}"
            self._available = False
        return self._available

    def fetch_html(self, url: str, domain: str, mobile: bool = False) -> Tuple[str, str, str]:
        future = self._executor.submit(self._fetch_html_in_worker, url, domain, mobile)
        return future.result(timeout=max(90, SCRAPER_BROWSER_TIMEOUT_MS // 1000 * 4))

    def _fetch_html_in_worker(self, url: str, domain: str, mobile: bool = False) -> Tuple[str, str, str]:
        if not self._available_in_worker() or not self._playwright:
            raise RuntimeError(self._last_error or "browser engine unavailable")
        key = "mobile" if mobile else "desktop"
        context = self._contexts.get(key)
        if context is None:
            context = self._new_context(mobile=mobile)
            self._contexts[key] = context
        page = context.new_page()
        try:
            print(f"[browser] goto {url} mobile={mobile} headless={SCRAPER_BROWSER_HEADLESS}")
            page.goto(f"https://{domain}/", wait_until="domcontentloaded", timeout=SCRAPER_BROWSER_TIMEOUT_MS)
            page.wait_for_timeout(random.randint(700, 1400))
            self._raise_if_signin(page)
            page.goto(url, wait_until="domcontentloaded", timeout=SCRAPER_BROWSER_TIMEOUT_MS)
            page.wait_for_timeout(random.randint(1800, 3000))
            self._raise_if_signin(page)
            self._settle_product_page(page)
            self._raise_if_signin(page)
            html = page.content()
            final_url = page.url
            title = page.title()
            return html, final_url, title
        finally:
            try:
                page.close()
            except Exception:
                pass

    def _new_context(self, mobile: bool = False):
        user_data_dir = os.path.join(SCRAPER_BROWSER_USER_DATA_DIR, "mobile" if mobile else "desktop")
        os.makedirs(user_data_dir, exist_ok=True)
        launch_kwargs: Dict[str, Any] = {
            "headless": SCRAPER_BROWSER_HEADLESS,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            "locale": SCRAPER_LOCALE.replace("_", "-"),
            "timezone_id": "Asia/Shanghai",
            "viewport": {"width": 390, "height": 844} if mobile else {"width": 1365, "height": 900},
            "user_agent": random.choice(MOBILE_USER_AGENTS if mobile else DESKTOP_USER_AGENTS),
        }
        if SCRAPER_HTTP_PROXY:
            launch_kwargs["proxy"] = {"server": SCRAPER_HTTP_PROXY}
        if SCRAPER_BROWSER_CHANNEL:
            launch_kwargs["channel"] = SCRAPER_BROWSER_CHANNEL
        try:
            return self._playwright.chromium.launch_persistent_context(user_data_dir, **launch_kwargs)
        except Exception as e:
            if launch_kwargs.pop("channel", None):
                print(f"[browser] channel {SCRAPER_BROWSER_CHANNEL} failed, fallback to bundled chromium: {e}")
                return self._playwright.chromium.launch_persistent_context(user_data_dir, **launch_kwargs)
            raise

    @staticmethod
    def _settle_product_page(page):
        for _ in range(4):
            page.mouse.wheel(0, random.randint(550, 900))
            page.wait_for_timeout(random.randint(500, 900))
        page.mouse.wheel(0, -1200)
        page.wait_for_timeout(random.randint(500, 900))

    @staticmethod
    def _raise_if_signin(page):
        url = (page.url or "").lower()
        title = ""
        try:
            title = (page.title() or "").lower()
        except Exception:
            title = ""
        if "/ap/signin" in url or "/ap/register" in url or "signin" in url:
            raise RuntimeError("Amazon Sign-in required")
        try:
            signin = page.locator("#ap_email, input[name='email'], form[name='signIn'], #authportal-main-section").count()
            if signin:
                raise RuntimeError("Amazon Sign-in required")
        except RuntimeError:
            raise
        except Exception:
            pass
        if "sign in" in title or "登录" in title or "登入" in title:
            raise RuntimeError("Amazon Sign-in required")

    def close(self):
        future = self._executor.submit(self._close_in_worker)
        try:
            future.result(timeout=30)
        except Exception as e:
            self._last_error = f"browser close failed: {e}"

    def _close_in_worker(self):
        for context in list(self._contexts.values()):
            try:
                context.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._playwright = None
        self._available = None


class Scraper:
    def __init__(self):
        self._session: Optional[requests.Session] = None
        self._sessions: Dict[str, requests.Session] = {}
        self._browser = BrowserEngine()
        self._warmed: set = set()
        self._last_html: str = ""
        self._last_review_html: str = ""
        self._last_attempts: List[Dict[str, Any]] = []
        self._last_parse_debug: Dict[str, Any] = {}

    def scrape(self, asin: str, marketplace: str) -> ProductResult:
        marketplace = marketplace.upper()
        if marketplace not in MARKETPLACE_DOMAINS:
            raise ValueError(f"不支持的站点: {marketplace}")
        domain = MARKETPLACE_DOMAINS[marketplace]
        last_err: Optional[Exception] = None
        self._last_html = ""
        self._last_review_html = ""
        self._last_attempts = []
        self._last_parse_debug = {}

        if SCRAPER_BROWSER_MODE in ("browser_first", "browser_only"):
            try:
                product = self._scrape_via_browser(asin, marketplace, domain)
                if self._is_usable_product(product):
                    return product
                last_err = ValueError("browser title 为空")
            except Exception as e:
                print(f"[browser失败] {e}")
                last_err = e
                if SCRAPER_BROWSER_MODE == "browser_only":
                    raise RuntimeError(f"浏览器内核抓取失败: {e}") from e

        for attempt in range(MAX_RETRIES):
            url = URL_PATTERNS[attempt % len(URL_PATTERNS)].format(domain=domain, asin=asin)
            mobile = False

            if attempt > 0:
                wait = min(2 ** attempt + random.uniform(0, 2), 15)
                print(f"[重试 {attempt+1}/{MAX_RETRIES}] 等待 {wait:.1f}s → {url}")
                if not SCRAPER_STICKY_SESSION:
                    self._reset_session()
                time.sleep(wait)

            try:
                product = self._do_fetch(url, asin, marketplace, domain, attempt, mobile=mobile)
                if self._is_usable_product(product):
                    product = self._enrich_product(product, asin, marketplace, domain)
                    if not product.reviews:
                        product.reviews = self._fetch_reviews_page(asin, domain)
                    return product
                print(f"[警告] 第 {attempt+1} 次: 页面解析成功但 title 为空，继续换入口")
                last_err = ValueError("title 为空")
            except Exception as e:
                print(f"[失败] 第 {attempt+1}/{MAX_RETRIES} 次: {e}")
                last_err = e

        raise RuntimeError(f"{MAX_RETRIES} 次尝试均失败，最后错误: {last_err}")

    def _scrape_via_browser(self, asin: str, marketplace: str, domain: str) -> ProductResult:
        urls = [
            f"https://{domain}/dp/{asin}?th=1&psc=1",
            f"https://{domain}/gp/product/{asin}?th=1&psc=1",
        ]
        last_err: Optional[Exception] = None
        for idx, url in enumerate(urls, start=1):
            mobile = False
            try:
                if idx > 1:
                    time.sleep(SCRAPER_BROWSER_PAGE_GAP)
                html, final_url, page_title = self._browser.fetch_html(url, domain, mobile=mobile)
                fake_resp = type("BrowserResp", (), {"text": html, "url": final_url, "status_code": 200})()
                block_reason = self._block_reason(fake_resp)
                self._last_html = html
                self._last_attempts.append({
                    "attempt": idx,
                    "url": url,
                    "status": 200,
                    "html_len": len(html),
                    "final_url": final_url,
                    "mobile": mobile,
                    "browser": True,
                    "page_title": page_title[:120],
                    "block_reason": block_reason,
                })
                if block_reason:
                    if "Sign-in" in block_reason:
                        self._browser.close()
                    last_err = RuntimeError(block_reason)
                    continue
                product = self._parse(html, asin, marketplace)
                if self._is_usable_product(product):
                    if not product.reviews:
                        product.reviews = self._fetch_reviews_via_browser(asin, domain)
                    return product
                last_err = ValueError("browser parsed title 为空")
            except Exception as e:
                if "Sign-in required" in str(e):
                    self._browser.close()
                last_err = e
                self._last_attempts.append({
                    "attempt": idx,
                    "url": url,
                    "status": 0,
                    "html_len": 0,
                    "final_url": "",
                    "mobile": mobile,
                    "browser": True,
                    "block_reason": "",
                    "error": str(e)[:300],
                })
        raise RuntimeError(last_err or "browser fetch failed")

    def _fetch_reviews_via_browser(self, asin: str, domain: str) -> List[ReviewItem]:
        review_url = f"https://{domain}/product-reviews/{asin}?sortBy=recent&pageNumber=1"
        try:
            html, final_url, _ = self._browser.fetch_html(review_url, domain, mobile=False)
            self._last_review_html = html
            fake_resp = type("BrowserResp", (), {"text": html, "url": final_url, "status_code": 200})()
            block_reason = self._block_reason(fake_resp)
            if block_reason:
                print(f"[browser reviews] blocked: {block_reason}")
                return []
            soup = BeautifulSoup(html, "lxml")
            reviews = self._reviews(soup)
            print(f"[browser reviews] 解析到 {len(reviews)} 条评论")
            return reviews
        except Exception as e:
            print(f"[browser reviews] failed: {e}")
            return []

    def search_via_browser(self, keywords: str, marketplace: str, max_pages: int = 2) -> List[SearchResultItem]:
        marketplace = marketplace.upper()
        domain = MARKETPLACE_DOMAINS[marketplace]
        all_items: List[SearchResultItem] = []
        seen: set = set()
        for page_num in range(1, max_pages + 1):
            encoded = requests.utils.quote(keywords)
            url = f"https://{domain}/s?k={encoded}&page={page_num}"
            if page_num > 1:
                time.sleep(SCRAPER_BROWSER_PAGE_GAP)
            html, final_url, page_title = self._browser.fetch_html(url, domain, mobile=False)
            fake_resp = type("BrowserResp", (), {"text": html, "url": final_url, "status_code": 200})()
            block_reason = self._block_reason(fake_resp)
            self._last_attempts.append({
                "attempt": len(self._last_attempts) + 1,
                "url": url,
                "status": 200,
                "html_len": len(html),
                "final_url": final_url,
                "mobile": False,
                "browser": True,
                "search": True,
                "page_title": page_title[:120],
                "block_reason": block_reason,
            })
            if block_reason:
                if "Sign-in" in block_reason:
                    self._browser.close()
                raise RuntimeError(block_reason)
            page_items = _parse_search_results(html, marketplace)
            print(f"[browser search] 页 {page_num} 解析到 {len(page_items)} 个商品")
            for item in page_items:
                if item.asin and item.asin not in seen:
                    seen.add(item.asin)
                    all_items.append(item)
            if len(page_items) < 5:
                break
        return all_items

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
            block_reason = self._block_reason(resp)
            if block_reason:
                print(f"[reviews] blocked: {block_reason}")
                self._reset_session(mobile=False)
                return []
            soup = BeautifulSoup(resp.text, "lxml")
            reviews = self._reviews(soup)
            print(f"[评论] 解析到 {len(reviews)} 条评论")
            return reviews
        except Exception as e:
            print(f"[评论] 评论页抓取失败: {e}")
            return []

    def _do_fetch(self, url: str, asin: str, marketplace: str, domain: str, attempt: int, mobile: bool = False) -> ProductResult:
        session = self._get_session(domain, mobile=mobile)
        self._warmup(session, domain, mobile=mobile)

        delay = random.uniform(1.5, 4) + attempt * 0.5
        print(f"[fetch] {url} (delay {delay:.1f}s)")
        time.sleep(delay)

        resp = session.get(url, timeout=FETCH_TIMEOUT, allow_redirects=True)
        self._last_html = resp.text
        block_reason = self._block_reason(resp)
        self._last_attempts.append({
            "attempt": attempt + 1,
            "url": url,
            "status": resp.status_code,
            "html_len": len(resp.text),
            "final_url": resp.url,
            "mobile": mobile,
            "block_reason": block_reason,
        })

        if resp.status_code == 404:
            raise ValueError(f"ASIN {asin} not found on {marketplace}")
        if resp.status_code in (429, 503):
            self._reset_session(mobile=mobile)
            raise RuntimeError(f"Amazon anti-bot/status {resp.status_code}")
        if block_reason:
            self._reset_session(mobile=mobile)
            raise RuntimeError(block_reason)
        if resp.status_code != 200:
            raise RuntimeError(f"unexpected status code: {resp.status_code}")

        return self._parse(resp.text, asin, marketplace)

    def _enrich_product(self, product: ProductResult, asin: str, marketplace: str, domain: str) -> ProductResult:
        missing_rich_fields = not product.bullet_points or not product.description or not product.category or not product.bsr_rank
        if not missing_rich_fields:
            return product

        enrich_urls = [
            (f"https://{domain}/dp/{asin}?th=1&psc=1&language=en_US", False),
            (f"https://{domain}/gp/product/{asin}?th=1&psc=1&language=en_US", False),
        ]
        tried = {a.get("url") for a in self._last_attempts}
        for url, mobile in enrich_urls:
            if url in tried:
                continue
            try:
                session = self._get_session(domain, mobile=mobile)
                self._warmup(session, domain, mobile=mobile)
                delay = random.uniform(0.8, 1.8)
                print(f"[enrich] {url} (delay {delay:.1f}s)")
                time.sleep(delay)
                resp = session.get(url, timeout=FETCH_TIMEOUT, allow_redirects=True)
                block_reason = self._block_reason(resp)
                self._last_attempts.append({
                    "attempt": len(self._last_attempts) + 1,
                    "url": url,
                    "status": resp.status_code,
                    "html_len": len(resp.text),
                    "final_url": resp.url,
                    "mobile": mobile,
                    "enrich": True,
                    "block_reason": block_reason,
                })
                if resp.status_code in (429, 503) or block_reason:
                    self._reset_session(mobile=mobile)
                    continue
                if resp.status_code != 200:
                    continue
                parsed = self._parse(resp.text, asin, marketplace)
                product = self._merge_product(product, parsed)
                if product.bullet_points and (product.description or product.bsr_rank or product.category):
                    break
            except Exception as e:
                print(f"[enrich] failed: {e}")
        return product

    @staticmethod
    def _merge_product(base: ProductResult, extra: ProductResult) -> ProductResult:
        for field in ("title", "brand", "price", "currency", "rating", "review_count", "description", "category", "bsr_rank", "monthly_sales_text"):
            if not getattr(base, field) and getattr(extra, field):
                setattr(base, field, getattr(extra, field))
        if not base.bullet_points and extra.bullet_points:
            base.bullet_points = extra.bullet_points
        if not base.images and extra.images:
            base.images = extra.images
        if not base.reviews and extra.reviews:
            base.reviews = extra.reviews
        return base

    # ── Session 管理 ──

    def _get_session(self, domain: str, mobile: bool = False) -> requests.Session:
        key = "mobile" if mobile else "desktop"
        if key not in self._sessions:
            self._sessions[key] = requests.Session()
            if SCRAPER_HTTP_PROXY:
                self._sessions[key].proxies.update({
                    "http": SCRAPER_HTTP_PROXY,
                    "https": SCRAPER_HTTP_PROXY,
                })
        session = self._sessions[key]
        ua = random.choice(MOBILE_USER_AGENTS if mobile else DESKTOP_USER_AGENTS)
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": SCRAPER_ACCEPT_LANGUAGE,
            "Accept-Encoding": "gzip, deflate",
            "Referer": f"https://{domain}/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        if "Chrome/" in ua or "Edg/" in ua:
            headers["sec-ch-ua"] = self._client_hints(ua)
            headers["sec-ch-ua-mobile"] = "?1" if mobile else "?0"
            headers["sec-ch-ua-platform"] = '"Android"' if mobile else '"Windows"'
        if mobile:
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
            headers["Viewport-Width"] = "390"
        session.headers.update(headers)
        session.cookies.set("i18n-prefs", SCRAPER_CURRENCY, domain=domain)
        session.cookies.set("lc-main", SCRAPER_LOCALE, domain=domain)
        return session

    @staticmethod
    def _client_hints(ua: str) -> str:
        chrome_version = "136"
        m = re.search(r"Chrome/(\d+)", ua)
        if m:
            chrome_version = m.group(1)
        if "Edg/" in ua:
            return f'"Chromium";v="{chrome_version}", "Microsoft Edge";v="{chrome_version}", "Not.A/Brand";v="99"'
        return f'"Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}", "Not.A/Brand";v="99"'

    def _warmup(self, session: requests.Session, domain: str, mobile: bool = False):
        warm_key = f"{domain}:mobile" if mobile else f"{domain}:desktop"
        if warm_key in self._warmed:
            return
        try:
            warm_url = f"https://{domain}/gp/aw" if mobile else f"https://{domain}/"
            print(f"[预热] 访问 {warm_url} 获取 cookie")
            time.sleep(random.uniform(0.5, 1.5))
            resp = session.get(warm_url, timeout=15, allow_redirects=True)
            block_reason = self._block_reason(resp)
            if resp.status_code in (429, 503) or block_reason:
                print(f"[预热失败] status={resp.status_code} block={block_reason or '-'}")
                self._reset_session(mobile=mobile)
                return
            self._warmed.add(warm_key)
        except Exception as e:
            print(f"[预热失败] {e}")

    def _reset_session(self, mobile: Optional[bool] = None):
        if mobile is None:
            keys = list(self._sessions.keys())
        else:
            keys = ["mobile" if mobile else "desktop"]
        for key in keys:
            session = self._sessions.pop(key, None)
            if session:
                try:
                    session.close()
                except Exception:
                    pass
        if mobile is None:
            self._warmed.clear()
        else:
            suffix = ":mobile" if mobile else ":desktop"
            self._warmed = {item for item in self._warmed if not str(item).endswith(suffix)}
        self._session = None

    # ── HTML 解析 ──

    @staticmethod
    def _block_reason(resp: requests.Response) -> str:
        head = (resp.text or "")[:12000]
        lower = head.lower()
        final_url = (resp.url or "").lower()
        if "/ap/signin" in final_url or "/ap/register" in final_url:
            return "Amazon Sign-in required"
        if "authportal-main-section" in lower or 'name="signIn"' in head or 'id="ap_email"' in head:
            return "Amazon Sign-in required"
        if "登录或创建账户" in head or "sign in or create account" in lower:
            return "Amazon Sign-in required"
        if "/errors/validatecaptcha" in final_url:
            return "Amazon CAPTCHA page"
        if 'action="/errors/validatecaptcha"' in lower or "enter the characters you see below" in lower:
            return "Amazon CAPTCHA page"
        if "<title>robot check" in lower or "sorry, we just need to make sure you're not a robot" in lower:
            return "Amazon Robot Check page"
        if "main-canvas" in lower and "captcha" in lower:
            return "Amazon JS/CAPTCHA challenge page"
        return ""

    @staticmethod
    def _is_usable_product(product: ProductResult) -> bool:
        if product.title and len(product.title.strip()) > 8:
            return True
        return False

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
        monthly_sales = self._monthly_sales_text(soup)
        imgs = self._images(soup, jld)
        review_list = self._reviews(soup)
        self._last_parse_debug = self._parse_debug(soup, jld, title)

        return ProductResult(
            asin=asin, marketplace=marketplace,
            title=title, brand=brand, price=price, currency=currency,
            rating=rating, review_count=reviews,
            bullet_points=bullets, description=desc,
            category=cat, bsr_rank=bsr, monthly_sales_text=monthly_sales, images=imgs[:5],
            reviews=review_list,
        )

    @staticmethod
    def _monthly_sales_text(soup: BeautifulSoup) -> str:
        selectors = [
            "#social-proofing-faceout-title-tk_bought",
            "#social-proofing-faceout-title",
            "#social-proofing-faceout-title-tk_bought span",
            "[id*='social-proofing']",
            "#zeitgeistBadge_feature_div",
        ]
        for sel in selectors:
            for el in soup.select(sel):
                txt = " ".join(el.get_text(" ", strip=True).split())
                if re.search(r"\b(bought|purchased)\b.*\b(past|month)\b", txt, re.I):
                    return txt[:160]
        text = soup.get_text(" ", strip=True)
        m = re.search(r"([0-9][0-9,]*\+?\s*(?:bought|purchased)\s+in\s+(?:the\s+)?past\s+month)", text, re.I)
        return m.group(1)[:160] if m else ""

    @staticmethod
    def _parse_debug(soup: BeautifulSoup, jld: Dict, title: str) -> Dict[str, Any]:
        candidates: Dict[str, str] = {}
        selectors = {
            "jld_name": str(jld.get("name", ""))[:300] if jld else "",
            "og_title": "",
            "meta_title": "",
            "productTitle": "",
            "title_id": "",
            "html_title": "",
            "first_img_alt": "",
        }
        og = soup.select_one('meta[property="og:title"]')
        mt = soup.select_one('meta[name="title"]')
        pt = soup.find(id="productTitle")
        tid = soup.find(id="title")
        html_title = soup.find("title")
        img = soup.select_one("img[alt]")
        selectors["og_title"] = (og.get("content", "") if og else "")[:300]
        selectors["meta_title"] = (mt.get("content", "") if mt else "")[:300]
        selectors["productTitle"] = pt.get_text(" ", strip=True)[:300] if pt else ""
        selectors["title_id"] = tid.get_text(" ", strip=True)[:300] if tid else ""
        selectors["html_title"] = html_title.get_text(" ", strip=True)[:300] if html_title else ""
        selectors["first_img_alt"] = (img.get("alt", "") if img else "")[:300]
        for key, value in selectors.items():
            if value:
                candidates[key] = value
        return {
            "title_found": bool(title),
            "title": title[:300],
            "candidate_titles": candidates,
            "has_product_title_id": bool(pt),
            "has_json_ld": bool(jld),
            "feature_bullets_count": len(soup.select("#feature-bullets li, [id*='featureBullets'] li")),
            "overview_row_count": len(soup.select("#productOverview_feature_div tr")),
            "detail_bullets_count": len(soup.select("#detailBullets_feature_div li, #detailBulletsWrapper_feature_div li")),
        }

    @staticmethod
    def _json_ld(soup: BeautifulSoup) -> Dict[str, Any]:
        def is_product(obj: Any) -> bool:
            if not isinstance(obj, dict):
                return False
            typ = obj.get("@type")
            return typ == "Product" or (isinstance(typ, list) and "Product" in typ)

        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                if is_product(data):
                    return data
                if isinstance(data, dict) and isinstance(data.get("@graph"), list):
                    for item in data["@graph"]:
                        if is_product(item):
                            return item
                if isinstance(data, list):
                    for item in data:
                        if is_product(item):
                            return item
            except (json.JSONDecodeError, TypeError):
                continue
        return {}

    @staticmethod
    def _title(soup: BeautifulSoup, jld: Dict) -> str:
        if jld.get("name"):
            return jld["name"].strip()
        meta_title = soup.select_one('meta[property="og:title"], meta[name="title"]')
        if meta_title:
            t = (meta_title.get("content") or "").strip()
            if t and "Amazon" not in t[:20]:
                return t
        for el in [
            soup.find("span", {"id": "productTitle"}),
            soup.find(id="productTitle"),
            soup.find("h1", {"id": "title"}),
            soup.select_one("#title span"),
            soup.select_one("#title"),
            soup.select_one("#ebooksProductTitle"),
            soup.select_one("[data-automation-id='title']"),
            soup.select_one("[data-feature-name='title'] span"),
            soup.select_one("[data-feature-name='title']"),
            soup.select_one(".a-size-large.product-title-word-break"),
            soup.select_one(".a-size-large.a-spacing-none"),
            soup.find("title"),
        ]:
            if el:
                t = el.get_text(strip=True)
                if t and "Amazon" not in t[:10]:
                    return t
        html = str(soup)
        for pattern in [
            r'"title"\s*:\s*"([^"]{20,300})"',
            r'"productTitle"\s*:\s*"([^"]{20,300})"',
            r'"item_name"\s*:\s*"([^"]{20,300})"',
            r'"displayTitle"\s*:\s*"([^"]{20,300})"',
            r'<img[^>]+alt="([^"]{20,300})"',
        ]:
            m = re.search(pattern, html, re.I)
            if m:
                t = m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore").strip()
                if t and "Amazon" not in t[:20] and "Captcha" not in t[:30]:
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
            soup.select_one("#brand"),
            soup.select_one('tr.po-brand td.a-span9 span'),
        ]:
            if el:
                t = el.get_text(strip=True)
                for p in ("Brand: ", "Visit the ", "ブランド: ", "Marke: "):
                    if t.startswith(p):
                        t = t[len(p):]
                return t.replace(" Store", "").strip()
        for row in soup.select("#productOverview_feature_div tr, #productDetails_techSpec_section_1 tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2 and "brand" in cells[0].get_text(" ", strip=True).lower():
                return cells[1].get_text(" ", strip=True).replace(" Store", "").strip()
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
            soup.select_one("#corePriceDisplay_desktop_feature_div .a-offscreen"),
            soup.select_one("#corePriceDisplay_mobile_feature_div .a-offscreen"),
            soup.select_one("#newBuyBoxPrice"),
            soup.select_one("#priceblock_saleprice"),
            soup.select_one("#priceblock_pospromoprice"),
            soup.select_one("[data-a-color='price'] .a-offscreen"),
            soup.select_one("[data-feature-name='corePrice'] .a-offscreen"),
            soup.select_one("#apex_desktop .a-price .a-offscreen"),
            soup.select_one("#price_inside_buybox"),
            soup.select_one(".a-price .a-offscreen"),
        ]:
            if el:
                raw = el.get_text(strip=True)
                if raw:
                    num, cur = _split(raw)
                    return num or raw, cur
        body_text = soup.get_text(" ", strip=True)
        m = re.search(r"(\$|US\$|£|€|¥|CA\$|A\$|AU\$|MX\$)\s*([\d][\d,]*(?:\.\d{2})?)", body_text)
        if m:
            return m.group(2), _sym_map.get(m.group(1), "")
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
            soup.select_one("#averageCustomerReviews .a-icon-alt"),
            soup.select_one("[data-hook='rating-out-of-text']"),
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
            soup.select_one("[data-hook='total-review-count']"),
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
            container = (
                soup.find(id="featurebullets_feature_div")
                or soup.find(id="featureBullets_feature_div")
                or soup.find(id="featureBulletsAndDetailBullets_feature_div")
            )
        if not container:
            candidates = []
            for el in soup.select(
                "[data-feature-name='featurebullets'] li, "
                "#mobile_feature_div li, #feature-bullets-btf li, "
                "[id*='featureBullets'] li, [id*='feature-bullets'] li"
            ):
                text = el.get_text(" ", strip=True)
                if text and len(text) > 5 and "Javascript" not in text:
                    candidates.append(text)
            if candidates:
                return Scraper._dedupe_texts(candidates, limit=10)
            overview = Scraper._overview_facts(soup)
            return overview[:10]
        items = container.select("li .a-list-item") or container.find_all("li")
        result: List[str] = []
        for el in items:
            # 多变体产品会把所有变体的 bullet 写入 HTML，靠 JS 隐藏非当前变体。
            # 抓取时不执行 JS，需手动过滤 display:none 的 li，避免抓到 20+ 条。
            parent_li = el.parent if el.name != "li" else el
            if parent_li and parent_li.name == "li":
                style = (parent_li.get("style", "") or "").replace(" ", "").lower()
                if "display:none" in style:
                    continue
            text = el.get_text(strip=True)
            if text and len(text) > 5 and "Javascript" not in text:
                result.append(text)
        # 最多保留 10 条：正常商品 5 条，单变体多 bullet 商品不超过 10 条
        return Scraper._dedupe_texts(result, limit=10)

    @staticmethod
    def _description(soup: BeautifulSoup) -> str:
        for el in [
            soup.find("div", {"id": "productDescription"}),
            soup.find(id="productDescription"),
            soup.find(id="productDescription_feature_div"),
            soup.find(id="mobile-product-description"),
            soup.find(id="bookDescription_feature_div"),
        ]:
            if el:
                t = el.get_text(" ", strip=True)
                if t:
                    return t
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc and meta_desc.get("content"):
            content = meta_desc["content"].strip()
            if len(content) > 30 and "Amazon" not in content[:20]:
                return content
        aplus = soup.find(id="aplus") or soup.find("div", {"id": "aplus_feature_div"})
        if aplus:
            texts = [p.get_text(strip=True) for p in aplus.find_all(["p", "h3", "h4", "span"])]
            r = "\n".join(t for t in texts if t and len(t) > 3)
            if r:
                return r
        bullets = Scraper._bullets(soup)
        if bullets:
            return "\n".join(bullets[:5])
        return ""

    @staticmethod
    def _category(soup: BeautifulSoup) -> str:
        bc = soup.find(id="wayfinding-breadcrumbs_feature_div")
        if bc:
            parts = [a.get_text(strip=True) for a in bc.select("a") if a.get_text(strip=True)]
            if parts:
                return " > ".join(parts)
        body_text = soup.get_text(" ", strip=True)
        m = re.search(r"Best Sellers Rank\s*[:#\s\d,]+in\s+([^#|]+?)(?:\s+\(|\s+#|\s+Customer|\s*$)", body_text, re.I)
        if m:
            return m.group(1).strip(" :>-")[:200]
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
                after = body_text[idx:idx + 400]
                m = re.search(r"#?([\d,]+)", after)
                if m:
                    return m.group(1).replace(",", "").strip()

        return ""

    @staticmethod
    def _overview_facts(soup: BeautifulSoup) -> List[str]:
        facts: List[str] = []
        for row in soup.select("#productOverview_feature_div tr, #productDetails_detailBullets_sections1 tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                key = cells[0].get_text(" ", strip=True).strip(":")
                val = cells[1].get_text(" ", strip=True)
                if key and val and len(val) > 1:
                    facts.append(f"{key}: {val}")
        for li in soup.select("#detailBullets_feature_div li, #detailBulletsWrapper_feature_div li"):
            text = li.get_text(" ", strip=True)
            if text and len(text) > 5:
                facts.append(text)
        return Scraper._dedupe_texts(facts, limit=10)

    @staticmethod
    def _dedupe_texts(values: List[str], limit: int = 10) -> List[str]:
        result: List[str] = []
        seen: set = set()
        for value in values:
            text = re.sub(r"\s+", " ", value).strip(" \t\n\r:;-")
            if not text or len(text) <= 5:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _images(soup: BeautifulSoup, jld: Dict) -> List[str]:
        img = jld.get("image")
        if isinstance(img, str):
            return [img]
        if isinstance(img, list) and img:
            return img[:5]
        meta_img = soup.select_one('meta[property="og:image"]')
        if meta_img and meta_img.get("content"):
            return [meta_img["content"]]
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
        if not images:
            for img_el in soup.select("img[src*='media-amazon.com']"):
                src = img_el.get("src", "")
                if src and src not in images:
                    images.append(src)
                if len(images) >= 5:
                    break
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
    return {
        "status": "ok",
        "service": "scraper-proxy",
        "version": SCRAPER_VERSION,
        "max_retries": MAX_RETRIES,
        "timeout": FETCH_TIMEOUT,
        "upstream_proxy": bool(SCRAPER_HTTP_PROXY),
        "accept_language": SCRAPER_ACCEPT_LANGUAGE,
        "locale": SCRAPER_LOCALE,
        "currency": SCRAPER_CURRENCY,
        "sticky_session": SCRAPER_STICKY_SESSION,
        "browser_mode": SCRAPER_BROWSER_MODE,
        "browser_channel": SCRAPER_BROWSER_CHANNEL,
        "browser_headless": SCRAPER_BROWSER_HEADLESS,
        "browser_page_gap": SCRAPER_BROWSER_PAGE_GAP,
        "browser_search": SCRAPER_BROWSER_SEARCH,
        "browser_available": scraper._browser.available(),
        "browser_error": scraper._browser.last_error,
    }

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

    if SCRAPER_BROWSER_SEARCH and SCRAPER_BROWSER_MODE in ("browser_first", "browser_only"):
        try:
            browser_items = scraper.search_via_browser(req.keywords, marketplace, req.max_pages)
            print(f"[browser search] 共获得 {len(browser_items)} 个不重复商品")
            return SearchResponse(
                success=True,
                query=req.keywords,
                marketplace=marketplace,
                results=browser_items,
                total_found=len(browser_items),
            )
        except Exception as e:
            print(f"[browser search] 失败: {e}")
            if SCRAPER_BROWSER_MODE == "browser_only":
                return SearchResponse(success=False, query=req.keywords, marketplace=marketplace, error=str(e))

    for page in range(1, req.max_pages + 1):
        encoded = requests.utils.quote(req.keywords)
        url = f"https://{domain}/s?k={encoded}&page={page}"
        print(f"[搜索] 页 {page}: {url}")

        try:
            session = scraper._get_session(domain)
            scraper._warmup(session, domain)
            if page > 1:
                time.sleep(random.uniform(1.5, 3.0))
            resp = session.get(url, timeout=FETCH_TIMEOUT, allow_redirects=True)
            print(f"[搜索] 页 {page} 状态码={resp.status_code} HTML长度={len(resp.text)}")

            if resp.status_code != 200:
                print(f"[搜索] 页 {page} 非200: {resp.status_code}")
                break

            block_reason = scraper._block_reason(resp)
            if block_reason:
                print(f"[search] page {page} blocked: {block_reason}")
                scraper._reset_session()
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
    print(f"收到抓取请求: ASIN={req.asin}, 站点={req.marketplace}, version={SCRAPER_VERSION}")
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
        debug_info["attempts"] = scraper._last_attempts
        debug_info["parse"] = scraper._last_parse_debug
        debug_info["version"] = SCRAPER_VERSION
        return ScrapeResponse(success=True, data=result, debug=debug_info)
    except Exception as e:
        print(f"[错误] {e}")
        return ScrapeResponse(
            success=False,
            error=str(e),
            debug={
                "attempts": scraper._last_attempts,
                "parse": scraper._last_parse_debug,
                "version": SCRAPER_VERSION,
            },
        )




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
║   版本: {SCRAPER_VERSION}       ║
║   监听: {args.host}:{args.port}                       ║
║   接口: POST /scrape                         ║
║   健康: GET  /health                         ║
╚══════════════════════════════════════════════╝
""")
    uvicorn.run(app, host=args.host, port=args.port)
