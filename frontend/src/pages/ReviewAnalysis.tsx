import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Card, Button, Input, Typography, Tag, Spin, message, Space,
  Upload, Row, Col, Divider, Tooltip, Select, Empty,
} from 'antd';
import {
  SearchOutlined, UploadOutlined, ThunderboltOutlined,
  FrownOutlined, SmileOutlined, StarOutlined, BulbOutlined,
  InfoCircleOutlined, ExperimentOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import { type ReviewItem, type ReviewAnalysisResult } from '../api';
import { useModels } from '../hooks/useModels';
import { useTaskManager } from '../context/TaskContext';

const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;

const FREQ_COLOR: Record<string, string> = { high: '#f5222d', medium: '#fa8c16', low: '#8c8c8c' };
const FREQ_LABEL: Record<string, string> = { high: '高频', medium: '中频', low: '低频' };
const SENTIMENT_MAP: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  positive: { color: '#52c41a', icon: <SmileOutlined />, label: '正面' },
  negative: { color: '#f5222d', icon: <FrownOutlined />, label: '负面' },
  neutral: { color: '#8c8c8c', icon: <InfoCircleOutlined />, label: '中性' },
  mixed: { color: '#fa8c16', icon: <ExperimentOutlined />, label: '混合' },
};

function parseUploadedReviews(text: string): ReviewItem[] {
  const lines = text.split('\n').filter(l => l.trim());
  return lines.map(line => {
    const starsMatch = line.match(/^(\d(?:\.\d)?)\s*[★☆]?\s*/);
    const stars = starsMatch ? parseFloat(starsMatch[1]) : 0;
    const body = starsMatch ? line.slice(starsMatch[0].length).trim() : line.trim();
    return { stars, title: '', body, date: '' };
  });
}

/* ── 缓存：参照 ListingOptimize 模式，每个字段独立键 ── */
const CK = 'ra_cache';
const CK_FORM = CK + '_form';       // { asin, marketplace, productTitle, selectedModel }
const CK_REVIEWS = CK + '_reviews';  // ReviewItem[]
const CK_RESULT = CK + '_result';    // ReviewAnalysisResult
const CK_TASK = CK + '_task_id';     // string (分析任务)
const CK_FETCH_TASK = CK + '_fetch_task_id'; // string (抓取任务)

function ssGet<T>(key: string, fallback: T): T {
  try { const r = sessionStorage.getItem(key); return r ? JSON.parse(r) : fallback; } catch { return fallback; }
}
function ssSet(key: string, val: unknown) {
  try { sessionStorage.setItem(key, JSON.stringify(val)); } catch {}
}
function ssSetRaw(key: string, val: string) {
  try { sessionStorage.setItem(key, val); } catch {}
}
function ssRm(key: string) { try { sessionStorage.removeItem(key); } catch {} }

export default function ReviewAnalysis() {
  const { models } = useModels();
  const { submitTask, tasks } = useTaskManager();

  /* ── 表单：从缓存初始化 ── */
  const [asin, setAsin] = useState(() => ssGet<any>(CK_FORM, {}).asin || '');
  const [marketplace, setMarketplace] = useState(() => ssGet<any>(CK_FORM, {}).marketplace || 'US');
  const [productTitle, setProductTitle] = useState(() => ssGet<any>(CK_FORM, {}).productTitle || '');
  const [selectedModel, setSelectedModel] = useState(() => ssGet<any>(CK_FORM, {}).selectedModel || '');

  /* ── 评论列表：从缓存初始化 ── */
  const [reviews, setReviews] = useState<ReviewItem[]>(() => ssGet<ReviewItem[]>(CK_REVIEWS, []));
  const [manualText, setManualText] = useState('');
  const [fetching, setFetching] = useState(() => !!sessionStorage.getItem(CK_FETCH_TASK));
  const [fetchTaskId, setFetchTaskId] = useState<string | null>(
    () => { try { return sessionStorage.getItem(CK_FETCH_TASK) || null; } catch { return null; } },
  );

  /* ── 分析任务：从缓存初始化 ── */
  const [analysisTaskId, setAnalysisTaskId] = useState<string | null>(
    () => { try { return sessionStorage.getItem(CK_TASK) || null; } catch { return null; } },
  );
  const [analyzing, setAnalyzing] = useState(() => !!sessionStorage.getItem(CK_TASK));
  const [result, setResult] = useState<ReviewAnalysisResult | null>(() => ssGet<ReviewAnalysisResult | null>(CK_RESULT, null));

  /* ── 缓存写入 ── */
  useEffect(() => {
    ssSet(CK_FORM, { asin, marketplace, productTitle, selectedModel });
  }, [asin, marketplace, productTitle, selectedModel]);

  useEffect(() => {
    ssSet(CK_REVIEWS, reviews);
  }, [reviews]);

  useEffect(() => {
    if (result) ssSet(CK_RESULT, result);
  }, [result]);

  /* ── 监听评论抓取后台任务 ── */
  useEffect(() => {
    if (!fetchTaskId) return;
    const t = tasks.get(fetchTaskId);
    if (!t) {
      setFetching(false);
      setFetchTaskId(null);
      ssRm(CK_FETCH_TASK);
      return;
    }
    if (t.status === 'completed' && t.result) {
      const data = t.result as any;
      const fetched: ReviewItem[] = data.reviews || [];
      if (fetched.length) {
        setReviews(prev => [...prev, ...fetched]);
        message.success(`抓取到 ${fetched.length} 条评论`);
      } else {
        message.info('未抓取到评论，请检查 ASIN 或手动输入');
      }
      if (data.title) setProductTitle(data.title);
      setFetching(false);
      setFetchTaskId(null);
      ssRm(CK_FETCH_TASK);
    } else if (t.status === 'failed') {
      message.error(t.error || '抓取失败');
      setFetching(false);
      setFetchTaskId(null);
      ssRm(CK_FETCH_TASK);
    } else if (t.status === 'pending' || t.status === 'running') {
      setFetching(true);
    }
  }, [tasks, fetchTaskId]);

  /* ── 监听分析后台任务 ── */
  useEffect(() => {
    if (!analysisTaskId) return;
    const t = tasks.get(analysisTaskId);
    if (!t) {
      setAnalyzing(false);
      setAnalysisTaskId(null);
      ssRm(CK_TASK);
      return;
    }
    if (t.status === 'completed' && t.result) {
      const analysis = (t.result as any).analysis;
      if (analysis) {
        setResult(analysis);
        ssSet(CK_RESULT, analysis);
        message.success('分析完成');
      } else if ((t.result as any).error) {
        message.error((t.result as any).error);
      }
      setAnalyzing(false);
      setAnalysisTaskId(null);
      ssRm(CK_TASK);
    } else if (t.status === 'failed') {
      setAnalyzing(false);
      setAnalysisTaskId(null);
      ssRm(CK_TASK);
      message.error(t.error || '分析失败');
    } else if (t.status === 'pending' || t.status === 'running') {
      setAnalyzing(true);
    }
  }, [tasks, analysisTaskId]);

  const handleFetchReviews = async () => {
    if (!asin || asin.length !== 10) {
      message.warning('请输入有效的 10 位 ASIN');
      return;
    }
    setFetching(true);
    try {
      const tid = await submitTask(
        'fetch_reviews' as any,
        { asin, marketplace },
        { asin, marketplace },
      );
      setFetchTaskId(tid);
      ssSetRaw(CK_FETCH_TASK, tid);
    } catch (e: any) {
      setFetching(false);
      message.error(e.message || '提交失败');
    }
  };

  const handleAddManual = () => {
    const parsed = parseUploadedReviews(manualText);
    if (!parsed.length) {
      message.warning('未解析到有效评论');
      return;
    }
    setReviews(prev => [...prev, ...parsed]);
    setManualText('');
    message.success(`已添加 ${parsed.length} 条评论`);
  };

  const handleUpload = (file: UploadFile) => {
    const reader = new FileReader();
    reader.onload = e => {
      const text = e.target?.result as string;
      if (!text) return;
      const parsed = parseUploadedReviews(text);
      setReviews(prev => [...prev, ...parsed]);
      message.success(`从文件导入 ${parsed.length} 条评论`);
    };
    reader.readAsText(file.originFileObj as File);
    return false;
  };

  const handleAnalyze = useCallback(async () => {
    if (!reviews.length) {
      message.warning('请先添加评论');
      return;
    }
    setAnalyzing(true);
    setResult(null);
    try {
      const tid = await submitTask('review_analysis' as any, {
        asin, marketplace, product_title: productTitle,
        reviews, model: selectedModel || '',
      }, { asin: asin || 'manual', marketplace });
      setAnalysisTaskId(tid);
      ssSetRaw(CK_TASK, tid);
    } catch (e: any) {
      setAnalyzing(false);
      message.error(e.message || '提交失败');
    }
  }, [reviews, asin, marketplace, productTitle, selectedModel, submitTask]);

  const handleClear = () => {
    setReviews([]);
    setResult(null);
    ssRm(CK_REVIEWS);
    ssRm(CK_RESULT);
  };

  const modelOptions = useMemo(() =>
    models.map(m => ({ label: m.provider_name ? `${m.provider_name} / ${m.model}` : m.model, value: m.id })),
    [models],
  );

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>
          <BulbOutlined style={{ marginRight: 8 }} />评论分析
        </Title>
        <Text type="secondary">从用户评论中提取痛点、卖点和核心特点</Text>
      </div>

      <Row gutter={16}>
        {/* 左侧：评论输入 */}
        <Col xs={24} lg={10}>
          <Card size="small" title="评论来源" style={{ marginBottom: 16, borderRadius: 12 }}>
            {/* 抓取 */}
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 12 }}>从 Amazon 抓取</Text>
              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <Input size="small" placeholder="ASIN（10位）" value={asin}
                  onChange={e => setAsin(e.target.value.toUpperCase())} style={{ flex: 1 }}
                  maxLength={10} />
                <Select size="small" value={marketplace} onChange={setMarketplace}
                  style={{ width: 80 }}
                  options={['US','UK','DE','JP','CA','FR','IT','ES','AU','MX'].map(v => ({ label: v, value: v }))} />
                <Button size="small" type="primary" icon={<SearchOutlined />}
                  loading={fetching} onClick={handleFetchReviews}>抓取</Button>
              </div>
            </div>

            <Divider style={{ margin: '12px 0' }} />

            {/* 手动输入 */}
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 12 }}>手动输入</Text>
              <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
                每行一条评论，可选格式: "4.5 评论内容"
              </Text>
              <TextArea rows={4} value={manualText} onChange={e => setManualText(e.target.value)}
                placeholder={'5 Great product, love it!\n2 Poor quality, broke in a week\n4 Good value for the price'}
                style={{ fontSize: 12 }} />
              <Button size="small" style={{ marginTop: 4 }} onClick={handleAddManual}
                disabled={!manualText.trim()}>添加</Button>
            </div>

            <Divider style={{ margin: '12px 0' }} />

            {/* 文件上传 */}
            <Upload accept=".txt,.csv" showUploadList={false} beforeUpload={() => false}
              onChange={({ file }) => handleUpload(file)}>
              <Button size="small" icon={<UploadOutlined />}>上传文件 (.txt/.csv)</Button>
            </Upload>
          </Card>

          {/* 评论列表 */}
          <Card size="small" title={`评论列表 (${reviews.length} 条)`}
            extra={reviews.length > 0 && <Button size="small" danger type="text"
              onClick={handleClear}>清空</Button>}
            style={{ marginBottom: 16, borderRadius: 12 }}>
            {!reviews.length ? (
              <Empty description="暂无评论" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <div style={{ maxHeight: 400, overflow: 'auto' }}>
                {reviews.map((rv, i) => (
                  <div key={i} style={{
                    padding: '6px 8px', borderBottom: '1px solid #f0f0f0', fontSize: 12,
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: '#FAAD14' }}>
                        {'★'.repeat(Math.round(rv.stars))}{'☆'.repeat(5 - Math.round(rv.stars))}
                        <span style={{ color: '#8c8c8c', marginLeft: 4 }}>{rv.stars}</span>
                      </span>
                      <Text type="secondary" style={{ fontSize: 10 }}>[{i}] {rv.date}</Text>
                    </div>
                    {rv.title && <div style={{ fontWeight: 600, marginTop: 2 }}>{rv.title}</div>}
                    {rv.body && <div style={{ color: '#595959', marginTop: 2, lineHeight: 1.5 }}>{rv.body.slice(0, 200)}{rv.body.length > 200 ? '...' : ''}</div>}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* 分析按钮 */}
          <Card size="small" style={{ borderRadius: 12 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Input size="small" placeholder="产品标题（可选，提升分析精度）" value={productTitle}
                onChange={e => setProductTitle(e.target.value)} style={{ flex: 1 }} />
              {modelOptions.length > 0 && (
                <Select size="small" placeholder="模型" allowClear value={selectedModel || undefined}
                  onChange={v => setSelectedModel(v || '')} options={modelOptions}
                  style={{ width: 160 }} />
              )}
              <Button type="primary" icon={<ThunderboltOutlined />} loading={analyzing}
                disabled={!reviews.length} onClick={handleAnalyze}>
                分析 ({reviews.length})
              </Button>
            </div>
          </Card>
        </Col>

        {/* 右侧：分析结果 */}
        <Col xs={24} lg={14}>
          {analyzing && (
            <Card style={{ borderRadius: 12, textAlign: 'center', padding: 40 }}>
              <Spin size="large" />
              <div style={{ marginTop: 16 }}>
                <Text type="secondary">正在分析 {reviews.length} 条评论（可切换页面，任务不会丢失）...</Text>
              </div>
            </Card>
          )}

          {result && !analyzing && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* 综合摘要 */}
              <Card size="small" style={{ borderRadius: 12, background: '#FAFAFA' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <Title level={5} style={{ margin: 0 }}>综合分析</Title>
                  {result.overall_sentiment && (() => {
                    const s = SENTIMENT_MAP[result.overall_sentiment] || SENTIMENT_MAP.neutral;
                    return <Tag color={s.color} icon={s.icon}>{s.label}</Tag>;
                  })()}
                </div>
                <Paragraph style={{ fontSize: 13, lineHeight: 1.8, margin: 0 }}>
                  {result.summary}
                </Paragraph>
              </Card>

              {/* 痛点 */}
              <Card size="small" title={
                <Space><FrownOutlined style={{ color: '#f5222d' }} /><span>用户痛点 ({result.pain_points.length})</span></Space>
              } style={{ borderRadius: 12, borderLeft: '4px solid #f5222d' }}>
                {result.pain_points.map((p, i) => (
                  <div key={i} style={{ padding: '8px 0', borderBottom: i < result.pain_points.length - 1 ? '1px solid #f5f5f5' : 'none' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Tag style={{ fontSize: 11 }}>{i + 1}</Tag>
                      <Text strong style={{ fontSize: 13 }}>{p.title}</Text>
                      <Tag color={FREQ_COLOR[p.frequency]} style={{ fontSize: 10 }}>{FREQ_LABEL[p.frequency] || p.frequency}</Tag>
                    </div>
                    <div style={{ fontSize: 12, color: '#595959', marginTop: 4, paddingLeft: 32, lineHeight: 1.6 }}>
                      {p.detail}
                    </div>
                    {p.related_reviews.length > 0 && (
                      <div style={{ paddingLeft: 32, marginTop: 4 }}>
                        {p.related_reviews.map(idx => (
                          <Tooltip key={idx} title={reviews[idx]?.body?.slice(0, 200) || ''}>
                            <Tag style={{ cursor: 'pointer', fontSize: 10 }}>评论[{idx}]</Tag>
                          </Tooltip>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {!result.pain_points.length && <Text type="secondary">未发现明显痛点</Text>}
              </Card>

              {/* 卖点 */}
              <Card size="small" title={
                <Space><SmileOutlined style={{ color: '#52c41a' }} /><span>产品卖点 ({result.selling_points.length})</span></Space>
              } style={{ borderRadius: 12, borderLeft: '4px solid #52c41a' }}>
                {result.selling_points.map((p, i) => (
                  <div key={i} style={{ padding: '8px 0', borderBottom: i < result.selling_points.length - 1 ? '1px solid #f5f5f5' : 'none' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Tag style={{ fontSize: 11 }}>{i + 1}</Tag>
                      <Text strong style={{ fontSize: 13 }}>{p.title}</Text>
                      <Tag color={FREQ_COLOR[p.frequency]} style={{ fontSize: 10 }}>{FREQ_LABEL[p.frequency] || p.frequency}</Tag>
                    </div>
                    <div style={{ fontSize: 12, color: '#595959', marginTop: 4, paddingLeft: 32, lineHeight: 1.6 }}>
                      {p.detail}
                    </div>
                    {p.related_reviews.length > 0 && (
                      <div style={{ paddingLeft: 32, marginTop: 4 }}>
                        {p.related_reviews.map(idx => (
                          <Tooltip key={idx} title={reviews[idx]?.body?.slice(0, 200) || ''}>
                            <Tag style={{ cursor: 'pointer', fontSize: 10 }}>评论[{idx}]</Tag>
                          </Tooltip>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {!result.selling_points.length && <Text type="secondary">未发现明显卖点</Text>}
              </Card>

              {/* 核心特点 */}
              <Card size="small" title={
                <Space><StarOutlined style={{ color: '#1890ff' }} /><span>核心特点 ({result.core_features.length})</span></Space>
              } style={{ borderRadius: 12, borderLeft: '4px solid #1890ff' }}>
                {result.core_features.map((f, i) => {
                  const s = SENTIMENT_MAP[f.sentiment] || SENTIMENT_MAP.neutral;
                  return (
                    <div key={i} style={{ padding: '8px 0', borderBottom: i < result.core_features.length - 1 ? '1px solid #f5f5f5' : 'none' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Tag style={{ fontSize: 11 }}>{i + 1}</Tag>
                        <Text strong style={{ fontSize: 13 }}>{f.title}</Text>
                        <Tag color={s.color} icon={s.icon} style={{ fontSize: 10 }}>{s.label}</Tag>
                      </div>
                      <div style={{ fontSize: 12, color: '#595959', marginTop: 4, paddingLeft: 32, lineHeight: 1.6 }}>
                        {f.detail}
                      </div>
                    </div>
                  );
                })}
                {!result.core_features.length && <Text type="secondary">未发现核心特点</Text>}
              </Card>
            </div>
          )}

          {!result && !analyzing && (
            <Card style={{ borderRadius: 12, textAlign: 'center', padding: 60 }}>
              <BulbOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
              <div style={{ marginTop: 16 }}>
                <Text type="secondary">添加评论后点击"分析"查看结果</Text>
              </div>
            </Card>
          )}
        </Col>
      </Row>
    </div>
  );
}
