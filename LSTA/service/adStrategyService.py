"""SP 广告投放策略与动作反馈服务。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

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

ACTION_TABLE = "lsta_sp_ad_strategy_action"
FEEDBACK_TABLE = "lsta_sp_ad_strategy_feedback"
TARGET_HOST = "10.0.10.21"
TARGET_DB = "ric-train-base"


def _f(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except Exception:
        return 0.0


def _i(v: Any) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


def _metrics(row: Dict[str, Any]) -> Dict[str, Any]:
    impressions = _i(row.get("impressions"))
    clicks = _i(row.get("clicks"))
    cost = _f(row.get("cost"))
    orders = _i(row.get("orders"))
    sales = _f(row.get("sales"))
    return {
        **row,
        "impressions": impressions,
        "clicks": clicks,
        "cost": round(cost, 4),
        "orders": orders,
        "sales": round(sales, 4),
        "units": _i(row.get("units")),
        "ctr": round(clicks / impressions, 6) if impressions else 0,
        "cpc": round(cost / clicks, 4) if clicks else 0,
        "cvr": round(orders / clicks, 6) if clicks else 0,
        "acos": round(cost / sales, 6) if sales else 0,
        "roas": round(sales / cost, 4) if cost else 0,
    }


class AdStrategyService:
    """广告策略：只读 Doris，动作/反馈只写 10.0.10.21 ric-train-base。"""

    def _target_connect(self) -> pymysql.Connection:
        cfg = settings.mysql
        host = str(cfg.host or "")
        if host != TARGET_HOST:
            raise RuntimeError(f"安全限制：广告策略建表只允许连接 {TARGET_HOST}，当前 DB_HOST={host}")
        return pymysql.connect(
            host=TARGET_HOST,
            port=int(cfg.port or 3306),
            user=cfg.user,
            password=str(cfg.password or ""),
            database=TARGET_DB,
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

    def ensure_tables(self) -> None:
        action_sql = f"""
        CREATE TABLE IF NOT EXISTS `{ACTION_TABLE}` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `action_date` DATE NOT NULL,
          `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
          `asin` VARCHAR(32) NOT NULL DEFAULT '',
          `sku` VARCHAR(160) NOT NULL DEFAULT '',
          `store_name` VARCHAR(80) NOT NULL DEFAULT '',
          `country_code` VARCHAR(16) NOT NULL DEFAULT '',
          `profile_id` VARCHAR(64) NOT NULL DEFAULT '',
          `campaign_id` VARCHAR(64) NOT NULL DEFAULT '',
          `campaign_name` VARCHAR(512) NOT NULL DEFAULT '',
          `ad_group_id` VARCHAR(64) NOT NULL DEFAULT '',
          `ad_group_name` VARCHAR(512) NOT NULL DEFAULT '',
          `entity_type` VARCHAR(64) NOT NULL DEFAULT '',
          `entity_value` VARCHAR(512) NOT NULL DEFAULT '',
          `action_type` VARCHAR(64) NOT NULL,
          `before_value` VARCHAR(512) NOT NULL DEFAULT '',
          `after_value` VARCHAR(512) NOT NULL DEFAULT '',
          `reason` VARCHAR(1024) NOT NULL DEFAULT '',
          `operator` VARCHAR(80) NOT NULL DEFAULT '',
          `feedback_days` INT NOT NULL DEFAULT 7,
          `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          KEY `idx_ad_strategy_action_asin` (`asin`, `action_date`),
          KEY `idx_ad_strategy_action_campaign` (`campaign_id`, `ad_group_id`, `action_date`),
          KEY `idx_ad_strategy_action_entity` (`entity_type`, `entity_value`(160), `action_date`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        feedback_sql = f"""
        CREATE TABLE IF NOT EXISTS `{FEEDBACK_TABLE}` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `action_id` BIGINT NOT NULL,
          `before_start` DATE NOT NULL,
          `before_end` DATE NOT NULL,
          `after_start` DATE NOT NULL,
          `after_end` DATE NOT NULL,
          `before_json` JSON NOT NULL,
          `after_json` JSON NOT NULL,
          `result_type` VARCHAR(64) NOT NULL DEFAULT '',
          `summary` VARCHAR(1024) NOT NULL DEFAULT '',
          `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uk_ad_strategy_feedback_action` (`action_id`, `before_start`, `after_end`),
          KEY `idx_ad_strategy_feedback_action` (`action_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(action_sql)
                cur.execute(feedback_sql)

    def analyze(self, *, asin: str = "", sku: str = "", store_name: str = "", country_code: str = "",
                days: int = 30, feedback_days: int = 7, limit: int = 80) -> Dict[str, Any]:
        self.ensure_tables()
        days = max(7, min(int(days or 30), 180))
        feedback_days = max(3, min(int(feedback_days or 7), 30))
        limit = max(10, min(int(limit or 80), 300))
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)
        prev_start = start - timedelta(days=days)
        prev_end = start - timedelta(days=1)

        product_rows = self._fetch_product_rows(start, end, asin, sku, store_name, country_code, limit)
        search_rows = self._fetch_term_rows("search_term", start, end, asin, sku, store_name, country_code, limit)
        keyword_rows = self._fetch_term_rows("keyword", start, end, asin, sku, store_name, country_code, limit)
        purchased_rows = self._fetch_purchased_asin_rows(start, end, asin, sku, store_name, country_code, limit)
        current = self._fetch_total_metrics(start, end, asin, sku, store_name, country_code)
        previous = self._fetch_total_metrics(prev_start, prev_end, asin, sku, store_name, country_code)
        actions = self._recommend_actions(search_rows, keyword_rows, product_rows, purchased_rows, feedback_days)
        pending_feedback = self.feedback(action_id=None, asin=asin, days=feedback_days).get("items", [])

        return {
            "date_start": str(start),
            "date_end": str(end),
            "compare_start": str(prev_start),
            "compare_end": str(prev_end),
            "filters": {"asin": asin, "sku": sku, "store_name": store_name, "country_code": country_code},
            "current": current,
            "previous": previous,
            "trend": self._trend(current, previous),
            "product_rows": product_rows,
            "search_terms": search_rows,
            "keywords": keyword_rows,
            "purchased_asins": purchased_rows,
            "recommended_actions": actions[:limit],
            "action_feedback": pending_feedback,
            "target_table": f"{TARGET_HOST}.{TARGET_DB}.{ACTION_TABLE}",
        }

    def create_action(self, payload: Dict[str, Any], operator: str = "") -> Dict[str, Any]:
        self.ensure_tables()
        action_date = payload.get("action_date") or str(date.today())
        fields = [
            "action_date", "asin", "sku", "store_name", "country_code", "profile_id",
            "campaign_id", "campaign_name", "ad_group_id", "ad_group_name",
            "entity_type", "entity_value", "action_type", "before_value",
            "after_value", "reason", "operator", "feedback_days",
        ]
        row = {f: payload.get(f, "") for f in fields}
        row["action_date"] = action_date
        row["operator"] = row.get("operator") or operator or ""
        row["feedback_days"] = int(row.get("feedback_days") or 7)
        sql = f"""
        INSERT INTO `{ACTION_TABLE}` ({", ".join(f"`{f}`" for f in fields)})
        VALUES ({", ".join(["%s"] * len(fields))})
        """
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [row[f] for f in fields])
                action_id = cur.lastrowid
        return {"success": True, "action_id": action_id, "table": f"{TARGET_HOST}.{TARGET_DB}.{ACTION_TABLE}"}

    def feedback(self, *, action_id: Optional[int], asin: str = "", days: int = 7) -> Dict[str, Any]:
        self.ensure_tables()
        filters = []
        params: List[Any] = []
        if action_id:
            filters.append("id = %s")
            params.append(action_id)
        if asin:
            filters.append("asin = %s")
            params.append(asin)
        where = "WHERE " + " AND ".join(filters) if filters else ""
        sql = f"""
        SELECT *
        FROM `{ACTION_TABLE}`
        {where}
        ORDER BY action_date DESC, id DESC
        LIMIT 50
        """
        with self._target_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                actions = list(cur.fetchall())
        items = []
        for action in actions:
            fb_days = int(action.get("feedback_days") or days or 7)
            action_date = action["action_date"]
            if isinstance(action_date, datetime):
                action_date = action_date.date()
            before_start = action_date - timedelta(days=fb_days)
            before_end = action_date - timedelta(days=1)
            after_start = action_date + timedelta(days=1)
            after_end = min(date.today() - timedelta(days=1), action_date + timedelta(days=fb_days))
            if after_end < after_start:
                items.append({"action": action, "status": "waiting", "summary": "动作后数据尚未到反馈周期。"})
                continue
            before = self._fetch_scope_metrics(action, before_start, before_end)
            after = self._fetch_scope_metrics(action, after_start, after_end)
            result_type, summary = self._judge_feedback(before, after)
            items.append({
                "action": action,
                "status": "evaluated",
                "before_start": str(before_start),
                "before_end": str(before_end),
                "after_start": str(after_start),
                "after_end": str(after_end),
                "before": before,
                "after": after,
                "result_type": result_type,
                "summary": summary,
            })
        return {"items": items}

    def _base_filters(self, asin: str, sku: str, store_name: str, country_code: str, alias: str = "p") -> tuple[str, List[Any]]:
        filters = []
        params: List[Any] = []
        if asin:
            filters.append(f"{alias}.asin = %s")
            params.append(asin)
        if sku:
            filters.append(f"{alias}.sku = %s")
            params.append(sku)
        if store_name:
            filters.append("ak.name = %s")
            params.append(store_name)
        if country_code:
            filters.append("ak.country_code = %s")
            params.append(country_code)
        return (" AND " + " AND ".join(filters)) if filters else "", params

    def _ak_cte(self) -> str:
        return """
        ak AS (
          SELECT profile_id, country_code, name
          FROM dim_lingxing_adv_account
          WHERE date = (SELECT MAX(date) FROM dim_lingxing_adv_account)
            AND status = 1
        )
        """

    def _fetch_total_metrics(self, start: date, end: date, asin: str, sku: str, store_name: str, country_code: str) -> Dict[str, Any]:
        extra, params = self._base_filters(asin, sku, store_name, country_code, "p")
        sql = f"""
        WITH {self._ak_cte()}
        SELECT
          SUM(p.impressions) AS impressions,
          SUM(p.clicks) AS clicks,
          SUM(p.cost) AS cost,
          SUM(p.orders) AS orders,
          SUM(p.sales) AS sales,
          SUM(p.units) AS units
        FROM dwd_lingxing_sp_product_ad_reports_incr p
        JOIN ak ON CAST(p.profile_id AS CHAR) = CAST(ak.profile_id AS CHAR)
        WHERE p.date BETWEEN %s AND %s {extra}
        """
        with self._source_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [start, end, *params])
                return _metrics(cur.fetchone() or {})

    def _fetch_product_rows(self, start: date, end: date, asin: str, sku: str, store_name: str, country_code: str, limit: int) -> List[Dict[str, Any]]:
        extra, params = self._base_filters(asin, sku, store_name, country_code, "p")
        sql = f"""
        WITH {self._ak_cte()}
        SELECT
          ak.name AS store_name, ak.country_code, CAST(p.profile_id AS CHAR) AS profile_id,
          p.asin, p.sku, CAST(p.campaign_id AS CHAR) AS campaign_id, IFNULL(c.name, '') AS campaign_name,
          CAST(p.ad_group_id AS CHAR) AS ad_group_id, IFNULL(g.name, '') AS ad_group_name,
          SUM(p.impressions) AS impressions, SUM(p.clicks) AS clicks, SUM(p.cost) AS cost,
          SUM(p.orders) AS orders, SUM(p.sales) AS sales, SUM(p.units) AS units
        FROM dwd_lingxing_sp_product_ad_reports_incr p
        JOIN ak ON CAST(p.profile_id AS CHAR) = CAST(ak.profile_id AS CHAR)
        LEFT JOIN dwd_lingxing_sp_campaigns_incr c ON c.profile_id = p.profile_id AND c.campaign_id = p.campaign_id
        LEFT JOIN dwd_lingxing_sp_ad_groups_incr g ON g.profile_id = p.profile_id AND g.ad_group_id = p.ad_group_id
        WHERE p.date BETWEEN %s AND %s {extra}
        GROUP BY ak.name, ak.country_code, p.profile_id, p.asin, p.sku, p.campaign_id, c.name, p.ad_group_id, g.name
        ORDER BY cost DESC, sales DESC
        LIMIT %s
        """
        with self._source_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [start, end, *params, limit])
                return [_metrics(r) for r in cur.fetchall()]

    def _fetch_term_rows(self, kind: str, start: date, end: date, asin: str, sku: str, store_name: str, country_code: str, limit: int) -> List[Dict[str, Any]]:
        table = "dwd_lingxing_sp_word_reports_incr" if kind == "search_term" else "dwd_lingxing_sp_key_word_reports_incr"
        word_col = "r.`query`" if kind == "search_term" else "r.keyword_text"
        extra, params = self._base_filters(asin, sku, store_name, country_code, "p")
        sql = f"""
        WITH {self._ak_cte()},
        p AS (
          SELECT profile_id, campaign_id, ad_group_id, asin, sku
          FROM dwd_lingxing_sp_product_ad_reports_incr
          WHERE date BETWEEN %s AND %s
          GROUP BY profile_id, campaign_id, ad_group_id, asin, sku
        )
        SELECT
          ak.name AS store_name, ak.country_code, CAST(r.profile_id AS CHAR) AS profile_id,
          p.asin, p.sku, CAST(r.campaign_id AS CHAR) AS campaign_id, IFNULL(c.name, '') AS campaign_name,
          CAST(r.ad_group_id AS CHAR) AS ad_group_id, IFNULL(g.name, '') AS ad_group_name,
          '{kind}' AS entity_type, {word_col} AS entity_value, IFNULL(r.match_type, '') AS match_type,
          SUM(r.impressions) AS impressions, SUM(r.clicks) AS clicks, SUM(r.cost) AS cost,
          SUM(r.orders) AS orders, SUM(r.sales) AS sales, SUM(r.units) AS units
        FROM {table} r
        JOIN p ON p.profile_id = r.profile_id AND p.ad_group_id = r.ad_group_id
          AND (p.campaign_id = r.campaign_id OR r.campaign_id IS NULL OR r.campaign_id = 0)
        JOIN ak ON CAST(r.profile_id AS CHAR) = CAST(ak.profile_id AS CHAR)
        LEFT JOIN dwd_lingxing_sp_campaigns_incr c ON c.profile_id = r.profile_id AND c.campaign_id = r.campaign_id
        LEFT JOIN dwd_lingxing_sp_ad_groups_incr g ON g.profile_id = r.profile_id AND g.ad_group_id = r.ad_group_id
        WHERE r.date BETWEEN %s AND %s
          AND {word_col} IS NOT NULL AND TRIM({word_col}) != '' {extra}
        GROUP BY ak.name, ak.country_code, r.profile_id, p.asin, p.sku, r.campaign_id, c.name, r.ad_group_id, g.name, {word_col}, r.match_type
        HAVING clicks > 0 OR impressions > 0 OR orders > 0
        ORDER BY cost DESC, sales DESC, impressions DESC
        LIMIT %s
        """
        with self._source_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [start, end, start, end, *params, limit])
                return [_metrics(r) for r in cur.fetchall()]

    def _fetch_purchased_asin_rows(self, start: date, end: date, asin: str, sku: str, store_name: str, country_code: str, limit: int) -> List[Dict[str, Any]]:
        extra, params = self._base_filters(asin, sku, store_name, country_code, "r")
        sql = f"""
        WITH {self._ak_cte()}
        SELECT
          ak.name AS store_name, ak.country_code, CAST(r.profile_id AS CHAR) AS profile_id,
          r.asin, r.sku, CAST(r.campaign_id AS CHAR) AS campaign_id, IFNULL(c.name, '') AS campaign_name,
          CAST(r.ad_group_id AS CHAR) AS ad_group_id, IFNULL(g.name, '') AS ad_group_name,
          'purchased_asin' AS entity_type, r.other_asin AS entity_value,
          SUM(r.other_orders) AS orders, SUM(r.other_sales) AS sales, SUM(r.other_units) AS units,
          0 AS impressions, 0 AS clicks, 0 AS cost
        FROM dwd_lingxing_sp_asin_reports_incr r
        JOIN ak ON CAST(r.profile_id AS CHAR) = CAST(ak.profile_id AS CHAR)
        LEFT JOIN dwd_lingxing_sp_campaigns_incr c ON c.profile_id = r.profile_id AND c.campaign_id = r.campaign_id
        LEFT JOIN dwd_lingxing_sp_ad_groups_incr g ON g.profile_id = r.profile_id AND g.ad_group_id = r.ad_group_id
        WHERE r.date BETWEEN %s AND %s
          AND r.other_asin IS NOT NULL AND TRIM(r.other_asin) != '' {extra}
        GROUP BY ak.name, ak.country_code, r.profile_id, r.asin, r.sku, r.campaign_id, c.name, r.ad_group_id, g.name, r.other_asin
        HAVING orders > 0 OR sales > 0
        ORDER BY sales DESC, orders DESC
        LIMIT %s
        """
        with self._source_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [start, end, *params, limit])
                return [_metrics(r) for r in cur.fetchall()]

    def _fetch_scope_metrics(self, action: Dict[str, Any], start: date, end: date) -> Dict[str, Any]:
        return self._fetch_total_metrics(
            start,
            end,
            str(action.get("asin") or ""),
            str(action.get("sku") or ""),
            str(action.get("store_name") or ""),
            str(action.get("country_code") or ""),
        )

    def _trend(self, current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for k in ("impressions", "clicks", "cost", "orders", "sales", "ctr", "cvr", "acos", "roas"):
            prev = _f(previous.get(k))
            cur = _f(current.get(k))
            out[k] = round((cur - prev) / prev, 4) if prev else (1 if cur > 0 else 0)
        return out

    def _recommend_actions(self, search_rows, keyword_rows, product_rows, purchased_rows, feedback_days: int) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []

        def push(row, action_type, reason, before="", after=""):
            actions.append({
                "action_type": action_type,
                "entity_type": row.get("entity_type") or "product",
                "entity_value": row.get("entity_value") or row.get("asin") or "",
                "asin": row.get("asin") or "",
                "sku": row.get("sku") or "",
                "store_name": row.get("store_name") or "",
                "country_code": row.get("country_code") or "",
                "profile_id": row.get("profile_id") or "",
                "campaign_id": row.get("campaign_id") or "",
                "campaign_name": row.get("campaign_name") or "",
                "ad_group_id": row.get("ad_group_id") or "",
                "ad_group_name": row.get("ad_group_name") or "",
                "before_value": before,
                "after_value": after,
                "reason": reason,
                "feedback_days": feedback_days,
                "metrics": row,
            })

        for row in [*search_rows, *keyword_rows]:
            if row["orders"] > 0 and row["sales"] > 0 and (row["acos"] == 0 or row["acos"] <= 0.35):
                push(row, "add_exact_or_raise_bid", "高转化且 ACOS 可控，建议收割到精准词或提高竞价。", f"ACOS={row['acos']}", "bid +10%~20%")
            elif row["clicks"] >= 15 and row["orders"] == 0:
                push(row, "negative_or_lower_bid", "点击较多但无订单，建议降竞价或加入否定，并检查 Listing 承接。", f"clicks={row['clicks']}, cost={row['cost']}", "bid -20% / negative")
            elif row["impressions"] >= 1000 and row["ctr"] < 0.003:
                push(row, "optimize_ctr_or_reduce", "曝光高但 CTR 低，建议优化主图/标题或降低弱相关流量。", f"CTR={row['ctr']}", "optimize image/title")
        for row in product_rows:
            if row["cost"] > 0 and row["sales"] == 0 and row["clicks"] >= 20:
                push(row, "pause_product_ad", "商品广告花费和点击较高但无销售，建议暂停或重组广告组。", f"cost={row['cost']}", "pause")
        for row in purchased_rows:
            if row["orders"] > 0:
                push(row, "add_product_target", "已购商品报表出现成交 ASIN，建议加入商品投放或竞品对标。", f"sales={row['sales']}", "product targeting")
        actions.sort(key=lambda x: (_f(x["metrics"].get("sales")), _f(x["metrics"].get("cost"))), reverse=True)
        return actions

    def _judge_feedback(self, before: Dict[str, Any], after: Dict[str, Any]) -> tuple[str, str]:
        before_orders, after_orders = _i(before.get("orders")), _i(after.get("orders"))
        before_sales, after_sales = _f(before.get("sales")), _f(after.get("sales"))
        before_acos, after_acos = _f(before.get("acos")), _f(after.get("acos"))
        if after_orders > before_orders and (after_acos <= before_acos or before_acos == 0):
            return "effective", "动作后订单提升且 ACOS 未恶化，建议继续放量或保持。"
        if after_sales > before_sales and after_acos <= max(before_acos * 1.15, 0.35):
            return "partially_effective", "动作后销售额提升，ACOS 可接受，继续观察。"
        if after_acos > before_acos * 1.25 and after_acos > 0.35:
            return "worse", "动作后 ACOS 明显恶化，建议回退或降竞价。"
        return "observe", "反馈不显著，建议继续观察或扩大样本周期。"


ad_strategy_service = AdStrategyService()
