"""SP advertising keyword insights for Listing optimization.

This service keeps a small MySQL cache in ric_ai_base and fills it from
dw_leang Lingxing SP advertising DWD tables. The cache is intentionally
Listing-oriented: only AK stores, only useful keyword/search-term candidates,
and metrics already aggregated for fast LSTA reads.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pymysql

from Base.Config.setting import settings
from LDA.constants import (
    STI_DB_CHARSET,
    STI_DB_HOST,
    STI_DB_NAME,
    STI_DB_PASSWORD,
    STI_DB_PORT,
    STI_DB_USER,
)
from LSTA.service.base import service_logger

logger = service_logger


TABLE_NAME = "lsta_sp_ad_keyword_insight"


class SpAdInsightService:
    """Build and query AK-store SP ad insight cache."""

    def _target_connect(self) -> pymysql.Connection:
        cfg = settings.mysql
        return pymysql.connect(
            host=cfg.host,
            port=int(cfg.port or 3306),
            user=cfg.user,
            password=str(cfg.password or ""),
            database=cfg.name,
            charset=cfg.charset or "utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=120,
        )

    def _source_connect(self) -> pymysql.Connection:
        return pymysql.connect(
            host=STI_DB_HOST,
            port=STI_DB_PORT,
            user=STI_DB_USER,
            password=STI_DB_PASSWORD,
            database=STI_DB_NAME,
            charset=STI_DB_CHARSET,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=300,
        )

    def ensure_table(self) -> None:
        sql = f"""
        CREATE TABLE IF NOT EXISTS `{TABLE_NAME}` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `date_start` DATE NOT NULL,
          `date_end` DATE NOT NULL,
          `store_name` VARCHAR(64) NOT NULL,
          `country_code` VARCHAR(16) NOT NULL,
          `profile_id` VARCHAR(64) NOT NULL,
          `asin` VARCHAR(32) NOT NULL DEFAULT '',
          `sku` VARCHAR(160) NOT NULL DEFAULT '',
          `word_type` VARCHAR(32) NOT NULL,
          `word_text` VARCHAR(512) NOT NULL,
          `match_type` VARCHAR(128) NOT NULL DEFAULT '',
          `campaign_id` VARCHAR(64) NOT NULL DEFAULT '',
          `campaign_name` VARCHAR(512) NOT NULL DEFAULT '',
          `ad_group_id` VARCHAR(64) NOT NULL DEFAULT '',
          `ad_group_name` VARCHAR(512) NOT NULL DEFAULT '',
          `impressions` BIGINT NOT NULL DEFAULT 0,
          `clicks` BIGINT NOT NULL DEFAULT 0,
          `cost` DECIMAL(18,4) NOT NULL DEFAULT 0,
          `orders` BIGINT NOT NULL DEFAULT 0,
          `sales` DECIMAL(18,4) NOT NULL DEFAULT 0,
          `units` BIGINT NOT NULL DEFAULT 0,
          `ctr` DECIMAL(18,8) NOT NULL DEFAULT 0,
          `cpc` DECIMAL(18,8) NOT NULL DEFAULT 0,
          `cvr` DECIMAL(18,8) NOT NULL DEFAULT 0,
          `acos` DECIMAL(18,8) NOT NULL DEFAULT 0,
          `roas` DECIMAL(18,8) NOT NULL DEFAULT 0,
          `insight_type` VARCHAR(64) NOT NULL,
          `source_table` VARCHAR(128) NOT NULL,
          `reason` VARCHAR(1024) NOT NULL DEFAULT '',
          `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uk_lsta_sp_ad_insight` (
            `date_start`, `date_end`, `store_name`, `asin`, `sku`(80),
            `word_type`, `word_text`(160), `match_type`, `campaign_id`, `ad_group_id`, `insight_type`
          ),
          KEY `idx_lsta_sp_ad_asin` (`asin`, `store_name`, `date_end`),
          KEY `idx_lsta_sp_ad_sku` (`sku`, `store_name`, `date_end`),
          KEY `idx_lsta_sp_ad_word` (`word_text`(120), `insight_type`),
          KEY `idx_lsta_sp_ad_store` (`store_name`, `country_code`, `date_end`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)

    def sync(
        self,
        *,
        days: int = 60,
        asin: Optional[str] = None,
        limit_per_type: int = 5000,
    ) -> Dict[str, Any]:
        """Refresh AK SP keyword/search-term candidates into MySQL cache."""
        self.ensure_table()
        days = max(1, min(int(days or 60), 366))
        limit_per_type = max(100, min(int(limit_per_type or 5000), 50000))
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)

        self._delete_existing(start=start, end=end, asin=asin)

        total = 0
        inserted = 0
        for word_type in ("search_term", "keyword", "purchased_asin"):
            rows = self._fetch_source_rows(
                word_type=word_type,
                start=start,
                end=end,
                asin=asin,
                limit=limit_per_type,
            )
            total += len(rows)
            inserted += self._upsert_rows(rows)

        return {
            "success": True,
            "table": TABLE_NAME,
            "date_start": str(start),
            "date_end": str(end),
            "days": days,
            "asin": asin or "",
            "source_rows": total,
            "upserted_rows": inserted,
        }

    def _delete_existing(self, *, start: date, end: date, asin: Optional[str]) -> None:
        filters = ["date_start = %s", "date_end = %s"]
        params: List[Any] = [start, end]
        if asin:
            filters.append("asin = %s")
            params.append(asin)
        sql = f"DELETE FROM `{TABLE_NAME}` WHERE {' AND '.join(filters)}"
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)

    def _fetch_source_rows(
        self,
        *,
        word_type: str,
        start: date,
        end: date,
        asin: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if word_type == "purchased_asin":
            return self._fetch_asin_report_rows(start=start, end=end, asin=asin, limit=limit)

        if word_type == "search_term":
            word_expr = "r.`query`"
            table = "dwd_lingxing_sp_word_reports_incr"
            source_table = table
        else:
            word_expr = "r.keyword_text"
            table = "dwd_lingxing_sp_key_word_reports_incr"
            source_table = table

        asin_filter = "AND p.asin = %s" if asin else ""
        params: List[Any] = [start, end, start, end]
        if asin:
            params.append(asin)
        params.extend([str(start), str(end), source_table, limit])

        sql = f"""
        WITH ak AS (
          SELECT sid, profile_id, country_code, name AS store_name
          FROM dim_lingxing_adv_account
          WHERE date = (SELECT MAX(date) FROM dim_lingxing_adv_account)
            AND name LIKE 'AK-%%'
            AND status = 1
        ),
        p AS (
          SELECT
            profile_id,
            campaign_id,
            ad_group_id,
            asin,
            sku
          FROM dwd_lingxing_sp_product_ad_reports_incr
          WHERE date BETWEEN %s AND %s
          GROUP BY profile_id, campaign_id, ad_group_id, asin, sku
        ),
        w AS (
          SELECT
            profile_id,
            campaign_id,
            ad_group_id,
            {word_expr} AS word_text,
            match_type,
            SUM(impressions) AS impressions,
            SUM(clicks) AS clicks,
            SUM(cost) AS cost,
            SUM(orders) AS orders,
            SUM(sales) AS sales,
            SUM(units) AS units
          FROM {table} r
          WHERE date BETWEEN %s AND %s
            AND {word_expr} IS NOT NULL
            AND TRIM({word_expr}) != ''
          GROUP BY profile_id, campaign_id, ad_group_id, {word_expr}, match_type
        )
        SELECT
          %s AS date_start,
          %s AS date_end,
          ak.store_name,
          ak.country_code,
          CAST(ak.profile_id AS CHAR) AS profile_id,
          p.asin,
          p.sku,
          '{word_type}' AS word_type,
          w.word_text,
          IFNULL(w.match_type, '') AS match_type,
          CAST(IFNULL(w.campaign_id, 0) AS CHAR) AS campaign_id,
          IFNULL(c.name, '') AS campaign_name,
          CAST(IFNULL(w.ad_group_id, 0) AS CHAR) AS ad_group_id,
          IFNULL(g.name, '') AS ad_group_name,
          w.impressions,
          w.clicks,
          w.cost,
          w.orders,
          w.sales,
          w.units,
          CASE WHEN w.impressions > 0 THEN w.clicks / w.impressions ELSE 0 END AS ctr,
          CASE WHEN w.clicks > 0 THEN w.cost / w.clicks ELSE 0 END AS cpc,
          CASE WHEN w.clicks > 0 THEN w.orders / w.clicks ELSE 0 END AS cvr,
          CASE WHEN w.sales > 0 THEN w.cost / w.sales ELSE 0 END AS acos,
          CASE WHEN w.cost > 0 THEN w.sales / w.cost ELSE 0 END AS roas,
          CASE
            WHEN w.orders > 0 AND w.sales > 0 AND (w.cost = 0 OR w.cost / w.sales <= 0.45)
              THEN 'high_conversion'
            WHEN w.clicks >= 15 AND w.orders = 0 AND w.cost >= 5
              THEN 'high_click_no_order'
            WHEN w.impressions >= 1000 AND (w.clicks / w.impressions) < 0.003
              THEN 'high_impression_low_ctr'
            ELSE 'candidate'
          END AS insight_type,
          %s AS source_table,
          CASE
            WHEN w.orders > 0 AND w.sales > 0 AND (w.cost = 0 OR w.cost / w.sales <= 0.45)
              THEN 'Orders and sales are present with acceptable ACOS; prioritize natural Listing coverage.'
            WHEN w.clicks >= 15 AND w.orders = 0 AND w.cost >= 5
              THEN 'Clicks and spend are present but no orders; check Listing relevance, promise, price, and images.'
            WHEN w.impressions >= 1000 AND (w.clicks / w.impressions) < 0.003
              THEN 'High impressions but low CTR; improve title/main-image relevance or avoid weak traffic.'
            ELSE 'Candidate ad term from AK SP data.'
          END AS reason
        FROM w
        JOIN ak ON CAST(w.profile_id AS CHAR) = CAST(ak.profile_id AS CHAR)
        JOIN p ON p.profile_id = w.profile_id
          AND p.ad_group_id = w.ad_group_id
          AND (w.campaign_id = p.campaign_id OR w.campaign_id IS NULL OR w.campaign_id = 0)
        LEFT JOIN dwd_lingxing_sp_campaigns_incr c
          ON c.profile_id = w.profile_id AND c.campaign_id = w.campaign_id
        LEFT JOIN dwd_lingxing_sp_ad_groups_incr g
          ON g.profile_id = w.profile_id AND g.ad_group_id = w.ad_group_id
        WHERE (
          w.orders > 0
          OR (w.clicks >= 15 AND w.cost >= 5)
          OR w.impressions >= 1000
        )
        {asin_filter}
        ORDER BY
          CASE
            WHEN w.orders > 0 AND w.sales > 0 AND (w.cost = 0 OR w.cost / w.sales <= 0.45) THEN 1
            WHEN w.clicks >= 15 AND w.orders = 0 AND w.cost >= 5 THEN 2
            WHEN w.impressions >= 1000 AND (w.clicks / w.impressions) < 0.003 THEN 3
            ELSE 4
          END,
          w.sales DESC,
          w.orders DESC,
          w.cost DESC
        LIMIT %s
        """

        with self._source_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())

    def _fetch_asin_report_rows(
        self,
        *,
        start: date,
        end: date,
        asin: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        asin_filter = "AND r.asin = %s" if asin else ""
        params: List[Any] = [start, end]
        if asin:
            params.append(asin)
        params.extend([str(start), str(end), limit])

        sql = f"""
        WITH ak AS (
          SELECT sid, profile_id, country_code, name AS store_name
          FROM dim_lingxing_adv_account
          WHERE date = (SELECT MAX(date) FROM dim_lingxing_adv_account)
            AND name LIKE 'AK-%%'
            AND status = 1
        ),
        x AS (
          SELECT
            r.profile_id,
            r.campaign_id,
            r.ad_group_id,
            r.asin,
            r.sku,
            COALESCE(NULLIF(TRIM(r.keyword_text), ''), NULLIF(TRIM(r.targeting_text), '')) AS word_text,
            IFNULL(r.match_type, '') AS match_type,
            SUM(r.other_orders) AS orders,
            SUM(r.other_sales) AS sales,
            SUM(r.other_units) AS units
          FROM dwd_lingxing_sp_asin_reports_incr r
          JOIN ak ON CAST(r.profile_id AS CHAR) = CAST(ak.profile_id AS CHAR)
          WHERE r.date BETWEEN %s AND %s
            AND COALESCE(NULLIF(TRIM(r.keyword_text), ''), NULLIF(TRIM(r.targeting_text), '')) IS NOT NULL
            AND LOWER(COALESCE(NULLIF(TRIM(r.keyword_text), ''), NULLIF(TRIM(r.targeting_text), ''))) NOT IN
              ('loose-match', 'close-match', 'substitutes', 'complements')
            {asin_filter}
          GROUP BY r.profile_id, r.campaign_id, r.ad_group_id, r.asin, r.sku, word_text, r.match_type
          HAVING orders > 0 OR sales > 0
        )
        SELECT
          %s AS date_start,
          %s AS date_end,
          ak.store_name,
          ak.country_code,
          CAST(ak.profile_id AS CHAR) AS profile_id,
          x.asin,
          x.sku,
          'purchased_asin' AS word_type,
          x.word_text,
          x.match_type,
          CAST(IFNULL(x.campaign_id, 0) AS CHAR) AS campaign_id,
          IFNULL(c.name, '') AS campaign_name,
          CAST(IFNULL(x.ad_group_id, 0) AS CHAR) AS ad_group_id,
          IFNULL(g.name, '') AS ad_group_name,
          0 AS impressions,
          0 AS clicks,
          0 AS cost,
          x.orders,
          x.sales,
          x.units,
          0 AS ctr,
          0 AS cpc,
          0 AS cvr,
          0 AS acos,
          0 AS roas,
          'high_conversion' AS insight_type,
          'dwd_lingxing_sp_asin_reports_incr' AS source_table,
          'Purchased-product report has attributed orders/sales; prioritize natural Listing coverage.' AS reason
        FROM x
        JOIN ak ON CAST(x.profile_id AS CHAR) = CAST(ak.profile_id AS CHAR)
        LEFT JOIN dwd_lingxing_sp_campaigns_incr c
          ON c.profile_id = x.profile_id AND c.campaign_id = x.campaign_id
        LEFT JOIN dwd_lingxing_sp_ad_groups_incr g
          ON g.profile_id = x.profile_id AND g.ad_group_id = x.ad_group_id
        ORDER BY x.sales DESC, x.orders DESC
        LIMIT %s
        """
        with self._source_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())

    def _upsert_rows(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        fields = [
            "date_start", "date_end", "store_name", "country_code", "profile_id",
            "asin", "sku", "word_type", "word_text", "match_type", "campaign_id",
            "campaign_name", "ad_group_id", "ad_group_name", "impressions",
            "clicks", "cost", "orders", "sales", "units", "ctr", "cpc", "cvr",
            "acos", "roas", "insight_type", "source_table", "reason",
        ]
        placeholders = ", ".join(["%s"] * len(fields))
        updates = ", ".join([f"`{f}` = VALUES(`{f}`)" for f in fields if f not in ("date_start", "date_end")])
        sql = f"""
        INSERT INTO `{TABLE_NAME}` ({", ".join(f"`{f}`" for f in fields)})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {updates}, `updated_at` = CURRENT_TIMESTAMP
        """
        values = [tuple(row.get(f) for f in fields) for row in rows]
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, values)
        return len(rows)

    def query(
        self,
        *,
        asin: str,
        store_name: Optional[str] = None,
        days: int = 60,
        limit: int = 80,
    ) -> Dict[str, Any]:
        self.ensure_table()
        days = max(1, min(int(days or 60), 366))
        limit = max(1, min(int(limit or 80), 500))

        filters = ["asin = %s", "date_end >= %s"]
        params: List[Any] = [asin, date.today() - timedelta(days=days + 1)]
        if store_name:
            filters.append("store_name = %s")
            params.append(store_name)
        where = " AND ".join(filters)

        sql = f"""
        SELECT *
        FROM `{TABLE_NAME}`
        WHERE {where}
        ORDER BY
          CASE insight_type
            WHEN 'high_conversion' THEN 1
            WHEN 'high_click_no_order' THEN 2
            WHEN 'high_impression_low_ctr' THEN 3
            ELSE 4
          END,
          sales DESC,
          orders DESC,
          clicks DESC,
          impressions DESC
        LIMIT %s
        """
        params.append(limit)

        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = list(cur.fetchall())

        summary = {
            "high_conversion": 0,
            "high_click_no_order": 0,
            "high_impression_low_ctr": 0,
            "candidate": 0,
        }
        for row in rows:
            key = row.get("insight_type") or "candidate"
            summary[key] = summary.get(key, 0) + 1

        return {
            "asin": asin,
            "store_name": store_name or "",
            "days": days,
            "table": TABLE_NAME,
            "total": len(rows),
            "summary": summary,
            "items": rows,
        }

    @staticmethod
    def top_words_for_prompt(items: List[Dict[str, Any]], limit: int = 20) -> Tuple[List[str], str]:
        selected: List[str] = []
        lines: List[str] = []
        seen: set[str] = set()
        for item in items:
            word = str(item.get("word_text") or "").strip()
            if not word:
                continue
            low = word.lower()
            if low in seen:
                continue
            seen.add(low)
            if item.get("insight_type") == "high_conversion":
                selected.append(word)
            if len(lines) < limit:
                lines.append(
                    "- {word} [{kind}] {store} {word_type}: impressions={impressions}, "
                    "clicks={clicks}, orders={orders}, sales={sales}, cost={cost}, "
                    "ACOS={acos}, reason={reason}".format(
                        word=word,
                        kind=item.get("insight_type") or "candidate",
                        store=item.get("store_name") or "",
                        word_type=item.get("word_type") or "",
                        impressions=item.get("impressions") or 0,
                        clicks=item.get("clicks") or 0,
                        orders=item.get("orders") or 0,
                        sales=item.get("sales") or 0,
                        cost=item.get("cost") or 0,
                        acos=item.get("acos") or 0,
                        reason=item.get("reason") or "",
                    )
                )
            if len(selected) >= limit and len(lines) >= limit:
                break
        return selected[:limit], "\n".join(lines)


sp_ad_insight_service = SpAdInsightService()
