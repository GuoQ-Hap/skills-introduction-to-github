import { useState, useMemo, useCallback, useEffect } from 'react';
import {
  Card,
  Tabs,
  Button,
  Table,
  Typography,
  Tag,
  Space,
  Spin,
  message,
  Select,
  Input,
  Alert,
  Tooltip,
  Statistic,
  Row,
  Col,
  Checkbox,
  InputNumber,
  Divider,
  Badge,
} from 'antd';
import {
  BarChartOutlined,
  ThunderboltOutlined,
  SearchOutlined,
  DownloadOutlined,
  LineChartOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  SettingOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { stiApi, listingApi, hasLocalDataRestrictions, type SQLExecResponse } from '../api';
import { RAINBOW, BTN_RAINBOW } from '../layouts/MainLayout';

const { Text } = Typography;
const R = BTN_RAINBOW;

/* ═════════════════════════════════════════════════════
   阈值配置类型与默认值
   ═════════════════════════════════════════════════════ */

export interface ThresholdConfig {
  // 表格颜色分级阈值（单位 %）
  ctrGreen: number;    // CTR% >= 此值 → 绿（优）
  ctrOrange: number;   // CTR% >= 此值 → 橙（良），否则红（差）
  cvrGreen: number;    // CVR% >= 此值 → 绿
  cvrOrange: number;   // CVR% >= 此值 → 橙
  acosGreen: number;   // ACOS% <= 此值 → 绿
  acosOrange: number;  // ACOS% <= 此值 → 橙
  cpcOrange: number;   // CPC >= 此值 → 橙（警示）
  cpcRed: number;      // CPC >= 此值 → 红
  // 诊断 SQL 判断阈值（单位 %）
  diagCtrAbs: number;  // 产品 CTR 绝对值低于此值时触发（默认 0.3%）
  diagCvrAbs: number;  // 产品 CVR 绝对值低于此值时触发（默认 10%）
  diagSessDec: number; // 流量下滑超过此值时触发（默认 20%）
}

const DEFAULT_THRESHOLD: ThresholdConfig = {
  ctrGreen: 0.30, ctrOrange: 0.15,
  cvrGreen: 10, cvrOrange: 5,
  acosGreen: 20, acosOrange: 40,
  cpcOrange: 1.5, cpcRed: 3.0,
  diagCtrAbs: 0.3, diagCvrAbs: 10, diagSessDec: 20,
};

const THRESHOLD_STORE_KEY = 'leang_analysis_thresholds';

function loadThresholds(): ThresholdConfig {
  try {
    const raw = localStorage.getItem(THRESHOLD_STORE_KEY);
    if (raw) return { ...DEFAULT_THRESHOLD, ...JSON.parse(raw) };
  } catch { /* */ }
  return { ...DEFAULT_THRESHOLD };
}

function saveThresholds(cfg: ThresholdConfig) {
  try { localStorage.setItem(THRESHOLD_STORE_KEY, JSON.stringify(cfg)); } catch { /* */ }
}

/* ─── 颜色辅助函数 ─── */
function ctrColor(v: number, cfg: ThresholdConfig) {
  return v >= cfg.ctrGreen ? 'green' : v >= cfg.ctrOrange ? 'orange' : 'red';
}
function cvrColor(v: number, cfg: ThresholdConfig) {
  return v >= cfg.cvrGreen ? 'green' : v >= cfg.cvrOrange ? 'orange' : 'red';
}
function acosColor(v: number, cfg: ThresholdConfig) {
  return v <= cfg.acosGreen ? 'green' : v <= cfg.acosOrange ? 'orange' : 'red';
}
function cpcColor(v: number, cfg: ThresholdConfig) {
  return v >= cfg.cpcRed ? 'red' : v >= cfg.cpcOrange ? 'orange' : 'green';
}

/* ─── 分级标签渲染 ─── */
function GradeTag({ value, color, suffix = '%' }: { value: number; color: string; suffix?: string }) {
  const label = color === 'green' ? '优' : color === 'orange' ? '良' : '差';
  return (
    <Space size={2}>
      <Tag color={color}>{value}{suffix}</Tag>
      <Tag color={color} style={{ fontSize: 10, padding: '0 4px', margin: 0 }}>{label}</Tag>
    </Space>
  );
}

/* ═════════════════════════════════════════════════════
   阈值配置面板
   ═════════════════════════════════════════════════════ */

const CTR_PRESETS = [
  { label: '严格', value: 'strict', green: 0.5, orange: 0.3 },
  { label: '标准（默认）', value: 'standard', green: 0.30, orange: 0.15 },
  { label: '宽松', value: 'loose', green: 0.15, orange: 0.10 },
  { label: '自定义', value: 'custom' },
];
const CVR_PRESETS = [
  { label: '严格', value: 'strict', green: 15, orange: 10 },
  { label: '标准（默认）', value: 'standard', green: 10, orange: 5 },
  { label: '宽松', value: 'loose', green: 8, orange: 3 },
  { label: '自定义', value: 'custom' },
];
const ACOS_PRESETS = [
  { label: '严格', value: 'strict', green: 15, orange: 25 },
  { label: '标准（默认）', value: 'standard', green: 20, orange: 40 },
  { label: '宽松', value: 'loose', green: 30, orange: 60 },
  { label: '自定义', value: 'custom' },
];

function detectPreset(
  presets: typeof CTR_PRESETS,
  green: number,
  orange: number,
): string {
  const found = presets.find(p => p.green === green && p.orange === orange);
  return found?.value || 'custom';
}

function ThresholdPanel({ cfg, onChange }: {
  cfg: ThresholdConfig;
  onChange: (next: ThresholdConfig) => void;
}) {
  const set = useCallback((patch: Partial<ThresholdConfig>) => onChange({ ...cfg, ...patch }), [cfg, onChange]);

  const ctrPreset = detectPreset(CTR_PRESETS, cfg.ctrGreen, cfg.ctrOrange);
  const cvrPreset = detectPreset(CVR_PRESETS, cfg.cvrGreen, cfg.cvrOrange);
  const acosPreset = detectPreset(ACOS_PRESETS, cfg.acosGreen, cfg.acosOrange);

  const handleCtrPreset = (v: string) => {
    const p = CTR_PRESETS.find(x => x.value === v);
    if (p && p.green) set({ ctrGreen: p.green, ctrOrange: p.orange! });
  };
  const handleCvrPreset = (v: string) => {
    const p = CVR_PRESETS.find(x => x.value === v);
    if (p && p.green) set({ cvrGreen: p.green, cvrOrange: p.orange! });
  };
  const handleAcosPreset = (v: string) => {
    const p = ACOS_PRESETS.find(x => x.value === v);
    if (p && p.green) set({ acosGreen: p.green, acosOrange: p.orange! });
  };

  const presetSelect = (presets: typeof CTR_PRESETS, value: string, onPreset: (v: string) => void) => (
    <Select size="small" value={value} onChange={onPreset} style={{ width: 130 }}>
      {presets.map(p => <Select.Option key={p.value} value={p.value}>{p.label}</Select.Option>)}
    </Select>
  );

  const numInput = (val: number, onVal: (v: number) => void, suffix = '%', step = 0.05) => (
    <InputNumber
      size="small" value={val} step={step} min={0} max={999}
      formatter={v => `${v}${suffix}`}
      parser={v => Number(String(v).replace(suffix, ''))}
      onChange={v => v != null && onVal(v)}
      style={{ width: 90 }}
    />
  );

  return (
    <Card
      size="small"
      style={{ marginBottom: 16, borderRadius: 12, border: '1px dashed #d9d9d9', background: '#fafafa' }}
      title={
        <Space>
          <SettingOutlined style={{ color: '#FF9800' }} />
          <Text style={{ fontSize: 13 }}>数据分级阈值配置</Text>
          <Badge count="已保存" color="green" style={{ fontSize: 10 }} />
        </Space>
      }
      extra={
        <Button size="small" onClick={() => onChange({ ...DEFAULT_THRESHOLD })} style={{ fontSize: 12 }}>
          恢复默认
        </Button>
      }
    >
      <Row gutter={[16, 8]} align="middle">
        {/* CTR */}
        <Col span={24}>
          <Space size={4} wrap align="center">
            <Text style={{ fontSize: 12, width: 80 }}><Tag color="blue">CTR</Tag>分级：</Text>
            {presetSelect(CTR_PRESETS, ctrPreset, handleCtrPreset)}
            <Text style={{ fontSize: 11, color: '#999' }}>优 ≥</Text>
            {numInput(cfg.ctrGreen, v => set({ ctrGreen: v }), '%', 0.05)}
            <Text style={{ fontSize: 11, color: '#999' }}>良 ≥</Text>
            {numInput(cfg.ctrOrange, v => set({ ctrOrange: v }), '%', 0.05)}
            <Text style={{ fontSize: 11, color: '#bbb' }}>差 &lt; {cfg.ctrOrange}%</Text>
            <Tooltip title="CTR（点击率）= 点击数 / 展示数。优/良/差三级标准决定表格颜色。">
              <InfoCircleOutlined style={{ color: '#bbb', fontSize: 12 }} />
            </Tooltip>
          </Space>
        </Col>
        {/* CVR */}
        <Col span={24}>
          <Space size={4} wrap align="center">
            <Text style={{ fontSize: 12, width: 80 }}><Tag color="purple">CVR</Tag>分级：</Text>
            {presetSelect(CVR_PRESETS, cvrPreset, handleCvrPreset)}
            <Text style={{ fontSize: 11, color: '#999' }}>优 ≥</Text>
            {numInput(cfg.cvrGreen, v => set({ cvrGreen: v }), '%', 0.5)}
            <Text style={{ fontSize: 11, color: '#999' }}>良 ≥</Text>
            {numInput(cfg.cvrOrange, v => set({ cvrOrange: v }), '%', 0.5)}
            <Text style={{ fontSize: 11, color: '#bbb' }}>差 &lt; {cfg.cvrOrange}%</Text>
            <Tooltip title="CVR（转化率）= 广告订单数 / 点击数。">
              <InfoCircleOutlined style={{ color: '#bbb', fontSize: 12 }} />
            </Tooltip>
          </Space>
        </Col>
        {/* ACOS */}
        <Col span={24}>
          <Space size={4} wrap align="center">
            <Text style={{ fontSize: 12, width: 80 }}><Tag color="orange">ACOS</Tag>分级：</Text>
            {presetSelect(ACOS_PRESETS, acosPreset, handleAcosPreset)}
            <Text style={{ fontSize: 11, color: '#999' }}>优 ≤</Text>
            {numInput(cfg.acosGreen, v => set({ acosGreen: v }), '%', 1)}
            <Text style={{ fontSize: 11, color: '#999' }}>良 ≤</Text>
            {numInput(cfg.acosOrange, v => set({ acosOrange: v }), '%', 1)}
            <Text style={{ fontSize: 11, color: '#bbb' }}>差 &gt; {cfg.acosOrange}%</Text>
            <Tooltip title="ACOS（广告销售成本）= 广告花费 / 广告销售额。越低越好。">
              <InfoCircleOutlined style={{ color: '#bbb', fontSize: 12 }} />
            </Tooltip>
          </Space>
        </Col>
        {/* CPC */}
        <Col span={24}>
          <Space size={4} wrap align="center">
            <Text style={{ fontSize: 12, width: 80 }}><Tag color="cyan">CPC</Tag>分级：</Text>
            <Text style={{ fontSize: 11, color: '#999' }}>警示 ≥ $</Text>
            {numInput(cfg.cpcOrange, v => set({ cpcOrange: v }), '$', 0.1)}
            <Text style={{ fontSize: 11, color: '#999' }}>危险 ≥ $</Text>
            {numInput(cfg.cpcRed, v => set({ cpcRed: v }), '$', 0.1)}
            <Tooltip title="CPC（单次点击成本）。超过警示值显示橙色，超过危险值显示红色。">
              <InfoCircleOutlined style={{ color: '#bbb', fontSize: 12 }} />
            </Tooltip>
          </Space>
        </Col>

        <Col span={24}><Divider style={{ margin: '4px 0' }} /></Col>

        {/* 诊断阈值 */}
        <Col span={24}>
          <Space size={12} wrap align="center">
            <Text style={{ fontSize: 12, fontWeight: 600 }}>
              <ThunderboltOutlined style={{ color: '#FF9800' }} /> 诊断触发阈值：
            </Text>
            <Space size={4} align="center">
              <Text style={{ fontSize: 11, color: '#666' }}>CTR绝对值 &lt;</Text>
              <Select size="small" value={cfg.diagCtrAbs} onChange={v => set({ diagCtrAbs: v })} style={{ width: 90 }}>
                {[0.1, 0.2, 0.3, 0.5, 1.0].map(v => (
                  <Select.Option key={v} value={v}>{v}%{v === 0.3 ? '（默认）' : ''}</Select.Option>
                ))}
              </Select>
            </Space>
            <Text style={{ fontSize: 11, color: '#999' }}>且低于类目均值 → 标题+主图优化</Text>
          </Space>
        </Col>
        <Col span={24}>
          <Space size={12} wrap align="center">
            <Text style={{ fontSize: 12, width: 118 }} />
            <Space size={4} align="center">
              <Text style={{ fontSize: 11, color: '#666' }}>CVR绝对值 &lt;</Text>
              <Select size="small" value={cfg.diagCvrAbs} onChange={v => set({ diagCvrAbs: v })} style={{ width: 100 }}>
                {[5, 8, 10, 15, 20].map(v => (
                  <Select.Option key={v} value={v}>{v}%{v === 10 ? '（默认）' : ''}</Select.Option>
                ))}
              </Select>
            </Space>
            <Text style={{ fontSize: 11, color: '#999' }}>且低于类目均值 → 五点+A+优化</Text>
          </Space>
        </Col>
        <Col span={24}>
          <Space size={12} wrap align="center">
            <Text style={{ fontSize: 12, width: 118 }} />
            <Space size={4} align="center">
              <Text style={{ fontSize: 11, color: '#666' }}>流量下滑 &gt;</Text>
              <Select size="small" value={cfg.diagSessDec} onChange={v => set({ diagSessDec: v })} style={{ width: 110 }}>
                {[10, 15, 20, 30, 50].map(v => (
                  <Select.Option key={v} value={v}>{v}%{v === 20 ? '（默认）' : ''}</Select.Option>
                ))}
              </Select>
            </Space>
            <Text style={{ fontSize: 11, color: '#999' }}>且有库存 → 必须优化（排名下滑）</Text>
          </Space>
        </Col>
      </Row>
    </Card>
  );
}

/* ═════════════════════════════════════════════════════
   预定义分析 SQL
   ═════════════════════════════════════════════════════ */

function buildCategorySQL(dateRange: number) {
  return `SELECT
    category_2,
    COUNT(DISTINCT asin) AS asin_count,
    SUM(volume) AS total_volume,
    ROUND(SUM(amount), 2) AS total_sales,
    SUM(clicks) AS total_clicks,
    SUM(impressions) AS total_impressions,
    SUM(ad_order_quantity) AS total_ad_orders,
    ROUND(SUM(spend), 2) AS total_spend,
    ROUND(SUM(ad_sales_amount), 2) AS total_ad_sales,
    CASE WHEN SUM(impressions) > 0
         THEN ROUND(SUM(clicks) * 100.0 / SUM(impressions), 4)
         ELSE 0 END AS avg_ctr_pct,
    CASE WHEN SUM(clicks) > 0
         THEN ROUND(SUM(ad_order_quantity) * 100.0 / SUM(clicks), 4)
         ELSE 0 END AS avg_cvr_pct,
    CASE WHEN SUM(ad_sales_amount) > 0
         THEN ROUND(SUM(spend) * 100.0 / SUM(ad_sales_amount), 4)
         ELSE 0 END AS avg_acos_pct,
    CASE WHEN SUM(clicks) > 0
         THEN ROUND(SUM(spend) * 1.0 / SUM(clicks), 4)
         ELSE 0 END AS avg_cpc
FROM ads_lingxing_sc_sales_daily_new
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL ${dateRange} DAY)
  AND category_2 IS NOT NULL AND category_2 != ''
GROUP BY category_2
ORDER BY total_sales DESC
LIMIT 100`;
}

function buildAsinSQL(dateRange: number, country: string, asinFilter: string) {
  const wheres = [
    `a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL ${dateRange} DAY)`,
    `a.impressions > 0`,
    `a.category_2 IS NOT NULL AND a.category_2 != ''`,
  ];
  if (country) wheres.push(`a.country_code = '${country.replace(/'/g, '')}'`);
  if (asinFilter) wheres.push(`a.asin = '${asinFilter.replace(/'/g, '')}'`);

  return `SELECT
    a.asin,
    a.price_list_seller_sku AS msku,
    a.store_name,
    a.country_code,
    a.category_2,
    SUM(a.clicks) AS total_clicks,
    SUM(a.impressions) AS total_impressions,
    SUM(a.ad_order_quantity) AS total_ad_orders,
    ROUND(SUM(a.spend), 2) AS total_spend,
    ROUND(SUM(a.ad_sales_amount), 2) AS total_ad_sales,
    SUM(a.volume) AS total_volume,
    ROUND(SUM(a.amount), 2) AS total_amount,
    CASE WHEN SUM(a.impressions) > 0
         THEN ROUND(SUM(a.clicks) * 100.0 / SUM(a.impressions), 4)
         ELSE 0 END AS ctr_pct,
    CASE WHEN SUM(a.clicks) > 0
         THEN ROUND(SUM(a.ad_order_quantity) * 100.0 / SUM(a.clicks), 4)
         ELSE 0 END AS cvr_pct,
    CASE WHEN SUM(a.ad_sales_amount) > 0
         THEN ROUND(SUM(a.spend) * 100.0 / SUM(a.ad_sales_amount), 4)
         ELSE 0 END AS acos_pct
FROM ads_lingxing_sc_sales_daily_new a
WHERE ${wheres.join('\n  AND ')}
GROUP BY a.asin, a.price_list_seller_sku, a.store_name, a.country_code, a.category_2
ORDER BY total_amount DESC
LIMIT 200`;
}

/** 三维诊断 SQL 由后端 LSTA `triDimSqlService` 生成，与 `/lsta/fetch-with-diagnostics` 中 tri_dim 同源 */
export async function fetchTriDimDiagnosticSql(opts: {
  dateRange: number;
  dims?: ('ctr' | 'cvr' | 'sessions')[];
  asin?: string;
  page?: number;
  pageSize?: number;
  thresholds?: ThresholdConfig;
  row_filter?: boolean;
  include_count_sql?: boolean;
  salesApartment?: string;
}) {
  const t = opts.thresholds;
  const localRestricted = hasLocalDataRestrictions();
  const ps = localRestricted && !opts.asin ? 5000 : (opts.pageSize ?? (opts.asin ? 50 : 100));
  const { data } = await listingApi.triDimDiagnosticSql({
    date_range: opts.dateRange,
    asin: opts.asin,
    page: localRestricted && !opts.asin ? 1 : (opts.page ?? 1),
    page_size: ps,
    dims: opts.dims,
    row_filter: opts.row_filter ?? true,
    include_count_sql: opts.include_count_sql ?? false,
    thresholds: t
      ? { diag_ctr_abs: t.diagCtrAbs, diag_cvr_abs: t.diagCvrAbs, diag_sess_dec: t.diagSessDec }
      : undefined,
    sales_apartment: opts.salesApartment || undefined,
  });
  return { dataSql: data.data_sql, countSql: data.count_sql ?? undefined };
}

/* ═════════════════════════════════════════════════════
   通用 hooks
   ═════════════════════════════════════════════════════ */

function useQueryRunner(cacheKey: string) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SQLExecResponse | null>(() => {
    try { const r = sessionStorage.getItem(cacheKey); return r ? JSON.parse(r) : null; } catch { return null; }
  });
  const [error, setError] = useState('');
  const [executedSql, setExecutedSql] = useState('');

  const run = async (sql: string) => {
    setLoading(true);
    setError('');
    setResult(null);
    setExecutedSql(sql);
    try {
      const { data } = await stiApi.execSql(sql);
      if (data.error) { setError(data.error); }
      else {
        setResult(data);
        try { sessionStorage.setItem(cacheKey, JSON.stringify(data)); } catch {}
        return data;
      }
    } catch (e: any) { setError(e.message || '查询失败'); }
    finally { setLoading(false); }
    return null;
  };

  return { loading, result, error, executedSql, run };
}

function exportCSV(columns: string[], rows: Record<string, any>[], filename: string) {
  const header = columns.join(',');
  const body = rows.map(r => columns.map(c => {
    const v = r[c];
    const s = v == null ? '' : String(v);
    return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s;
  }).join(',')).join('\n');
  const blob = new Blob(['\uFEFF' + header + '\n' + body], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  message.success('CSV 导出成功');
}

/* ═════════════════════════════════════════════════════
   1. CTR/CVR 类目分析
   ═════════════════════════════════════════════════════ */

function CategoryAnalysis({ cfg }: { cfg: ThresholdConfig }) {
  const [dateRange, setDateRange] = useState(30);
  const q = useQueryRunner('da_category');

  const columns = useMemo(() => [
    { title: '二级类目', dataIndex: 'category_2', key: 'category_2', width: 180, fixed: 'left' as const,
      ellipsis: true },
    { title: 'ASIN数', dataIndex: 'asin_count', key: 'asin_count', width: 80, sorter: (a: any, b: any) => a.asin_count - b.asin_count },
    { title: '总销量', dataIndex: 'total_volume', key: 'total_volume', width: 90, sorter: (a: any, b: any) => a.total_volume - b.total_volume,
      render: (v: number) => v?.toLocaleString() },
    { title: '总销售额', dataIndex: 'total_sales', key: 'total_sales', width: 110, sorter: (a: any, b: any) => a.total_sales - b.total_sales,
      render: (v: number) => `$${v?.toLocaleString()}` },
    { title: '总点击', dataIndex: 'total_clicks', key: 'total_clicks', width: 90, sorter: (a: any, b: any) => a.total_clicks - b.total_clicks,
      render: (v: number) => v?.toLocaleString() },
    { title: '总展示', dataIndex: 'total_impressions', key: 'total_impressions', width: 100, sorter: (a: any, b: any) => a.total_impressions - b.total_impressions,
      render: (v: number) => v?.toLocaleString() },
    { title: `CTR% (优≥${cfg.ctrGreen}%)`, dataIndex: 'avg_ctr_pct', key: 'avg_ctr_pct', width: 110,
      sorter: (a: any, b: any) => a.avg_ctr_pct - b.avg_ctr_pct,
      render: (v: number) => <GradeTag value={v} color={ctrColor(v, cfg)} /> },
    { title: `CVR% (优≥${cfg.cvrGreen}%)`, dataIndex: 'avg_cvr_pct', key: 'avg_cvr_pct', width: 110,
      sorter: (a: any, b: any) => a.avg_cvr_pct - b.avg_cvr_pct,
      render: (v: number) => <GradeTag value={v} color={cvrColor(v, cfg)} /> },
    { title: `ACOS% (优≤${cfg.acosGreen}%)`, dataIndex: 'avg_acos_pct', key: 'avg_acos_pct', width: 120,
      sorter: (a: any, b: any) => a.avg_acos_pct - b.avg_acos_pct,
      render: (v: number) => <GradeTag value={v} color={acosColor(v, cfg)} /> },
    { title: `CPC (警≥$${cfg.cpcOrange})`, dataIndex: 'avg_cpc', key: 'avg_cpc', width: 110,
      sorter: (a: any, b: any) => a.avg_cpc - b.avg_cpc,
      render: (v: number) => <Tag color={cpcColor(v, cfg)}>${v}</Tag> },
    { title: '广告花费', dataIndex: 'total_spend', key: 'total_spend', width: 100, sorter: (a: any, b: any) => a.total_spend - b.total_spend,
      render: (v: number) => `$${v?.toLocaleString()}` },
  ], [cfg]);

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16, borderRadius: 12 }}>
        <Space wrap>
          <Text strong>时间范围：</Text>
          <Select value={dateRange} onChange={setDateRange} style={{ width: 120 }}
            options={[
              { value: 7, label: '近 7 天' }, { value: 14, label: '近 14 天' },
              { value: 30, label: '近 30 天' }, { value: 60, label: '近 60 天' },
              { value: 90, label: '近 90 天' },
            ]} />
          <Button type="primary" icon={<SearchOutlined />} loading={q.loading}
            onClick={() => q.run(buildCategorySQL(dateRange))}
            style={{ background: R[2] }}>
            开始分析
          </Button>
          {q.result && (
            <Button icon={<DownloadOutlined />}
              onClick={() => exportCSV(q.result!.columns, q.result!.rows, 'category_analysis')}>
              导出 CSV
            </Button>
          )}
          {q.result && <Tag color="blue">{q.result.row_count} 个类目</Tag>}
        </Space>
      </Card>

      {q.error && <Alert message="查询失败" description={q.error} type="error" showIcon closable style={{ marginBottom: 16 }} />}

      {q.loading && (
        <Card style={{ textAlign: 'center', padding: 60, borderRadius: 12 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}><Text type="secondary">正在分析类目数据...</Text></div>
        </Card>
      )}

      {q.result && !q.loading && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 10 }}>
                <Statistic title="类目总数" value={q.result.row_count} prefix={<BarChartOutlined />} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 10 }}>
                <Statistic title="总销售额" value={q.result.rows.reduce((s, r) => s + (Number(r.total_sales) || 0), 0)}
                  prefix="$" precision={0} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 10 }}>
                <Statistic title="平均 CTR" suffix="%"
                  value={(() => {
                    const tc = q.result!.rows.reduce((s, r) => s + (Number(r.total_clicks) || 0), 0);
                    const ti = q.result!.rows.reduce((s, r) => s + (Number(r.total_impressions) || 0), 0);
                    return ti > 0 ? (tc * 100 / ti).toFixed(4) : 0;
                  })()} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 10 }}>
                <Statistic title="平均 CVR" suffix="%"
                  value={(() => {
                    const to = q.result!.rows.reduce((s, r) => s + (Number(r.total_ad_orders) || 0), 0);
                    const tc = q.result!.rows.reduce((s, r) => s + (Number(r.total_clicks) || 0), 0);
                    return tc > 0 ? (to * 100 / tc).toFixed(4) : 0;
                  })()} />
              </Card>
            </Col>
          </Row>

          <Card size="small" style={{ borderRadius: 12 }}>
            <Table
              dataSource={q.result.rows.map((r, i) => ({ ...r, _key: i }))}
              columns={columns}
              rowKey="_key"
              size="small"
              scroll={{ x: 1200 }}
              pagination={{ pageSize: 20, showSizeChanger: true, showTotal: t => `共 ${t} 个类目` }}
            />
          </Card>
        </>
      )}
    </div>
  );
}

/* ═════════════════════════════════════════════════════
   2. ASIN 明细查询
   ═════════════════════════════════════════════════════ */

function AsinDetail({ cfg }: { cfg: ThresholdConfig }) {
  const [dateRange, setDateRange] = useState(30);
  const [country, setCountry] = useState('');
  const [asinFilter, setAsinFilter] = useState('');
  const q = useQueryRunner('da_asin');

  const columns = useMemo(() => [
    { title: 'ASIN', dataIndex: 'asin', key: 'asin', width: 120, fixed: 'left' as const },
    { title: 'MSKU', dataIndex: 'msku', key: 'msku', width: 140, ellipsis: true },
    { title: '店铺', dataIndex: 'store_name', key: 'store_name', width: 120, ellipsis: true },
    { title: '国家', dataIndex: 'country_code', key: 'country_code', width: 60 },
    { title: '类目', dataIndex: 'category_2', key: 'category_2', width: 150, ellipsis: true },
    { title: '点击', dataIndex: 'total_clicks', key: 'total_clicks', width: 80, sorter: (a: any, b: any) => a.total_clicks - b.total_clicks,
      render: (v: number) => v?.toLocaleString() },
    { title: '展示', dataIndex: 'total_impressions', key: 'total_impressions', width: 90, sorter: (a: any, b: any) => a.total_impressions - b.total_impressions,
      render: (v: number) => v?.toLocaleString() },
    { title: '销量', dataIndex: 'total_volume', key: 'total_volume', width: 80, sorter: (a: any, b: any) => a.total_volume - b.total_volume,
      render: (v: number) => v?.toLocaleString() },
    { title: '销售额', dataIndex: 'total_amount', key: 'total_amount', width: 100, sorter: (a: any, b: any) => a.total_amount - b.total_amount,
      render: (v: number) => `$${v?.toLocaleString()}` },
    { title: `CTR% (优≥${cfg.ctrGreen}%)`, dataIndex: 'ctr_pct', key: 'ctr_pct', width: 110,
      sorter: (a: any, b: any) => a.ctr_pct - b.ctr_pct,
      render: (v: number) => <GradeTag value={v} color={ctrColor(v, cfg)} /> },
    { title: `CVR% (优≥${cfg.cvrGreen}%)`, dataIndex: 'cvr_pct', key: 'cvr_pct', width: 110,
      sorter: (a: any, b: any) => a.cvr_pct - b.cvr_pct,
      render: (v: number) => <GradeTag value={v} color={cvrColor(v, cfg)} /> },
    { title: `ACOS% (优≤${cfg.acosGreen}%)`, dataIndex: 'acos_pct', key: 'acos_pct', width: 120,
      sorter: (a: any, b: any) => a.acos_pct - b.acos_pct,
      render: (v: number) => <GradeTag value={v} color={acosColor(v, cfg)} /> },
    { title: '广告花费', dataIndex: 'total_spend', key: 'total_spend', width: 90, sorter: (a: any, b: any) => a.total_spend - b.total_spend,
      render: (v: number) => `$${v?.toLocaleString()}` },
  ], [cfg]);

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16, borderRadius: 12 }}>
        <Space wrap>
          <Text strong>时间：</Text>
          <Select value={dateRange} onChange={setDateRange} style={{ width: 110 }}
            options={[
              { value: 7, label: '近 7 天' }, { value: 14, label: '近 14 天' },
              { value: 30, label: '近 30 天' }, { value: 60, label: '近 60 天' },
            ]} />
          <Text strong>国家：</Text>
          <Select value={country} onChange={setCountry} style={{ width: 100 }} allowClear placeholder="全部"
            options={[
              { value: 'US', label: 'US' }, { value: 'UK', label: 'UK' },
              { value: 'DE', label: 'DE' }, { value: 'JP', label: 'JP' },
              { value: 'CA', label: 'CA' }, { value: 'FR', label: 'FR' },
            ]} />
          <Text strong>ASIN：</Text>
          <Input placeholder="输入ASIN筛选" value={asinFilter} onChange={e => setAsinFilter(e.target.value)}
            maxLength={10} style={{ width: 130 }} allowClear />
          <Button type="primary" icon={<SearchOutlined />} loading={q.loading}
            onClick={() => q.run(buildAsinSQL(dateRange, country, asinFilter))}
            style={{ background: R[2] }}>
            查询
          </Button>
          {q.result && (
            <Button icon={<DownloadOutlined />}
              onClick={() => exportCSV(q.result!.columns, q.result!.rows, 'asin_detail')}>
              导出 CSV
            </Button>
          )}
          {q.result && <Tag color="blue">{q.result.row_count} 条记录</Tag>}
        </Space>
      </Card>

      {q.error && <Alert message="查询失败" description={q.error} type="error" showIcon closable style={{ marginBottom: 16 }} />}

      {q.loading && (
        <Card style={{ textAlign: 'center', padding: 60, borderRadius: 12 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}><Text type="secondary">正在查询 ASIN 明细...</Text></div>
        </Card>
      )}

      {q.result && !q.loading && (
        <Card size="small" style={{ borderRadius: 12 }}>
          <Table
            dataSource={q.result.rows.map((r, i) => ({ ...r, _key: i }))}
            columns={columns}
            rowKey="_key"
            size="small"
            scroll={{ x: 1400 }}
            pagination={{ pageSize: 20, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
          />
        </Card>
      )}
    </div>
  );
}

/* ═════════════════════════════════════════════════════
   3. 三维诊断报告
   ═════════════════════════════════════════════════════ */

type DiagDim = 'ctr' | 'cvr' | 'sessions';
const DIAG_DIM_OPTS: { value: DiagDim; label: string }[] = [
  { value: 'ctr', label: 'CTR 低（标题+主图）' },
  { value: 'cvr', label: 'CVR 低（五点+A+）' },
  { value: 'sessions', label: '流量下滑（必须优化）' },
];

function DiagnosticReport({ cfg }: { cfg: ThresholdConfig }) {
  const [dateRange, setDateRange] = useState(30);
  const [dims, setDims] = useState<DiagDim[]>(['ctr', 'cvr', 'sessions']);
  const [salesApartment, setSalesApartment] = useState<string>('');
  const [saOptions, setSaOptions] = useState<{ label: string; value: string }[]>([]);
  const [saLoading, setSaLoading] = useState(false);
  const q = useQueryRunner('da_diagnostic');
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [countLoading, setCountLoading] = useState(false);

  // 加载销售部门选项
  useEffect(() => {
    setSaLoading(true);
    stiApi.execSql(
      "SELECT DISTINCT sales_apartment FROM dim_lingxing_product_info WHERE sales_apartment IS NOT NULL AND sales_apartment != '' ORDER BY sales_apartment"
    ).then(res => {
      const opts = (res.data.rows || []).map((r: any) => ({
        label: String(r.sales_apartment),
        value: String(r.sales_apartment),
      }));
      setSaOptions(opts);
    }).catch(() => {}).finally(() => setSaLoading(false));
  }, []);

  const runDiagnostic = async (page = 1, ps = pageSize, d = dims, dr = dateRange, sa = salesApartment) => {
    setCurrentPage(page);
    setCountLoading(true);
    try {
      const localRestricted = hasLocalDataRestrictions();
      const { dataSql, countSql } = await fetchTriDimDiagnosticSql({
        dateRange: dr,
        dims: d,
        page: localRestricted ? 1 : page,
        pageSize: localRestricted ? 5000 : ps,
        thresholds: cfg,
        row_filter: true,
        include_count_sql: page === 1 && !localRestricted,
        salesApartment: sa,
      });
      const [countRes, dataRes] = await Promise.all([
        page === 1 && countSql && !localRestricted ? stiApi.execSql(countSql) : Promise.resolve(null),
        q.run(dataSql),
      ]);
      if (countRes?.data?.rows?.[0]?.total != null) {
        setTotal(Number(countRes.data.rows[0].total));
      } else if (localRestricted) {
        setTotal(dataRes?.row_count ?? 0);
      }
    } catch { /* handled by q.run */ }
    setCountLoading(false);
  };

  const columns = useMemo(() => [
    { title: 'ASIN', dataIndex: 'asin', key: 'asin', width: 120, fixed: 'left' as const },
    { title: 'MSKU', dataIndex: 'msku', key: 'msku', width: 130, ellipsis: true },
    { title: '店铺', dataIndex: 'store_name', key: 'store_name', width: 110, ellipsis: true },
    { title: '国家', dataIndex: 'country_code', key: 'cc', width: 55 },
    { title: '类目', dataIndex: 'category_2', key: 'category_2', width: 130, ellipsis: true },
    { title: '品牌', dataIndex: 'brand', key: 'brand', width: 90, ellipsis: true },
    { title: '销量', dataIndex: 'total_volume', key: 'vol', width: 70, sorter: (a: any, b: any) => a.total_volume - b.total_volume },
    { title: '销售额', dataIndex: 'total_amount', key: 'amt', width: 90, sorter: (a: any, b: any) => a.total_amount - b.total_amount,
      render: (v: number) => `$${v?.toLocaleString()}` },
    { title: `CTR%(触发<${cfg.diagCtrAbs}%)`, dataIndex: 'product_ctr_pct', key: 'pctr', width: 110,
      sorter: (a: any, b: any) => a.product_ctr_pct - b.product_ctr_pct,
      render: (v: number, r: any) => (
        <Tooltip title={`类目均值: ${r.cat_avg_ctr_pct}%，触发阈值: <${cfg.diagCtrAbs}%`}>
          <Tag color={r.flag_ctr_low ? 'red' : ctrColor(v, cfg)}>{v}%</Tag>
        </Tooltip>
      ) },
    { title: '类目CTR%', dataIndex: 'cat_avg_ctr_pct', key: 'cctr', width: 85 },
    { title: `CVR%(触发<${cfg.diagCvrAbs}%)`, dataIndex: 'product_cvr_pct', key: 'pcvr', width: 110,
      sorter: (a: any, b: any) => a.product_cvr_pct - b.product_cvr_pct,
      render: (v: number, r: any) => (
        <Tooltip title={`类目均值: ${r.cat_avg_cvr_pct}%，触发阈值: <${cfg.diagCvrAbs}%`}>
          <Tag color={r.flag_cvr_low ? 'red' : cvrColor(v, cfg)}>{v}%</Tag>
        </Tooltip>
      ) },
    { title: '类目CVR%', dataIndex: 'cat_avg_cvr_pct', key: 'ccvr', width: 85 },
    { title: `流量变化%(触发>-${cfg.diagSessDec}%)`, dataIndex: 'sessions_change_pct', key: 'schg', width: 130,
      sorter: (a: any, b: any) => (a.sessions_change_pct || 0) - (b.sessions_change_pct || 0),
      render: (v: number, r: any) => v != null ? (
        <Tag color={r.flag_sessions_decline ? 'red' : v < 0 ? 'orange' : 'green'}>
          {v > 0 ? '+' : ''}{v}%
        </Tag>
      ) : '-' },
    { title: '库存', dataIndex: 'avg_stock_qty', key: 'stk', width: 60 },
    { title: '命中', dataIndex: 'hit_count', key: 'hit', width: 55, sorter: (a: any, b: any) => a.hit_count - b.hit_count,
      render: (v: number) => (
        <Tag color={v >= 3 ? 'red' : v >= 2 ? 'orange' : 'blue'} style={{ fontWeight: 700 }}>{v}</Tag>
      ) },
    { title: '优化建议', dataIndex: 'optimization_actions', key: 'actions', width: 220,
      render: (v: string) => v ? (
        <Space size={2} wrap>
          {v.split(' | ').filter(Boolean).map((a, i) => (
            <Tag key={i} color={a.includes('必须') ? 'red' : a.includes('标题') ? 'orange' : 'blue'} style={{ fontSize: 11 }}>
              {a}
            </Tag>
          ))}
        </Space>
      ) : <CheckCircleOutlined style={{ color: '#10B981' }} /> },
    { title: '运营', dataIndex: 'salesman', key: 'sales', width: 80, ellipsis: true },
    { title: '产品经理', dataIndex: 'product_manager', key: 'pm', width: 80, ellipsis: true },
    { title: '销售部门', dataIndex: 'sales_apartment', key: 'sa', width: 100, ellipsis: true },
  ], []);

  const summary = useMemo(() => {
    if (!q.result) return null;
    const rows = q.result.rows;
    const ctrLow = rows.filter(r => r.flag_ctr_low).length;
    const cvrLow = rows.filter(r => r.flag_cvr_low).length;
    const sessDecline = rows.filter(r => r.flag_sessions_decline).length;
    const hit3 = rows.filter(r => r.hit_count >= 3).length;
    return { total, pageCount: rows.length, ctrLow, cvrLow, sessDecline, hit3 };
  }, [q.result, total]);

  return (
    <div>
      {/* 诊断规则说明 */}
      <Alert
        message="三维诊断规则（当前阈值配置）"
        description={
          <Space direction="vertical" size={2} style={{ fontSize: 12 }}>
            <span><WarningOutlined style={{ color: RAINBOW[1].from }} /> <strong>维度1 - CTR 低于类目均值</strong>：产品 CTR &lt; 类目均值 且 CTR &lt; <Tag color="orange">{cfg.diagCtrAbs}%</Tag> → 优化标题 + 主图</span>
            <span><ExclamationCircleOutlined style={{ color: RAINBOW[3].from }} /> <strong>维度2 - CVR 低于类目均值</strong>：产品 CVR &lt; 类目均值 且 CVR &lt; <Tag color="orange">{cfg.diagCvrAbs}%</Tag> → 优化五点描述 + A+ 页面</span>
            <span><LineChartOutlined style={{ color: RAINBOW[4].from }} /> <strong>维度3 - 流量持续下滑</strong>：近期 sessions 下滑 &gt; <Tag color="orange">{cfg.diagSessDec}%</Tag> 且无断货 → 必须优化</span>
          </Space>
        }
        type="info" showIcon closable style={{ marginBottom: 16, borderRadius: 12 }}
      />

      <Card size="small" style={{ marginBottom: 16, borderRadius: 12 }}>
        <Space wrap style={{ marginBottom: 8 }}>
          <Text strong>分析周期：</Text>
          <Select value={dateRange} onChange={setDateRange} style={{ width: 120 }}
            options={[
              { value: 14, label: '近 14 天' }, { value: 30, label: '近 30 天' },
              { value: 60, label: '近 60 天' },
            ]} />
          <Text strong style={{ marginLeft: 8 }}>销售部门：</Text>
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="全部部门（可输入关键字即时筛选）"
            loading={saLoading}
            value={salesApartment || undefined}
            onChange={v => {
              const next = v ?? '';
              setSalesApartment(next);
              // 选择部门后立即重新查询，无需再点“全维度诊断”。
              if (dims.length > 0) {
                runDiagnostic(1, pageSize, dims, dateRange, next);
              }
            }}
            style={{ minWidth: 200, width: 220 }}
            options={saOptions}
            filterOption={(input, opt) => {
              const q = input.trim().toLowerCase();
              if (!q) return true;
              const label = typeof opt?.label === 'string' ? opt.label : String(opt?.value ?? '');
              return label.toLowerCase().includes(q);
            }}
            popupMatchSelectWidth={280}
            listHeight={320}
          />
          <Text strong style={{ marginLeft: 8 }}>诊断维度：</Text>
          <Checkbox.Group value={dims} onChange={v => setDims(v as DiagDim[])}
            options={DIAG_DIM_OPTS} />
        </Space>
        <div>
          <Space wrap>
            <Button type="primary" icon={<ThunderboltOutlined />} loading={q.loading || countLoading}
              disabled={dims.length === 0}
              onClick={() => runDiagnostic(1, pageSize, dims, dateRange, salesApartment)}
              style={{ background: dims.length ? R[0] : undefined }}>
              {dims.length === 3 ? '全维度诊断' : dims.length ? `${dims.length}维诊断` : '请选择维度'}
            </Button>
            {DIAG_DIM_OPTS.map(d => (
              <Button key={d.value} size="small"
                onClick={() => { setDims([d.value]); runDiagnostic(1, pageSize, [d.value], dateRange, salesApartment); }}
                loading={q.loading || countLoading}
                style={{
                  borderColor: d.value === 'ctr' ? RAINBOW[1].from : d.value === 'cvr' ? RAINBOW[3].from : RAINBOW[4].from,
                  color: d.value === 'ctr' ? RAINBOW[1].from : d.value === 'cvr' ? RAINBOW[3].from : RAINBOW[4].from,
                }}>
                仅{d.label.split('（')[0]}
              </Button>
            ))}
            {q.result && (
              <Button icon={<DownloadOutlined />}
                onClick={() => exportCSV(q.result!.columns, q.result!.rows, 'diagnostic_report')}>
                导出 CSV
              </Button>
            )}
            {total > 0 && <Tag color="red">{total} 个需优化产品</Tag>}
            {salesApartment && <Tag color="blue">部门：{salesApartment}</Tag>}
          </Space>
        </div>
      </Card>

      {q.error && <Alert message="诊断失败" description={q.error} type="error" showIcon closable style={{ marginBottom: 16 }} />}

      {q.loading && (
        <Card style={{ textAlign: 'center', padding: 60, borderRadius: 12 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}><Text type="secondary">正在运行三维诊断分析，可能需要 30-60 秒...</Text></div>
        </Card>
      )}

      {summary && !q.loading && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={5}>
              <Card size="small" style={{ borderRadius: 10, borderLeft: `4px solid ${RAINBOW[0].from}` }}>
                <Statistic title="需优化产品总数" value={summary.total} valueStyle={{ color: RAINBOW[0].from }} />
              </Card>
            </Col>
            <Col span={5}>
              <Card size="small" style={{ borderRadius: 10, borderLeft: `4px solid ${RAINBOW[1].from}` }}>
                <Statistic title={`CTR 低 (本页 ${summary.ctrLow})`} value={summary.ctrLow}
                  suffix={`/ ${summary.pageCount}`}
                  valueStyle={{ color: RAINBOW[1].from }} />
              </Card>
            </Col>
            <Col span={5}>
              <Card size="small" style={{ borderRadius: 10, borderLeft: `4px solid ${RAINBOW[3].from}` }}>
                <Statistic title={`CVR 低 (本页 ${summary.cvrLow})`} value={summary.cvrLow}
                  suffix={`/ ${summary.pageCount}`}
                  valueStyle={{ color: RAINBOW[3].from }} />
              </Card>
            </Col>
            <Col span={5}>
              <Card size="small" style={{ borderRadius: 10, borderLeft: `4px solid ${RAINBOW[4].from}` }}>
                <Statistic title={`流量下滑 (本页 ${summary.sessDecline})`} value={summary.sessDecline}
                  suffix={`/ ${summary.pageCount}`}
                  valueStyle={{ color: RAINBOW[4].from }} />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small" style={{ borderRadius: 10, borderLeft: `4px solid ${RAINBOW[0].to}` }}>
                <Statistic title={`三维全命中 (本页 ${summary.hit3})`} value={summary.hit3}
                  suffix={`/ ${summary.pageCount}`}
                  valueStyle={{ color: RAINBOW[0].to, fontWeight: 700 }} />
              </Card>
            </Col>
          </Row>

          <Card size="small" style={{ borderRadius: 12 }}>
            <Table
              dataSource={q.result!.rows.map((r, i) => ({ ...r, _key: `${currentPage}_${i}` }))}
              columns={columns}
              rowKey="_key"
              size="small"
              scroll={{ x: 2200 }}
              pagination={{
                current: currentPage,
                pageSize,
                total,
                showSizeChanger: true,
                pageSizeOptions: ['20', '50', '100', '200'],
                showTotal: (t, range) => `第 ${range[0]}-${range[1]} 条 / 共 ${t} 条`,
                showQuickJumper: true,
                onChange: (page, ps) => {
                  if (ps !== pageSize) { setPageSize(ps); runDiagnostic(1, ps, dims, dateRange, salesApartment); }
                  else { runDiagnostic(page, ps, dims, dateRange, salesApartment); }
                },
              }}
              loading={q.loading}
              rowClassName={(r: any) => r.hit_count >= 3 ? 'diagnostic-critical' : ''}
            />
          </Card>
        </>
      )}
    </div>
  );
}

/* ═════════════════════════════════════════════════════
   主组件
   ═════════════════════════════════════════════════════ */

export default function DataAnalysis() {
  const [tab, setTab] = useState('category');
  const [cfg, setCfg] = useState<ThresholdConfig>(loadThresholds);
  const [showConfig, setShowConfig] = useState(false);

  const handleCfgChange = useCallback((next: ThresholdConfig) => {
    setCfg(next);
    saveThresholds(next);
  }, []);

  return (
    <div>
      <Tabs
        activeKey={tab}
        onChange={setTab}
        tabBarExtraContent={
          <Button
            size="small"
            icon={<SettingOutlined />}
            onClick={() => setShowConfig(v => !v)}
            type={showConfig ? 'primary' : 'default'}
            style={showConfig ? { background: R[2], border: 'none', borderRadius: 8 } : { borderRadius: 8 }}
          >
            阈值配置
          </Button>
        }
        items={[
          { key: 'category', label: <span><BarChartOutlined /> CTR/CVR 类目分析</span> },
          { key: 'asin', label: <span><SearchOutlined /> ASIN 明细查询</span> },
          { key: 'diagnostic', label: <span><ThunderboltOutlined style={{ color: RAINBOW[0].from }} /> 三维产品诊断</span> },
        ]}
        style={{ marginBottom: showConfig ? 0 : 16 }}
      />

      {showConfig && (
        <ThresholdPanel cfg={cfg} onChange={handleCfgChange} />
      )}

      {tab === 'category' && <CategoryAnalysis cfg={cfg} />}
      {tab === 'asin' && <AsinDetail cfg={cfg} />}
      {tab === 'diagnostic' && <DiagnosticReport cfg={cfg} />}
    </div>
  );
}
