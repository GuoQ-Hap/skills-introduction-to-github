"""Lingxing MWS review table reader."""
from __future__ import annotations

import json
from typing import Any, List, Tuple

from LDA.service.dbService import db_service
from LSTA.models.listingState import ReviewItem
from LSTA.service.base import service_logger

logger = service_logger

TABLE_NAME = "dwd_lingxing_mws_reviews_incr"

_MARKETPLACE_CN = {
    "US": "美国",
    "UK": "英国",
    "GB": "英国",
    "DE": "德国",
    "FR": "法国",
    "IT": "意大利",
    "ES": "西班牙",
    "JP": "日本",
    "CA": "加拿大",
    "AU": "澳大利亚",
    "MX": "墨西哥",
}


class MwsReviewService:
    """Fetch review samples from dwd_lingxing_mws_reviews_incr."""

    def query_reviews(self, *, asin: str, marketplace: str = "US", limit: int = 30) -> List[ReviewItem]:
        _, reviews = self.query_reviews_with_title(asin=asin, marketplace=marketplace, limit=limit)
        return reviews

    def query_reviews_with_title(
        self,
        *,
        asin: str,
        marketplace: str = "US",
        limit: int = 30,
    ) -> Tuple[str, List[ReviewItem]]:
        asin = (asin or "").strip().upper()
        if not asin:
            return "", []
        limit = max(1, min(int(limit or 30), 100))
        marketplace = (marketplace or "").strip().upper()
        market_cn = _MARKETPLACE_CN.get(marketplace, marketplace)

        market_filter = ""
        if market_cn:
            market_filter = f" AND (marketplace = '{_escape(market_cn)}' OR marketplace = '{_escape(marketplace)}')"

        sql = f"""
        SELECT
          last_star,
          last_title,
          last_content,
          create_time,
          review_id,
          review_likes,
          author,
          item_name
        FROM (
          SELECT
            last_star,
            last_title,
            last_content,
            create_time,
            review_id,
            review_likes,
            author,
            item_name,
            ROW_NUMBER() OVER (
              PARTITION BY review_id
              ORDER BY date DESC, update_time DESC, crawl_date DESC
            ) AS rn
          FROM {TABLE_NAME}
          WHERE asin = '{_escape(asin)}'
            AND last_content IS NOT NULL
            AND TRIM(last_content) != ''
            {market_filter}
        ) x
        WHERE rn = 1
        ORDER BY create_time DESC, review_likes DESC
        LIMIT {limit}
        """
        try:
            _, rows = db_service.execute_sql(sql)
        except Exception as exc:
            logger.warning("MWS 评论表查询失败 asin=%s marketplace=%s: %s", asin, marketplace, exc)
            return "", []

        reviews: List[ReviewItem] = []
        title = ""
        for row in rows:
            if not title and row.get("item_name"):
                title = _clean_item_name(row.get("item_name"))
            reviews.append(ReviewItem(
                stars=_safe_float(row.get("last_star")),
                title=str(row.get("last_title") or ""),
                body=str(row.get("last_content") or ""),
                date=str(row.get("create_time") or ""),
            ))
        return title, reviews


def _escape(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("'", "''")


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _clean_item_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list) and parsed:
                return str(parsed[0] or "").strip()
        except Exception:
            pass
    return text.strip('"').strip()


mws_review_service = MwsReviewService()
