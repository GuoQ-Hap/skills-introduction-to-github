-- 计划量
DROP TABLE IF EXISTS `dim_lingxing_planned_shipment_quantity_new`;
CREATE TABLE `dim_lingxing_planned_shipment_quantity_new` AS
SELECT
    msku,
    store_name,
    fnsku,
    SUM(CAST(quantity AS DECIMAL(10,2))) AS shipment_quantity
FROM (
    SELECT
        json_unquote(json_extract(V1.item, '$.msku')) AS msku,
        S.name AS store_name,
        json_unquote(json_extract(V1.item, '$.fnsku')) AS fnsku,
        json_unquote(json_extract(V2.item1, '$.quantity')) AS quantity
    FROM dwd_lingxing_inbound_shipment_detail_incr T1
    LATERAL VIEW EXPLODE_JSON_ARRAY_JSON_OUTER(items) V1 AS item
    LATERAL VIEW EXPLODE_JSON_ARRAY_JSON_OUTER(
        json_unquote(json_extract(V1.item, '$.shipment_ids'))
    ) V2 AS item1
    LATERAL VIEW EXPLODE_JSON_ARRAY_JSON_OUTER(
        json_unquote(json_extract(V1.item, '$.shipment_order_list'))
    ) V3 AS item2
    LEFT JOIN dim_lingxing_store S
        ON json_unquote(json_extract(V1.item, '$.sid')) = S.sid
    WHERE T1.STATUS ='0'
) AS raw_data
GROUP BY msku, store_name, fnsku;

-- 库存预处理
DROP TABLE IF EXISTS `temp_lingxing_kucun_num` ;
create table `temp_lingxing_kucun_num` as
with max_date as (select max(date) AS max_date from dwd_lingxing_fba_warehouse_detail),
wid_nam as (
    select a.*,b.type house_type
from dwd_lingxing_sc_warehouse a left join dim_lingxing_warehouse_mapping b on a.name=b.name
where a.date=(select max(date) from dwd_lingxing_sc_warehouse)
),
ranked_inventory as (
    select *
    from dwd_lingxing_inventory_details
    where product_valid_num+product_qc_num+quantity_receive+product_onway>0 and seller_id>0 and fnsku!=''
),
temp_local as (
    select
    t1.seller_id,
    t1.fnsku,
    sum(product_valid_num) as product_valid_num,
    sum(product_onway) as product_onway,
    -- 海外仓
    sum(case when t3.house_type = '海外仓' then product_qc_num else 0 end) as overseas_wh_product_qc_num,
    sum(case when t3.house_type = '海外仓' then product_onway else 0 end) as overseas_wh_product_onway,
    sum(case when t3.house_type = '海外仓' then product_valid_num else 0 end) as overseas_warehouse_quantity,
    sum(case when t3.house_type = '海外仓' then product_qc_num + product_onway else 0 end) as oversease_afn_inbound_shipped_quantity,

    -- 本地仓
    sum(case when t3.house_type = '本地仓' then quantity_receive else 0 end) as quantity_receive,
    sum(case when t3.house_type = '本地仓' then product_qc_num else 0 end) as local_wh_product_qc_num,
    sum(case when t3.house_type = '本地仓' then product_onway else 0 end) as local_wh_product_onway,
    sum(case when t3.house_type = '本地仓' then product_valid_num else 0 end) as local_warehouse_quantity,
    sum(case when t3.house_type = '本地仓' then product_qc_num + product_onway+quantity_receive else 0 end) as local_afn_inbound_shipped_quantity,
    t1.date
from ranked_inventory t1
left join wid_nam t3 on t1.wid = t3.wid
group by t1.seller_id, t1.fnsku,t1.date),

temp_fba_info as (
    select t1.*,t2.sid,ifnull(afn_fulfillable_quantity,0) afn_fulfillable_quantity,
           ifnull(reserved_fc_transfers,0) reserved_fc_transfers,
           ifnull(reserved_fc_processing,0) reserved_fc_processing,
           ifnull(afn_inbound_receiving_quantity,0) afn_inbound_receiving_quantity,
           ifnull(fba_warehouse_quantity,0) fba_warehouse_quantity,
           ifnull(stock_up_num,0) stock_up_num,
           ifnull(afn_inbound_working_quantity,0) afn_inbound_working_quantity,
           ifnull(inv_age_0_to_30_days,0) inv_age_0_to_30_days,
           ifnull(inv_age_31_to_60_days,0) inv_age_31_to_60_days,
           ifnull(inv_age_61_to_90_days,0) inv_age_61_to_90_days,
           ifnull(inv_age_91_to_180_days,0) inv_age_91_to_180_days,
           ifnull(inv_age_181_to_270_days,0) inv_age_181_to_270_days,
           ifnull(inv_age_271_to_330_days,0) inv_age_271_to_330_days,
           ifnull(inv_age_331_to_365_days,0) inv_age_331_to_365_days,
           ifnull(inv_age_365_plus_days,0) inv_age_365_plus_days
    from dim_lingxing_product_info t1 left join (select fnsku,seller_sku,b.sid,b.name store_name,
        sum(afn_fulfillable_quantity) afn_fulfillable_quantity,
        sum(reserved_fc_transfers) reserved_fc_transfers,
        sum(reserved_fc_processing) reserved_fc_processing,
        sum(afn_inbound_receiving_quantity) afn_inbound_receiving_quantity,
        sum(afn_fulfillable_quantity)+sum(reserved_fc_transfers)+sum(afn_inbound_receiving_quantity)+sum(reserved_fc_processing) fba_warehouse_quantity,
        sum(stock_up_num) stock_up_num,
        sum(afn_inbound_working_quantity) afn_inbound_working_quantity,
        sum(inv_age_0_to_30_days) inv_age_0_to_30_days,
        sum(inv_age_31_to_60_days) inv_age_31_to_60_days,
        sum(inv_age_61_to_90_days) inv_age_61_to_90_days,
        sum(inv_age_91_to_180_days) inv_age_91_to_180_days,
        sum(inv_age_181_to_270_days) inv_age_181_to_270_days,
        sum(inv_age_271_to_330_days) inv_age_271_to_330_days,
        sum(inv_age_331_to_365_days) inv_age_331_to_365_days,
        sum(inv_age_365_plus_days) inv_age_365_plus_days
from dwd_lingxing_fba_warehouse_detail a left join dim_lingxing_store b on a.sid=b.sid  group by fnsku,seller_sku,b.sid,b.name) t2 on t1.fnsku=t2.fnsku and t1.msku=t2.seller_sku and t1.store_name=t2.store_name
),
rs as (
    SELECT a.*,
       IFNULL(b.overseas_wh_product_qc_num, 0) AS overseas_wh_product_qc_num,
       IFNULL(b.overseas_wh_product_onway, 0) AS overseas_wh_product_onway,
       IFNULL(b.overseas_warehouse_quantity, 0) AS overseas_warehouse_quantity,
       IFNULL(b.oversease_afn_inbound_shipped_quantity, 0) AS oversease_afn_inbound_shipped_quantity,
       IFNULL(b.quantity_receive, 0) AS quantity_receive,
       IFNULL(b.local_wh_product_qc_num, 0) AS local_wh_product_qc_num,
       IFNULL(b.local_wh_product_onway, 0) AS local_wh_product_onway,
       IFNULL(b.local_warehouse_quantity, 0) AS local_warehouse_quantity,
       IFNULL(b.local_afn_inbound_shipped_quantity, 0) AS local_afn_inbound_shipped_quantity,
       IFNULL(c.shipment_quantity, 0) AS shipment_quantity2,
       a.fba_warehouse_quantity AS fnsku_inventory_1,
       a.fba_warehouse_quantity + a.stock_up_num  + IFNULL(c.shipment_quantity, 0) AS fnsku_inventory_2,
       a.fba_warehouse_quantity + a.stock_up_num  + IFNULL(c.shipment_quantity, 0)+ IFNULL(b.overseas_warehouse_quantity, 0) AS fnsku_inventory_3,
       a.fba_warehouse_quantity + a.stock_up_num  + IFNULL(c.shipment_quantity, 0)+ IFNULL(b.overseas_warehouse_quantity, 0) + IFNULL(b.oversease_afn_inbound_shipped_quantity, 0) AS fnsku_inventory_4,
       a.fba_warehouse_quantity + a.stock_up_num  + IFNULL(c.shipment_quantity, 0)+ IFNULL(b.overseas_warehouse_quantity, 0) + IFNULL(b.oversease_afn_inbound_shipped_quantity, 0) + IFNULL(b.local_warehouse_quantity, 0) AS fnsku_inventory_5,
       a.fba_warehouse_quantity + a.stock_up_num  + IFNULL(c.shipment_quantity, 0)+ IFNULL(b.overseas_warehouse_quantity, 0) + IFNULL(b.oversease_afn_inbound_shipped_quantity, 0) + IFNULL(b.local_warehouse_quantity, 0) + IFNULL(b.local_afn_inbound_shipped_quantity, 0) AS fnsku_inventory_6,
       md.max_date as date
    FROM temp_fba_info a
    LEFT JOIN temp_local b ON a.sid = b.seller_id AND a.fnsku = b.fnsku
    LEFT JOIN dim_lingxing_planned_shipment_quantity_new c ON a.store_name=c.store_name AND a.fnsku=c.fnsku AND a.msku=c.msku
    CROSS JOIN max_date md
),
max_dt AS (
    SELECT MAX(date) AS dt
    FROM dwd_spotter_list_storage_warehouse_incr
),
spotter_inventory as (
    SELECT
        t2.store_name, t2.erp_sku AS sku, t1.plt_sku AS asin, t2.fnsku,
        SUM(
            CASE
                -- spotter 仓
                WHEN t1.storage_name NOT LIKE 'LEANG%'
                     AND t1.upc IS NOT NULL
                     AND t1.storage_name IS NOT NULL
                THEN t1.available_num
                -- VC 仓
                WHEN t1.storage_name IS NULL
                     AND t1.upc IS NULL
                THEN t1.vc_total_inventory
                ELSE 0
            END
        ) AS available_num
    FROM dwd_spotter_list_storage_warehouse_incr t1
    JOIN max_dt m
        ON t1.date = m.dt
    
    LEFT JOIN dim_spotter_product_info t2
        ON (
            -- 两种 join 条件合并
            t1.plt_sku = t2.asin
            OR t1.ssku = t2.sku
        )
    WHERE t2.store_name IS NOT NULL
    GROUP BY t2.store_name, t2.erp_sku, t1.plt_sku, t2.fnsku
)
select
    t1.`msku`, t1.`sku`, t1.`store_name`, t1.`asin`, t1.`onsale_spu`, t1.`msku_status`, t1.`sku_status`, t1.`channel`, t1.`seller_id`,
    t1.`main_store`, t1.`country_code`, t1.`region`, t1.`shipments_country`, t1.`shipment_warehouse`, t1.`brand`, t1.`new_msku`,
    t1.`msku_product_property`, t1.`msku_isattract`, t1.`msku_sales_property`, t1.`msku_life_process`, t1.`new_sku`, t1.`sku_name`,
    t1.`fnsku`, t1.`channel_price_range`, t1.`selling_price_plan`, t1.`gross_cost_plan`, t1.`spu`, t1.`spu_name`, t1.`spu_status`,
    t1.`onsale_spu_product_property`, t1.`onsale_spu_isattract`, t1.`onsale_spu_sales_property`, t1.`onsale_spu_status`, t1.`onsale_spu_life_process_store`,
    t1.`onsale_spu_life_process_market`, t1.`seasonality`, t1.`weight_gram`, t1.`size_length_cm`, t1.`size_width_cm`, t1.`size_height_cm`, t1.`category_1`,
    t1.`category_2`, t1.`category_3`, t1.`parent_asin`, t1.`material`, t1.`colour`, t1.`color`, t1.`size`, t1.`technique`, t1.`pattern`, t1.`shape`,
    t1.`style`, t1.`scene`, t1.`sales_unit`, t1.`unit_quantity`, t1.`sales_date_actual`, t1.`sales_date_plan`, t1.`sales_apartment`, t1.`salesman`,
    t1.`product_manager`, t1.`reserved_string1`, t1.`reserved_string2`, t1.`reserved_string3`, t1.`reserved_number1`, t1.`reserved_number2`,
    t1.`reserved_number3`, t1.`sid`, t1.`afn_fulfillable_quantity`, t1.`reserved_fc_transfers`, t1.`reserved_fc_processing`, t1.`afn_inbound_receiving_quantity`,
    t1.`fba_warehouse_quantity`, t1.`stock_up_num`, t1.`afn_inbound_working_quantity`, t1.`inv_age_0_to_30_days`, t1.`inv_age_31_to_60_days`, t1.`inv_age_61_to_90_days`,
    t1.`inv_age_91_to_180_days`, t1.`inv_age_181_to_270_days`, t1.`inv_age_271_to_330_days`, t1.`inv_age_331_to_365_days`, t1.`inv_age_365_plus_days`,
    t1.`overseas_wh_product_qc_num`, t1.`overseas_wh_product_onway`, t1.`overseas_warehouse_quantity`, t1.`oversease_afn_inbound_shipped_quantity`,
    t1.`quantity_receive`, t1.`local_wh_product_qc_num`, t1.`local_wh_product_onway`, t1.`local_warehouse_quantity`, t1.`local_afn_inbound_shipped_quantity`,
    t1.`shipment_quantity2`, t1.`fnsku_inventory_1`, t1.`fnsku_inventory_2`,
    case
        when t1.store_name in ('DJWZ-US', 'GZ-US', 'FR-US') then t1.fnsku_inventory_3 + ifnull(t2.available_num,0)
        else t1.fnsku_inventory_3
    end as fnsku_inventory_3,
    case
        when t1.store_name in ('DJWZ-US', 'GZ-US', 'FR-US') then t1.fnsku_inventory_4 + ifnull(t2.available_num,0)
        else t1.fnsku_inventory_4
    end as fnsku_inventory_4,
    case
        when t1.store_name in ('DJWZ-US', 'GZ-US', 'FR-US') then t1.fnsku_inventory_5 + ifnull(t2.available_num,0)
        else t1.fnsku_inventory_5
    end as fnsku_inventory_5,
    case
        when t1.store_name in ('DJWZ-US', 'GZ-US', 'FR-US') then t1.fnsku_inventory_6 + ifnull(t2.available_num,0)
        else t1.fnsku_inventory_6
    end as fnsku_inventory_6,
    t1.`date`
from rs t1
left join spotter_inventory t2
on t1.store_name = t2.store_name and t1.fnsku = t2.fnsku and t1.asin = t2.asin and t1.sku = t2.sku;


-- 历史销量计算

DROP TABLE IF EXISTS `temp_lingxing_fnsku_quantity` ;
CREATE TABLE `temp_lingxing_fnsku_quantity` AS
WITH ranked_orders AS (
    SELECT
        price_list_seller_sku msku,
        fnsku,
        lower(seller_store_countries_seller_name) store_name,
        amount/volume  product_sales,
        amount,
        gross_profit,
        volume quantity,
        currency_icon,
        date,
        ROW_NUMBER() OVER (
            PARTITION BY price_list_seller_sku, fnsku, lower(seller_store_countries_seller_name)
            ORDER BY date DESC
        ) AS rn
    FROM (select t1.*,t2.fnsku from dwd_lingxing_sc_product_performance_msku t1 inner join dim_lingxing_product_info t2 on t1.price_list_seller_sku=t2.msku and t1.price_list_seller_name=t2.store_name) t
),
recent_30 AS (
    SELECT *
    FROM ranked_orders
    WHERE rn <= 30
),
recent_price AS (
SELECT
    msku,
    fnsku,
    lower(store_name) store_name,
    ROUND(SUM(product_sales*t2.my_rate) / NULLIF(SUM(quantity), 0), 2) AS last_30_order_price,
    ROUND(SUM(product_sales*t2.my_rate/us_rate) / NULLIF(SUM(quantity), 0), 2) AS last_30_order_us_price,
    ROUND(SUM(gross_profit) / NULLIF(SUM(amount), 0), 4) AS last_30_gross_margin
FROM recent_30 t1 left join (select a.*,b.us_rate
from dwd_lingxing_sc_rate a left join (select my_rate as us_rate,date
from dwd_lingxing_sc_rate
where name='美元') b on a.date=b.date) t2 on date_format(t1.date,'%Y-%m')=date_format(t2.date,'%Y-%m') and t1.currency_icon=t2.icon
GROUP BY msku, fnsku, lower(store_name)

)
SELECT
    t.price_list_seller_sku msku,
    t.fnsku,
    lower(t.price_list_seller_name) store_name,
    seller_store_countries_country country,

    -- 最近7天平均销量（T-9 到 T-2）
    ROUND(SUM(CASE WHEN date BETWEEN DATE_SUB(CURDATE(), INTERVAL 8 DAY)
                              AND DATE_SUB(CURDATE(), INTERVAL 2 DAY)
              THEN volume ELSE 0 END) / 7, 2) AS sale_quantity_7,

    -- 最近14天平均销量（T-16 到 T-2）
    ROUND(SUM(CASE WHEN date BETWEEN DATE_SUB(CURDATE(), INTERVAL 14 DAY)
                              AND DATE_SUB(CURDATE(), INTERVAL 2 DAY)
              THEN volume ELSE 0 END) / 14, 2) AS sale_quantity_14,

    -- 最近30天平均销量（T-32 到 T-2）
    ROUND(SUM(CASE WHEN date BETWEEN DATE_SUB(CURDATE(), INTERVAL 31 DAY)
                              AND DATE_SUB(CURDATE(), INTERVAL 2 DAY)
              THEN volume ELSE 0 END) / 30, 2) AS sale_quantity_30,
    -- 去年同期 300天销量
    ROUND(SUM(CASE WHEN date BETWEEN DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 31 DAY)
                              AND DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 2 DAY)
              THEN volume ELSE 0 END) / 30, 2) AS last_year_sale_quantity_30,

    -- 最近60天平均销量（T-62 到 T-2）
    ROUND(SUM(CASE WHEN date BETWEEN DATE_SUB(CURDATE(), INTERVAL 61 DAY)
                              AND DATE_SUB(CURDATE(), INTERVAL 2 DAY)
              THEN volume ELSE 0 END) / 60, 2) AS sale_quantity_60,
    -- 去年同期 60天销量
    ROUND(SUM(CASE WHEN date BETWEEN DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 61 DAY)
                              AND DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 2 DAY)
              THEN volume ELSE 0 END) / 60, 2) AS last_year_sale_quantity_60,

    -- 最近90天平均销量（T-92 到 T-2）
    ROUND(SUM(CASE WHEN date BETWEEN DATE_SUB(CURDATE(), INTERVAL 91 DAY)
                              AND DATE_SUB(CURDATE(), INTERVAL 2 DAY)
              THEN volume ELSE 0 END) / 90, 2) AS sale_quantity_90,
    -- 去年同期 90天销量
    ROUND(SUM(CASE WHEN date BETWEEN DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 91 DAY)
                              AND DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 2 DAY)
              THEN volume ELSE 0 END) / 90, 2) AS last_year_sale_quantity_90,
ROUND(SUM(CASE WHEN date BETWEEN DATE_SUB(CURDATE(), INTERVAL 91 DAY)
                              AND DATE_SUB(CURDATE(), INTERVAL 2 DAY)
              THEN gross_profit ELSE 0 END) /sum(amount), 4) AS last_90_gross_margin,
    rp.last_30_order_price,
    rp.last_30_order_us_price,
    rp.last_30_gross_margin
FROM (select t1.*,t2.fnsku from dwd_lingxing_sc_product_performance_msku t1 inner join dim_lingxing_product_info t2 on t1.price_list_seller_sku=t2.msku and t1.price_list_seller_name=t2.store_name) t
LEFT JOIN recent_price rp
       ON t.price_list_seller_sku = rp.msku
      AND t.fnsku = rp.fnsku
      AND lower(t.price_list_seller_name) = lower(rp.store_name)
GROUP BY t.price_list_seller_sku, t.fnsku, lower(t.price_list_seller_name), t.seller_store_countries_country, rp.last_30_order_price,rp.last_30_order_us_price,rp.last_30_gross_margin;


-- 销量预处理

DROP TABLE IF EXISTS `temp_lingxing_fnsku_sales` ;
CREATE TABLE `temp_lingxing_fnsku_sales` AS
with max_date as (select max(date) AS max_date from dwd_lingxing_fba_warehouse_detail),
max_sale as (
    select FNSKU,store_name,round(max(total),2) as max_total
    from dim_lingxing_sales_estimates
    group by FNSKU,store_name
),
temp_total as(
    select t1.fnsku,msku,t1.store_name,total as min_total,md.max_date as min_date,t2.max_total
    from dim_lingxing_sales_estimates t1 left join max_sale t2 on t1.FNSKU=t2.FNSKU and t1.store_name=t2.store_name
        CROSS JOIN max_date md
    where date=md.max_date
)
select t1.FNSKU,t1.store_name store_name,t1.msku,sum(total-min_total+daily_sales_quantity) as total,sum(daily_sales_quantity) daily_sales_quantity,max_total,date
from dim_lingxing_sales_estimates t1 left join temp_total t2
    on t1.fnsku=t2.fnsku and t1.store_name=t2.store_name
where t1.date>=t2.min_date group by t1.FNSKU,t1.store_name,t1.msku,max_total, date;


-- 累计销量处理

DROP TABLE IF EXISTS `temp_lingxing_fnsku_sales_forecast` ;
create table `temp_lingxing_fnsku_sales_forecast` as
-- 先算每个 SKU 最大日期
WITH max_date_per_sku AS (
    SELECT
        MAX(date) AS max_date
    FROM dwd_lingxing_fba_warehouse_detail
)
SELECT
    d.FNSKU,
    d.msku,
    d.store_name,
    SUM(CASE WHEN d.date BETWEEN m.max_date AND date_add(m.max_date, 14) THEN d.daily_sales_quantity ELSE 0 END) AS future_15d_sales,
    SUM(CASE WHEN d.date BETWEEN m.max_date AND date_add(m.max_date, 29) THEN d.daily_sales_quantity ELSE 0 END) AS future_30d_sales,
    SUM(CASE WHEN d.date BETWEEN m.max_date AND date_add(m.max_date, 44) THEN d.daily_sales_quantity ELSE 0 END) AS future_45d_sales,
    SUM(CASE WHEN d.date BETWEEN m.max_date AND date_add(m.max_date, 59) THEN d.daily_sales_quantity ELSE 0 END) AS future_60d_sales,
    SUM(CASE WHEN d.date BETWEEN m.max_date AND date_add(m.max_date, 74) THEN d.daily_sales_quantity ELSE 0 END) AS future_75d_sales,
    SUM(CASE WHEN d.date BETWEEN m.max_date AND date_add(m.max_date, 89) THEN d.daily_sales_quantity ELSE 0 END) AS future_90d_sales,
    SUM(CASE WHEN d.date BETWEEN m.max_date AND date_add(m.max_date, 104) THEN d.daily_sales_quantity ELSE 0 END) AS future_105d_sales

FROM dim_lingxing_sales_estimates d CROSS JOIN max_date_per_sku m
GROUP BY d.FNSKU, d.msku, d.store_name
ORDER BY d.FNSKU, d.msku, d.store_name;


-- 计算库存天数


DROP TABLE
IF
        EXISTS `temp_kucun_fnsku_zgb`;
CREATE TABLE `temp_kucun_fnsku_zgb` AS

with fba_date as (
    select max(date) as min_date
    from dwd_lingxing_fba_warehouse_detail
),
sale_date as (
    select max(date) as max_date
    from dim_lingxing_sales_estimates
),
days as(
select
    datediff(s.max_date, f.min_date) as day_num
from fba_date f
cross join sale_date s)
SELECT
        t1.SKU,
        t1.fnsku,
        t1.msku,
        t1.store_name,
        t1.region,
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
        t1.afn_fulfillable_quantity,
        t1.reserved_fc_transfers,
        t1.reserved_fc_processing,
        t1.afn_inbound_receiving_quantity,
        t1.stock_up_num,
        t1.afn_inbound_working_quantity,
        t1.inv_age_0_to_30_days,
        t1.inv_age_31_to_60_days,
        t1.inv_age_61_to_90_days,
        t1.inv_age_91_to_180_days,
        t1.inv_age_181_to_270_days,
        t1.inv_age_271_to_330_days,
        t1.inv_age_331_to_365_days,
        t1.inv_age_365_plus_days,
        t3.future_15d_sales,
        t3.future_30d_sales,
        t3.future_45d_sales,
        t3.future_60d_sales,
        t3.future_75d_sales,
        t3.future_90d_sales,
        IFNULL(t2.daily_sales_quantity,0) AS daily_sales_quantity ,
        IFNULL(t2.total,0) AS total,
        t1.fnsku_inventory_1+ifnull(t2.total,-0.01) AS 'maxTotal1',
        t1.fnsku_inventory_2+ifnull(t2.total,-0.01) AS 'maxTotal2',
        t1.fnsku_inventory_3+ifnull(t2.total,-0.01) AS 'maxTotal3',
        t1.fnsku_inventory_4+ifnull(t2.total,-0.01) AS 'maxTotal4',
        t1.fnsku_inventory_5 +ifnull(t2.total,-0.01) AS 'maxTotal5',
        t1.fnsku_inventory_6+ifnull(t2.total,-0.01) AS 'maxTotal6',
        t1.overseas_wh_product_qc_num,
        t1.overseas_wh_product_onway,
        t1.planned_quantity,
        t1.local_wh_product_qc_num ,
        t1.local_wh_product_onway ,
        t1.quantity_receive,
        t1.procurement_plan_quantity ,
        days.day_num as day_num,
        t1.date,
        max_total
FROM
        (
        select SKU, fnsku,msku,region,store_name,
        sum(fba_warehouse_quantity) fba_warehouse_quantity,
        sum(overseas_warehouse_quantity) overseas_warehouse_quantity,
        sum(oversease_afn_inbound_shipped_quantity) oversease_afn_inbound_shipped_quantity,
        sum(local_warehouse_quantity) local_warehouse_quantity,
        sum(local_afn_inbound_shipped_quantity) local_afn_inbound_shipped_quantity,
        sum(fnsku_inventory_1) fnsku_inventory_1,
        sum(fnsku_inventory_2) fnsku_inventory_2,
        sum(fnsku_inventory_3) fnsku_inventory_3,
        sum(fnsku_inventory_4) fnsku_inventory_4,
        sum(fnsku_inventory_5) fnsku_inventory_5,
        sum(fnsku_inventory_6) fnsku_inventory_6,
        sum(shipment_quantity2) shipment_quantity2,
        sum(afn_fulfillable_quantity) afn_fulfillable_quantity,
        sum(reserved_fc_transfers) reserved_fc_transfers,
        sum(reserved_fc_processing) reserved_fc_processing,
        sum(afn_inbound_receiving_quantity) afn_inbound_receiving_quantity,
        sum(stock_up_num) stock_up_num,
        sum(afn_inbound_working_quantity) afn_inbound_working_quantity,
        sum(inv_age_0_to_30_days) inv_age_0_to_30_days,
        sum(inv_age_31_to_60_days) inv_age_31_to_60_days,
        sum(inv_age_61_to_90_days) inv_age_61_to_90_days,
        sum(inv_age_91_to_180_days) inv_age_91_to_180_days,
        sum(inv_age_181_to_270_days) inv_age_181_to_270_days,
        sum(inv_age_271_to_330_days) inv_age_271_to_330_days,
        sum(inv_age_331_to_365_days) inv_age_331_to_365_days,
        sum(inv_age_365_plus_days) inv_age_365_plus_days,
        sum(overseas_wh_product_qc_num) overseas_wh_product_qc_num,
        sum(overseas_wh_product_onway) overseas_wh_product_onway,
        sum(0) planned_quantity,
        sum(local_wh_product_qc_num) local_wh_product_qc_num,
        sum(local_wh_product_onway) local_wh_product_onway,
        sum(quantity_receive) quantity_receive,
        sum(0) procurement_plan_quantity,
        date
        from temp_lingxing_kucun_num
                                                       group by SKU,fnsku,msku,store_name,date,region) AS t1
        LEFT JOIN
        temp_lingxing_fnsku_sales AS t2 ON t1.fnsku = t2.FNSKU
                                               and t1.store_name=t2.store_name
        and t1.DATE = t2.DATE left join temp_lingxing_fnsku_sales_forecast t3 on t1.fnsku=t3.FNSKU and t1.Store_Name=t3.store_name
        cross join days;


-- 可售天数


DROP TABLE IF EXISTS temp_keshou_fnsku_zjg;
CREATE TABLE temp_keshou_fnsku_zjg AS
SELECT
    t1.fnsku,
    t1.msku,
    t1.store_name,
    t1.forecast_date,
    t1.fba_warehouse_quantity,
    t1.overseas_warehouse_quantity,
    t1.oversease_afn_inbound_shipped_quantity,
    t1.local_warehouse_quantity,
    t1.local_afn_inbound_shipped_quantity,
    t1.overseas_wh_product_qc_num,
    t1.overseas_wh_product_onway,
    t1.planned_quantity,
    t1.local_wh_product_qc_num ,
    t1.local_wh_product_onway ,
    t1.quantity_receive,
    t1.procurement_plan_quantity ,
    t1.afn_fulfillable_quantity,
    t1.reserved_fc_transfers,
    t1.reserved_fc_processing,
    t1.afn_inbound_receiving_quantity,
    t1.stock_up_num,
    t1.afn_inbound_working_quantity,
    t1.future_15d_sales,
    t1.future_30d_sales,
    t1.future_45d_sales,
    t1.future_60d_sales,
    t1.future_75d_sales,
    t1.future_90d_sales,
    t1.fnsku_inventory_1,
    t1.fnsku_inventory_2,
    t1.fnsku_inventory_3,
    t1.fnsku_inventory_4,
    t1.fnsku_inventory_5,
    t1.fnsku_inventory_6,
    t1.shipment_quantity2,
    t1.inv_age_0_to_30_days,
    t1.inv_age_31_to_60_days,
    t1.inv_age_61_to_90_days,
    t1.inv_age_91_to_180_days,
    t1.inv_age_181_to_270_days,
    t1.inv_age_271_to_330_days,
    t1.inv_age_331_to_365_days,
    t1.inv_age_365_plus_days,
    t1.fnsku_available_days_1,
    t1.fnsku_available_days_str_1,
    t2.fnsku_available_days_2,
    t2.fnsku_available_days_str_2,
    t3.fnsku_available_days_3,
    t3.fnsku_available_days_str_3,
    t4.fnsku_available_days_4,
    t4.fnsku_available_days_str_4,
    t5.fnsku_available_days_5,
    t5.fnsku_available_days_str_5,
    t6.fnsku_available_days_6,
    t6.fnsku_available_days_str_6,
    t1.date,
    day_num
FROM (
    SELECT
        ranked_forecasts.*,
                                CASE
                                                when max_total is null THEN '数据缺失'
                                                WHEN forecast_date IS NULL AND max_total > 0 and fnsku_inventory_1 >0 THEN CONCAT(day_num, '+')
                                                when fnsku_inventory_1=0 then 0
                                                when forecast_date is not null then TO_DAYS(forecast_date) - TO_DAYS(date)
                                                ELSE '+∞'
                                END AS fnsku_available_days_str_1,
                                CASE
                                                WHEN fnsku_inventory_1 = 0 THEN 0
                                                WHEN forecast_date IS NULL AND maxTotal1 >= fnsku_inventory_1 THEN day_num
                                                WHEN forecast_date IS NULL THEN 0
                                                ELSE TO_DAYS(forecast_date) - TO_DAYS(date)
                                END AS fnsku_available_days_1
    FROM (
        SELECT
            i.*,
            sf.DATE AS forecast_date,
            ROW_NUMBER() OVER (PARTITION BY i.fnsku,i.store_name ORDER BY sf.DATE) AS rn
        FROM temp_kucun_fnsku_zgb i
        LEFT JOIN temp_lingxing_fnsku_sales sf
            ON sf.FNSKU = i.fnsku
            and lower(sf.store_name)=lower(i.store_name)
            AND sf.total > i.maxTotal1
    ) AS ranked_forecasts
    WHERE rn = 1
) t1
LEFT JOIN (
    SELECT
        ranked_forecasts.fnsku,
        ranked_forecasts.store_name,
                                CASE
                                                when max_total is null THEN '数据缺失'
                                                WHEN forecast_date IS NULL AND max_total > 0 and fnsku_inventory_2 >0 THEN CONCAT(day_num, '+')
                                                when fnsku_inventory_2=0 then 0
                                                when forecast_date is not null then TO_DAYS(forecast_date) - TO_DAYS(date)
                                                ELSE '+∞'
                                END AS fnsku_available_days_str_2,
                                CASE
                                                WHEN fnsku_inventory_2 = 0 THEN 0
                                                WHEN forecast_date IS NULL AND maxTotal2 >= fnsku_inventory_2 THEN day_num
                                                WHEN forecast_date IS NULL THEN 0
                                                ELSE TO_DAYS(forecast_date) - TO_DAYS(date)
                                END AS fnsku_available_days_2
    FROM (
        SELECT
            i.*,
            sf.DATE AS forecast_date,
            ROW_NUMBER() OVER (PARTITION BY i.fnsku, i.store_name ORDER BY sf.DATE) AS rn
        FROM temp_kucun_fnsku_zgb i
        LEFT JOIN temp_lingxing_fnsku_sales sf
            ON sf.FNSKU = i.fnsku
                   and lower(sf.store_name)=lower(i.store_name)
            AND sf.total > i.maxTotal2
    ) AS ranked_forecasts
    WHERE rn = 1
) t2 ON t1.fnsku = t2.fnsku and t1.store_name=t2.store_name
LEFT JOIN (
    SELECT
        ranked_forecasts.fnsku,
        ranked_forecasts.store_name,
                                CASE
                                                when max_total is null THEN '数据缺失'
                                                WHEN forecast_date IS NULL AND max_total > 0 and fnsku_inventory_3 >0 THEN CONCAT(day_num, '+')
                                                when fnsku_inventory_3=0 then 0
                                                when forecast_date is not null then TO_DAYS(forecast_date) - TO_DAYS(date)
                                                ELSE '+∞'
                                END AS fnsku_available_days_str_3,
                                CASE
                                                WHEN fnsku_inventory_3 = 0 THEN 0
                                                WHEN forecast_date IS NULL AND maxTotal3 >= fnsku_inventory_3 THEN day_num
                                                WHEN forecast_date IS NULL THEN 0
                                                ELSE TO_DAYS(forecast_date) - TO_DAYS(date)
                                END AS fnsku_available_days_3
    FROM (
        SELECT
            i.*,
            sf.DATE AS forecast_date,
            ROW_NUMBER() OVER (PARTITION BY i.fnsku, i.store_name ORDER BY sf.DATE) AS rn
        FROM temp_kucun_fnsku_zgb i
        LEFT JOIN temp_lingxing_fnsku_sales sf
            ON sf.FNSKU = i.fnsku
                   and lower(sf.store_name)=lower(i.store_name)
            AND sf.total > i.maxTotal3
    ) AS ranked_forecasts
    WHERE rn = 1
) t3 ON t1.fnsku = t3.fnsku and t1.store_name=t3.store_name
LEFT JOIN (
    SELECT
        ranked_forecasts.fnsku,
        ranked_forecasts.store_name,
                                CASE
                                                when max_total is null THEN '数据缺失'
                                                WHEN forecast_date IS NULL AND max_total > 0 and fnsku_inventory_4 >0 THEN CONCAT(day_num, '+')
                                                when fnsku_inventory_4=0 then 0
                                                when forecast_date is not null then TO_DAYS(forecast_date) - TO_DAYS(date)
                                                ELSE '+∞'
                                END AS fnsku_available_days_str_4,
                                CASE
                                                WHEN fnsku_inventory_4 = 0 THEN 0
                                                WHEN forecast_date IS NULL AND maxTotal6 >= fnsku_inventory_4 THEN day_num
                                                WHEN forecast_date IS NULL THEN 0
                                                ELSE TO_DAYS(forecast_date) - TO_DAYS(date)
                                END AS fnsku_available_days_4
    FROM (
        SELECT
            i.*,
            sf.DATE AS forecast_date,
            ROW_NUMBER() OVER (PARTITION BY i.fnsku, i.store_name ORDER BY sf.DATE) AS rn
        FROM temp_kucun_fnsku_zgb i
        LEFT JOIN temp_lingxing_fnsku_sales sf
            ON sf.FNSKU = i.fnsku
                   and lower(sf.store_name)=lower(i.store_name)
            AND sf.total > i.maxTotal4
    ) AS ranked_forecasts
    WHERE rn = 1
) t4 ON t1.fnsku = t4.fnsku and t1.store_name=t4.store_name
LEFT JOIN (
    SELECT
        ranked_forecasts.fnsku,
        ranked_forecasts.store_name,
                                CASE
                                                when max_total is null THEN '数据缺失'
                                                WHEN forecast_date IS NULL AND max_total > 0 and fnsku_inventory_5 >0 THEN CONCAT(day_num, '+')
                                                when fnsku_inventory_5=0 then 0
                                                when forecast_date is not null then TO_DAYS(forecast_date) - TO_DAYS(date)
                                                ELSE '+∞'
                                END AS fnsku_available_days_str_5,
                                CASE
                                                WHEN fnsku_inventory_5 = 0 THEN 0
                                                WHEN forecast_date IS NULL AND maxTotal5 >= fnsku_inventory_5 THEN day_num
                                                WHEN forecast_date IS NULL THEN 0
                                                ELSE TO_DAYS(forecast_date) - TO_DAYS(date)
                                END AS fnsku_available_days_5
    FROM (
        SELECT
            i.*,
            sf.DATE AS forecast_date,
            ROW_NUMBER() OVER (PARTITION BY i.fnsku,i.store_name ORDER BY sf.DATE) AS rn
        FROM temp_kucun_fnsku_zgb i
        LEFT JOIN temp_lingxing_fnsku_sales sf
            ON sf.FNSKU = i.fnsku
                   and lower(sf.store_name)=lower(i.store_name)
            AND sf.total > i.maxTotal5
    ) AS ranked_forecasts
    WHERE rn = 1
) t5 ON t1.fnsku = t5.fnsku and t1.store_name=t5.store_name
LEFT JOIN (
    SELECT
        ranked_forecasts.fnsku,
        ranked_forecasts.store_name,
                                                               CASE
                                                when max_total is null THEN '数据缺失'
                                                WHEN forecast_date IS NULL AND max_total > 0 and fnsku_inventory_6 >0 THEN CONCAT(day_num, '+')
                                                when fnsku_inventory_6=0 then 0
                                                when forecast_date is not null then TO_DAYS(forecast_date) - TO_DAYS(date)
                                                ELSE '+∞'
                                END AS fnsku_available_days_str_6,
                                CASE
                                                WHEN fnsku_inventory_6 = 0 THEN 0
                                                WHEN forecast_date IS NULL AND maxTotal6 >= fnsku_inventory_6 THEN day_num
                                                WHEN forecast_date IS NULL THEN 0
                                                ELSE TO_DAYS(forecast_date) - TO_DAYS(date)
                                END AS fnsku_available_days_6
    FROM (
        SELECT
            i.*,
            sf.DATE AS forecast_date,
            ROW_NUMBER() OVER (PARTITION BY i.fnsku,i.store_name ORDER BY sf.DATE) AS rn
        FROM temp_kucun_fnsku_zgb i
        LEFT JOIN temp_lingxing_fnsku_sales sf
            ON sf.FNSKU = i.fnsku
                   and lower(sf.store_name)=lower(i.store_name)
            AND sf.total > i.maxTotal6
    ) AS ranked_forecasts
    WHERE rn = 1
) t6 ON t1.fnsku = t6.fnsku and t1.store_name=t6.store_name;


-- 备货规则中间表

DROP TABLE IF EXISTS temp_lingxing_stocking_rules_temp;

CREATE TABLE temp_lingxing_stocking_rules_temp
AS
WITH max_date AS (
    SELECT MAX(date) AS max_date
    FROM dwd_lingxing_fba_warehouse_detail
),
rules AS (
SELECT
    r.FNSKU,
    r.store_name,
    r.asin,
    r.msku,
    r.logistics_model,
    r.first_leg_logistics_channel,
    IFNULL(r.restocking_frequency,0) restocking_frequency,
    IFNULL(r.shipments_frequency,0) shipments_frequency,
    ifnull(r.order_duration,0) order_duration,
    ifnull(r.production_duration,0) production_duration,
    ifnull(r.next_restock_production_duration,0) next_restock_production_duration, -- 下次生产时长
    ifnull(r.local_warehouse_pick_time,0) local_warehouse_pick_time,
    ifnull(r.overseas_warehouse_pick_time,0) overseas_warehouse_pick_time,
    ifnull(r.local_to_FBA_time,0) local_to_FBA_time,
    ifnull(r.next_restock_local_to_fba_time,0) next_restock_local_to_fba_time, -- 下次本地仓-fba
    ifnull(r.local_to_overseas_warehouse_time,0) local_to_overseas_warehouse_time,
    IFNULL(r.next_restock_local_to_overseas_warehouse_time,0) next_restock_local_to_overseas_warehouse_time, -- 下次本地仓到awd
    ifnull(r.overseas_to_FBA_time,0) overseas_to_FBA_time,
    ifnull(r.next_restock_overseas_to_fba_time,0) next_restock_overseas_to_fba_time, -- 下次awd到FBA
    ifnull(r.max_over_sell_ratio,0) max_over_sell_ratio,
    ifnull(r.next_restock_max_over_sell_ratio,0) next_restock_max_over_sell_ratio, -- 下次超卖
    ifnull(r.logistics_safety_stock_days,0) logistics_safety_stock_days,
    ifnull(r.next_restock_logistics_safety_stock_days,0) next_restock_logistics_safety_stock_days, -- 下次物流安全库存天数
    ifnull(r.production_safety_stock_days,0) production_safety_stock_days,
    ifnull(r.next_restock_production_safety_stock_days,0) next_restock_production_safety_stock_days, -- 下次补货生产安全库存天数
    CASE
        WHEN r.logistics_model = '本地仓中转模式' THEN
            IFNULL(r.order_duration, 0) + IFNULL(r.local_warehouse_pick_time, 0) + IFNULL(r.local_to_FBA_time, 0)
        WHEN r.logistics_model = '本地仓&海外仓中转' THEN
            IFNULL(r.order_duration, 0) + IFNULL(r.overseas_warehouse_pick_time, 0) + IFNULL(r.overseas_to_FBA_time, 0)
        ELSE
            IFNULL(r.order_duration, 0) + IFNULL(r.local_warehouse_pick_time, 0) + IFNULL(r.local_to_FBA_time, 0)
    END AS FBA_delivery_time_fn,
    /* NEXT FBA仓交付时长 */
    CASE
        WHEN r.logistics_model = '本地仓中转模式' THEN
            IFNULL(r.order_duration, 0) + IFNULL(r.local_warehouse_pick_time, 0) + IFNULL(r.next_restock_local_to_fba_time, 0)
        WHEN r.logistics_model = '本地仓&海外仓中转' THEN
            IFNULL(r.order_duration, 0) + IFNULL(r.overseas_warehouse_pick_time, 0) + IFNULL(r.next_restock_overseas_to_fba_time, 0)
        ELSE
            IFNULL(r.order_duration, 0) + IFNULL(r.local_warehouse_pick_time, 0) + IFNULL(r.next_restock_local_to_fba_time, 0)
    END AS FBA_delivery_time_fn_next,

    /* 海外仓交付时长 */
    CASE
        WHEN r.logistics_model = '本地仓中转模式' THEN 0
        WHEN r.logistics_model = '本地仓&海外仓中转' THEN
            IFNULL(r.order_duration, 0) + IFNULL(r.local_warehouse_pick_time, 0) + IFNULL(r.local_to_overseas_warehouse_time, 0)
        ELSE 0
    END AS overseas_warehouse_delivery_time_fn,

   /* NEXT 海外仓交付时长 */
    CASE
        WHEN r.logistics_model = '本地仓中转模式' THEN 0
        WHEN r.logistics_model = '本地仓&海外仓中转' THEN
            IFNULL(r.order_duration, 0) + IFNULL(r.local_warehouse_pick_time, 0) + IFNULL(r.next_restock_local_to_overseas_warehouse_time, 0)
        ELSE 0
     END AS overseas_warehouse_delivery_time_fn_next,

    /* 本地仓交付时长 */
    CASE
        WHEN r.logistics_model = '本地仓中转模式' THEN
            IFNULL(r.order_duration, 0) + IFNULL(r.production_duration, 0)
        WHEN r.logistics_model = '本地仓&海外仓中转' THEN
            IFNULL(r.order_duration, 0) + IFNULL(r.production_duration, 0)
        ELSE
            IFNULL(r.order_duration, 0) + IFNULL(r.production_duration, 0)
    END AS local_warehouse_delivery_time_fn,

   /* next本地仓交付时长 */
      CASE
        WHEN r.logistics_model = '本地仓中转模式' THEN
            IFNULL(r.order_duration, 0) + IFNULL(r.next_restock_production_duration, 0)
        WHEN r.logistics_model = '本地仓&海外仓中转' THEN
            IFNULL(r.order_duration, 0) + IFNULL(r.next_restock_production_duration, 0)
        ELSE
            IFNULL(r.order_duration, 0) + IFNULL(r.next_restock_production_duration, 0)
    END AS local_warehouse_delivery_time_fn_next,

  /* next销售安全库存 */
    CASE
        WHEN r.logistics_model = '本地仓中转模式' THEN
            IFNULL(r.order_duration, 0)
            + IFNULL(r.local_warehouse_pick_time, 0)
            + IFNULL(r.next_restock_local_to_fba_time, 0)
            + IFNULL(r.next_restock_logistics_safety_stock_days, 0)
        WHEN r.logistics_model = '本地仓&海外仓中转' THEN
            IFNULL(r.order_duration, 0)
            + IFNULL(r.local_warehouse_pick_time, 0)
            + IFNULL(r.next_restock_local_to_overseas_warehouse_time, 0)
            + IFNULL(r.overseas_warehouse_pick_time, 0)
            + IFNULL(r.next_restock_overseas_to_fba_time, 0)
            + IFNULL(r.next_restock_logistics_safety_stock_days, 0)
        ELSE
            IFNULL(r.order_duration, 0)
            + IFNULL(r.local_warehouse_pick_time, 0)
            + IFNULL(r.next_restock_local_to_fba_time, 0)
            + IFNULL(r.next_restock_logistics_safety_stock_days, 0)
    END AS day_safety_stock_sales_next,

    /* 销售安全库存 */
       CASE
        WHEN r.logistics_model = '本地仓中转模式' THEN
            IFNULL(r.order_duration, 0)
            + IFNULL(r.local_warehouse_pick_time, 0)
            + IFNULL(r.local_to_FBA_time, 0)
            + IFNULL(r.logistics_safety_stock_days, 0)
        WHEN r.logistics_model = '本地仓&海外仓中转' THEN
            IFNULL(r.order_duration, 0)
            + IFNULL(r.local_warehouse_pick_time, 0)
            + IFNULL(r.local_to_overseas_warehouse_time, 0)
            + IFNULL(r.overseas_warehouse_pick_time, 0)
            + IFNULL(r.overseas_to_FBA_time, 0)
            + IFNULL(r.logistics_safety_stock_days, 0)
        ELSE
            IFNULL(r.order_duration, 0)
            + IFNULL(r.local_warehouse_pick_time, 0)
            + IFNULL(r.local_to_FBA_time, 0)
            + IFNULL(r.logistics_safety_stock_days, 0)
    END AS day_safety_stock_sales,
    case when r.logistics_model='本地仓&海外仓中转' then ifnull(logistics_safety_stock_days,0) else 0 end overseas_warehouse_safety_days,
    case when r.logistics_model='本地仓&海外仓中转' then ifnull(next_restock_logistics_safety_stock_days,0) else 0 end next_overseas_warehouse_safety_days, -- 下次海外安全天数
    case when r.logistics_model='本地仓&海外仓中转' then ifnull(production_safety_stock_days,0) else ifnull(production_safety_stock_days,0) end local_warehouse_safety_days,
    case when r.logistics_model='本地仓&海外仓中转' then ifnull(next_restock_production_safety_stock_days,0) else ifnull(next_restock_production_safety_stock_days,0) end next_local_warehouse_safety_days, -- 下次本地安全天数
    m.max_date
FROM dim_lingxing_stocking_rules r
CROSS JOIN max_date m
),
sales AS (
    SELECT
        s.FNSKU,
        s.ASIN,
        s.msku,
        s.store_name,
        SUM(ifnull(s.daily_sales_quantity,0)) AS safety_stock_sales
    FROM dim_lingxing_sales_estimates s
    JOIN rules r
      ON s.FNSKU = r.FNSKU
     AND s.ASIN = r.ASIN
     AND s.msku = r.msku
     AND s.store_name = r.store_name
     AND s.date >= r.max_date
     AND s.date <= DATE_ADD(r.max_date, INTERVAL r.day_safety_stock_sales DAY)
    GROUP BY s.FNSKU, s.ASIN, s.msku,s.store_name
)
SELECT
    r.*,
    s.safety_stock_sales * ifnull(r.max_over_sell_ratio,0) AS safety_stock_sales
FROM rules r
LEFT JOIN sales s
  ON r.FNSKU = s.FNSKU
 AND r.ASIN = s.ASIN
 AND r.msku = s.msku
 AND r.store_name = s.store_name;

-- 备货规则
DROP TABLE IF EXISTS temp_lingxing_stocking_rules;

CREATE TABLE temp_lingxing_stocking_rules
AS
with temp_rule as (
select t1.*,t2.total+t1.safety_stock_sales as max_safety_stock_sales,DATE_ADD(t1.max_date, INTERVAL t1.FBA_delivery_time_fn+ifnull(t1.logistics_safety_stock_days,0) DAY) as min_date,
      DATE_ADD(t1.max_date, INTERVAL t1.FBA_delivery_time_fn_next+ifnull(t1.next_restock_logistics_safety_stock_days,0) DAY) as min_date2
from temp_lingxing_stocking_rules_temp t1 left join temp_lingxing_fnsku_sales t2 on t1.FNSKU=t2.FNSKU
and t1.msku = t2.msku and lower(t1.store_name)=lower(t2.store_name)
and t2.DATE >= DATE_ADD(t1.max_date, INTERVAL t1.FBA_delivery_time_fn+ifnull(t1.logistics_safety_stock_days,0) DAY)
),
temp_sale as (
    select *,
       CASE
    WHEN safety_stock_sales = 0 THEN 0
    ELSE
        GREATEST(0,
        COALESCE(DATEDIFF(
        COALESCE(DATE, CURDATE()),
        COALESCE(min_date, CURDATE())
    ), 0))
END AS safety_stock_days_sales, -- 安全库存天数

          CASE
    WHEN safety_stock_sales = 0 THEN 0
    ELSE
        GREATEST(0,
        COALESCE(DATEDIFF(
        COALESCE(DATE, CURDATE()),
        COALESCE(min_date2, CURDATE())
    ), 0))
END AS next_safety_stock_days_sales, -- 安全库存天数下次


    /* FBA安全天数 */
CASE
    WHEN t.logistics_model = '本地仓&海外仓中转模式' THEN
        CASE
            WHEN safety_stock_sales = 0 THEN 0
            ELSE
                GREATEST(0,
                COALESCE(DATEDIFF(
                COALESCE(DATE, CURDATE()),
                COALESCE(min_date, CURDATE())
            ), 0))
        END
    ELSE
        CASE
            WHEN safety_stock_sales = 0 THEN 0
            ELSE
                GREATEST(0,
                COALESCE(DATEDIFF(
                COALESCE(DATE, CURDATE()),
                COALESCE(min_date, CURDATE())
            ), 0)) + logistics_safety_stock_days
        END
END AS fba_safety_days_fn,

         /* 下次FBA安全天数 */
CASE
    WHEN t.logistics_model = '本地仓&海外仓中转模式' THEN
        CASE
            WHEN safety_stock_sales = 0 THEN 0
            ELSE
                GREATEST(0,
                COALESCE(DATEDIFF(
                COALESCE(DATE, CURDATE()),
                COALESCE(min_date2, CURDATE())
            ), 0))
        END
    ELSE
        CASE
            WHEN safety_stock_sales = 0 THEN 0
            ELSE
                GREATEST(0,
                COALESCE(DATEDIFF(
                COALESCE(DATE, CURDATE()),
                COALESCE(min_date2, CURDATE())
            ), 0)) + logistics_safety_stock_days
        END
END AS next_fba_safety_days_fn,

    case
        when logistics_model='本地仓&海外仓中转模式' then logistics_safety_stock_days
        else 0
        end as overseas_warehouse_delivery_days_fn,
    case
        when logistics_model='本地仓&海外仓中转模式' then production_safety_stock_days
        else production_safety_stock_days
        end as local_warehouse_delivery_days_fn

from (select t1.*,t2.DATE,ROW_NUMBER() OVER (PARTITION BY t1.fnsku,t1.store_name ORDER BY t2.DATE) AS rn
from temp_rule t1 left join temp_lingxing_fnsku_sales t2 on t1.FNSKU=t2.FNSKU and lower(t1.store_name)=lower(t2.store_name)
where t2.total>=t1.max_safety_stock_sales) t
where rn=1

)
select t1.*,ifnull(t2.safety_stock_days_sales,0) safety_stock_days_sales,
       ifnull(t2.next_safety_stock_days_sales,0) next_safety_stock_days_sales,
       ifnull(t2.fba_safety_days_fn,0) fba_safety_days_fn,
       ifnull(t2.next_fba_safety_days_fn,0) next_fba_safety_days_fn,
       ifnull(t2.overseas_warehouse_delivery_days_fn,0) overseas_warehouse_delivery_days_fn,
       ifnull(t2.local_warehouse_delivery_days_fn,0) local_warehouse_delivery_days_fn
from temp_lingxing_stocking_rules_temp t1 left join temp_sale t2 on t1.FNSKU=t2.FNSKU and t1.store_name=t2.store_name;


-- 计算补货倒计时


DROP TABLE IF EXISTS temp_buhuo_fnsku_zjg;
CREATE TABLE temp_buhuo_fnsku_zjg AS
select t1.*,
        t2.logistics_model,
        t2.first_leg_logistics_channel,
        t2.order_duration,
        t2.production_duration,
        t2.next_restock_production_duration,
        t2.local_warehouse_pick_time,
        t2.overseas_warehouse_pick_time,
        t2.local_to_FBA_time,
        t2.next_restock_local_to_fba_time,
        t2.local_to_overseas_warehouse_time,
        t2.next_restock_local_to_overseas_warehouse_time,
        t2.overseas_to_FBA_time,
        t2.next_restock_overseas_to_fba_time,
       t2.max_over_sell_ratio,
       t2.next_restock_max_over_sell_ratio,
       t2.safety_stock_sales,
       t2.safety_stock_days_sales,
       t2.logistics_safety_stock_days,
       t2.next_restock_logistics_safety_stock_days,
       t2.production_safety_stock_days,
       t2.next_restock_production_safety_stock_days,
       t2.fba_safety_days_fn,
       t2.overseas_warehouse_safety_days,
       t2.local_warehouse_safety_days,
       t2.FBA_delivery_time_fn,
       t2.FBA_delivery_time_fn_next,
       t2.overseas_warehouse_delivery_time_fn,
       t2.overseas_warehouse_delivery_time_fn_next,
       t2.local_warehouse_delivery_time_fn,
       t2.local_warehouse_delivery_time_fn_next,
       t2.restocking_frequency,
       t2.shipments_frequency,
       t2.day_safety_stock_sales_next,
       t2.next_overseas_warehouse_safety_days,
       t2.next_local_warehouse_safety_days,
       t2.next_fba_safety_days_fn,
       t2.next_safety_stock_days_sales,



       case
           when t2.FBA_delivery_time_fn is null then 0
           when t1.fnsku_available_days_str_1='数据缺失' or t1.fnsku_available_days_str_1='+∞' then t1.fnsku_available_days_1
           when t1.fnsku_available_days_str_1=CONCAT(day_num, '+') then t1.fnsku_available_days_1

           else t1.fnsku_available_days_1-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn end as fnsku_restocking_countdown_1,
        case
            when t2.FBA_delivery_time_fn is null then '数据缺失'
            when t1.fnsku_available_days_str_1='数据缺失' or t1.fnsku_available_days_str_1='+∞'  then t1.fnsku_available_days_str_1
           when t1.fnsku_available_days_str_1=CONCAT(day_num, '+') then t1.fnsku_available_days_str_1
           else t1.fnsku_available_days_1-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn end as fnsku_restocking_countdown_str_1,
       case
           when t2.FBA_delivery_time_fn is null then 0
           when t1.fnsku_available_days_str_2='数据缺失' or t1.fnsku_available_days_str_2='+∞' then t1.fnsku_available_days_2
           when t1.fnsku_available_days_str_2=CONCAT(day_num, '+') then t1.fnsku_available_days_2
           else t1.fnsku_available_days_2-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn end as fnsku_restocking_countdown_2,
    case
        when t2.FBA_delivery_time_fn is null then '数据缺失'
           when t1.fnsku_available_days_str_2='数据缺失' or t1.fnsku_available_days_str_2='+∞' then t1.fnsku_available_days_str_2
           when t1.fnsku_available_days_str_2=CONCAT(day_num, '+') then t1.fnsku_available_days_str_2
           else t1.fnsku_available_days_2-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn end as fnsku_restocking_countdown_str_2,
       case
           when t2.FBA_delivery_time_fn is null then 0
           when t1.fnsku_available_days_str_3='数据缺失' or t1.fnsku_available_days_str_3='+∞' then t1.fnsku_available_days_3
           when t1.fnsku_available_days_str_3=CONCAT(day_num, '+') then t1.fnsku_available_days_3
           else t1.fnsku_available_days_3-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn-t2.overseas_warehouse_safety_days-t2.overseas_warehouse_delivery_time_fn end as fnsku_restocking_countdown_3,
    case
        when t2.FBA_delivery_time_fn is null then '数据缺失'
           when t1.fnsku_available_days_str_3='数据缺失' or t1.fnsku_available_days_str_3='+∞' then t1.fnsku_available_days_str_3
           when t1.fnsku_available_days_str_3=CONCAT(day_num, '+') then t1.fnsku_available_days_str_3
           else t1.fnsku_available_days_3-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn-t2.overseas_warehouse_safety_days-t2.overseas_warehouse_delivery_time_fn end as fnsku_restocking_countdown_str_3,
       case
           when t2.FBA_delivery_time_fn is null then 0
           when t1.fnsku_available_days_str_4='数据缺失' or t1.fnsku_available_days_str_4='+∞' then t1.fnsku_available_days_4
           when t1.fnsku_available_days_str_4=CONCAT(day_num, '+') then t1.fnsku_available_days_4
           else t1.fnsku_available_days_4-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn-t2.overseas_warehouse_safety_days-t2.overseas_warehouse_delivery_time_fn end as fnsku_restocking_countdown_4,
    case
        when t2.FBA_delivery_time_fn is null then '数据缺失'
           when t1.fnsku_available_days_str_4='数据缺失' or t1.fnsku_available_days_str_4='+∞' then t1.fnsku_available_days_str_4
           when t1.fnsku_available_days_str_4=CONCAT(day_num, '+') then t1.fnsku_available_days_str_4
           else t1.fnsku_available_days_4-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn-t2.overseas_warehouse_safety_days-t2.overseas_warehouse_delivery_time_fn end as fnsku_restocking_countdown_str_4,

       case
           when t2.FBA_delivery_time_fn is null then 0
           when t1.fnsku_available_days_str_5='数据缺失' or t1.fnsku_available_days_str_5='+∞' then t1.fnsku_available_days_5
           when t1.fnsku_available_days_str_5=CONCAT(day_num, '+') then t1.fnsku_available_days_5
           else t1.fnsku_available_days_5-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn-t2.overseas_warehouse_safety_days-t2.overseas_warehouse_delivery_time_fn-t2.local_warehouse_safety_days-t2.local_warehouse_delivery_time_fn end as fnsku_restocking_countdown_5,
      case
          when t2.FBA_delivery_time_fn is null then '数据缺失'
           when t1.fnsku_available_days_str_5='数据缺失' or t1.fnsku_available_days_str_5='+∞' then t1.fnsku_available_days_str_5
           when t1.fnsku_available_days_str_5=CONCAT(day_num, '+') then t1.fnsku_available_days_str_5
           else t1.fnsku_available_days_5-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn-t2.overseas_warehouse_safety_days-t2.overseas_warehouse_delivery_time_fn-t2.local_warehouse_safety_days-t2.local_warehouse_delivery_time_fn end as fnsku_restocking_countdown_str_5,
    case
         when t2.FBA_delivery_time_fn is null then 0
           when t1.fnsku_available_days_str_6='数据缺失' or t1.fnsku_available_days_str_6='+∞' then t1.fnsku_available_days_6
           when t1.fnsku_available_days_str_6=CONCAT(day_num, '+') then t1.fnsku_available_days_6
           else t1.fnsku_available_days_6-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn-t2.overseas_warehouse_safety_days-t2.overseas_warehouse_delivery_time_fn-t2.local_warehouse_safety_days-t2.local_warehouse_delivery_time_fn end as fnsku_restocking_countdown_6,
    case
        when t2.FBA_delivery_time_fn is null then '数据缺失'
           when t1.fnsku_available_days_str_6='数据缺失' or t1.fnsku_available_days_str_6='+∞' then t1.fnsku_available_days_str_6
           when t1.fnsku_available_days_str_6=CONCAT(day_num, '+') then t1.fnsku_available_days_str_6
           else t1.fnsku_available_days_6-t2.FBA_delivery_time_fn-t2.fba_safety_days_fn-t2.overseas_warehouse_safety_days-t2.overseas_warehouse_delivery_time_fn-t2.local_warehouse_safety_days-t2.local_warehouse_delivery_time_fn end as fnsku_restocking_countdown_str_6
from temp_keshou_fnsku_zjg t1 left join temp_lingxing_stocking_rules t2 on
t1.FNSKU=t2.FNSKU
and t1.msku = t2.msku
and t1.store_name=t2.store_name;


-- 底表代码 13461

DROP TABLE IF EXISTS temp_select_fnsku_zjg;
CREATE TABLE temp_select_fnsku_zjg AS
select t1.*,
       t2.sale_quantity_7,
       t2.sale_quantity_14,
       t2.sale_quantity_30,
       t2.sale_quantity_60,
       t2.sale_quantity_90,
       t2.last_year_sale_quantity_30,
       t2.last_year_sale_quantity_60,
       t2.last_year_sale_quantity_90,
       t2.last_30_order_price,
       t2.last_30_order_us_price,
       t2.last_90_gross_margin,
       case
           when ifnull(t2.sale_quantity_30,0) =0 and t1.fnsku_inventory_1 != 0 then day_num
           when ifnull(t2.sale_quantity_30,0) =0 or t1.fnsku_inventory_1 = 0  then 0
           when round(t1.fnsku_inventory_1/t2.sale_quantity_30,2)>=day_num then day_num
           else
       round(t1.fnsku_inventory_1/t2.sale_quantity_30,2) end as 'sale_fnsku_available_1',
          case
              when ifnull(t2.sale_quantity_30,0) =0 and t1.fnsku_inventory_2 != 0 then day_num
              when ifnull(t2.sale_quantity_30,0) =0 or t1.fnsku_inventory_2 = 0  then 0
              when round(t1.fnsku_inventory_2/t2.sale_quantity_30,2)>=day_num then day_num
              else
       round(t1.fnsku_inventory_2/t2.sale_quantity_30,2) end as 'sale_fnsku_available_2',
          case
              when ifnull(t2.sale_quantity_30,0) =0 and t1.fnsku_inventory_3 != 0 then day_num
              when ifnull(t2.sale_quantity_30,0) =0 or t1.fnsku_inventory_3 = 0  then 0
              when round(t1.fnsku_inventory_3/t2.sale_quantity_30,2)>=day_num then day_num
              else
       round(t1.fnsku_inventory_3/t2.sale_quantity_30,2) end as 'sale_fnsku_available_3',
          case
              when ifnull(t2.sale_quantity_30,0) =0 and t1.fnsku_inventory_4 != 0 then day_num
              when ifnull(t2.sale_quantity_30,0) =0 or t1.fnsku_inventory_4 = 0  then 0
              when round(t1.fnsku_inventory_4/t2.sale_quantity_30,2)>=day_num then day_num
              else
       round(t1.fnsku_inventory_4/t2.sale_quantity_30,2) end as 'sale_fnsku_available_4',
          case
              when ifnull(t2.sale_quantity_30,0) =0 and t1.fnsku_inventory_5 != 0 then day_num
              when ifnull(t2.sale_quantity_30,0) =0 or t1.fnsku_inventory_5 = 0  then 0
              when round(t1.fnsku_inventory_5/t2.sale_quantity_30,2)>=day_num then day_num
              else
       round(t1.fnsku_inventory_5/t2.sale_quantity_30,2) end as 'sale_fnsku_available_5',
          case
              when ifnull(t2.sale_quantity_30,0) =0 and t1.fnsku_inventory_6 != 0 then day_num
              when ifnull(t2.sale_quantity_30,0) =0 or t1.fnsku_inventory_6 = 0  then 0
              when round(t1.fnsku_inventory_6/t2.sale_quantity_30,2)>=day_num then day_num
              else
       round(t1.fnsku_inventory_6/t2.sale_quantity_30,2) end as 'sale_fnsku_available_6',

    case
        when t2.sale_quantity_30 is null then '数据缺失'
        when t2. sale_quantity_30=0 and t1.fnsku_inventory_1 != 0 then '+∞'
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_1=0 then 0
        when round(t1.fnsku_inventory_1/t2.sale_quantity_30,2)>=day_num then CONCAT(day_num, '+')
        else
       round(t1.fnsku_inventory_1/t2.sale_quantity_30,2) end as 'sale_fnsku_available_str_1',
          case
              when t2.sale_quantity_30 is null then '数据缺失'
              when t2.sale_quantity_30=0 or t1.fnsku_inventory_1=0 then 0
              when t2.sale_quantity_30 =0 and t1.fnsku_inventory_2 != 0 then '+∞'
              when round(t1.fnsku_inventory_2/t2.sale_quantity_30,2)>=day_num then CONCAT(day_num, '+')
              else
       round(t1.fnsku_inventory_2/t2.sale_quantity_30,2) end as 'sale_fnsku_available_str_2',
          case
              when t2.sale_quantity_30 is null then '数据缺失'
              when t2.sale_quantity_30=0 or t1.fnsku_inventory_1=0 then 0
              when t2.sale_quantity_30 =0 and t1.fnsku_inventory_3 != 0 then '+∞'
              when round(t1.fnsku_inventory_3/t2.sale_quantity_30,2)>=day_num then CONCAT(day_num, '+')
              else
       round(t1.fnsku_inventory_3/t2.sale_quantity_30,2) end as 'sale_fnsku_available_str_3',
          case
              when t2.sale_quantity_30 is null then '数据缺失'
              when t2.sale_quantity_30=0 or t1.fnsku_inventory_1=0 then 0
              when t2.sale_quantity_30 =0 and t1.fnsku_inventory_4 != 0 then '+∞'
              when round(t1.fnsku_inventory_4/t2.sale_quantity_30,2)>=day_num then CONCAT(day_num, '+')
              else
       round(t1.fnsku_inventory_4/t2.sale_quantity_30,2) end as 'sale_fnsku_available_str_4',
          case
              when t2.sale_quantity_30 is null then '数据缺失'
              when t2.sale_quantity_30 =0 and t1.fnsku_inventory_5 != 0 then '+∞'
              when t2.sale_quantity_30=0 or t1.fnsku_inventory_1=0 then 0
              when round(t1.fnsku_inventory_5/t2.sale_quantity_30,2)>=day_num then CONCAT(day_num, '+')
              else
       round(t1.fnsku_inventory_5/t2.sale_quantity_30,2) end as 'sale_fnsku_available_str_5',
          case
              when t2.sale_quantity_30 is null then '数据缺失'
              when t2.sale_quantity_30 =0 and t1.fnsku_inventory_6 != 0 then '+∞'
              when t2.sale_quantity_30=0 or t1.fnsku_inventory_1=0 then 0
              when round(t1.fnsku_inventory_6/t2.sale_quantity_30,2)>=day_num then CONCAT(day_num, '+')
              else
       round(t1.fnsku_inventory_6/t2.sale_quantity_30,2) end as 'sale_fnsku_available_str_6',

    case
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_1=0 then 0
        when t2.sale_quantity_30 is null and t1.fnsku_inventory_1 != 0 or t1.FBA_delivery_time_fn is null or t1.fnsku_inventory_1/t2.sale_quantity_30>=day_num then day_num
        else
       round(t1.fnsku_inventory_1/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn,2) end as sale_fnsku_restocking_countdown_1,
    case
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_2=0 then 0
        when t2.sale_quantity_30 is null and t1.fnsku_inventory_2 != 0  or t1.FBA_delivery_time_fn is null or t1.fnsku_inventory_2/t2.sale_quantity_30>=day_num then day_num
        else
       round(t1.fnsku_inventory_2/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn,2) end as sale_fnsku_restocking_countdown_2,
    case
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_3=0 then 0
        when t2.sale_quantity_30 is null and t1.fnsku_inventory_3 != 0 or t1.FBA_delivery_time_fn is null or t1.fnsku_inventory_3/t2.sale_quantity_30>=day_num then day_num
        else
       round(t1.fnsku_inventory_3/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn,0) end as sale_fnsku_restocking_countdown_3,
    case
        when t2.sale_quantity_30=0  or t1.fnsku_inventory_4=0 then 0
        when t2.sale_quantity_30 is null and t1.fnsku_inventory_4 != 0 or t1.FBA_delivery_time_fn is null or t1.fnsku_inventory_4/t2.sale_quantity_30>=day_num then day_num
        else
       round(t1.fnsku_inventory_4/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn,0) end as sale_fnsku_restocking_countdown_4,
    case
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_5=0 then 0
        when t2.sale_quantity_30 is null and t1.fnsku_inventory_5 != 0  or t1.FBA_delivery_time_fn is null or t1.fnsku_inventory_5/t2.sale_quantity_30>=day_num then day_num
        else
       round(t1.fnsku_inventory_5/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn,0) end as sale_fnsku_restocking_countdown_5,
    case
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_6=0 then 0
        when t2.sale_quantity_30 is null and t1.fnsku_inventory_6 != 0  or t1.FBA_delivery_time_fn is null or t1.fnsku_inventory_6/t2.sale_quantity_30>=day_num then day_num
        else
       round(t1.fnsku_inventory_6/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn,0) end as sale_fnsku_restocking_countdown_6,

    case
        when t2.sale_quantity_30 is null or t1.FBA_delivery_time_fn is null then '数据缺失'
        when t2.sale_quantity_30=0 and t1.fnsku_inventory_1 != 0 then '+∞'
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_1=0 then 0
        when t1.fnsku_inventory_1/t2.sale_quantity_30>=day_num then CONCAT(day_num, '+')
        else round(t1.fnsku_inventory_1/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn,2) end as sale_fnsku_restocking_countdown_str_1,
    case
        when t2.sale_quantity_30 is null or t1.FBA_delivery_time_fn is null then '数据缺失'
        when t2.sale_quantity_30=0 and t1.fnsku_inventory_2 != 0 then '+∞'
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_2=0 then 0
        when t1.fnsku_inventory_2/t2.sale_quantity_30>=day_num then CONCAT(day_num, '+')
        else round(t1.fnsku_inventory_2/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn,2) end as sale_fnsku_restocking_countdown_str_2,
    case
        when t2.sale_quantity_30 is null or t1.FBA_delivery_time_fn is null then '数据缺失'
        when t2.sale_quantity_30=0 and t1.fnsku_inventory_3 != 0 then '+∞'
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_3=0 then 0
        when t1.fnsku_inventory_3/t2.sale_quantity_30>=day_num then CONCAT(day_num, '+')
        else round(t1.fnsku_inventory_3/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn,0) end as sale_fnsku_restocking_countdown_str_3,
    case
        when t2.sale_quantity_30 is null or t1.FBA_delivery_time_fn is null then '数据缺失'
        when t2.sale_quantity_30=0 and t1.fnsku_inventory_4 != 0 then '+∞'
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_4=0 then 0
        when t1.fnsku_inventory_4/t2.sale_quantity_30>=day_num then CONCAT(day_num, '+')
        else round(t1.fnsku_inventory_4/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn,0) end as sale_fnsku_restocking_countdown_str_4,
    case
        when t2.sale_quantity_30 is null or t1.FBA_delivery_time_fn is null then '数据缺失'
        when t2.sale_quantity_30=0 and t1.fnsku_inventory_5 != 0 then '+∞'
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_5=0 then 0
        when t1.fnsku_inventory_5/t2.sale_quantity_30>=day_num then CONCAT(day_num, '+')
        else round(t1.fnsku_inventory_5/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn,0) end as sale_fnsku_restocking_countdown_str_5,
    case
        when t2.sale_quantity_30 is null or t1.FBA_delivery_time_fn is null then '数据缺失'
        when t2.sale_quantity_30=0 and t1.fnsku_inventory_6 != 0 then '+∞'
        when t2.sale_quantity_30=0 or t1.fnsku_inventory_6=0 then 0
        when t1.fnsku_inventory_6/t2.sale_quantity_30>=day_num then CONCAT(day_num, '+')
        else round(t1.fnsku_inventory_6/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn,0) end as sale_fnsku_restocking_countdown_str_6,


       case when FBA_delivery_time_fn is null then '数据缺失'
                                          when fnsku_available_days_str_1='数据缺失' then '数据缺失'
            when fnsku_available_days_str_1=CONCAT(day_num, '+') or fnsku_available_days_str_1='+∞' THEN '安全'
            when fnsku_restocking_countdown_1<=-fba_safety_days_fn then '严重'
            when fnsku_restocking_countdown_1<=-0.5*fba_safety_days_fn then '中等'
            when fnsku_restocking_countdown_1<=0 then '轻微'
            else '安全' end as fnsku_out_of_stock_risk_1,
        case when FBA_delivery_time_fn is null then '数据缺失'
                                                          when fnsku_available_days_str_2='数据缺失' then '数据缺失'
                when fnsku_available_days_str_2=CONCAT(day_num, '+') or fnsku_available_days_str_2='+∞'  THEN '安全'
                when fnsku_restocking_countdown_2<=-fba_safety_days_fn then '严重'
                when fnsku_restocking_countdown_2<=-0.5*fba_safety_days_fn then '中等'
                when fnsku_restocking_countdown_2<=0 then '轻微'
                else '安全' end as fnsku_out_of_stock_risk_2,
        case when FBA_delivery_time_fn is null then '数据缺失'
                                                  when fnsku_available_days_str_3='数据缺失' then '数据缺失'
                when fnsku_available_days_str_3=CONCAT(day_num, '+') or fnsku_available_days_str_3='+∞'  THEN '安全'
                when fnsku_restocking_countdown_3<=-(fba_safety_days_fn+overseas_warehouse_safety_days) then '严重'
                when fnsku_restocking_countdown_3<=-0.5*(fba_safety_days_fn+overseas_warehouse_safety_days) then '中等'
                when fnsku_restocking_countdown_3<=0 then '轻微'
                else '安全' end as fnsku_out_of_stock_risk_3,
        case         when FBA_delivery_time_fn is null then '数据缺失'
                                                                          when fnsku_available_days_str_4='数据缺失' then '数据缺失'
                    when fnsku_available_days_str_4=CONCAT(day_num, '+') or fnsku_available_days_str_4='+∞'  THEN '安全'
                    when fnsku_restocking_countdown_4<=-(fba_safety_days_fn+overseas_warehouse_safety_days) then '严重'
                    when fnsku_restocking_countdown_4<=-0.5*(fba_safety_days_fn+overseas_warehouse_safety_days) then '中等'
                    when fnsku_restocking_countdown_4<=0 then '轻微'
                    else '安全' end as fnsku_out_of_stock_risk_4,
        case when FBA_delivery_time_fn is null then '数据缺失'
                                                  when fnsku_available_days_str_5='数据缺失' then '数据缺失'
                    when fnsku_available_days_str_5=CONCAT(day_num, '+') or fnsku_available_days_str_5='+∞'  THEN '安全'
                    when fnsku_restocking_countdown_5<=-(fba_safety_days_fn+overseas_warehouse_safety_days) then '严重'
                    when fnsku_restocking_countdown_5<=-0.5*(fba_safety_days_fn+overseas_warehouse_safety_days) then '中等'
                    when fnsku_restocking_countdown_5<=0 then '轻微'
                    else '安全' end as fnsku_out_of_stock_risk_5,
        case when FBA_delivery_time_fn is null then '数据缺失'
                                                                          when fnsku_available_days_str_6='数据缺失' then '数据缺失'
                    when fnsku_available_days_str_6=CONCAT(day_num, '+') or fnsku_available_days_str_6='+∞'  THEN '安全'
                    when fnsku_restocking_countdown_6<=-(fba_safety_days_fn+overseas_warehouse_safety_days+local_warehouse_safety_days) then '严重'
                    when fnsku_restocking_countdown_6<=-0.5*(fba_safety_days_fn+overseas_warehouse_safety_days+local_warehouse_safety_days) then '中等'
                    when fnsku_restocking_countdown_6<=0 then '轻微'
                    else '安全' end as fnsku_out_of_stock_risk_6,

        case
            when t1.FBA_delivery_time_fn is null then '数据缺失'
            when coalesce(t2.sale_quantity_30,0) = 0  then '安全'
            when coalesce(t2.sale_quantity_30,0) + coalesce(t1.fnsku_inventory_1,0) =0 then '安全'
            when t1.fnsku_inventory_1/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn>0 then '安全'
            when t1.fnsku_inventory_1/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn<=-fba_safety_days_fn then '严重'
            when t1.fnsku_inventory_1/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn<=-0.5*fba_safety_days_fn then '中等'
            when t1.fnsku_inventory_1/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn<=0 then '轻微'
            else '异常' end as sale_fnsku_out_of_stock_risk_1,
        case
            when t1.FBA_delivery_time_fn is null then '数据缺失'
            when coalesce(t2.sale_quantity_30,0) = 0 then '安全'
            when coalesce(t2.sale_quantity_30,0) + coalesce(t1.fnsku_inventory_2,0) =0 then '安全'
            when t1.fnsku_inventory_2/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn>0 then '安全'
                when t1.fnsku_inventory_2/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn<=-fba_safety_days_fn then '严重'
                when t1.fnsku_inventory_2/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn<=-0.5*fba_safety_days_fn then '中等'
                when t1.fnsku_inventory_2/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn<=0 then '轻微'
                else '异常' end as sale_fnsku_out_of_stock_risk_2,
        case
            when t1.FBA_delivery_time_fn is null then '数据缺失'
            when coalesce(t2.sale_quantity_30,0) = 0 then '安全'
                when coalesce(t2.sale_quantity_30,0) + coalesce(t1.fnsku_inventory_3,0)=0 then '安全'
                when t1.fnsku_inventory_3/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn>0 then '安全'
                when t1.fnsku_inventory_3/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn<=-(fba_safety_days_fn+overseas_warehouse_safety_days) then '严重'
                when t1.fnsku_inventory_3/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn<=-0.5*(fba_safety_days_fn+overseas_warehouse_safety_days) then '中等'
                when t1.fnsku_inventory_3/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn<=0 then '轻微'
                else '异常' end as sale_fnsku_out_of_stock_risk_3,
        case
            when t1.FBA_delivery_time_fn is null then '数据缺失'
            when coalesce(t2.sale_quantity_30,0) = 0  then '安全'
            when coalesce(t2.sale_quantity_30,0) + coalesce(t1.fnsku_inventory_4,0) =0 then '安全'
            when t1.fnsku_inventory_3/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn>0 then '安全'
                    when t1.fnsku_inventory_4/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn<=-(fba_safety_days_fn+overseas_warehouse_safety_days) then '严重'
                    when t1.fnsku_inventory_4/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn<=-0.5*(fba_safety_days_fn+overseas_warehouse_safety_days) then '中等'
                    when t1.fnsku_inventory_4/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn<=0 then '轻微'
                    else '异常' end as sale_fnsku_out_of_stock_risk_4,
        case
            when t1.FBA_delivery_time_fn is null then '数据缺失'
            when coalesce(t2.sale_quantity_30,0) = 0 then '安全'
            when coalesce(t2.sale_quantity_30,0) + coalesce(t1.fnsku_inventory_5,0) =0 then '安全'
            when t1.fnsku_inventory_5/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn>0 then '安全'
                    when t1.fnsku_inventory_5/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn<=-(fba_safety_days_fn+overseas_warehouse_safety_days) then '严重'
                    when t1.fnsku_inventory_5/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn<=-0.5*(fba_safety_days_fn+overseas_warehouse_safety_days) then '中等'
                    when t1.fnsku_inventory_5/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn<=0 then '轻微'
                    else '异常' end as sale_fnsku_out_of_stock_risk_5,
        case
            when t1.FBA_delivery_time_fn is null then '数据缺失'
            when coalesce(t2.sale_quantity_30,0) = 0 then '安全'
            when coalesce(t2.sale_quantity_30,0) + coalesce(t1.fnsku_inventory_6,0) =0 then '安全'
            when t1.fnsku_inventory_5/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn>0 then '安全'
                    when t1.fnsku_inventory_6/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn<=-(fba_safety_days_fn+overseas_warehouse_safety_days+local_warehouse_safety_days) then '严重'
                    when t1.fnsku_inventory_6/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn<=-0.5*(fba_safety_days_fn+overseas_warehouse_safety_days+local_warehouse_safety_days) then '中等'
                    when t1.fnsku_inventory_6/t2.sale_quantity_30-t1.FBA_delivery_time_fn-t1.fba_safety_days_fn-overseas_warehouse_safety_days-overseas_warehouse_delivery_time_fn-local_warehouse_safety_days-local_warehouse_delivery_time_fn<=0 then '轻微'
                    else '异常' end as sale_fnsku_out_of_stock_risk_6

from temp_buhuo_fnsku_zjg t1 left join temp_lingxing_fnsku_quantity t2 on
t1.fnsku=t2.fnsku and lower(t1.store_name)=lower(t2.store_name) and t1.msku = t2.msku;


-- 批次库存叠加
DROP TABLE IF EXISTS temp_lingxing_kucu_pici;

CREATE TABLE temp_lingxing_kucu_pici as
WITH
pici_type AS (
    SELECT
        FNSKU,
        store_name,
        estimated_shelf_life as put_date,
        quantity_receive ship_num,
        type
    FROM dim_lingxing_lot_tracking_new t1
    WHERE estimated_shelf_life >CURDATE()
),

-- ① 批次排序
pici_paixu AS (
    SELECT
        FNSKU,
        store_name,
        put_date AS 到货日期,
        ship_num AS 到货量,
        LEAD(put_date, 1, '2099-12-31') OVER (PARTITION BY FNSKU, store_name,type ORDER BY put_date) AS 下批日期,
        type,
        ROW_NUMBER() OVER (PARTITION BY FNSKU, store_name,type ORDER BY put_date) AS rn
    FROM (select sum(ship_num) ship_num,fnsku,store_name,type,put_date from pici_type where put_date>=CURRENT_DATE() group by fnsku,store_name,type,put_date ) t
),

-- ② 当前库存叠加到首批
初始批次 AS (
    SELECT
        p.FNSKU,
        p.store_name,
        p.到货日期,
        p.到货量,
        CASE WHEN type='FBA仓' THEN COALESCE(w.fnsku_inventory_1, 0)
        WHEN type='海外仓' THEN COALESCE(w.fnsku_inventory_3, 0)
        WHEN type='本地仓' THEN COALESCE(w.fnsku_inventory_5, 0)
            ELSE 0 END AS 当前库存,
        p.下批日期,
        CASE WHEN type='FBA仓' THEN COALESCE(w.fnsku_inventory_1, 0) + p.到货量
        WHEN type='海外仓' THEN COALESCE(w.fnsku_inventory_3, 0) + p.到货量
        WHEN type='本地仓' THEN COALESCE(w.fnsku_inventory_5, 0) + p.到货量
            ELSE 0 END AS 起始库存,
        p.type
    FROM pici_paixu p
    LEFT JOIN temp_kucun_fnsku_zgb w
        ON p.FNSKU = w.FNSKU AND p.store_name = w.store_name
),

-- ③ 计算每个批次区间内的销量
批次销量 AS (
    SELECT
        t1.FNSKU,
        t1.store_name,
        t1.到货日期,
        t1.下批日期,
        case when t1.下批日期='2099-12-31' then 0
        else SUM(COALESCE(t2.daily_sales_quantity, 0)) end AS 批次销量,
        t1.type
    FROM 初始批次 t1
    LEFT JOIN dim_lingxing_sales_estimates t2
        ON t1.FNSKU = t2.FNSKU
        AND t1.store_name = t2.store_name
        AND t2.date >= t1.到货日期
        AND t2.date <  t1.下批日期
    GROUP BY t1.FNSKU, t1.store_name,t1.type, t1.到货日期, t1.下批日期
),
latest_batch AS (
    SELECT
        FNSKU,
        store_name,
        min(put_date) AS 最新批次日期,
        type
    FROM pici_type
    GROUP BY FNSKU, store_name,type
),
temp_one as (
SELECT
    t2.fnsku AS FNSKU,
    t2.store_name,
    CURRENT_DATE() AS 统计日期,
    最新批次日期,
    SUM(t2.daily_sales_quantity) AS 销量和,
    type
FROM dim_lingxing_sales_estimates t2
INNER JOIN latest_batch lb
    ON t2.fnsku = lb.FNSKU
   AND t2.store_name = lb.store_name
WHERE t2.date BETWEEN CURRENT_DATE() AND lb.最新批次日期
GROUP BY t2.fnsku, t2.store_name,lb.type, CURRENT_DATE(),最新批次日期
ORDER BY t2.fnsku, t2.store_name,lb.type)

SELECT
a.FNSKU,
a.store_name,
CAST(a.到货日期 AS CHAR) put_date,
a.到货量 put_num,
c.销量和 sale_num,
b.批次销量 batch_num,
CASE
    WHEN c.销量和 AND a.当前库存 - c.销量和 > 0 THEN a.当前库存 - c.销量和
    ELSE 0
END AS day_kucun,
CASE
    WHEN c.销量和 AND a.当前库存 - c.销量和 > 0 THEN a.当前库存 - c.销量和 + a.到货量
    WHEN c.销量和 AND a.当前库存 - c.销量和 <= 0 THEN a.到货量
    ELSE 0
END AS jieyu_kucun,
    a.type
FROM 初始批次 a
LEFT JOIN 批次销量 b
ON a.FNSKU = b.FNSKU
AND a.store_name = b.store_name
AND a.到货日期 = b.到货日期
and a.type=b.type
LEFT JOIN temp_one c
ON a.store_name = c.store_name
AND a.FNSKU = c.FNSKU
and a.type=c.type
AND a.到货日期 = c.最新批次日期;