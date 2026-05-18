import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Alert, Button, Card, Col, Empty, Image, Input, InputNumber, Row, Select,
  Space, Spin, Statistic, Switch, Table, Tag, Typography, message,
} from 'antd';
import {
  BarChartOutlined, BulbOutlined, DollarOutlined, FireOutlined, LinkOutlined,
  RadarChartOutlined, SearchOutlined, ShopOutlined, StarOutlined,
} from '@ant-design/icons';
import { type MarketAnalysisResponse, type MarketProductItem } from '../api';
import { useTaskManager } from '../context/TaskContext';

const { Text, Title, Paragraph } = Typography;

const CK = 'market_analysis_cache';
const CK_FORM = CK + '_form';
const CK_RESULT = CK + '_result';
const CK_TASK = CK + '_task_id';

function ssGet<T>(key: string, fallback: T): T {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function ssSet(key: string, value: unknown) {
  try { sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
}

function ssSetRaw(key: string, value: string) {
  try { sessionStorage.setItem(key, value); } catch { /* ignore */ }
}

function ssRm(key: string) {
  try { sessionStorage.removeItem(key); } catch { /* ignore */ }
}

function InsightBlock({ title, icon, items, color }: {
  title: string;
  icon: ReactNode;
  items: string[];
  color: string;
}) {
  return (
    <Card size="small" title={<Space>{icon}<span>{title}</span></Space>} style={{ height: '100%' }}>
      {items?.length ? (
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          {items.slice(0, 8).map((item, idx) => (
            <div key={`${title}-${idx}`} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <Tag color={color} style={{ margin: 0 }}>{idx + 1}</Tag>
              <Text style={{ fontSize: 13 }}>{item}</Text>
            </div>
          ))}
        </Space>
      ) : (
        <Text type="secondary">暂无</Text>
      )}
    </Card>
  );
}

export default function MarketAnalysis() {
  const { submitTask, tasks } = useTaskManager();
  const formCache = ssGet<any>(CK_FORM, {});

  const [keyword, setKeyword] = useState(formCache.keyword || '地毯');
  const [marketplace, setMarketplace] = useState(formCache.marketplace || 'US');
  const [maxResults, setMaxResults] = useState(formCache.maxResults || 40);
  const [maxPages, setMaxPages] = useState(formCache.maxPages || 2);
  const [withDetails, setWithDetails] = useState(
    typeof formCache.withDetails === 'boolean' ? formCache.withDetails : true,
  );

  const [taskId, setTaskId] = useState<string | null>(() => {
    try { return sessionStorage.getItem(CK_TASK) || null; } catch { return null; }
  });
  const [loading, setLoading] = useState(() => !!sessionStorage.getItem(CK_TASK));
  const [result, setResult] = useState<MarketAnalysisResponse | null>(
    () => ssGet<MarketAnalysisResponse | null>(CK_RESULT, null),
  );

  useEffect(() => {
    ssSet(CK_FORM, { keyword, marketplace, maxResults, maxPages, withDetails });
  }, [keyword, marketplace, maxResults, maxPages, withDetails]);

  useEffect(() => {
    if (result) ssSet(CK_RESULT, result);
  }, [result]);

  useEffect(() => {
    if (!taskId) return;
    const t = tasks.get(taskId);
    if (!t) {
      setLoading(false);
      setTaskId(null);
      ssRm(CK_TASK);
      return;
    }
    if (t.status === 'completed' && t.result) {
      const r = t.result as MarketAnalysisResponse;
      setResult(r);
      ssSet(CK_RESULT, r);
      setLoading(false);
      setTaskId(null);
      ssRm(CK_TASK);
      message.success('市场分析完成');
    } else if (t.status === 'failed') {
      setLoading(false);
      setTaskId(null);
      ssRm(CK_TASK);
      message.error(t.error || '市场分析失败');
    } else if (t.status === 'pending' || t.status === 'running') {
      setLoading(true);
    }
  }, [tasks, taskId]);

  const handleAnalyze = useCallback(async () => {
    const k = keyword.trim();
    if (!k) {
      message.warning('请输入统计方向');
      return;
    }
    setLoading(true);
    setResult(null);
    ssRm(CK_RESULT);
    try {
      const tid = await submitTask('market_analysis', {
        keyword: k,
        marketplace,
        max_results: maxResults,
        max_pages: maxPages,
        with_details: withDetails,
      }, { asin: k, marketplace });
      setTaskId(tid);
      ssSetRaw(CK_TASK, tid);
    } catch (e: any) {
      setLoading(false);
      message.error(e.message || '提交失败');
    }
  }, [keyword, marketplace, maxResults, maxPages, withDetails, submitTask]);

  const productColumns = useMemo(() => [
    {
      title: '商品样本',
      key: 'product',
      render: (_: any, r: MarketProductItem) => (
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          {r.image ? (
            <Image src={r.image} width={52} height={52}
              style={{ objectFit: 'contain', border: '1px solid #eef1f5', borderRadius: 6 }}
              preview={{ mask: '放大' }} />
          ) : (
            <div style={{ width: 52, height: 52, background: '#f5f7fa', borderRadius: 6 }} />
          )}
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12, lineHeight: 1.5, wordBreak: 'break-word' }}>{r.title || r.asin}</div>
            <Space size={6} wrap style={{ marginTop: 4 }}>
              <Text copyable={{ text: r.asin }} style={{ fontFamily: 'monospace', fontSize: 11, color: '#7a8795' }}>
                {r.asin}
              </Text>
              {r.brand && <Tag style={{ margin: 0 }}>{r.brand}</Tag>}
              {r.product_url && (
                <Button type="link" size="small" href={r.product_url} target="_blank"
                  icon={<LinkOutlined />} style={{ padding: 0, height: 'auto' }}>
                  Amazon
                </Button>
              )}
            </Space>
          </div>
        </div>
      ),
    },
    {
      title: '价格',
      width: 100,
      align: 'right' as const,
      sorter: (a: MarketProductItem, b: MarketProductItem) => (a.avg_price || 0) - (b.avg_price || 0),
      render: (_: any, r: MarketProductItem) => r.avg_price != null ? (
        <Text strong>{r.avg_price.toFixed(2)} <Text type="secondary">{r.currency}</Text></Text>
      ) : <Text type="secondary">-</Text>,
    },
    {
      title: '评分',
      width: 86,
      align: 'center' as const,
      render: (_: any, r: MarketProductItem) => r.rating ? (
        <Space size={3}><StarOutlined style={{ color: '#faad14' }} /><Text strong>{r.rating}</Text></Space>
      ) : <Text type="secondary">-</Text>,
    },
    {
      title: '评论',
      width: 96,
      align: 'center' as const,
      sorter: (a: MarketProductItem, b: MarketProductItem) =>
        parseInt((a.review_count || '0').replace(/[^\d]/g, ''), 10)
        - parseInt((b.review_count || '0').replace(/[^\d]/g, ''), 10),
      render: (_: any, r: MarketProductItem) => r.review_count || '-',
    },
    {
      title: 'BSR/月销',
      width: 150,
      render: (_: any, r: MarketProductItem) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>{r.bsr_rank || '-'}</Text>
          {r.monthly_sales_text && <Text type="secondary" style={{ fontSize: 11 }}>{r.monthly_sales_text}</Text>}
        </Space>
      ),
    },
  ], []);

  return (
    <div className="market-analysis-page" style={{ padding: 24, maxWidth: 1440, margin: '0 auto' }}>
      <div style={{ marginBottom: 20 }}>
        <Title level={4} style={{ margin: 0 }}>
          <RadarChartOutlined style={{ marginRight: 8 }} />市场分析
        </Title>
        <Text type="secondary">输入统计方向，自动搜索 Amazon 样本并汇总市场容量、头部品牌、评论痛点和切入机会</Text>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[14, 12]} align="middle">
          <Col xs={24} md={8}>
            <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>统计方向</Text>
            <Input value={keyword} onChange={e => setKeyword(e.target.value)}
              onPressEnter={handleAnalyze} placeholder="如：地毯 / 桌垫 / washable rug" />
          </Col>
          <Col xs={12} md={3}>
            <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>站点</Text>
            <Select value={marketplace} onChange={setMarketplace} style={{ width: '100%' }}
              options={['US','UK','DE','JP','CA','FR','IT','ES','AU'].map(v => ({ label: v, value: v }))} />
          </Col>
          <Col xs={12} md={3}>
            <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>样本数</Text>
            <InputNumber min={5} max={100} value={maxResults} onChange={v => setMaxResults(v || 40)}
              style={{ width: '100%' }} />
          </Col>
          <Col xs={12} md={3}>
            <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>搜索页</Text>
            <InputNumber min={1} max={5} value={maxPages} onChange={v => setMaxPages(v || 2)}
              style={{ width: '100%' }} />
          </Col>
          <Col xs={12} md={3}>
            <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>详情评论</Text>
            <Space>
              <Switch checked={withDetails} onChange={setWithDetails} />
              <Text type="secondary">{withDetails ? '开启' : '关闭'}</Text>
            </Space>
          </Col>
          <Col xs={24} md={4} style={{ textAlign: 'right' }}>
            <Button type="primary" icon={<SearchOutlined />} loading={loading}
              onClick={handleAnalyze} disabled={!keyword.trim()}>
              开始分析
            </Button>
          </Col>
        </Row>
      </Card>

      {loading && (
        <Card style={{ textAlign: 'center', padding: 42 }}>
          <Spin size="large" />
          <div style={{ marginTop: 14 }}>
            <Text type="secondary">正在抓取 Amazon 搜索样本、商品详情和评论，请稍候...</Text>
          </div>
        </Card>
      )}

      {result && !loading && (
        <>
          {result.error && <Alert type="warning" message={result.error} showIcon style={{ marginBottom: 16 }} />}

          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} md={6}><Card size="small"><Statistic title="搜索样本" value={result.analyzed_count} suffix={`/ ${result.total_found}`} prefix={<ShopOutlined />} /></Card></Col>
            <Col xs={12} md={6}><Card size="small"><Statistic title="均价" value={result.avg_price ?? 0} precision={2} prefix={<DollarOutlined />} /></Card></Col>
            <Col xs={12} md={6}><Card size="small"><Statistic title="平均评分" value={result.avg_rating ?? 0} precision={2} prefix={<StarOutlined />} /></Card></Col>
            <Col xs={12} md={6}><Card size="small"><Statistic title="样本评论量" value={result.total_reviews} prefix={<BarChartOutlined />} /></Card></Col>
          </Row>

          <Card size="small" style={{ marginBottom: 16 }}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space wrap>
                <Text strong>搜索词</Text>
                {result.search_keywords.map(k => <Tag color="blue" key={k}>{k}</Tag>)}
              </Space>
              <Paragraph style={{ marginBottom: 0 }}>{result.insight.summary}</Paragraph>
              <Alert type="info" showIcon message={result.insight.market_capacity || '市场容量会基于 Amazon 样本估算，需结合 ABA/SQR/广告数据复核。'} />
            </Space>
          </Card>

          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} lg={12}>
              <InsightBlock title="最火方向" icon={<FireOutlined style={{ color: '#ff4d4f' }} />}
                items={result.insight.hot_directions} color="red" />
            </Col>
            <Col xs={24} lg={12}>
              <InsightBlock title="评论缺点" icon={<BulbOutlined style={{ color: '#faad14' }} />}
                items={result.insight.review_pain_points} color="orange" />
            </Col>
            <Col xs={24} lg={12}>
              <InsightBlock title="可切入市场" icon={<ShopOutlined style={{ color: '#1677ff' }} />}
                items={result.insight.accessible_markets} color="blue" />
            </Col>
            <Col xs={24} lg={12}>
              <InsightBlock title="市场风向" icon={<RadarChartOutlined style={{ color: '#52c41a' }} />}
                items={result.insight.market_trends} color="green" />
            </Col>
          </Row>

          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} lg={8}>
              <Card size="small" title="头部品牌">
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  {result.top_brands.length ? result.top_brands.slice(0, 10).map(b => (
                    <div key={b.brand} className="market-brand-row">
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                        <Text strong>{b.brand}</Text>
                        <Text type="secondary" style={{ whiteSpace: 'nowrap' }}>
                          {b.count}款 / {b.total_reviews.toLocaleString()}评
                        </Text>
                      </div>
                      {b.description && (
                        <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.5 }}>
                          {b.description}
                        </Text>
                      )}
                    </div>
                  )) : <Text type="secondary">暂无</Text>}
                </Space>
              </Card>
            </Col>
            <Col xs={24} lg={8}>
              <InsightBlock title="机会建议" icon={<BulbOutlined />} items={result.insight.opportunities} color="cyan" />
            </Col>
            <Col xs={24} lg={8}>
              <InsightBlock title="TK设计师/达人方向" icon={<FireOutlined />} items={result.insight.top_tk_designers} color="purple" />
            </Col>
          </Row>

          <Card size="small" title="商品样本">
            {result.top_products.length ? (
              <Table
                rowKey="asin"
                columns={productColumns}
                dataSource={result.top_products}
                size="middle"
                pagination={{ pageSize: 12, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
              />
            ) : (
              <Empty description="未获取到商品样本" />
            )}
          </Card>
        </>
      )}

      {!result && !loading && (
        <Card style={{ textAlign: 'center', padding: 56 }}>
          <RadarChartOutlined style={{ fontSize: 46, color: '#c9d1dc' }} />
          <div style={{ marginTop: 14 }}>
            <Text type="secondary">输入市场方向后开始分析</Text>
          </div>
        </Card>
      )}
    </div>
  );
}
