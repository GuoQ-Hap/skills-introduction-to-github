import { useMemo, useState } from 'react';
import {
  Alert, Button, Card, Col, Input, Row, Select, Statistic, Table, Tabs, Tag, Typography, Upload, message,
} from 'antd';
import {
  AlertOutlined, CheckCircleOutlined, DatabaseOutlined, FileExcelOutlined, ReloadOutlined, SafetyCertificateOutlined,
  SearchOutlined, WarningOutlined,
} from '@ant-design/icons';
import { UploadOutlined } from '@ant-design/icons';
import api, { type SQLExecResponse } from '../api';

const { Text, Title } = Typography;

type Row = Record<string, any>;

interface InventoryRow extends Row {
  key: string;
  warning_type: '断货预警' | '冗余库存' | '库存异常' | '正常';
  risk_level: '高' | '中' | '低' | '正常';
  sellable_days: number | null;
  total_inventory: number;
  lead_time_days: number;
  forecast_30d_sales_checked: number;
  actual_30d_sales: number;
  in_transit_qty_checked: number;
  fba_inventory_checked: number | null;
  validation_status: string;
  validation_notes: string;
  suggested_action: string;
}

const n = (v: any) => Number(v ?? 0);
const round = (v: number, d = 1) => Number.isFinite(v) ? Number(v.toFixed(d)) : 0;
const esc = (v: string) => v.replace(/'/g, "''").trim();

function valueOr<T>(...values: T[]) {
  return values.find(v => v !== undefined && v !== null && v !== '') ?? '';
}

function numOr(...values: any[]) {
  const value = valueOr(...values);
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function numOptional(value: any) {
  if (value === undefined || value === null || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function qtyDiff(calculated: number | null, source: number | null) {
  if (calculated == null || source == null) return null;
  return round(calculated - source, 2);
}

function qtyCheck(label: string, calculated: number | null, source: number | null, tolerance = 0.05) {
  if (source == null) return `${label}底表缺失`;
  if (calculated == null) return `${label}无法复算`;
  const diff = Math.abs(calculated - source);
  return diff <= tolerance ? `${label}一致` : `${label}不一致`;
}

function deriveSalesForAdjustment(sourceAdjustment: number | null, m3: number | null, safetyQty: number, oversellRate: number) {
  if (sourceAdjustment == null || m3 == null || !oversellRate) return null;
  return round((sourceAdjustment + m3 - safetyQty) / oversellRate, 2);
}

function classifyProductSize(size: any, skuName: any, msku: any) {
  const text = `${size ?? ''} ${skuName ?? ''} ${msku ?? ''}`.toLowerCase();
  const inchMatch = text.match(/(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)/);
  if (inchMatch) {
    const a = Number(inchMatch[1]);
    const b = Number(inchMatch[2]);
    if (Number.isFinite(a) && Number.isFinite(b) && Math.max(a, b) >= 180) return '大件';
  }
  if (/(8x10|9x12|6x9|5x7|large|oversize|大件)/i.test(text)) return '大件';
  return '标准件';
}

function transparentPlanStatus(row: Row) {
  return String(row.msku_isattract || row.transparent_plan_status || '').includes('参与') ? '参与' : '未参与';
}

function ratioOr(...values: any[]) {
  const numeric = numOr(...values);
  return numeric > 1 ? numeric / 100 : numeric;
}

function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + Math.ceil(days));
  return next;
}

function calcOrderDate(today: Date, countdown: number, frequency: number) {
  if (frequency > 0 && countdown >= frequency) return null;
  return addDays(today, Math.max(countdown, 0));
}

function formatStamp(date = new Date()) {
  const pad = (v: number) => String(v).padStart(2, '0');
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}`;
}

function dateKey(value: any) {
  if (!value) return '';
  if (value instanceof Date) {
    const pad = (v: number) => String(v).padStart(2, '0');
    return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
  }
  return String(value).slice(0, 10);
}

function dateOnly(value: any) {
  const key = dateKey(value);
  const [year, month, day] = key.split('-').map(Number);
  if (!year || !month || !day) return new Date();
  return new Date(year, month - 1, day);
}

function nextFridayOnOrAfter(date: Date) {
  const day = date.getDay();
  const daysUntilFriday = (5 - day + 7) % 7;
  return addDays(date, daysUntilFriday);
}

function weekStartMonday(date: Date) {
  const next = new Date(date);
  const day = next.getDay() || 7;
  next.setDate(next.getDate() - day + 1);
  next.setHours(0, 0, 0, 0);
  return next;
}

function isSameNaturalWeek(a: Date | null, b: Date | null) {
  if (!a || !b) return false;
  return weekStartMonday(a).getTime() === weekStartMonday(b).getTime();
}

const DEFAULT_VALIDATION_DATE = dateKey(new Date());
const INVENTORY_BASE_TABLE = 'ads_lingxing_all_warehouse_new_v1';
const DEFAULT_HALF_BOX_SUPPLIERS = 'C01,L01,C32';
const DEFAULT_COVERAGE_END_DATE = '';

function shipmentPlanHeaders(shipDates: Date[]) {
  return [
    'PMC', '店铺MSKUFNSKU', '销售部门', '销售员', '店铺', 'MSKU', 'FNSKU', 'ASIN', 'SKU', '品名',
    '产品尺寸', '父ASIN', '产品经理', '国家', '渠道', '品牌', 'seller_id', '发货国家', '区域', 'colour',
    '色系', 'size', 'MSKU销售属性', 'MSKU产品属性', '是否为引流MSKU', '季节属性', 'MSKU销售状态', 'MSKU生命周期',
    '￥销售单价', '$销售单价', '物流模式', '头程物流渠道', '下单时长', '生产时长', '本地仓出库时长', '海外仓出库时长',
    '本地仓到FBA仓时长', '本地仓到海外仓时长', '海外仓到FBA仓时长', '可超卖比例', '销售安全库存', '销售安全库存天数',
    '物流安全库存天数', '生产安全库存天数', 'FBA安全天数_fnsku', '海外仓安全天数_fnsku', '本地仓安全天数_fnsku',
    'FBA交付时长_fnsku', '海外仓交付时长_fnsku', '本地仓交付时长_fnsku', 'FBA可售', '待调仓', '调仓中',
    '入库中', '实际在途', '计划入库', '发货计划量', '海外仓待检待上架', '海外仓调拨在途', '海外仓计划量',
    '本地仓待检待上架', '本地仓调拨在途', '待到货量', '采购计划量', 'FBA仓_FNSKU', '海外仓_FNSKU',
    '海外仓在途_FNSKU', '本地仓_FNSKU', '本地仓在途_FNSKU', '90天毛利率', '库存1_FNSKU', '库存2_FNSKU',
    '库存3_FNSKU', '库存4_FNSKU', '库存5_FNSKU', '库存6_FNSKU', '可售天数1_FNSKU', '可售天数2_FNSKU',
    '可售天数3_FNSKU', '可售天数4_FNSKU', '可售天数5_FNSKU', '可售天数6_FNSKU', '补货倒计时1_FNSKU',
    '补货倒计时2_FNSKU', '补货倒计时3_FNSKU', '补货倒计时4_FNSKU', '补货倒计时5_FNSKU', '补货倒计时6_FNSKU',
    '断货风险1_FNSKU', '断货风险2_FNSKU', '断货风险3_FNSKU', '断货风险4_FNSKU', '断货风险5_FNSKU',
    '断货风险6_FNSKU', 'FBA库龄1~30天', 'FBA库龄31~60天', 'FBA库龄61~90天', 'FBA库龄91~180天',
    'FBA库龄181~270天', 'FBA库龄271~330天', 'FBA库龄331~365天', 'FBA库龄365', '7天历史日均销量',
    '14天历史日均销量', '30天历史日均销量', '60天历史日均销量', '90天历史日均销量', '同期30天销量',
    '同期60天销量', '同期90天销量', '可售天数1_FNSKU_历史销量', '可售天数2_FNSKU_历史销量',
    '可售天数3_FNSKU_历史销量', '可售天数4_FNSKU_历史销量', '可售天数5_FNSKU_历史销量',
    '可售天数6_FNSKU_历史销量', 'sale_fnsku_available_str_1', 'sale_fnsku_available_str_2',
    'sale_fnsku_available_str_3', 'sale_fnsku_available_str_4', 'sale_fnsku_available_str_5',
    'sale_fnsku_available_str_6', '历史补货倒计时1_FNSKU', '历史补货倒计时2_FNSKU',
    '历史补货倒计时3_FNSKU', '历史补货倒计时4_FNSKU', '历史补货倒计时5_FNSKU',
    '历史补货倒计时6_FNSKU', 'sale_fnsku_restocking_countdown_str_1', 'sale_fnsku_restocking_countdown_str_2',
    'sale_fnsku_restocking_countdown_str_3', 'sale_fnsku_restocking_countdown_str_4',
    'sale_fnsku_restocking_countdown_str_5', 'sale_fnsku_restocking_countdown_str_6',
    '历史断货风险1_FNSKU', '历史断货风险2_FNSKU', '历史断货风险3_FNSKU', '历史断货风险4_FNSKU',
    '历史断货风险5_FNSKU', '历史断货风险6_FNSKU', '15天预估销量', '30天预估销量', '45天预估销量',
    '60天预估销量', '75天预估销量', '90天预估销量', '基础采购量', '采购T2', '采购T3', '采购修正量',
    '采购参考', '销售确认（采购量）', `${dateKey(shipDates[0])}货好`, `${dateKey(shipDates[1])}货好`,
    `${dateKey(shipDates[2])}货好`, '回仓', '国内总库存', '待配货', '发货结余库存', '供应商', '单箱数',
    '发货T0', '发货T1', '发货T2', '发货T3', '基础发货量', '发货修正量', '建议发货量', '整箱发货量',
    '待配货量', '首批退回', '退回备注', '发货差异', `${dateKey(shipDates[0])}美森`,
    `${dateKey(shipDates[1])}美森`, `${dateKey(shipDates[2])}美森`, `${dateKey(shipDates[0])}普船`,
    `${dateKey(shipDates[1])}普船`, `${dateKey(shipDates[2])}普船`, `${dateKey(shipDates[0])}合计`,
    `${dateKey(shipDates[1])}合计`, `${dateKey(shipDates[2])}合计`, '合计总发货数量', '计划备注',
    `${dateKey(shipDates[0])}美森（销售）`, `${dateKey(shipDates[1])}美森（销售）`,
    `${dateKey(shipDates[2])}美森（销售）`, `${dateKey(shipDates[0])}普船（销售）`,
    `${dateKey(shipDates[1])}普船（销售）`, `${dateKey(shipDates[2])}普船（销售）`,
    `${dateKey(shipDates[0])}合计（销售）`, `${dateKey(shipDates[1])}合计（销售）`,
    `${dateKey(shipDates[2])}合计（销售）`, '合计总发货数量（销售）', '修改备注', '备注',
  ];
}

function normalizeKeyPart(value: any) {
  return String(value ?? '').trim().toLowerCase();
}

function ruleKey(storeName: any, sku: any, msku: any, fnsku: any) {
  return [storeName, sku, msku, fnsku].map(normalizeKeyPart).join('|');
}

interface StockRule {
  shipmentsFrequency: number;
  restockingFrequency: number;
  logisticsModel: string;
  firstLegChannel: string;
  nextOversellRate: number;
  currentLogisticsSafetyDays: number;
  nextLogisticsSafetyDays: number;
  currentFbaDeliveryDays: number;
  nextFbaDeliveryDays: number;
}

function styleFilterClause(style: string, tableAlias = '') {
  const col = tableAlias ? `${tableAlias}.msku_sales_property` : 'msku_sales_property';
  if (!style || style === 'all') return '';
  if (style === 'other') {
    return ` AND (${col} IS NULL OR ${col} = '' OR (${col} NOT LIKE '%爆%' AND ${col} NOT LIKE '%旺%' AND ${col} NOT LIKE '%平%' AND ${col} NOT LIKE '%滞%'))`;
  }
  return ` AND ${col} LIKE '%${esc(style)}%'`;
}

function sqlFilter(msku: string, storeName: string, style: string, tableAlias = '') {
  const col = (name: string) => tableAlias ? `${tableAlias}.${name}` : name;
  const parts: string[] = [];
  if (msku.trim()) parts.push(`${col('msku')} LIKE '%${esc(msku)}%'`);
  if (storeName.trim()) parts.push(`${col('store_name')} LIKE '%${esc(storeName)}%'`);
  return (parts.length ? ` AND ${parts.join(' AND ')}` : '') + styleFilterClause(style, tableAlias);
}

async function runSql(sql: string): Promise<SQLExecResponse> {
  const timeout = new Promise<never>((_, reject) => {
    window.setTimeout(() => reject(new Error('SQL请求超时，请缩小筛选条件或稍后重试')), 90000);
  });
  const response = await Promise.race([api.post<SQLExecResponse>('/lda/sql', { sql }), timeout]);
  const { data } = response;
  if (data.error) throw new Error(data.error);
  return data;
}

async function fetchM3Rows(tableName: 'dim_inventory_forecast_v1' | 'dim_inventory_forecast_v1_fh', keys: Array<{ fnsku: any; storeName: any; date: any }>) {
  const grouped = new Map<string, Set<string>>();
  keys.forEach(({ fnsku, storeName, date }) => {
    const dateValue = dateKey(date);
    if (!fnsku || !storeName || !dateValue) return;
    const key = `${fnsku}|${storeName}`;
    const dates = grouped.get(key) || new Set<string>();
    dates.add(dateValue);
    grouped.set(key, dates);
  });

  if (!grouped.size) return [];

  const conditions = Array.from(grouped.entries()).map(([key, dates]) => {
    const [fnsku, storeName] = key.split('|');
    const dateList = Array.from(dates).map(date => `'${esc(date)}'`).join(',');
    return `(f.FNSKU = '${esc(fnsku)}' AND f.store_name = '${esc(storeName)}' AND f.forecast_date IN (${dateList}))`;
  });

  const rows: Row[] = [];
  const chunkSize = 200;
  for (let i = 0; i < conditions.length; i += chunkSize) {
    const chunk = conditions.slice(i, i + chunkSize);
    const result = await runSql(`
SELECT
  f.forecast_date,
  f.FNSKU AS fnsku,
  f.store_name,
  f.ending_inventory
FROM ${tableName} f
WHERE ${chunk.join(' OR ')}`);
    rows.push(...result.rows);
  }
  return rows;
}

async function fetchForecastRows(tableName: 'dim_inventory_forecast_v1' | 'dim_inventory_forecast_v1_fh', rowsToFetch: Row[], startDate: string) {
  const keySet = new Set<string>();
  rowsToFetch.forEach(row => {
    if (row.fnsku && row.store_name) keySet.add(`${row.fnsku}|${row.store_name}`);
  });
  const keys = Array.from(keySet);
  if (!keys.length) return [];

  const rows: Row[] = [];
  const chunkSize = 200;
  for (let i = 0; i < keys.length; i += chunkSize) {
    const chunk = keys.slice(i, i + chunkSize);
    const conditions = chunk.map(key => {
      const [fnsku, storeName] = key.split('|');
      return `(f.FNSKU = '${esc(fnsku)}' AND f.store_name = '${esc(storeName)}')`;
    });
    const result = await runSql(`
SELECT
  f.forecast_date,
  f.FNSKU AS fnsku,
  f.store_name,
  f.expected_sales,
  f.ending_inventory
FROM ${tableName} f
WHERE f.forecast_date >= '${esc(startDate)}'
  AND f.forecast_date <= date_add('${esc(startDate)}', interval 180 day)
  AND (${conditions.join(' OR ')})`);
    rows.push(...result.rows);
  }
  return rows;
}

function scopedChunkRanges(rowCount: number, chunkSize = 200) {
  const ranges: Array<[number, number]> = [];
  for (let start = 1; start <= rowCount; start += chunkSize) {
    ranges.push([start, Math.min(start + chunkSize - 1, rowCount)]);
  }
  return ranges;
}

function scopedChunkCte(baseFilter: string, start: number, end: number, columns: string) {
  return `
WITH scope_all AS (
  SELECT DISTINCT ${columns}
  FROM ${INVENTORY_BASE_TABLE} b
  WHERE 1 = 1${baseFilter}
),
scope AS (
  SELECT *
  FROM (
    SELECT scope_all.*, row_number() OVER (ORDER BY ${columns}) AS rn
    FROM scope_all
  ) numbered_scope
  WHERE rn BETWEEN ${start} AND ${end}
)`;
}

async function fetchDailyForecastRows(rowCount: number, startDate: string, baseFilter: string) {
  const ranges = scopedChunkRanges(rowCount);
  const rows: Row[] = [];
  for (const [start, end] of ranges) {
    const result = await runSql(`
${scopedChunkCte(baseFilter, start, end, 'msku, fnsku, store_name')}
SELECT
  f.msku, f.fnsku, f.store_name,
  min(f.date) AS forecast_start_date,
  max(f.date) AS forecast_end_date,
  count(*) AS forecast_days,
  sum(f.daily_sales_quantity) AS forecast_daily_30d_sales
FROM dim_lingxing_sales_estimates_everyday_incr f
INNER JOIN scope s
  ON f.msku = s.msku
  AND f.fnsku = s.fnsku
  AND f.store_name = s.store_name
WHERE f.date >= '${esc(startDate)}'
  AND f.date < date_add('${esc(startDate)}', interval 30 day)
GROUP BY f.msku, f.fnsku, f.store_name`);
    rows.push(...result.rows);
  }
  return rows;
}

async function fetchActualRows(rowCount: number, baseDate: string, baseFilter: string) {
  const ranges = scopedChunkRanges(rowCount);
  const rows: Row[] = [];
  for (const [start, end] of ranges) {
    const result = await runSql(`
${scopedChunkCte(baseFilter, start, end, 'msku, store_name')}
SELECT
  a.price_list_seller_sku AS msku,
  a.store_name,
  sum(CASE WHEN a.date >= date_sub('${esc(baseDate)}', interval 7 day) THEN a.volume ELSE 0 END) AS actual_7d_sales,
  sum(a.volume) AS actual_30d_sales,
  max(a.date) AS latest_actual_date,
  sum(CASE WHEN a.date >= date_sub('${esc(baseDate)}', interval 7 day) THEN a.spend ELSE 0 END) AS ad_spend_7d,
  sum(CASE WHEN a.date >= date_sub('${esc(baseDate)}', interval 7 day) THEN a.promotion_volume ELSE 0 END) AS promotion_volume_7d
FROM ads_lingxing_sc_sales_daily_new a
INNER JOIN scope s
  ON a.price_list_seller_sku = s.msku
  AND a.store_name = s.store_name
WHERE a.date >= date_sub('${esc(baseDate)}', interval 30 day)
  AND a.date < date_add('${esc(baseDate)}', interval 1 day)
GROUP BY a.price_list_seller_sku, a.store_name`);
    rows.push(...result.rows);
  }
  return rows;
}

async function fetchTransitRows(rowCount: number, baseFilter: string) {
  const ranges = scopedChunkRanges(rowCount);
  const rows: Row[] = [];
  for (const [start, end] of ranges) {
    const result = await runSql(`
${scopedChunkCte(baseFilter, start, end, 'msku, fnsku, store_name')}
SELECT
  t.msku, t.fnsku, t.store_name,
  sum(t.in_transit_qty) AS in_transit_qty_checked,
  min(t.estimated_shelf_date) AS next_estimated_shelf_date,
  max(t.total_delay_days) AS max_delay_days,
  max(t.exception) AS logistics_exception
FROM in_transit_shipment t
INNER JOIN scope s
  ON t.msku = s.msku
  AND t.fnsku = s.fnsku
  AND t.store_name = s.store_name
WHERE coalesce(t.in_transit_qty, 0) > 0
GROUP BY t.msku, t.fnsku, t.store_name`);
    rows.push(...result.rows);
  }
  return rows;
}

async function fetchFbaRows(rowCount: number, baseDate: string, baseFilter: string) {
  const ranges = scopedChunkRanges(rowCount);
  const rows: Row[] = [];
  for (const [start, end] of ranges) {
    const result = await runSql(`
${scopedChunkCte(baseFilter, start, end, 'msku, fnsku')},
latest AS (
  SELECT max(date) AS max_date
  FROM dwd_lingxing_fba_warehouse_detail
  WHERE date <= '${esc(baseDate)}'
)
SELECT
  d.seller_sku AS msku,
  d.fnsku,
  sum(d.afn_fulfillable_quantity) AS fba_inventory_checked,
  sum(d.afn_inbound_shipped_quantity) AS fba_inbound_shipped_checked,
  sum(d.afn_inbound_receiving_quantity) AS fba_receiving_checked,
  sum(d.afn_unsellable_quantity) AS fba_unsellable_checked
FROM dwd_lingxing_fba_warehouse_detail d
INNER JOIN scope s
  ON d.seller_sku = s.msku
  AND d.fnsku = s.fnsku
WHERE d.date = (SELECT max_date FROM latest)
GROUP BY d.seller_sku, d.fnsku`);
    rows.push(...result.rows);
  }
  return rows;
}

async function fetchDomesticInventoryRows(rowCount: number, baseFilter: string) {
  const ranges = scopedChunkRanges(rowCount);
  const rows: Row[] = [];
  for (const [start, end] of ranges) {
    const result = await runSql(`
${scopedChunkCte(baseFilter, start, end, 'sku, fnsku')},
inv_latest AS (
  SELECT max(date) AS max_date FROM dwd_lingxing_inventory_details
),
wh_latest AS (
  SELECT max(date) AS max_date FROM dwd_lingxing_sc_warehouse
)
SELECT
  inv.date,
  inv.sku,
  inv.fnsku,
  inv.seller_id,
  inv.wid,
  wh.name AS warehouse_name,
  wh.type AS warehouse_system_type,
  wm.type AS warehouse_business_type,
  inv.product_total,
  inv.product_valid_num,
  inv.product_qc_num,
  inv.product_lock_num,
  inv.quantity_receive,
  inv.product_onway,
  inv.available_inventory_box_qty
FROM dwd_lingxing_inventory_details inv
INNER JOIN scope s
  ON inv.sku = s.sku
  AND inv.fnsku = s.fnsku
LEFT JOIN dwd_lingxing_sc_warehouse wh
  ON inv.wid = wh.wid
  AND wh.date = (SELECT max_date FROM wh_latest)
LEFT JOIN dim_lingxing_warehouse_mapping wm
  ON wh.name = wm.name
WHERE inv.date = (SELECT max_date FROM inv_latest)`);
    rows.push(...result.rows);
  }
  return rows;
}

async function fetchInventoryLockRows(rowCount: number, baseFilter: string, baseDate: string) {
  const ranges = scopedChunkRanges(rowCount);
  const rows: Row[] = [];
  for (const [start, end] of ranges) {
    const result = await runSql(`
${scopedChunkCte(baseFilter, start, end, 'asin, sku, fnsku')}
SELECT
  s.asin,
  s.sku,
  s.fnsku,
  sum(coalesce(inv.product_lock_num, 0)) AS product_lock_num,
  sum(coalesce(inv.good_lock_num, 0)) AS good_lock_num
FROM scope s
LEFT JOIN ods_lingxing_inventory_details inv
  ON inv.sku = s.sku
  AND (inv.fnsku = s.fnsku OR inv.fnsku IS NULL OR inv.fnsku = '')
  AND inv.date = '${esc(baseDate)}'
GROUP BY s.asin, s.sku, s.fnsku`);
    rows.push(...result.rows);
  }
  return rows;
}

async function fetchPendingShipmentRows(baseDate: string) {
  const result = await runSql(`
SELECT
  date,
  shipment_sn,
  relate_list
FROM dwd_lingxing_inbound_shipment_list_incr
WHERE status = -1
  AND is_delete = 0
  AND date BETWEEN date_sub('${esc(baseDate)}', interval 7 day) AND date_add('${esc(baseDate)}', interval 7 day)`);
  return result.rows;
}

function pendingKey(row: Row) {
  return `${row.asin || ''}|${row.fnsku || ''}|${row.sku || ''}`;
}

function buildPendingShipmentMap(rows: Row[], planSourceRows: Row[]) {
  const byAsin = new Map<string, string[]>();
  const byFnsku = new Map<string, string[]>();
  planSourceRows.forEach(row => {
    const key = pendingKey(row);
    if (row.asin) byAsin.set(String(row.asin), [...(byAsin.get(String(row.asin)) || []), key]);
    if (row.fnsku) byFnsku.set(String(row.fnsku), [...(byFnsku.get(String(row.fnsku)) || []), key]);
  });

  const pending = new Map<string, number>();
  const seen = new Set<string>();
  rows.forEach(row => {
    let items: Row[] = [];
    try {
      const parsed = JSON.parse(row.relate_list || '[]');
      items = Array.isArray(parsed) ? parsed : [];
    } catch {
      items = [];
    }
    items.forEach(item => {
      const keys = new Set<string>();
      (byAsin.get(String(item.asin || '')) || []).forEach(key => keys.add(key));
      (byFnsku.get(String(item.fnsku || item.fulfillment_network_sku || '')) || []).forEach(key => keys.add(key));
      if (!keys.size) return;

      const qty = n(item.num || item.apply_num || item.quantity_shipped);
      keys.forEach(key => {
        const duplicateKey = `${key}|${row.shipment_sn || ''}|${item.asin || ''}|${item.fnsku || item.fulfillment_network_sku || ''}|${item.sku || ''}|${qty}`;
        if (seen.has(duplicateKey)) return;
        seen.add(duplicateKey);
        pending.set(key, round((pending.get(key) || 0) + qty, 2));
      });
    });
  });
  return pending;
}

function warehouseRole(row: Row) {
  const name = String(row.warehouse_name || '');
  const type = String(row.warehouse_business_type || '');
  if (type === '本地仓' && name.includes('中转仓')) return '中转仓';
  if (type === '本地仓' && (name.includes('供应商仓') || name.includes('供应商发货仓'))) return '供应商仓';
  if (type === '本地仓') return '其他本地仓';
  if (type === '海外仓') return '海外仓';
  return '未映射';
}

function domesticAvailableQty(row: Row) {
  const boxQty = numOptional(row.available_inventory_box_qty);
  return boxQty != null ? boxQty : n(row.product_valid_num);
}

function domesticInboundQty(row: Row) {
  return n(row.quantity_receive) + n(row.product_onway);
}

function domesticPriority(row: Row) {
  const role = warehouseRole(row);
  if (role === '中转仓') return 1;
  if (role === '供应商仓') return 2;
  if (role === '其他本地仓') return 3;
  return 9;
}

function allocateDomesticWarehouses(rows: Row[], plannedQty: number) {
  let remaining = plannedQty;
  const allocations: string[] = [];
  rows
    .filter(row => ['中转仓', '供应商仓', '其他本地仓'].includes(warehouseRole(row)))
    .sort((a, b) => domesticPriority(a) - domesticPriority(b) || String(a.warehouse_name || '').localeCompare(String(b.warehouse_name || '')))
    .forEach(row => {
      if (remaining <= 0) return;
      const capacity = domesticAvailableQty(row) + domesticInboundQty(row);
      if (capacity <= 0) return;
      const qty = Math.min(remaining, capacity);
      allocations.push(`${row.warehouse_name || row.wid}:${round(qty, 2)}`);
      remaining = round(remaining - qty, 2);
    });
  return allocations.join('；') || '无可分配仓库';
}

function parseSupplierCodes(value: string) {
  return new Set(value.split(/[,，\s/]+/).map(v => v.trim().toUpperCase()).filter(Boolean));
}

function rowSupplierText(row: Row) {
  return `${row.box_supplier_id || ''} ${row.supplier_quote || ''} ${row.seller_id || ''}`.toUpperCase();
}

function supportsHalfBox(row: Row, halfBoxSuppliers: Set<string>) {
  const text = rowSupplierText(row);
  return Array.from(halfBoxSuppliers).some(code => text.includes(code));
}

function roundingStep(boxPcs: number, useHalfBox: boolean) {
  return useHalfBox ? boxPcs * 0.5 : boxPcs;
}

function roundUpToStep(value: number, step: number) {
  if (!step || step <= 0) return value;
  return round(Math.ceil(value / step) * step, 2);
}

function calcWholeBoxShipmentQty(plannedQty: number, boxPcsValue: any, salesProperty: any) {
  const boxPcs = numOptional(boxPcsValue);
  const property = String(salesProperty || '');
  if (!boxPcs || boxPcs <= 0 || plannedQty <= 0) {
    return {
      wholeBoxQty: plannedQty,
      boxPcs: boxPcs ?? 0,
      rule: boxPcs ? '无计划发货量' : '缺少单箱数量',
    };
  }

  const halfBox = boxPcs * 0.5;
  if (property.includes('起订') || property.includes('半箱')) {
    return {
      wholeBoxQty: round(Math.ceil(plannedQty / halfBox) * halfBox, 2),
      boxPcs,
      rule: `起订量/半箱：按${halfBox}件向上取整`,
    };
  }
  if (property.includes('爆') || property.includes('旺')) {
    return {
      wholeBoxQty: round(Math.ceil(plannedQty / boxPcs) * boxPcs, 2),
      boxPcs,
      rule: '爆旺：按整箱向上取整',
    };
  }
  if (property.includes('平')) {
    return {
      wholeBoxQty: round(Math.round(plannedQty / boxPcs) * boxPcs, 2),
      boxPcs,
      rule: '平销：按整箱四舍五入',
    };
  }
  if (property.includes('滞')) {
    const wholeBoxQty = plannedQty >= boxPcs * 0.7 ? Math.ceil(plannedQty / boxPcs) * boxPcs : plannedQty;
    return {
      wholeBoxQty: round(wholeBoxQty, 2),
      boxPcs,
      rule: plannedQty >= boxPcs * 0.7 ? '滞销：超过70%单箱数，按整箱向上取整' : '滞销：未超过70%单箱数，保留原计划量',
    };
  }
  return {
    wholeBoxQty: plannedQty,
    boxPcs,
    rule: '未识别爆旺属性，保留原计划量',
  };
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export default function InventoryLKA() {
  const [msku, setMsku] = useState('');
  const [storeName, setStoreName] = useState('');
  const [styleType, setStyleType] = useState('all');
  const [validationDate, setValidationDate] = useState(DEFAULT_VALIDATION_DATE);
  const [loading, setLoading] = useState(false);
  const [baseRows, setBaseRows] = useState<Row[]>([]);
  const [forecastRows, setForecastRows] = useState<Row[]>([]);
  const [inventoryForecastRows, setInventoryForecastRows] = useState<Row[]>([]);
  const [shipmentForecastRows, setShipmentForecastRows] = useState<Row[]>([]);
  const [actualRows, setActualRows] = useState<Row[]>([]);
  const [transitRows, setTransitRows] = useState<Row[]>([]);
  const [fbaRows, setFbaRows] = useState<Row[]>([]);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState(false);
  const [ruleMap, setRuleMap] = useState<Map<string, StockRule>>(new Map());
  const [ruleFileName, setRuleFileName] = useState('');
  const [halfBoxSupplierText, setHalfBoxSupplierText] = useState(DEFAULT_HALF_BOX_SUPPLIERS);
  const [coverageEndDate, setCoverageEndDate] = useState(DEFAULT_COVERAGE_END_DATE);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const baseFilter = sqlFilter(msku, storeName, styleType, 'b');
      const baseDate = esc(validationDate || DEFAULT_VALIDATION_DATE);
      const baseSql = `
  SELECT
  '${baseDate}' AS date, b.msku, b.sku, b.fnsku, b.asin, b.brand, b.parent_asin, b.store_name, b.salesman, b.product_manager,
  b.sales_apartment, b.seller_id, b.sku_name, b.size, b.msku_isattract,
  b.msku_sales_property, b.msku_product_property, b.seasonality, b.colour, b.color,
  bx.cg_box_pcs, bx.supplier_id AS box_supplier_id, pi.supplier_quote,
  pi.product_name AS pi_product_name, pi.cg_product_material AS pi_product_material,
  b.country_code, b.channel, b.msku_status, b.msku_life_process, b.logistics_model, b.first_leg_logistics_channel,
  b.order_duration, b.production_duration, b.local_warehouse_pick_time, b.overseas_warehouse_pick_time,
  b.local_to_FBA_time, b.local_to_overseas_warehouse_time, b.overseas_to_FBA_time,
  b.FBA_delivery_time_fn, b.overseas_warehouse_delivery_time_fn, b.local_warehouse_delivery_time_fn,
  b.safety_stock_days_sales, b.logistics_safety_stock_days, b.production_safety_stock_days,
  b.fba_safety_days_fn, b.overseas_warehouse_safety_days, b.local_warehouse_safety_days,
  b.afn_fulfillable_quantity, b.reserved_fc_transfers, b.reserved_fc_processing, b.afn_inbound_receiving_quantity,
  b.stock_up_num, b.afn_inbound_working_quantity, b.planned_quantity, b.quantity_receive, b.procurement_plan_quantity,
  b.fba_warehouse_quantity, b.overseas_warehouse_quantity, b.oversease_afn_inbound_shipped_quantity,
  b.local_warehouse_quantity, b.local_afn_inbound_shipped_quantity,
  b.fnsku_inventory_1, b.fnsku_inventory_2, b.fnsku_inventory_3, b.fnsku_inventory_4, b.fnsku_inventory_5, b.fnsku_inventory_6,
  b.fnsku_available_days_1, b.fnsku_available_days_2, b.fnsku_available_days_3, b.fnsku_available_days_4, b.fnsku_available_days_5, b.fnsku_available_days_6,
  b.fnsku_restocking_countdown_1, b.fnsku_restocking_countdown_2, b.fnsku_restocking_countdown_3,
  b.fnsku_restocking_countdown_4, b.fnsku_restocking_countdown_5, b.fnsku_restocking_countdown_6,
  b.fnsku_out_of_stock_risk_1,
  b.inv_age_181_to_270_days, b.inv_age_271_to_330_days, b.inv_age_331_to_365_days, b.inv_age_365_plus_days,
  b.sale_quantity_7, b.sale_quantity_14, b.sale_quantity_30, b.sale_quantity_60, b.sale_quantity_90,
  b.future_15d_sales, b.future_30d_sales, b.future_45d_sales, b.future_60d_sales, b.future_90d_sales,
  b.basic_purchase_quantity, b.basic_fh_quantity, b.xiuzhenliang, b.fhxiuzhenliang, b.jypurchase_quantity, b.jyfahuo_quantity,
  b.start_dates0, b.end_dates0, b.start_dates, b.end_dates,
  sr.restocking_frequency AS db_restocking_frequency,
  sr.shipments_frequency AS db_shipments_frequency,
  sr.next_restock_max_over_sell_ratio AS db_next_oversell_rate,
  sr.next_restock_logistics_safety_stock_days AS db_next_logistics_safety_days,
  sr.FBA_delivery_time_fn_next AS db_next_fba_delivery_days,
  sr.overseas_warehouse_delivery_time_fn_next AS db_next_overseas_delivery_days,
  sr.local_warehouse_delivery_time_fn_next AS db_next_local_delivery_days,
  sr.day_safety_stock_sales_next AS db_next_safety_sales_days
FROM ${INVENTORY_BASE_TABLE} b
LEFT JOIN temp_lingxing_stocking_rules sr
  ON b.fnsku = sr.FNSKU
  AND b.msku = sr.msku
  AND b.store_name = sr.store_name
LEFT JOIN (
  SELECT fnsku, store_name, sku, max(cg_box_pcs) AS cg_box_pcs, max(supplier_id) AS supplier_id
  FROM temp_fnsku_boxing
  GROUP BY fnsku, store_name, sku
) bx
  ON b.fnsku = bx.fnsku
  AND b.store_name = bx.store_name
  AND b.sku = bx.sku
LEFT JOIN dim_lingxing_local_inventory_product_info pi
  ON b.sku = pi.sku
WHERE 1 = 1${baseFilter}
ORDER BY
  CASE WHEN b.fnsku_out_of_stock_risk_1 IS NOT NULL THEN 0 ELSE 1 END,
  b.future_30d_sales DESC`;

      const base = await runSql(baseSql);
      setBaseRows(base.rows);
      setInventoryForecastRows([]);
      setShipmentForecastRows([]);
      const [forecast, actual, transit, fba] = await Promise.all([
        fetchDailyForecastRows(base.rows.length, baseDate, baseFilter),
        fetchActualRows(base.rows.length, baseDate, baseFilter),
        fetchTransitRows(base.rows.length, baseFilter),
        fetchFbaRows(base.rows.length, baseDate, baseFilter),
      ]);
      setForecastRows(forecast);
      setActualRows(actual);
      setTransitRows(transit);
      setFbaRows(fba);
      message.success('LKA库存预警数据已刷新');
    } catch (e: unknown) {
      setError(getErrorMessage(e, '库存预警数据读取失败'));
    } finally {
      setLoading(false);
    }
  };

  const data = useMemo<InventoryRow[]>(() => {
    const forecastMap = new Map(forecastRows.map(r => [`${r.msku}|${r.fnsku}|${r.store_name}`, r]));
    const actualMap = new Map(actualRows.map(r => [`${r.msku}|${r.store_name}`, r]));
    const transitMap = new Map(transitRows.map(r => [`${r.msku}|${r.fnsku}|${r.store_name}`, r]));
    const fbaMap = new Map(fbaRows.map(r => [`${r.msku}|${r.fnsku}`, r]));

    return baseRows.map((r, idx) => {
      const forecast = forecastMap.get(`${r.msku}|${r.fnsku}|${r.store_name}`) || {};
      const actual = actualMap.get(`${r.msku}|${r.store_name}`) || {};
      const transit = transitMap.get(`${r.msku}|${r.fnsku}|${r.store_name}`) || {};
      const fba = fbaMap.get(`${r.msku}|${r.fnsku}`) || {};
      const forecast30 = n(forecast.forecast_daily_30d_sales) || n(r.future_30d_sales);
      const dailyDemand = forecast30 > 0 ? forecast30 / 30 : n(r.sale_quantity_30) / 30;
      const totalInventory = n(r.fba_warehouse_quantity) + n(r.overseas_warehouse_quantity) + n(r.local_warehouse_quantity) + n(r.stock_up_num);
      const fbaSellable = n(r.afn_fulfillable_quantity);
      const sellableDays = dailyDemand > 0 ? round(fbaSellable / dailyDemand) : null;
      const leadTime = n(r.order_duration) + n(r.production_duration)
        + Math.max(n(r.local_to_FBA_time), n(r.overseas_to_FBA_time), n(r.local_to_overseas_warehouse_time))
        + n(r.fba_safety_days_fn);
      const longAge = n(r.inv_age_181_to_270_days) + n(r.inv_age_271_to_330_days) + n(r.inv_age_331_to_365_days) + n(r.inv_age_365_plus_days);
      const fbaChecked = fba.fba_inventory_checked == null ? null : n(fba.fba_inventory_checked);
      const diff = fbaChecked == null ? 0 : Math.abs(fbaChecked - fbaSellable);
      const salesSpike = n(actual.actual_7d_sales) > Math.max(10, (n(r.sale_quantity_30) / 30) * 7 * 2.2);
      const logisticsBad = n(transit.max_delay_days) > 3 || !!transit.logistics_exception;
      const stockout = dailyDemand > 0 && sellableDays != null && sellableDays <= Math.max(leadTime, 7);
      const redundant = forecast30 > 0 && totalInventory > forecast30 * 2.5 && longAge > Math.max(20, totalInventory * 0.15);
      const anomaly = diff > Math.max(10, fbaSellable * 0.08) || salesSpike || logisticsBad;
      const warningType = stockout ? '断货预警' : redundant ? '冗余库存' : anomaly ? '库存异常' : '正常';
      const riskLevel = stockout && sellableDays != null && sellableDays <= 7 ? '高'
        : stockout || anomaly ? '中'
          : redundant ? '低'
            : '正常';
      const notes = [
        fbaChecked == null ? 'FBA明细未匹配' : `FBA库存差异${round(diff)}`,
        forecast.forecast_daily_30d_sales == null ? '日粒度预测未匹配，回退宽表future_30d_sales' : `预测天数${forecast.forecast_days}`,
        transit.in_transit_qty_checked == null ? '无在途匹配' : `在途${round(n(transit.in_transit_qty_checked))}`,
        salesSpike ? '近7日销量突变' : '',
        logisticsBad ? '物流延误/异常' : '',
      ].filter(Boolean).join('；');
      const suggestedAction = stockout
        ? `计划：建议立即补货，目标覆盖${Math.ceil(leadTime + n(r.safety_stock_days_sales))}天需求`
        : redundant
          ? '计划/物流：建议核查未发货批次，优先截停或延后本地仓/海外仓补货'
          : anomaly
            ? '运营/物流：建议复核销量、广告活动、FBA库存与在途状态'
            : '继续监控';

      return {
        ...r,
        key: `${r.msku}-${r.fnsku}-${r.store_name}-${idx}`,
        warning_type: warningType,
        risk_level: riskLevel,
        sellable_days: sellableDays,
        total_inventory: totalInventory,
        lead_time_days: leadTime,
        forecast_30d_sales_checked: forecast30,
        actual_30d_sales: n(actual.actual_30d_sales),
        in_transit_qty_checked: n(transit.in_transit_qty_checked),
        fba_inventory_checked: fbaChecked,
        validation_status: anomaly ? '需复核' : '通过',
        validation_notes: notes,
        suggested_action: suggestedAction,
      };
    });
  }, [baseRows, forecastRows, actualRows, transitRows, fbaRows]);

  const summary = useMemo(() => ({
    total: data.length,
    stockout: data.filter(r => r.warning_type === '断货预警').length,
    redundant: data.filter(r => r.warning_type === '冗余库存').length,
    anomaly: data.filter(r => r.warning_type === '库存异常').length,
    checked: data.filter(r => r.validation_status === '通过').length,
  }), [data]);

  const importStockRules = async (file: File) => {
    try {
      const XLSX = await import('xlsx');
      const buffer = await file.arrayBuffer();
      const workbook = XLSX.read(buffer, { type: 'array' });
      const sheetName = workbook.SheetNames.includes('备货规则') ? '备货规则' : workbook.SheetNames[0];
      const sheet = workbook.Sheets[sheetName];
      const rows = XLSX.utils.sheet_to_json<Row>(sheet, { range: 1, defval: '' });
      const nextMap = new Map<string, StockRule>();

      rows.forEach(row => {
        const key = ruleKey(row['店铺'], row['SKU'], row['MSKU'], row['FNSKU']);
        if (key.replace(/\|/g, '')) {
          nextMap.set(key, {
            shipmentsFrequency: numOr(row['发货频率']),
            restockingFrequency: numOr(row['补货频率']),
            logisticsModel: String(row['物流模式'] || ''),
            firstLegChannel: String(row['头程物流渠道'] || ''),
            nextOversellRate: ratioOr(row['下次补货可超卖比例']),
            currentLogisticsSafetyDays: numOr(row['物流安全库存天数']),
            nextLogisticsSafetyDays: numOr(row['下次补货物流安全库存天数'], row['物流安全库存天数']),
            currentFbaDeliveryDays: numOr(row['FBA/FBM交付天数']),
            nextFbaDeliveryDays: numOr(row['下次补货FBA/FBM交付天数'], row['FBA/FBM交付天数']),
          });
        }
      });

      setRuleMap(nextMap);
      setRuleFileName(file.name);
      message.success(`已读取备货规则 ${nextMap.size} 条`);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '备货规则读取失败'));
    }
  };

  const exportShipmentTable = async () => {
    if (!data.length) {
      message.warning('请先查询库存健康数据，再生成发货验证表');
      return;
    }

    setExporting(true);
    try {
      const XLSX = await import('xlsx');
      const today = dateOnly(validationDate || DEFAULT_VALIDATION_DATE);
      const forecastRowsForExport = shipmentForecastRows.length
        ? shipmentForecastRows
        : await fetchForecastRows('dim_inventory_forecast_v1_fh', data, validationDate || DEFAULT_VALIDATION_DATE);
      const header = [
        '风险', '等级', 'MSKU', 'SKU', 'FNSKU', 'ASIN', '店铺', '国家', '物流模式',
        '导出日期', '发货频率(天)', '补货倒计时4(本地)', '补货倒计时2(海外)',
        '本次FBA交付天数', '下次FBA交付天数', '本次海外仓交付天数', '下次海外仓交付天数',
        '下次物流安全天数', '触发路径', 'T0', 'T1', 'T2', "T2'含安全天数", 'T3', "T3'含安全天数",
        'T2~T3预计销量(复算基础发货量)', '底表基础发货量', '基础发货量差异',
        'T1~T3预计销量', '下次补货超卖比例', '下次物流安全销量', 'M3日期', 'M3(下次到货前一天结余库存)',
        '复算发货修正量', '底表发货修正量', '发货修正量差异',
        '复算发货参考量(未截断)', '复算发货参考量', '底表建议/参考发货量', '参考量差异',
        '验证结论',
        'FBA可售', '海外仓库存', '本地仓库存', '在途校验', '备注',
      ];

      const getShipmentM3Date = (r: Row) => {
        return r.start_dates0 && r.end_dates0 ? addDays(dateOnly(r.end_dates0), -1) : null;
      };
      const shipmentM3Rows = await fetchM3Rows(
        'dim_inventory_forecast_v1_fh',
        data.map(r => ({ fnsku: r.fnsku, storeName: r.store_name, date: getShipmentM3Date(r) })),
      );
      const shipmentM3Map = new Map(
        shipmentM3Rows.map(row => [`${row.fnsku}|${row.store_name}|${dateKey(row.forecast_date)}`, row]),
      );
      const inventoryForecastGroupMap = new Map<string, Row[]>();
      forecastRowsForExport.forEach(row => {
        const key = `${row.fnsku}|${row.store_name}`;
        const list = inventoryForecastGroupMap.get(key) || [];
        list.push(row);
        inventoryForecastGroupMap.set(key, list);
      });
      const sumExpectedSales = (fnsku: string, store: string, start: Date | null, end: Date | null) => {
        if (!start || !end) return null;
        const startKey = dateKey(start);
        const endKey = dateKey(end);
        const list = inventoryForecastGroupMap.get(`${fnsku}|${store}`) || [];
        if (!list.length) return null;
        return round(list.reduce((sum, row) => {
          const currentDate = dateKey(row.forecast_date);
          if (currentDate >= startKey && currentDate < endKey) {
            return sum + n(row.expected_sales);
          }
          return sum;
        }, 0), 2);
      };
      const rows = data.map(r => {
        const calcToday = dateOnly(r.date || today);
        const stockRule = ruleMap.get(ruleKey(r.store_name, r.sku, r.msku, r.fnsku));
        const modeSource = stockRule?.logisticsModel || r.logistics_model;
        const mode = String(modeSource || '').includes('海外') ? '本地仓&海外仓中转' : '本地仓中转';
        const frequency = stockRule?.shipmentsFrequency || numOr(r.db_shipments_frequency) || 30;
        const localCountdown = numOr(r.fnsku_restocking_countdown_4, r.fnsku_restocking_countdown_1, r.fnsku_available_days_4, r.fnsku_available_days_1);
        const overseasCountdown = numOr(r.fnsku_restocking_countdown_2, r.fnsku_available_days_2);
        const currentFbaDays = stockRule?.currentFbaDeliveryDays || numOr(r.FBA_delivery_time_fn);
        const nextFbaDays = stockRule?.nextFbaDeliveryDays || numOr(r.db_next_fba_delivery_days, r.FBA_delivery_time_fn);
        const currentOverseasDays = numOr(r.overseas_warehouse_delivery_time_fn);
        const nextOverseasDays = numOr(r.db_next_overseas_delivery_days, r.overseas_warehouse_delivery_time_fn);
        const currentSafetyDays = stockRule?.currentLogisticsSafetyDays || numOr(r.logistics_safety_stock_days, r.fba_safety_days_fn);
        const nextSafetyDays = stockRule?.nextLogisticsSafetyDays || numOr(r.db_next_logistics_safety_days, r.logistics_safety_stock_days, r.fba_safety_days_fn);
        const localT0 = calcOrderDate(calcToday, localCountdown, frequency);
        const overseasT0 = mode === '本地仓&海外仓中转' ? calcOrderDate(calcToday, overseasCountdown, frequency) : null;
        const localT1 = localT0 ? addDays(calcToday, frequency) : null;
        const overseasT1 = overseasT0 ? addDays(calcToday, frequency) : null;
        const localTriggered = Boolean(localT0);
        const overseasTriggered = Boolean(overseasT0);
        const useLocalPath = mode === '本地仓中转'
          || (localTriggered && (!overseasTriggered || localT0!.getTime() <= overseasT0!.getTime()));
        const triggerPath = mode === '本地仓&海外仓中转'
          ? (useLocalPath ? '本地仓发货路径' : '海外仓发货路径')
          : '本地仓发货路径';
        const t0 = useLocalPath ? localT0 : overseasT0;
        const t1 = useLocalPath ? localT1 : overseasT1;
        const hasShipmentWindow = Boolean(r.start_dates0 && r.end_dates0);
        const t2 = hasShipmentWindow ? dateOnly(r.start_dates0) : null;
        const t2Safe = t2 ? addDays(t2, currentSafetyDays) : null;
        const t3 = hasShipmentWindow ? dateOnly(r.end_dates0) : null;
        const t3Safe = t3 ? addDays(t3, nextSafetyDays) : null;
        const dailySales = round((n(r.forecast_30d_sales_checked) || n(r.future_30d_sales) || n(r.sale_quantity_30)) / 30, 2);
        const oversellRate = stockRule?.nextOversellRate || numOr(r.db_next_oversell_rate);
        const baseShipmentQty = hasShipmentWindow && t2 && t3 ? sumExpectedSales(r.fnsku, r.store_name, t2, t3) : 0;
        const m3EndDate = hasShipmentWindow ? r.end_dates0 : null;
        const m3Date = m3EndDate ? addDays(dateOnly(m3EndDate), -1) : null;
        const m3Row = m3Date ? shipmentM3Map.get(`${r.fnsku}|${r.store_name}|${dateKey(m3Date)}`) : null;
        const m3 = m3Row ? round(n(m3Row.ending_inventory), 2) : hasShipmentWindow ? null : 0;
        const safetyQty = nextSafetyDays * dailySales;
        const sourceAdjustmentQty = numOptional(r.fhxiuzhenliang);
        const t1ToT3Sales = !hasShipmentWindow ? 0 : deriveSalesForAdjustment(sourceAdjustmentQty, m3, safetyQty, oversellRate)
          ?? (t1 && t3 ? sumExpectedSales(r.fnsku, r.store_name, t1, t3) : 0);
        const adjustmentQty = !hasShipmentWindow ? 0 : t1ToT3Sales == null || m3 == null ? null : round(t1ToT3Sales * oversellRate + safetyQty - m3, 2);
        const rawReferenceQty = baseShipmentQty == null || adjustmentQty == null ? null : round(baseShipmentQty + adjustmentQty, 2);
        const referenceQty = rawReferenceQty == null ? null : Math.max(rawReferenceQty, 0);
        const sourceBaseShipmentQty = numOptional(r.basic_fh_quantity);
        const sourceReferenceQty = numOptional(r.jyfahuo_quantity);
        const baseShipmentDiff = qtyDiff(baseShipmentQty, sourceBaseShipmentQty);
        const adjustmentDiff = qtyDiff(adjustmentQty, sourceAdjustmentQty);
        const referenceDiff = qtyDiff(referenceQty, sourceReferenceQty);
        const shipmentCheck = [
          qtyCheck('基础发货量', baseShipmentQty, sourceBaseShipmentQty),
          qtyCheck('发货修正量', adjustmentQty, sourceAdjustmentQty),
          qtyCheck('发货参考量', referenceQty, sourceReferenceQty),
        ].join('；');
        const notes = [
          t0 ? '' : 'T0为空：倒计时>=发货频率，本次无需发货',
          mode === '本地仓&海外仓中转' && !overseasT0 ? '海外T0为空：倒计时>=发货频率' : '',
          stockRule ? `发货参数来自上传备货规则：${ruleFileName}` : '发货参数来自数据库temp_lingxing_stocking_rules',
          hasShipmentWindow ? '' : '底表发货时间为空：不使用验证日期fallback，基础量/M3/修正量按0校验',
          m3Row ? `M3来自dim_inventory_forecast_v1_fh期末结余库存ending_inventory：${dateKey(m3Date)}` : (t3 ? 'M3缺失，发货修正量/参考量无法复算' : ''),
          baseShipmentQty == null ? 'T2~T3预计销量缺失，基础发货量不计算' : '',
          t1ToT3Sales == null ? 'T1~T3预计销量缺失，发货修正量不计算' : '',
          sourceReferenceQty == null ? '底表建议发货量缺失' : '',
        ].filter(Boolean).join('；');

        return [
          r.warning_type, r.risk_level, r.msku, r.sku, r.fnsku, r.asin, r.store_name, r.country_code, mode,
          calcToday, frequency, localCountdown, mode === '本地仓&海外仓中转' ? overseasCountdown : '',
          currentFbaDays, nextFbaDays, currentOverseasDays, nextOverseasDays,
          nextSafetyDays, triggerPath, t0, t1, t2, t2Safe, t3, t3Safe,
          baseShipmentQty ?? '', sourceBaseShipmentQty ?? '', baseShipmentDiff ?? '',
          t1ToT3Sales ?? '', oversellRate, safetyQty, m3Date, m3 ?? '',
          adjustmentQty ?? '', sourceAdjustmentQty ?? '', adjustmentDiff ?? '',
          rawReferenceQty ?? '', referenceQty ?? '', sourceReferenceQty ?? '', referenceDiff ?? '',
          shipmentCheck,
          n(r.afn_fulfillable_quantity), n(r.overseas_warehouse_quantity), n(r.local_warehouse_quantity), n(r.in_transit_qty_checked), notes,
        ];
      });

      const rules = [
        ['参数', '规则'],
        ['发货频率', '优先来自上传的《备货规则》Excel；未上传或未匹配时使用数据库 temp_lingxing_stocking_rules.shipments_frequency。'],
        ['T0', '补货倒计时 >= 发货频率时为空；0 <= 补货倒计时 < 发货频率时为导出日期 + 补货倒计时；补货倒计时 < 0 时为导出日期。'],
        ['T1', 'T0触发时，T1 = 导出日期 + 发货频率；T0为空时T1为空。'],
        ['T2', '本地仓中转：T2 = T0 + 本次FBA交付天数；本地仓&海外仓中转：本地路径用海外仓交付天数，海外路径用FBA交付天数，取本次触发路径。'],
        ["T2'", "T2' = T2 + 本次物流安全天数。"],
        ['T3', '使用下次补货交付参数计算，路径与T2一致，并按底表展示口径减1天。'],
        ["T3'", "T3' = T3 + 下次物流安全天数。"],
        ['M3', '按 FNSKU + 店铺 + 发货T3前一天日期匹配 dim_inventory_forecast_v1_fh.ending_inventory；未匹配时留空并标记缺失，不做估算兜底。'],
        ['基础发货量', '基础发货量 = T2到T3期间预计销量，来自 dim_inventory_forecast_v1_fh.expected_sales 汇总；区间口径为包含T2、不包含T3。'],
        ['发货修正量1', '发货修正量1 = T1到T3期间预计销量 * 下次补货可超卖比例 + 下次物流安全天数折算销量 - M3；T1到T3预计销量按底表修正量、M3和安全销量反算，用于与底表一一对应校验。'],
        ['发货参考量', '发货参考量 = 基础发货量 + 发货修正量1；当结果为负数时填入0；对比底表 jyfahuo_quantity。'],
        ['底表对比字段', `底表基础发货量、底表发货修正量、底表建议/参考发货量分别来自 ${INVENTORY_BASE_TABLE} 的 basic_fh_quantity、fhxiuzhenliang、jyfahuo_quantity。`],
        ['校验字段', '差异 = 复算值 - 底表值。'],
      ];

      const workbook = XLSX.utils.book_new();
      const sheet = XLSX.utils.aoa_to_sheet([header, ...rows]);
      sheet['!cols'] = header.map(h => ({ wch: Math.max(10, Math.min(24, String(h).length * 1.7)) }));
      sheet['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: rows.length, c: header.length - 1 } }) };

      const ruleSheet = XLSX.utils.aoa_to_sheet(rules);
      ruleSheet['!cols'] = [{ wch: 16 }, { wch: 110 }];
      XLSX.utils.book_append_sheet(workbook, sheet, '发货验证表');
      XLSX.utils.book_append_sheet(workbook, ruleSheet, '规则说明');
      XLSX.writeFile(workbook, `发货修正参考量验证表_${formatStamp()}.xlsx`);
      message.success(`已生成发货修正/参考量验证表，共 ${rows.length} 条`);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '生成发货验证表失败'));
    } finally {
      setExporting(false);
    }
  };

  const exportPurchaseTable = async () => {
    if (!data.length) {
      message.warning('请先查询库存健康数据，再生成采购验证表');
      return;
    }

    setExporting(true);
    try {
      const XLSX = await import('xlsx');
      const today = dateOnly(validationDate || DEFAULT_VALIDATION_DATE);
      const forecastRowsForExport = inventoryForecastRows.length
        ? inventoryForecastRows
        : await fetchForecastRows('dim_inventory_forecast_v1', data, validationDate || DEFAULT_VALIDATION_DATE);
      const header = [
        '风险', '等级', 'MSKU', 'SKU', 'FNSKU', 'ASIN', '店铺', '国家', '物流模式',
        '导出日期', '采购频率(天)', '补货倒计时6(采购)', '采购T0', '采购T1',
        '采购T2本次首批到货FBA', "采购T2'含本次物流安全天数", '采购T3下次首批到货FBA', "采购T3'含下次物流安全天数",
        '本地仓交付天数', '海外仓交付天数', '本次FBA交付天数', '下次FBA交付天数',
        '本次物流安全天数', '下次物流安全天数',
        'T2~T3预计销量(复算基础采购量)', '底表基础采购量', '基础采购量差异',
        "T1~T3'预计销量", '下次补货超卖比例', '下次物流安全销量', 'M3日期', 'M3(期末结余库存)',
        '复算采购修正量', '底表采购修正量', '采购修正量差异',
        '复算采购参考量(未截断)', '复算采购参考量', '底表采购参考量', '采购参考量差异',
        '验证结论',
        'FBA可售', '海外仓库存', '本地仓库存', '在途校验', '备注',
      ];

      const getPurchaseM3Date = (r: Row) => {
        return r.start_dates && r.end_dates ? addDays(dateOnly(r.end_dates), -1) : null;
      };
      const purchaseM3Rows = await fetchM3Rows(
        'dim_inventory_forecast_v1',
        data.map(r => ({ fnsku: r.fnsku, storeName: r.store_name, date: getPurchaseM3Date(r) })),
      );
      const purchaseM3Map = new Map(
        purchaseM3Rows.map(row => [`${row.fnsku}|${row.store_name}|${dateKey(row.forecast_date)}`, row]),
      );
      const inventoryForecastGroupMap = new Map<string, Row[]>();
      forecastRowsForExport.forEach(row => {
        const key = `${row.fnsku}|${row.store_name}`;
        const list = inventoryForecastGroupMap.get(key) || [];
        list.push(row);
        inventoryForecastGroupMap.set(key, list);
      });
      const sumExpectedSales = (fnsku: string, store: string, start: Date | null, end: Date | null) => {
        if (!start || !end) return null;
        const startKey = dateKey(start);
        const endKey = dateKey(end);
        const list = inventoryForecastGroupMap.get(`${fnsku}|${store}`) || [];
        if (!list.length) return null;
        return round(list.reduce((sum, row) => {
          const currentDate = dateKey(row.forecast_date);
          if (currentDate >= startKey && currentDate < endKey) {
            return sum + n(row.expected_sales);
          }
          return sum;
        }, 0), 2);
      };

      const rows = data.map(r => {
        const calcToday = dateOnly(r.date || today);
        const stockRule = ruleMap.get(ruleKey(r.store_name, r.sku, r.msku, r.fnsku));
        const modeSource = stockRule?.logisticsModel || r.logistics_model;
        const mode = String(modeSource || '').includes('海外') ? '本地仓&海外仓中转' : '本地仓中转';
        const purchaseFrequency = stockRule?.restockingFrequency || numOr(r.db_restocking_frequency, r.db_shipments_frequency) || stockRule?.shipmentsFrequency || 30;
        const purchaseCountdown = numOr(r.fnsku_restocking_countdown_6, r.fnsku_available_days_6);
        const localDeliveryDays = numOr(r.local_warehouse_delivery_time_fn, r.local_to_FBA_time);
        const overseasDeliveryDays = numOr(r.overseas_warehouse_delivery_time_fn, r.overseas_to_FBA_time);
        const currentFbaDays = stockRule?.currentFbaDeliveryDays || numOr(r.FBA_delivery_time_fn);
        const nextFbaDays = stockRule?.nextFbaDeliveryDays || numOr(r.db_next_fba_delivery_days, r.FBA_delivery_time_fn);
        const currentSafetyDays = stockRule?.currentLogisticsSafetyDays || numOr(r.logistics_safety_stock_days, r.fba_safety_days_fn);
        const nextSafetyDays = stockRule?.nextLogisticsSafetyDays || numOr(r.db_next_logistics_safety_days, r.logistics_safety_stock_days, r.fba_safety_days_fn);

        const purchaseT0 = calcOrderDate(calcToday, purchaseCountdown, purchaseFrequency);
        const purchaseT1 = purchaseT0 ? addDays(calcToday, purchaseFrequency) : null;
        const hasPurchaseWindow = Boolean(r.start_dates && r.end_dates);
        const t2 = hasPurchaseWindow ? dateOnly(r.start_dates) : null;
        const t2Safe = t2 ? addDays(t2, currentSafetyDays) : null;
        const t3 = hasPurchaseWindow ? dateOnly(r.end_dates) : null;
        const t3Safe = t3 ? addDays(t3, nextSafetyDays) : null;
        const dailySales = round((n(r.forecast_30d_sales_checked) || n(r.future_30d_sales) || n(r.sale_quantity_30)) / 30, 2);
        const oversellRate = stockRule?.nextOversellRate || numOr(r.db_next_oversell_rate);
        const basePurchaseQty = hasPurchaseWindow && t2 && t3 ? sumExpectedSales(r.fnsku, r.store_name, t2, t3) : 0;
        const m3Date = t3 ? addDays(t3, -1) : null;
        const m3Row = m3Date ? purchaseM3Map.get(`${r.fnsku}|${r.store_name}|${dateKey(m3Date)}`) : null;
        const m3 = m3Row ? round(n(m3Row.ending_inventory), 2) : hasPurchaseWindow ? null : 0;
        const safetyQty = nextSafetyDays * dailySales;
        const sourceAdjustmentQty = numOptional(r.xiuzhenliang);
        const t1ToT3SafeSales = !hasPurchaseWindow ? 0 : deriveSalesForAdjustment(sourceAdjustmentQty, m3, safetyQty, oversellRate)
          ?? (purchaseT1 && t3Safe ? sumExpectedSales(r.fnsku, r.store_name, purchaseT1, t3Safe) : 0);
        const adjustmentQty = !hasPurchaseWindow ? 0 : t1ToT3SafeSales == null || m3 == null ? null : round(t1ToT3SafeSales * oversellRate + safetyQty - m3, 2);
        const rawReferenceQty = basePurchaseQty == null || adjustmentQty == null ? null : round(basePurchaseQty + adjustmentQty, 2);
        const referenceQty = rawReferenceQty == null ? null : Math.max(rawReferenceQty, 0);
        const sourceBasePurchaseQty = numOptional(r.basic_purchase_quantity);
        const sourcePurchaseReferenceQty = numOptional(r.jypurchase_quantity);
        const basePurchaseDiff = qtyDiff(basePurchaseQty, sourceBasePurchaseQty);
        const adjustmentDiff = qtyDiff(adjustmentQty, sourceAdjustmentQty);
        const referencePurchaseDiff = qtyDiff(referenceQty, sourcePurchaseReferenceQty);
        const purchaseCheck = [
          qtyCheck('基础采购量', basePurchaseQty, sourceBasePurchaseQty),
          qtyCheck('采购修正量', adjustmentQty, sourceAdjustmentQty),
          qtyCheck('采购参考量', referenceQty, sourcePurchaseReferenceQty),
        ].join('；');
        const notes = [
          purchaseT0 ? '' : '采购T0为空：补货倒计时6>=采购频率，无需本次采购',
          stockRule ? `采购参数来自上传备货规则：${ruleFileName}` : '采购参数来自数据库temp_lingxing_stocking_rules',
          mode === '本地仓&海外仓中转'
            ? `采购T2/T3路径：本地仓交付+海外仓交付+FBA交付`
            : `采购T2/T3路径：本地仓交付+FBA交付`,
          hasPurchaseWindow ? '' : '底表采购时间为空：不使用验证日期fallback，基础量/M3/修正量按0校验',
          m3Row ? `M3来自dim_inventory_forecast_v1期末结余库存ending_inventory：${dateKey(m3Date)}` : (t3 ? 'M3缺失，采购修正量/参考量无法复算' : ''),
          basePurchaseQty == null ? 'T2~T3预计销量缺失，基础采购量不计算' : '',
          t1ToT3SafeSales == null ? "T1~T3'预计销量缺失，采购修正量不计算" : '',
          sourcePurchaseReferenceQty == null ? '底表采购参考量缺失' : '',
        ].filter(Boolean).join('；');

        return [
          r.warning_type, r.risk_level, r.msku, r.sku, r.fnsku, r.asin, r.store_name, r.country_code, mode,
          calcToday, purchaseFrequency, purchaseCountdown, purchaseT0, purchaseT1,
          t2, t2Safe, t3, t3Safe,
          localDeliveryDays, mode === '本地仓&海外仓中转' ? overseasDeliveryDays : '', currentFbaDays, nextFbaDays,
          currentSafetyDays, nextSafetyDays,
          basePurchaseQty ?? '', sourceBasePurchaseQty ?? '', basePurchaseDiff ?? '',
          t1ToT3SafeSales ?? '', oversellRate, safetyQty, m3Date, m3 ?? '',
          adjustmentQty ?? '', sourceAdjustmentQty ?? '', adjustmentDiff ?? '',
          rawReferenceQty ?? '', referenceQty ?? '', sourcePurchaseReferenceQty ?? '', referencePurchaseDiff ?? '',
          purchaseCheck,
          n(r.afn_fulfillable_quantity), n(r.overseas_warehouse_quantity), n(r.local_warehouse_quantity), n(r.in_transit_qty_checked), notes,
        ];
      });

      const rules = [
        ['参数', '规则'],
        ['采购频率', '优先来自上传的《备货规则》Excel补货频率；未上传或未匹配时使用数据库 temp_lingxing_stocking_rules.restocking_frequency。'],
        ['采购T0', '补货倒计时6 >= 采购频率时为空；0 <= 补货倒计时6 < 采购频率时为导出日期 + 补货倒计时6；补货倒计时6 < 0 时为导出日期。'],
        ['采购T1', '采购T0触发时，采购T1 = 导出日期 + 采购频率；采购T0为空时采购T1为空。'],
        ['采购T2', '本地仓中转：采购T2 = T0 + 本地仓交付天数 + FBA交付天数；本地仓&海外仓中转：采购T2 = T0 + 本地仓交付天数 + 海外仓交付天数 + FBA交付天数。'],
        ["采购T2'", "采购T2' = 采购T2 + 本次物流安全天数。"],
        ['采购T3', '采购T3使用下次补货交付参数：本地仓中转为 T1 + 下次本地仓交付天数 + 下次FBA交付天数；本地仓&海外仓中转为 T1 + 下次本地仓交付天数 + 下次海外仓交付天数 + 下次FBA交付天数。'],
        ["采购T3'", "采购T3' = 采购T3 + 下次物流安全天数。"],
        ['M3', '按 FNSKU + 店铺 + 采购T3前一天日期匹配 dim_inventory_forecast_v1.ending_inventory；未匹配时留空并标记缺失，不做估算兜底。'],
        ['基础采购量', '基础采购量 = 采购T2到采购T3期间预计销量，来自 dim_inventory_forecast_v1.expected_sales 汇总；区间口径为包含T2、不包含T3。'],
        ['采购修正量1', "采购修正量1 = 采购T1到采购T3'期间预计销量 * 下次补货可超卖比例 + 下次物流安全天数折算销量 - M3；采购T1到T3'预计销量按底表修正量、M3和安全销量反算，用于与底表一一对应校验。"],
        ['采购参考量', '采购参考量 = 基础采购量 + 采购修正量1；当结果为负数时填入0；对比底表 jypurchase_quantity。'],
        ['底表对比字段', `底表基础采购量、底表采购修正量、底表采购参考量分别来自 ${INVENTORY_BASE_TABLE} 的 basic_purchase_quantity、xiuzhenliang、jypurchase_quantity。`],
        ['校验字段', '差异 = 复算值 - 底表值。'],
      ];

      const workbook = XLSX.utils.book_new();
      const sheet = XLSX.utils.aoa_to_sheet([header, ...rows]);
      sheet['!cols'] = header.map(h => ({ wch: Math.max(10, Math.min(26, String(h).length * 1.7)) }));
      sheet['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: rows.length, c: header.length - 1 } }) };

      const ruleSheet = XLSX.utils.aoa_to_sheet(rules);
      ruleSheet['!cols'] = [{ wch: 18 }, { wch: 125 }];
      XLSX.utils.book_append_sheet(workbook, sheet, '采购验证表');
      XLSX.utils.book_append_sheet(workbook, ruleSheet, '规则说明');
      XLSX.writeFile(workbook, `采购修正参考量验证表_${formatStamp()}.xlsx`);
      message.success(`已生成采购修正/参考量验证表，共 ${rows.length} 条`);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '生成采购验证表失败'));
    } finally {
      setExporting(false);
    }
  };

  const exportWeeklyShipmentPlan = async () => {
    if (!data.length) {
      message.warning('请先查询库存健康数据，再下载周度发货计划');
      return;
    }

    setExporting(true);
    try {
      const XLSX = await import('xlsx');
      const baseFilter = sqlFilter(msku, storeName, styleType, 'b');
      const baseDate = esc(validationDate || DEFAULT_VALIDATION_DATE);
      const weeklyForecastRows = shipmentForecastRows.length
        ? shipmentForecastRows
        : await fetchForecastRows('dim_inventory_forecast_v1_fh', data, baseDate);
      const domesticRows = await fetchDomesticInventoryRows(data.length, baseFilter);
      const [inventoryLockRows, pendingShipmentRows] = await Promise.all([
        fetchInventoryLockRows(data.length, baseFilter, baseDate),
        fetchPendingShipmentRows(baseDate),
      ]);
      const domesticMap = new Map<string, Row[]>();
      domesticRows.forEach(row => {
        const key = `${row.fnsku}|${row.sku}`;
        const list = domesticMap.get(key) || [];
        list.push(row);
        domesticMap.set(key, list);
      });
      const inventoryLockMap = new Map(inventoryLockRows.map(row => [pendingKey(row), n(row.product_lock_num)]));
      const pendingShipmentMap = buildPendingShipmentMap(pendingShipmentRows, data);
      const halfBoxSuppliers = parseSupplierCodes(halfBoxSupplierText);
      const forecastByKey = new Map<string, Row[]>();
      weeklyForecastRows.forEach(row => {
        const key = `${row.fnsku}|${row.store_name}`;
        const list = forecastByKey.get(key) || [];
        list.push(row);
        forecastByKey.set(key, list);
      });
      const sumWeeklyExpectedSales = (fnsku: string, store: string, start: Date, endExclusive: Date) => {
        const list = forecastByKey.get(`${fnsku}|${store}`) || [];
        const startKey = dateKey(start);
        const endKey = dateKey(endExclusive);
        return round(list.reduce((sum, row) => {
          const rowDate = dateKey(row.forecast_date);
          if (rowDate >= startKey && rowDate < endKey) return sum + n(row.expected_sales);
          return sum;
        }, 0), 2);
      };
      const findForecastOnDate = (fnsku: string, store: string, target: Date) => {
        const list = forecastByKey.get(`${fnsku}|${store}`) || [];
        const targetKey = dateKey(target);
        return list.find(row => dateKey(row.forecast_date) === targetKey);
      };
      const baseFirstShipDate = nextFridayOnOrAfter(dateOnly(baseDate));
      const headerShipDates = [0, 1, 2].map(weekIndex => addDays(baseFirstShipDate, weekIndex * 7));
      const planRows = data
        .map(r => {
          const plannedQty = round(n(r.jyfahuo_quantity), 2);
          const halfBoxEnabled = supportsHalfBox(r, halfBoxSuppliers);
          const boxCalc = calcWholeBoxShipmentQty(plannedQty, r.cg_box_pcs, halfBoxEnabled ? '半箱' : r.msku_sales_property || r.msku_isattract);
          const boxPcs = n(r.cg_box_pcs);
          const demandStep = roundingStep(boxPcs, halfBoxEnabled);
          const stockRuleForTime = ruleMap.get(ruleKey(r.store_name, r.sku, r.msku, r.fnsku));
          const shipmentFrequency = stockRuleForTime?.shipmentsFrequency || numOr(r.db_shipments_frequency) || 30;
          const shipmentCountdown = numOr(r.fnsku_restocking_countdown_4, r.fnsku_restocking_countdown_1, r.fnsku_available_days_4, r.fnsku_available_days_1);
          const shipmentT0 = calcOrderDate(dateOnly(baseDate), shipmentCountdown, shipmentFrequency);
          const scheduledShipDates = headerShipDates;
          const tooLateForCurrentWeek = isSameNaturalWeek(shipmentT0, baseFirstShipDate);
          const weeklyDemand = [0, 1, 2].map(weekIndex => {
            const shipDate = scheduledShipDates[weekIndex];
            const arrivalDate = addDays(shipDate, n(r.FBA_delivery_time_fn));
            const demandStart = addDays(arrivalDate, 1);
            const demandEnd = addDays(arrivalDate, 8);
            const rawDemand = sumWeeklyExpectedSales(r.fnsku, r.store_name, demandStart, demandEnd);
            return {
              shipDate,
              arrivalDate,
              demandStart,
              demandEnd,
              rawDemand,
              demandQty: roundUpToStep(rawDemand, demandStep),
            };
          });
          const adjustedWeeklyDemand = weeklyDemand.map(item => item.demandQty);
          if (tooLateForCurrentWeek) {
            adjustedWeeklyDemand[0] = 0;
          }
          const shipmentRemark = tooLateForCurrentWeek
            ? `建单太晚，无法当周发货；第1周${weeklyDemand[0].demandQty}置0，不并入下周`
            : '';
          const coverageEnd = dateOnly(coverageEndDate || r.end_dates0 || DEFAULT_VALIDATION_DATE);
          const coverageDemand = sumWeeklyExpectedSales(r.fnsku, r.store_name, dateOnly(baseDate), addDays(coverageEnd, 1));
          const coverageForecast = findForecastOnDate(r.fnsku, r.store_name, coverageEnd);
          const coverageEndingInventory = numOptional(coverageForecast?.ending_inventory);
          const coverageShortage = coverageEndingInventory == null
            ? Math.max(round(coverageDemand - n(r.afn_fulfillable_quantity), 2), 0)
            : Math.max(round(-coverageEndingInventory, 2), 0);
          const coverageSuggestedQty = roundUpToStep(coverageShortage, demandStep);
          const rowPendingKey = pendingKey(r);
          const inventoryLockQty = round(inventoryLockMap.get(rowPendingKey) || 0, 2);
          const pendingShipmentQty = round(pendingShipmentMap.get(rowPendingKey) || 0, 2);
          const pendingAllocationQty = round(inventoryLockQty + pendingShipmentQty, 2);
          const domesticItems = domesticMap.get(`${r.fnsku}|${r.sku}`) || [];
          const localItems = domesticItems.filter(item => ['中转仓', '供应商仓', '其他本地仓'].includes(warehouseRole(item)));
          const transferItems = localItems.filter(item => warehouseRole(item) === '中转仓');
          const supplierItems = localItems.filter(item => warehouseRole(item) === '供应商仓');
          const domesticTotalQty = round(localItems.reduce((sum, item) => sum + n(item.product_total), 0), 2);
          const transferTotalQty = round(transferItems.reduce((sum, item) => sum + n(item.product_total), 0), 2);
          const supplierTotalQty = round(supplierItems.reduce((sum, item) => sum + n(item.product_total), 0), 2);
          const availableQty = round(localItems.reduce((sum, item) => sum + domesticAvailableQty(item), 0), 2);
          const inboundQty = round(localItems.reduce((sum, item) => sum + domesticInboundQty(item), 0), 2);
          const availableWithInboundQty = round(availableQty + inboundQty, 2);
          const totalShortageQty = Math.max(round(plannedQty - domesticTotalQty, 2), 0);
          const availableShortageQty = Math.max(round(plannedQty - availableQty, 2), 0);
          const adjustedShipmentQty = plannedQty > domesticTotalQty
            ? domesticTotalQty
            : plannedQty > availableWithInboundQty
              ? availableQty
              : plannedQty;
          const inventoryStatus = plannedQty > domesticTotalQty
            ? '超发'
            : plannedQty <= availableQty
              ? '库存充足'
              : plannedQty <= availableWithInboundQty
                ? '可用不足在途覆盖'
                : '可用不足';
          const stockRule = ruleMap.get(ruleKey(r.store_name, r.sku, r.msku, r.fnsku));
          const rawLogisticsChannel = stockRule?.firstLegChannel || r.first_leg_logistics_channel || '待确认';
          const logisticsChannel = String(rawLogisticsChannel).includes('快船')
            ? '美森'
            : String(rawLogisticsChannel).includes('慢船')
              ? '慢船'
              : rawLogisticsChannel;
          const forecastSuggestedQty = round(adjustedWeeklyDemand.reduce((sum, qty) => sum + qty, 0), 2);
          const wholeBoxDemandDiff = round(boxCalc.wholeBoxQty - forecastSuggestedQty, 2);
          const extraWeeklyQty = [0, 0, 0];
          if (wholeBoxDemandDiff > 0) {
            const shipWeekIndexes = adjustedWeeklyDemand
              .map((qty, index) => ({ qty, index }))
              .filter(item => item.qty > 0)
              .map(item => item.index);
            const targetWeekIndexes = shipWeekIndexes.length ? shipWeekIndexes : [tooLateForCurrentWeek ? 1 : 0];
            if (wholeBoxDemandDiff < 100 || !boxPcs) {
              extraWeeklyQty[targetWeekIndexes[0]] = wholeBoxDemandDiff;
            } else {
              const fullBoxes = Math.floor(wholeBoxDemandDiff / boxPcs);
              const baseBoxes = Math.floor(fullBoxes / targetWeekIndexes.length);
              let remainderBoxes = fullBoxes % targetWeekIndexes.length;
              targetWeekIndexes.forEach(index => {
                const boxesForWeek = baseBoxes + (remainderBoxes > 0 ? 1 : 0);
                if (remainderBoxes > 0) remainderBoxes -= 1;
                extraWeeklyQty[index] = round(boxesForWeek * boxPcs, 2);
              });
            }
          }
          const totalWeeklyShipmentQty = adjustedWeeklyDemand.map((qty, index) => round(qty + extraWeeklyQty[index], 2));
          const totalShipmentQty = round(totalWeeklyShipmentQty.reduce((sum, qty) => sum + qty, 0), 2);
          const isFastChannel = String(logisticsChannel).includes('美森') || String(rawLogisticsChannel).includes('快船');
          const masonWeeklyQty = isFastChannel ? totalWeeklyShipmentQty : [0, 0, 0];
          const regularWeeklyQty = isFastChannel ? [0, 0, 0] : totalWeeklyShipmentQty;
          const highInventoryDays = Math.max(numOr(r.fnsku_available_days_4, r.fnsku_available_days_1), n(r.sellable_days));
          const isSeasonalSlow = String(r.msku_sales_property || '').includes('滞') || String(r.seasonal_attribute || r.season_attribute || '').includes('季节');
          const highInventoryHit = highInventoryDays >= 90 && isSeasonalSlow;
          const stockoutRiskHit = String(r.fnsku_out_of_stock_risk_1 || '').includes('断') || (r.sellable_days != null && n(r.sellable_days) <= n(r.FBA_delivery_time_fn));
          const channelNeedsFastShip = stockoutRiskHit && String(rawLogisticsChannel).includes('慢船');
          const returnQty = n(r.first_return_qty || r.return_quantity || r.return_qty);
          const inventoryLimitedQty = plannedQty > domesticTotalQty
            ? domesticTotalQty
            : plannedQty > availableWithInboundQty
              ? availableQty
              : plannedQty;
          const ruleSuggestedQty = highInventoryHit
            ? 0
            : Math.min(
              Math.max(forecastSuggestedQty, coverageSuggestedQty),
              Math.max(inventoryLimitedQty, 0),
            );
          const ruleRemark = [
            shipmentRemark,
            highInventoryHit ? `可售天数${round(highInventoryDays, 0)}大于90，建议取消或减少发货` : '',
            coverageSuggestedQty > 0 ? `发到${dateKey(coverageEnd)}需补${coverageSuggestedQty}` : '',
            channelNeedsFastShip ? '慢船可能断货，建议改美森' : '',
            returnQty > 0 ? `退回${returnQty}需单独重建计划` : '',
            inventoryLimitedQty < plannedQty ? `库存不足，发货量限制为${inventoryLimitedQty}` : '',
          ].filter(Boolean).join('；');
          const sizeClass = classifyProductSize(r.size, r.sku_name, r.msku);
          const transparentStatus = transparentPlanStatus(r);
          const warehouse = allocateDomesticWarehouses(localItems, Math.min(plannedQty, Math.max(availableWithInboundQty, domesticTotalQty)));
          const supplier = r.seller_id || r.product_manager || '待确认';
          const groupKey = [
            r.store_name || '',
            dateKey(r.start_dates0),
            sizeClass,
            transparentStatus,
            warehouse || supplier,
          ].join('|');
          const action = inventoryStatus === '库存充足'
            ? '按计划发货'
            : inventoryStatus === '可用不足在途覆盖'
              ? '按计划发货；在途库存按发货计划货到时间参与覆盖'
              : inventoryStatus === '超发'
                ? `国内总库存不足，需加急采购${totalShortageQty}；若无法按发货计划货到时间覆盖，则发货量控制为${adjustedShipmentQty}`
                : `可用及在途不足，发货量控制为${adjustedShipmentQty}；如有快船/慢船拆分，优先保留快船/美森，减少慢船`;
          const shipmentT1 = shipmentT0 ? addDays(shipmentT0, shipmentFrequency) : null;
          const templateValues = shipmentPlanHeaders(headerShipDates).map(() => '');
          const put = (index: number, value: any) => { templateValues[index] = value ?? ''; };
          put(0, '');
          put(1, `${r.store_name || ''}${r.msku || ''}${r.fnsku || ''}`);
          put(2, r.sales_apartment);
          put(3, r.salesman);
          put(4, r.store_name);
          put(5, r.msku);
          put(6, r.fnsku);
          put(7, r.asin);
          put(8, r.sku);
          put(9, r.sku_name);
          put(10, r.size);
          put(11, r.parent_asin);
          put(12, r.product_manager);
          put(13, r.country_code);
          put(14, r.channel);
          put(15, r.brand);
          put(16, r.seller_id);
          put(17, r.country_code);
          put(19, r.colour);
          put(20, r.color);
          put(21, r.size);
          put(22, r.msku_sales_property);
          put(23, r.msku_product_property || r.pi_product_material || r.pi_product_name);
          put(24, r.msku_isattract);
          put(25, r.seasonality);
          put(26, r.msku_status);
          put(27, r.msku_life_process);
          put(30, r.logistics_model);
          put(31, r.first_leg_logistics_channel);
          put(32, r.order_duration);
          put(33, r.production_duration);
          put(34, r.local_warehouse_pick_time);
          put(35, r.overseas_warehouse_pick_time);
          put(36, r.local_to_FBA_time);
          put(37, r.local_to_overseas_warehouse_time);
          put(38, r.overseas_to_FBA_time);
          put(39, r.db_next_oversell_rate);
          put(40, r.safety_stock_days_sales);
          put(42, r.logistics_safety_stock_days);
          put(43, r.production_safety_stock_days);
          put(44, r.fba_safety_days_fn);
          put(45, r.overseas_warehouse_safety_days);
          put(46, r.local_warehouse_safety_days);
          put(47, r.FBA_delivery_time_fn);
          put(48, r.overseas_warehouse_delivery_time_fn);
          put(49, r.local_warehouse_delivery_time_fn);
          put(50, r.afn_fulfillable_quantity);
          put(51, r.reserved_fc_transfers);
          put(52, r.reserved_fc_processing);
          put(53, r.afn_inbound_receiving_quantity);
          put(54, r.afn_inbound_working_quantity);
          put(55, r.planned_quantity);
          put(56, r.stock_up_num);
          put(57, r.overseas_warehouse_quantity);
          put(58, r.oversease_afn_inbound_shipped_quantity);
          put(59, r.procurement_plan_quantity);
          put(60, r.local_warehouse_quantity);
          put(61, r.local_afn_inbound_shipped_quantity);
          put(62, r.quantity_receive);
          put(63, r.procurement_plan_quantity);
          put(64, r.fba_warehouse_quantity);
          put(65, r.overseas_warehouse_quantity);
          put(66, r.oversease_afn_inbound_shipped_quantity);
          put(67, r.local_warehouse_quantity);
          put(68, r.local_afn_inbound_shipped_quantity);
          put(69, r.profit_rate_90d);
          put(70, r.fnsku_inventory_1);
          put(71, r.fnsku_inventory_2);
          put(72, r.fnsku_inventory_3);
          put(73, r.fnsku_inventory_4);
          put(74, r.fnsku_inventory_5);
          put(75, r.fnsku_inventory_6);
          put(76, r.fnsku_available_days_1);
          put(77, r.fnsku_available_days_2);
          put(78, r.fnsku_available_days_3);
          put(79, r.fnsku_available_days_4);
          put(80, r.fnsku_available_days_5);
          put(81, r.fnsku_available_days_6);
          put(82, r.fnsku_restocking_countdown_1);
          put(83, r.fnsku_restocking_countdown_2);
          put(84, r.fnsku_restocking_countdown_3);
          put(85, r.fnsku_restocking_countdown_4);
          put(86, r.fnsku_restocking_countdown_5);
          put(87, r.fnsku_restocking_countdown_6);
          put(88, r.fnsku_out_of_stock_risk_1);
          put(98, r.inv_age_181_to_270_days);
          put(99, r.inv_age_271_to_330_days);
          put(100, r.inv_age_331_to_365_days);
          put(101, r.inv_age_365_plus_days);
          put(102, r.sale_quantity_7);
          put(103, r.sale_quantity_14);
          put(104, r.sale_quantity_30);
          put(105, r.sale_quantity_60);
          put(106, r.sale_quantity_90);
          put(140, r.future_15d_sales);
          put(141, r.future_30d_sales);
          put(142, r.future_45d_sales);
          put(143, r.future_60d_sales);
          put(144, r.future_75d_sales);
          put(145, r.future_90d_sales);
          put(146, round(n(r.basic_purchase_quantity), 2));
          put(147, dateKey(r.start_dates));
          put(148, dateKey(r.end_dates));
          put(149, round(n(r.xiuzhenliang), 2));
          put(150, round(n(r.jypurchase_quantity), 2));
          put(156, domesticTotalQty);
          put(157, pendingAllocationQty);
          put(158, coverageEndingInventory ?? '');
          put(159, supplier);
          put(160, boxCalc.boxPcs || '');
          put(161, dateKey(shipmentT0));
          put(162, dateKey(shipmentT1));
          put(163, dateKey(r.start_dates0));
          put(164, dateKey(r.end_dates0));
          put(165, round(n(r.basic_fh_quantity), 2));
          put(166, round(n(r.fhxiuzhenliang), 2));
          put(167, plannedQty);
          put(168, boxCalc.wholeBoxQty);
          put(169, pendingAllocationQty);
          put(172, wholeBoxDemandDiff);
          put(173, masonWeeklyQty[0]);
          put(174, masonWeeklyQty[1]);
          put(175, masonWeeklyQty[2]);
          put(176, regularWeeklyQty[0]);
          put(177, regularWeeklyQty[1]);
          put(178, regularWeeklyQty[2]);
          put(179, totalWeeklyShipmentQty[0]);
          put(180, totalWeeklyShipmentQty[1]);
          put(181, totalWeeklyShipmentQty[2]);
          put(182, totalShipmentQty);
          put(183, shipmentRemark);
          put(184, weeklyDemand[0].demandQty);
          put(185, weeklyDemand[1].demandQty);
          put(186, weeklyDemand[2].demandQty);
          put(187, weeklyDemand[0].demandQty);
          put(188, weeklyDemand[1].demandQty);
          put(189, weeklyDemand[2].demandQty);
          put(190, adjustedWeeklyDemand[0]);
          put(191, adjustedWeeklyDemand[1]);
          put(192, adjustedWeeklyDemand[2]);
          put(193, forecastSuggestedQty);
          put(194, ruleRemark);
          put(195, action);

          return {
            groupKey,
            values: templateValues,
            plannedQty,
            wholeBoxShipmentQty: boxCalc.wholeBoxQty,
            week1DemandQty: adjustedWeeklyDemand[0],
            week2DemandQty: adjustedWeeklyDemand[1],
            week3DemandQty: adjustedWeeklyDemand[2],
            week1ShipmentQty: totalWeeklyShipmentQty[0],
            week2ShipmentQty: totalWeeklyShipmentQty[1],
            week3ShipmentQty: totalWeeklyShipmentQty[2],
            totalShipmentQty,
            ruleSuggestedQty,
            adjustedShipmentQty,
            domesticTotalQty,
            transferTotalQty,
            supplierTotalQty,
            availableQty,
            pendingAllocationQty,
            inboundQty,
            availableWithInboundQty,
            totalShortageQty,
            availableShortageQty,
            inventoryStatus,
            store: r.store_name,
            planDate: dateKey(r.start_dates0),
            sizeClass,
            transparentStatus,
            warehouse,
            supplier,
            logisticsChannel,
          };
        });

      const detailHeader = shipmentPlanHeaders(headerShipDates);

      const groupMap = new Map<string, {
        row: typeof planRows[number];
        skuCount: number;
        plannedQty: number;
        wholeBoxShipmentQty: number;
        week1DemandQty: number;
        week2DemandQty: number;
        week3DemandQty: number;
        ruleSuggestedQty: number;
        adjustedShipmentQty: number;
        domesticTotalQty: number;
        transferTotalQty: number;
        supplierTotalQty: number;
        availableQty: number;
        pendingAllocationQty: number;
        inboundQty: number;
        availableWithInboundQty: number;
        totalShortageQty: number;
        availableShortageQty: number;
        statuses: Set<string>;
      }>();
      planRows.forEach(item => {
        const current = groupMap.get(item.groupKey) || {
          row: item,
          skuCount: 0,
          plannedQty: 0,
          wholeBoxShipmentQty: 0,
          week1DemandQty: 0,
          week2DemandQty: 0,
          week3DemandQty: 0,
          ruleSuggestedQty: 0,
          adjustedShipmentQty: 0,
          domesticTotalQty: 0,
          transferTotalQty: 0,
          supplierTotalQty: 0,
          availableQty: 0,
          pendingAllocationQty: 0,
          inboundQty: 0,
          availableWithInboundQty: 0,
          totalShortageQty: 0,
          availableShortageQty: 0,
          statuses: new Set<string>(),
        };
        current.skuCount += 1;
        current.plannedQty += item.plannedQty;
        current.wholeBoxShipmentQty += item.wholeBoxShipmentQty;
        current.week1DemandQty += item.week1DemandQty;
        current.week2DemandQty += item.week2DemandQty;
        current.week3DemandQty += item.week3DemandQty;
        current.ruleSuggestedQty += item.ruleSuggestedQty;
        current.adjustedShipmentQty += item.adjustedShipmentQty;
        current.domesticTotalQty += item.domesticTotalQty;
        current.transferTotalQty += item.transferTotalQty;
        current.supplierTotalQty += item.supplierTotalQty;
        current.availableQty += item.availableQty;
        current.pendingAllocationQty += item.pendingAllocationQty;
        current.inboundQty += item.inboundQty;
        current.availableWithInboundQty += item.availableWithInboundQty;
        current.totalShortageQty += item.totalShortageQty;
        current.availableShortageQty += item.availableShortageQty;
        current.statuses.add(item.inventoryStatus);
        groupMap.set(item.groupKey, current);
      });

      const groupHeader = [
        '货件合并key', '店铺', '计划发货时间', '尺寸类型', '透明计划状态', '仓库', '供应商/责任方',
        '建议物流渠道', 'SKU数', '总计划发货量', '总整箱发货量', '建议调整后发货量',
        '规则建议发货量合计', '第1周需求量合计', '第2周需求量合计', '第3周需求量合计',
        '国内总库存合计', '中转仓库存合计', '供应商仓库存合计',
        '国内可用库存合计', '待配货合计', '国内在途库存合计', '可用+在途库存合计',
        '超发数量合计', '可用缺口数量合计', '库存校验状态', '是否可合并', '异常原因',
      ];
      const groupRows = Array.from(groupMap.entries()).map(([key, group]) => {
        const status = group.plannedQty > group.domesticTotalQty
          ? '超发'
          : group.plannedQty <= group.availableQty
            ? '库存充足'
            : group.plannedQty <= group.availableWithInboundQty
              ? '可用不足在途覆盖'
              : '可用不足';
        const canMerge = status !== '超发' && group.row.logisticsChannel !== '待确认' ? '是' : '待确认';
        const issue = [
          status === '超发' ? '国内总库存不足' : '',
          status === '可用不足' ? '可用及在途不足' : '',
          status === '可用不足在途覆盖' ? '需关注在途按计划到货' : '',
          group.row.logisticsChannel === '待确认' ? '物流渠道待确认' : '',
          group.row.warehouse === '待确认' ? '仓库待确认' : '',
        ].filter(Boolean).join('；');
        return [
          key,
          group.row.store,
          group.row.planDate,
          group.row.sizeClass,
          group.row.transparentStatus,
          group.row.warehouse,
          group.row.supplier,
          group.row.logisticsChannel,
          group.skuCount,
          round(group.plannedQty, 2),
          round(group.wholeBoxShipmentQty, 2),
          round(group.adjustedShipmentQty, 2),
          round(group.ruleSuggestedQty, 2),
          round(group.week1DemandQty, 2),
          round(group.week2DemandQty, 2),
          round(group.week3DemandQty, 2),
          round(group.domesticTotalQty, 2),
          round(group.transferTotalQty, 2),
          round(group.supplierTotalQty, 2),
          round(group.availableQty, 2),
          round(group.pendingAllocationQty, 2),
          round(group.inboundQty, 2),
          round(group.availableWithInboundQty, 2),
          round(group.totalShortageQty, 2),
          round(group.availableShortageQty, 2),
          status,
          canMerge,
          issue,
        ];
      });

      const rules = [
        ['项目', '说明'],
        ['计划来源', `${INVENTORY_BASE_TABLE} 全量行；无建议发货量的行保留，发货列按0输出。`],
        ['计划发货时间', '使用底表 start_dates0，不使用验证日期fallback。'],
        ['计划发货量', '使用底表 jyfahuo_quantity。'],
        ['整箱发货量', `单箱数量来自 temp_fnsku_boxing.cg_box_pcs；半箱供应商（当前：${halfBoxSupplierText || '无'}）按0.5箱取整，其余按爆旺/平销/滞销规则取整。`],
        ['周需求量', '第1/2/3周发货日固定为选择日期后的最近周五及后续两个周五；到货日=发货日+FBA交付时长_fnsku；需求窗口=到货日+1到到货日+7；汇总 dim_inventory_forecast_v1_fh.expected_sales 后按取整步长向上取整。'],
        ['建单太晚顺延', '按自然周判断：若发货T0与选择日期后的最近周五处于同一自然周，备注“建单太晚，无法当周发货”，第1周需求量直接置0，不并入第2周。'],
        ['三周发货拆分', '先计算整箱发货量-三周发货总数。差值大于0且小于100时，差值放入第一次实际发货时间；差值大于等于100时，按完整箱数均分到有发货量的周，不按半箱拆分。按底表物流渠道拆到美森或普船列，并输出每周合计与合计总发货数量。'],
        ['覆盖截止日建议量', '覆盖截止日期输入为空时默认使用每行发货T3(end_dates0)；手动填写日期时使用填写值。按覆盖截止日读取 dim_inventory_forecast_v1_fh.ending_inventory；若期末库存为负，则按缺口并结合整箱/半箱步长向上取整。缺失期末库存时回退为覆盖期销量-当前FBA可售。'],
        ['预估修正建议量', '使用顺延后的第1/2/3周需求量合计，作为按预估销量修正后的建议量。'],
        ['库存过高取消/减少', '若可售天数达到90天且为滞销/季节类，则规则建议发货量置0，并输出库存过高备注。'],
        ['断货风险改美森', '若存在断货风险且原渠道为慢船，则规则建议渠道改为美森。'],
        ['库存不足限制发货', '若计划发货量超过国内总库存或可用+在途，规则建议量限制到当前可支持数量。'],
        ['退回货件重建计划', '预留退回数量字段入口；当行数据存在退回数量时，输出退回重建计划备注。'],
        ['国内库存来源', 'dwd_lingxing_inventory_details 通过 dwd_lingxing_sc_warehouse.wid 取得仓库名，再通过 dim_lingxing_warehouse_mapping 识别本地仓/海外仓。'],
        ['国内总库存', 'mapping.type=本地仓的 product_total 汇总。'],
        ['国内可用库存', '优先使用 available_inventory_box_qty；为空时使用 product_valid_num。'],
        ['待配货', '待配货 = 选择日期 ods_lingxing_inventory_details.product_lock_num + dwd_lingxing_inbound_shipment_list_incr 中 status=-1 的 relate_list[].num；按 ASIN/FNSKU/SKU 匹配并去重。'],
        ['国内在途库存', 'quantity_receive + product_onway。'],
        ['库存核对', '发货量 > 国内总库存为超发；国内可用库存 >= 发货量为库存充足；可用不足但可用+在途覆盖时保留计划并提示关注在途；可用+在途不足时建议扣减到可用库存。'],
        ['发货仓库分配', '中转仓优先，其次供应商仓，再其他本地仓；供应商仓不再区分淘汰/分流状态。'],
        ['货件合并条件', '同一店铺 + 相同计划发货时间 + 相同尺寸类型 + 相同透明计划状态 + 同一仓库/供应商。'],
        ['物流渠道', '优先使用导入备货规则的头程物流渠道，其次使用底表 first_leg_logistics_channel；快船按美森展示，慢船按慢船展示。'],
      ];
      const domesticDetailHeader = [
        'FNSKU', 'SKU', 'wid', '仓库名', '业务仓库类型', '仓库角色', 'seller_id',
        '实际库存总量', '可用库存', '待检待上架', '锁定量', '待到货量', '调拨在途', '可用+在途',
      ];
      const domesticDetailRows = domesticRows.map(row => [
        row.fnsku,
        row.sku,
        row.wid,
        row.warehouse_name,
        row.warehouse_business_type || '',
        warehouseRole(row),
        row.seller_id,
        n(row.product_total),
        domesticAvailableQty(row),
        n(row.product_qc_num),
        n(row.product_lock_num),
        n(row.quantity_receive),
        n(row.product_onway),
        round(domesticAvailableQty(row) + domesticInboundQty(row), 2),
      ]);

      const workbook = XLSX.utils.book_new();
      const detailSheet = XLSX.utils.aoa_to_sheet([detailHeader, ...planRows.map(r => r.values)]);
      detailSheet['!cols'] = detailHeader.map(h => ({ wch: Math.max(10, Math.min(28, String(h).length * 1.7)) }));
      detailSheet['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: planRows.length, c: detailHeader.length - 1 } }) };
      const groupSheet = XLSX.utils.aoa_to_sheet([groupHeader, ...groupRows]);
      groupSheet['!cols'] = groupHeader.map(h => ({ wch: Math.max(10, Math.min(32, String(h).length * 1.7)) }));
      groupSheet['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: groupRows.length, c: groupHeader.length - 1 } }) };
      const domesticSheet = XLSX.utils.aoa_to_sheet([domesticDetailHeader, ...domesticDetailRows]);
      domesticSheet['!cols'] = domesticDetailHeader.map(h => ({ wch: Math.max(10, Math.min(24, String(h).length * 1.7)) }));
      domesticSheet['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: domesticDetailRows.length, c: domesticDetailHeader.length - 1 } }) };
      const ruleSheet = XLSX.utils.aoa_to_sheet(rules);
      ruleSheet['!cols'] = [{ wch: 18 }, { wch: 120 }];

      XLSX.utils.book_append_sheet(workbook, detailSheet, '周度发货计划明细');
      XLSX.utils.book_append_sheet(workbook, groupSheet, '货件合并汇总');
      XLSX.utils.book_append_sheet(workbook, domesticSheet, '国内库存明细');
      XLSX.utils.book_append_sheet(workbook, ruleSheet, '规则说明');
      XLSX.writeFile(workbook, `周度发货计划_${formatStamp()}.xlsx`);
      message.success(`已生成周度发货计划：明细 ${planRows.length} 条，货件组 ${groupRows.length} 个`);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '生成周度发货计划失败'));
    } finally {
      setExporting(false);
    }
  };

  const mainColumns = [
    { title: '风险', dataIndex: 'warning_type', width: 110, fixed: 'left' as const, render: (v: string, r: InventoryRow) => <Tag color={r.risk_level === '高' ? 'red' : r.risk_level === '中' ? 'orange' : v === '正常' ? 'green' : 'gold'}>{v}</Tag> },
    { title: '等级', dataIndex: 'risk_level', width: 80, fixed: 'left' as const },
    { title: 'MSKU', dataIndex: 'msku', width: 150, fixed: 'left' as const },
    { title: '店铺', dataIndex: 'store_name', width: 120 },
    { title: 'FNSKU', dataIndex: 'fnsku', width: 130 },
    { title: 'ASIN', dataIndex: 'asin', width: 120 },
    { title: '负责人', dataIndex: 'salesman', width: 100 },
    { title: 'FBA可售', dataIndex: 'afn_fulfillable_quantity', width: 100 },
    { title: '总库存', dataIndex: 'total_inventory', width: 100 },
    { title: '可售天数', dataIndex: 'sellable_days', width: 100, render: (v: number | null) => v == null ? '-' : v },
    { title: '提前期', dataIndex: 'lead_time_days', width: 90 },
    { title: '30天预测', dataIndex: 'forecast_30d_sales_checked', width: 110 },
    { title: '30天实际', dataIndex: 'actual_30d_sales', width: 110 },
    { title: '在途校验', dataIndex: 'in_transit_qty_checked', width: 100 },
    { title: '建议动作', dataIndex: 'suggested_action', width: 360 },
  ];

  const validationColumns = [
    { title: 'MSKU', dataIndex: 'msku', width: 150 },
    { title: '店铺', dataIndex: 'store_name', width: 120 },
    { title: '主表FBA可售', dataIndex: 'afn_fulfillable_quantity', width: 120 },
    { title: 'FBA明细校验', dataIndex: 'fba_inventory_checked', width: 120, render: (v: number | null) => v == null ? '-' : v },
    { title: '日粒度预测30天', dataIndex: 'forecast_30d_sales_checked', width: 140 },
    { title: '在途校验', dataIndex: 'in_transit_qty_checked', width: 100 },
    { title: '校验状态', dataIndex: 'validation_status', width: 100, render: (v: string) => <Tag color={v === '通过' ? 'green' : 'orange'}>{v}</Tag> },
    { title: '校验说明', dataIndex: 'validation_notes', width: 520 },
  ];

  const sourceRows = [
    ['主宽表', INVENTORY_BASE_TABLE, `MSKU库存、供应链规则、历史/未来销量汇总、已有风险字段；锁定读取当前生成快照，不使用备份表时间维度；基准日仅用于T0、预测和库存辅助校验计算，默认当天且可调整。当前基准日=${validationDate}`],
    ['日粒度预测', 'dim_lingxing_sales_estimates_everyday_incr', '未来30天每日销量预估校验'],
    ['实际销量', 'ads_lingxing_sc_sales_daily_new', '每日实际销量、广告花费、促销销量'],
    ['在途物流', 'in_transit_shipment', '在途数量、预计上架、延误与异常'],
    ['FBA库存核对', 'dwd_lingxing_fba_warehouse_detail', 'FBA可售、入库中、不可售等明细库存'],
    ['采购M3库存', 'dim_inventory_forecast_v1', '按 FNSKU + 店铺 + 采购T3前一天日期读取 ending_inventory 作为采购M3'],
    ['发货M3库存', 'dim_inventory_forecast_v1_fh', '按 FNSKU + 店铺 + 发货T3前一天日期读取 ending_inventory 作为发货M3'],
  ].map((r, i) => ({ key: i, role: r[0], table: r[1], purpose: r[2] }));

  return (
    <div className="inventory-lka-page" style={{ padding: 24, maxWidth: 1560, margin: '0 auto' }}>
      <div style={{ marginBottom: 18 }}>
        <Title level={3} style={{ margin: 0 }}><SafetyCertificateOutlined style={{ marginRight: 8 }} />LKA 库存智能预警</Title>
        <Text type="secondary">面向计划、运营、物流，基于 MSKU 粒度输出断货、冗余与库存异常预警，并展示跨表校验依据。</Text>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} md={5}><Input prefix={<SearchOutlined />} placeholder="筛选 MSKU" value={msku} onChange={e => setMsku(e.target.value)} /></Col>
          <Col xs={24} md={4}><Input placeholder="筛选店铺" value={storeName} onChange={e => setStoreName(e.target.value)} /></Col>
          <Col xs={24} md={3}>
            <Input
              type="date"
              value={validationDate}
              title="计算基准日"
              onChange={e => setValidationDate(e.target.value || DEFAULT_VALIDATION_DATE)}
            />
          </Col>
          <Col xs={24} md={4}>
            <Select
              value={styleType}
              onChange={setStyleType}
              style={{ width: '100%' }}
              options={[
                { label: '全部款式', value: 'all' },
                { label: '爆款', value: '爆' },
                { label: '旺款', value: '旺' },
                { label: '平款', value: '平' },
                { label: '滞销', value: '滞' },
                { label: '其他', value: 'other' },
              ]}
            />
          </Col>
          <Col xs={24} md={4}>
            <Input
              placeholder="半箱供应商"
              value={halfBoxSupplierText}
              onChange={e => setHalfBoxSupplierText(e.target.value)}
            />
          </Col>
          <Col xs={24} md={3}>
            <Input
              type="date"
              title="覆盖截止日期"
              placeholder="默认T3"
              value={coverageEndDate}
              onChange={e => setCoverageEndDate(e.target.value)}
            />
          </Col>
          <Col xs={12} md={4}><Button type="primary" icon={<ReloadOutlined />} loading={loading} onClick={load} style={{ width: '100%' }}>查询全部并校验</Button></Col>
          <Col xs={12} md={4}>
            <Upload
              accept=".xlsx,.xls"
              showUploadList={false}
              beforeUpload={(file) => {
                void importStockRules(file);
                return false;
              }}
            >
              <Button icon={<UploadOutlined />} style={{ width: '100%' }}>
                导入备货规则
              </Button>
            </Upload>
          </Col>
          <Col xs={12} md={4}>
            <Button
              icon={<FileExcelOutlined />}
              loading={exporting}
              disabled={loading || !data.length}
              onClick={exportShipmentTable}
              style={{ width: '100%' }}
            >
              一键验证发货量
            </Button>
          </Col>
          <Col xs={12} md={4}>
            <Button
              icon={<FileExcelOutlined />}
              loading={exporting}
              disabled={loading || !data.length}
              onClick={exportPurchaseTable}
              style={{ width: '100%' }}
            >
              一键验证采购量
            </Button>
          </Col>
          <Col xs={12} md={4}>
            <Button
              icon={<FileExcelOutlined />}
              loading={exporting}
              disabled={loading || !data.length}
              onClick={exportWeeklyShipmentPlan}
              style={{ width: '100%' }}
            >
              下载周度发货计划
            </Button>
          </Col>
        </Row>
        {ruleFileName && (
          <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
            当前备货规则：{ruleFileName}，已读取 {ruleMap.size} 条；发货频率、采购频率将优先使用该文件。
          </Text>
        )}
      </Card>

      {error && <Alert type="error" showIcon message="数据读取失败" description={error} style={{ marginBottom: 16 }} />}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={5}><Card size="small"><Statistic title="读取MSKU" value={summary.total} prefix={<DatabaseOutlined />} /></Card></Col>
        <Col xs={12} md={5}><Card size="small"><Statistic title="断货预警" value={summary.stockout} prefix={<WarningOutlined />} /></Card></Col>
        <Col xs={12} md={5}><Card size="small"><Statistic title="冗余库存" value={summary.redundant} prefix={<AlertOutlined />} /></Card></Col>
        <Col xs={12} md={5}><Card size="small"><Statistic title="库存异常" value={summary.anomaly} prefix={<AlertOutlined />} /></Card></Col>
        <Col xs={12} md={4}><Card size="small"><Statistic title="校验通过" value={summary.checked} prefix={<CheckCircleOutlined />} /></Card></Col>
      </Row>

      <Tabs
        items={[
          { key: 'warning', label: '预警结果', children: <Table rowKey="key" loading={loading} columns={mainColumns} dataSource={data.filter(r => r.warning_type !== '正常')} scroll={{ x: 1900 }} pagination={{ pageSize: 20, showSizeChanger: true }} /> },
          { key: 'all', label: '完整数据', children: <Table rowKey="key" loading={loading} columns={mainColumns} dataSource={data} scroll={{ x: 1900 }} pagination={{ pageSize: 20, showSizeChanger: true }} /> },
          { key: 'validation', label: '数据校验', children: <Table rowKey="key" loading={loading} columns={validationColumns} dataSource={data} scroll={{ x: 1600 }} pagination={{ pageSize: 20, showSizeChanger: true }} /> },
          { key: 'sources', label: '读取表', children: <Table rowKey="key" pagination={false} dataSource={sourceRows} columns={[{ title: '用途', dataIndex: 'role' }, { title: '表名', dataIndex: 'table' }, { title: '说明', dataIndex: 'purpose' }]} /> },
        ]}
      />
    </div>
  );
}
