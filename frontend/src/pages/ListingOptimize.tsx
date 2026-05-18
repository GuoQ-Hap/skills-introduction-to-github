import { useState, useEffect, useRef, useCallback, useMemo, type CSSProperties } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Row,
  Col,
  Card,
  Input,
  Select,
  Button,
  Typography,
  Tag,
  Space,
  Alert,
  Spin,
  message,
  Collapse,
  Drawer,
  Tooltip,
  Checkbox,
  Modal,
  Table,
  Switch,
  Image,
  InputNumber,
  Progress,
  Tabs,
} from 'antd';
import {
  SearchOutlined,
  ThunderboltOutlined,
  BarChartOutlined,
  CopyOutlined,
  ShoppingOutlined,
  TagOutlined,
  EditOutlined,
  DatabaseOutlined,
  CheckOutlined,
  PlusOutlined,
  DeleteOutlined,
  SettingOutlined,
  DownloadOutlined,
  UploadOutlined,
  UndoOutlined,
  SendOutlined,
  LikeOutlined,
  LikeFilled,
  DislikeOutlined,
  DislikeFilled,
  CommentOutlined,
} from '@ant-design/icons';
import {
  listingApi,
  stiApi,
  type ListingOptimizeResponse,
  type OptimizedListing,
  type ListingAnalyzeResponse,
  type EvaluateScores,
  type EvaluateAnalysis,
  type DimensionAnalysis,
  type ListingDeepDiagnosticResponse,
  type PromptDefaults,
  type SQLExecResponse,
  type TriDimDiagnostic,
  type TrafficWordItem,
  type SearchTermRecommendResponse,
  type SqrSearchVolumeResponse,
  type ReviewAnalysisResult,
  type ProductData,
  type OptimizedVariant,
  type CompetitorItem,
  type CompetitorDiscoveryResponse,
} from '../api';
import { fetchTriDimDiagnosticSql } from './DataAnalysis';
import ModelSelector from '../components/ModelSelector';
import { RAINBOW, BTN_RAINBOW, BTN_RAINBOW_DARK } from '../layouts/MainLayout';
import { useTaskManager } from '../context/TaskContext';

const { Text } = Typography;

const ACCENT = RAINBOW[1].from;
const LIGHT_BG = `${ACCENT}08`;
const R = BTN_RAINBOW;
const RD = BTN_RAINBOW_DARK;

const MARKETPLACES = [
  { value: 'US', label: '美国 (US)' },
  { value: 'UK', label: '英国 (UK)' },
  { value: 'DE', label: '德国 (DE)' },
  { value: 'JP', label: '日本 (JP)' },
  { value: 'CA', label: '加拿大 (CA)' },
  { value: 'FR', label: '法国 (FR)' },
  { value: 'IT', label: '意大利 (IT)' },
  { value: 'ES', label: '西班牙 (ES)' },
  { value: 'AU', label: '澳大利亚 (AU)' },
  { value: 'MX', label: '墨西哥 (MX)' },
];

/** 亚马逊站点 ASIN 详情页域名（与 MARKETPLACES 对齐） */
const AMAZON_DOMAINS: Record<string, string> = {
  US: 'www.amazon.com',
  UK: 'www.amazon.co.uk',
  DE: 'www.amazon.de',
  JP: 'www.amazon.co.jp',
  CA: 'www.amazon.ca',
  FR: 'www.amazon.fr',
  IT: 'www.amazon.it',
  ES: 'www.amazon.es',
  AU: 'www.amazon.com.au',
  MX: 'www.amazon.com.mx',
};
function amazonDetailUrl(asin: string, marketplace: string): string {
  const domain = AMAZON_DOMAINS[(marketplace || 'US').toUpperCase()] || 'www.amazon.com';
  return `https://${domain}/dp/${asin}`;
}

const AUTO_COMPETITOR_LIMIT = 5;

/* ── Hover 中文翻译（按需 + 缓存） ── */

const TRANSLATE_CACHE = new Map<string, string>();

function TranslateHover({
  text,
  children,
  placement = 'top',
}: {
  text: string;
  children: React.ReactNode;
  placement?: 'top' | 'bottom' | 'left' | 'right';
}) {
  const [zh, setZh] = useState<string>(() => TRANSLATE_CACHE.get(text) ?? '');
  const [loading, setLoading] = useState(false);
  const [errored, setErrored] = useState(false);
  const firedRef = useRef(false);

  const triggerTranslate = useCallback(async () => {
    if (!text || !text.trim()) return;
    if (firedRef.current) return;
    if (TRANSLATE_CACHE.has(text)) {
      setZh(TRANSLATE_CACHE.get(text) || '');
      return;
    }
    firedRef.current = true;
    setLoading(true);
    setErrored(false);
    try {
      const resp = await listingApi.translate({ texts: [text], target_lang: 'zh-CN' });
      const t = (resp.data?.translations?.[0] || '').trim();
      if (t) {
        TRANSLATE_CACHE.set(text, t);
        setZh(t);
      } else {
        setErrored(true);
      }
    } catch (err) {
      setErrored(true);
      firedRef.current = false;
    } finally {
      setLoading(false);
    }
  }, [text]);

  const title = (
    <div style={{ maxWidth: 420, lineHeight: 1.6, fontSize: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 4, opacity: 0.85 }}>中文翻译</div>
      {loading && !zh && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Spin size="small" /> <span>正在翻译…</span>
        </div>
      )}
      {zh && <div style={{ whiteSpace: 'pre-wrap' }}>{zh}</div>}
      {!loading && !zh && errored && (
        <div style={{ opacity: 0.7 }}>翻译失败，点击悬停重试</div>
      )}
    </div>
  );

  return (
    <Tooltip
      title={title}
      placement={placement}
      mouseEnterDelay={0.5}
      destroyTooltipOnHide={false}
      onOpenChange={(open) => { if (open) triggerTranslate(); }}
      overlayInnerStyle={{ maxWidth: 440 }}
    >
      <div>{children}</div>
    </Tooltip>
  );
}

/* ── 关键词高亮渲染 ── */

const WORD_SOURCE_STYLES: Record<string, { bg: string; color: string; border: string }> = {
  traffic:    { bg: '#fee2e2', color: '#dc2626', border: '#dc2626' },
  manual:     { bg: '#dbeafe', color: '#2563eb', border: '#2563eb' },
  searchlib:  { bg: '#dcfce7', color: '#15803d', border: '#15803d' },
  multi:      { bg: '#fef9c3', color: '#a16207', border: '#a16207' },
};

function HighlightLegend() {
  const items = [
    { label: '流量词', ...WORD_SOURCE_STYLES.traffic },
    { label: '手动添加', ...WORD_SOURCE_STYLES.manual },
    { label: '搜索词库', ...WORD_SOURCE_STYLES.searchlib },
    { label: '多重命中', ...WORD_SOURCE_STYLES.multi },
  ];
  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
      {items.map(it => (
        <span key={it.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
          <span style={{
            display: 'inline-block', width: 32, height: 14, borderRadius: 3,
            background: it.bg, border: `1px solid ${it.border}`,
          }} />
          <span style={{ color: it.color, fontWeight: 600 }}>{it.label}</span>
        </span>
      ))}
    </div>
  );
}

function HighlightedText({ text, wordSourceMap, trafficWordMeta }: {
  text: string;
  wordSourceMap?: Map<string, 'traffic' | 'manual' | 'searchlib' | 'multi'> | null;
  /** key=lowercase word，value=流量词原始条目，用于 hover 时展示 ABA/SQR/理由 */
  trafficWordMeta?: Map<string, TrafficWordItem> | null;
}) {
  if (!wordSourceMap || wordSourceMap.size === 0 || !text) return <>{text}</>;

  const allWords = [...wordSourceMap.keys()].filter(w => w.length >= 2);
  allWords.sort((a, b) => b.length - a.length);

  if (allWords.length === 0) return <>{text}</>;

  const escaped = allWords.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const regex = new RegExp(`(${escaped.join('|')})`, 'gi');
  const parts = text.split(regex);

  const sourceLabel: Record<string, string> = {
    traffic: '流量词',
    manual: '手动添加',
    searchlib: '搜索词库',
    multi: '多重命中（流量词+搜索词库）',
  };
  const relevanceLabel: Record<string, string> = {
    clear: '清晰',
    fuzzy: '模糊',
    broad: '宽泛',
    unknown: '未判定',
  };

  const buildTooltip = (low: string, fallback: string) => {
    const meta = trafficWordMeta?.get(low) || null;
    if (!meta) return fallback;
    const rankStr = meta.aba_search_rank != null ? `ABA#${meta.aba_search_rank}` : '';
    const impStr = meta.sqr_total_impressions != null
      ? `${(meta.sqr_total_impressions / 1000).toFixed(1)}K次`
      : '';
    const detail = [rankStr, impStr].filter(Boolean).join(' · ');
    const relText = meta.relevance && meta.relevance !== 'unknown'
      ? relevanceLabel[meta.relevance] ?? ''
      : '';
    const headline = [detail, meta.reason].filter(Boolean).join(' | ');
    return (
      <div style={{ maxWidth: 320, lineHeight: 1.55 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>
          {fallback}
          {relText && (
            <span style={{ marginLeft: 6, fontWeight: 400, fontSize: 11, opacity: 0.85 }}>
              · 相关性 {relText}
            </span>
          )}
        </div>
        {headline ? (
          <div style={{ fontSize: 12 }}>{headline}</div>
        ) : (
          <div style={{ fontSize: 12, opacity: 0.75 }}>暂无更多数据</div>
        )}
      </div>
    );
  };

  return (
    <>
      {parts.map((part, i) => {
        const low = part.toLowerCase();
        const source = wordSourceMap.get(low);
        if (source) {
          const style = WORD_SOURCE_STYLES[source];
          return (
            <Tooltip
              key={i}
              title={buildTooltip(low, sourceLabel[source])}
              mouseEnterDelay={0.15}
            >
              <span style={{
                background: style.bg, color: style.color, fontWeight: 600,
                padding: '1px 3px', borderRadius: 3, cursor: 'help',
                borderBottom: `2px solid ${style.border}`,
              }}>
                {part}
              </span>
            </Tooltip>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

/* ── 关键词覆盖情况面板 ── */

function TrafficWordPanel({ optimized, selectedKeywords }: {
  optimized: OptimizedListing;
  selectedKeywords: string[];
}) {
  const selectedKws = selectedKeywords;
  const trafficCount = optimized.word_analysis?.traffic_words?.length ?? 0;

  // 检查每个勾选关键词是否出现在优化结果文本中
  const allText = [
    optimized.title,
    ...optimized.bullet_points,
    optimized.description,
    optimized.search_terms,
  ].join(' ').toLowerCase();

  const included = selectedKws.filter(kw => allText.includes(kw.toLowerCase()));
  const missing  = selectedKws.filter(kw => !allText.includes(kw.toLowerCase()));

  if (selectedKws.length === 0 && trafficCount === 0) return null;

  return (
    <div style={{ borderTop: '1px dashed #E5E7EB', paddingTop: 12, marginBottom: 12 }}>

      {/* 高亮图例 */}
      {trafficCount > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>高亮图例：</Text>
          <span style={{ background: '#FEE2E2', color: '#DC2626', padding: '1px 6px', borderRadius: 3, fontSize: 11, fontWeight: 600 }}>流量词(红)</span>
          <span style={{ background: '#FEF3C7', color: '#D97706', padding: '1px 6px', borderRadius: 3, fontSize: 11, fontWeight: 600 }}>关键词(黄)</span>
          <span style={{ background: '#D1FAE5', color: '#059669', padding: '1px 6px', borderRadius: 3, fontSize: 11, fontWeight: 500 }}>描述词(绿)</span>
          <Tag color="red" style={{ fontSize: 10, marginLeft: 4 }}>共 {trafficCount} 个流量词</Tag>
        </div>
      )}

      {/* 关键词覆盖情况 */}
      {selectedKws.length > 0 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <TagOutlined style={{ color: '#7c3aed' }} />
            <Text strong style={{ fontSize: 12, color: '#7c3aed' }}>选定关键词覆盖情况</Text>
            <Tag color={missing.length === 0 ? 'success' : 'warning'} style={{ fontSize: 10 }}>
              已覆盖 {included.length} / {selectedKws.length}
            </Tag>
          </div>

          {/* 已包含 */}
          {included.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
              {included.map((kw, i) => (
                <Tag key={i} color="success" style={{ fontSize: 11 }}>✓ {kw}</Tag>
              ))}
            </div>
          )}

          {/* 缺失警告 */}
          {missing.length > 0 && (
            <div style={{
              background: '#FFF7ED', border: '1px solid #FDBA74', borderRadius: 8,
              padding: '8px 12px',
            }}>
              <Text style={{ fontSize: 11, color: '#C2410C', fontWeight: 600, display: 'block', marginBottom: 4 }}>
                ⚠ 以下 {missing.length} 个关键词未出现在优化结果中，建议手动补充或重新优化：
              </Text>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {missing.map((kw, i) => (
                  <Tag key={i} color="error" style={{ fontSize: 11 }}>{kw}</Tag>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const PROMPT_CFG_KEY = 'lsta_prompt_overrides';

const PROMPT_FIELDS: { key: keyof PromptDefaults; label: string }[] = [
  { key: 'company_info', label: '公司信息' },
  { key: 'core_capabilities', label: '核心能力' },
  { key: 'bullet_rules', label: '五点描述提示' },
  { key: 'description_rules', label: '产品描述提示' },
];

function usePromptConfig() {
  const [defaults, setDefaults] = useState<PromptDefaults | null>(null);
  const [overrides, setOverrides] = useState<Partial<PromptDefaults>>(() => {
    try {
      const raw = sessionStorage.getItem(PROMPT_CFG_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
  });
  const loaded = useRef(false);

  const loadDefaults = useCallback(async () => {
    if (loaded.current && defaults) return;
    try {
      const { data } = await listingApi.promptDefaults();
      setDefaults(data);
      loaded.current = true;
    } catch {
      message.error('加载提示词默认值失败');
    }
  }, [defaults]);

  const save = useCallback((next: Partial<PromptDefaults>) => {
    setOverrides(next);
    try { sessionStorage.setItem(PROMPT_CFG_KEY, JSON.stringify(next)); } catch {}
  }, []);

  const resetAll = useCallback(() => save({}), [save]);

  const activeOverrides = useCallback((): Partial<PromptDefaults> | undefined => {
    const filled = Object.fromEntries(
      Object.entries(overrides).filter(([, v]) => v && v.trim()),
    ) as Partial<PromptDefaults>;
    return Object.keys(filled).length ? filled : undefined;
  }, [overrides]);

  return { defaults, overrides, loadDefaults, save, resetAll, activeOverrides };
}

function escapeCSV(v: string) {
  if (/[,"\n\r]/.test(v)) return `"${v.replace(/"/g, '""')}"`;
  return v;
}

function parseCSVRecords(text: string): string[][] {
  const records: string[][] = [];
  let i = 0;
  let record: string[] = [];
  let field = '';
  let inQuotes = false;
  while (i < text.length) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; }
        else { inQuotes = false; i++; }
      } else { field += ch; i++; }
    } else {
      if (ch === '"') { inQuotes = true; i++; }
      else if (ch === ',') { record.push(field); field = ''; i++; }
      else if (ch === '\r' || ch === '\n') {
        record.push(field); field = '';
        if (record.some(c => c.trim())) records.push(record);
        record = [];
        if (ch === '\r' && text[i + 1] === '\n') i++;
        i++;
      } else { field += ch; i++; }
    }
  }
  if (field || record.length > 0) { record.push(field); records.push(record); }
  return records;
}

function PromptSettingsDrawer({
  open, onClose, promptCfg,
}: {
  open: boolean;
  onClose: () => void;
  promptCfg: ReturnType<typeof usePromptConfig>;
}) {
  const { defaults, overrides, loadDefaults, save, resetAll } = promptCfg;
  const [local, setLocal] = useState<Partial<PromptDefaults>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      loadDefaults();
      setLocal({ ...overrides });
    }
  }, [open]);

  const getValue = (key: keyof PromptDefaults) =>
    local[key] ?? overrides[key] ?? '';

  const getPlaceholder = (key: keyof PromptDefaults) =>
    defaults?.[key] ?? '加载中...';

  const handleChange = (key: keyof PromptDefaults, val: string) => {
    setLocal(prev => ({ ...prev, [key]: val }));
  };

  const handleSave = () => {
    save(local);
    message.success('提示词设置已保存');
    onClose();
  };

  const handleReset = () => {
    resetAll();
    setLocal({});
    message.success('已恢复默认值');
  };

  const handleExport = () => {
    const merged: Record<string, string> = {};
    for (const { key } of PROMPT_FIELDS) {
      merged[key] = local[key] || overrides[key] || defaults?.[key] || '';
    }
    const header = 'field,value';
    const rows = PROMPT_FIELDS.map(f => `${f.key},${escapeCSV(merged[f.key])}`);
    const csv = [header, ...rows].join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'prompt_config.csv';
    a.click();
    URL.revokeObjectURL(url);
    message.success('已导出 CSV');
  };

  const handleImport = () => {
    fileInputRef.current?.click();
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = (reader.result as string).replace(/^\uFEFF/, '');
        const records = parseCSVRecords(text);
        if (records.length < 2) { message.error('CSV 文件格式不正确'); return; }
        const imported: Partial<PromptDefaults> = {};
        const validKeys = PROMPT_FIELDS.map(f => f.key);
        for (let i = 1; i < records.length; i++) {
          const cols = records[i];
          if (cols.length >= 2) {
            const key = cols[0].trim() as keyof PromptDefaults;
            if (validKeys.includes(key)) {
              imported[key] = cols.slice(1).join(',');
            }
          }
        }
        setLocal(imported);
        message.success('CSV 导入成功，请确认后保存');
      } catch { message.error('CSV 解析失败'); }
    };
    reader.readAsText(file, 'utf-8');
    e.target.value = '';
  };

  const hasOverrides = PROMPT_FIELDS.some(f => (local[f.key] ?? overrides[f.key] ?? '').trim());

  return (
    <Drawer
      title={
        <Space>
          <SettingOutlined style={{ color: ACCENT }} />
          <span>提示词设置</span>
          {hasOverrides && <Tag color="orange" style={{ fontSize: 10 }}>已自定义</Tag>}
        </Space>
      }
      open={open}
      onClose={onClose}
      width={560}
      extra={
        <Space>
          <Tooltip title="导入 CSV">
            <Button icon={<UploadOutlined />} onClick={handleImport}>导入</Button>
          </Tooltip>
          <Tooltip title="导出 CSV">
            <Button icon={<DownloadOutlined />} onClick={handleExport}>导出</Button>
          </Tooltip>
          <Tooltip title="恢复默认">
            <Button icon={<UndoOutlined />} onClick={handleReset} danger>重置</Button>
          </Tooltip>
        </Space>
      }
      footer={
        <div style={{ textAlign: 'right' }}>
          <Space>
            <Button onClick={onClose}>取消</Button>
            <Button type="primary" onClick={handleSave}
              style={{ background: R[1] }}>
              保存设置
            </Button>
          </Space>
        </div>
      }
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv"
        style={{ display: 'none' }}
        onChange={onFileChange}
      />
      <Alert
        message="自定义提示词将在优化时传递给 AI，留空则使用默认值"
        type="info"
        showIcon
        style={{ marginBottom: 16, borderRadius: 8 }}
      />
      {PROMPT_FIELDS.map(({ key, label }) => (
        <div key={key} style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <Text strong style={{ fontSize: 13, color: ACCENT }}>{label}</Text>
            {(local[key] ?? overrides[key] ?? '').trim() && (
              <Button
                type="link" size="small" danger
                onClick={() => handleChange(key, '')}
                style={{ fontSize: 11, padding: 0 }}
              >
                清除
              </Button>
            )}
          </div>
          <Input.TextArea
            value={getValue(key)}
            onChange={e => handleChange(key, e.target.value)}
            placeholder={getPlaceholder(key)}
            autoSize={{ minRows: 3, maxRows: 8 }}
            style={{ borderRadius: 8, fontSize: 12 }}
          />
        </div>
      ))}
    </Drawer>
  );
}

const CACHE_KEY = 'lsta_result';

function copyText(text: string) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text);
  } else {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
  message.success('已复制到剪贴板');
}

/* ─── 评论洞察面板 ─── */

function ReviewInsightsPanel({ data }: { data: ReviewAnalysisResult }) {
  const FREQ_COLOR: Record<string, string> = { high: '#f5222d', medium: '#fa8c16', low: '#8c8c8c' };
  const FREQ_LABEL: Record<string, string> = { high: '高频', medium: '中频', low: '低频' };
  const SENTIMENT_ICON: Record<string, string> = { positive: '+', neutral: '~', negative: '-', mixed: '±' };

  return (
    <Card
      size="small"
      title={
        <span style={{ fontSize: 13 }}>
          <TagOutlined style={{ marginRight: 6, color: ACCENT }} />
          评论洞察
          {data.overall_sentiment && (
            <Tag color={data.overall_sentiment === 'positive' ? 'green' : data.overall_sentiment === 'negative' ? 'red' : 'default'}
              style={{ marginLeft: 8, fontSize: 11 }}>
              {SENTIMENT_ICON[data.overall_sentiment] || '~'} {data.overall_sentiment}
            </Tag>
          )}
        </span>
      }
      style={{ borderRadius: 12, border: `1px solid ${ACCENT}30`, marginBottom: 12 }}
      styles={{ body: { padding: '8px 12px' } }}
    >
      {data.selling_points.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <Text style={{ fontSize: 11, color: '#52c41a', fontWeight: 600 }}>卖点</Text>
          <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {data.selling_points.map((sp, i) => (
              <Tooltip key={i} title={sp.detail}>
                <Tag color="green" style={{ fontSize: 11, margin: 0, cursor: 'help' }}>
                  {sp.title}
                  <span style={{ opacity: 0.6, marginLeft: 4, fontSize: 10 }}>{FREQ_LABEL[sp.frequency] || ''}</span>
                </Tag>
              </Tooltip>
            ))}
          </div>
        </div>
      )}
      {data.core_features.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <Text style={{ fontSize: 11, color: '#1890ff', fontWeight: 600 }}>核心特点</Text>
          <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {data.core_features.map((cf, i) => (
              <Tooltip key={i} title={cf.detail}>
                <Tag color={cf.sentiment === 'positive' ? 'blue' : cf.sentiment === 'negative' ? 'orange' : 'default'}
                  style={{ fontSize: 11, margin: 0, cursor: 'help' }}>
                  {cf.title}
                </Tag>
              </Tooltip>
            ))}
          </div>
        </div>
      )}
      {data.pain_points.length > 0 && (
        <div style={{ marginBottom: 4 }}>
          <Text style={{ fontSize: 11, color: '#f5222d', fontWeight: 600 }}>痛点</Text>
          <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {data.pain_points.map((pp, i) => (
              <Tooltip key={i} title={pp.detail}>
                <Tag color={FREQ_COLOR[pp.frequency] === '#f5222d' ? 'red' : FREQ_COLOR[pp.frequency] === '#fa8c16' ? 'orange' : 'default'}
                  style={{ fontSize: 11, margin: 0, cursor: 'help' }}>
                  {pp.title}
                  <span style={{ opacity: 0.6, marginLeft: 4, fontSize: 10 }}>{FREQ_LABEL[pp.frequency] || ''}</span>
                </Tag>
              </Tooltip>
            ))}
          </div>
        </div>
      )}
      {data.summary && (
        <div style={{ marginTop: 6, padding: '6px 8px', background: 'rgba(6, 23, 38, 0.88)', border: '1px solid rgba(122, 205, 232, 0.2)', borderRadius: 6, fontSize: 11, color: '#bdddea', lineHeight: 1.6 }}>
          {data.summary}
        </div>
      )}
    </Card>
  );
}


/* ─── 可编辑的原始产品信息卡 ─── */

interface EditableProductProps {
  product: ProductData;
  onChange: (p: ProductData) => void;
  fetching?: boolean;
  triDim?: TriDimDiagnostic | null;
  fetchStage?: 'idle' | 'product' | 'search-term' | 'done';
  searchTermLoading?: boolean;
}

function TriDimBar({ triDim }: { triDim: TriDimDiagnostic }) {
  const fmtPct = (v: number | null) => v != null ? `${v.toFixed(3)}%` : '-';
  const fmtPct2 = (v: number | null) => v != null ? `${v.toFixed(2)}%` : '-';
  const isLowCtr = triDim.product_ctr_pct != null && triDim.cat_avg_ctr_pct != null && triDim.product_ctr_pct < triDim.cat_avg_ctr_pct;
  const isLowCvr = triDim.product_cvr_pct != null && triDim.cat_avg_cvr_pct != null && triDim.product_cvr_pct < triDim.cat_avg_cvr_pct;
  const isDecline = triDim.sessions_change_pct != null && triDim.sessions_change_pct < 0;
  const hitLabel = triDim.hit_count > 0 ? `${triDim.hit_count}维` : '正常';
  const hitColor = triDim.hit_count >= 3 ? '#DC2626' : triDim.hit_count >= 2 ? '#F59E0B' : triDim.hit_count >= 1 ? '#D97706' : '#10B981';

  const items = [
    { label: 'CTR%', value: fmtPct(triDim.product_ctr_pct), warn: isLowCtr },
    { label: '类目CTR%', value: fmtPct(triDim.cat_avg_ctr_pct), warn: false },
    { label: 'CVR%', value: fmtPct(triDim.product_cvr_pct), warn: isLowCvr },
    { label: '类目CVR%', value: fmtPct(triDim.cat_avg_cvr_pct), warn: false },
    { label: '流量变化%', value: fmtPct2(triDim.sessions_change_pct), warn: isDecline },
    { label: '库存', value: triDim.avg_stock_qty != null ? String(triDim.avg_stock_qty) : '-', warn: false },
  ];

  return (
    <div style={{ marginTop: 8, padding: '8px 10px', background: '#FFF7ED', border: '1px solid #FDE68A', borderRadius: 8 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 12px', alignItems: 'center', marginBottom: 4 }}>
        {items.map((it, i) => (
          <div key={i} style={{ textAlign: 'center', minWidth: 60 }}>
            <div style={{ fontSize: 10, color: '#6B7280' }}>{it.label}</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: it.warn ? '#DC2626' : '#111827' }}>{it.value}</div>
          </div>
        ))}
        <div style={{ textAlign: 'center', minWidth: 40 }}>
          <div style={{ fontSize: 10, color: '#6B7280' }}>命中</div>
          <Tag color={hitColor} style={{ fontSize: 11, fontWeight: 600, margin: 0 }}>{hitLabel}</Tag>
        </div>
      </div>
      {triDim.optimization_actions && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {triDim.optimization_actions.split(' | ').filter(Boolean).map((act, i) => (
            <Tag key={i} color={act.includes('必须') ? 'red' : 'orange'} style={{ fontSize: 10, margin: 0 }}>{act}</Tag>
          ))}
        </div>
      )}
    </div>
  );
}

function EditableProductCard({ product, onChange, fetching, triDim, fetchStage, searchTermLoading }: EditableProductProps) {
  const upd = (patch: Partial<ProductData>) => onChange({ ...product, ...patch });
  const updBullet = (idx: number, val: string) => {
    const next = [...product.bullet_points];
    next[idx] = val;
    upd({ bullet_points: next });
  };

  const hasProductData = !!product.title;

  // 没有产品数据时才显示全屏进度占位卡
  const showFullProgress = !hasProductData && (fetching || (fetchStage && fetchStage !== 'done' && fetchStage !== 'idle'));
  if (showFullProgress) {
    const steps = [
      { key: 'product', label: '获取产品数据 + 三维诊断 + 流量词' },
      { key: 'search-term', label: '获取搜索词相关性推荐' },
    ];
    const currentIdx = fetchStage === 'product' ? 0 : fetchStage === 'search-term' ? 1 : -1;

    return (
      <Card style={{ borderRadius: 12, padding: '24px 32px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {steps.map((step, i) => {
            const isDone = i < currentIdx || (!fetching && i === 0);
            const isCurrent = (i === 0 && fetching) || (i === 1 && !fetching && searchTermLoading);
            return (
              <div key={step.key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {isDone ? (
                  <CheckOutlined style={{ color: '#10B981', fontSize: 16 }} />
                ) : isCurrent ? (
                  <Spin size="small" />
                ) : (
                  <span style={{
                    width: 16, height: 16, borderRadius: '50%',
                    border: '2px solid #e5e7eb', display: 'inline-block',
                  }} />
                )}
                <Text style={{
                  fontSize: 13,
                  color: isDone ? '#10B981' : isCurrent ? '#F57C00' : '#9ca3af',
                  fontWeight: isCurrent ? 600 : 400,
                }}>
                  {isDone ? `✓ ${step.label}` : isCurrent ? `正在${step.label}...` : step.label}
                </Text>
              </div>
            );
          })}
        </div>
      </Card>
    );
  }

  // 有产品数据但后台任务还在跑（三维诊断/流量词/搜索词仍在加载）时，在卡片顶部显示内联进度条
  const showInlineProgress = hasProductData && (fetching || searchTermLoading);
  const inlineLabel = fetching
    ? '正在后台加载三维诊断 & 流量词...'
    : searchTermLoading
      ? '正在加载搜索词相关性推荐...'
      : '';

  return (
    <Card
      size="small"
      title={<Space><ShoppingOutlined /><span>原始产品信息</span><Tag color="blue" style={{ fontSize: 10 }}>可编辑</Tag></Space>}
      style={{ borderRadius: 12 }}
    >
      {showInlineProgress && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 10px', marginBottom: 12,
          background: '#FFF7ED', border: '1px solid #FDE68A', borderRadius: 8,
        }}>
          <Spin size="small" />
          <Text style={{ fontSize: 12, color: '#D97706' }}>{inlineLabel}</Text>
        </div>
      )}
      <Row gutter={[12, 8]}>
        <Col span={24}>
          <Text strong style={{ fontSize: 12, color: ACCENT }}>标题</Text>
          <Input.TextArea value={product.title} onChange={e => upd({ title: e.target.value })}
            autoSize={{ minRows: 1, maxRows: 3 }} style={{ borderRadius: 8, fontSize: 13, marginTop: 2 }} />
        </Col>
        <Col span={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>品牌</Text>
          <Input size="small" value={product.brand} onChange={e => upd({ brand: e.target.value })} />
        </Col>
        <Col span={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>价格</Text>
          <Input size="small" value={product.price} onChange={e => upd({ price: e.target.value })}
            addonAfter={product.currency || 'USD'} />
        </Col>
        <Col span={8}>
          <Text type="secondary" style={{ fontSize: 11 }}>评分</Text>
          <Input size="small" value={product.rating} onChange={e => upd({ rating: e.target.value })}
            suffix={<span style={{ fontSize: 11, color: '#999' }}>{product.review_count} 条</span>} />
        </Col>
        <Col span={12}>
          <Text type="secondary" style={{ fontSize: 11 }}>类目</Text>
          <Input size="small" value={product.category} onChange={e => upd({ category: e.target.value })} />
        </Col>
        <Col span={12}>
          <Text type="secondary" style={{ fontSize: 11 }}>BSR</Text>
          <Input size="small" value={product.bsr_rank} onChange={e => upd({ bsr_rank: e.target.value })} />
        </Col>

        {/* ── 产品图片 ── */}
        {product.images && product.images.length > 0 && (
          <Col span={24}>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>产品图片</Text>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <Image.PreviewGroup>
                {product.images.map((src, i) => (
                  <Image key={i} src={src} width={64} height={64}
                    style={{ objectFit: 'contain', borderRadius: 6, border: '1px solid #f0f0f0' }}
                    fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8/+F/PQAJpAN4sKMfFwAAAABJRU5ErkJggg==" />
                ))}
              </Image.PreviewGroup>
            </div>
          </Col>
        )}

        {/* ── 三维诊断指标 ── */}
        {triDim && (
          <Col span={24}>
            <TriDimBar triDim={triDim} />
          </Col>
        )}

        <Col span={24}>
          <Collapse size="small" items={[{
            key: 'bullets',
            label: `五点描述 (${product.bullet_points.length} 条)`,
            children: (
              <div>
                {product.bullet_points.map((bp, i) => (
                  <div key={i} style={{ display: 'flex', gap: 4, marginBottom: 4, alignItems: 'flex-start' }}>
                    <Tag color="orange" style={{ fontSize: 10, padding: '0 3px', marginTop: 6, flexShrink: 0 }}>{i + 1}</Tag>
                    <Input.TextArea value={bp} onChange={e => updBullet(i, e.target.value)}
                      autoSize={{ minRows: 1, maxRows: 4 }} style={{ flex: 1, borderRadius: 6, fontSize: 12 }} />
                  </div>
                ))}
                <Button size="small" type="dashed" icon={<PlusOutlined />} block
                  onClick={() => upd({ bullet_points: [...product.bullet_points, ''] })}
                  style={{ marginTop: 4 }}>添加</Button>
              </div>
            ),
          }]} />
        </Col>
        <Col span={24}>
          <Collapse size="small" items={[{
            key: 'desc',
            label: '产品描述',
            children: (
              <Input.TextArea value={product.description} onChange={e => upd({ description: e.target.value })}
                autoSize={{ minRows: 2, maxRows: 8 }} style={{ borderRadius: 8, fontSize: 12 }} />
            ),
          }]} />
        </Col>

        {product.reviews && product.reviews.length > 0 && (
          <Col span={24}>
            <Collapse size="small" items={[{
              key: 'reviews',
              label: `用户评论 (${product.reviews.length} 条)`,
              children: (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {product.reviews.map((rv, i) => (
                    <div key={i} style={{
                      padding: '8px 10px', background: '#FAFAFA', borderRadius: 8,
                      border: '1px solid #F0F0F0',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 600 }}>
                          {'★'.repeat(Math.round(rv.stars))}{'☆'.repeat(5 - Math.round(rv.stars))}
                          <span style={{ marginLeft: 4, color: '#8C8C8C', fontWeight: 400 }}>{rv.stars}</span>
                        </span>
                        {rv.date && <Text type="secondary" style={{ fontSize: 10 }}>{rv.date}</Text>}
                      </div>
                      {rv.title && <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{rv.title}</div>}
                      {rv.body && <div style={{ fontSize: 11, color: '#595959', lineHeight: 1.6 }}>{rv.body}</div>}
                    </div>
                  ))}
                </div>
              ),
            }]} />
          </Col>
        )}
      </Row>
    </Card>
  );
}

/* ─── 流量词选择器 ─── */

interface TrafficWordSelectorProps {
  trafficWords: TrafficWordItem[];
  selectedWords: string[];
  onSelectedChange: (words: string[]) => void;
}

function TrafficWordSelector({ trafficWords, selectedWords, onSelectedChange }: TrafficWordSelectorProps) {
  const [customInput, setCustomInput] = useState('');

  const toggleWord = (word: string) => {
    if (selectedWords.includes(word)) {
      onSelectedChange(selectedWords.filter(w => w !== word));
    } else {
      onSelectedChange([...selectedWords, word]);
    }
  };

  const addCustom = () => {
    const trimmed = customInput.trim();
    if (!trimmed) return;
    const newWords = trimmed.split(/[,，\s]+/).filter(Boolean);
    const toAdd = newWords.filter(w => !selectedWords.includes(w.toLowerCase()));
    if (toAdd.length) onSelectedChange([...selectedWords, ...toAdd.map(w => w.toLowerCase())]);
    setCustomInput('');
  };

  const selectAll = () => onSelectedChange(trafficWords.map(tw => tw.word));
  const clearAll = () => onSelectedChange([]);

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <Text strong style={{ fontSize: 12 }}>
          <TagOutlined style={{ marginRight: 4, color: '#EF4444' }} />
          流量词
          {trafficWords.length > 0 && (
            <Tag color="red" style={{ fontSize: 10, marginLeft: 4, verticalAlign: 'middle' }}>
              {trafficWords.length} 词
            </Tag>
          )}
        </Text>
        <Space size={4}>
          <Button type="link" size="small" onClick={selectAll} style={{ fontSize: 11, padding: 0 }}>全选</Button>
          <Button type="link" size="small" onClick={clearAll} style={{ fontSize: 11, padding: 0 }}>清空</Button>
        </Space>
      </div>

      {trafficWords.length > 0 ? (
        <div style={{
          maxHeight: 200, overflowY: 'auto', border: '1px solid rgba(83, 210, 255, 0.24)', borderRadius: 8,
          padding: '6px 8px', background: 'rgba(2, 12, 23, 0.72)',
        }}>
          {trafficWords.map((tw) => {
            const checked = selectedWords.includes(tw.word);
            const rankStr = tw.aba_search_rank != null ? `ABA#${tw.aba_search_rank}` : '';
            const impStr = tw.sqr_total_impressions != null ? `${(tw.sqr_total_impressions / 1000).toFixed(1)}K次` : '';
            const detail = [rankStr, impStr].filter(Boolean).join(' · ');
            const tooltipText = [detail, tw.reason].filter(Boolean).join(' | ');

            const isManual = tw.source === 'manual';
            const relevanceCfg: Record<string, { label: string; color: string; bg: string; border: string }> = {
              clear:   { label: '清晰', color: '#79f2b4', bg: 'rgba(16, 185, 129, 0.14)', border: 'rgba(52, 211, 153, 0.44)' },
              fuzzy:   { label: '模糊', color: '#f8d477', bg: 'rgba(245, 158, 11, 0.13)', border: 'rgba(250, 204, 21, 0.42)' },
              broad:   { label: '宽泛', color: '#ff9a9a', bg: 'rgba(239, 68, 68, 0.13)', border: 'rgba(248, 113, 113, 0.4)' },
              unknown: { label: '未判定', color: '#9db9c5', bg: 'rgba(122, 205, 232, 0.08)', border: 'rgba(122, 205, 232, 0.2)' },
              manual:  { label: '手动添加', color: '#93c5fd', bg: 'rgba(37, 99, 235, 0.16)', border: 'rgba(96, 165, 250, 0.42)' },
            };
            const rel = relevanceCfg[isManual ? 'manual' : (tw.relevance ?? 'unknown')];

            return (
              <div key={tw.word} style={{
                display: 'flex', alignItems: 'center', gap: 5, padding: '3px 0',
                borderBottom: '1px solid rgba(122, 205, 232, 0.1)',
              }}>
                <Checkbox checked={checked} onChange={() => toggleWord(tw.word)} />
                <Tooltip title={tooltipText || tw.source}>
                  <span
                    style={{
                      fontSize: 12, cursor: 'pointer', fontWeight: checked ? 600 : 400,
                      color: isManual ? '#93c5fd' : (checked ? '#e9f8ff' : '#b7d7e4'),
                      maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}
                    onClick={() => toggleWord(tw.word)}
                  >
                    {tw.word}
                  </span>
                </Tooltip>
                <span style={{
                  fontSize: 10, padding: '0 5px', borderRadius: 3, lineHeight: '16px',
                  background: rel.bg, color: rel.color, border: `1px solid ${rel.border}`,
                  fontWeight: rel.label === '清晰' ? 700 : 500,
                  whiteSpace: 'nowrap', flexShrink: 0,
                }}>
                  {rel.label}
                </span>
                {detail && (
                  <Text type="secondary" style={{ fontSize: 10, whiteSpace: 'nowrap', flexShrink: 0 }}>
                    {detail}
                  </Text>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{
          padding: '12px 8px', textAlign: 'center', border: '1px dashed #D1D5DB', borderRadius: 8,
          color: '#9CA3AF', fontSize: 12,
        }}>
          获取产品信息后自动分析流量词
        </div>
      )}

      <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
        <Input
          size="small" placeholder="手动添加流量词（逗号分隔）"
          value={customInput} onChange={e => setCustomInput(e.target.value)}
          onPressEnter={addCustom}
          style={{ flex: 1, borderRadius: 6, fontSize: 12 }}
        />
        <Button size="small" type="primary" icon={<PlusOutlined />} onClick={addCustom}
          style={{ borderRadius: 6 }}>
          添加
        </Button>
      </div>

      {selectedWords.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <Text type="secondary" style={{ fontSize: 10 }}>已选 {selectedWords.length} 个流量词用于优化：</Text>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 2 }}>
            {selectedWords.map(w => (
              <Tag key={w} closable onClose={() => toggleWord(w)} color="red"
                style={{ fontSize: 10, margin: 0 }}>
                {w}
              </Tag>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function formatSqrDisplayCount(n: number): string {
  if (n >= 10000) {
    const w = n / 10000;
    const wStr = Number.isInteger(w) ? String(w) : w.toFixed(w >= 10 ? 1 : 2);
    return `${n.toLocaleString()}（${wStr}万）`;
  }
  return n.toLocaleString();
}

/** 搜索量分档筛选：A~F 独立档位；null=全部 */
type SqrTrafficBand = null | 'A' | 'B' | 'C' | 'D' | 'E' | 'F';

const SQR_TRAFFIC_BAND_OPTS: { key: SqrTrafficBand; label: string; hint: string }[] = [
  { key: null, label: '全部', hint: '' },
  { key: 'A', label: 'A', hint: '≥30W' },
  { key: 'B', label: 'B', hint: '20–30W' },
  { key: 'C', label: 'C', hint: '10–20W' },
  { key: 'D', label: 'D', hint: '5–10W' },
  { key: 'E', label: 'E', hint: '1–5W' },
  { key: 'F', label: 'F', hint: '＜1W' },
];

function sqrGradeMatchesBand(grade: string, band: SqrTrafficBand): boolean {
  if (!band) return true;
  return grade === band;
}

/** SQR 档位 A~F → 评分展示 */
function sqrVolumeScoreLetter(grade: string): string {
  if (['A', 'B', 'C', 'D', 'E', 'F'].includes(grade)) return grade;
  return '?';
}

const SCORE_LETTER_STYLE: Record<string, { bg: string; color: string; border: string }> = {
  A: { bg: 'rgba(16, 185, 129, 0.14)', color: '#8df2bd', border: 'rgba(52, 211, 153, 0.42)' },
  B: { bg: 'rgba(6, 182, 212, 0.14)', color: '#8eeaff', border: 'rgba(103, 232, 249, 0.42)' },
  C: { bg: 'rgba(245, 158, 11, 0.13)', color: '#f8d477', border: 'rgba(250, 204, 21, 0.42)' },
  D: { bg: 'rgba(124, 58, 237, 0.14)', color: '#c4b5fd', border: 'rgba(167, 139, 250, 0.42)' },
  E: { bg: 'rgba(122, 205, 232, 0.08)', color: '#9db9c5', border: 'rgba(122, 205, 232, 0.2)' },
  F: { bg: 'rgba(122, 205, 232, 0.08)', color: '#9db9c5', border: 'rgba(122, 205, 232, 0.2)' },
  '?': { bg: 'rgba(122, 205, 232, 0.06)', color: '#7faec1', border: 'rgba(122, 205, 232, 0.14)' },
};

/* ─── 搜索词相关性推荐库选择器 ─── */

const RELEVANCE_LEVELS = [
  { key: '高相关', color: '#8df2bd', bg: 'rgba(16, 185, 129, 0.14)', border: 'rgba(52, 211, 153, 0.42)' },
  { key: '中高相关', color: '#8eeaff', bg: 'rgba(6, 182, 212, 0.14)', border: 'rgba(103, 232, 249, 0.42)' },
  { key: '中相关', color: '#f8d477', bg: 'rgba(245, 158, 11, 0.13)', border: 'rgba(250, 204, 21, 0.42)' },
  { key: '中低相关', color: '#ffc08a', bg: 'rgba(249, 115, 22, 0.13)', border: 'rgba(253, 186, 116, 0.4)' },
  { key: '低相关', color: '#ff9a9a', bg: 'rgba(239, 68, 68, 0.13)', border: 'rgba(248, 113, 113, 0.4)' },
];

interface SearchTermLibProps {
  loading: boolean;
  data: SearchTermRecommendResponse | null;
  error: string;
  selectedTerms: string[];
  onSelectedChange: (terms: string[]) => void;
  activeLevel: string | null;
  onLevelChange: (level: string | null) => void;
  levelLoading: boolean;
}

function SearchTermLibSelector({
  loading, data, error, selectedTerms, onSelectedChange,
  activeLevel, onLevelChange, levelLoading,
}: SearchTermLibProps) {
  const [expanded, setExpanded] = useState(false);
  const [sqrBand, setSqrBand] = useState<SqrTrafficBand>(null);
  const [volumeMap, setVolumeMap] = useState<Record<string, SqrSearchVolumeResponse>>({});
  const [volumeLoading, setVolumeLoading] = useState(false);
  const [volumeError, setVolumeError] = useState('');

  const termsSig = useMemo(
    () => (data?.search_terms ?? []).map(t => t.search_term).join('\u0001'),
    [data?.search_terms],
  );

  useEffect(() => {
    setSqrBand(null);
  }, [activeLevel]);

  useEffect(() => {
    if (!data?.success || !activeLevel || !data.search_terms?.length) {
      setVolumeMap({});
      setVolumeLoading(false);
      setVolumeError('');
      return;
    }
    let cancelled = false;
    const terms = data.search_terms.map(t => t.search_term);
    setVolumeLoading(true);
    setVolumeError('');
    (async () => {
      try {
        const merged: Record<string, SqrSearchVolumeResponse> = {};
        const chunk = 500;
        for (let i = 0; i < terms.length; i += chunk) {
          if (cancelled) return;
          const part = terms.slice(i, i + chunk);
          if (!part.length) continue;
          const { data: resp } = await listingApi.sqrSearchVolumes({ terms: part });
          if (cancelled) return;
          const vols = resp.volumes || {};
          for (const [k, v] of Object.entries(vols)) {
            merged[k.toLowerCase()] = v as SqrSearchVolumeResponse;
          }
        }
        if (!cancelled) setVolumeMap(merged);
      } catch (e: unknown) {
        if (!cancelled) setVolumeError(e instanceof Error ? e.message : 'SQR 加载失败');
      } finally {
        if (!cancelled) setVolumeLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [data?.success, activeLevel, termsSig]);

  const effectiveBand = volumeLoading ? null : sqrBand;

  const filteredSortedTerms = useMemo(() => {
    if (!data?.search_terms?.length) return [];
    const getV = (st: string) => volumeMap[st.toLowerCase()];
    let list = [...data.search_terms];
    if (effectiveBand) {
      list = list.filter((t) => {
        const v = getV(t.search_term);
        return v ? sqrGradeMatchesBand(v.grade, effectiveBand) : false;
      });
    }
    list.sort((a, b) => {
      const ca = getV(a.search_term)?.total_search_count ?? -1;
      const cb = getV(b.search_term)?.total_search_count ?? -1;
      return cb - ca;
    });
    return list;
  }, [data?.search_terms, effectiveBand, volumeMap]);

  const displayTerms = useMemo(() => {
    if (!filteredSortedTerms.length) return [];
    return expanded ? filteredSortedTerms : filteredSortedTerms.slice(0, 50);
  }, [filteredSortedTerms, expanded]);

  const toggleTerm = (term: string) => {
    const low = term.toLowerCase();
    if (selectedTerms.includes(low)) onSelectedChange(selectedTerms.filter(w => w !== low));
    else onSelectedChange([...selectedTerms, low]);
  };


  if (loading) {
    return (
      <div style={{
        padding: '8px 10px', borderRadius: 8, background: '#FFF7ED',
        border: '1px solid #FDBA74', marginBottom: 12,
      }}>
        <Spin size="small" />
        <Text style={{ marginLeft: 8, fontSize: 12, color: '#c2410c' }}>正在获取搜索词相关性推荐...</Text>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{
        padding: '6px 10px', borderRadius: 8, background: '#FEF2F2',
        border: '1px solid #FECACA', marginBottom: 12, fontSize: 11, color: '#dc2626',
      }}>
        搜索词推荐: {error}
      </div>
    );
  }

  if (!data) return null;

  if (!data.success) {
    return (
      <div style={{
        padding: '8px 10px', borderRadius: 8, background: '#FFFBEB',
        border: '1px solid #FDE68A', marginBottom: 12,
      }}>
        <Text style={{ fontSize: 12, color: '#92400e' }}>
          <DatabaseOutlined style={{ marginRight: 4 }} />
          搜索词相关性库: {data.message}
        </Text>
        {data.msku_info?.length > 0 && (
          <div style={{ fontSize: 11, color: '#a16207', marginTop: 4 }}>
            MSKU: {data.msku_info.map((m: any) => `${m.msku}(${m.store_name})`).join(', ')}
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <Text strong style={{ fontSize: 12 }}>
          <DatabaseOutlined style={{ marginRight: 4, color: '#0e7490' }} />
          搜索词相关性库
          <Tag color="cyan" style={{ fontSize: 10, marginLeft: 4, verticalAlign: 'middle' }}>
            {data.total_unique} 词
          </Tag>
        </Text>
      </div>

      {/* MSKU + 店铺信息 */}
      <div style={{
        padding: '6px 8px', borderRadius: 6, background: 'rgba(6, 23, 38, 0.88)',
        border: '1px solid rgba(83, 210, 255, 0.24)', marginBottom: 6, fontSize: 11,
      }}>
        <Text style={{ fontSize: 11 }}>
          MSKU: <Text strong style={{ fontSize: 11 }}>{data.matched_msku}</Text>
          <span style={{ margin: '0 8px', color: '#d1d5db' }}>|</span>
          店铺: <Text strong style={{ fontSize: 11 }}>{data.matched_store}</Text>
        </Text>
      </div>

      {/* 相关性等级单选标签 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
        {RELEVANCE_LEVELS.map(lv => {
          const count = data.summary[lv.key] ?? 0;
          if (count === 0) return null;
          const active = activeLevel === lv.key;
          return (
            <span
              key={lv.key}
              onClick={() => onLevelChange(active ? null : lv.key)}
              style={{
                fontSize: 10, padding: '1px 7px', borderRadius: 4, cursor: 'pointer',
                background: active ? lv.bg : 'rgba(6, 23, 38, 0.64)',
                color: active ? lv.color : '#9db9c5',
                border: `1px solid ${active ? lv.border : 'rgba(122, 205, 232, 0.22)'}`,
                fontWeight: active ? 600 : 400,
                transition: 'all 0.15s',
              }}
            >
              {lv.key} ({count})
            </span>
          );
        })}
      </div>

      {/* 搜索量分档（互斥）：筛选后按 SQR 次数降序 */}
      {activeLevel && data.search_terms.length > 0 && (
        <div style={{ marginBottom: 6, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
          <Text type="secondary" style={{ fontSize: 10, marginRight: 2 }}>搜索量档</Text>
          {volumeLoading && <Spin size="small" />}
          {SQR_TRAFFIC_BAND_OPTS.map(opt => {
            const active = sqrBand === opt.key;
            return (
              <button
                key={opt.key === null ? 'all' : opt.key}
                type="button"
                disabled={volumeLoading}
                onClick={() => setSqrBand(opt.key)}
                style={{
                  fontSize: 10,
                  padding: '2px 8px',
                  borderRadius: 4,
                  cursor: volumeLoading ? 'not-allowed' : 'pointer',
                  border: `1px solid ${active ? 'rgba(103, 232, 249, 0.48)' : 'rgba(122, 205, 232, 0.22)'}`,
                  background: active ? 'rgba(6, 182, 212, 0.16)' : 'rgba(6, 23, 38, 0.64)',
                  color: active ? '#8eeaff' : '#9db9c5',
                  fontWeight: active ? 600 : 400,
                  lineHeight: 1.3,
                }}
                title={opt.hint}
              >
                {opt.key === null ? '全部' : `${opt.label}档`}
              </button>
            );
          })}
        </div>
      )}
      {volumeError && (
        <div style={{ fontSize: 10, color: '#dc2626', marginBottom: 6 }}>{volumeError}</div>
      )}

      {/* 搜索词列表 */}
      {levelLoading && (
        <div style={{ padding: 8, textAlign: 'center' }}>
          <Spin size="small" />
          <Text style={{ marginLeft: 8, fontSize: 11, color: '#6b7280' }}>加载 {activeLevel} 搜索词...</Text>
        </div>
      )}

      {!levelLoading && activeLevel && data.search_terms.length > 0 && (
        <div style={{
          maxHeight: 240, overflowY: 'auto', border: '1px solid rgba(83, 210, 255, 0.24)', borderRadius: 8,
          padding: '4px 8px', background: 'rgba(2, 12, 23, 0.72)',
        }}>
          {!volumeLoading && filteredSortedTerms.length === 0 && (
            <div style={{ padding: 12, textAlign: 'center', fontSize: 11, color: '#9ca3af' }}>
              {volumeError ? 'SQR 数据不可用' : (sqrBand ? '当前搜索量档位下无匹配词' : '无词')}
            </div>
          )}
          {displayTerms.map((t) => {
            const checked = selectedTerms.includes(t.search_term.toLowerCase());
            const lv = RELEVANCE_LEVELS.find(l => l.key === t.relevance);
            const vrow = volumeMap[t.search_term.toLowerCase()];
            const scoreLt = vrow ? sqrVolumeScoreLetter(vrow.grade) : null;
            const stScore = scoreLt ? SCORE_LETTER_STYLE[scoreLt] : null;
            return (
              <div key={t.search_term} style={{
                display: 'flex', alignItems: 'center', gap: 5, padding: '2px 0',
                borderBottom: '1px solid rgba(122, 205, 232, 0.1)',
              }}>
                <Checkbox checked={checked} onChange={() => toggleTerm(t.search_term)} />
                <Tooltip title={`相关性 Excel 分值：${t.total_score ?? '-'}`}>
                  <span style={{
                    fontSize: 12, cursor: 'pointer', fontWeight: checked ? 600 : 400,
                    color: checked ? '#e9f8ff' : '#b7d7e4', maxWidth: 150, overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }} onClick={() => toggleTerm(t.search_term)}>
                    {t.search_term}
                  </span>
                </Tooltip>
                {lv && (
                  <span style={{
                    fontSize: 10, padding: '0 5px', borderRadius: 3, lineHeight: '16px',
                    background: lv.bg, color: lv.color, border: `1px solid ${lv.border}`,
                    fontWeight: 500, whiteSpace: 'nowrap', flexShrink: 0,
                  }}>
                    {t.relevance}
                  </span>
                )}
                {t.total_score != null && t.total_score > 0 && (
                  <Text type="secondary" style={{ fontSize: 10, whiteSpace: 'nowrap', flexShrink: 0 }}>
                    {t.total_score.toFixed(2)}
                  </Text>
                )}
                <Text type="secondary" style={{ fontSize: 9, flexShrink: 0 }}>评分</Text>
                {vrow && stScore ? (
                  <Tooltip
                    title={(
                      <div style={{ fontSize: 12 }}>
                        <div><strong>汇总次数：</strong>{formatSqrDisplayCount(vrow.total_search_count)}</div>
                        <div><strong>档位：</strong>{vrow.grade_label}</div>
                        <div style={{ marginTop: 4, fontSize: 11, color: '#d1d5db' }}>统计自 {vrow.since_date} 起</div>
                        {vrow.cached ? <div style={{ fontSize: 10, color: '#9ca3af' }}>命中服务端缓存</div> : null}
                      </div>
                    )}
                  >
                    <span style={{
                      fontSize: 10, fontWeight: 700, minWidth: 18, textAlign: 'center',
                      padding: '0 5px', borderRadius: 3, lineHeight: '18px', cursor: 'help',
                      flexShrink: 0,
                      background: stScore.bg, color: stScore.color, border: `1px solid ${stScore.border}`,
                    }}>
                      {scoreLt}
                    </span>
                  </Tooltip>
                ) : (
                  <span style={{ fontSize: 10, color: '#d1d5db', flexShrink: 0 }}>—</span>
                )}
              </div>
            );
          })}
          {!expanded && filteredSortedTerms.length > 50 && (
            <div style={{ textAlign: 'center', padding: '4px 0' }}>
              <Button type="link" size="small" style={{ fontSize: 11 }}
                onClick={() => setExpanded(true)}>
                展开全部 ({filteredSortedTerms.length} 条)
              </Button>
            </div>
          )}
        </div>
      )}

      {!levelLoading && !activeLevel && (
        <div style={{ padding: 8, textAlign: 'center', color: '#9ca3af', fontSize: 11 }}>
          请点击上方等级标签查看对应搜索词
        </div>
      )}

      {!levelLoading && activeLevel && data.search_terms.length === 0 && (
        <div style={{ padding: 8, textAlign: 'center', color: '#9ca3af', fontSize: 11 }}>
          当前等级无搜索词
        </div>
      )}
    </div>
  );
}

/* ─── 四维雷达得分图（纯 SVG） ─── */

const RADAR_DIMS = [
  { key: 'cosmo', label: 'COSMO\n关系覆盖' },
  { key: 'keywords', label: '关键词\n覆盖' },
  { key: 'rufus', label: 'Rufus\n语义覆盖' },
  { key: 'idq', label: 'IDQ\n语义完整' },
] as const;

const dimScoreColor = (v: number) =>
  v >= 20 ? '#10B981' : v >= 15 ? '#6366F1' : v >= 10 ? '#F59E0B' : '#EF4444';
const totalScoreColor = (t: number) =>
  t >= 80 ? '#10B981' : t >= 60 ? '#6366F1' : t >= 40 ? '#F59E0B' : '#EF4444';

function RadarScoreChart({ scores, size = 300 }: { scores: EvaluateScores; size?: number }) {
  const pad = 60;
  const vw = size + pad * 2;
  const vh = size + pad * 2;
  const cx = vw / 2;
  const cy = vh / 2;
  const maxR = size * 0.32;
  const levels = [5, 10, 15, 20, 25];
  const n = RADAR_DIMS.length;
  const angleStep = (2 * Math.PI) / n;
  const startAngle = -Math.PI / 2;

  const getPoint = (index: number, value: number) => {
    const angle = startAngle + index * angleStep;
    const r = (value / 25) * maxR;
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  };

  const gridPaths = levels.map((lv) => {
    const pts = Array.from({ length: n }, (_, i) => getPoint(i, lv));
    return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + ' Z';
  });

  const values = RADAR_DIMS.map((d) => (scores[d.key] as { subtotal: number }).subtotal);
  const dataPts = values.map((v, i) => getPoint(i, v));
  const dataPath = dataPts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + ' Z';

  const tColor = totalScoreColor(scores.total);
  const gradId = `radar-fill-${scores.total}`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <svg width={vw} height={vh} viewBox={`0 0 ${vw} ${vh}`} style={{ overflow: 'visible' }}>
        <defs>
          <radialGradient id={gradId} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={tColor} stopOpacity={0.3} />
            <stop offset="100%" stopColor={tColor} stopOpacity={0.08} />
          </radialGradient>
        </defs>
        {gridPaths.map((d, i) => (
          <path key={i} d={d} fill="none" stroke="#e5e7eb" strokeWidth={1}
            strokeDasharray={i < levels.length - 1 ? '3,3' : undefined} />
        ))}
        {RADAR_DIMS.map((_, i) => {
          const edge = getPoint(i, 25);
          return <line key={i} x1={cx} y1={cy} x2={edge.x} y2={edge.y} stroke="#d1d5db" strokeWidth={1} />;
        })}
        <path d={dataPath} fill={`url(#${gradId})`} stroke={tColor} strokeWidth={2.5} strokeLinejoin="round" />
        {dataPts.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={5}
            fill="#fff" stroke={dimScoreColor(values[i])} strokeWidth={2.5} />
        ))}
        {RADAR_DIMS.map((dim, i) => {
          const labelR = maxR + 38;
          const angle = startAngle + i * angleStep;
          const lx = cx + labelR * Math.cos(angle);
          const ly = cy + labelR * Math.sin(angle);
          const lines = dim.label.split('\n');
          const clr = dimScoreColor(values[i]);
          return (
            <g key={dim.key}>
              {lines.map((line, li) => (
                <text key={li} x={lx} y={ly + (li - (lines.length - 1) / 2) * 15}
                  textAnchor="middle" dominantBaseline="central"
                  fill="#374151" fontSize={12} fontWeight={500}>
                  {line}
                </text>
              ))}
              <text x={lx} y={ly + lines.length * 8 + 6}
                textAnchor="middle" dominantBaseline="central"
                fill={clr} fontSize={14} fontWeight={700}>
                {values[i]}/25
              </text>
            </g>
          );
        })}
        <text x={cx} y={cy - 10} textAnchor="middle" dominantBaseline="central"
          fill={tColor} fontSize={28} fontWeight={800}>
          {scores.total}
        </text>
        <text x={cx} y={cy + 14} textAnchor="middle" dominantBaseline="central"
          fill="#9ca3af" fontSize={11}>
          / 100 分
        </text>
      </svg>
    </div>
  );
}

/* ─── 维度分析折叠面板 ─── */

const DIM_META_ICONS: Record<string, { label: string; icon: string }> = {
  cosmo: { label: 'COSMO 关系覆盖', icon: '🔗' },
  keywords: { label: '关键词覆盖', icon: '🔍' },
  rufus: { label: 'Rufus 语义覆盖', icon: '🤖' },
  idq: { label: 'IDQ 语义完整性', icon: '📋' },
};

function DimensionPanel({ dimKey, analysis, score }: {
  dimKey: string; analysis: DimensionAnalysis; score: number;
}) {
  const meta = DIM_META_ICONS[dimKey] || { label: dimKey, icon: '📊' };
  const pct = Math.round((score / 25) * 100);
  const barColor = dimScoreColor(score);

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 16 }}>{meta.icon}</span>
        <Text strong style={{ color: barColor, fontSize: 14 }}>{meta.label}</Text>
        <Tag color={barColor} style={{ marginLeft: 'auto', fontWeight: 700 }}>{score}/25</Tag>
      </div>
      <div style={{ height: 6, background: '#f3f4f6', borderRadius: 3, marginBottom: 8, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: barColor, borderRadius: 3, transition: 'width 0.6s ease' }} />
      </div>
      {analysis.summary && (
        <div style={{ fontSize: 13, color: '#4b5563', marginBottom: 6, lineHeight: 1.6 }}>{analysis.summary}</div>
      )}
      {analysis.strengths?.length > 0 && (
        <div style={{ marginBottom: 4 }}>
          <Text type="success" style={{ fontSize: 12, fontWeight: 600 }}>✅ 优势：</Text>
          <span style={{ fontSize: 12, color: '#374151' }}>{analysis.strengths.join('；')}</span>
        </div>
      )}
      {analysis.weaknesses?.length > 0 && (
        <div style={{ marginBottom: 4 }}>
          <Text type="danger" style={{ fontSize: 12, fontWeight: 600 }}>⚠️ 不足：</Text>
          <span style={{ fontSize: 12, color: '#374151' }}>{analysis.weaknesses.join('；')}</span>
        </div>
      )}
      {analysis.suggestions?.length > 0 && (
        <div>
          <Text type="warning" style={{ fontSize: 12, fontWeight: 600 }}>💡 建议：</Text>
          <span style={{ fontSize: 12, color: '#374151' }}>{analysis.suggestions.join('；')}</span>
        </div>
      )}
    </div>
  );
}

/* ─── 诊断结果 ─── */

function AnalyzeResultCard({ data }: { data: ListingAnalyzeResponse }) {
  const hasScores = !!data.scores;
  const hasAnalysis = !!data.evaluate_analysis;

  return (
    <Card
      title={
        <Space>
          <BarChartOutlined style={{ color: '#10B981' }} />
          <span>Listing 四维诊断报告</span>
          {data.score != null && (
            <Tag
              color={data.score >= 70 ? 'success' : data.score >= 50 ? 'warning' : 'error'}
              style={{ fontSize: 14, padding: '2px 12px' }}
            >
              {data.score} / 100 分
            </Tag>
          )}
        </Space>
      }
      style={{ borderRadius: 12, marginTop: 0 }}
    >
      {hasScores ? (
        <>
          {/* 雷达图 + 总结 */}
          <Row gutter={24} align="middle">
            <Col xs={24} md={12} lg={10} style={{ display: 'flex', justifyContent: 'center', minHeight: 280 }}>
              <RadarScoreChart scores={data.scores!} size={260} />
            </Col>
            <Col xs={24} md={12} lg={14}>
              {data.overall_summary && (
                <Alert
                  type="info" showIcon
                  message="综合评判"
                  description={data.overall_summary}
                  style={{ marginBottom: 16, borderRadius: 8 }}
                />
              )}
              {data.priority_actions && data.priority_actions.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <Text strong style={{ fontSize: 13, color: '#EF4444' }}>🎯 优先行动：</Text>
                  <ol style={{ margin: '6px 0 0 16px', padding: 0, fontSize: 13, lineHeight: 1.8, color: '#374151' }}>
                    {data.priority_actions.map((a, i) => <li key={i}>{a}</li>)}
                  </ol>
                </div>
              )}
            </Col>
          </Row>

          {/* 四维分析详情 */}
          {hasAnalysis && (
            <Collapse
              ghost
              style={{ marginTop: 16 }}
              items={Object.keys(DIM_META_ICONS).map((dimKey) => {
                const dimAnalysis = data.evaluate_analysis![dimKey as keyof EvaluateAnalysis];
                const dimScore = (data.scores![dimKey as keyof EvaluateScores] as { subtotal: number }).subtotal;
                const meta = DIM_META_ICONS[dimKey];
                const clr = dimScoreColor(dimScore);
                return {
                  key: dimKey,
                  label: (
                    <Space>
                      <span>{meta.icon}</span>
                      <Text strong style={{ color: clr }}>{meta.label}</Text>
                      <Tag color={clr} style={{ fontWeight: 700 }}>
                        {dimScore}/25
                      </Tag>
                    </Space>
                  ),
                  children: (
                    <DimensionPanel
                      dimKey={dimKey}
                      analysis={dimAnalysis as DimensionAnalysis}
                      score={dimScore}
                    />
                  ),
                };
              })}
            />
          )}
        </>
      ) : (
        <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, fontSize: 14 }}>
          {data.analysis}
        </div>
      )}
    </Card>
  );
}

function DeepDiagnosticResultCard({ data }: { data: ListingDeepDiagnosticResponse }) {
  const renderList = (items?: string[]) => {
    const list = (items || []).filter(Boolean);
    if (!list.length) return <Text style={{ color: 'rgba(223,247,255,0.62)', fontSize: 13 }}>暂无明确结论</Text>;
    return (
      <ul style={{ margin: '8px 0 0 18px', padding: 0, color: '#dff7ff', fontSize: 13, lineHeight: 1.85 }}>
        {list.map((item, i) => <li key={`${item}-${i}`}>{item}</li>)}
      </ul>
    );
  };
  const renderField = (label: string, content?: string | string[]) => (
    <div style={{ marginTop: 12 }}>
      <Text strong style={{ color: '#7acde8', fontSize: 13 }}>{label}</Text>
      {Array.isArray(content)
        ? renderList(content)
        : (
          <div style={{ marginTop: 6, color: '#dff7ff', fontSize: 13, lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>
            {content || '暂无明确结论'}
          </div>
        )}
    </div>
  );
  const sectionStyle: CSSProperties = {
    borderRadius: 12,
    padding: 16,
    border: '1px solid rgba(122, 205, 232, 0.22)',
    background: 'linear-gradient(135deg, rgba(6, 23, 38, 0.92), rgba(8, 36, 54, 0.78))',
    boxShadow: '0 0 24px rgba(34, 211, 238, 0.08) inset',
  };

  return (
    <Card
      title={
        <Space>
          <BarChartOutlined style={{ color: '#22d3ee' }} />
          <span style={{ color: '#e6fbff' }}>Listing 深度诊断报告</span>
          <Tag style={{ color: '#7acde8', background: 'rgba(34, 211, 238, 0.10)', borderColor: 'rgba(34, 211, 238, 0.34)' }}>
            自我诊断 + 竞品对比
          </Tag>
        </Space>
      }
      style={{
        borderRadius: 12,
        marginTop: 0,
        border: '1px solid rgba(83, 210, 255, 0.22)',
        background: 'linear-gradient(135deg, rgba(4, 14, 32, 0.96), rgba(3, 18, 32, 0.92))',
      }}
      styles={{ body: { padding: 16 } }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 0.9fr) minmax(420px, 1.4fr)', gap: 14 }}>
        <div style={sectionStyle}>
          <Text strong style={{ color: '#e6fbff', fontSize: 15 }}>自我诊断</Text>
          <div style={{ marginTop: 10, color: '#dff7ff', fontSize: 13, lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>
            {data.self_diagnosis.summary || '暂无摘要'}
          </div>
          {renderField('优势', data.self_diagnosis.strengths)}
          {renderField('问题', data.self_diagnosis.weaknesses)}
          {renderField('修改建议', data.self_diagnosis.suggestions)}
        </div>

        <div style={sectionStyle}>
          <Text strong style={{ color: '#e6fbff', fontSize: 15 }}>逐竞品对比</Text>
          {data.competitor_diagnoses?.length ? (
            <Tabs
              size="small"
              style={{ marginTop: 10 }}
              items={data.competitor_diagnoses.map((c) => ({
                key: c.competitor_asin || c.competitor_label,
                label: `竞品 ${c.competitor_label || ''}`,
                children: (
                  <div style={{ color: '#dff7ff' }}>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10 }}>
                      {c.competitor_image && (
                        <Image src={c.competitor_image} width={72} height={72} style={{ objectFit: 'cover', borderRadius: 8 }} preview={false} />
                      )}
                      <div style={{ minWidth: 0 }}>
                        <div style={{ color: '#e6fbff', fontSize: 13, fontWeight: 800, lineHeight: 1.4 }}>
                          {c.competitor_title || c.competitor_asin}
                        </div>
                        <div style={{ marginTop: 5, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          {c.competitor_brand && <Tag color="cyan">品牌 {c.competitor_brand}</Tag>}
                          {c.competitor_monthly_sales_text && <Tag color="green">{c.competitor_monthly_sales_text}</Tag>}
                          {!c.competitor_monthly_sales_text && c.competitor_bsr_rank && <Tag color="blue">BSR {c.competitor_bsr_rank}</Tag>}
                        </div>
                      </div>
                    </div>
                    <div style={{ fontSize: 13, lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>
                      {c.summary || '暂无摘要'}
                    </div>
                    {renderField('图片对比', c.image_comparison)}
                    {renderField('品牌对比', c.brand_comparison)}
                    {renderField('评论对比', c.review_comparison)}
                    {renderField('Listing 对比', c.listing_comparison)}
                    {renderField('标题对比', c.title_comparison)}
                    {renderField('场景对比', c.scenario_comparison)}
                    {renderField('销量/热度对比', c.sales_comparison)}
                    {renderField('我产品优势', c.own_advantages)}
                    {renderField('我产品劣势', c.own_disadvantages)}
                    {renderField('竞品优势', c.competitor_advantages)}
                    {renderField('竞品劣势', c.competitor_disadvantages)}
                    {renderField('针对性建议', c.suggestions)}
                  </div>
                ),
              }))}
            />
          ) : (
            <div style={{ marginTop: 10, color: '#dff7ff', fontSize: 13 }}>
              暂无逐竞品对比结果，请先确保已抓取到 5 条竞品。
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

/* ─── 优化版本卡 ─── */

const MAX_REFINE = 3;

interface RefineVersion {
  optimized: ListingOptimizeResponse['optimized'];
  feedback: string;
  /** 多候选模式携带的变体元数据（评分、排名、是否最优） */
  variant?: OptimizedVariant;
  /** 多候选模式下该候选在全部 variants 中的排名（1 为最优） */
  variantRank?: number;
  /** 多候选总数 */
  variantTotal?: number;
  /** 关联的 llm_memory.id，用于回收用户反馈（点赞/差劲/评论） */
  memoryId?: number | null;
}

/**
 * 将 /lsta/optimize 返回结果映射为 VersionCard 可消费的 RefineVersion[]。
 * - 多候选模式：按后端已排好的总分倒序展开，每张卡片携带评分/排名徽章。
 * - 单候选模式：退化为原行为，仅一张"初始优化"卡片。
 */
function buildVersionsFromOptimizeResult(data: ListingOptimizeResponse): RefineVersion[] {
  const variants = data.variants || [];
  const variantMemIds = data.variant_memory_ids ?? [];
  const mem = data.memory_id ?? null;
  if (variants.length > 1) {
    return variants.map((v, i) => ({
      optimized: v.listing,
      feedback: '',
      variant: v,
      variantRank: i + 1,
      variantTotal: variants.length,
      // 优先用各自独立的记忆 id，回退到整体 memory_id
      memoryId: (variantMemIds[i] ?? mem),
    }));
  }
  return [{ optimized: data.optimized, feedback: '', memoryId: mem }];
}

function RefinePanel({
  asin, marketplace, versions, onNewVersion, sessionId, selectedModel,
}: {
  asin: string; marketplace: string; versions: RefineVersion[];
  onNewVersion: (v: RefineVersion) => void; sessionId: string; selectedModel?: string;
}) {
  const [feedback, setFeedback] = useState('');
  const [loading, setLoading] = useState(false);
  const [showInput, setShowInput] = useState(false);

  const lastVersion = versions[versions.length - 1].optimized;
  const canRefine = versions.length <= MAX_REFINE;

  const handleRefine = async () => {
    if (!feedback.trim()) { message.warning('请输入修改意见'); return; }
    setLoading(true);
    try {
      const { data } = await listingApi.refine({
        asin, marketplace,
        current_title: lastVersion.title,
        current_bullet_points: lastVersion.bullet_points,
        current_description: lastVersion.description,
        current_search_terms: lastVersion.search_terms,
        user_feedback: feedback.trim(),
        session_id: sessionId, model: selectedModel,
      });
      onNewVersion({ optimized: data.optimized, feedback: feedback.trim() });
      setFeedback(''); setShowInput(false);
    } catch (e: any) { message.error(e.message || '迭代修改失败'); }
    finally { setLoading(false); }
  };

  if (!canRefine) return null;

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', minWidth: showInput ? 320 : 60, padding: '0 8px',
    }}>
      {!showInput ? (
        <div onClick={() => setShowInput(true)}
          style={{
            width: 48, height: 48, borderRadius: '50%', cursor: 'pointer',
            background: R[1],
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: 24, fontWeight: 700,
            boxShadow: `0 4px 12px ${ACCENT}66`, transition: 'all 0.3s',
          }}
          title={`追加修改（还剩 ${MAX_REFINE - versions.length + 1} 次）`}
          onMouseEnter={e => { (e.target as HTMLDivElement).style.transform = 'scale(1.15)'; }}
          onMouseLeave={e => { (e.target as HTMLDivElement).style.transform = 'scale(1)'; }}
        >+</div>
      ) : (
        <Card size="small" style={{ borderRadius: 12, width: '100%', border: `2px dashed ${RAINBOW[1].from}` }}
          styles={{ body: { padding: 12 } }}>
          <div style={{ marginBottom: 8 }}>
            <Text strong style={{ color: RAINBOW[1].from, fontSize: 13 }}>修改意见（第 {versions.length} 次迭代）</Text>
            <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>剩余 {MAX_REFINE - versions.length + 1} 次</Text>
          </div>
          <Input.TextArea value={feedback} onChange={e => setFeedback(e.target.value)}
            placeholder="例如：标题太长了，缩短到150字符以内；五点描述第3条改为强调防水性能..."
            autoSize={{ minRows: 3, maxRows: 6 }} style={{ marginBottom: 8, borderRadius: 8 }} autoFocus />
          <Space>
            <Button type="primary" size="small" loading={loading} onClick={handleRefine}
              style={{ background: R[1] }}>生成修改版</Button>
            <Button size="small" onClick={() => { setShowInput(false); setFeedback(''); }}>取消</Button>
          </Space>
        </Card>
      )}
    </div>
  );
}

function VersionCard({
  version, index, asin, marketplace, selectedKeywords = [], trafficWords = [], searchLibWords = [],
  productContext, reviewAnalysis, competitorProducts = [],
}: {
  version: RefineVersion; index: number; asin: string; marketplace: string;
  selectedKeywords?: string[];
  trafficWords?: TrafficWordItem[];
  searchLibWords?: string[];
  productContext?: ProductData | null;
  reviewAnalysis?: ReviewAnalysisResult | null;
  competitorProducts?: ProductData[];
}) {
  const { optimized, feedback, variant, variantRank, variantTotal, memoryId } = version;
  const isVariantMode = !!variant && (variantTotal ?? 0) > 1;
  const isBestVariant = variant?.is_best === true;

  // 用第一阶段的数据在前端构造 wordAnalysis 供高亮使用
  const wordSourceMap = useMemo<Map<string, 'traffic' | 'manual' | 'searchlib' | 'multi'> | null>(() => {
    if (!trafficWords.length && !selectedKeywords.length) return null;
    const map = new Map<string, 'traffic' | 'manual' | 'searchlib' | 'multi'>();
    const trafficSet = new Set(trafficWords.map(tw => tw.word.toLowerCase()));
    const searchLibSet = new Set(searchLibWords.map(w => w.toLowerCase()));
    for (const kw of selectedKeywords) {
      const low = kw.toLowerCase();
      const inTraffic = trafficSet.has(low);
      const inSearchLib = searchLibSet.has(low);
      if (inTraffic && inSearchLib) map.set(low, 'multi');
      else if (inTraffic) map.set(low, 'traffic');
      else if (inSearchLib) map.set(low, 'searchlib');
      else map.set(low, 'manual');
    }
    return map.size > 0 ? map : null;
  }, [trafficWords, selectedKeywords, searchLibWords]);

  // 流量词元数据，供 HighlightedText 的 Tooltip 展示 ABA/SQR/理由
  const trafficWordMeta = useMemo<Map<string, TrafficWordItem> | null>(() => {
    if (!trafficWords.length) return null;
    const m = new Map<string, TrafficWordItem>();
    for (const tw of trafficWords) {
      if (tw?.word) m.set(tw.word.toLowerCase(), tw);
    }
    return m.size > 0 ? m : null;
  }, [trafficWords]);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(optimized.title);
  const [editBullets, setEditBullets] = useState([...optimized.bullet_points]);
  const [editDesc, setEditDesc] = useState(optimized.description);
  const [editSearch, setEditSearch] = useState(optimized.search_terms);
  const [diagModel, setDiagModel] = useState<string | undefined>(undefined);
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagResult, setDiagResult] = useState<ListingDeepDiagnosticResponse | null>(null);
  const [submitAsin, setSubmitAsin] = useState(asin);
  const [submitting, setSubmitting] = useState(false);
  // 用户反馈：点赞 / 差劲 / 评论
  const [feedbackLiked, setFeedbackLiked] = useState(false);
  const [feedbackDisliked, setFeedbackDisliked] = useState(false);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [commentOpen, setCommentOpen] = useState(false);
  const [commentDraft, setCommentDraft] = useState('');
  const [commentSaved, setCommentSaved] = useState('');
  const [recordOpen, setRecordOpen] = useState(false);
  const [recordReason, setRecordReason] = useState('');
  const [recordDirection, setRecordDirection] = useState('');
  const [recordRemark, setRecordRemark] = useState('');
  const [recordSubmitting, setRecordSubmitting] = useState(false);

  const startEdit = () => {
    setEditTitle(optimized.title); setEditBullets([...optimized.bullet_points]);
    setEditDesc(optimized.description); setEditSearch(optimized.search_terms);
    setEditing(true);
  };
  const saveEdit = () => {
    optimized.title = editTitle; optimized.bullet_points = editBullets;
    optimized.description = editDesc; optimized.search_terms = editSearch;
    setEditing(false); message.success('修改已保存');
  };
  const handleBulletChange = (i: number, v: string) => {
    const next = [...editBullets]; next[i] = v; setEditBullets(next);
  };
  const submitFeedback = async (
    payload: { liked?: boolean | null; disliked?: boolean | null; comment?: string | null },
    successMsg: string,
  ) => {
    if (!memoryId) {
      message.warning('当前结果暂未持久化，无法提交反馈');
      return false;
    }
    setFeedbackSubmitting(true);
    try {
      await listingApi.submitFeedback({ memory_id: memoryId, ...payload });
      message.success(successMsg);
      return true;
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '提交反馈失败');
      return false;
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const handleLike = async () => {
    const next = !feedbackLiked;
    const ok = await submitFeedback(
      { liked: next, disliked: next ? false : null },
      next ? '已点赞，感谢反馈' : '已取消点赞',
    );
    if (ok) {
      setFeedbackLiked(next);
      if (next) setFeedbackDisliked(false);
    }
  };

  const handleDislike = async () => {
    const next = !feedbackDisliked;
    const ok = await submitFeedback(
      { disliked: next, liked: next ? false : null },
      next ? '已记录"差劲"，我们会改进' : '已取消"差劲"标记',
    );
    if (ok) {
      setFeedbackDisliked(next);
      if (next) setFeedbackLiked(false);
    }
  };

  const handleSubmitComment = async () => {
    const text = commentDraft.trim();
    const ok = await submitFeedback(
      { comment: text },
      text ? '评论已提交' : '评论已清空',
    );
    if (ok) {
      setCommentSaved(text);
      setCommentOpen(false);
    }
  };

  const handleDiagnose = async () => {
    const t = editing ? editTitle : optimized.title;
    if (!t.trim()) { message.warning('标题不能为空'); return; }
    const baseProduct = productContext || {
      asin, marketplace, title: t, brand: '', price: '', currency: '', rating: '', review_count: '',
      category: '', bsr_rank: '', bullet_points: [], description: '', images: [], reviews: [],
    };
    setDiagnosing(true);
    setDiagResult(null);
    try {
      const pd: ProductData = {
        ...baseProduct,
        asin, marketplace,
        title: t,
        bullet_points: editing ? editBullets : optimized.bullet_points,
        description: editing ? editDesc : optimized.description,
      };
      const { data } = await listingApi.deepDiagnostic({
        asin, marketplace, model: diagModel,
        product_data: pd,
        current_title: pd.title,
        current_bullet_points: pd.bullet_points,
        current_description: pd.description,
        current_search_terms: editing ? editSearch : optimized.search_terms,
        review_analysis: reviewAnalysis ?? undefined,
        competitor_products: competitorProducts.slice(0, 5),
      });
      setDiagResult(data);
    } catch (e: any) { message.error(e.message || '诊断失败'); }
    finally { setDiagnosing(false); }
  };

  const renderDiagList = (items?: string[]) => {
    const list = (items || []).filter(Boolean);
    if (!list.length) return <Text style={{ color: 'rgba(223,247,255,0.62)', fontSize: 12 }}>暂无明确结论</Text>;
    return (
      <ul style={{ margin: '6px 0 0 16px', padding: 0, color: '#dff7ff', fontSize: 12, lineHeight: 1.75 }}>
        {list.map((item, i) => <li key={`${item}-${i}`}>{item}</li>)}
      </ul>
    );
  };

  const renderDiagField = (label: string, content?: string | string[]) => (
    <div style={{ marginTop: 10 }}>
      <Text strong style={{ color: '#7acde8', fontSize: 12 }}>{label}</Text>
      {Array.isArray(content)
        ? renderDiagList(content)
        : (
          <div style={{
            marginTop: 5, color: '#dff7ff', fontSize: 12, lineHeight: 1.7,
            whiteSpace: 'pre-wrap',
          }}>
            {content || '暂无明确结论'}
          </div>
        )}
    </div>
  );

  const handleSubmitToLingxing = () => {
    const t = editing ? editTitle : optimized.title;
    if (!t.trim()) { message.warning('标题不能为空'); return; }
    if (!submitAsin.trim() || submitAsin.trim().length !== 10) {
      message.warning('请输入有效的 10 位 ASIN'); return;
    }
    Modal.confirm({
      title: '确认提交到领星',
      content: (
        <div style={{ fontSize: 13, lineHeight: 1.8 }}>
          <p>即将把以下 Listing 数据提交到<strong>领星 ERP</strong>：</p>
          <ul style={{ paddingLeft: 20 }}>
            <li><strong>目标 ASIN</strong>：{submitAsin.trim()}</li>
            <li><strong>标题</strong>：{t.slice(0, 60)}{t.length > 60 ? '...' : ''}</li>
            <li><strong>五点描述</strong>：{(editing ? editBullets : optimized.bullet_points).length} 条</li>
            <li><strong>站点</strong>：{marketplace}</li>
          </ul>
          <p style={{ color: ACCENT, fontWeight: 500 }}>提交后将直接更新领星中的 Listing 数据，请确认无误。</p>
        </div>
      ),
      okText: '确认提交',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setSubmitting(true);
        try {
          const { data: res } = await listingApi.submitToLingxing({
            asin: submitAsin.trim(),
            marketplace,
            title: editing ? editTitle : optimized.title,
            bullet_points: editing ? editBullets : optimized.bullet_points,
            description: editing ? editDesc : optimized.description,
            search_terms: editing ? editSearch : optimized.search_terms,
          });
          if (res.success) message.success(res.message || '提交成功');
          else message.error(res.message || '提交失败');
        } catch (e: any) {
          message.error(e?.response?.data?.detail || e.message || '提交领星失败');
        } finally { setSubmitting(false); }
      },
    });
  };

  const buildOriginalListing = (): OptimizedListing => ({
    title: productContext?.title || '',
    bullet_points: productContext?.bullet_points || [],
    description: productContext?.description || '',
    search_terms: '',
    optimization_notes: '',
    word_analysis: null,
  });

  const handleCreateRecord = async () => {
    const t = editing ? editTitle : optimized.title;
    if (!t.trim()) { message.warning('标题不能为空'); return; }
    setRecordSubmitting(true);
    try {
      const beforeListing = buildOriginalListing();
      const reason = recordReason.trim()
        || optimized.optimization_notes
        || variant?.overall_summary
        || '确认采用该 Listing 优化结果';
      const direction = recordDirection.trim()
        || variant?.priority_actions?.join('；')
        || variant?.free_form_score?.suggestions?.join('；')
        || '提升标题点击、五点转化和关键词覆盖';
      const { data } = await listingApi.createOptimizeRecord({
        asin,
        marketplace,
        store_name: '',
        country_code: marketplace,
        optimization_reason: reason,
        optimization_direction: direction,
        remark: recordRemark.trim(),
        before_listing: beforeListing,
        after_listing: {
          title: editing ? editTitle : optimized.title,
          bullet_points: editing ? editBullets : optimized.bullet_points,
          description: editing ? editDesc : optimized.description,
          search_terms: editing ? editSearch : optimized.search_terms,
          optimization_notes: optimized.optimization_notes,
          word_analysis: optimized.word_analysis,
        },
        before_images: productContext?.images || [],
        after_images: productContext?.images || [],
        metric_period_days: 30,
        variant_rank: variantRank ?? null,
        variant_total: variantTotal ?? null,
        source_memory_id: memoryId ?? null,
        extra: {
          variant_score: variant?.composite_score,
          expose_score: variant?.total_score,
          conversion_score: variant?.free_form_score?.total,
        },
      });
      message.success(`优化记录已入库 #${data.id}`);
      setRecordOpen(false);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '优化记录入库失败');
    } finally {
      setRecordSubmitting(false);
    }
  };

  const curTitle = editing ? editTitle : optimized.title;
  const curBullets = editing ? editBullets : optimized.bullet_points;
  const curDesc = editing ? editDesc : optimized.description;
  const curSearch = editing ? editSearch : optimized.search_terms;

  return (
    <Card size="small"
      style={{
        minWidth: 460, maxWidth: 560, borderRadius: 12, flexShrink: 0,
        border: isBestVariant ? `2px solid #f59e0b` : undefined,
        boxShadow: isBestVariant ? '0 4px 16px rgba(245, 158, 11, 0.25)' : undefined,
      }}
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
          <Space size={4} wrap>
            {isVariantMode ? (
              <>
                <Tag color={isBestVariant ? 'gold' : 'default'} style={{ fontSize: 12, fontWeight: 600 }}>
                  {isBestVariant ? '★ 最优候选' : `候选 ${variantRank}`}
                  {variantTotal ? ` / ${variantTotal}` : ''}
                </Tag>
                {variant?.scores ? (
                  <Tooltip
                    title={
                      <div style={{ fontSize: 12, lineHeight: 1.8 }}>
                        <div style={{ fontWeight: 600, marginBottom: 4 }}>曝光评分（COSMO 四维规则）</div>
                        <div>COSMO: {variant.scores.cosmo.subtotal}/25</div>
                        <div>关键词: {variant.scores.keywords.subtotal}/25</div>
                        <div>Rufus: {variant.scores.rufus.subtotal}/25</div>
                        <div>IDQ: {variant.scores.idq.subtotal}/25</div>
                      </div>
                    }
                  >
                    <Tag
                      color={isBestVariant ? 'orange' : 'blue'}
                      style={{ fontSize: 12, fontWeight: 700, cursor: 'help' }}
                    >
                      曝光 {variant.total_score}/100
                    </Tag>
                  </Tooltip>
                ) : variant?.evaluate_error ? (
                  <Tag color="red" style={{ fontSize: 11 }}>曝光评分失败</Tag>
                ) : null}
                {variant?.free_form_score ? (
                  <Tooltip
                    title={
                      <div style={{ fontSize: 12, lineHeight: 1.8, maxWidth: 320 }}>
                        <div style={{ fontWeight: 600, marginBottom: 4 }}>转化评分（LLM 仅从转化视角打分）</div>
                        {variant.free_form_score.summary && (
                          <div style={{ marginBottom: 4 }}>{variant.free_form_score.summary}</div>
                        )}
                        {variant.free_form_score.strengths?.length > 0 && (
                          <div>✅ {variant.free_form_score.strengths.join('；')}</div>
                        )}
                        {variant.free_form_score.weaknesses?.length > 0 && (
                          <div>⚠️ {variant.free_form_score.weaknesses.join('；')}</div>
                        )}
                      </div>
                    }
                  >
                    <Tag
                      color="purple"
                      style={{ fontSize: 12, fontWeight: 700, cursor: 'help' }}
                    >
                      转化 {variant.free_form_score.total}/100
                    </Tag>
                  </Tooltip>
                ) : variant?.free_form_error ? (
                  <Tag color="red" style={{ fontSize: 11 }}>转化评分失败</Tag>
                ) : null}
                {variant && typeof variant.composite_score === 'number' && variant.composite_score > 0 && (
                  <Tag
                    color={isBestVariant ? 'gold' : 'geekblue'}
                    style={{ fontSize: 12, fontWeight: 700 }}
                    title="综合分 = 曝光×w曝光 + 转化×w转化；权重随三维诊断命中情况动态分配"
                  >
                    综合 {variant.composite_score.toFixed(1)}
                  </Tag>
                )}
              </>
            ) : (
              <Tag color={index === 0 ? 'orange' : 'blue'} style={{ fontSize: 12 }}>
                {index === 0 ? '初始优化' : `第 ${index} 次修改`}
              </Tag>
            )}
            {feedback && <Text type="secondary" style={{ fontSize: 11 }}>意见: {feedback.slice(0, 30)}{feedback.length > 30 ? '...' : ''}</Text>}
            {editing && <Tag color="orange" style={{ fontSize: 10 }}>编辑中</Tag>}
          </Space>
          <Space size={4} wrap>
            <ModelSelector value={diagModel} onChange={setDiagModel}
              style={{ width: 130 }} size="small" placeholder="诊断模型" />
            <Button size="small" type="primary" icon={<BarChartOutlined />} loading={diagnosing}
              onClick={handleDiagnose} style={{ background: R[2] }}>诊断</Button>
            {!editing ? (
              <Button size="small" icon={<EditOutlined />} onClick={startEdit}
                style={{ borderColor: RAINBOW[1].from, color: RAINBOW[1].from }}>修改</Button>
            ) : (
              <Button size="small" type="primary" icon={<CheckOutlined />} onClick={saveEdit}
                style={{ background: RD[2] }}>保存</Button>
            )}
            <Tooltip title={memoryId ? (feedbackLiked ? '取消点赞' : '点赞这条结果') : '结果尚未持久化'}>
              <Button
                size="small"
                icon={feedbackLiked ? <LikeFilled /> : <LikeOutlined />}
                onClick={handleLike}
                loading={feedbackSubmitting}
                disabled={!memoryId}
                type={feedbackLiked ? 'primary' : 'default'}
                style={feedbackLiked
                  ? { background: '#10b981', borderColor: '#10b981' }
                  : { borderColor: '#10b981', color: '#047857' }}
              >
                点赞
              </Button>
            </Tooltip>
            <Tooltip title={memoryId ? (feedbackDisliked ? '取消差劲' : '标记为差劲') : '结果尚未持久化'}>
              <Button
                size="small"
                icon={feedbackDisliked ? <DislikeFilled /> : <DislikeOutlined />}
                onClick={handleDislike}
                loading={feedbackSubmitting}
                disabled={!memoryId}
                type={feedbackDisliked ? 'primary' : 'default'}
                danger={feedbackDisliked}
                style={feedbackDisliked
                  ? undefined
                  : { borderColor: '#ef4444', color: '#b91c1c' }}
              >
                差劲
              </Button>
            </Tooltip>
            <Tooltip title={memoryId ? (commentSaved ? `已留言：${commentSaved.slice(0, 20)}${commentSaved.length > 20 ? '…' : ''}` : '写一条评论') : '结果尚未持久化'}>
              <Button
                size="small"
                icon={<CommentOutlined />}
                onClick={() => { setCommentDraft(commentSaved); setCommentOpen(true); }}
                disabled={!memoryId}
                type={commentSaved ? 'primary' : 'default'}
                style={commentSaved
                  ? { background: '#6366f1', borderColor: '#6366f1' }
                  : { borderColor: '#6366f1', color: '#4338ca' }}
              >
                评论{commentSaved ? '已留' : ''}
              </Button>
            </Tooltip>
            <Tooltip title="确认采用该优化结果，并写入优化记录库">
              <Button
                size="small"
                type="primary"
                icon={<DatabaseOutlined />}
                onClick={() => {
                  setRecordReason(optimized.optimization_notes || variant?.overall_summary || '');
                  setRecordDirection(variant?.priority_actions?.join('；') || variant?.free_form_score?.suggestions?.join('；') || '');
                  setRecordRemark('');
                  setRecordOpen(true);
                }}
                style={{ background: R[3] }}
              >
                确认入库
              </Button>
            </Tooltip>
          </Space>
        </div>
      }
      styles={{ body: { padding: '12px 16px', maxHeight: 650, overflow: 'auto' } }}
    >
      {wordSourceMap && <HighlightLegend />}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong style={{ fontSize: 13, color: ACCENT }}><TagOutlined /> 标题</Text>
          <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copyText(curTitle)} />
        </div>
        {editing ? (
          <Input.TextArea value={editTitle} onChange={e => setEditTitle(e.target.value)}
            autoSize={{ minRows: 2, maxRows: 4 }} style={{ borderRadius: 8, fontSize: 13, marginTop: 4 }} />
        ) : (
          <TranslateHover text={curTitle}>
            <div style={{ background: LIGHT_BG, padding: '8px 12px', borderRadius: 8, fontSize: 13, marginTop: 4, lineHeight: 1.8 }}>
              <HighlightedText text={curTitle} wordSourceMap={wordSourceMap} trafficWordMeta={trafficWordMeta} />
            </div>
          </TranslateHover>
        )}
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong style={{ fontSize: 13, color: ACCENT }}>五点描述</Text>
          <Space size={0}>
            {editing && <Button type="link" size="small" icon={<PlusOutlined />}
              onClick={() => setEditBullets([...editBullets, ''])} />}
            <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copyText(curBullets.join('\n'))} />
          </Space>
        </div>
        {curBullets.map((bp, i) => (
          editing ? (
            <div key={i} style={{
              background: '#fff', padding: '4px 0',
              borderRadius: 8, fontSize: 12, marginTop: 4, lineHeight: 1.5,
            }}>
              <div style={{ display: 'flex', gap: 4, alignItems: 'flex-start' }}>
                <Tag color="orange" style={{ fontSize: 10, padding: '0 3px', marginTop: 6, flexShrink: 0 }}>第{i + 1}条</Tag>
                <Input.TextArea value={bp} onChange={e => handleBulletChange(i, e.target.value)}
                  autoSize={{ minRows: 2, maxRows: 5 }} style={{ flex: 1, borderRadius: 6, fontSize: 12 }} />
                {editBullets.length > 1 && <Button type="text" danger size="small" icon={<DeleteOutlined />}
                  onClick={() => setEditBullets(editBullets.filter((_, j) => j !== i))} style={{ marginTop: 2 }} />}
              </div>
            </div>
          ) : (
            <TranslateHover key={i} text={bp}>
              <div style={{
                background: LIGHT_BG, padding: '6px 12px',
                borderRadius: 8, fontSize: 12, marginTop: 4,
                borderLeft: `3px solid ${ACCENT}`, lineHeight: 1.5,
              }}>
                <Tag color="orange" style={{ fontSize: 10, padding: '0 4px' }}>第{i + 1}条</Tag>
                <HighlightedText text={bp} wordSourceMap={wordSourceMap} trafficWordMeta={trafficWordMeta} />
              </div>
            </TranslateHover>
          )
        ))}
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong style={{ fontSize: 13, color: ACCENT }}>产品描述</Text>
          <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copyText(curDesc)} />
        </div>
        {editing ? (
          <Input.TextArea value={editDesc} onChange={e => setEditDesc(e.target.value)}
            autoSize={{ minRows: 3, maxRows: 10 }} style={{ borderRadius: 8, fontSize: 12, marginTop: 4 }} />
        ) : (
          <TranslateHover text={curDesc}>
            <div style={{ background: LIGHT_BG, padding: '8px 12px', borderRadius: 8, fontSize: 12, lineHeight: 1.8, whiteSpace: 'pre-wrap', marginTop: 4, maxHeight: 200, overflow: 'auto' }}>
              <HighlightedText text={curDesc} wordSourceMap={wordSourceMap} trafficWordMeta={trafficWordMeta} />
            </div>
          </TranslateHover>
        )}
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong style={{ fontSize: 13, color: ACCENT }}>搜索关键词</Text>
          <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copyText(curSearch)} />
        </div>
        {editing ? (
          <Input.TextArea value={editSearch} onChange={e => setEditSearch(e.target.value)}
            autoSize={{ minRows: 2, maxRows: 4 }} style={{ borderRadius: 8, fontSize: 12, marginTop: 4 }} />
        ) : (
          <div style={{ background: '#FEF3C7', padding: '8px 12px', borderRadius: 8, fontSize: 12, marginTop: 4, lineHeight: 1.8 }}>
            <HighlightedText text={curSearch} wordSourceMap={wordSourceMap} trafficWordMeta={trafficWordMeta} />
          </div>
        )}
      </div>
      {isVariantMode && variant && (variant.overall_summary || variant.priority_actions?.length) && (
        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ fontSize: 13, color: isBestVariant ? '#b45309' : '#6366f1' }}>
            曝光评分意见（COSMO 四维）
          </Text>
          <div style={{
            background: isBestVariant ? 'rgba(245, 158, 11, 0.13)' : 'rgba(37, 99, 235, 0.14)',
            border: `1px solid ${isBestVariant ? 'rgba(250, 204, 21, 0.42)' : 'rgba(96, 165, 250, 0.36)'}`,
            padding: '8px 12px', borderRadius: 8, fontSize: 12, lineHeight: 1.6, marginTop: 4,
            color: '#dff7ff',
          }}>
            {variant.overall_summary && (
              <div style={{ marginBottom: variant.priority_actions?.length ? 6 : 0 }}>
                {variant.overall_summary}
              </div>
            )}
            {variant.priority_actions?.length ? (
              <div>
                <Text strong style={{ fontSize: 11, color: '#7c3aed' }}>优先改进：</Text>
                <ol style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                  {variant.priority_actions.slice(0, 3).map((a, i) => (
                    <li key={i} style={{ fontSize: 12, marginBottom: 2 }}>{a}</li>
                  ))}
                </ol>
              </div>
            ) : null}
          </div>
        </div>
      )}
      {isVariantMode && variant?.free_form_score && (
        <div style={{ marginBottom: 12 }}>
          <Space size={6} align="center">
            <Text strong style={{ fontSize: 13, color: '#7c3aed' }}>转化评分意见</Text>
            <Tag color="purple" style={{ fontSize: 11, fontWeight: 700 }}>
              {variant.free_form_score.total}/100
            </Tag>
          </Space>
          <div style={{
            background: 'rgba(88, 28, 135, 0.18)',
            border: '1px solid rgba(167, 139, 250, 0.36)',
            padding: '8px 12px', borderRadius: 8, fontSize: 12, lineHeight: 1.6, marginTop: 4,
            color: '#dff7ff',
          }}>
            {variant.free_form_score.summary && (
              <div style={{ marginBottom: 6 }}>{variant.free_form_score.summary}</div>
            )}
            {variant.free_form_score.strengths?.length > 0 && (
              <div style={{ marginBottom: 2 }}>
                <Text type="success" style={{ fontSize: 11, fontWeight: 600 }}>✅ 优点：</Text>
                <span style={{ fontSize: 12, color: '#dff7ff' }}>
                  {variant.free_form_score.strengths.join('；')}
                </span>
              </div>
            )}
            {variant.free_form_score.weaknesses?.length > 0 && (
              <div style={{ marginBottom: 2 }}>
                <Text type="danger" style={{ fontSize: 11, fontWeight: 600 }}>⚠️ 不足：</Text>
                <span style={{ fontSize: 12, color: '#dff7ff' }}>
                  {variant.free_form_score.weaknesses.join('；')}
                </span>
              </div>
            )}
            {variant.free_form_score.suggestions?.length > 0 && (
              <div>
                <Text type="warning" style={{ fontSize: 11, fontWeight: 600 }}>💡 建议：</Text>
                <span style={{ fontSize: 12, color: '#dff7ff' }}>
                  {variant.free_form_score.suggestions.join('；')}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
      {isVariantMode && !variant?.free_form_score && variant?.free_form_error && (
        <div style={{ marginBottom: 12, fontSize: 12, color: '#dc2626' }}>
          转化评分失败：{variant.free_form_error}
        </div>
      )}
      {optimized.optimization_notes && (
        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ fontSize: 13, color: '#10B981' }}>修改说明</Text>
          <div style={{ background: '#F0FDF4', padding: '8px 12px', borderRadius: 8, fontSize: 12, lineHeight: 1.6, whiteSpace: 'pre-wrap', marginTop: 4 }}>
            {optimized.optimization_notes}
          </div>
        </div>
      )}
      {selectedKeywords.length > 0 && (
        <TrafficWordPanel optimized={optimized} selectedKeywords={selectedKeywords} />
      )}

      {diagnosing && (
        <div style={{ textAlign: 'center', padding: '16px 0' }}>
          <Spin size="small" />
          <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>正在诊断...</Text>
        </div>
      )}
      {diagResult && (
        <div style={{ borderTop: '1px dashed rgba(122, 205, 232, 0.22)', paddingTop: 12, marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <Space size={6}>
              <BarChartOutlined style={{ color: '#22d3ee' }} />
              <Text strong style={{ fontSize: 13, color: '#dff7ff' }}>Listing 深度诊断</Text>
              <Tag style={{
                color: '#7acde8', background: 'rgba(34, 211, 238, 0.10)',
                borderColor: 'rgba(34, 211, 238, 0.34)', fontSize: 12,
              }}>
                自我 + 对比
              </Tag>
            </Space>
            <Button type="link" size="small" danger onClick={() => setDiagResult(null)}>关闭</Button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 10 }}>
            <div style={{
              background: 'linear-gradient(135deg, rgba(6, 23, 38, 0.90), rgba(8, 36, 54, 0.74))',
              border: '1px solid rgba(122, 205, 232, 0.22)',
              borderRadius: 10,
              padding: 12,
              boxShadow: '0 0 18px rgba(34, 211, 238, 0.08) inset',
            }}>
              <Text strong style={{ color: '#e6fbff', fontSize: 13 }}>自我诊断</Text>
              <div style={{ marginTop: 8, color: '#dff7ff', fontSize: 12, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                {diagResult.self_diagnosis.summary || '暂无摘要'}
              </div>
              {renderDiagField('优势', diagResult.self_diagnosis.strengths)}
              {renderDiagField('问题', diagResult.self_diagnosis.weaknesses)}
              {renderDiagField('修改建议', diagResult.self_diagnosis.suggestions)}
            </div>

            <div style={{
              background: 'linear-gradient(135deg, rgba(8, 28, 45, 0.92), rgba(11, 41, 58, 0.76))',
              border: '1px solid rgba(62, 166, 226, 0.24)',
              borderRadius: 10,
              padding: 12,
              boxShadow: '0 0 20px rgba(59, 130, 246, 0.08) inset',
            }}>
              <Text strong style={{ color: '#e6fbff', fontSize: 13 }}>对比诊断</Text>
              <div style={{ marginTop: 8, color: '#dff7ff', fontSize: 12, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                {diagResult.comparison_diagnosis.summary || '暂无摘要'}
              </div>
              {renderDiagField('我产品优势', diagResult.comparison_diagnosis.own_advantages)}
              {renderDiagField('我产品劣势', diagResult.comparison_diagnosis.own_disadvantages)}
              {renderDiagField('竞品优势', diagResult.comparison_diagnosis.competitor_advantages)}
              {renderDiagField('竞品劣势', diagResult.comparison_diagnosis.competitor_disadvantages)}
              {renderDiagField('差评差距', diagResult.comparison_diagnosis.negative_review_gap)}
              {renderDiagField('销量对比', diagResult.comparison_diagnosis.sales_comparison)}
              {renderDiagField('产品潜力', diagResult.comparison_diagnosis.product_potential)}
              {renderDiagField('优先调整', diagResult.comparison_diagnosis.suggestions)}
            </div>
          </div>
        </div>
      )}

      {/* ── 领星 ERP 提交 ── */}
      <div style={{
        borderTop: '1px solid #F3F4F6', paddingTop: 12,
        display: 'flex', gap: 8, alignItems: 'center',
      }}>
        <div style={{ flex: 1 }}>
          <Text type="secondary" style={{ fontSize: 10, display: 'block', marginBottom: 2 }}>提交 ASIN</Text>
          <Input
            size="small" value={submitAsin}
            onChange={e => setSubmitAsin(e.target.value)}
            maxLength={10} placeholder="目标 ASIN"
            style={{ borderRadius: 6, fontSize: 12 }}
          />
        </div>
        <Button
          type="primary" size="small"
          icon={<SendOutlined />}
          loading={submitting}
          onClick={handleSubmitToLingxing}
          disabled={submitAsin.trim().length !== 10}
          style={{
            marginTop: 16, borderRadius: 6, fontWeight: 600,
            background: R[4],
          }}
        >
          提交领星
        </Button>
      </div>
      <Modal
        title={<span><CommentOutlined style={{ marginRight: 6, color: '#6366f1' }} />留下评论 / 反馈意见</span>}
        open={commentOpen}
        onCancel={() => setCommentOpen(false)}
        onOk={handleSubmitComment}
        confirmLoading={feedbackSubmitting}
        okText={commentDraft.trim() ? '提交评论' : '清空已有评论'}
        cancelText="取消"
        destroyOnClose
      >
        <Text type="secondary" style={{ fontSize: 12 }}>
          这条评论会写入 llm_memory，用于汇总用户对模型产出的真实反馈。
        </Text>
        <Input.TextArea
          value={commentDraft}
          onChange={e => setCommentDraft(e.target.value)}
          autoSize={{ minRows: 4, maxRows: 10 }}
          maxLength={2000}
          showCount
          placeholder="例如：标题信息密度太低 / 五点没有点出主卖点 / 关键词覆盖不足……"
          style={{ marginTop: 8, borderRadius: 8 }}
        />
      </Modal>
      <Modal
        title={<span><DatabaseOutlined style={{ marginRight: 6, color: ACCENT }} />确认优化入库</span>}
        open={recordOpen}
        onCancel={() => setRecordOpen(false)}
        onOk={handleCreateRecord}
        confirmLoading={recordSubmitting}
        okText="确认入库"
        cancelText="取消"
        destroyOnClose
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message={`ASIN ${asin} / ${marketplace}`}
            description="会记录优化前文案、当前候选文案、图片到 MinIO，并保存 30 天统计时段内的 CTR/CVR/流量快照。"
          />
          <div>
            <Text strong style={{ fontSize: 13 }}>优化原因</Text>
            <Input.TextArea
              value={recordReason}
              onChange={e => setRecordReason(e.target.value)}
              autoSize={{ minRows: 3, maxRows: 6 }}
              maxLength={2000}
              showCount
              style={{ marginTop: 6 }}
            />
          </div>
          <div>
            <Text strong style={{ fontSize: 13 }}>优化方向</Text>
            <Input.TextArea
              value={recordDirection}
              onChange={e => setRecordDirection(e.target.value)}
              autoSize={{ minRows: 3, maxRows: 6 }}
              maxLength={2000}
              showCount
              style={{ marginTop: 6 }}
            />
          </div>
          <div>
            <Text strong style={{ fontSize: 13 }}>备注</Text>
            <Input.TextArea
              value={recordRemark}
              onChange={e => setRecordRemark(e.target.value)}
              autoSize={{ minRows: 2, maxRows: 5 }}
              maxLength={4000}
              showCount
              placeholder="可填写上线批次、负责人说明、观察口径等，后续可在记录页修改"
              style={{ marginTop: 6 }}
            />
          </div>
        </Space>
      </Modal>
    </Card>
  );
}

/* ═══════════════════════════════════════════════
   批量优化面板
   ═══════════════════════════════════════════════ */

interface CompEntry { asin: string; loading: boolean; data: ProductData | null; error: string; }

interface BatchRow {
  id: string;
  asin: string;
  marketplace: string;
  model?: string;
  product: ProductData | null;
  fetchLoading: boolean;
  fetchError: string;
  keywords: string;
  notes: string;
  optimizeSections: string[];
  competitors: CompEntry[];
  enableFab: boolean;
  discoveredTrafficWords: TrafficWordItem[];
  selectedTrafficWords: string[];
  optimizeLoading: boolean;
  analyzeLoading: boolean;
  optimizeResult: ListingOptimizeResponse | null;
  analyzeResult: ListingAnalyzeResponse | null;
  refineVersions: RefineVersion[];
  triDimLoading: boolean;
  triDimResult: SQLExecResponse | null;
  submitLoading: boolean;
  submitted: boolean;
  sessionId: string;
  optimizeTaskId?: string;
  analyzeTaskId?: string;
}

function genId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(8)), b => b.toString(16).padStart(2, '0')).join('');
}

const ALL_SECTIONS = ['title', 'bullet_points', 'description', 'search_terms'] as const;
const SEC_LABELS: Record<string, string> = {
  title: '标题', bullet_points: '五点描述', description: '产品描述', search_terms: '搜索关键词',
};

function newBatchRow(): BatchRow {
  return {
    id: genId(), asin: '', marketplace: 'US', model: undefined,
    product: null, fetchLoading: false, fetchError: '',
    keywords: '', notes: '', optimizeSections: [...ALL_SECTIONS], competitors: [],
    enableFab: true,
    discoveredTrafficWords: [], selectedTrafficWords: [],
    optimizeLoading: false, analyzeLoading: false,
    optimizeResult: null, analyzeResult: null, refineVersions: [],
    triDimLoading: false, triDimResult: null,
    submitLoading: false, submitted: false, sessionId: genId(),
  };
}

const BATCH_CACHE_KEY = 'lsta_batch_rows';

function saveBatchCache(rows: BatchRow[]) {
  try {
    const slim = rows.map(r => ({
      ...r,
      fetchLoading: false, optimizeLoading: false, analyzeLoading: false, submitLoading: false, triDimLoading: false,
      competitors: r.competitors.map(c => ({ ...c, loading: false })),
    }));
    sessionStorage.setItem(BATCH_CACHE_KEY, JSON.stringify(slim));
  } catch { /* quota exceeded — ignore */ }
}

function loadBatchCache(): BatchRow[] | null {
  try {
    const raw = sessionStorage.getItem(BATCH_CACHE_KEY);
    if (!raw) return null;
    const parsed: BatchRow[] = JSON.parse(raw);
    if (!Array.isArray(parsed) || !parsed.length) return null;
    return parsed.map(r => ({
      ...newBatchRow(),
      ...r,
      fetchLoading: false,
      optimizeLoading: !!r.optimizeTaskId,
      analyzeLoading: !!r.analyzeTaskId,
      submitLoading: false,
      triDimLoading: false,
      competitors: (r.competitors || []).map(c => ({ ...c, loading: false })),
    }));
  } catch { return null; }
}

function BatchOptimizePanel() {
  const [rows, setRows] = useState<BatchRow[]>(() => loadBatchCache() || [newBatchRow()]);
  const [detailIdx, setDetailIdx] = useState<number | null>(null);
  const [resultIdx, setResultIdx] = useState<number | null>(null);
  const [batchSettingsOpen, setBatchSettingsOpen] = useState(false);
  const batchPromptCfg = usePromptConfig();
  const [batchEnableFab, setBatchEnableFab] = useState(true);

  const { submitTask: batchTaskSubmit, tasks: bgTasks } = useTaskManager();

  useEffect(() => { saveBatchCache(rows); }, [rows]);

  /* ── 监听后台任务完成，自动更新批量行结果 ── */
  useEffect(() => {
    setRows(prev => {
      let anyChanged = false;
      const next = prev.map(row => {
        let patch: Partial<BatchRow> = {};
        let rowChanged = false;
        if (row.optimizeTaskId) {
          const t = bgTasks.get(row.optimizeTaskId);
          if (t?.status === 'completed' && t.result) {
            patch = {
              ...patch,
              optimizeLoading: false,
              optimizeResult: t.result as ListingOptimizeResponse,
              refineVersions: [{ optimized: (t.result as ListingOptimizeResponse).optimized, feedback: '' }],
              optimizeTaskId: undefined,
            };
            rowChanged = true;
            message.success(`${row.asin} 优化完成`);
          } else if (t?.status === 'failed') {
            patch = { ...patch, optimizeLoading: false, optimizeTaskId: undefined };
            rowChanged = true;
            message.error(`${row.asin} 优化失败: ${t.error || '未知错误'}`);
          }
        }
        if (row.analyzeTaskId) {
          const t = bgTasks.get(row.analyzeTaskId);
          if (t?.status === 'completed' && t.result) {
            patch = {
              ...patch,
              analyzeLoading: false,
              analyzeResult: t.result as ListingAnalyzeResponse,
              analyzeTaskId: undefined,
            };
            rowChanged = true;
            message.success(`${row.asin} 诊断完成`);
          } else if (t?.status === 'failed') {
            patch = { ...patch, analyzeLoading: false, analyzeTaskId: undefined };
            rowChanged = true;
            message.error(`${row.asin} 诊断失败: ${t.error || '未知错误'}`);
          }
        }
        if (rowChanged) { anyChanged = true; return { ...row, ...patch }; }
        return row;
      });
      return anyChanged ? next : prev;
    });
  }, [bgTasks]);

  const update = (id: string, patch: Partial<BatchRow>) =>
    setRows(prev => prev.map(r => r.id === id ? { ...r, ...patch } : r));

  const addRow = () => setRows(prev => [...prev, newBatchRow()]);
  const removeRow = (id: string) => setRows(prev => prev.filter(r => r.id !== id));
  const fileInputRef = useRef<HTMLInputElement>(null);

  const parseRowsFromSheet = (sheetRows: string[][]) => {
    if (sheetRows.length < 2) { message.warning('文件为空或仅有表头'); return; }
    const header = sheetRows[0].map(h => String(h ?? '').trim().toLowerCase());
    const asinIdx = header.findIndex(h => h === 'asin' || h.includes('asin'));
    if (asinIdx === -1) { message.error('未找到 ASIN 列，请确保表头包含 "ASIN"'); return; }
    const mpIdx = header.findIndex(h =>
      h === 'marketplace' || h === '站点' || h === 'site' || h === 'country' || h === '国家'
    );
    const validMps = ['US', 'UK', 'DE', 'JP', 'CA', 'FR', 'IT', 'ES', 'AU', 'MX'];
    const imported: BatchRow[] = [];
    for (let i = 1; i < sheetRows.length; i++) {
      const cols = sheetRows[i].map(c => String(c ?? '').trim());
      const asin = cols[asinIdx];
      if (!asin || asin.length !== 10) continue;
      const mp = mpIdx >= 0 ? (cols[mpIdx]?.toUpperCase() || 'US') : 'US';
      imported.push({ ...newBatchRow(), asin, marketplace: validMps.includes(mp) ? mp : 'US' });
    }
    if (!imported.length) { message.warning('未解析到有效的 ASIN（需 10 位）'); return; }
    setRows(prev => {
      const empty = prev.length === 1 && !prev[0].asin.trim();
      return empty ? imported : [...prev, ...imported];
    });
    message.success(`成功导入 ${imported.length} 个 ASIN`);
  };

  const handleImportExcel = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const ext = file.name.split('.').pop()?.toLowerCase();

    if (ext === 'xlsx' || ext === 'xls') {
      const reader = new FileReader();
      reader.onload = async (ev) => {
        try {
          const XLSX = await import('xlsx');
          const data = new Uint8Array(ev.target?.result as ArrayBuffer);
          const wb = XLSX.read(data, { type: 'array' });
          const ws = wb.Sheets[wb.SheetNames[0]];
          const rows: string[][] = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
          parseRowsFromSheet(rows);
        } catch { message.error('Excel 解析失败，请检查文件格式'); }
      };
      reader.readAsArrayBuffer(file);
    } else {
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const text = (ev.target?.result as string).replace(/^\uFEFF/, '');
          const lines = text.split(/\r?\n/).filter(l => l.trim());
          const rows = lines.map(l => l.split(/[,\t]/).map(c => c.replace(/^"|"$/g, '')));
          parseRowsFromSheet(rows);
        } catch { message.error('文件解析失败，请检查格式'); }
      };
      reader.readAsText(file);
    }
    e.target.value = '';
  };

  const fetchProduct = async (row: BatchRow) => {
    if (row.asin.trim().length !== 10) return;
    update(row.id, { fetchLoading: true, fetchError: '' });
    try {
      const { data } = await listingApi.fetchWithDiagnostics({ asin: row.asin.trim(), marketplace: row.marketplace });
      const autoSelect: string[] = [];
      (data.traffic_words || [])
        .filter((tw: TrafficWordItem) => tw.relevance === 'clear' || (tw.relevance === 'unknown' && tw.aba_search_rank != null && tw.aba_search_rank <= 50000))
        .forEach((tw: TrafficWordItem) => autoSelect.push(tw.word));
      update(row.id, {
        fetchLoading: false, product: data.product, fetchError: '',
        discoveredTrafficWords: data.traffic_words || [],
        selectedTrafficWords: autoSelect,
      });
    } catch (e: any) {
      update(row.id, { fetchLoading: false, fetchError: e.message || '获取失败' });
    }
  };

  const fetchThenOptimize = async (row: BatchRow) => {
    let pd = row.product;
    if (!pd && row.asin.trim().length === 10) {
      update(row.id, { fetchLoading: true, fetchError: '' });
      try {
        const { data } = await listingApi.fetchWithDiagnostics({ asin: row.asin.trim(), marketplace: row.marketplace });
        pd = data.product;
        const autoSelect: string[] = [];
        (data.traffic_words || [])
          .filter((tw: TrafficWordItem) => tw.relevance === 'clear' || (tw.relevance === 'unknown' && tw.aba_search_rank != null && tw.aba_search_rank <= 50000))
          .forEach((tw: TrafficWordItem) => autoSelect.push(tw.word));
        update(row.id, {
          fetchLoading: false, product: data.product,
          discoveredTrafficWords: data.traffic_words || [],
          selectedTrafficWords: autoSelect,
        });
      } catch (e: any) {
        update(row.id, { fetchLoading: false, fetchError: e.message || '获取失败' });
        return;
      }
    }
    update(row.id, { optimizeLoading: true, optimizeResult: null, refineVersions: [] });
    try {
      const kw = row.keywords ? row.keywords.split(/[,，\n]/).map(k => k.trim()).filter(Boolean) : [];
      const compProducts = row.competitors.filter(c => c.data).map(c => c.data!);
      const overrides = batchPromptCfg.activeOverrides();
      const twForApi = row.selectedTrafficWords.length
        ? row.selectedTrafficWords.map(w => {
            const found = row.discoveredTrafficWords.find(tw => tw.word === w);
            return found || { word: w, source: 'manual' as const, relevance: 'unknown' as const };
          })
        : undefined;
      const params: Record<string, any> = {
        asin: pd?.asin || row.asin.trim(), marketplace: pd?.marketplace || row.marketplace,
        model: row.model, product_data: pd?.title ? pd : undefined,
        target_keywords: kw, target_audience: row.notes,
        session_id: row.sessionId, prompt_overrides: overrides,
        optimize_sections: row.optimizeSections.length < 4 ? row.optimizeSections : undefined,
        competitor_products: compProducts.length ? compProducts : undefined,
        enable_fab: row.enableFab,
        traffic_words: twForApi,
      };
      const taskId = await batchTaskSubmit('optimize', params, {
        asin: params.asin, marketplace: params.marketplace,
      });
      update(row.id, { optimizeTaskId: taskId });
    } catch (e: any) {
      update(row.id, { optimizeLoading: false });
      message.error(`${row.asin} 优化提交失败: ${e.message}`);
    }
  };

  const fetchThenAnalyze = async (row: BatchRow) => {
    let pd = row.product;
    if (!pd && row.asin.trim().length === 10) {
      update(row.id, { fetchLoading: true, fetchError: '' });
      try {
        const { data } = await listingApi.fetchWithDiagnostics({ asin: row.asin.trim(), marketplace: row.marketplace });
        pd = data.product;
        update(row.id, { fetchLoading: false, product: data.product });
      } catch (e: any) {
        update(row.id, { fetchLoading: false, fetchError: e.message || '获取失败' });
        return;
      }
    }
    update(row.id, { analyzeLoading: true, analyzeResult: null });
    try {
      const params = {
        asin: pd?.asin || row.asin.trim(), marketplace: pd?.marketplace || row.marketplace,
        model: row.model, product_data: pd?.title ? pd : undefined,
      };
      const taskId = await batchTaskSubmit('analyze', params, {
        asin: params.asin, marketplace: params.marketplace,
      });
      update(row.id, { analyzeTaskId: taskId });
    } catch (e: any) {
      update(row.id, { analyzeLoading: false });
      message.error(`${row.asin} 诊断提交失败: ${e.message}`);
    }
  };

  const batchFetchAll = () => {
    const pending = rows.filter(r => r.asin.trim().length === 10 && !r.product && !r.fetchLoading);
    if (!pending.length) { message.warning('没有需要获取的 ASIN'); return; }
    for (const r of pending) fetchProduct(r);
    message.info(`正在获取 ${pending.length} 个 ASIN 的产品信息...`);
  };

  const submitRow = async (row: BatchRow) => {
    const latest = row.refineVersions.length ? row.refineVersions[row.refineVersions.length - 1].optimized : row.optimizeResult?.optimized;
    if (!latest?.title) { message.warning(`${row.asin} 暂无优化结果`); return; }
    update(row.id, { submitLoading: true });
    try {
      const { data: res } = await listingApi.submitToLingxing({
        asin: row.asin.trim(),
        marketplace: row.marketplace,
        title: latest.title,
        bullet_points: latest.bullet_points,
        description: latest.description,
        search_terms: latest.search_terms,
      });
      if (res.success) {
        update(row.id, { submitLoading: false, submitted: true });
        message.success(`${row.asin} 提交成功`);
      } else {
        update(row.id, { submitLoading: false });
        message.error(res.message || `${row.asin} 提交失败`);
      }
    } catch (e: any) {
      update(row.id, { submitLoading: false });
      message.error(e?.response?.data?.detail || e.message || `${row.asin} 提交失败`);
    }
  };

  const batchSubmitAll = () => {
    const pending = rows.filter(r => (r.refineVersions.length > 0 || r.optimizeResult?.optimized?.title) && !r.submitLoading && !r.submitted);
    if (!pending.length) { message.warning('没有可提交的优化结果'); return; }
    Modal.confirm({
      title: '批量提交到领星',
      content: (
        <div style={{ fontSize: 13, lineHeight: 1.8 }}>
          <p>即将把以下 <strong>{pending.length}</strong> 个 ASIN 的优化结果提交到<strong>领星 ERP</strong>：</p>
          <ul style={{ paddingLeft: 20, maxHeight: 200, overflow: 'auto' }}>
            {pending.map(r => <li key={r.id}>{r.asin}（{r.marketplace}）</li>)}
          </ul>
          <p style={{ color: ACCENT, fontWeight: 500 }}>提交后将直接更新领星中的 Listing 数据，请确认无误。</p>
        </div>
      ),
      okText: '确认提交',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => { for (const r of pending) submitRow(r); },
    });
  };

  const batchOptimizeAll = () => {
    const pending = rows.filter(r => r.asin.trim().length === 10 && !r.optimizeLoading);
    if (!pending.length) { message.warning('没有可优化的 ASIN'); return; }
    for (const r of pending) fetchThenOptimize(r);
  };

  const batchAnalyzeAll = () => {
    const pending = rows.filter(r => r.asin.trim().length === 10 && !r.analyzeLoading);
    if (!pending.length) { message.warning('没有可诊断的 ASIN'); return; }
    for (const r of pending) fetchThenAnalyze(r);
  };

  /* ── 三维数据诊断 ── */
  const [triDimIdx, setTriDimIdx] = useState<number | null>(null);
  const [triDimPage, setTriDimPage] = useState(1);
  const [triDimPageSize, setTriDimPageSize] = useState(50);
  const [triDimTotal, setTriDimTotal] = useState(0);

  const runTriDim = async (row: BatchRow, page = 1, ps = 50) => {
    if (row.asin.trim().length !== 10) return;
    update(row.id, { triDimLoading: true });
    setTriDimPage(page);
    try {
      const asinVal = row.asin.trim();
      const { dataSql, countSql } = await fetchTriDimDiagnosticSql({
        dateRange: 30,
        asin: asinVal,
        page,
        pageSize: ps,
        row_filter: true,
        include_count_sql: page === 1,
      });
      const [dataRes, countRes] = await Promise.all([
        stiApi.execSql(dataSql),
        page === 1 && countSql ? stiApi.execSql(countSql) : Promise.resolve(null),
      ]);
      if (dataRes.data.error) {
        update(row.id, { triDimLoading: false });
        message.error(`${row.asin} 三维诊断失败: ${dataRes.data.error}`);
      } else {
        update(row.id, { triDimLoading: false, triDimResult: dataRes.data });
        if (countRes?.data?.rows?.[0]?.total != null) setTriDimTotal(Number(countRes.data.rows[0].total));
        if (page === 1) message.success(`${row.asin} 三维诊断完成`);
      }
    } catch (e: any) {
      update(row.id, { triDimLoading: false });
      message.error(`${row.asin} 三维诊断失败: ${e.message}`);
    }
  };

  const batchTriDimAll = () => {
    const pending = rows.filter(r => r.asin.trim().length === 10 && !r.triDimLoading);
    if (!pending.length) { message.warning('没有可分析的 ASIN'); return; }
    for (const r of pending) runTriDim(r);
    message.info(`正在对 ${pending.length} 个 ASIN 进行三维诊断...`);
  };

  const detailRow = detailIdx !== null ? rows[detailIdx] : null;
  const resultRow = resultIdx !== null ? rows[resultIdx] : null;
  const triDimRow = triDimIdx !== null ? rows[triDimIdx] : null;

  return (
    <Card
      title={
        <Space>
          <ShoppingOutlined style={{ color: ACCENT }} />
          <span>批量优化</span>
          <Tag color="blue">{rows.length} 个 ASIN</Tag>
          <Tooltip title="提示词设置">
            <Button type="text" size="small" icon={<SettingOutlined />}
              onClick={() => setBatchSettingsOpen(true)}
              style={{ color: batchPromptCfg.activeOverrides() ? ACCENT : '#6B7280' }} />
          </Tooltip>
        </Space>
      }
      extra={
        <Space wrap>
          <Button icon={<PlusOutlined />} onClick={addRow}>添加行</Button>
          <Button type="primary" icon={<UploadOutlined />}
            onClick={() => fileInputRef.current?.click()}
            style={{ background: R[3] }}>
            导入 Excel
          </Button>
          <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.xls,.tsv,.txt"
            style={{ display: 'none' }} onChange={handleImportExcel} />
          <Button type="primary" icon={<SearchOutlined />} onClick={batchFetchAll}
            style={{ background: R[0] }}>
            全部获取
          </Button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Text style={{ fontSize: 12, color: batchEnableFab ? '#15803d' : '#666' }}>FAB</Text>
            <Switch size="small" checked={batchEnableFab} onChange={setBatchEnableFab}
              style={batchEnableFab ? { background: '#16a34a' } : {}} />
          </div>
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={batchOptimizeAll}
            style={{ background: R[1] }}>
            全部优化
          </Button>
          <Button type="primary" icon={<BarChartOutlined />} onClick={batchAnalyzeAll}
            style={{ background: R[2] }}>
            全部诊断
          </Button>
          <Button type="primary" icon={<BarChartOutlined />} onClick={batchTriDimAll}
            style={{ background: R[3] }}>
            全部三维
          </Button>
          <Button type="primary" icon={<SendOutlined />} onClick={batchSubmitAll}
            style={{ background: R[4] }}>
            批量提交
          </Button>
        </Space>
      }
      style={{ borderRadius: 14, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}
    >
      {/* 表头 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '2fr 1fr 1.6fr 0.7fr 0.5fr 0.7fr 0.7fr 0.7fr 0.7fr 0.7fr 0.4fr',
        gap: 8, padding: '10px 4px', borderBottom: '2px solid #E5E7EB',
        fontWeight: 600, fontSize: 12, color: '#6B7280', textAlign: 'center',
      }}>
        <div style={{ textAlign: 'left' }}>ASIN</div>
        <div>站点</div>
        <div>模型</div>
        <div>获取</div>
        <div>参数</div>
        <div>优化</div>
        <div>诊断</div>
        <div>三维</div>
        <div>提交</div>
        <div>结果</div>
        <div></div>
      </div>

      {/* 数据行 */}
      {rows.map((row, idx) => (
        <div key={row.id} style={{
          display: 'grid',
          gridTemplateColumns: '2fr 1fr 1.6fr 0.7fr 0.5fr 0.7fr 0.7fr 0.7fr 0.7fr 0.7fr 0.4fr',
          gap: 8, padding: '8px 4px', borderBottom: '1px solid #F3F4F6',
          alignItems: 'center',
        }}>
          {/* ASIN */}
          <div>
            <Input
              size="small" placeholder="10 位 ASIN" maxLength={10}
              value={row.asin}
              onChange={e => update(row.id, { asin: e.target.value })}
              onPressEnter={() => fetchProduct(row)}
              status={row.fetchError ? 'error' : row.product ? undefined : undefined}
              suffix={
                row.fetchLoading ? <Spin size="small" /> :
                row.product ? <CheckOutlined style={{ color: '#10B981', fontSize: 11 }} /> : null
              }
              style={{ borderRadius: 6, fontSize: 12 }}
            />
            {row.fetchError && <Text type="danger" style={{ fontSize: 9 }}>{row.fetchError}</Text>}
          </div>

          {/* 站点 */}
          <Select
            size="small" value={row.marketplace}
            onChange={v => update(row.id, { marketplace: v })}
            options={MARKETPLACES} style={{ width: '100%' }}
          />

          {/* 模型 */}
          <ModelSelector
            size="small" value={row.model}
            onChange={v => update(row.id, { model: v })}
            style={{ width: '100%' }}
          />

          {/* 获取 */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Button
              size="small" type="primary" block
              icon={<SearchOutlined />}
              loading={row.fetchLoading}
              disabled={row.asin.trim().length !== 10}
              onClick={() => fetchProduct(row)}
              style={{
                borderRadius: 6, fontSize: 11, letterSpacing: 2,
                background: row.product ? RD[0] : R[0],
              }}
            >
              {row.product ? '已获取' : '获 取'}
            </Button>
          </div>

          {/* 参数设置 */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Button
              size="small" type="primary" block
              icon={<SettingOutlined />}
              onClick={() => setDetailIdx(idx)}
              style={{
                borderRadius: 6, fontSize: 11, letterSpacing: 2,
                background: (row.keywords || row.notes || row.competitors.length) ? RD[4] : R[4],
              }}
            >
              参 数
            </Button>
          </div>

          {/* 优化 */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Button
              size="small" type="primary" block
              icon={<ThunderboltOutlined />}
              loading={row.optimizeLoading || (row.fetchLoading && !row.analyzeLoading)}
              disabled={row.asin.trim().length !== 10}
              onClick={() => fetchThenOptimize(row)}
              style={{
                borderRadius: 6, fontSize: 11, letterSpacing: 2,
                background: row.optimizeResult ? RD[1] : R[1],
              }}
            >
              {row.optimizeResult ? '已完成' : '优 化'}
            </Button>
          </div>

          {/* 诊断 */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Button
              size="small" type="primary" block
              icon={<BarChartOutlined />}
              loading={row.analyzeLoading || (row.fetchLoading && !row.optimizeLoading)}
              disabled={row.asin.trim().length !== 10}
              onClick={() => fetchThenAnalyze(row)}
              style={{
                borderRadius: 6, fontSize: 11, letterSpacing: 2,
                background: row.analyzeResult ? RD[2] : R[2],
              }}
            >
              {row.analyzeResult ? '已完成' : '诊 断'}
            </Button>
          </div>

          {/* 三维数据诊断 */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Button
              size="small" type="primary" block
              icon={<BarChartOutlined />}
              loading={row.triDimLoading}
              disabled={row.asin.trim().length !== 10}
              onClick={() => {
                if (row.triDimResult) { setTriDimIdx(idx); }
                else { runTriDim(row); }
              }}
              style={{
                borderRadius: 6, fontSize: 11, letterSpacing: 2,
                background: row.triDimResult ? RD[3] : R[3],
              }}
            >
              {row.triDimResult ? '查 看' : '三 维'}
            </Button>
          </div>

          {/* 提交领星 */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Button
              size="small" type="primary" block
              icon={<SendOutlined />}
              loading={row.submitLoading}
              disabled={(!row.refineVersions.length && !row.optimizeResult?.optimized?.title) || row.submitted}
              onClick={() => {
                if (row.submitted) return;
                Modal.confirm({
                  title: '确认提交到领星',
                  content: `将 ${row.asin}（${row.marketplace}）的优化结果提交到领星 ERP，确认？`,
                  okText: '确认', cancelText: '取消',
                  okButtonProps: { danger: true },
                  onOk: () => submitRow(row),
                });
              }}
              style={{
                borderRadius: 6, fontSize: 11, letterSpacing: 2,
                background: row.submitted ? '#D1D5DB' : R[4],
              }}
            >
              {row.submitted ? '已提交' : '提 交'}
            </Button>
          </div>

          {/* 结果查看 */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Button
              size="small" type="primary" block
              icon={<SearchOutlined />}
              disabled={!row.refineVersions.length && !row.analyzeResult}
              onClick={() => setResultIdx(idx)}
              style={{
                borderRadius: 6, fontSize: 11, letterSpacing: 2,
                background: (row.refineVersions.length || row.analyzeResult) ? R[0] : undefined,
              }}
            >
              {(row.refineVersions.length || row.analyzeResult) ? '查 看' : '-'}
            </Button>
          </div>

          {/* 删除 */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <Button size="small" type="text" danger icon={<DeleteOutlined />}
              disabled={rows.length <= 1}
              onClick={() => removeRow(row.id)}
            />
          </div>
        </div>
      ))}

      {rows.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: '#9CA3AF' }}>
          <Text type="secondary">点击"添加行"开始批量优化</Text>
        </div>
      )}

      {/* ── 参数详情 Drawer ── */}
      <Drawer
        title={detailRow ? `优化参数 - ${detailRow.asin || '未输入'}` : '优化参数'}
        open={detailIdx !== null}
        onClose={() => setDetailIdx(null)}
        width={600}
        destroyOnClose
      >
        {detailRow && (
          <BatchParamEditor
            row={detailRow}
            onUpdate={(patch) => { update(detailRow.id, patch); }}
            onClose={() => setDetailIdx(null)}
          />
        )}
      </Drawer>

      {/* ── 结果查看 Drawer ── */}
      <Drawer
        title={resultRow ? `结果对比 - ${resultRow.asin}（${resultRow.marketplace}）` : '结果'}
        open={resultIdx !== null}
        onClose={() => setResultIdx(null)}
        width={Math.min(window.innerWidth * 0.9, 1400)}
        destroyOnClose
      >
        {resultRow && (resultRow.refineVersions.length > 0 || resultRow.analyzeResult) ? (
          <div>
            {resultRow.refineVersions.length > 0 && (
              <div style={{ display: 'flex', gap: 16, overflowX: 'auto', padding: '8px 0 16px', alignItems: 'flex-start' }}>
                {/* 原始数据对比栏 */}
                {resultRow.product && (
                  <OriginalDataCard product={resultRow.product} />
                )}
                {resultRow.refineVersions.map((v, i) => (
                  <VersionCard key={i} version={v} index={i}
                    asin={resultRow.optimizeResult?.asin || resultRow.asin}
                    marketplace={resultRow.optimizeResult?.marketplace || resultRow.marketplace}
                    selectedKeywords={resultRow.selectedTrafficWords}
                    trafficWords={resultRow.discoveredTrafficWords}
                    searchLibWords={[]}
                    productContext={resultRow.product || resultRow.optimizeResult?.original || null}
                    competitorProducts={resultRow.competitors.filter(c => c.data).map(c => c.data!)} />
                ))}
                {resultRow.refineVersions.length > 0 && resultRow.refineVersions.length <= MAX_REFINE && (
                  <BatchRefinePanel
                    row={resultRow}
                    onNewVersion={(v) => {
                      update(resultRow.id, { refineVersions: [...resultRow.refineVersions, v] });
                    }}
                  />
                )}
              </div>
            )}
            {resultRow.analyzeResult && (
              <div style={{ marginTop: resultRow.refineVersions.length > 0 ? 16 : 0 }}>
                <AnalyzeResultCard data={resultRow.analyzeResult} />
              </div>
            )}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 40, color: '#9CA3AF' }}>暂无结果</div>
        )}
      </Drawer>

      {/* ── 三维数据诊断 Drawer ── */}
      <Drawer
        title={
          <Space>
            <BarChartOutlined style={{ color: RAINBOW[3].from }} />
            <span>三维数据诊断 - {triDimRow?.asin || 'N/A'}（{triDimRow?.marketplace || ''}）</span>
            {triDimTotal > 0 && <Tag color="red">{triDimTotal} 条记录</Tag>}
          </Space>
        }
        open={triDimIdx !== null}
        onClose={() => setTriDimIdx(null)}
        width={Math.min(window.innerWidth * 0.85, 1200)}
        destroyOnClose
      >
        {triDimRow?.triDimLoading && (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" />
            <div style={{ marginTop: 16 }}><Text type="secondary">正在查询数据库，分析 CTR/CVR/流量趋势...</Text></div>
          </div>
        )}
        {triDimRow?.triDimResult && (
          <div>
            {triDimRow.triDimResult.row_count === 0 && triDimTotal === 0 ? (
              <Alert message="该 ASIN 未命中任何诊断维度" description="产品各项指标均在正常范围内，无需特别优化。" type="success" showIcon />
            ) : (
              <TriDimTable
                data={triDimRow.triDimResult}
                loading={triDimRow.triDimLoading}
                total={triDimTotal}
                current={triDimPage}
                pageSize={triDimPageSize}
                onPageChange={(page, ps) => {
                  setTriDimPageSize(ps);
                  runTriDim(triDimRow, page, ps);
                }}
              />
            )}
          </div>
        )}
        {!triDimRow?.triDimResult && !triDimRow?.triDimLoading && (
          <div style={{ textAlign: 'center', padding: 60, color: '#9CA3AF' }}>
            <BarChartOutlined style={{ fontSize: 48, marginBottom: 16 }} />
            <div>暂无三维诊断数据</div>
            <Button type="primary" style={{ marginTop: 16, background: R[3] }}
              onClick={() => { if (triDimRow) runTriDim(triDimRow); }}>
              开始诊断
            </Button>
          </div>
        )}
      </Drawer>

      {/* ── 提示词设置 Drawer ── */}
      <PromptSettingsDrawer open={batchSettingsOpen} onClose={() => setBatchSettingsOpen(false)} promptCfg={batchPromptCfg} />
    </Card>
  );
}

/* ── 三维诊断表格（可分页）── */

function TriDimTable({ data, loading, total, current, pageSize, onPageChange }: {
  data: SQLExecResponse;
  loading: boolean;
  total: number;
  current: number;
  pageSize: number;
  onPageChange: (page: number, pageSize: number) => void;
}) {
  const triDimCols = [
    { title: 'ASIN', dataIndex: 'asin', key: 'asin', width: 120, fixed: 'left' as const },
    { title: 'MSKU', dataIndex: 'msku', key: 'msku', width: 130, ellipsis: true },
    { title: '店铺', dataIndex: 'store_name', key: 'store', width: 110, ellipsis: true },
    { title: '国家', dataIndex: 'country_code', key: 'cc', width: 55 },
    { title: '类目', dataIndex: 'category_2', key: 'cat', width: 120, ellipsis: true },
    {
      title: 'CTR%', dataIndex: 'product_ctr_pct', key: 'ctr', width: 80,
      render: (v: number, r: any) => (
        <span style={{ color: r.flag_ctr_low ? '#EF4444' : '#10B981', fontWeight: 600 }}>
          {v}%
        </span>
      ),
    },
    { title: '类目CTR%', dataIndex: 'cat_avg_ctr_pct', key: 'cat_ctr', width: 85, render: (v: number) => `${v}%` },
    {
      title: 'CVR%', dataIndex: 'product_cvr_pct', key: 'cvr', width: 80,
      render: (v: number, r: any) => (
        <span style={{ color: r.flag_cvr_low ? '#EF4444' : '#10B981', fontWeight: 600 }}>
          {v}%
        </span>
      ),
    },
    { title: '类目CVR%', dataIndex: 'cat_avg_cvr_pct', key: 'cat_cvr', width: 85, render: (v: number) => `${v}%` },
    {
      title: '流量变化%', dataIndex: 'sessions_change_pct', key: 'sess', width: 95,
      render: (v: number | null, r: any) => v != null ? (
        <span style={{ color: r.flag_sessions_decline ? '#EF4444' : v < 0 ? '#F59E0B' : '#10B981', fontWeight: 600 }}>
          {v > 0 ? '+' : ''}{v}%
        </span>
      ) : 'N/A',
    },
    { title: '库存', dataIndex: 'avg_stock_qty', key: 'stock', width: 65 },
    {
      title: '命中', dataIndex: 'hit_count', key: 'hit', width: 55,
      render: (v: number) => (
        <Tag color={v >= 3 ? 'red' : v >= 2 ? 'orange' : 'blue'} style={{ fontWeight: 700 }}>{v}维</Tag>
      ),
    },
    {
      title: '优化建议', dataIndex: 'optimization_actions', key: 'actions', width: 220,
      render: (v: string) => v ? (
        <Space wrap size={2}>
          {v.split(' | ').filter(Boolean).map((a, i) => (
            <Tag key={i} color={a.includes('必须') ? 'red' : a.includes('标题') ? 'orange' : 'blue'} style={{ fontSize: 11 }}>{a}</Tag>
          ))}
        </Space>
      ) : <Tag color="green">正常</Tag>,
    },
    { title: '运营', dataIndex: 'salesman', key: 'sales', width: 80, ellipsis: true },
    { title: '产品经理', dataIndex: 'product_manager', key: 'pm', width: 80, ellipsis: true },
  ];

  return (
    <Table
      dataSource={data.rows.map((r, i) => ({ ...r, _key: `${current}_${i}` }))}
      columns={triDimCols}
      rowKey="_key"
      size="small"
      scroll={{ x: 1600 }}
      loading={loading}
      pagination={{
        current,
        pageSize,
        total,
        showSizeChanger: true,
        pageSizeOptions: ['20', '50', '100'],
        showTotal: (t, range) => `第 ${range[0]}-${range[1]} 条 / 共 ${t} 条`,
        showQuickJumper: true,
        onChange: onPageChange,
      }}
      rowClassName={(r: any) => r.hit_count >= 3 ? 'diagnostic-critical' : ''}
    />
  );
}

/* ── 原始数据对比卡（在结果 Drawer 最左侧展示） ── */

function OriginalDataCard({ product }: { product: ProductData }) {
  return (
    <Card size="small"
      style={{
        minWidth: 420, maxWidth: 500, borderRadius: 12, flexShrink: 0,
        border: '2px solid #E5E7EB', background: '#FAFAFA',
      }}
      title={
        <Space size={4}>
          <ShoppingOutlined style={{ color: '#6B7280' }} />
          <Tag color="default" style={{ fontSize: 12 }}>原始 Listing</Tag>
          {product.brand && <Text type="secondary" style={{ fontSize: 11 }}>{product.brand}</Text>}
        </Space>
      }
      styles={{ body: { padding: '12px 16px', maxHeight: 650, overflow: 'auto' } }}
    >
      {/* 基本信息 */}
      <div style={{
        display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12,
        padding: '6px 10px', background: '#F3F4F6', borderRadius: 8,
      }}>
        {product.price && <Tag style={{ fontSize: 11 }}>{product.price} {product.currency || 'USD'}</Tag>}
        {product.rating && <Tag style={{ fontSize: 11 }}>★ {product.rating}{product.review_count ? ` (${product.review_count})` : ''}</Tag>}
        {product.category && <Tag style={{ fontSize: 11 }}>{product.category}</Tag>}
        {product.bsr_rank && <Tag style={{ fontSize: 11 }}>BSR #{product.bsr_rank}</Tag>}
      </div>

      {/* 标题 */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong style={{ fontSize: 13, color: '#6B7280' }}><TagOutlined /> 标题</Text>
          <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copyText(product.title)} />
        </div>
        <div style={{ background: '#fff', padding: '8px 12px', borderRadius: 8, fontSize: 13, marginTop: 4, border: '1px solid #E5E7EB' }}>
          {product.title || <Text type="secondary" style={{ fontSize: 12 }}>无标题</Text>}
        </div>
      </div>

      {/* 五点描述 */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong style={{ fontSize: 13, color: '#6B7280' }}>五点描述</Text>
          <Button type="link" size="small" icon={<CopyOutlined />}
            onClick={() => copyText(product.bullet_points.join('\n'))} />
        </div>
        {product.bullet_points.length > 0 ? product.bullet_points.map((bp, i) => (
          <div key={i} style={{
            background: '#fff', padding: '6px 12px', borderRadius: 8, fontSize: 12,
            marginTop: 4, borderLeft: '3px solid #9CA3AF', lineHeight: 1.5,
          }}>
            <Tag color="default" style={{ fontSize: 10, padding: '0 4px' }}>第{i + 1}条</Tag>
            {bp}
          </div>
        )) : <Text type="secondary" style={{ fontSize: 12 }}>无五点描述</Text>}
      </div>

      {/* 产品描述 */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong style={{ fontSize: 13, color: '#6B7280' }}>产品描述</Text>
          <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copyText(product.description)} />
        </div>
        {product.description ? (
          <div style={{
            background: '#fff', padding: '8px 12px', borderRadius: 8,
            fontSize: 12, lineHeight: 1.6, whiteSpace: 'pre-wrap', marginTop: 4,
            maxHeight: 200, overflow: 'auto', border: '1px solid #E5E7EB',
          }}>
            {product.description}
          </div>
        ) : <Text type="secondary" style={{ fontSize: 12 }}>无产品描述</Text>}
      </div>

      {/* 用户评论 */}
      {product.reviews && product.reviews.length > 0 && (
        <div>
          <Collapse size="small" style={{ marginTop: 4 }} items={[{
            key: 'reviews',
            label: <Text strong style={{ fontSize: 13, color: '#6B7280' }}>用户评论 ({product.reviews.length} 条)</Text>,
            children: (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {product.reviews.map((rv, i) => (
                  <div key={i} style={{
                    padding: '8px 10px', background: '#fff', borderRadius: 8,
                    border: '1px solid #F0F0F0',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontSize: 12, color: '#FAAD14' }}>
                        {'★'.repeat(Math.round(rv.stars))}{'☆'.repeat(5 - Math.round(rv.stars))}
                        <span style={{ marginLeft: 4, color: '#8C8C8C', fontSize: 11 }}>{rv.stars}</span>
                      </span>
                      {rv.date && <Text type="secondary" style={{ fontSize: 10 }}>{rv.date}</Text>}
                    </div>
                    {rv.title && <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{rv.title}</div>}
                    {rv.body && <div style={{ fontSize: 11, color: '#595959', lineHeight: 1.6 }}>{rv.body}</div>}
                  </div>
                ))}
              </div>
            ),
          }]} />
        </div>
      )}
    </Card>
  );
}

/* ── 批量参数编辑子组件（对应截图：竞品ASIN、关键词、修改意见、模型选择、优化范围 + 产品信息查看） ── */

function BatchParamEditor({ row, onUpdate, onClose }: {
  row: BatchRow;
  onUpdate: (patch: Partial<BatchRow>) => void;
  onClose: () => void;
}) {
  const [keywords, setKeywords] = useState(row.keywords);
  const [notes, setNotes] = useState(row.notes);
  const [sections, setSections] = useState<string[]>([...row.optimizeSections]);
  const [comps, setComps] = useState<CompEntry[]>([...row.competitors]);
  const [fab, setFab] = useState(row.enableFab);
  const [selWords, setSelWords] = useState<string[]>([...row.selectedTrafficWords]);

  const addComp = () => setComps(prev => [...prev, { asin: '', loading: false, data: null, error: '' }]);
  const removeComp = (idx: number) => setComps(prev => prev.filter((_, i) => i !== idx));
  const updateCompAsin = (idx: number, val: string) =>
    setComps(prev => prev.map((c, i) => i === idx ? { ...c, asin: val, error: '' } : c));

  const fetchComp = async (idx: number) => {
    const entry = comps[idx];
    if (!entry || entry.asin.trim().length !== 10) return;
    setComps(prev => prev.map((c, i) => i === idx ? { ...c, loading: true, error: '' } : c));
    try {
      const { data } = await listingApi.fetch({ asin: entry.asin.trim(), marketplace: row.marketplace });
      setComps(prev => prev.map((c, i) => i === idx ? { ...c, loading: false, data, error: '' } : c));
    } catch (e: any) {
      setComps(prev => prev.map((c, i) => i === idx ? { ...c, loading: false, error: e.message || '获取失败' } : c));
    }
  };

  const handleSave = () => {
    onUpdate({
      keywords, notes, optimizeSections: sections, competitors: comps,
      enableFab: fab, selectedTrafficWords: selWords,
    });
    message.success('参数已保存');
    onClose();
  };

  return (
    <div className="listing-optimize-page">
      {/* 竞品 ASIN */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <Text strong style={{ fontSize: 13 }}>竞品 ASIN</Text>
          <Button type="link" size="small" icon={<PlusOutlined />} disabled={comps.length >= 5}
            onClick={addComp} style={{ fontSize: 12, padding: 0 }}>添加竞品</Button>
        </div>
        {comps.map((comp, ci) => (
          <div key={ci} style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <Input size="small" placeholder="竞品 ASIN（10位）" maxLength={10}
                value={comp.asin} onChange={e => updateCompAsin(ci, e.target.value)}
                onPressEnter={() => fetchComp(ci)}
                status={comp.error ? 'error' : undefined}
                style={{ flex: 1, borderRadius: 6, fontSize: 12 }} />
              <Button size="small" type="primary" icon={<SearchOutlined />}
                loading={comp.loading} disabled={comp.asin.trim().length !== 10}
                onClick={() => fetchComp(ci)}
                style={{
                  borderRadius: 6, flexShrink: 0,
                  background: comp.data ? RD[0] : R[0],
                }} />
              <Button size="small" type="text" danger icon={<DeleteOutlined />}
                onClick={() => removeComp(ci)} style={{ flexShrink: 0 }} />
            </div>
            {comp.error && <Text type="danger" style={{ fontSize: 10 }}>{comp.error}</Text>}
            {comp.data && (
              <div style={{
                marginTop: 4, padding: '4px 8px', borderRadius: 6,
                background: '#F0FDF4', border: '1px solid #D1FAE5', fontSize: 11, lineHeight: 1.5,
              }}>
                <Text ellipsis style={{ fontSize: 11, fontWeight: 500, display: 'block' }}>{comp.data.title}</Text>
                <Text type="secondary" style={{ fontSize: 10 }}>
                  {comp.data.brand || '未知品牌'} · {comp.data.price || 'N/A'} {comp.data.currency} · ★{comp.data.rating || 'N/A'}
                </Text>
              </div>
            )}
          </div>
        ))}
        {comps.length === 0 && <Text type="secondary" style={{ fontSize: 11 }}>暂无竞品，点击"添加竞品"开始</Text>}
      </div>

      {/* 流量词 */}
      <TrafficWordSelector
        trafficWords={row.discoveredTrafficWords}
        selectedWords={selWords}
        onSelectedChange={setSelWords}
      />

      {/* 重点关键词 */}
      <div style={{ marginBottom: 20 }}>
        <Text strong style={{ fontSize: 13 }}>重点关键词</Text>
        <Input.TextArea value={keywords} onChange={e => setKeywords(e.target.value)}
          placeholder="多个关键词用逗号分隔"
          autoSize={{ minRows: 2, maxRows: 4 }} style={{ marginTop: 4, borderRadius: 8 }} />
      </div>

      {/* 修改意见 */}
      <div style={{ marginBottom: 20 }}>
        <Text strong style={{ fontSize: 13 }}>修改意见</Text>
        <Input.TextArea value={notes} onChange={e => setNotes(e.target.value)}
          placeholder="对优化结果的补充说明或特殊要求"
          autoSize={{ minRows: 2, maxRows: 4 }} style={{ marginTop: 4, borderRadius: 8 }} />
      </div>

      {/* 模型选择 */}
      <div style={{ marginBottom: 20 }}>
        <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 4 }}>模型选择</Text>
        <ModelSelector value={row.model} onChange={v => onUpdate({ model: v })} style={{ width: '100%' }} />
      </div>

      {/* FAB 增强模式 */}
      <div style={{
        marginBottom: 20,
        background: fab ? '#f0fdf4' : '#f9fafb',
        border: `1px solid ${fab ? '#86efac' : '#e5e7eb'}`,
        borderRadius: 10, padding: '10px 14px', transition: 'all 0.2s',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <Text style={{ fontSize: 13, fontWeight: 600, color: fab ? '#15803d' : '#374151' }}>
              FAB 增强模式
            </Text>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 2 }}>
              {fab
                ? 'COSMO 四维 + FAB 文案 + 评论洞察 '
                : '标准 SEO 优化（不含 FAB 结构和评论洞察注入）'}
            </Text>
          </div>
          <Switch checked={fab} onChange={setFab}
            style={fab ? { background: '#16a34a' } : {}} />
        </div>
      </div>

      {/* 优化范围 */}
      <div style={{ marginBottom: 20 }}>
        <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>优化范围</Text>
        <Checkbox.Group value={sections} onChange={vals => setSections(vals as string[])}
          style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 0' }}>
          {ALL_SECTIONS.map(k => (
            <Checkbox key={k} value={k} style={{ marginRight: 12, fontSize: 13 }}>{SEC_LABELS[k]}</Checkbox>
          ))}
        </Checkbox.Group>
      </div>

      {/* 产品信息折叠 */}
      {row.product && (
        <Collapse size="small" style={{ marginBottom: 20 }} items={[{
          key: 'product',
          label: <Space><ShoppingOutlined /><span>已获取的产品信息</span><Tag color="green" style={{ fontSize: 10 }}>可查看</Tag></Space>,
          children: (
            <div style={{ fontSize: 12, lineHeight: 1.8 }}>
              <div><Text strong>标题：</Text>{row.product.title}</div>
              <div><Text strong>品牌：</Text>{row.product.brand} | <Text strong>价格：</Text>{row.product.price} {row.product.currency} | <Text strong>评分：</Text>{row.product.rating}</div>
              <div><Text strong>类目：</Text>{row.product.category} | <Text strong>BSR：</Text>{row.product.bsr_rank}</div>
              {row.product.bullet_points.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  <Text strong>五点描述：</Text>
                  {row.product.bullet_points.map((bp, i) => (
                    <div key={i} style={{
                      background: LIGHT_BG, padding: '4px 8px', borderRadius: 6,
                      marginTop: 2, borderLeft: `2px solid ${ACCENT}`, fontSize: 11,
                    }}>
                      <Tag color="orange" style={{ fontSize: 9, padding: '0 3px' }}>{i + 1}</Tag> {bp}
                    </div>
                  ))}
                </div>
              )}
              {row.product.description && (
                <div style={{ marginTop: 4 }}>
                  <Text strong>描述：</Text>
                  <div style={{ background: LIGHT_BG, padding: '4px 8px', borderRadius: 6, whiteSpace: 'pre-wrap', maxHeight: 120, overflow: 'auto' }}>
                    {row.product.description}
                  </div>
                </div>
              )}
            </div>
          ),
        }]} />
      )}

      <Button type="primary" block size="large" icon={<CheckOutlined />}
        onClick={handleSave}
        style={{ borderRadius: 10, fontWeight: 600, background: R[2] }}
      >
        保存参数
      </Button>
    </div>
  );
}

/* ── 批量结果面板中的迭代修改组件 ── */

function BatchRefinePanel({ row, onNewVersion }: {
  row: BatchRow;
  onNewVersion: (v: RefineVersion) => void;
}) {
  const [feedback, setFeedback] = useState('');
  const [loading, setLoading] = useState(false);
  const [showInput, setShowInput] = useState(false);

  const lastVersion = row.refineVersions[row.refineVersions.length - 1].optimized;
  const canRefine = row.refineVersions.length <= MAX_REFINE;

  const handleRefine = async () => {
    if (!feedback.trim()) { message.warning('请输入修改意见'); return; }
    setLoading(true);
    try {
      const { data } = await listingApi.refine({
        asin: row.optimizeResult?.asin || row.asin,
        marketplace: row.optimizeResult?.marketplace || row.marketplace,
        current_title: lastVersion.title,
        current_bullet_points: lastVersion.bullet_points,
        current_description: lastVersion.description,
        current_search_terms: lastVersion.search_terms,
        user_feedback: feedback.trim(),
        session_id: row.sessionId, model: row.model,
      });
      onNewVersion({ optimized: data.optimized, feedback: feedback.trim() });
      setFeedback(''); setShowInput(false);
    } catch (e: any) { message.error(e.message || '迭代修改失败'); }
    finally { setLoading(false); }
  };

  if (!canRefine) return null;

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', minWidth: showInput ? 320 : 60, padding: '0 8px',
    }}>
      {!showInput ? (
        <div onClick={() => setShowInput(true)}
          style={{
            width: 48, height: 48, borderRadius: '50%', cursor: 'pointer',
            background: R[1],
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: 24, fontWeight: 700,
            boxShadow: `0 4px 12px ${ACCENT}66`, transition: 'all 0.3s',
          }}
          title={`追加修改（还剩 ${MAX_REFINE - row.refineVersions.length + 1} 次）`}
          onMouseEnter={e => { (e.target as HTMLDivElement).style.transform = 'scale(1.15)'; }}
          onMouseLeave={e => { (e.target as HTMLDivElement).style.transform = 'scale(1)'; }}
        >+</div>
      ) : (
        <Card size="small" style={{ borderRadius: 12, width: '100%', border: `2px dashed ${ACCENT}` }}
          styles={{ body: { padding: 12 } }}>
          <div style={{ marginBottom: 8 }}>
            <Text strong style={{ color: ACCENT, fontSize: 13 }}>修改意见（第 {row.refineVersions.length} 次迭代）</Text>
            <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>剩余 {MAX_REFINE - row.refineVersions.length + 1} 次</Text>
          </div>
          <Input.TextArea value={feedback} onChange={e => setFeedback(e.target.value)}
            placeholder="例如：标题太长了，缩短到150字符以内..."
            autoSize={{ minRows: 3, maxRows: 6 }} style={{ marginBottom: 8, borderRadius: 8 }} autoFocus />
          <Space>
            <Button type="primary" size="small" loading={loading} onClick={handleRefine}
              style={{ background: R[1] }}>生成修改版</Button>
            <Button size="small" onClick={() => { setShowInput(false); setFeedback(''); }}>取消</Button>
          </Space>
        </Card>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════
   主组件
   ═══════════════════════════════════════════════ */

const EMPTY_PRODUCT: ProductData = {
  asin: '', marketplace: '', title: '', brand: '', price: '', currency: '',
  rating: '', review_count: '', bullet_points: [], description: '',
  category: '', bsr_rank: '', images: [], reviews: [],
};

export default function ListingOptimize() {
  const [searchParams] = useSearchParams();
  const tabFromUrl = searchParams.get('tab') as 'optimize' | 'analyze' | 'batch' | null;
  const [activeTab, setActiveTabRaw] = useState<'optimize' | 'analyze' | 'batch'>(
    tabFromUrl && ['optimize', 'analyze', 'batch'].includes(tabFromUrl) ? tabFromUrl : 'optimize'
  );

  useEffect(() => {
    if (tabFromUrl && ['optimize', 'analyze', 'batch'].includes(tabFromUrl) && tabFromUrl !== activeTab) {
      setActiveTabRaw(tabFromUrl);
    }
  }, [tabFromUrl]);

  const { submitTask, tasks } = useTaskManager();
  const [currentOptTaskId, setCurrentOptTaskId] = useState<string | null>(
    () => sessionStorage.getItem('lsta_opt_task_id') || null,
  );
  const [currentAnaTaskId, setCurrentAnaTaskId] = useState<string | null>(null);

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const promptCfg = usePromptConfig();
  const [selectedModel, setSelectedModel] = useState<string | undefined>(
    () => sessionStorage.getItem('lsta_model') || undefined,
  );
  // 候选评价模型（多候选评分阶段专用）；未选则回退到优化模型
  const [selectedEvalModel, setSelectedEvalModel] = useState<string | undefined>(
    () => sessionStorage.getItem('lsta_eval_model') || undefined,
  );
  const [sessionId] = useState(() => {
    const cached = sessionStorage.getItem('lsta_session_id');
    if (cached) return cached;
    const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
    sessionStorage.setItem('lsta_session_id', id);
    return id;
  });

  /* ── 表单（诊断模式下从缓存恢复 ASIN/站点/产品信息） ── */
  const [asin, setAsin] = useState(() => {
    try {
      const f = sessionStorage.getItem(CACHE_KEY + '_fetch');
      if (f) return JSON.parse(f)?.product?.asin ?? '';
      const r = sessionStorage.getItem(CACHE_KEY + '_analyze');
      if (r) return JSON.parse(r)?.asin ?? '';
    } catch { /* */ }
    return '';
  });
  const [marketplace, setMarketplace] = useState(() => {
    try {
      const f = sessionStorage.getItem(CACHE_KEY + '_fetch');
      if (f) return JSON.parse(f)?.product?.marketplace ?? 'US';
      const r = sessionStorage.getItem(CACHE_KEY + '_analyze');
      if (r) return JSON.parse(r)?.marketplace ?? 'US';
    } catch { /* */ }
    return 'US';
  });
  const [keywords] = useState('');
  const [notes, setNotes] = useState('');

  /* ── 产品获取任务 ID（后台任务） ── */
  const [fetchProductTaskId, setFetchProductTaskId] = useState<string | null>(
    () => sessionStorage.getItem('lsta_fetch_task_id') || null,
  );

  /* ── 产品数据（含缓存恢复） ── */
  const [fetchingProduct, setFetchingProduct] = useState(
    () => !!sessionStorage.getItem('lsta_fetch_task_id'),
  );
  const [product, setProduct] = useState<ProductData | null>(() => {
    try {
      const r = sessionStorage.getItem(CACHE_KEY + '_fetch');
      if (r) return JSON.parse(r)?.product ?? null;
      const r2 = sessionStorage.getItem(CACHE_KEY + '_analyze');
      if (r2) return JSON.parse(r2)?.product ?? null;
    } catch { /* */ }
    return null;
  });
  const [fetchError, setFetchError] = useState('');

  const [triDimData, setTriDimData] = useState<TriDimDiagnostic | null>(() => {
    try { const r = sessionStorage.getItem(CACHE_KEY + '_fetch'); return r ? JSON.parse(r)?.triDim ?? null : null; } catch { return null; }
  });
  const [discoveredTrafficWords, setDiscoveredTrafficWords] = useState<TrafficWordItem[]>(() => {
    try { const r = sessionStorage.getItem(CACHE_KEY + '_fetch'); return r ? JSON.parse(r)?.trafficWords ?? [] : []; } catch { return []; }
  });
  const [selectedTrafficWords, setSelectedTrafficWords] = useState<string[]>(() => {
    try { const r = sessionStorage.getItem(CACHE_KEY + '_fetch'); return r ? JSON.parse(r)?.selectedWords ?? [] : []; } catch { return []; }
  });

  /* ── 评论分析结果（产品获取阶段自动并行执行） ── */
  const [reviewAnalysis, setReviewAnalysis] = useState<ReviewAnalysisResult | null>(() => {
    try { const r = sessionStorage.getItem(CACHE_KEY + '_fetch'); return r ? JSON.parse(r)?.reviewAnalysis ?? null : null; } catch { return null; }
  });
  /* ── 产品颜色（来自 leang_product_info.colour，供竞品发现/优化使用） ── */
  const [productColor, setProductColor] = useState<string>(() => {
    try { const r = sessionStorage.getItem(CACHE_KEY + '_fetch'); return r ? JSON.parse(r)?.dbColor ?? '' : ''; } catch { return ''; }
  });

  /* ── 搜索词相关性推荐 ── */
  const [searchTermLoading, setSearchTermLoading] = useState(false);
  const [searchTermData, setSearchTermData] = useState<SearchTermRecommendResponse | null>(() => {
    try { const r = sessionStorage.getItem(CACHE_KEY + '_searchTerm'); return r ? JSON.parse(r) : null; } catch { return null; }
  });
  const [searchTermError, setSearchTermError] = useState('');
  const [searchTermActiveLevel, setSearchTermActiveLevel] = useState<string | null>(() => {
    try { return sessionStorage.getItem(CACHE_KEY + '_searchTermLevel') || null; } catch { return null; }
  });
  const [searchTermLevelLoading, setSearchTermLevelLoading] = useState(false);
  const [searchLibSelectedWords, setSearchLibSelectedWords] = useState<string[]>([]);

  /* ── 分层获取进度 ── */
  type FetchStage = 'idle' | 'product' | 'search-term' | 'done';
  const [fetchStage, setFetchStage] = useState<FetchStage>('idle');

  /* ── 竞品 ASIN ── */
  interface CompetitorEntry { asin: string; loading: boolean; data: ProductData | null; error: string; }
  const [competitors, setCompetitors] = useState<CompetitorEntry[]>([]);

  /* ── 自动发现竞品（产品获取成功后异步触发，5 条，含完整 ProductData） ── */
  // 缓存：以 asin+marketplace 为 key，一次抓取可反复使用，页面刷新后恢复
  const AUTO_COMP_CACHE_KEY = 'lsta_auto_comp_data';
  interface AutoCompCache {
    asin: string;
    marketplace: string;
    competitors: CompetitorItem[];
    selected: string[];
    available: { colors: string[]; sizes: string[]; styles: string[] };
    filters: { colors: string[]; sizes: string[]; styles: string[] };
  }
  const _readAutoCompCache = (): AutoCompCache | null => {
    try {
      const raw = sessionStorage.getItem(AUTO_COMP_CACHE_KEY);
      return raw ? (JSON.parse(raw) as AutoCompCache) : null;
    } catch { return null; }
  };
  const _initialAutoCache = _readAutoCompCache();
  const [autoCompetitors, setAutoCompetitors] = useState<CompetitorItem[]>(
    () => (_initialAutoCache?.competitors || []).slice(0, AUTO_COMPETITOR_LIMIT),
  );
  const [autoCompSelected, setAutoCompSelected] = useState<Set<string>>(
    () => new Set((_initialAutoCache?.selected || []).slice(0, AUTO_COMPETITOR_LIMIT)),
  );
  const [autoCompLoading, setAutoCompLoading] = useState(false);
  const [autoCompError, setAutoCompError] = useState('');
  const [autoCompTaskId, setAutoCompTaskId] = useState<string | null>(
    () => sessionStorage.getItem('lsta_auto_comp_task_id') || null,
  );
  // 维度筛选勾选
  const [compFilterColors, setCompFilterColors] = useState<string[]>(
    () => _initialAutoCache?.filters?.colors || [],
  );
  const [compFilterSizes, setCompFilterSizes] = useState<string[]>(
    () => _initialAutoCache?.filters?.sizes || [],
  );
  const [compFilterStyles, setCompFilterStyles] = useState<string[]>(
    () => _initialAutoCache?.filters?.styles || [],
  );
  const [autoCompAvailable, setAutoCompAvailable] = useState<{
    colors: string[]; sizes: string[]; styles: string[];
  }>(
    () => _initialAutoCache?.available || { colors: [], sizes: [], styles: [] },
  );
  // 记录当前缓存对应的 asin/marketplace，用于 fetch 后判断是否需要重新发现
  const autoCompCacheKeyRef = useRef<{ asin: string; marketplace: string } | null>(
    _initialAutoCache ? { asin: _initialAutoCache.asin, marketplace: _initialAutoCache.marketplace } : null,
  );

  // 持久化：状态变更时写 sessionStorage（仅在有竞品数据时写入，清空则移除）
  useEffect(() => {
    if (!autoCompetitors.length) {
      sessionStorage.removeItem(AUTO_COMP_CACHE_KEY);
      return;
    }
    const ref = autoCompCacheKeyRef.current;
    if (!ref) return;
    try {
      const payload: AutoCompCache = {
        asin: ref.asin,
        marketplace: ref.marketplace,
        competitors: autoCompetitors,
        selected: Array.from(autoCompSelected),
        available: autoCompAvailable,
        filters: {
          colors: compFilterColors,
          sizes: compFilterSizes,
          styles: compFilterStyles,
        },
      };
      sessionStorage.setItem(AUTO_COMP_CACHE_KEY, JSON.stringify(payload));
    } catch { /* quota */ }
  }, [
    autoCompetitors, autoCompSelected, autoCompAvailable,
    compFilterColors, compFilterSizes, compFilterStyles,
  ]);
  const addCompetitor = () => setCompetitors(prev => [...prev, { asin: '', loading: false, data: null, error: '' }]);
  const removeCompetitor = (idx: number) => setCompetitors(prev => prev.filter((_, i) => i !== idx));
  const updateCompetitorAsin = (idx: number, val: string) =>
    setCompetitors(prev => prev.map((c, i) => i === idx ? { ...c, asin: val, error: '' } : c));
  const fetchCompetitor = async (idx: number) => {
    const entry = competitors[idx];
    if (!entry || entry.asin.trim().length !== 10) return;
    setCompetitors(prev => prev.map((c, i) => i === idx ? { ...c, loading: true, error: '' } : c));
    try {
      const { data } = await listingApi.fetch({ asin: entry.asin.trim(), marketplace });
      setCompetitors(prev => prev.map((c, i) => i === idx ? { ...c, loading: false, data, error: '' } : c));
    } catch (e: any) {
      setCompetitors(prev => prev.map((c, i) => i === idx ? { ...c, loading: false, error: e.message || '获取失败' } : c));
    }
  };

  const selectedCompetitorProducts = useMemo<ProductData[]>(() => {
    const manual = competitors.filter(c => c.data).map(c => c.data!);
    const auto = autoCompetitors
      .filter(c => autoCompSelected.has(c.asin) && c.product_data?.title)
      .map(c => c.product_data as ProductData);
    const seen = new Set<string>();
    const merged: ProductData[] = [];
    for (const pd of [...manual, ...auto]) {
      const key = (pd?.asin || pd?.title || '').trim().toUpperCase();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      merged.push(pd);
      if (merged.length >= AUTO_COMPETITOR_LIMIT) break;
    }
    return merged;
  }, [competitors, autoCompetitors, autoCompSelected]);

  /* ── FAB 增强模式开关（默认开启） ── */
  const [enableFab, setEnableFab] = useState(true);

  /* ── 候选数量（Best-of-N，1~10；>1 时并行生成多份候选 + LLM 评分择优）。默认 3。 ── */
  const [variantCount, setVariantCount] = useState<number>(() => {
    try {
      const raw = sessionStorage.getItem('lsta_variant_count');
      if (raw == null || raw === '') return 3;
      const v = Number(raw);
      return v >= 1 && v <= 10 ? Math.round(v) : 3;
    } catch { return 3; }
  });
  useEffect(() => {
    try { sessionStorage.setItem('lsta_variant_count', String(variantCount)); } catch {}
  }, [variantCount]);

  /* ── 选择性优化勾选项 ── */
  const [optimizeSections, setOptimizeSections] = useState<string[]>([...ALL_SECTIONS]);

  /* ── 优化 / 诊断结果（独立等待状态） ── */
  const [optimizeRunning, setOptimizeRunning] = useState(() => !!sessionStorage.getItem('lsta_opt_task_id'));
  const [analyzeRunning, setAnalyzeRunning] = useState(false);
  const [optimizeResult, setOptimizeResult] = useState<ListingOptimizeResponse | null>(() => {
    try { const r = sessionStorage.getItem(CACHE_KEY + '_optimize'); return r ? JSON.parse(r) : null; } catch { return null; }
  });
  const [analyzeResult, setAnalyzeResult] = useState<ListingAnalyzeResponse | null>(() => {
    try {
      const r = sessionStorage.getItem(CACHE_KEY + '_analyze');
      if (!r) return null;
      const parsed = JSON.parse(r);
      return parsed?.result ?? parsed ?? null;
    } catch { return null; }
  });
  const [deepDiagnosticResult, setDeepDiagnosticResult] = useState<ListingDeepDiagnosticResponse | null>(() => {
    try { const r = sessionStorage.getItem(CACHE_KEY + '_deepDiagnostic'); return r ? JSON.parse(r) : null; } catch { return null; }
  });
  const [analyzeStartedAt, setAnalyzeStartedAt] = useState<number | null>(null);
  const [refineVersions, setRefineVersions] = useState<RefineVersion[]>(() => {
    try { const r = sessionStorage.getItem(CACHE_KEY + '_refines'); return r ? JSON.parse(r) : []; } catch { return []; }
  });
  const [actionError, setActionError] = useState('');

  /* ── 三维分析 ── */
  const [triDimOpen, setTriDimOpen] = useState(false);
  const [triDimLoading, setTriDimLoading] = useState(false);
  const [triDimResult, setTriDimResult] = useState<SQLExecResponse | null>(null);
  const [triDimError, setTriDimError] = useState('');
  const [triDimPage2, setTriDimPage2] = useState(1);
  const [triDimPageSize2, setTriDimPageSize2] = useState(50);
  const [triDimTotal2, setTriDimTotal2] = useState(0);

  const loadTriDimPage = async (target: string, page: number, ps: number) => {
    setTriDimLoading(true);
    setTriDimError('');
    setTriDimPage2(page);
    try {
      const { dataSql, countSql } = await fetchTriDimDiagnosticSql({
        dateRange: 30,
        asin: target,
        page,
        pageSize: ps,
        row_filter: true,
        include_count_sql: page === 1,
      });
      const [dataRes, countRes] = await Promise.all([
        stiApi.execSql(dataSql),
        page === 1 && countSql ? stiApi.execSql(countSql) : Promise.resolve(null),
      ]);
      if (dataRes.data.error) setTriDimError(dataRes.data.error);
      else {
        setTriDimResult(dataRes.data);
        if (countRes?.data?.rows?.[0]?.total != null) setTriDimTotal2(Number(countRes.data.rows[0].total));
      }
    } catch (e: any) { setTriDimError(e.message || '查询失败'); }
    finally { setTriDimLoading(false); }
  };

  const handleTriDimAnalysis = async () => {
    const target = asin.trim();
    if (target.length !== 10) { message.warning('请输入 10 位 ASIN'); return; }
    setTriDimOpen(true);
    setTriDimResult(null);
    setTriDimTotal2(0);
    setTriDimPage2(1);
    loadTriDimPage(target, 1, triDimPageSize2);
  };

  useEffect(() => {
    if (searchTermData) try { sessionStorage.setItem(CACHE_KEY + '_searchTerm', JSON.stringify(searchTermData)); } catch {}
  }, [searchTermData]);
  useEffect(() => {
    if (searchTermActiveLevel) try { sessionStorage.setItem(CACHE_KEY + '_searchTermLevel', searchTermActiveLevel); }
    catch {} 
  }, [searchTermActiveLevel]);
  useEffect(() => {
    if (optimizeResult) try { sessionStorage.setItem(CACHE_KEY + '_optimize', JSON.stringify(optimizeResult)); } catch {}
  }, [optimizeResult]);
  useEffect(() => {
    if (analyzeResult) {
      try {
        sessionStorage.setItem(CACHE_KEY + '_analyze', JSON.stringify({
          result: analyzeResult,
          product: product ?? analyzeResult.product ?? null,
          asin: analyzeResult.asin || asin,
          marketplace: analyzeResult.marketplace || marketplace,
        }));
      } catch { /* */ }
    }
  }, [analyzeResult, product, asin, marketplace]);
  useEffect(() => {
    if (deepDiagnosticResult) {
      try { sessionStorage.setItem(CACHE_KEY + '_deepDiagnostic', JSON.stringify(deepDiagnosticResult)); } catch {}
    }
  }, [deepDiagnosticResult]);
  useEffect(() => {
    try { sessionStorage.setItem(CACHE_KEY + '_refines', JSON.stringify(refineVersions)); } catch {}
  }, [refineVersions]);
  /* ── 监听后台优化任务完成 ── */
  useEffect(() => {
    if (!currentOptTaskId) return;
    const info = tasks.get(currentOptTaskId);
    if (!info) {
      // 任务记录已不存在（如 sessionStorage 不一致 / 后端重启），自愈解除 loading
      setOptimizeRunning(false);
      setCurrentOptTaskId(null);
      sessionStorage.removeItem('lsta_opt_task_id');
      return;
    }
    if (info.status === 'completed' && info.result) {
      const data = info.result as import('../api').ListingOptimizeResponse;
      setOptimizeResult(data);
      setRefineVersions(buildVersionsFromOptimizeResult(data));
      setOptimizeRunning(false);
      setCurrentOptTaskId(null);
      sessionStorage.removeItem('lsta_opt_task_id');
      const vCount = data.variants?.length ?? 0;
      if (vCount > 1) {
        message.success(`已生成 ${vCount} 份候选，已按曝光/转化加权择优`);
      } else {
        message.success('优化完成');
      }
    } else if (info.status === 'failed') {
      setActionError(info.error || '优化失败');
      message.error(info.error || '优化失败', 6);
      setOptimizeRunning(false);
      setCurrentOptTaskId(null);
      sessionStorage.removeItem('lsta_opt_task_id');
    }
  }, [currentOptTaskId, tasks]);

  /* ── 监听后台诊断任务完成 ── */
  useEffect(() => {
    if (!currentAnaTaskId) return;
    const info = tasks.get(currentAnaTaskId);
    if (!info) {
      setAnalyzeRunning(false);
      setCurrentAnaTaskId(null);
      sessionStorage.removeItem('lsta_ana_task_id');
      return;
    }
    if (info.status === 'completed' && info.result) {
      const data = info.result as import('../api').ListingAnalyzeResponse;
      setAnalyzeResult(data);
      if (data.product && !product?.title) setProduct(data.product);
      setAnalyzeRunning(false);
      setCurrentAnaTaskId(null);
      sessionStorage.removeItem('lsta_ana_task_id');
      message.success('诊断完成');
    } else if (info.status === 'failed') {
      setActionError(info.error || '诊断失败');
      message.error(info.error || '诊断失败', 6);
      setAnalyzeRunning(false);
      setCurrentAnaTaskId(null);
      sessionStorage.removeItem('lsta_ana_task_id');
    }
  }, [currentAnaTaskId, tasks, product]);

  // 用户手动改变选中词时，同步更新 fetch 缓存中的 selectedWords
  useEffect(() => {
    try {
      const r = sessionStorage.getItem(CACHE_KEY + '_fetch');
      if (r) {
        const cached = JSON.parse(r);
        cached.selectedWords = selectedTrafficWords;
        sessionStorage.setItem(CACHE_KEY + '_fetch', JSON.stringify(cached));
      }
    } catch { /* */ }
  }, [selectedTrafficWords]);

  /* ── 搜索词推荐（产品获取完成后自动触发） ── */
  const _loadSearchTerms = useCallback(async (asinVal: string) => {
    setSearchTermLoading(true);
    setSearchTermError('');
    try {
      const { data: stData } = await listingApi.searchTermRecommend({
        asin: asinVal, relevance_filter: null,
      });
      setSearchTermData(stData);
      try { sessionStorage.setItem(CACHE_KEY + '_searchTerm', JSON.stringify(stData)); } catch {}

      if (stData.success && stData.summary) {
        const LEVEL_ORDER = ['高相关', '中高相关', '中相关', '中低相关', '低相关'];
        const firstLevel = LEVEL_ORDER.find(lv => (stData.summary[lv] ?? 0) > 0);
        if (firstLevel) {
          setSearchTermActiveLevel(firstLevel);
          setSearchTermLevelLoading(true);
          try {
            const { data: levelResp } = await listingApi.searchTermRecommend({
              asin: asinVal, relevance_filter: firstLevel,
            });
            setSearchTermData(levelResp);
          } catch { /* */ }
          setSearchTermLevelLoading(false);
        }
      }
    } catch (e: any) {
      setSearchTermError(e.message || '搜索词推荐获取失败');
    } finally {
      setSearchTermLoading(false);
      setFetchStage('done');
    }
  }, []);

  /* ── 监听产品获取后台任务 ── */
  useEffect(() => {
    if (!fetchProductTaskId) return;
    const t = tasks.get(fetchProductTaskId);
    if (!t) {
      setFetchingProduct(false);
      setFetchProductTaskId(null);
      sessionStorage.removeItem('lsta_fetch_task_id');
      setFetchStage('idle');
      return;
    }
    if (t.status === 'completed' && t.result) {
      const data = t.result as any;
      const prod = data.product;
      if (prod) {
        setProduct(prod);
        if (data.tri_dim) setTriDimData(data.tri_dim);
        if (data.review_analysis) setReviewAnalysis(data.review_analysis);
        const dbColor = (data.db_color || '').trim();
        setProductColor(dbColor);
        const autoSelect: string[] = [];
        if (data.traffic_words?.length) {
          setDiscoveredTrafficWords(data.traffic_words);
          data.traffic_words
            .filter((tw: any) =>
              tw.relevance === 'clear' ||
              (tw.relevance === 'unknown' && tw.aba_search_rank != null && tw.aba_search_rank <= 50000),
            )
            .forEach((tw: any) => autoSelect.push(tw.word));
          setSelectedTrafficWords(autoSelect);
        }
        try {
          sessionStorage.setItem(CACHE_KEY + '_fetch', JSON.stringify({
            product: prod,
            triDim: data.tri_dim ?? null,
            trafficWords: data.traffic_words ?? [],
            selectedWords: autoSelect,
            reviewAnalysis: data.review_analysis ?? null,
            dbColor,
          }));
        } catch { /* quota */ }
      }
      setFetchingProduct(false);
      setFetchProductTaskId(null);
      sessionStorage.removeItem('lsta_fetch_task_id');
      setFetchStage('search-term');
      if (prod?.asin) {
        _loadSearchTerms(prod.asin);
        // 命中缓存（同 asin+marketplace 已有竞品）则直接复用，避免重复抓取
        const mkt = prod.marketplace || marketplace;
        const cacheRef = autoCompCacheKeyRef.current;
        const cacheHit = !!cacheRef
          && cacheRef.asin === prod.asin
          && cacheRef.marketplace === mkt
          && autoCompetitors.length > 0;
        if (cacheHit) {
          setAutoCompLoading(false);
          setAutoCompError('');
          return;
        }
        // 异步触发一次竞品发现（5 条 + 完整 ProductData），用于差异化优化
        (async () => {
          try {
            setAutoCompetitors([]);
            setAutoCompSelected(new Set());
            setAutoCompAvailable({ colors: [], sizes: [], styles: [] });
            setCompFilterColors([]);
            setCompFilterSizes([]);
            setCompFilterStyles([]);
            setAutoCompError('');
            setAutoCompLoading(true);
            autoCompCacheKeyRef.current = { asin: prod.asin, marketplace: mkt };
            const productForCompetitors: ProductData = {
              ...prod,
              price: prod.price || product?.price || '',
              currency: prod.currency || product?.currency || 'USD',
            };
            const tid = await submitTask(
              'discover_competitors',
              {
                asin: prod.asin,
                marketplace: mkt,
                product_data: productForCompetitors,
                max_results: 5,
                with_details: true,
                color: (data.db_color || '').trim() || undefined,
              },
              { asin: prod.asin, marketplace: mkt },
            );
            setAutoCompTaskId(tid);
            sessionStorage.setItem('lsta_auto_comp_task_id', tid);
          } catch (e: any) {
            setAutoCompLoading(false);
            setAutoCompError(e?.message || '竞品发现提交失败');
          }
        })();
      }
    } else if (t.status === 'failed') {
      setFetchError(t.error || '获取失败');
      setFetchingProduct(false);
      setFetchProductTaskId(null);
      sessionStorage.removeItem('lsta_fetch_task_id');
      setFetchStage('idle');
    } else if (t.status === 'pending' || t.status === 'running') {
      setFetchingProduct(true);
      // 产品数据一就绪就提前渲染，无需等三维诊断/流量词全部完成
      const partialData = (t as any).partial as any;
      if (partialData?.product) {
        setProduct(prev => prev ?? partialData.product);
      }
    }
  }, [tasks, fetchProductTaskId, _loadSearchTerms]);

  /* ── 监听自动竞品发现任务 ── */
  useEffect(() => {
    if (!autoCompTaskId) return;
    const t = tasks.get(autoCompTaskId);
    if (!t) {
      // 任务记录丢失（后端重启等），自愈清理
      setAutoCompLoading(false);
      setAutoCompTaskId(null);
      sessionStorage.removeItem('lsta_auto_comp_task_id');
      return;
    }
    if (t.status === 'completed' && t.result) {
      const resp = t.result as CompetitorDiscoveryResponse;
      const list = (resp.competitors || []).slice(0, AUTO_COMPETITOR_LIMIT);
      setAutoCompetitors(list);
      // 后端已按贴合度排序；这里只默认选择前 5 个有完整详情的精选竞品。
      const preSelected = new Set(
        list
          .filter(c => c.product_data?.title)
          .slice(0, AUTO_COMPETITOR_LIMIT)
          .map(c => c.asin),
      );
      setAutoCompSelected(preSelected);
      setAutoCompAvailable({
        colors: resp.available_colors || [],
        sizes: resp.available_sizes || [],
        styles: resp.available_styles || [],
      });
      setAutoCompLoading(false);
      setAutoCompError(resp.error || '');
      setAutoCompTaskId(null);
      sessionStorage.removeItem('lsta_auto_comp_task_id');
    } else if (t.status === 'failed') {
      setAutoCompError(t.error || '竞品发现失败');
      setAutoCompLoading(false);
      setAutoCompTaskId(null);
      sessionStorage.removeItem('lsta_auto_comp_task_id');
    } else if (t.status === 'pending' || t.status === 'running') {
      setAutoCompLoading(true);
    }
  }, [tasks, autoCompTaskId]);

  /* ── 手动获取产品数据（提交后台任务，可切换页面不丢失） ── */
  const handleFetchProduct = async () => {
    const trimmed = asin.trim();
    if (trimmed.length !== 10) {
      setFetchError('ASIN 必须是 10 位');
      return;
    }
    setFetchingProduct(true);
    setFetchError('');
    setProduct(null);
    setOptimizeResult(null);
    setAnalyzeResult(null);
    setRefineVersions([]);
    setTriDimData(null);
    setDiscoveredTrafficWords([]);
    setSelectedTrafficWords([]);
    setSearchLibSelectedWords([]);
    setReviewAnalysis(null);
    setProductColor('');
    setSearchTermData(null);
    setSearchTermError('');
    setSearchTermActiveLevel(null);
    setFetchStage('product');
    sessionStorage.removeItem(CACHE_KEY + '_fetch');
    sessionStorage.removeItem(CACHE_KEY + '_searchTerm');
    sessionStorage.removeItem(CACHE_KEY + '_searchTermLevel');

    try {
      const tid = await submitTask(
        'fetch_product' as any,
        { asin: trimmed, marketplace },
        { asin: trimmed, marketplace },
      );
      setFetchProductTaskId(tid);
      sessionStorage.setItem('lsta_fetch_task_id', tid);
    } catch (e: any) {
      setFetchingProduct(false);
      setFetchError(e.message || '提交失败');
      setFetchStage('idle');
    }
  };

  const handleSearchTermLevelChange = async (level: string | null) => {
    setSearchTermActiveLevel(level);
    if (!level || !asin.trim()) {
      setSearchTermData(prev => prev ? { ...prev, search_terms: [] } : prev);
      return;
    }
    setSearchTermLevelLoading(true);
    try {
      const { data: resp } = await listingApi.searchTermRecommend({
        asin: asin.trim(),
        relevance_filter: level,
      });
      setSearchTermData(resp);
    } catch (e: any) {
      setSearchTermError(e.message || '加载失败');
    } finally {
      setSearchTermLevelLoading(false);
    }
  };

  const handleModelChange = (v: string | undefined) => {
    setSelectedModel(v);
    if (v) sessionStorage.setItem('lsta_model', v);
    else sessionStorage.removeItem('lsta_model');
  };
  const handleEvalModelChange = (v: string | undefined) => {
    setSelectedEvalModel(v);
    if (v) sessionStorage.setItem('lsta_eval_model', v);
    else sessionStorage.removeItem('lsta_eval_model');
  };

  /* ── 开始优化（后台任务） ── */
  const handleOptimize = async () => {
    const p = product || EMPTY_PRODUCT;
    if (!asin.trim() && !p.asin) { message.warning('请输入 ASIN'); return; }
    setOptimizeRunning(true);
    setActionError('');
    setOptimizeResult(null);
    setRefineVersions([]);
    try {
      const useProduct = p.asin ? p : { ...p, asin: asin.trim(), marketplace };
      const kw = selectedTrafficWords.length > 0 ? [...selectedTrafficWords] : (keywords ? keywords.split(/[,，\n]/).map(k => k.trim()).filter(Boolean) : []);
      const params = {
        asin: useProduct.asin || asin.trim(), marketplace: useProduct.marketplace || marketplace,
        target_keywords: kw,
        target_audience: notes,
        session_id: sessionId,
        model: selectedModel,
        eval_model: selectedEvalModel,
        prompt_overrides: promptCfg.activeOverrides(),
        product_data: useProduct.title ? useProduct : undefined,
        optimize_sections: optimizeSections.length < 4 ? optimizeSections : undefined,
        competitor_products: selectedCompetitorProducts.length ? selectedCompetitorProducts : undefined,
        enable_fab: enableFab,
        review_analysis: reviewAnalysis ?? undefined,
        variant_count: variantCount,
        color: productColor || undefined,
        tri_dim: triDimData ?? undefined,
      };
      const taskId = await submitTask('optimize', params, {
        asin: params.asin, marketplace: params.marketplace,
      });
      setCurrentOptTaskId(taskId);
      sessionStorage.setItem('lsta_opt_task_id', taskId);
      if (variantCount > 1) {
        message.info(`已提交：将并行生成 ${variantCount} 份候选，按曝光/转化加权择优`);
      } else {
        message.info('优化任务已提交到后台，可自由切换页面');
      }
    } catch (e: any) {
      setOptimizeRunning(false);
      const errMsg = e.response?.data?.detail || e.message || '提交失败';
      setActionError(errMsg);
      message.error(errMsg, 6);
    }
  };

  /* ── 开始深度诊断：继承产品信息，补齐竞品，再生成自我 + 对比诊断 ── */
  const handleAnalyze = async () => {
    const p = product || EMPTY_PRODUCT;
    if (!asin.trim() && !p.asin) { message.warning('请输入 ASIN'); return; }
    setAnalyzeRunning(true);
    setAnalyzeStartedAt(Date.now());
    setActionError('');
    setAnalyzeResult(null);
    setDeepDiagnosticResult(null);
    sessionStorage.removeItem(CACHE_KEY + '_deepDiagnostic');
    sessionStorage.removeItem('lsta_ana_task_id');
    setCurrentAnaTaskId(null);
    try {
      const targetAsin = (p.asin || asin.trim()).trim();
      const targetMarketplace = p.marketplace || marketplace;
      let useProduct: ProductData = p.title
        ? { ...p, asin: targetAsin, marketplace: targetMarketplace }
        : { ...(await listingApi.fetch({ asin: targetAsin, marketplace: targetMarketplace })).data, asin: targetAsin, marketplace: targetMarketplace };
      if (!product?.title) setProduct(useProduct);

      let compProducts = selectedCompetitorProducts;
      if (compProducts.length < AUTO_COMPETITOR_LIMIT) {
        message.info('正在补齐诊断所需的 5 条竞品信息...');
        setAutoCompLoading(true);
        setAutoCompError('');
        const { data: compResp } = await listingApi.discoverCompetitors({
          asin: targetAsin,
          marketplace: targetMarketplace,
          product_data: useProduct,
          max_results: AUTO_COMPETITOR_LIMIT,
          with_details: true,
          color: productColor || undefined,
        });
        const discovered = (compResp.competitors || []).slice(0, AUTO_COMPETITOR_LIMIT);
        setAutoCompetitors(discovered);
        setAutoCompSelected(new Set(discovered.filter(c => c.product_data?.title).map(c => c.asin)));
        setAutoCompAvailable({
          colors: compResp.available_colors || [],
          sizes: compResp.available_sizes || [],
          styles: compResp.available_styles || [],
        });
        setAutoCompLoading(false);
        setAutoCompError(compResp.error || '');
        autoCompCacheKeyRef.current = { asin: targetAsin, marketplace: targetMarketplace };
        compProducts = discovered
          .filter(c => c.product_data?.title)
          .map(c => c.product_data as ProductData)
          .slice(0, AUTO_COMPETITOR_LIMIT);
      }

      const { data } = await listingApi.deepDiagnostic({
        asin: targetAsin,
        marketplace: targetMarketplace,
        model: selectedModel,
        product_data: useProduct,
        current_title: useProduct.title,
        current_bullet_points: useProduct.bullet_points || [],
        current_description: useProduct.description || '',
        current_search_terms: selectedTrafficWords.join(' '),
        review_analysis: reviewAnalysis ?? undefined,
        competitor_products: compProducts.slice(0, AUTO_COMPETITOR_LIMIT),
      });
      setDeepDiagnosticResult(data);
      message.success(`诊断完成，已纳入 ${compProducts.length} 条竞品做对比`);
    } catch (e: any) {
      setAnalyzeRunning(false);
      setAutoCompLoading(false);
      const errMsg = e.response?.data?.detail || e.message || '提交失败';
      setActionError(errMsg);
      message.error(errMsg, 6);
      return;
    } finally {
      setAnalyzeRunning(false);
    }
  };

  const optimizeFlowSteps = [
    {
      key: 'input',
      title: '产品输入',
      desc: asin.trim() || 'ASIN / 站点',
      icon: <SearchOutlined />,
      state: asin.trim().length === 10 || product?.title ? 'done' : 'active',
    },
    {
      key: 'product',
      title: '产品获取',
      desc: fetchingProduct ? '抓取中' : product?.title ? '已获取' : '等待抓取',
      icon: <ShoppingOutlined />,
      state: fetchingProduct ? 'active' : product?.title ? 'done' : 'idle',
    },
    {
      key: 'competitor',
      title: '竞品发现',
      desc: autoCompLoading ? '自动寻找中' : autoCompetitors.length ? `已选 ${autoCompSelected.size}/${autoCompetitors.length}` : '差异化参考',
      icon: <DatabaseOutlined />,
      state: autoCompLoading ? 'active' : autoCompetitors.length ? 'done' : product?.title ? 'ready' : 'idle',
    },
    {
      key: 'config',
      title: '策略配置',
      desc: `候选 x${variantCount} / ${enableFab ? 'FAB开' : 'FAB关'}`,
      icon: <SettingOutlined />,
      state: product?.title ? 'ready' : 'idle',
    },
    {
      key: 'optimize',
      title: 'AI 优化',
      desc: optimizeRunning ? '生成与评分中' : optimizeResult ? '已完成' : '等待启动',
      icon: <ThunderboltOutlined />,
      state: optimizeRunning ? 'active' : optimizeResult ? 'done' : product?.title ? 'ready' : 'idle',
    },
    {
      key: 'result',
      title: '结果对比',
      desc: optimizeResult?.variants?.length ? `${optimizeResult.variants.length} 份候选` : optimizeResult ? '可查看' : '待生成',
      icon: <CheckOutlined />,
      state: optimizeResult ? 'done' : 'idle',
    },
  ];

  const analyzeTaskInfo = currentAnaTaskId ? tasks.get(currentAnaTaskId) : undefined;
  const analyzeReportReady = !!deepDiagnosticResult;
  const analyzeElapsedMs = analyzeTaskInfo?.elapsedMs
    ?? (analyzeStartedAt ? Date.now() - analyzeStartedAt : 0);
  const analyzeFlowSteps = [
    {
      key: 'input',
      title: '诊断输入',
      desc: asin.trim() || 'ASIN / 站点',
      icon: <SearchOutlined />,
      state: asin.trim().length === 10 || product?.title ? 'done' : 'active',
    },
    {
      key: 'product',
      title: '资料继承',
      desc: fetchingProduct ? '抓取中' : product?.title ? '已继承产品信息' : '等待产品信息',
      icon: <ShoppingOutlined />,
      state: fetchingProduct ? 'active' : product?.title ? 'done' : 'idle',
    },
    {
      key: 'evidence',
      title: '评论图片',
      desc: product?.images?.length || reviewAnalysis ? `图片 ${product?.images?.length || 0} / 评论已就绪` : '等待素材',
      icon: <DatabaseOutlined />,
      state: product?.images?.length || reviewAnalysis ? 'done' : product?.title ? 'ready' : 'idle',
    },
    {
      key: 'diagnose',
      title: 'AI 诊断',
      desc: analyzeRunning ? '诊断中' : analyzeReportReady ? '已完成' : '等待启动',
      icon: <BarChartOutlined />,
      state: analyzeRunning ? 'active' : analyzeReportReady ? 'done' : product?.title ? 'ready' : 'idle',
    },
    {
      key: 'structure',
      title: '对比诊断',
      desc: analyzeReportReady ? '竞品对比已生成' : selectedCompetitorProducts.length ? `竞品 ${selectedCompetitorProducts.length}/5` : '待获取竞品',
      icon: <TagOutlined />,
      state: analyzeReportReady ? 'done' : analyzeRunning || selectedCompetitorProducts.length ? 'ready' : 'idle',
    },
    {
      key: 'result',
      title: '诊断报告',
      desc: analyzeReportReady ? '可查看' : '待输出',
      icon: <CheckOutlined />,
      state: analyzeReportReady ? 'done' : 'idle',
    },
  ];
  const flowSteps = activeTab === 'analyze' ? analyzeFlowSteps : optimizeFlowSteps;
  const flowTitle = activeTab === 'analyze' ? 'Listing 诊断执行链路' : 'Listing 优化执行链路';
  const flowKicker = activeTab === 'analyze' ? 'LISTING DIAGNOSTIC WORKFLOW' : 'LISTING OPTIMIZE WORKFLOW';
  const flowMeta = activeTab === 'analyze'
    ? (analyzeRunning ? '诊断运行中' : analyzeReportReady ? '诊断报告已生成' : product?.title ? '诊断资料已就绪' : '等待产品输入')
    : (optimizeRunning ? '优化运行中' : optimizeResult ? '已生成结果' : product?.title ? '产品信息已就绪' : '等待产品输入');

  return (
    <div className="listing-optimize-page">
      {activeTab === 'batch' ? (
        <BatchOptimizePanel />
      ) : (
      <>
      <div className="lsta-flow-indicator" aria-label={flowTitle}>
        <div className="lsta-flow-header">
          <div>
            <div className="lsta-flow-kicker">{flowKicker}</div>
            <div className="lsta-flow-title">{flowTitle}</div>
          </div>
          <div className="lsta-flow-meta">
            {flowMeta}
          </div>
        </div>
        <div className="lsta-flow-track">
          {flowSteps.map((step, idx) => (
            <div
              key={step.key}
              className={`lsta-flow-step is-${step.state} ${idx < flowSteps.length - 1 ? 'has-next' : ''}`}
            >
              <div className="lsta-flow-node">
                <span className="lsta-flow-icon">{step.icon}</span>
              </div>
              <div className="lsta-flow-copy">
                <span>{step.title}</span>
                <em>{step.desc}</em>
              </div>
            </div>
          ))}
        </div>
      </div>
      <Row gutter={24}>
        {/* ── 左侧：输入面板 ── */}
        <Col xs={24} lg={7}>
          <Card
            title="产品查询"
            extra={
              <Space size={0}>
                <Tooltip title="细节设置（修改意见 / 模型 / FAB / 优化范围 / 候选数量）">
                  <Button
                    type="text"
                    icon={<EditOutlined />}
                    onClick={() => setDetailsOpen(true)}
                    style={{
                      color: (
                        notes.trim()
                        || (activeTab === 'optimize' && variantCount > 1)
                        || (activeTab === 'optimize' && optimizeSections.length < ALL_SECTIONS.length)
                        || (activeTab === 'optimize' && !enableFab)
                      ) ? ACCENT : undefined,
                    }}
                  />
                </Tooltip>
                <Tooltip title="提示词设置">
                  <Button type="text" icon={<SettingOutlined />}
                    onClick={() => setSettingsOpen(true)}
                    style={{ color: promptCfg.activeOverrides() ? ACCENT : undefined }} />
                </Tooltip>
              </Space>
            }
            style={{ borderRadius: 14, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', position: 'sticky', top: 88, zIndex: 10 }}
          >
            <div style={{ marginBottom: 12 }}>
              <Text strong style={{ fontSize: 12 }}>ASIN</Text>
              <Input
                placeholder="输入 10 位 ASIN"
                maxLength={10} size="large" allowClear
                value={asin} onChange={e => setAsin(e.target.value)}
                status={fetchError ? 'error' : undefined}
                onPressEnter={handleFetchProduct}
                style={{ marginTop: 4 }}
              />
              {fetchError && <Text type="danger" style={{ fontSize: 11 }}>{fetchError}</Text>}
            </div>

            <div style={{ marginBottom: 12 }}>
              <Text strong style={{ fontSize: 12 }}>站点</Text>
              <Select options={MARKETPLACES} value={marketplace} onChange={setMarketplace}
                size="large" style={{ width: '100%', marginTop: 4 }} />
            </div>

            <Button
              type="primary" block size="large"
              icon={<SearchOutlined />}
              loading={fetchingProduct}
              onClick={handleFetchProduct}
              disabled={asin.trim().length !== 10}
              style={{
                marginBottom: 16, height: 44, borderRadius: 10, fontWeight: 600,
                background: product ? RD[0] : R[0],
              }}
            >
              {fetchingProduct ? '获取中...' : product ? '重新获取产品信息' : '获取产品信息'}
            </Button>

            {/* ── 自动发现竞品（产品获取成功后异步触发，支持维度筛选 + 勾选） ── */}
            {activeTab === 'optimize' && (product || autoCompLoading || autoCompetitors.length > 0 || autoCompError) && (() => {
              // 根据筛选维度过滤
              const filtered = autoCompetitors.filter(c => {
                if (compFilterColors.length && !compFilterColors.includes(c.color || '')) return false;
                if (compFilterSizes.length && !compFilterSizes.includes(c.size || '')) return false;
                if (compFilterStyles.length && !compFilterStyles.includes(c.style || '')) return false;
                return true;
              });
              const selectedCount = autoCompetitors.filter(c => autoCompSelected.has(c.asin)).length;
              const mkt = product?.marketplace || marketplace || 'US';
              return (
                <div style={{ marginBottom: 12, background: 'rgba(6, 23, 38, 0.88)', border: '1px solid rgba(83, 210, 255, 0.28)', borderRadius: 10, padding: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <Text strong style={{ fontSize: 12 }}>
                      自动发现的竞品
                      {autoCompetitors.length > 0 && (
                        <Tag color="blue" style={{ marginLeft: 6, fontSize: 10 }}>
                          精选 {selectedCount}/{Math.min(AUTO_COMPETITOR_LIMIT, autoCompetitors.length)}
                        </Tag>
                      )}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 10 }}>
                      仅选最贴合的 5 件参与优化
                    </Text>
                  </div>
                  {autoCompLoading && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 4px' }}>
                      <Spin size="small" />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        AI 正在为你自动寻找 5 条竞品（含完整文案），预计 15-30 秒...
                      </Text>
                    </div>
                  )}
                  {autoCompError && !autoCompLoading && (
                    <Alert
                      type="warning"
                      showIcon
                      message={autoCompError}
                      style={{ fontSize: 12, marginBottom: 6 }}
                    />
                  )}
                  {autoCompetitors.length > 0 && (
                    <>
                      {/* 维度筛选 */}
                      {(autoCompAvailable.colors.length + autoCompAvailable.sizes.length + autoCompAvailable.styles.length) > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8, padding: '6px 8px', background: 'rgba(2, 12, 23, 0.72)', border: '1px solid rgba(122, 205, 232, 0.2)', borderRadius: 6 }}>
                          {autoCompAvailable.colors.length > 0 && (
                            <div>
                              <Text type="secondary" style={{ fontSize: 10, marginRight: 6 }}>颜色：</Text>
                              <Checkbox.Group
                                value={compFilterColors}
                                onChange={v => setCompFilterColors(v as string[])}
                                style={{ fontSize: 11 }}
                              >
                                {autoCompAvailable.colors.map(c => (
                                  <Checkbox key={c} value={c} style={{ fontSize: 11 }}>{c}</Checkbox>
                                ))}
                              </Checkbox.Group>
                            </div>
                          )}
                          {autoCompAvailable.sizes.length > 0 && (
                            <div>
                              <Text type="secondary" style={{ fontSize: 10, marginRight: 6 }}>尺寸：</Text>
                              <Checkbox.Group
                                value={compFilterSizes}
                                onChange={v => setCompFilterSizes(v as string[])}
                                style={{ fontSize: 11 }}
                              >
                                {autoCompAvailable.sizes.map(s => (
                                  <Checkbox key={s} value={s} style={{ fontSize: 11 }}>{s}</Checkbox>
                                ))}
                              </Checkbox.Group>
                            </div>
                          )}
                          {autoCompAvailable.styles.length > 0 && (
                            <div>
                              <Text type="secondary" style={{ fontSize: 10, marginRight: 6 }}>款式：</Text>
                              <Checkbox.Group
                                value={compFilterStyles}
                                onChange={v => setCompFilterStyles(v as string[])}
                                style={{ fontSize: 11 }}
                              >
                                {autoCompAvailable.styles.map(s => (
                                  <Checkbox key={s} value={s} style={{ fontSize: 11 }}>{s}</Checkbox>
                                ))}
                              </Checkbox.Group>
                            </div>
                          )}
                          {(compFilterColors.length + compFilterSizes.length + compFilterStyles.length) > 0 && (
                            <Button
                              type="link" size="small" style={{ padding: 0, fontSize: 10, alignSelf: 'flex-end' }}
                              onClick={() => {
                                setCompFilterColors([]);
                                setCompFilterSizes([]);
                                setCompFilterStyles([]);
                              }}
                            >
                              清除筛选
                            </Button>
                          )}
                        </div>
                      )}
                      {/* 竞品卡片列表（按 ABCDE 标号，最多 5 条） */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {filtered.map((c, idx) => {
                          const checked = autoCompSelected.has(c.asin);
                          const hasDetail = !!c.product_data?.title;
                          const label = ['A', 'B', 'C', 'D', 'E'][idx] ?? '';
                          const bsr = c.bsr_rank || c.product_data?.bsr_rank || '';
                          return (
                            <div
                              key={c.asin}
                              style={{
                                display: 'flex', gap: 6, padding: 6, borderRadius: 6,
                                background: checked ? 'rgba(14, 165, 199, 0.2)' : 'rgba(2, 12, 23, 0.66)',
                                border: `1px solid ${checked ? 'rgba(53, 217, 255, 0.55)' : 'rgba(122, 205, 232, 0.22)'}`,
                                transition: 'background .15s',
                              }}
                            >
                              <Checkbox
                                checked={checked}
                                disabled={!hasDetail || (!checked && selectedCount >= AUTO_COMPETITOR_LIMIT)}
                                onChange={e => {
                                  setAutoCompSelected(prev => {
                                    const next = new Set(prev);
                                    if (e.target.checked) next.add(c.asin);
                                    else next.delete(c.asin);
                                    return next;
                                  });
                                }}
                                style={{ alignSelf: 'flex-start', marginTop: 2 }}
                              />
                              {label && (
                                <div
                                  title={`竞品 ${label}`}
                                  style={{
                                    width: 22, height: 22, borderRadius: '50%',
                                    background: checked ? '#2563EB' : '#9CA3AF',
                                    color: '#fff', fontSize: 11, fontWeight: 700,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    flexShrink: 0, alignSelf: 'flex-start', marginTop: 2,
                                  }}
                                >
                                  {label}
                                </div>
                              )}
                              {c.image && (
                                <img
                                  src={c.image}
                                  alt={c.asin}
                                  style={{ width: 44, height: 44, objectFit: 'cover', borderRadius: 4, flexShrink: 0 }}
                                />
                              )}
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <a
                                  href={amazonDetailUrl(c.asin, mkt)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  title={`打开 Amazon: ${c.asin}`}
                                  style={{ fontSize: 11, fontWeight: 500, color: '#2563EB', textDecoration: 'none', display: 'block', lineHeight: 1.4 }}
                                >
                                  <span style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                                    {c.title || c.asin}
                                  </span>
                                </a>
                                <div style={{ fontSize: 10, color: '#6B7280', marginTop: 2 }}>
                                  <a
                                    href={amazonDetailUrl(c.asin, mkt)}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ color: '#6B7280', textDecoration: 'underline dotted' }}
                                  >{c.asin}</a>
                                  <span style={{ margin: '0 4px' }}>·</span>
                                  {c.price || 'N/A'}
                                  {c.rating && <><span style={{ margin: '0 4px' }}>·</span>★{c.rating}</>}
                                  {c.review_count && <> ({c.review_count})</>}
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 3 }}>
                                  {bsr && (
                                    <Tag
                                      color="gold"
                                      style={{ fontSize: 10, margin: 0, padding: '0 4px', lineHeight: '16px', fontWeight: 600 }}
                                      title="Best Sellers Rank"
                                    >
                                      BSR #{bsr}
                                    </Tag>
                                  )}
                                  {c.color && <Tag color="magenta" style={{ fontSize: 10, margin: 0, padding: '0 4px', lineHeight: '16px' }}>{c.color}</Tag>}
                                  {c.size && <Tag color="cyan" style={{ fontSize: 10, margin: 0, padding: '0 4px', lineHeight: '16px' }}>{c.size}</Tag>}
                                  {c.style && <Tag color="purple" style={{ fontSize: 10, margin: 0, padding: '0 4px', lineHeight: '16px' }}>{c.style}</Tag>}
                                  {!hasDetail && (
                                    <Tag color="default" style={{ fontSize: 10, margin: 0, padding: '0 4px', lineHeight: '16px' }} title="详情抓取失败，无法参与差异化优化">
                                      无详情
                                    </Tag>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                        {filtered.length === 0 && (
                          <Text type="secondary" style={{ fontSize: 11, textAlign: 'center', padding: 10 }}>
                            当前筛选条件下无匹配竞品，请清除筛选
                          </Text>
                        )}
                      </div>
                    </>
                  )}
                </div>
              );
            })()}

            {/* ── 竞品 ASIN（仅优化模式使用） ── */}
            {activeTab === 'optimize' && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <Text strong style={{ fontSize: 12 }}>手动添加竞品 ASIN</Text>
                <Button type="link" size="small" icon={<PlusOutlined />}
                  disabled={competitors.length >= 5}
                  onClick={addCompetitor}
                  style={{ fontSize: 12, padding: 0 }}>
                  添加竞品
                </Button>
              </div>
              {competitors.map((comp, ci) => (
                <div key={ci} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    <Input
                      size="small" placeholder="竞品 ASIN（10位）" maxLength={10}
                      value={comp.asin} onChange={e => updateCompetitorAsin(ci, e.target.value)}
                      onPressEnter={() => fetchCompetitor(ci)}
                      status={comp.error ? 'error' : comp.data ? undefined : undefined}
                      style={{ flex: 1, borderRadius: 6, fontSize: 12 }}
                    />
                    <Button size="small" type="primary" icon={<SearchOutlined />}
                      loading={comp.loading}
                      disabled={comp.asin.trim().length !== 10}
                      onClick={() => fetchCompetitor(ci)}
                      style={{
                        borderRadius: 6, flexShrink: 0,
                        background: comp.data ? RD[0] : R[0],
                      }}
                    />
                    <Button size="small" type="text" danger icon={<DeleteOutlined />}
                      onClick={() => removeCompetitor(ci)} style={{ flexShrink: 0 }} />
                  </div>
                  {comp.error && <Text type="danger" style={{ fontSize: 10 }}>{comp.error}</Text>}
                  {comp.data && (
                    <div style={{
                      marginTop: 4, padding: '4px 8px', borderRadius: 6,
                      background: '#F0FDF4', border: '1px solid #D1FAE5', fontSize: 11, lineHeight: 1.5,
                    }}>
                      <Text ellipsis style={{ fontSize: 11, fontWeight: 500, display: 'block' }}>
                        {comp.data.title}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 10 }}>
                        {comp.data.brand || '未知品牌'} · {comp.data.price || 'N/A'} {comp.data.currency} · ★{comp.data.rating || 'N/A'}
                      </Text>
                    </div>
                  )}
                </div>
              ))}
            </div>
            )}

            {activeTab === 'optimize' && (
              <>
                <TrafficWordSelector
                  trafficWords={discoveredTrafficWords}
                  selectedWords={selectedTrafficWords}
                  onSelectedChange={setSelectedTrafficWords}
                />
                <SearchTermLibSelector
                  loading={searchTermLoading}
                  data={searchTermData}
                  error={searchTermError}
                  selectedTerms={selectedTrafficWords}
                  onSelectedChange={(words) => {
                    const prevSet = new Set(selectedTrafficWords);
                    const newSet = new Set(words);
                    const added = words.filter(w => !prevSet.has(w));
                    const removed = selectedTrafficWords.filter(w => !newSet.has(w));
                    setSelectedTrafficWords(words);
                    setSearchLibSelectedWords(prev => {
                      const next = prev.filter(w => !removed.includes(w));
                      return [...next, ...added];
                    });
                  }}
                  activeLevel={searchTermActiveLevel}
                  onLevelChange={handleSearchTermLevelChange}
                  levelLoading={searchTermLevelLoading}
                />
              </>
            )}

            {/* ── 当前细节设置摘要（一行展示，便于不打开抽屉也能看） ── */}
            <div
              onClick={() => setDetailsOpen(true)}
              style={{
                marginBottom: 12, padding: '8px 12px', borderRadius: 10, cursor: 'pointer',
                background: 'rgba(6, 23, 38, 0.88)', border: '1px dashed rgba(83, 210, 255, 0.28)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
              }}
            >
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', flex: 1, minWidth: 0 }}>
                <Tag color="default" style={{ fontSize: 11, margin: 0 }}>细节设置</Tag>
                {activeTab === 'optimize' && (
                  <>
                    <Tag color={variantCount > 1 ? 'gold' : 'default'} style={{ fontSize: 11, margin: 0 }}>
                      候选 ×{variantCount}
                    </Tag>
                    <Tag color={enableFab ? 'green' : 'default'} style={{ fontSize: 11, margin: 0 }}>
                      FAB {enableFab ? '开' : '关'}
                    </Tag>
                    <Tag
                      color={optimizeSections.length === ALL_SECTIONS.length ? 'blue' : 'orange'}
                      style={{ fontSize: 11, margin: 0 }}
                    >
                      范围 {optimizeSections.length}/{ALL_SECTIONS.length}
                    </Tag>
                    {notes.trim() && (
                      <Tag color="purple" style={{ fontSize: 11, margin: 0 }}>有修改意见</Tag>
                    )}
                  </>
                )}
                {selectedModel && (
                  <Tag color="cyan" style={{ fontSize: 11, margin: 0, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    模型：{selectedModel}
                  </Tag>
                )}
              </div>
              <EditOutlined style={{ color: '#9CA3AF', fontSize: 13, flexShrink: 0 }} />
            </div>

            {activeTab === 'optimize' ? (
              <Button
                type="primary" block size="large"
                icon={<ThunderboltOutlined />}
                loading={optimizeRunning}
                onClick={handleOptimize}
                disabled={optimizeSections.length === 0}
                style={{
                  height: 48, borderRadius: 10, fontWeight: 600, fontSize: 15,
                  background: optimizeSections.length === 0 ? undefined : R[1],
                }}
              >
                {optimizeRunning ? '优化运行中...' : '开始优化'}
              </Button>
            ) : (
              <Button
                type="primary" block size="large"
                icon={<BarChartOutlined />}
                loading={analyzeRunning}
                onClick={handleAnalyze}
                style={{
                  height: 48, borderRadius: 10, fontWeight: 600, fontSize: 15,
                  background: R[2],
                }}
              >
                {analyzeRunning ? '诊断运行中...' : '开始诊断'}
              </Button>
            )}

            <Button
              block size="large"
              icon={<BarChartOutlined />}
              loading={triDimLoading}
              onClick={handleTriDimAnalysis}
              disabled={asin.trim().length !== 10}
              style={{
                marginTop: 10, height: 42, borderRadius: 10, fontWeight: 600, fontSize: 14,
                borderColor: RAINBOW[3].from, color: RAINBOW[3].from,
              }}
            >
              三维数据诊断（CTR/CVR/流量）
            </Button>
          </Card>
        </Col>

        {/* ── 右侧：产品信息 + 操作按钮 + 结果 ── */}
        <Col xs={24} lg={17}>
          {actionError && (
            <Alert message="操作失败" description={actionError} type="error" showIcon closable
              onClose={() => setActionError('')} style={{ marginBottom: 16, borderRadius: 12 }} />
          )}

          {/* 产品信息（始终显示，支持手动输入和抓取回填） */}
          <div style={{ marginBottom: 16 }}>
            <EditableProductCard
              product={product || EMPTY_PRODUCT}
              onChange={p => setProduct(p.title ? p : null)}
              fetching={fetchingProduct}
              triDim={triDimData}
              fetchStage={fetchStage}
              searchTermLoading={searchTermLoading}
            />
          </div>

          {/* 评论洞察（产品获取阶段自动生成） */}
          {reviewAnalysis && (
            <div style={{ marginBottom: 16 }}>
              <ReviewInsightsPanel data={reviewAnalysis} />
            </div>
          )}

          {/* 优化中 loading（多候选：展示动态进度 + 已生成候选实时渲染） */}
          {activeTab === 'optimize' && optimizeRunning && (() => {
            const taskInfo = currentOptTaskId ? tasks.get(currentOptTaskId) : undefined;
            const partial = taskInfo?.partial;
            const isMulti = variantCount > 1;
            const total = partial?.total ?? variantCount;
            const generated = partial?.generated ?? 0;
            const evaluated = partial?.evaluated ?? 0;
            const elapsedMs = taskInfo?.elapsedMs ?? (taskInfo ? Date.now() - taskInfo.submittedAt : 0);

            // 动态预估：优先用已完成调用的实际速率；未开始则按并发=3 的经验公式
            const totalCalls = isMulti ? 2 * total : 2;
            const doneCalls = isMulti ? generated + evaluated : 0;
            const pendingCalls = Math.max(totalCalls - doneCalls, 0);
            let estSec: number;
            if (doneCalls > 0 && elapsedMs > 0) {
              estSec = Math.max(3, Math.round((elapsedMs * pendingCalls) / doneCalls / 1000));
            } else {
              const waves = Math.ceil(totalCalls / 3);
              estSec = waves * 15 + 8;
            }

            const percent = totalCalls > 0
              ? Math.min(99, Math.round((doneCalls / totalCalls) * 100))
              : 0;

            // partial.variants 中 listing.title 非空者视为"已生成可展示"
            const readyVariants = (partial?.variants || []).filter(
              (v: any) => v?.listing?.title && String(v.listing.title).trim().length > 0,
            );

            return (
              <Card style={{ borderRadius: 14, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', padding: isMulti ? 24 : 60, textAlign: isMulti ? 'left' : 'center' }}>
                {!isMulti ? (
                  <>
                    <div style={{ textAlign: 'center' }}>
                      <Spin size="large" />
                    </div>
                    <div style={{ marginTop: 20, textAlign: 'center' }}>
                      <Text type="secondary" style={{ fontSize: 15 }}>
                        AI 正在优化 Listing，预计需要 25-50 秒...
                      </Text>
                    </div>
                  </>
                ) : (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
                      <Spin />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <Text strong style={{ fontSize: 15 }}>
                          AI 正在并行生成 {total} 份候选 Listing 并进行四维评分择优
                        </Text>
                        <div style={{ marginTop: 6, fontSize: 12, color: '#6B7280' }}>
                          已生成 <strong style={{ color: '#2563EB' }}>{generated}/{total}</strong>
                          <span style={{ margin: '0 8px' }}>·</span>
                          已评分 <strong style={{ color: '#16A34A' }}>{evaluated}/{total}</strong>
                          <span style={{ margin: '0 8px' }}>·</span>
                          预计剩余 <strong style={{ color: '#B45309' }}>{estSec}</strong> 秒
                          <span style={{ margin: '0 8px' }}>·</span>
                          已用时 {Math.round(elapsedMs / 1000)} 秒
                        </div>
                      </div>
                    </div>
                    <Progress
                      percent={percent}
                      size="small"
                      status="active"
                      strokeColor={{ from: '#3B82F6', to: '#10B981' }}
                      style={{ marginBottom: 20 }}
                    />
                    {readyVariants.length > 0 ? (
                      <>
                        <div style={{ fontSize: 12, color: '#6B7280', marginBottom: 10 }}>
                          已完成候选（{readyVariants.length} 份，正在陆续评分中）：
                        </div>
                        <div style={{ display: 'flex', gap: 16, overflowX: 'auto', padding: '0 0 8px', alignItems: 'flex-start' }}>
                          {readyVariants.map((v: any, i: number) => {
                            const rv: RefineVersion = {
                              optimized: v.listing,
                              feedback: '',
                              variant: v,
                              variantRank: i + 1,
                              variantTotal: total,
                            };
                            return (
                              <VersionCard
                                key={`partial-${v.variant_index}`}
                                version={rv}
                                index={i}
                                asin={asin || product?.asin || ''}
                                marketplace={marketplace || product?.marketplace || 'US'}
                                selectedKeywords={selectedTrafficWords}
                                trafficWords={discoveredTrafficWords}
                                searchLibWords={searchLibSelectedWords}
                                productContext={product || optimizeResult?.original || null}
                                reviewAnalysis={reviewAnalysis}
                                competitorProducts={selectedCompetitorProducts}
                              />
                            );
                          })}
                        </div>
                      </>
                    ) : (
                      <div style={{ fontSize: 12, color: '#9CA3AF', textAlign: 'center', padding: '20px 0' }}>
                        首个候选生成后将在此处实时显示 · 你可以先切到其他页面继续工作
                      </div>
                    )}
                  </>
                )}
              </Card>
            );
          })()}

          {/* 诊断中 loading */}
          {activeTab === 'analyze' && analyzeRunning && (
            <Card style={{
              borderRadius: 12,
              border: '1px solid rgba(83, 210, 255, 0.22)',
              background: 'linear-gradient(135deg, rgba(4, 14, 32, 0.94), rgba(6, 26, 44, 0.88))',
              boxShadow: '0 18px 44px rgba(0, 0, 0, 0.24), inset 0 0 24px rgba(34, 211, 238, 0.05)',
              marginBottom: 16,
            }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 14 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: '50%', display: 'grid', placeItems: 'center',
                  border: '1px solid rgba(71, 231, 255, 0.54)',
                  boxShadow: '0 0 28px rgba(0, 229, 255, 0.32)',
                  background: 'radial-gradient(circle at 35% 30%, rgba(34, 211, 238, 0.24), rgba(3, 13, 28, 0.96))',
                }}>
                  <Spin size="small" />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text strong style={{ color: '#e6fbff', fontSize: 15 }}>Listing 诊断链路观察</Text>
                  <div style={{ marginTop: 6, fontSize: 12, color: '#93b8c7', lineHeight: 1.7 }}>
                    当前状态 <strong style={{ color: '#25e7ff' }}>{analyzeTaskInfo?.status || 'running'}</strong>
                    <span style={{ margin: '0 8px' }}>·</span>
                    已用时 <strong style={{ color: '#bdefff' }}>{Math.max(1, Math.round(analyzeElapsedMs / 1000))}</strong> 秒
                    <span style={{ margin: '0 8px' }}>·</span>
                    {selectedCompetitorProducts.length >= AUTO_COMPETITOR_LIMIT ? '已带入 5 条竞品进入对比' : '正在补齐竞品并生成对比诊断'}
                  </div>
                </div>
              </div>
              <Progress
                percent={analyzeTaskInfo?.status === 'running' ? 68 : 35}
                size="small"
                status="active"
                showInfo={false}
                strokeColor={{ from: '#22D3EE', to: '#3B82F6' }}
                trailColor="rgba(122, 205, 232, 0.12)"
                style={{ marginBottom: 14 }}
              />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
                {[
                  ['资料读取', product?.title ? '已就绪' : '补齐中'],
                  ['竞品对比', selectedCompetitorProducts.length >= AUTO_COMPETITOR_LIMIT ? '已就绪' : '补齐中'],
                  ['报告输出', '生成中'],
                ].map(([label, desc]) => (
                  <div key={label} style={{
                    padding: '10px 12px',
                    borderRadius: 8,
                    border: '1px solid rgba(122, 205, 232, 0.18)',
                    background: 'rgba(4, 18, 31, 0.72)',
                  }}>
                    <div style={{ color: '#dff7ff', fontSize: 12, fontWeight: 800 }}>{label}</div>
                    <div style={{ color: '#7faec1', fontSize: 11, marginTop: 4 }}>{desc}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* 优化结果 */}
          {!optimizeRunning && optimizeResult && activeTab === 'optimize' && (() => {
            const isMultiVariant = refineVersions.some(v => !!v.variant && (v.variantTotal ?? 0) > 1);
            return (
              <>
                {isMultiVariant && (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 12, borderRadius: 10 }}
                    message={
                      <span>
                        已并行生成 <strong>{refineVersions.length}</strong> 份候选。每份候选会同时产出
                        <Tag color="blue" style={{ margin: '0 4px' }}>曝光评分</Tag>
                        与 <Tag color="purple" style={{ margin: '0 4px' }}>转化评分</Tag>，
                        按三维诊断命中情况加权得到
                        <Tag color="geekblue" style={{ margin: '0 4px' }}>综合分</Tag>，
                        带 <Tag color="gold" style={{ margin: '0 4px' }}>★ 最优候选</Tag> 的为综合分最高的文案。
                      </span>
                    }
                  />
                )}
                {isMultiVariant && optimizeResult.tri_dim_hit && (
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 12, borderRadius: 10 }}
                    message={
                      <span style={{ fontSize: 13 }}>
                        <strong>本次加权规则：</strong>
                        {optimizeResult.tri_dim_hit.rule}
                        <span style={{ marginLeft: 8, color: '#6b7280' }}>
                          （曝光 {(optimizeResult.tri_dim_hit.weight_expose * 10).toFixed(0)} : 转化 {(optimizeResult.tri_dim_hit.weight_conversion * 10).toFixed(0)}）
                        </span>
                        <span style={{ marginLeft: 12, fontSize: 12, color: '#6b7280' }}>
                          流量下降命中: {optimizeResult.tri_dim_hit.sessions_decline ? '是' : '否'} /
                          CTR 低: {optimizeResult.tri_dim_hit.ctr_low ? '是' : '否'} /
                          CVR 低: {optimizeResult.tri_dim_hit.cvr_low ? '是' : '否'}
                        </span>
                      </span>
                    }
                  />
                )}
                <div style={{ display: 'flex', gap: 16, overflowX: 'auto', padding: '8px 0 16px', alignItems: 'flex-start' }}>
                  {refineVersions.map((v, i) => (
                    <VersionCard key={i} version={v} index={i}
                      asin={optimizeResult.asin} marketplace={optimizeResult.marketplace}
                      selectedKeywords={selectedTrafficWords}
                      trafficWords={discoveredTrafficWords}
                      searchLibWords={searchLibSelectedWords}
                      productContext={product || optimizeResult.original || null}
                      reviewAnalysis={reviewAnalysis}
                      competitorProducts={selectedCompetitorProducts}
                    />
                  ))}
                  {refineVersions.length > 0 && !isMultiVariant && (
                    <RefinePanel
                      asin={optimizeResult.asin} marketplace={optimizeResult.marketplace}
                      versions={refineVersions} onNewVersion={v => setRefineVersions(prev => [...prev, v])}
                      sessionId={sessionId} selectedModel={selectedModel}
                    />
                  )}
                </div>
              </>
            );
          })()}

          {/* 诊断结果 */}
          {!analyzeRunning && deepDiagnosticResult && activeTab === 'analyze' && (
            <DeepDiagnosticResultCard data={deepDiagnosticResult} />
          )}
        </Col>
      </Row>
      </>
      )}

      {/* ── 三维数据诊断 Drawer ── */}
      <Drawer
        title={
          <Space>
            <BarChartOutlined style={{ color: RAINBOW[3].from }} />
            <span>三维数据诊断 - {asin || 'N/A'}</span>
            {triDimTotal2 > 0 && <Tag color="red">{triDimTotal2} 条记录</Tag>}
          </Space>
        }
        open={triDimOpen}
        onClose={() => setTriDimOpen(false)}
        width={Math.min(window.innerWidth * 0.85, 1200)}
        destroyOnClose
      >
        {triDimLoading && !triDimResult && (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" />
            <div style={{ marginTop: 16 }}><Text type="secondary">正在查询数据库，分析 CTR/CVR/流量趋势...</Text></div>
          </div>
        )}
        {triDimError && <Alert message="查询失败" description={triDimError} type="error" showIcon style={{ marginBottom: 16 }} />}
        {triDimResult && (
          <div>
            {triDimResult.row_count === 0 && triDimTotal2 === 0 ? (
              <Alert message="该 ASIN 未命中任何诊断维度" description="产品各项指标均在正常范围内，无需特别优化。" type="success" showIcon />
            ) : (
              <TriDimTable
                data={triDimResult}
                loading={triDimLoading}
                total={triDimTotal2}
                current={triDimPage2}
                pageSize={triDimPageSize2}
                onPageChange={(page, ps) => {
                  setTriDimPageSize2(ps);
                  loadTriDimPage(asin.trim(), page, ps);
                }}
              />
            )}
          </div>
        )}
      </Drawer>

      <PromptSettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} promptCfg={promptCfg} />

      {/* ── 细节设置 Drawer（修改意见 / 模型 / FAB / 优化范围 / 候选数量） ── */}
      <Drawer
        title={
          <Space>
            <EditOutlined style={{ color: ACCENT }} />
            <span>细节设置</span>
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              修改意见 / 模型 / FAB / 优化范围 / 候选数量
            </Text>
          </Space>
        }
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        width={Math.min(window.innerWidth * 0.5, 520)}
        destroyOnClose={false}
      >
        {activeTab === 'optimize' && (
          <div style={{ marginBottom: 16 }}>
            <Text strong style={{ fontSize: 13 }}>修改意见</Text>
            <Input.TextArea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="对优化结果的补充说明或特殊要求"
              autoSize={{ minRows: 3, maxRows: 6 }}
              style={{ marginTop: 6, borderRadius: 8 }}
            />
          </div>
        )}

        <div style={{ marginBottom: 16 }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
            优化模型 <span style={{ color: '#9CA3AF' }}>（用于生成候选文案）</span>
          </Text>
          <ModelSelector value={selectedModel} onChange={handleModelChange} style={{ width: '100%' }} />
        </div>

        {activeTab === 'optimize' && variantCount > 1 && (
          <div style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
              评价模型 <span style={{ color: '#9CA3AF' }}>（用于多候选四维打分，留空则与优化模型相同）</span>
            </Text>
            <ModelSelector
              value={selectedEvalModel}
              onChange={handleEvalModelChange}
              style={{ width: '100%' }}
            />
          </div>
        )}

        {activeTab === 'optimize' && (
          <>
            {/* ── FAB 增强模式开关 ── */}
            <div style={{
              marginBottom: 14,
              background: enableFab ? '#f0fdf4' : '#f9fafb',
              border: `1px solid ${enableFab ? '#86efac' : '#e5e7eb'}`,
              borderRadius: 10,
              padding: '10px 14px',
              transition: 'all 0.2s',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <Text style={{ fontSize: 13, fontWeight: 600, color: enableFab ? '#15803d' : '#374151' }}>
                    FAB 增强模式
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 2 }}>
                    {enableFab
                      ? 'COSMO 四维 + FAB 文案结构 + 评论洞察注入'
                      : '标准 SEO 优化（不含 FAB 结构和评论洞察注入）'}
                  </Text>
                </div>
                <Switch
                  checked={enableFab}
                  onChange={setEnableFab}
                  style={enableFab ? { background: '#16a34a' } : {}}
                />
              </div>
            </div>

            <div style={{ marginBottom: 14 }}>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>优化范围</Text>
              <Checkbox.Group
                value={optimizeSections}
                onChange={(vals) => setOptimizeSections(vals as string[])}
                style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 0' }}
              >
                {ALL_SECTIONS.map(k => (
                  <Checkbox key={k} value={k} style={{ marginRight: 12, fontSize: 13 }}>
                    {SEC_LABELS[k]}
                  </Checkbox>
                ))}
              </Checkbox.Group>
            </div>

            {/* ── 候选数量（多候选 + LLM 评分择优） ── */}
            <div style={{
              marginBottom: 14,
              background: variantCount > 1 ? '#fffbeb' : '#f9fafb',
              border: `1px solid ${variantCount > 1 ? '#fcd34d' : '#e5e7eb'}`,
              borderRadius: 10,
              padding: '10px 14px',
              transition: 'all 0.2s',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text style={{ fontSize: 13, fontWeight: 600, color: variantCount > 1 ? '#b45309' : '#374151' }}>
                    候选数量（Best-of-N）
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 2 }}>
                    {variantCount > 1
                      ? `并行生成 ${variantCount} 份候选，LLM 四维评分后自动标注最优（默认 3）`
                      : '仅生成 1 份（关闭 Best-of-N）'}
                  </Text>
                </div>
                <InputNumber
                  min={1}
                  max={10}
                  value={variantCount}
                  onChange={(v) => {
                    const n = Math.max(1, Math.min(10, Math.round(Number(v) || 1)));
                    setVariantCount(n);
                  }}
                  size="small"
                  style={{ width: 64, flexShrink: 0 }}
                />
              </div>
            </div>
          </>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 24, gap: 8 }}>
          <Button onClick={() => setDetailsOpen(false)}>关闭</Button>
        </div>
      </Drawer>
    </div>
  );
}
