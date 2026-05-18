-- 可售天数计算
DROP TABLE IF EXISTS temp_lingxing_keshou_pici;
CREATE TABLE temp_lingxing_keshou_pici as
WITH forecast_cum AS (
    SELECT
        k.fnsku,
        k.store_name,
        k.put_date,
        k.jieyu_kucun AS 当前库存,
        s.date,
        k.type,
        SUM(s.daily_sales_quantity) OVER (
            PARTITION BY k.fnsku, k.store_name, k.put_date,k.type
            ORDER BY s.date
        ) AS 累计预估销量
    FROM temp_batch_kucun k
    JOIN dim_lingxing_sales_estimates s
        ON k.fnsku = s.fnsku
        AND k.store_name = s.store_name
        AND s.date >= k.put_date
),
耗尽日期 AS (
    SELECT
        f.fnsku,
        f.store_name,
        f.put_date,
        f.当前库存,
        MIN(f.date) AS 库存耗尽日期,
        f.type
    FROM forecast_cum f
    WHERE f.累计预估销量 >= f.当前库存
    GROUP BY f.fnsku, f.store_name, f.put_date, f.当前库存,f.type
),
最大累计 AS (
    SELECT
        f.fnsku,
        f.store_name,
        f.put_date,
        MAX(f.累计预估销量) AS 最大累计销量
    FROM forecast_cum f
    GROUP BY f.fnsku, f.store_name, f.put_date
),
合并结果 AS (
    SELECT
        k.fnsku,
        k.store_name,
        k.put_date,
        k.put_num,
        k.jieyu_kucun,
        d.库存耗尽日期 ens_date,
        CASE
            WHEN d.库存耗尽日期 IS NOT NULL THEN DATEDIFF(d.库存耗尽日期, k.put_date)
            WHEN m.最大累计销量 < k.jieyu_kucun THEN 9999
            ELSE NULL
        END AS pici_available_days,
        k.type
    FROM temp_batch_kucun k
    LEFT JOIN 耗尽日期 d
        ON k.fnsku = d.fnsku
        AND k.store_name = d.store_name
        AND k.put_date = d.put_date
        and k.type=d.type
    LEFT JOIN 最大累计 m
        ON k.fnsku = m.fnsku
        AND k.store_name = m.store_name
        AND k.put_date = m.put_date
)
SELECT *
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY fnsku, store_name, put_date,type ORDER BY pici_available_days DESC) AS rn
    FROM 合并结果
) t
WHERE rn = 1;


-- 补货倒计时
DROP TABLE IF EXISTS temp_pici_buhuo_zjg;
CREATE TABLE temp_pici_buhuo_zjg AS
with temp_countdown as (

    select t1.*,FBA_delivery_time_fn,fba_safety_days_fn,overseas_warehouse_delivery_time_fn,overseas_warehouse_safety_days,local_warehouse_delivery_time_fn,local_warehouse_safety_days,
       case
           when t1.pici_available_days=9999 then 9999
           when t1.type='FBA仓' then t1.pici_available_days-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn
           when t1.type='海外仓' then t1.pici_available_days-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn-t2.overseas_warehouse_safety_days-t2.overseas_warehouse_delivery_time_fn
           when t1.type='本地仓' then t1.pici_available_days-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn-t2.overseas_warehouse_safety_days-t2.overseas_warehouse_delivery_time_fn-t2.local_warehouse_safety_days-t2.local_warehouse_delivery_time_fn
        end as pici_fnsku_restocking_countdown

from temp_lingxing_keshou_pici t1 left join temp_lingxing_stocking_rules t2
on t1.fnsku=t2.fnsku
and t1.store_name=t2.store_name
)
select *,
       case
           when pici_available_days=9999 then 0
            when type='FBA仓' and pici_fnsku_restocking_countdown<=-fba_safety_days_fn then 4
            when type='FBA仓' and pici_fnsku_restocking_countdown<=-0.5*fba_safety_days_fn then 3
            when type='FBA仓' and pici_fnsku_restocking_countdown<=0 then 2
            when type='FBA仓' and pici_fnsku_restocking_countdown>0 then 1
           when type='海外仓' and pici_fnsku_restocking_countdown<=-(fba_safety_days_fn+overseas_warehouse_safety_days) then 4
            when type='海外仓' and pici_fnsku_restocking_countdown<=-(fba_safety_days_fn+overseas_warehouse_safety_days)*0.5 then 3
            when type='海外仓' and pici_fnsku_restocking_countdown<=0 then 2
            when type='海外仓' and pici_fnsku_restocking_countdown>0 then 1
           when type='本地仓' and pici_fnsku_restocking_countdown<=-(fba_safety_days_fn+overseas_warehouse_safety_days+local_warehouse_safety_days) then 4
            when type='本地仓' and pici_fnsku_restocking_countdown<=-(fba_safety_days_fn+overseas_warehouse_safety_days+local_warehouse_safety_days)*0.5 then 3
            when type='本地仓' and pici_fnsku_restocking_countdown<=0 then 2
            when type='本地仓' and pici_fnsku_restocking_countdown>0 then 1
            end as pici_fnsku_out_of_stock_risk

from temp_countdown;

DROP TABLE IF EXISTS ads_lingxing_all_warehouse_new;
CREATE TABLE ads_lingxing_all_warehouse_new AS
with temp_a as (select *,DATE_FORMAT(DATE_SUB(put_date, INTERVAL 1 DAY), '%Y-%m-%d') AS last_date
from temp_pici_buhuo_zjg
),
temp_b as (
    select t1.*,
           case when t1.jieyu_kucun-t1.put_num>0 then t1.jieyu_kucun-t1.put_num +t2.daily_sales_quantity
               else t1.jieyu_kucun-t1.put_num end
        as last_kucun,t1.jieyu_kucun-t1.put_num-daily_sales_quantity+total maxTotal1,t2.total
    from temp_a t1 inner join temp_lingxing_fnsku_sales t2 on t1.fnsku=t2.fnsku and t1.store_name=t2.store_name and t1.last_date=t2.date
    ),
temp_pici_buhuo_zjg2 as (
select ranked_forecasts.*,
        CASE
            when forecast_date is not null then TO_DAYS(forecast_date) - TO_DAYS(last_date)-1
        END AS last_available_days,
    case when  TO_DAYS(forecast_date) - TO_DAYS(last_date)-1<=0 then 4
        when TO_DAYS(forecast_date) - TO_DAYS(last_date)-1<fba_safety_days_fn/2 then 3
        when TO_DAYS(forecast_date) - TO_DAYS(last_date)-1<=fba_safety_days_fn then 2
        else 1 end as last_pici_fnsku_out_of_stock_risk
from (select i.*,
            sf.DATE AS forecast_date,
            ROW_NUMBER() OVER (PARTITION BY i.fnsku,i.store_name,i.type,last_date ORDER BY sf.DATE) AS sale_rn
      from temp_b i left join temp_lingxing_fnsku_sales sf
            ON sf.FNSKU = i.fnsku
            and lower(sf.store_name)=lower(i.store_name)
            AND sf.total > i.maxTotal1) AS ranked_forecasts
    WHERE sale_rn = 1 and type='FBA仓'
union all
select ranked_forecasts.*,
        CASE
            when forecast_date is not null then TO_DAYS(forecast_date) - TO_DAYS(last_date)-1
        END AS last_available_days,
    case when  TO_DAYS(forecast_date) - TO_DAYS(last_date)-1<=0 then 4
        when TO_DAYS(forecast_date) - TO_DAYS(last_date)-1<(fba_safety_days_fn+overseas_warehouse_safety_days)/2 then 3
        when TO_DAYS(forecast_date) - TO_DAYS(last_date)-1>=(fba_safety_days_fn+overseas_warehouse_safety_days)/2 then 2
        else 1 end as last_pici_fnsku_out_of_stock_risk
from (select i.*,
            sf.DATE AS forecast_date,
            ROW_NUMBER() OVER (PARTITION BY i.fnsku,i.store_name,i.type,last_date ORDER BY sf.DATE) AS sale_rn
      from temp_b i left join temp_lingxing_fnsku_sales sf
            ON sf.FNSKU = i.fnsku
            and lower(sf.store_name)=lower(i.store_name)
            AND sf.total > i.maxTotal1) AS ranked_forecasts
    WHERE sale_rn = 1 and type='海外仓'
union all
select ranked_forecasts.*,
        CASE
            when forecast_date is not null then TO_DAYS(forecast_date) - TO_DAYS(last_date)-1
        END AS last_available_days,
    case when  TO_DAYS(forecast_date) - TO_DAYS(last_date)-1<=0 then 4
        when TO_DAYS(forecast_date) - TO_DAYS(last_date)-1<(fba_safety_days_fn+overseas_warehouse_safety_days+local_warehouse_safety_days)/2 then 3
        when TO_DAYS(forecast_date) - TO_DAYS(last_date)-1>=(fba_safety_days_fn+overseas_warehouse_safety_days+local_warehouse_safety_days)/2 then 2
        else 1 end as last_pici_fnsku_out_of_stock_risk
from (select i.*,
            sf.DATE AS forecast_date,
            ROW_NUMBER() OVER (PARTITION BY i.fnsku,i.store_name,i.type,last_date ORDER BY sf.DATE) AS sale_rn
      from temp_b i left join temp_lingxing_fnsku_sales sf
            ON sf.FNSKU = i.fnsku
            and lower(sf.store_name)=lower(i.store_name)
            AND sf.total > i.maxTotal1) AS ranked_forecasts
    WHERE sale_rn = 1 and type='本地仓'),

temp_pici_duanhuo_raw AS (
    SELECT
        fnsku,
        store_name,
        type,
        CASE
            when last_kucun<0 then '严重'
            WHEN last_pici_fnsku_out_of_stock_risk = 4 THEN '严重'
            WHEN last_pici_fnsku_out_of_stock_risk = 3 THEN '中等'
            WHEN last_pici_fnsku_out_of_stock_risk = 2 THEN '轻微'
            WHEN last_pici_fnsku_out_of_stock_risk = 1 OR last_pici_fnsku_out_of_stock_risk = 0 THEN '安全'
            ELSE NULL
        END AS pici_fnsku_out_of_stock_risk_str
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY fnsku, store_name, type
                   ORDER BY last_pici_fnsku_out_of_stock_risk DESC
               ) AS row_num
        FROM temp_pici_buhuo_zjg2
    ) t
    WHERE row_num = 1
),
fba_risk AS (
    SELECT fnsku, store_name, pici_fnsku_out_of_stock_risk_str
    FROM temp_pici_duanhuo_raw
    WHERE type = 'FBA仓'
),
overseas_risk AS (
    SELECT fnsku, store_name, pici_fnsku_out_of_stock_risk_str
    FROM temp_pici_duanhuo_raw
    WHERE type = '海外仓'
),
local_risk AS (
    SELECT fnsku, store_name, pici_fnsku_out_of_stock_risk_str
    FROM temp_pici_duanhuo_raw
    WHERE type = '本地仓'
)
SELECT
    t2.msku,
    t2.sku,
    t2.fnsku,
    t2.asin,
    t2.brand,
    t2.parent_asin,
    t2.store_name,
    t2.sales_apartment,
    t2.salesman,
    t2.product_manager,
    t2.country_code,
    t2.channel,
    t2.sku_name,
    t2.seller_id,
    t2.shipments_country,
    t2.region,
    t2.msku_sales_property,
    t2.msku_product_property,
    t2.msku_isattract,
    t2.seasonality,
    t2.msku_status,
    t2.msku_life_process,
    t2.colour,
    t2.color,
    t2.size,
    t1.last_30_order_price,
    t1.last_30_order_us_price,
    t1.logistics_model,
    t1.first_leg_logistics_channel,
    t1.order_duration,
    t1.production_duration,
    t1.local_warehouse_pick_time,
    t1.overseas_warehouse_pick_time,
    t1.local_to_FBA_time,
    t1.local_to_overseas_warehouse_time,
    t1.overseas_to_FBA_time,
    t1.max_over_sell_ratio,
    t1.safety_stock_sales,
    t1.safety_stock_days_sales,
    t1.logistics_safety_stock_days,
    t1.production_safety_stock_days,
    t1.fba_safety_days_fn,
    t1.overseas_warehouse_safety_days,
    t1.local_warehouse_safety_days,
    t1.FBA_delivery_time_fn,
    t1.overseas_warehouse_delivery_time_fn,
    t1.local_warehouse_delivery_time_fn,
    t1.afn_fulfillable_quantity,
    t1.reserved_fc_transfers,
    t1.reserved_fc_processing,
    t1.afn_inbound_receiving_quantity,
    t1.stock_up_num,
    t1.afn_inbound_working_quantity,
    t1.overseas_wh_product_qc_num,
    t1.overseas_wh_product_onway,
    t1.planned_quantity,
    t1.local_wh_product_qc_num,
    t1.local_wh_product_onway,
    t1.quantity_receive,
    t1.procurement_plan_quantity,
    t1.fba_warehouse_quantity,
    t1.overseas_warehouse_quantity,
    t1.oversease_afn_inbound_shipped_quantity,
    t1.local_warehouse_quantity,
    t1.local_afn_inbound_shipped_quantity,
    t1.fnsku_inventory_1,
    t1.fnsku_inventory_2,
    t1.fnsku_inventory_3,
    t1.fnsku_inventory_4,
    t1.fnsku_inventory_5,
    t1.fnsku_inventory_6,
    t1.shipment_quantity2,
    t1.fnsku_available_days_1,
    t1.fnsku_available_days_2,
    t1.fnsku_available_days_3,
    t1.fnsku_available_days_4,
    t1.fnsku_available_days_5,
    t1.fnsku_available_days_6,
    t1.fnsku_available_days_str_1,
    t1.fnsku_available_days_str_2,
    t1.fnsku_available_days_str_3,
    t1.fnsku_available_days_str_4,
    t1.fnsku_available_days_str_5,
    t1.fnsku_available_days_str_6,
    t1.fnsku_restocking_countdown_1,
    t1.fnsku_restocking_countdown_2,
    t1.fnsku_restocking_countdown_3,
    t1.fnsku_restocking_countdown_4,
    t1.fnsku_restocking_countdown_5,
    t1.fnsku_restocking_countdown_6,
    t1.fnsku_restocking_countdown_str_1,
    t1.fnsku_restocking_countdown_str_2,
    t1.fnsku_restocking_countdown_str_3,
    t1.fnsku_restocking_countdown_str_4,
    t1.fnsku_restocking_countdown_str_5,
    t1.fnsku_restocking_countdown_str_6,
    case
        when t1.fnsku_out_of_stock_risk_1 ='数据缺失' then '数据缺失'
        when fba_risk.pici_fnsku_out_of_stock_risk_str is null then t1.fnsku_out_of_stock_risk_1
        when t1.fnsku_out_of_stock_risk_2 in ('严重','中等','轻微') and fba_risk.pici_fnsku_out_of_stock_risk_str='安全' then fnsku_out_of_stock_risk_2
        when t1.fnsku_out_of_stock_risk_2 in ('严重') and fba_risk.pici_fnsku_out_of_stock_risk_str='中等' then fnsku_out_of_stock_risk_2
        when t1.fnsku_out_of_stock_risk_2 in ('严重','中等') and fba_risk.pici_fnsku_out_of_stock_risk_str='轻微' then fnsku_out_of_stock_risk_2
        else fba_risk.pici_fnsku_out_of_stock_risk_str
    end AS fnsku_out_of_stock_risk_1,
    t1.fnsku_out_of_stock_risk_2,
            case
        when t1.fnsku_out_of_stock_risk_3 ='数据缺失' then '数据缺失'
        when overseas_risk.pici_fnsku_out_of_stock_risk_str is null then t1.fnsku_out_of_stock_risk_3
        when t1.fnsku_out_of_stock_risk_4 in ('严重','中等','轻微') and overseas_risk.pici_fnsku_out_of_stock_risk_str='安全' then fnsku_out_of_stock_risk_4
        when t1.fnsku_out_of_stock_risk_4 in ('严重') and overseas_risk.pici_fnsku_out_of_stock_risk_str='中等' then fnsku_out_of_stock_risk_4
        when t1.fnsku_out_of_stock_risk_4 in ('严重','中等') and overseas_risk.pici_fnsku_out_of_stock_risk_str='轻微' then fnsku_out_of_stock_risk_4
        else overseas_risk.pici_fnsku_out_of_stock_risk_str
    end AS fnsku_out_of_stock_risk_3,
    t1.fnsku_out_of_stock_risk_4,
        case
        when t1.fnsku_out_of_stock_risk_5 ='数据缺失' then '数据缺失'
        when local_risk.pici_fnsku_out_of_stock_risk_str is null then t1.fnsku_out_of_stock_risk_5
        when t1.fnsku_out_of_stock_risk_6 in ('严重','中等','轻微') and local_risk.pici_fnsku_out_of_stock_risk_str='安全' then fnsku_out_of_stock_risk_6
        when t1.fnsku_out_of_stock_risk_6 in ('严重') and local_risk.pici_fnsku_out_of_stock_risk_str='中等' then fnsku_out_of_stock_risk_6
        when t1.fnsku_out_of_stock_risk_6 in ('严重','中等') and local_risk.pici_fnsku_out_of_stock_risk_str='轻微' then fnsku_out_of_stock_risk_6
        else local_risk.pici_fnsku_out_of_stock_risk_str
    end AS fnsku_out_of_stock_risk_5,
    t1.fnsku_out_of_stock_risk_6,
    t1.inv_age_0_to_30_days,
    t1.inv_age_31_to_60_days,
    t1.inv_age_61_to_90_days,
    t1.inv_age_91_to_180_days,
    t1.inv_age_181_to_270_days,
    t1.inv_age_271_to_330_days,
    t1.inv_age_331_to_365_days,
    t1.inv_age_365_plus_days,
    t1.sale_quantity_7,
    t1.sale_quantity_14,
    t1.sale_quantity_30,
    t1.sale_quantity_60,
    t1.sale_quantity_90,
    t1.last_year_sale_quantity_30,
    t1.last_year_sale_quantity_60,
    t1.last_year_sale_quantity_90,
    t1.last_90_gross_margin,
    t1.sale_fnsku_available_1,
    t1.sale_fnsku_available_2,
    t1.sale_fnsku_available_3,
    t1.sale_fnsku_available_4,
    t1.sale_fnsku_available_5,
    t1.sale_fnsku_available_6,
    t1.sale_fnsku_available_str_1,
    t1.sale_fnsku_available_str_2,
    t1.sale_fnsku_available_str_3,
    t1.sale_fnsku_available_str_4,
    t1.sale_fnsku_available_str_5,
    t1.sale_fnsku_available_str_6,
    t1.sale_fnsku_restocking_countdown_1,
    t1.sale_fnsku_restocking_countdown_2,
    t1.sale_fnsku_restocking_countdown_3,
    t1.sale_fnsku_restocking_countdown_4,
    t1.sale_fnsku_restocking_countdown_5,
    t1.sale_fnsku_restocking_countdown_6,
    t1.sale_fnsku_restocking_countdown_str_1,
    t1.sale_fnsku_restocking_countdown_str_2,
    t1.sale_fnsku_restocking_countdown_str_3,
    t1.sale_fnsku_restocking_countdown_str_4,
    t1.sale_fnsku_restocking_countdown_str_5,
    t1.sale_fnsku_restocking_countdown_str_6,
    t1.sale_fnsku_out_of_stock_risk_1,
    t1.sale_fnsku_out_of_stock_risk_2,
    t1.sale_fnsku_out_of_stock_risk_3,
    t1.sale_fnsku_out_of_stock_risk_4,
    t1.sale_fnsku_out_of_stock_risk_5,
    t1.sale_fnsku_out_of_stock_risk_6,
    t1.future_15d_sales,
    t1.future_30d_sales,
    t1.future_45d_sales,
    t1.future_60d_sales,
    t1.future_75d_sales,
    t1.future_90d_sales
FROM dim_lingxing_product_info t2
INNER JOIN temp_select_fnsku_zjg t1
    ON t1.fnsku = t2.fnsku
   AND t1.msku = t2.msku
   AND LOWER(t1.store_name) = LOWER(t2.store_name)
LEFT JOIN fba_risk
    ON t1.fnsku = fba_risk.fnsku
   AND LOWER(t1.store_name) = LOWER(fba_risk.store_name)
LEFT JOIN overseas_risk
    ON t1.fnsku = overseas_risk.fnsku
   AND LOWER(t1.store_name) = LOWER(overseas_risk.store_name)
LEFT JOIN local_risk
    ON t1.fnsku = local_risk.fnsku
   AND LOWER(t1.store_name) = LOWER(local_risk.store_name);


--  虚拟到货批次

DROP TABLE IF EXISTS temp_lingxing_pici_sale;

CREATE TABLE temp_lingxing_pici_sale as
WITH
temp_ware AS (
SELECT
    DISTINCT
    t1.FNSKU,
    t1.store_name,
    fnsku_inventory_1,
    t1.overseas_warehouse_quantity AS ship_num,
    DATE_ADD(CURDATE(), INTERVAL t1.overseas_to_FBA_time+t1.order_duration+overseas_warehouse_pick_time DAY) AS put_date,
    logistics_model
FROM
    ads_lingxing_all_warehouse_new t1
WHERE
    t1.logistics_model IS NOT NULL
    AND t1.overseas_to_FBA_time IS NOT NULL
    AND t1.overseas_warehouse_quantity IS NOT NULL

UNION ALL

SELECT
    DISTINCT
    t1.FNSKU,
    t1.store_name,
    fnsku_inventory_1,
    t1.local_warehouse_quantity AS ship_num,
    case when logistics_model='本地仓中转' then DATE_ADD(CURDATE(), INTERVAL t1.local_to_FBA_time+t1.order_duration+local_warehouse_pick_time DAY)
        when logistics_model='本地仓&海外仓中转' then DATE_ADD(CURDATE(), INTERVAL t1.order_duration+local_warehouse_pick_time+t1.local_to_overseas_warehouse_time+overseas_warehouse_pick_time+overseas_to_FBA_time DAY)
        end AS put_date,
    logistics_model
FROM
    ads_lingxing_all_warehouse_new t1
WHERE
    t1.logistics_model IS NOT NULL
    AND t1.local_to_FBA_time IS NOT NULL
    AND t1.local_warehouse_pick_time IS NOT NULL
),

qujian_pici as (
SELECT
    FNSKU,
    store_name,
    fnsku_inventory_1,
    -- 统计不同时间段的到货量
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 6 THEN ship_num ELSE 0 END),0) AS ship_0_7,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 13 THEN ship_num ELSE 0 END),0) AS ship_0_14,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 20 THEN ship_num ELSE 0 END),0) AS ship_0_21,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 27 THEN ship_num ELSE 0 END),0) AS ship_0_28,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 34 THEN ship_num ELSE 0 END),0) AS ship_0_35,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 41 THEN ship_num ELSE 0 END),0) AS ship_0_42,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 48 THEN ship_num ELSE 0 END),0) AS ship_0_49,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 55 THEN ship_num ELSE 0 END),0) AS ship_0_56,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 62 THEN ship_num ELSE 0 END),0) AS ship_0_63,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 69 THEN ship_num ELSE 0 END),0) AS ship_0_70,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 76 THEN ship_num ELSE 0 END),0) AS ship_0_77,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 83 THEN ship_num ELSE 0 END),0) AS ship_0_84,
    ROUND(SUM(CASE WHEN DATEDIFF(put_date, CURRENT_DATE()) BETWEEN 0 AND 98 THEN ship_num ELSE 0 END),0) AS ship_0_98
FROM temp_ware
GROUP BY
    FNSKU,
    store_name,
    fnsku_inventory_1
ORDER BY
    FNSKU,
    store_name,
    fnsku_inventory_1
),
shiji_batch as (
select
    t.FNSKU,
    t.店铺 store_name,
    -- 统计不同时间段的到货量
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 6 THEN 待到货量 ELSE 0 END),0) AS ship_0_7,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 13 THEN 待到货量 ELSE 0 END),0) AS ship_0_14,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 20 THEN 待到货量 ELSE 0 END),0) AS ship_0_21,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 27 THEN 待到货量 ELSE 0 END),0) AS ship_0_28,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 34 THEN 待到货量 ELSE 0 END),0) AS ship_0_35,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 41 THEN 待到货量 ELSE 0 END),0) AS ship_0_42,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 48 THEN 待到货量 ELSE 0 END),0) AS ship_0_49,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 55 THEN 待到货量 ELSE 0 END),0) AS ship_0_56,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 62 THEN 待到货量 ELSE 0 END),0) AS ship_0_63,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 69 THEN 待到货量 ELSE 0 END),0) AS ship_0_70,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 76 THEN 待到货量 ELSE 0 END),0) AS ship_0_77,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 83 THEN 待到货量 ELSE 0 END),0) AS ship_0_84,
    ROUND(SUM(CASE WHEN DATEDIFF(预估上架（入库）时间, CURRENT_DATE()) BETWEEN 0 AND 97 THEN 待到货量 ELSE 0 END),0) AS ship_0_98
FROM (select t1.FNSKU,t1.店铺,ifnull(t1.待到货量,0) 待到货量,
             case when t1.到货仓类型 ='FBA仓' then t1.预估上架（入库）时间
                  when t1.到货仓类型='海外仓' then DATE_ADD(t1.预估上架（入库）时间, INTERVAL t2.overseas_to_fba_time+t2.overseas_warehouse_pick_time+t2.order_duration DAY)
                  when t1.到货仓类型='本地仓' and t2.logistics_model='本地仓中转' then DATE_ADD(t1.预估上架（入库）时间, INTERVAL t2.local_to_fba_time+t2.local_warehouse_pick_time+t2.order_duration DAY)
                 when t1.到货仓类型='本地仓' and t2.logistics_model='本地仓&海外仓中转' then DATE_ADD(t1.预估上架（入库）时间, INTERVAL t2.local_warehouse_pick_time+t2.order_duration+t2.local_to_overseas_warehouse_time+t2.overseas_warehouse_pick_time+t2.overseas_to_fba_time DAY)

      end as 预估上架（入库）时间
      from (select FNSKU,
                   store_name 店铺,
                   case when type='FBA仓' then quantity_receive else 0
                   end as 待到货量,
                   type 到货仓类型,
            estimated_shelf_life as 预估上架（入库）时间 from dim_lingxing_lot_tracking_new) t1 left join dim_lingxing_stocking_rules t2
          on t1.FNSKU=t2.FNSKU and t1.店铺=t2.store_name where 预估上架（入库）时间>=CURRENT_DATE()) t
GROUP BY
    t.FNSKU,
    t.店铺
ORDER BY
    t.FNSKU,
    t.店铺
),

qujian_pici2 as (
    select t1.fnsku,t1.store_name, fnsku_inventory_1,
           t1.ship_0_7+ifnull(t2.ship_0_7,0) as ship_0_7,
           t1.ship_0_14+ifnull(t2.ship_0_14,0) as ship_0_14,
           t1.ship_0_21+ifnull(t2.ship_0_21,0) as ship_0_21,
           t1.ship_0_28+ifnull(t2.ship_0_28,0) as ship_0_28,
           t1.ship_0_35+ifnull(t2.ship_0_35,0) as ship_0_35,
           t1.ship_0_42+ifnull(t2.ship_0_42,0) as ship_0_42,
           t1.ship_0_49+ifnull(t2.ship_0_49,0) as ship_0_49,
           t1.ship_0_56+ifnull(t2.ship_0_56,0) as ship_0_56,
           t1.ship_0_63+ifnull(t2.ship_0_63,0) as ship_0_63,
           t1.ship_0_70+ifnull(t2.ship_0_70,0) as ship_0_70,
           t1.ship_0_77+ifnull(t2.ship_0_77,0) as ship_0_77,
           t1.ship_0_84+ifnull(t2.ship_0_84,0) as ship_0_84,
           t1.ship_0_98+ifnull(t2.ship_0_98,0) as ship_0_98
    from qujian_pici t1 left join shiji_batch t2 on t1.fnsku=t2.FNSKU and t1.store_name=t2.store_name
),

sales_data AS (
    SELECT
        fnsku,
         store_name,
        date,
        daily_sales_quantity daily_sales
    FROM dim_lingxing_sales_estimates
    WHERE date >= CURRENT_DATE()
),
temp_sale as (
    SELECT
    fnsku,
    store_name,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 6 THEN daily_sales ELSE 0 END),0) AS sales_0_7,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 13 THEN daily_sales ELSE 0 END),0) AS sales_0_14,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 20 THEN daily_sales ELSE 0 END),0) AS sales_0_21,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 27 THEN daily_sales ELSE 0 END),0) AS sales_0_28,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 34 THEN daily_sales ELSE 0 END),0) AS sales_0_35,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 41 THEN daily_sales ELSE 0 END),0) AS sales_0_42,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 48 THEN daily_sales ELSE 0 END),0) AS sales_0_49,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 55 THEN daily_sales ELSE 0 END),0) AS sales_0_56,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 62 THEN daily_sales ELSE 0 END),0) AS sales_0_63,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 69 THEN daily_sales ELSE 0 END),0) AS sales_0_70,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 76 THEN daily_sales ELSE 0 END),0) AS sales_0_77,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 83 THEN daily_sales ELSE 0 END),0) AS sales_0_84,
    ROUND(SUM(CASE WHEN DATEDIFF(date, CURRENT_DATE()) BETWEEN 0 AND 97 THEN daily_sales ELSE 0 END),0) AS sales_0_98
FROM sales_data
GROUP BY
    fnsku,
    store_name
ORDER BY
    fnsku,
    store_name
)
select t1.*,
       t2.sales_0_7,
       t2.sales_0_14,
       t2.sales_0_21,
       t2.sales_0_28,
       t2.sales_0_35,
       t2.sales_0_42,
       t2.sales_0_49,
       t2.sales_0_56,
       t2.sales_0_63,
       t2.sales_0_70,
       t2.sales_0_77,
       t2.sales_0_84,
       t2.sales_0_98,
CONCAT(t1.fnsku_inventory_1 + t1.ship_0_7 ,'/', ifnull(t2.sales_0_7,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_7) - ifnull(t2.sales_0_7,0), 0),')') AS chazhi_0_7,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_14 ,'/', ifnull(t2.sales_0_14,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_14) - ifnull(t2.sales_0_14,0), 0),')') AS chazhi_0_14,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_21 ,'/', ifnull(t2.sales_0_21,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_21) - ifnull(t2.sales_0_21,0), 0),')') AS chazhi_0_21,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_28 ,'/', ifnull(t2.sales_0_28,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_28) - ifnull(t2.sales_0_28,0), 0),')') AS chazhi_0_28,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_35 ,'/', ifnull(t2.sales_0_35,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_35) - ifnull(t2.sales_0_35,0), 0),')') AS chazhi_0_35,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_42 ,'/', ifnull(t2.sales_0_42,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_42) - ifnull(t2.sales_0_42,0), 0),')') AS chazhi_0_42,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_49 ,'/', ifnull(t2.sales_0_49,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_49) - ifnull(t2.sales_0_49,0), 0),')') AS chazhi_0_49,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_56 ,'/', ifnull(t2.sales_0_56,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_56) - ifnull(t2.sales_0_56,0), 0),')') AS chazhi_0_56,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_63 ,'/', ifnull(t2.sales_0_63,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_63) - ifnull(t2.sales_0_63,0), 0),')') AS chazhi_0_63,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_70 ,'/', ifnull(t2.sales_0_70,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_70) - ifnull(t2.sales_0_70,0), 0),')') AS chazhi_0_70,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_77 ,'/', ifnull(t2.sales_0_77,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_77) - ifnull(t2.sales_0_77,0), 0),')') AS chazhi_0_77,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_84 ,'/', ifnull(t2.sales_0_84,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_84) - ifnull(t2.sales_0_84,0), 0),')') AS chazhi_0_84,
    CONCAT(t1.fnsku_inventory_1 + t1.ship_0_98 ,'/', ifnull(t2.sales_0_98,0),'(',ROUND((t1.fnsku_inventory_1 + t1.ship_0_98) - ifnull(t2.sales_0_98,0), 0),')') AS chazhi_0_98
from qujian_pici2 t1 left join temp_sale t2
on t1.FNSKU=t2.fnsku
and t1.store_name=t2.store_name;



DELETE FROM ads_lingxing_all_warehouse_new_sh WHERE date = CURRENT_DATE;
INSERT INTO ads_lingxing_all_warehouse_new_sh
SELECT
    m.*,
    CURRENT_DATE as `date`
FROM ads_lingxing_all_warehouse_new m;
