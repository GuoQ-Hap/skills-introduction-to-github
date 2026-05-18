"""三维诊断 Doris SQL 生成（单一来源，供 LSTA 后端与前端经 API 共用）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def _sanitize_sql_literal(s: str) -> str:
    return (s or "").replace("'", "")


@dataclass
class TriDimThresholds:
    """与前端 ThresholdConfig 中诊断三项一致，单位为「百分比」数值（如 0.3 表示 0.3%）。"""

    diag_ctr_abs: float = 0.3
    diag_cvr_abs: float = 10.0
    diag_sess_dec: float = 20.0

    @classmethod
    def merge(cls, raw: Optional[Dict[str, Any]]) -> "TriDimThresholds":
        if not raw:
            return cls()
        def _f(key_snake: str, key_camel: str, default: float) -> float:
            v = raw.get(key_snake)
            if v is None:
                v = raw.get(key_camel)
            if v is None:
                return default
            return float(v)

        return cls(
            diag_ctr_abs=_f("diag_ctr_abs", "diagCtrAbs", cls.diag_ctr_abs),
            diag_cvr_abs=_f("diag_cvr_abs", "diagCvrAbs", cls.diag_cvr_abs),
            diag_sess_dec=_f("diag_sess_dec", "diagSessDec", cls.diag_sess_dec),
        )


def _dims_flags(dims: Optional[List[str]]) -> Tuple[bool, bool, bool]:
    """与 DataAnalysis.tsx 中 diagCommon 一致：dims 为 None 表示三维度全开；[] 则全关。"""
    if dims is None:
        return True, True, True
    if len(dims) == 0:
        return False, False, False
    s = {str(d).lower() for d in dims}
    return ("ctr" in s), ("cvr" in s), ("sessions" in s)


def _diag_common(
    dims: Optional[List[str]],
    thresholds: TriDimThresholds,
) -> Tuple[str, float, float, float]:
    do_ctr, do_cvr, do_sess = _dims_flags(dims)
    ctr_abs = thresholds.diag_ctr_abs / 100.0
    cvr_abs = thresholds.diag_cvr_abs / 100.0
    sess_dec = thresholds.diag_sess_dec / 100.0

    where_clauses: List[str] = []
    if do_ctr:
        where_clauses.append(
            f"(p.product_ctr < b.cat_avg_ctr AND p.product_ctr < {ctr_abs})"
        )
    if do_cvr:
        where_clauses.append(
            f"(p.product_cvr < b.cat_avg_cvr AND p.product_cvr < {cvr_abs})"
        )
    if do_sess:
        where_clauses.append(
            "(se.earlier_sessions > 0\n"
            f"        AND (sr.recent_sessions - se.earlier_sessions) * 1.0 / se.earlier_sessions < -{sess_dec}\n"
            "        AND sr.avg_stock > 0)"
        )
    where_str = (
        "WHERE\n    " + "\n    OR ".join(where_clauses)
        if where_clauses
        else ""
    )
    return where_str, ctr_abs, cvr_abs, sess_dec


def build_diagnostic_count_sql(
    date_range: int,
    *,
    asin: Optional[str] = None,
    dims: Optional[List[str]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
    row_filter: bool = True,
    sales_apartment: Optional[str] = None,
) -> str:
    th = TriDimThresholds.merge(
        thresholds if isinstance(thresholds, dict) else None
    )
    where_str, _, _, _ = _diag_common(dims, th)
    half = max(1, int(date_range // 2))
    asin_where = ""
    if asin:
        asin_where = f"\n      AND a.asin = '{_sanitize_sql_literal(asin)}'"
    sa_filter = ""
    if sales_apartment:
        sa_filter = f"\n      AND dim.sales_apartment = '{_sanitize_sql_literal(sales_apartment)}'"

    outer_where = f"\n{where_str}" if (row_filter and where_str) else ""
    return f"""WITH category_benchmark AS (
    SELECT
        a.category_2,
        CASE WHEN SUM(a.impressions) > 0
             THEN SUM(a.clicks) * 1.0 / SUM(a.impressions)
             ELSE 0 END AS cat_avg_ctr,
        CASE WHEN SUM(a.clicks) > 0
             THEN SUM(a.ad_order_quantity) * 1.0 / SUM(a.clicks)
             ELSE 0 END AS cat_avg_cvr
    FROM ads_lingxing_sc_sales_daily_new a
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range} DAY)
      AND a.category_2 IS NOT NULL AND a.category_2 != ''
    GROUP BY a.category_2
),
product_30d AS (
    SELECT
        a.asin,
        a.price_list_seller_sku AS msku,
        a.store_name,
        a.country_code,
        a.category_2,
        dim.brand,
        dim.salesman,
        dim.sales_apartment,
        SUM(a.impressions) AS total_impressions,
        SUM(a.clicks) AS total_clicks,
        SUM(a.ad_order_quantity) AS total_ad_orders,
        CASE WHEN SUM(a.impressions) > 0
             THEN SUM(a.clicks) * 1.0 / SUM(a.impressions)
             ELSE 0 END AS product_ctr,
        CASE WHEN SUM(a.clicks) > 0
             THEN SUM(a.ad_order_quantity) * 1.0 / SUM(a.clicks)
             ELSE 0 END AS product_cvr
    FROM ads_lingxing_sc_sales_daily_new a
    LEFT JOIN dim_lingxing_product_info dim
        ON a.price_list_seller_sku = dim.msku
        AND a.country_code = dim.country_code
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range} DAY)
      AND a.category_2 IS NOT NULL AND a.category_2 != ''
      AND a.impressions > 0
      AND a.clicks > 0{asin_where}{sa_filter}
    GROUP BY a.asin, a.price_list_seller_sku,
             a.store_name, a.country_code, a.category_2,
             dim.brand, dim.salesman, dim.sales_apartment
),
sessions_earlier AS (
    SELECT a.asin, a.price_list_seller_sku AS msku,
           a.store_name, a.country_code,
           SUM(a.sessions_total) AS earlier_sessions
    FROM ads_lingxing_sc_sales_daily_new a
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range} DAY)
      AND a.date < DATE_SUB(CURRENT_DATE(), INTERVAL {half} DAY)
    GROUP BY a.asin, a.price_list_seller_sku, a.store_name, a.country_code
),
sessions_recent AS (
    SELECT a.asin, a.price_list_seller_sku AS msku,
           a.store_name, a.country_code,
           SUM(a.sessions_total) AS recent_sessions,
           AVG(a.afn_fulfillable_quantity) AS avg_stock
    FROM ads_lingxing_sc_sales_daily_new a
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {half} DAY)
      AND a.date < CURRENT_DATE()
    GROUP BY a.asin, a.price_list_seller_sku, a.store_name, a.country_code
)
SELECT COUNT(*) AS total
FROM product_30d p
JOIN category_benchmark b ON p.category_2 = b.category_2
LEFT JOIN sessions_earlier se ON p.asin = se.asin AND p.msku = se.msku AND p.store_name = se.store_name AND p.country_code = se.country_code
LEFT JOIN sessions_recent sr ON p.asin = sr.asin AND p.msku = sr.msku AND p.store_name = sr.store_name AND p.country_code = sr.country_code{outer_where}"""


def build_diagnostic_sql(
    date_range: int,
    *,
    asin: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    dims: Optional[List[str]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
    row_filter: bool = True,
    sales_apartment: Optional[str] = None,
) -> str:
    th = TriDimThresholds.merge(
        thresholds if isinstance(thresholds, dict) else None
    )
    where_str, ctr_abs, cvr_abs, sess_dec = _diag_common(dims, th)
    half = max(1, int(date_range // 2))
    limit = page_size if page_size > 0 else (50 if asin else 100)
    offset = (page - 1) * limit if page and page > 1 else 0
    limit_clause = f"LIMIT {limit} OFFSET {offset}"
    asin_where = ""
    if asin:
        asin_where = f"\n      AND a.asin = '{_sanitize_sql_literal(asin)}'"
    sa_filter = ""
    if sales_apartment:
        sa_filter = f"\n      AND dim.sales_apartment = '{_sanitize_sql_literal(sales_apartment)}'"

    outer_where = f"\n{where_str}" if (row_filter and where_str) else ""

    return f"""WITH category_benchmark AS (
    SELECT
        a.category_2,
        CASE WHEN SUM(a.impressions) > 0
             THEN SUM(a.clicks) * 1.0 / SUM(a.impressions)
             ELSE 0 END AS cat_avg_ctr,
        CASE WHEN SUM(a.clicks) > 0
             THEN SUM(a.ad_order_quantity) * 1.0 / SUM(a.clicks)
             ELSE 0 END AS cat_avg_cvr
    FROM ads_lingxing_sc_sales_daily_new a
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range} DAY)
      AND a.category_2 IS NOT NULL AND a.category_2 != ''
    GROUP BY a.category_2
),
product_30d AS (
    SELECT
        a.asin,
        a.price_list_seller_sku AS msku,
        a.spu,
        a.store_name,
        a.country_code,
        a.category_2,
        dim.brand,
        dim.msku_status,
        dim.salesman,
        dim.product_manager,
        dim.sales_apartment,
        SUM(a.clicks) AS total_clicks,
        SUM(a.impressions) AS total_impressions,
        SUM(a.ad_order_quantity) AS total_ad_orders,
        SUM(a.volume) AS total_volume,
        ROUND(SUM(a.amount), 2) AS total_amount,
        CASE WHEN SUM(a.impressions) > 0
             THEN SUM(a.clicks) * 1.0 / SUM(a.impressions)
             ELSE 0 END AS product_ctr,
        CASE WHEN SUM(a.clicks) > 0
             THEN SUM(a.ad_order_quantity) * 1.0 / SUM(a.clicks)
             ELSE 0 END AS product_cvr
    FROM ads_lingxing_sc_sales_daily_new a
    LEFT JOIN dim_lingxing_product_info dim
        ON a.price_list_seller_sku = dim.msku
        AND a.country_code = dim.country_code
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range} DAY)
      AND a.category_2 IS NOT NULL AND a.category_2 != ''
      AND a.impressions > 0
      AND a.clicks > 0{asin_where}{sa_filter}
    GROUP BY a.asin, a.price_list_seller_sku, a.spu,
             a.store_name, a.country_code, a.category_2,
             dim.brand, dim.msku_status, dim.salesman, dim.product_manager, dim.sales_apartment
),
sessions_earlier AS (
    SELECT a.asin, a.price_list_seller_sku AS msku,
           a.store_name, a.country_code,
           SUM(a.sessions_total) AS earlier_sessions
    FROM ads_lingxing_sc_sales_daily_new a
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range} DAY)
      AND a.date < DATE_SUB(CURRENT_DATE(), INTERVAL {half} DAY)
    GROUP BY a.asin, a.price_list_seller_sku, a.store_name, a.country_code
),
sessions_recent AS (
    SELECT a.asin, a.price_list_seller_sku AS msku,
           a.store_name, a.country_code,
           SUM(a.sessions_total) AS recent_sessions,
           AVG(a.afn_fulfillable_quantity) AS avg_stock
    FROM ads_lingxing_sc_sales_daily_new a
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {half} DAY)
      AND a.date < CURRENT_DATE()
    GROUP BY a.asin, a.price_list_seller_sku, a.store_name, a.country_code
)
SELECT
    p.asin,
    p.msku,
    p.spu,
    p.store_name,
    p.country_code,
    p.category_2,
    p.brand,
    p.msku_status,
    p.salesman,
    p.product_manager,
    p.sales_apartment,
    p.total_volume,
    p.total_amount,
    ROUND(p.product_ctr * 100, 4) AS product_ctr_pct,
    ROUND(b.cat_avg_ctr * 100, 4) AS cat_avg_ctr_pct,
    ROUND(p.product_cvr * 100, 4) AS product_cvr_pct,
    ROUND(b.cat_avg_cvr * 100, 4) AS cat_avg_cvr_pct,
    CASE WHEN p.product_ctr < b.cat_avg_ctr AND p.product_ctr < {ctr_abs} THEN 1 ELSE 0 END AS flag_ctr_low,
    CASE WHEN p.product_cvr < b.cat_avg_cvr AND p.product_cvr < {cvr_abs} THEN 1 ELSE 0 END AS flag_cvr_low,
    se.earlier_sessions,
    sr.recent_sessions,
    ROUND((sr.recent_sessions - se.earlier_sessions) * 100.0 / NULLIF(se.earlier_sessions, 0), 2) AS sessions_change_pct,
    ROUND(sr.avg_stock, 0) AS avg_stock_qty,
    CASE WHEN se.earlier_sessions > 0
          AND (sr.recent_sessions - se.earlier_sessions) * 1.0 / se.earlier_sessions < -{sess_dec}
          AND sr.avg_stock > 0
         THEN 1 ELSE 0 END AS flag_sessions_decline,
    CONCAT_WS(' | ',
        CASE WHEN p.product_ctr < b.cat_avg_ctr AND p.product_ctr < {ctr_abs} THEN '优化标题+主图' END,
        CASE WHEN p.product_cvr < b.cat_avg_cvr AND p.product_cvr < {cvr_abs} THEN '优化五点+A+' END,
        CASE WHEN se.earlier_sessions > 0
              AND (sr.recent_sessions - se.earlier_sessions) * 1.0 / se.earlier_sessions < -{sess_dec}
              AND sr.avg_stock > 0 THEN '必须优化(排名下滑)' END
    ) AS optimization_actions,
    (CASE WHEN p.product_ctr < b.cat_avg_ctr AND p.product_ctr < {ctr_abs} THEN 1 ELSE 0 END)
  + (CASE WHEN p.product_cvr < b.cat_avg_cvr AND p.product_cvr < {cvr_abs} THEN 1 ELSE 0 END)
  + (CASE WHEN se.earlier_sessions > 0
          AND (sr.recent_sessions - se.earlier_sessions) * 1.0 / se.earlier_sessions < -{sess_dec}
          AND sr.avg_stock > 0 THEN 1 ELSE 0 END) AS hit_count
FROM product_30d p
JOIN category_benchmark b ON p.category_2 = b.category_2
LEFT JOIN sessions_earlier se ON p.asin = se.asin AND p.msku = se.msku AND p.store_name = se.store_name AND p.country_code = se.country_code
LEFT JOIN sessions_recent sr ON p.asin = sr.asin AND p.msku = sr.msku AND p.store_name = sr.store_name AND p.country_code = sr.country_code{outer_where}
ORDER BY hit_count DESC, p.total_amount DESC
{limit_clause}"""
