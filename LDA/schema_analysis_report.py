"""
数据库Schema联合分析报告 & CTR/CVR计算脚本
===========================================
分析文件:
  - schema_raw copy.json  (358张表的原始字段定义)
  - schema_index copy.json (表索引、分层、关键词映射)

分析目标:
  1. 识别重复和无效内容
  2. 提炼核心基础表
  3. 给出CTR/CVR计算公式和获取脚本
"""

import json

with open('data/schema_raw copy.json', 'r', encoding='utf-8') as f:
    raw = json.load(f)

with open('data/schema_index copy.json', 'r', encoding='utf-8') as f:
    index = json.load(f)


# ============================================================
# 一、核心表精简结果
# ============================================================
CORE_TABLES = {
    "CTR/CVR计算-方案A（ADS宽表，含category_2）": {
        "主表": "ads_lingxing_sc_sales_daily_new",
        "说明": "最完整的ADS层销售日报(128列)，直接含category_2分类字段",
        "关键字段": [
            "date (日期)", "asin (ASIN)", "price_list_seller_sku (MSKU)",
            "spu (SPU)", "store_name (店铺名)", "country_code (国家代码)",
            "clicks (点击量)", "impressions (展示量)", "ad_order_quantity (广告订单量)",
            "spend (广告花费)", "ad_sales_amount (广告销售额)", "volume (销量)",
            "amount (销售额)", "category_1 (一级类目)", "category_2 (二级类目)",
            "category_3 (三级类目)"
        ]
    },
    "CTR/CVR计算-方案B（DWD明细+维度JOIN）": {
        "明细表": "dwd_lingxing_sc_product_performance_asin",
        "维度表": "dim_lingxing_product_info",
        "说明": "DWD表已内置ctr/cvr/acos字段，但需JOIN dim表获取category_2",
        "关键字段_明细": [
            "date (日期)", "clicks (点击量)", "impressions (展示量)",
            "ad_order_quantity (广告订单量)", "ctr (内置CTR)", "cvr (内置CVR)",
            "acos (广告花费/广告销售额)", "spend (广告花费)"
        ],
        "关键字段_维度": [
            "asin (ASIN)", "store_name (店铺名)", "country_code (国家代码)",
            "category_2 (二级类目)"
        ]
    }
}


# ============================================================
# 二、重复/无效表清单
# ============================================================
def get_redundant_tables():
    redundant = {
        "sc_sales_daily冗余版本(保留_new)": [
            "ads_lingxing_sc_sales_daily",
            "ads_lingxing_sc_sales_daily2",
            "ads_lingxing_sc_sales_daily_tmp1",
            "ads_lingxing_sc_sales_daily_tmp2",
        ],
        "ODS冗余(DWD已覆盖)": [
            "ods_lingxing_sc_product_performance",
            "ods_lingxing_sc_product_performance_asin",
            "ods_lingxing_sc_product_performance_msku",
            "ods_lingxing_awd_warehouse_detail",
            "ods_lingxing_fba_warehouse_detail",
            "ods_lingxing_inventory_details",
            "ods_lingxing_sc_rate",
            "ods_lingxing_sc_warehouse",
            "ods_original_sales_estimates",
        ],
        "临时表/测试表": [t for t in raw.keys() if any(x in t for x in ['_tmp', '_test', '_temp'])],
        "多版本冗余(保留最新)": [
            "dim_lingxing_sales_estimates (保留_v1)",
            "dim_lingxing_sales_estimates_everyday_incr (保留_v1_incr)",
            "dim_lingxing_sales_estimates_everyday_incr2",
            "dim_lingxing_sales_estimates_everyday_incr3",
            "dim_lingxing_sales_estimates_monthly (保留_v1)",
            "dim_lingxing_stocking_rules (保留_v1)",
            "dim_lingxing_stocking_rules2",
            "ods_lingxing_sales_estimates (保留_v2)",
            "ods_lingxing_sales_estimates_v1",
            "ods_lingxing_sales_estimates_monthly (保留_v1)",
            "ods_lingxing_stocking_rules (保留_v1)",
            "ods_original_sales_estimates (保留_v1)",
        ]
    }
    return redundant


# ============================================================
# 三、CTR/CVR 计算公式
# ============================================================
FORMULAS = """
=======================================================================
 CTR/CVR 计算公式
=======================================================================

 CTR (Click-Through Rate, 点击率):
   CTR = clicks / impressions
   含义: 广告展示后被点击的比率
   类目均值: GROUP BY category_2

 CVR (Conversion Rate, 转化率):
   CVR = ad_order_quantity / clicks
   含义: 点击后产生订单的转化比率
   类目均值: GROUP BY category_2

 附加指标:
   ACOS = spend / ad_sales_amount (广告花费占广告销售额比)
   广告订单占比 = ad_order_quantity / volume (广告订单量占总销量比)
   CPC = spend / clicks (每次点击成本)

=======================================================================
 产品具体分析 - 三维诊断规则
=======================================================================

 维度1: CTR是否低于类目平均?
   条件: product_ctr < cat_avg_ctr AND product_ctr < 0.3%
   结论: -> 优化标题 + 主图

 维度2: CVR是否低于类目平均?
   条件: product_cvr < cat_avg_cvr AND product_cvr < 10%
   结论: -> 优化五点描述 + A+页面

 维度3: 近30天自然排名是否持续下滑?
   条件: sessions_total 前15天 vs 后15天下滑 >20%
          且 afn_fulfillable_quantity > 0 (无断货)
   结论: -> 必须优化

 关键字段来源 (均来自 ads_lingxing_sc_sales_daily_new):
   - clicks / impressions / ad_order_quantity: CTR/CVR计算
   - sessions_total: 总流量(含自然+广告)，作为排名代理指标
   - afn_fulfillable_quantity: FBA可售库存，判断是否断货
   - category_2: 二级类目，用于分组计算类目均值
"""


# ============================================================
# 四、SQL 获取脚本
# ============================================================
SQL_SCRIPTS = {

"方案A: 从ADS宽表直接计算CTR/CVR类目均值": """
-- =========================================================
-- 方案A: 从 ads_lingxing_sc_sales_daily_new 直接计算
-- 优点: 无需JOIN，字段完整，含category_2
-- =========================================================

-- 1. CTR 类目均值 (按 category_2 分组)
SELECT
    category_2,
    SUM(clicks)                                     AS total_clicks,
    SUM(impressions)                                AS total_impressions,
    CASE WHEN SUM(impressions) > 0
         THEN ROUND(SUM(clicks) * 1.0 / SUM(impressions), 6)
         ELSE 0 END                                 AS avg_ctr
FROM ads_lingxing_sc_sales_daily_new
WHERE impressions > 0
  AND category_2 IS NOT NULL AND category_2 != ''
GROUP BY category_2
ORDER BY avg_ctr DESC;


-- 2. CVR 类目均值 (按 category_2 分组)
SELECT
    category_2,
    SUM(ad_order_quantity)                          AS total_ad_orders,
    SUM(clicks)                                     AS total_clicks,
    CASE WHEN SUM(clicks) > 0
         THEN ROUND(SUM(ad_order_quantity) * 1.0 / SUM(clicks), 6)
         ELSE 0 END                                 AS avg_cvr
FROM ads_lingxing_sc_sales_daily_new
WHERE clicks > 0
  AND category_2 IS NOT NULL AND category_2 != ''
GROUP BY category_2
ORDER BY avg_cvr DESC;


-- 3. CTR + CVR + ACOS 综合类目分析
SELECT
    category_2,
    COUNT(DISTINCT asin)                            AS asin_count,
    SUM(volume)                                     AS total_volume,
    SUM(amount)                                     AS total_sales_amount,
    SUM(clicks)                                     AS total_clicks,
    SUM(impressions)                                AS total_impressions,
    SUM(ad_order_quantity)                          AS total_ad_orders,
    SUM(spend)                                      AS total_ad_spend,
    SUM(ad_sales_amount)                            AS total_ad_sales,
    -- CTR
    CASE WHEN SUM(impressions) > 0
         THEN ROUND(SUM(clicks) * 1.0 / SUM(impressions), 6)
         ELSE 0 END                                 AS avg_ctr,
    -- CVR
    CASE WHEN SUM(clicks) > 0
         THEN ROUND(SUM(ad_order_quantity) * 1.0 / SUM(clicks), 6)
         ELSE 0 END                                 AS avg_cvr,
    -- ACOS
    CASE WHEN SUM(ad_sales_amount) > 0
         THEN ROUND(SUM(spend) * 1.0 / SUM(ad_sales_amount), 6)
         ELSE 0 END                                 AS avg_acos,
    -- CPC
    CASE WHEN SUM(clicks) > 0
         THEN ROUND(SUM(spend) * 1.0 / SUM(clicks), 4)
         ELSE 0 END                                 AS avg_cpc
FROM ads_lingxing_sc_sales_daily_new
WHERE category_2 IS NOT NULL AND category_2 != ''
GROUP BY category_2
ORDER BY total_sales_amount DESC;


-- 4. 按日期+类目的趋势分析
SELECT
    date,
    category_2,
    SUM(clicks)                                     AS daily_clicks,
    SUM(impressions)                                AS daily_impressions,
    SUM(ad_order_quantity)                          AS daily_ad_orders,
    CASE WHEN SUM(impressions) > 0
         THEN ROUND(SUM(clicks) * 1.0 / SUM(impressions), 6)
         ELSE 0 END                                 AS daily_ctr,
    CASE WHEN SUM(clicks) > 0
         THEN ROUND(SUM(ad_order_quantity) * 1.0 / SUM(clicks), 6)
         ELSE 0 END                                 AS daily_cvr
FROM ads_lingxing_sc_sales_daily_new
WHERE category_2 IS NOT NULL AND category_2 != ''
GROUP BY date, category_2
ORDER BY date DESC, category_2;
""",

"方案B: 从DWD明细表+维度表JOIN计算": """
-- =========================================================
-- 方案B: 从 dwd_lingxing_sc_product_performance_asin
--        JOIN dim_lingxing_product_info 获取 category_2
-- 优点: DWD表已有内置ctr/cvr/acos字段可交叉验证
-- =========================================================

-- 1. CTR 类目均值
SELECT
    d.category_2,
    SUM(p.clicks)                                   AS total_clicks,
    SUM(p.impressions)                              AS total_impressions,
    CASE WHEN SUM(p.impressions) > 0
         THEN ROUND(SUM(p.clicks) * 1.0 / SUM(p.impressions), 6)
         ELSE 0 END                                 AS calc_avg_ctr,
    AVG(p.ctr)                                      AS builtin_avg_ctr
FROM dwd_lingxing_sc_product_performance_asin p
JOIN dim_lingxing_product_info d
  ON p.asins_asin = d.asin
  AND p.sid = d.sid
WHERE p.impressions > 0
  AND d.category_2 IS NOT NULL AND d.category_2 != ''
GROUP BY d.category_2
ORDER BY calc_avg_ctr DESC;


-- 2. CVR 类目均值
SELECT
    d.category_2,
    SUM(p.ad_order_quantity)                        AS total_ad_orders,
    SUM(p.clicks)                                   AS total_clicks,
    CASE WHEN SUM(p.clicks) > 0
         THEN ROUND(SUM(p.ad_order_quantity) * 1.0 / SUM(p.clicks), 6)
         ELSE 0 END                                 AS calc_avg_cvr,
    AVG(p.cvr)                                      AS builtin_avg_cvr
FROM dwd_lingxing_sc_product_performance_asin p
JOIN dim_lingxing_product_info d
  ON p.asins_asin = d.asin
  AND p.sid = d.sid
WHERE p.clicks > 0
  AND d.category_2 IS NOT NULL AND d.category_2 != ''
GROUP BY d.category_2
ORDER BY calc_avg_cvr DESC;
""",

"ASIN级别明细查询": """
-- =========================================================
-- ASIN级别明细: 单品CTR/CVR及所属类目
-- =========================================================
SELECT
    a.date,
    a.asin,
    a.price_list_seller_sku AS msku,
    a.store_name,
    a.country_code,
    a.category_2,
    a.clicks,
    a.impressions,
    a.ad_order_quantity,
    a.spend,
    a.ad_sales_amount,
    a.volume,
    a.amount,
    -- CTR
    CASE WHEN a.impressions > 0
         THEN ROUND(a.clicks * 1.0 / a.impressions, 6)
         ELSE 0 END AS ctr,
    -- CVR
    CASE WHEN a.clicks > 0
         THEN ROUND(a.ad_order_quantity * 1.0 / a.clicks, 6)
         ELSE 0 END AS cvr,
    -- ACOS
    CASE WHEN a.ad_sales_amount > 0
         THEN ROUND(a.spend * 1.0 / a.ad_sales_amount, 6)
         ELSE 0 END AS acos
FROM ads_lingxing_sc_sales_daily_new a
WHERE a.impressions > 0
  AND a.category_2 IS NOT NULL AND a.category_2 != ''
ORDER BY a.date DESC, a.category_2, a.asin;
""",


# ------------------------------------------------------------------
# 产品具体分析: 三维筛选诊断
# ------------------------------------------------------------------
# 判断维度:
#   1. CTR < 类目均值 且 < 0.3%  -> 优化标题+主图
#   2. CVR < 类目均值 且 < 10%   -> 优化五点+A+
#   3. 近30天sessions_total持续下滑 >20% 且无断货 -> 必须优化
# ------------------------------------------------------------------

"产品诊断-Step1: 计算类目均值基准": """
-- =========================================================
-- Step1: 先算出各 category_2 的 CTR/CVR 均值基准线
-- 建议取最近30天数据作为基准
-- =========================================================
WITH category_benchmark AS (
    SELECT
        category_2,
        CASE WHEN SUM(impressions) > 0
             THEN SUM(clicks) * 1.0 / SUM(impressions)
             ELSE 0 END AS cat_avg_ctr,
        CASE WHEN SUM(clicks) > 0
             THEN SUM(ad_order_quantity) * 1.0 / SUM(clicks)
             ELSE 0 END AS cat_avg_cvr
    FROM ads_lingxing_sc_sales_daily_new
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      AND category_2 IS NOT NULL AND category_2 != ''
    GROUP BY category_2
)
SELECT * FROM category_benchmark
ORDER BY cat_avg_ctr DESC;
""",

"产品诊断-Step2: CTR低于类目均值筛选(优化标题+主图)": """
-- =========================================================
-- 筛选条件: CTR < 类目均值 且 CTR < 0.3%
-- 优化建议: 优化标题 + 主图
-- =========================================================
WITH category_benchmark AS (
    SELECT
        category_2,
        CASE WHEN SUM(impressions) > 0
             THEN SUM(clicks) * 1.0 / SUM(impressions)
             ELSE 0 END AS cat_avg_ctr
    FROM ads_lingxing_sc_sales_daily_new
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      AND category_2 IS NOT NULL AND category_2 != ''
    GROUP BY category_2
),
product_ctr AS (
    SELECT
        a.asin,
        a.price_list_seller_sku AS msku,
        a.spu,
        a.store_name,
        a.country_code,
        a.category_2,
        SUM(a.clicks)       AS total_clicks,
        SUM(a.impressions)  AS total_impressions,
        CASE WHEN SUM(a.impressions) > 0
             THEN SUM(a.clicks) * 1.0 / SUM(a.impressions)
             ELSE 0 END     AS product_ctr
    FROM ads_lingxing_sc_sales_daily_new a
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      AND a.category_2 IS NOT NULL AND a.category_2 != ''
      AND a.impressions > 0
      AND a.clicks > 0
    GROUP BY a.asin, a.price_list_seller_sku, a.spu,
             a.store_name, a.country_code, a.category_2
)
SELECT
    p.asin,
    p.msku,
    p.spu,
    p.store_name,
    p.country_code,
    p.category_2,
    p.total_clicks,
    p.total_impressions,
    ROUND(p.product_ctr * 100, 4)   AS product_ctr_pct,
    ROUND(b.cat_avg_ctr * 100, 4)   AS category_avg_ctr_pct,
    ROUND((p.product_ctr - b.cat_avg_ctr) * 100, 4) AS ctr_gap_pct,
    '优化标题+主图' AS optimization_action
FROM product_ctr p
JOIN category_benchmark b ON p.category_2 = b.category_2
WHERE p.product_ctr < b.cat_avg_ctr
  AND p.product_ctr < 0.003
ORDER BY p.product_ctr ASC, p.total_impressions DESC;
""",

"产品诊断-Step3: CVR低于类目均值筛选(优化五点+A+)": """
-- =========================================================
-- 筛选条件: CVR < 类目均值 且 CVR < 10%
-- 优化建议: 优化五点描述 + A+页面
-- =========================================================
WITH category_benchmark AS (
    SELECT
        category_2,
        CASE WHEN SUM(clicks) > 0
             THEN SUM(ad_order_quantity) * 1.0 / SUM(clicks)
             ELSE 0 END AS cat_avg_cvr
    FROM ads_lingxing_sc_sales_daily_new
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      AND category_2 IS NOT NULL AND category_2 != ''
    GROUP BY category_2
),
product_cvr AS (
    SELECT
        a.asin,
        a.price_list_seller_sku AS msku,
        a.spu,
        a.store_name,
        a.country_code,
        a.category_2,
        SUM(a.ad_order_quantity) AS total_ad_orders,
        SUM(a.clicks)            AS total_clicks,
        CASE WHEN SUM(a.clicks) > 0
             THEN SUM(a.ad_order_quantity) * 1.0 / SUM(a.clicks)
             ELSE 0 END          AS product_cvr
    FROM ads_lingxing_sc_sales_daily_new a
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      AND a.category_2 IS NOT NULL AND a.category_2 != ''
      AND a.impressions > 0
      AND a.clicks > 0
    GROUP BY a.asin, a.price_list_seller_sku, a.spu,
             a.store_name, a.country_code, a.category_2
)
SELECT
    p.asin,
    p.msku,
    p.spu,
    p.store_name,
    p.country_code,
    p.category_2,
    p.total_ad_orders,
    p.total_clicks,
    ROUND(p.product_cvr * 100, 4)    AS product_cvr_pct,
    ROUND(b.cat_avg_cvr * 100, 4)    AS category_avg_cvr_pct,
    ROUND((p.product_cvr - b.cat_avg_cvr) * 100, 4) AS cvr_gap_pct,
    '优化五点+A+' AS optimization_action
FROM product_cvr p
JOIN category_benchmark b ON p.category_2 = b.category_2
WHERE p.product_cvr < b.cat_avg_cvr
  AND p.product_cvr < 0.10
ORDER BY p.product_cvr ASC, p.total_clicks DESC;
""",

"产品诊断-Step4: 近30天自然流量持续下滑筛选(必须优化)": """
-- =========================================================
-- 筛选条件: 近30天 sessions_total 下滑超20% 且无断货(afn_fulfillable_quantity>0)
-- 优化建议: 必须优化
-- 说明: sessions_total 代表总流量(含自然+广告)，作为排名变化的代理指标
--       afn_fulfillable_quantity > 0 表示有库存未断货
-- =========================================================
WITH recent_period AS (
    SELECT
        asin,
        price_list_seller_sku AS msku,
        spu,
        store_name,
        country_code,
        category_2,
        SUM(sessions_total)              AS recent_sessions,
        SUM(volume)                      AS recent_volume,
        AVG(afn_fulfillable_quantity)    AS avg_stock
    FROM ads_lingxing_sc_sales_daily_new
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 15 DAY)
      AND date < CURRENT_DATE()
      AND category_2 IS NOT NULL AND category_2 != ''
    GROUP BY asin, price_list_seller_sku, spu, store_name, country_code, category_2
),
earlier_period AS (
    SELECT
        asin,
        price_list_seller_sku AS msku,
        store_name,
        country_code,
        SUM(sessions_total) AS earlier_sessions,
        SUM(volume)         AS earlier_volume
    FROM ads_lingxing_sc_sales_daily_new
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 15 DAY)
    GROUP BY asin, price_list_seller_sku, store_name, country_code
)
SELECT
    r.asin,
    r.msku,
    r.spu,
    r.store_name,
    r.country_code,
    r.category_2,
    e.earlier_sessions,
    r.recent_sessions,
    ROUND((r.recent_sessions - e.earlier_sessions) * 100.0
          / NULLIF(e.earlier_sessions, 0), 2)   AS sessions_change_pct,
    e.earlier_volume,
    r.recent_volume,
    ROUND(r.avg_stock, 0)                        AS avg_stock_qty,
    '必须优化' AS optimization_action
FROM recent_period r
JOIN earlier_period e
  ON r.asin = e.asin
  AND r.msku = e.msku
  AND r.store_name = e.store_name
  AND r.country_code = e.country_code
WHERE e.earlier_sessions > 0
  AND (r.recent_sessions - e.earlier_sessions) * 1.0 / e.earlier_sessions < -0.20
  AND r.avg_stock > 0
ORDER BY sessions_change_pct ASC;
""",

"产品诊断-综合: 三维一体化诊断报告": """
-- =========================================================
-- 综合诊断: 将CTR/CVR/流量下滑三个维度合并输出
-- 每个产品可能同时命中多个维度
-- =========================================================
WITH date_range AS (
    SELECT
        DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) AS start_30d,
        DATE_SUB(CURRENT_DATE(), INTERVAL 15 DAY) AS mid_15d,
        CURRENT_DATE() AS today
),

-- 类目CTR/CVR基准
category_benchmark AS (
    SELECT
        category_2,
        CASE WHEN SUM(impressions) > 0
             THEN SUM(clicks) * 1.0 / SUM(impressions)
             ELSE 0 END AS cat_avg_ctr,
        CASE WHEN SUM(clicks) > 0
             THEN SUM(ad_order_quantity) * 1.0 / SUM(clicks)
             ELSE 0 END AS cat_avg_cvr
    FROM ads_lingxing_sc_sales_daily_new, date_range d
    WHERE date >= d.start_30d
      AND category_2 IS NOT NULL AND category_2 != ''
    GROUP BY category_2
),

-- 产品30天汇总
product_30d AS (
    SELECT
        a.asin,
        a.price_list_seller_sku AS msku,
        a.spu,
        a.store_name,
        a.country_code,
        a.category_2,
        SUM(a.clicks)                AS total_clicks,
        SUM(a.impressions)           AS total_impressions,
        SUM(a.ad_order_quantity)     AS total_ad_orders,
        SUM(a.spend)                 AS total_spend,
        SUM(a.ad_sales_amount)       AS total_ad_sales,
        SUM(a.volume)                AS total_volume,
        SUM(a.amount)                AS total_amount,
        CASE WHEN SUM(a.impressions) > 0
             THEN SUM(a.clicks) * 1.0 / SUM(a.impressions)
             ELSE 0 END              AS product_ctr,
        CASE WHEN SUM(a.clicks) > 0
             THEN SUM(a.ad_order_quantity) * 1.0 / SUM(a.clicks)
             ELSE 0 END              AS product_cvr
    FROM ads_lingxing_sc_sales_daily_new a, date_range d
    WHERE a.date >= d.start_30d
      AND a.category_2 IS NOT NULL AND a.category_2 != ''
      AND a.impressions > 0
      AND a.clicks > 0
    GROUP BY a.asin, a.price_list_seller_sku, a.spu,
             a.store_name, a.country_code, a.category_2
),

-- 前15天 vs 后15天流量对比
sessions_earlier AS (
    SELECT asin, price_list_seller_sku AS msku, store_name, country_code,
           SUM(sessions_total) AS earlier_sessions
    FROM ads_lingxing_sc_sales_daily_new, date_range d
    WHERE date >= d.start_30d AND date < d.mid_15d
    GROUP BY asin, price_list_seller_sku, store_name, country_code
),
sessions_recent AS (
    SELECT asin, price_list_seller_sku AS msku, store_name, country_code,
           SUM(sessions_total) AS recent_sessions,
           AVG(afn_fulfillable_quantity) AS avg_stock
    FROM ads_lingxing_sc_sales_daily_new, date_range d
    WHERE date >= d.mid_15d AND date < d.today
    GROUP BY asin, price_list_seller_sku, store_name, country_code
)

SELECT
    p.asin,
    p.msku,
    p.spu,
    p.store_name,
    p.country_code,
    p.category_2,
    -- CTR诊断
    ROUND(p.product_ctr * 100, 4)         AS product_ctr_pct,
    ROUND(b.cat_avg_ctr * 100, 4)         AS cat_avg_ctr_pct,
    CASE WHEN p.product_ctr < b.cat_avg_ctr AND p.product_ctr < 0.003
         THEN 1 ELSE 0 END                AS flag_ctr_low,
    -- CVR诊断
    ROUND(p.product_cvr * 100, 4)         AS product_cvr_pct,
    ROUND(b.cat_avg_cvr * 100, 4)         AS cat_avg_cvr_pct,
    CASE WHEN p.product_cvr < b.cat_avg_cvr AND p.product_cvr < 0.10
         THEN 1 ELSE 0 END                AS flag_cvr_low,
    -- 流量下滑诊断
    se.earlier_sessions,
    sr.recent_sessions,
    ROUND((sr.recent_sessions - se.earlier_sessions) * 100.0
          / NULLIF(se.earlier_sessions, 0), 2) AS sessions_change_pct,
    ROUND(sr.avg_stock, 0)                 AS avg_stock_qty,
    CASE WHEN se.earlier_sessions > 0
          AND (sr.recent_sessions - se.earlier_sessions) * 1.0 / se.earlier_sessions < -0.20
          AND sr.avg_stock > 0
         THEN 1 ELSE 0 END                AS flag_sessions_decline,
    -- 综合优化建议
    CONCAT_WS(' | ',
        CASE WHEN p.product_ctr < b.cat_avg_ctr AND p.product_ctr < 0.003
             THEN '优化标题+主图' END,
        CASE WHEN p.product_cvr < b.cat_avg_cvr AND p.product_cvr < 0.10
             THEN '优化五点+A+' END,
        CASE WHEN se.earlier_sessions > 0
              AND (sr.recent_sessions - se.earlier_sessions) * 1.0 / se.earlier_sessions < -0.20
              AND sr.avg_stock > 0
             THEN '必须优化(排名下滑)' END
    ) AS optimization_actions,
    -- 命中维度数
    (CASE WHEN p.product_ctr < b.cat_avg_ctr AND p.product_ctr < 0.003 THEN 1 ELSE 0 END)
  + (CASE WHEN p.product_cvr < b.cat_avg_cvr AND p.product_cvr < 0.10 THEN 1 ELSE 0 END)
  + (CASE WHEN se.earlier_sessions > 0
          AND (sr.recent_sessions - se.earlier_sessions) * 1.0 / se.earlier_sessions < -0.20
          AND sr.avg_stock > 0 THEN 1 ELSE 0 END)
    AS hit_count
FROM product_30d p
JOIN category_benchmark b ON p.category_2 = b.category_2
LEFT JOIN sessions_earlier se
  ON p.asin = se.asin AND p.msku = se.msku
  AND p.store_name = se.store_name AND p.country_code = se.country_code
LEFT JOIN sessions_recent sr
  ON p.asin = sr.asin AND p.msku = sr.msku
  AND p.store_name = sr.store_name AND p.country_code = sr.country_code
WHERE
    (p.product_ctr < b.cat_avg_ctr AND p.product_ctr < 0.003)
    OR (p.product_cvr < b.cat_avg_cvr AND p.product_cvr < 0.10)
    OR (se.earlier_sessions > 0
        AND (sr.recent_sessions - se.earlier_sessions) * 1.0 / se.earlier_sessions < -0.20
        AND sr.avg_stock > 0)
ORDER BY hit_count DESC, p.total_amount DESC;
"""
}


# ============================================================
# 五、精简后的核心表Schema输出
# ============================================================
def print_core_schema():
    core_table_names = [
        'ads_lingxing_sc_sales_daily_new',
        'dwd_lingxing_sc_product_performance_asin',
        'dim_lingxing_product_info',
    ]
    
    print("\n" + "=" * 80)
    print("精简后的核心表Schema（仅保留CTR/CVR相关字段）")
    print("=" * 80)
    
    core_fields_map = {
        'ads_lingxing_sc_sales_daily_new': [
            'date', 'sid', 'store_name', 'asin', 'price_list_seller_sku',
            'spu', 'country_code', 'volume', 'amount', 'clicks',
            'impressions', 'ad_order_quantity', 'spend', 'ad_sales_amount',
            'category_1', 'category_2', 'category_3'
        ],
        'dwd_lingxing_sc_product_performance_asin': [
            'date', 'sid', 'asins_asin', 'price_list_seller_sku',
            'volume', 'amount', 'clicks', 'impressions',
            'ad_order_quantity', 'spend', 'ad_sales_amount',
            'ctr', 'cvr', 'acos'
        ],
        'dim_lingxing_product_info': [
            'sid', 'asin', 'store_name', 'country_code',
            'spu', 'category_2', 'price_list_seller_sku'
        ]
    }
    
    tables_dict = index.get('tables', {})
    
    for tname in core_table_names:
        tinfo = tables_dict.get(tname, {})
        desc = tinfo.get('description_cn', '')
        columns = tinfo.get('columns', [])
        layer = tinfo.get('layer', '')
        
        print(f"\n--- {tname} ---")
        print(f"  描述: {desc}")
        print(f"  层级: {layer}")
        print(f"  核心字段:")
        
        wanted = core_fields_map.get(tname, [])
        for c in columns:
            if isinstance(c, dict) and c.get('name') in wanted:
                desc_cn = c.get('description_cn', c.get('comment', ''))
                print(f"    {c['name']:<35} {c.get('type', ''):<25} {desc_cn}")


# ============================================================
# 输出报告
# ============================================================
if __name__ == '__main__':
    print(FORMULAS)
    
    print_core_schema()
    
    print("\n" + "=" * 80)
    print("可清理的重复/无效表")
    print("=" * 80)
    redundant = get_redundant_tables()
    total_removable = 0
    for category, tables in redundant.items():
        print(f"\n  [{category}] ({len(tables)}张)")
        for t in tables:
            print(f"    - {t}")
        total_removable += len(tables)
    print(f"\n  总计可精简: {total_removable} 张 / {len(raw)} 张")
    
    print("\n" + "=" * 80)
    print("SQL 获取脚本")
    print("=" * 80)
    for name, sql in SQL_SCRIPTS.items():
        print(f"\n{'=' * 60}")
        print(f" {name}")
        print(f"{'=' * 60}")
        print(sql)
