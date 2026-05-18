
--  120天序列
DROP TABLE IF EXISTS temp_date_series;
CREATE TABLE temp_date_series AS
SELECT
    CURRENT_DATE() + INTERVAL (n.number) DAY AS forecast_date,
    n.number AS day_num
FROM (
    select * from numbers('number' = '180')
) n
WHERE n.number <= 180;


-- fnsku+store 获取所有需要预测的SKU和店铺组合
DROP TABLE IF EXISTS temp_sku_store_combinations;
CREATE TABLE temp_sku_store_combinations AS
SELECT DISTINCT FNSKU, store_name
FROM (
    SELECT t1.FNSKU, t1.store_name
    FROM dim_lingxing_lot_tracking_new t1
    WHERE t1.estimated_shelf_life > CURDATE()
      AND NULLIF(TRIM(t1.FNSKU), '') IS NOT NULL  -- 过滤空和空白FNSKU

    UNION

    SELECT FNSKU, store_name
    FROM dim_lingxing_sales_estimates
    WHERE NULLIF(TRIM(FNSKU), '') IS NOT NULL

    UNION

    SELECT FNSKU, store_name
    FROM temp_kucun_fnsku_zgb
    WHERE NULLIF(TRIM(FNSKU), '') IS NOT NULL
) AS combined
WHERE NULLIF(TRIM(FNSKU), '') IS NOT NULL;


-- 计算每个批次的上架日期
DROP TABLE IF EXISTS temp_pici_type;
CREATE TABLE temp_pici_type AS
SELECT *
FROM (
    SELECT
        t1.FNSKU,
        t1.store_name,
        t1.quantity_receive AS ship_num,
        CASE
            WHEN t1.type = '本地仓' THEN DATE_ADD(t1.estimated_shelf_life, INTERVAL (COALESCE(t2.local_warehouse_pick_time, 0) + COALESCE(t2.local_to_fba_time, 0)) DAY)
            WHEN t1.type = '海外仓' THEN DATE_ADD(t1.estimated_shelf_life, INTERVAL (COALESCE(t2.overseas_warehouse_pick_time, 0) + COALESCE(t2.overseas_to_fba_time, 0)) DAY)
            ELSE t1.estimated_shelf_life
        END AS put_date
    FROM dim_lingxing_lot_tracking_new t1
    LEFT JOIN dim_lingxing_stocking_rules t2
        ON t1.fnsku = t2.fnsku
        AND t1.store_name = t2.store_name
    WHERE t1.estimated_shelf_life > CURDATE()
) AS calculated
WHERE put_date >= CURRENT_DATE();



-- 计算每天每个FSKU的预计到货量
DROP TABLE IF EXISTS temp_daily_arrivals;
CREATE TABLE temp_daily_arrivals AS
SELECT
    ds.forecast_date,
    ssc.FNSKU,
    ssc.store_name,
    COALESCE(SUM(CASE WHEN pt.put_date = ds.forecast_date THEN pt.ship_num ELSE 0 END), 0) AS expected_arrival
FROM temp_date_series ds
CROSS JOIN temp_sku_store_combinations ssc
LEFT JOIN temp_pici_type pt
    ON ssc.FNSKU = pt.FNSKU
    AND ssc.store_name = pt.store_name
    AND pt.put_date = ds.forecast_date
GROUP BY ds.forecast_date, ssc.FNSKU, ssc.store_name;



-- 二次处理
DROP TABLE IF EXISTS temp_daily_arrivals2;
CREATE TABLE temp_daily_arrivals2
  AS
SELECT
    T1.forecast_date,
    T1.FNSKU,
    T1.store_name,
   CASE WHEN T2.basic_purchase_quantity IS NULL THEN  T1.expected_arrival
    ELSE T2.basic_purchase_quantity + T1.expected_arrival
    END AS expected_arrival
FROM temp_daily_arrivals T1
LEFT JOIN temp_purchase_quantity_temp_v1 T2
    ON T1.FNSKU = T2.FNSKU
    AND T1.store_name = T2.store_name
    AND T1.forecast_date = T2.start_dates;



-- 计算每天的预计销量
DROP TABLE IF EXISTS temp_daily_sales;
CREATE TABLE temp_daily_sales AS
SELECT
    ds.forecast_date,
    ssc.FNSKU,
    ssc.store_name,
    COALESCE(se.daily_sales_quantity, 0) AS expected_sales
FROM temp_date_series ds
CROSS JOIN temp_sku_store_combinations ssc
LEFT JOIN dim_lingxing_sales_estimates_everyday_incr se
    ON ds.forecast_date = se.date
    AND ssc.FNSKU = se.FNSKU
    AND ssc.store_name = se.store_name;


-- 获取当前库存
DROP TABLE IF EXISTS temp_current_inventory;
CREATE TABLE temp_current_inventory AS
SELECT
    ssc.FNSKU,
    ssc.store_name,
    COALESCE(w.fnsku_inventory_1, 0) AS current_inventory
FROM temp_sku_store_combinations ssc
LEFT JOIN temp_kucun_fnsku_zgb w
    ON ssc.FNSKU = w.FNSKU
    AND ssc.store_name = w.store_name;


-- 合并所有基础数据
DROP TABLE IF EXISTS temp_base_data;
CREATE TABLE temp_base_data AS
SELECT
    ds.forecast_date,
    ds.day_num,
    ssc.FNSKU,
    ssc.store_name,
    COALESCE(da.expected_arrival, 0) AS expected_arrival,
    COALESCE(sales.expected_sales, 0) AS expected_sales,
    COALESCE(ci.current_inventory, 0) AS starting_inventory
FROM temp_date_series ds
CROSS JOIN temp_sku_store_combinations ssc
LEFT JOIN temp_daily_arrivals2 da
    ON ds.forecast_date = da.forecast_date
    AND ssc.FNSKU = da.FNSKU
    AND ssc.store_name = da.store_name
LEFT JOIN temp_daily_sales sales
    ON ds.forecast_date = sales.forecast_date
    AND ssc.FNSKU = sales.FNSKU
    AND ssc.store_name = sales.store_name
LEFT JOIN temp_current_inventory ci
    ON ssc.FNSKU = ci.FNSKU
    AND ssc.store_name = ci.store_name;


-- 计算库存预测
DROP TABLE IF EXISTS dim_inventory_forecast;
CREATE TABLE dim_inventory_forecast AS
WITH base_data AS (
    SELECT
        forecast_date,
        FNSKU,
        store_name,
        expected_arrival,
        expected_sales,
        starting_inventory
    FROM temp_base_data
    WHERE
        NULLIF(TRIM(FNSKU), '') IS NOT NULL
        AND NULLIF(TRIM(store_name), '') IS NOT NULL
        AND starting_inventory IS NOT NULL
),
theoretical_calc AS (
    SELECT
        *,
        starting_inventory +
        SUM(expected_arrival - expected_sales) OVER (
            PARTITION BY FNSKU, store_name
            ORDER BY forecast_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS theoretical_ending
    FROM base_data
),
min_cumulative AS (
    SELECT
        *,
        MIN(theoretical_ending) OVER (
            PARTITION BY FNSKU, store_name
            ORDER BY forecast_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS min_ending
    FROM theoretical_calc
),
reset_inventory AS (
    SELECT
        *,
        theoretical_ending - LEAST(min_ending, 0) AS ending_inventory
    FROM min_cumulative
)
SELECT
    forecast_date,
    FNSKU,
    store_name,
    expected_arrival,
    expected_sales,
    COALESCE(
        LAG(ending_inventory) OVER (
            PARTITION BY FNSKU, store_name
            ORDER BY forecast_date
        ),
        starting_inventory
    ) AS starting_inventory,
    ending_inventory
FROM reset_inventory;


-- 计算库存预警
DROP TABLE IF EXISTS dim_inventory_forecast2;
CREATE TABLE dim_inventory_forecast2 AS
SELECT
  t1.forecast_date,
  t1.FNSKU,
  t1.store_name,
  t1.expected_arrival,
  t1.expected_sales,
  t1.starting_inventory,
  t1.ending_inventory,
  COALESCE(t2.alert_level, 0) as yujing,
  t2.start_date,
  t2.end_date,
  t2.consecutive_days
FROM
  dim_inventory_forecast t1
LEFT JOIN (
  SELECT
    FNSKU,
    store_name,
    start_date,
    end_date,
    consecutive_days,
    CASE
      WHEN consecutive_days >= 14 THEN 2
      WHEN consecutive_days >= 7 THEN 1
      ELSE 0
    END as alert_level
  FROM (
    SELECT
      FNSKU,
      store_name,
      MIN(forecast_date) as start_date,
      MAX(forecast_date) as end_date,
      COUNT(*) as consecutive_days
    FROM (
      SELECT
        FNSKU,
        store_name,
        forecast_date,
        ending_inventory,
        date_sub(forecast_date, row_number() OVER (
          PARTITION BY FNSKU, store_name
          ORDER BY forecast_date
        )) as group_marker
      FROM dim_inventory_forecast
      WHERE ending_inventory = 0
    ) t
    GROUP BY FNSKU, store_name, group_marker
    HAVING COUNT(*) >= 7
  ) sequences
) t2 ON t1.FNSKU = t2.FNSKU
  AND t1.store_name = t2.store_name
  AND t1.forecast_date >= t2.start_date
  AND t1.forecast_date <= t2.end_date