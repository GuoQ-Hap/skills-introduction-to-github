import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Card, Button, Input, Typography, Tag, Spin, message, Space,
  Row, Col, Table, Slider, InputNumber, Select, Statistic, Empty,
  Alert, Image, Modal, Descriptions, Checkbox, Switch,
} from 'antd';
import {
  TrophyOutlined, AimOutlined, DollarOutlined,
  StarOutlined, ThunderboltOutlined, EyeOutlined, LoadingOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import { listingApi, type CompetitorItem, type CompetitorDiscoveryResponse, type ProductData } from '../api';
import { useTaskManager } from '../context/TaskContext';

const { Text, Title } = Typography;

const IMG_FALLBACK = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8/+F/PQAJpAN4sKMfFwAAAABJRU5ErkJggg==';

/* ── 缓存：参照 ListingOptimize 模式，每个字段独立键 ── */
const CK = 'cd_cache';
const CK_FORM = CK + '_form';       // { asin, marketplace, priceTolerance, maxResults, withDetails }
const CK_RESULT = CK + '_result';   // CompetitorDiscoveryResponse
const CK_TASK = CK + '_task_id';    // string
const CK_FILTERS = CK + '_filters'; // { colors: string[], sizes: string[], styles: string[] }

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

function getAmazonUrl(asin: string, marketplace: string) {
  const domains: Record<string, string> = {
    US: 'www.amazon.com', UK: 'www.amazon.co.uk', DE: 'www.amazon.de',
    JP: 'www.amazon.co.jp', CA: 'www.amazon.ca', FR: 'www.amazon.fr',
    IT: 'www.amazon.it', ES: 'www.amazon.es', AU: 'www.amazon.com.au',
  };
  return `https://${domains[marketplace] || 'www.amazon.com'}/dp/${asin}`;
}

/* ── 产品详情弹窗 ── */
function ProductDetailModal({ asin, marketplace, open, onClose }: {
  asin: string; marketplace: string; open: boolean; onClose: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [product, setProduct] = useState<ProductData | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open || !asin) return;
    setLoading(true);
    setError('');
    setProduct(null);
    listingApi.fetch({ asin, marketplace }).then(res => {
      const pd = res.data as any;
      if (pd && pd.title) setProduct(pd);
      else if (pd && pd.data && pd.data.title) setProduct(pd.data);
      else setError('未获取到产品数据');
    }).catch(e => setError(e.message || '请求失败')).finally(() => setLoading(false));
  }, [open, asin, marketplace]);

  return (
    <Modal
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingRight: 24 }}>
          <Space><EyeOutlined /><span>{asin} 产品详情</span></Space>
          <Button type="primary" size="small" icon={<LinkOutlined />}
            href={getAmazonUrl(asin, marketplace)} target="_blank">
            在 Amazon 查看
          </Button>
        </div>
      }
      open={open} onCancel={onClose} footer={null}
      width={720} destroyOnClose
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 32 }} />} />
          <div style={{ marginTop: 12 }}><Text type="secondary">正在抓取产品信息...</Text></div>
        </div>
      )}
      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
      {product && (
        <>
          {product.images && product.images.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Image.PreviewGroup>
                  {product.images.map((src, i) => (
                    <Image key={i} src={src} width={80} height={80}
                      style={{ objectFit: 'contain', borderRadius: 6, border: '1px solid #f0f0f0' }}
                      fallback={IMG_FALLBACK} />
                  ))}
                </Image.PreviewGroup>
              </div>
            </div>
          )}
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="标题" span={2}>
              <Text style={{ fontSize: 13, fontWeight: 500 }}>{product.title || '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="品牌">{product.brand || '-'}</Descriptions.Item>
            <Descriptions.Item label="价格">
              {product.price ? `${product.price} ${product.currency || ''}` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="评分">{product.rating || '-'}</Descriptions.Item>
            <Descriptions.Item label="评论数">{product.review_count || '-'}</Descriptions.Item>
            <Descriptions.Item label="类目" span={2}>{product.category || '-'}</Descriptions.Item>
            <Descriptions.Item label="BSR" span={2}>{product.bsr_rank || '-'}</Descriptions.Item>
          </Descriptions>
          {product.bullet_points && product.bullet_points.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <Text strong style={{ fontSize: 12 }}>五点描述</Text>
              <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
                {product.bullet_points.map((bp, i) => (
                  <li key={i} style={{ fontSize: 12, color: '#595959', marginBottom: 3 }}>{bp}</li>
                ))}
              </ul>
            </div>
          )}
          {product.description && (
            <div style={{ marginTop: 12 }}>
              <Text strong style={{ fontSize: 12 }}>产品描述</Text>
              <div style={{ fontSize: 12, color: '#595959', marginTop: 4, lineHeight: 1.6,
                maxHeight: 200, overflow: 'auto' }}>{product.description}</div>
            </div>
          )}
          {product.reviews && product.reviews.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <Text strong style={{ fontSize: 12 }}>评论 ({product.reviews.length} 条)</Text>
              <div style={{ marginTop: 4, maxHeight: 240, overflow: 'auto' }}>
                {product.reviews.map((rv, i) => (
                  <div key={i} style={{ padding: '6px 8px', background: '#fafafa', borderRadius: 6,
                    border: '1px solid #f0f0f0', marginBottom: 6 }}>
                    <div style={{ fontSize: 11 }}>
                      <span style={{ color: '#faad14' }}>{'★'.repeat(Math.round(rv.stars))}</span>
                      <span style={{ color: '#d9d9d9' }}>{'☆'.repeat(5 - Math.round(rv.stars))}</span>
                      {rv.date && <Text type="secondary" style={{ fontSize: 10, marginLeft: 8 }}>{rv.date}</Text>}
                    </div>
                    {rv.title && <div style={{ fontSize: 12, fontWeight: 600, marginTop: 2 }}>{rv.title}</div>}
                    {rv.body && <div style={{ fontSize: 11, color: '#595959', marginTop: 2 }}>{rv.body}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}

export default function CompetitorDiscovery() {
  const { submitTask, tasks } = useTaskManager();

  /* ── 表单：从缓存初始化 ── */
  const [asin, setAsin] = useState(() => ssGet<any>(CK_FORM, {}).asin || '');
  const [marketplace, setMarketplace] = useState(() => ssGet<any>(CK_FORM, {}).marketplace || 'US');
  const [priceTolerance, setPriceTolerance] = useState(() => ssGet<any>(CK_FORM, {}).priceTolerance || 30);
  const [maxResults, setMaxResults] = useState(() => ssGet<any>(CK_FORM, {}).maxResults || 20);
  const [withDetails, setWithDetails] = useState<boolean>(() => {
    const v = ssGet<any>(CK_FORM, {}).withDetails;
    return typeof v === 'boolean' ? v : false;
  });

  /* ── 维度勾选筛选（颜色 / 尺寸 / 款式） ── */
  const [filterColors, setFilterColors] = useState<string[]>(
    () => ssGet<any>(CK_FILTERS, { colors: [] }).colors || [],
  );
  const [filterSizes, setFilterSizes] = useState<string[]>(
    () => ssGet<any>(CK_FILTERS, { sizes: [] }).sizes || [],
  );
  const [filterStyles, setFilterStyles] = useState<string[]>(
    () => ssGet<any>(CK_FILTERS, { styles: [] }).styles || [],
  );

  /* ── 任务 + 结果：从缓存初始化 ── */
  const [taskId, setTaskId] = useState<string | null>(
    () => { try { return sessionStorage.getItem(CK_TASK) || null; } catch { return null; } },
  );
  const [loading, setLoading] = useState(() => !!sessionStorage.getItem(CK_TASK));
  const [result, setResult] = useState<CompetitorDiscoveryResponse | null>(
    () => ssGet<CompetitorDiscoveryResponse | null>(CK_RESULT, null),
  );

  const [detailAsin, setDetailAsin] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);

  /* ── 缓存写入 ── */
  useEffect(() => {
    ssSet(CK_FORM, { asin, marketplace, priceTolerance, maxResults, withDetails });
  }, [asin, marketplace, priceTolerance, maxResults, withDetails]);

  useEffect(() => {
    if (result) ssSet(CK_RESULT, result);
  }, [result]);

  useEffect(() => {
    ssSet(CK_FILTERS, { colors: filterColors, sizes: filterSizes, styles: filterStyles });
  }, [filterColors, filterSizes, filterStyles]);

  /* ── 恢复 / 监听任务状态（统一处理初始化 + 后续变化） ── */
  useEffect(() => {
    if (!taskId) return;
    const t = tasks.get(taskId);
    if (!t) {
      // 任务不在 TaskContext 中（可能已被清理），停止 loading
      setLoading(false);
      setTaskId(null);
      ssRm(CK_TASK);
      return;
    }
    if (t.status === 'completed' && t.result) {
      const r = t.result as CompetitorDiscoveryResponse;
      setResult(r);
      ssSet(CK_RESULT, r);
      setLoading(false);
      setTaskId(null);
      ssRm(CK_TASK);
      if (r.error) message.warning(r.error);
      else message.success(`发现 ${r.total_found} 条竞品`);
    } else if (t.status === 'failed') {
      setLoading(false);
      setTaskId(null);
      ssRm(CK_TASK);
      message.error(t.error || '竞品发现失败');
    } else if (t.status === 'pending' || t.status === 'running') {
      setLoading(true);
    }
  }, [tasks, taskId]);

  const handleDiscover = useCallback(async () => {
    const trimmed = asin.trim().toUpperCase();
    if (trimmed.length !== 10) {
      message.warning('请输入有效的 10 位 ASIN');
      return;
    }
    setLoading(true);
    setResult(null);
    ssRm(CK_RESULT);
    // 新查询：重置维度筛选，避免上一次的勾选误伤新结果
    setFilterColors([]); setFilterSizes([]); setFilterStyles([]);
    try {
      const tid = await submitTask('discover_competitors' as any, {
        asin: trimmed,
        marketplace,
        price_tolerance: priceTolerance / 100,
        max_results: maxResults,
        with_details: withDetails,
      }, { asin: trimmed, marketplace });
      setTaskId(tid);
      ssSetRaw(CK_TASK, tid);
    } catch (e: any) {
      setLoading(false);
      message.error(e.message || '提交失败');
    }
  }, [asin, marketplace, priceTolerance, maxResults, withDetails, submitTask]);

  const openDetail = useCallback((targetAsin: string) => {
    setDetailAsin(targetAsin);
    setDetailOpen(true);
  }, []);

  const columns = useMemo(() => [
    {
      title: '商品', key: 'product',
      render: (_: any, r: CompetitorItem) => (
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          {r.image ? (
            <Image src={r.image} width={52} height={52}
              style={{ objectFit: 'contain', borderRadius: 6, border: '1px solid #f0f0f0', flexShrink: 0 }}
              preview={{ mask: '放大' }} fallback={IMG_FALLBACK} />
          ) : (
            <div style={{ width: 52, height: 52, background: '#f5f5f5', borderRadius: 6, flexShrink: 0 }} />
          )}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, lineHeight: 1.5, whiteSpace: 'normal', wordBreak: 'break-word' as const }}>
              {r.title || r.asin}
            </div>
            <div style={{ marginTop: 4, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <Text copyable={{ text: r.asin }} style={{ fontFamily: 'monospace', fontSize: 11, color: '#8c8c8c' }}>
                {r.asin}
              </Text>
              <Button type="link" size="small" icon={<LinkOutlined />}
                href={getAmazonUrl(r.asin, marketplace)} target="_blank"
                style={{ fontSize: 11, padding: 0, height: 'auto' }}>
                Amazon
              </Button>
              <Button type="link" size="small" icon={<EyeOutlined />}
                onClick={() => openDetail(r.asin)}
                style={{ fontSize: 11, padding: 0, height: 'auto' }}>
                详情
              </Button>
            </div>
          </div>
        </div>
      ),
    },
    {
      title: '价格', dataIndex: 'avg_price', key: 'price', width: 110, align: 'right' as const,
      sorter: (a: CompetitorItem, b: CompetitorItem) => (a.avg_price || 0) - (b.avg_price || 0),
      render: (_: any, r: CompetitorItem) => r.avg_price != null ? (
        <div>
          <Text strong style={{ fontSize: 14 }}>{r.avg_price.toFixed(2)}</Text>
          {r.currency && <Text type="secondary" style={{ fontSize: 10, marginLeft: 3 }}>{r.currency}</Text>}
        </div>
      ) : '-',
    },
    {
      title: '评分', dataIndex: 'rating', key: 'rating', width: 80, align: 'center' as const,
      sorter: (a: CompetitorItem, b: CompetitorItem) => parseFloat(a.rating || '0') - parseFloat(b.rating || '0'),
      render: (v: string) => v ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3 }}>
          <StarOutlined style={{ color: '#faad14', fontSize: 13 }} />
          <Text strong style={{ fontSize: 13 }}>{v}</Text>
        </div>
      ) : <Text type="secondary">-</Text>,
    },
    {
      title: '评论数', dataIndex: 'review_count', key: 'rc', width: 90, align: 'center' as const,
      sorter: (a: CompetitorItem, b: CompetitorItem) =>
        parseInt(a.review_count || '0') - parseInt(b.review_count || '0'),
      render: (v: string) => {
        const n = parseInt(v || '0');
        if (!v || isNaN(n)) return <Text type="secondary">-</Text>;
        const color = n > 1000 ? '#ff4d4f' : n > 500 ? '#fa8c16' : n > 100 ? '#1890ff' : '#8c8c8c';
        return <Text strong style={{ color }}>{n.toLocaleString()}</Text>;
      },
    },
    {
      title: '维度', key: 'dims', width: 180,
      render: (_: any, r: CompetitorItem) => {
        const parts: { label: string; value: string; color: string }[] = [];
        if (r.color) parts.push({ label: '色', value: r.color, color: 'magenta' });
        if (r.size) parts.push({ label: '寸', value: r.size, color: 'geekblue' });
        if (r.style) parts.push({ label: '款', value: r.style, color: 'purple' });
        if (!parts.length) return <Text type="secondary" style={{ fontSize: 11 }}>-</Text>;
        return (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {parts.map(p => (
              <Tag key={p.label + p.value} color={p.color} style={{ margin: 0, fontSize: 10 }}>
                {p.label}·{p.value}
              </Tag>
            ))}
          </div>
        );
      },
    },
  ], [openDetail, marketplace]);

  /* ── 按勾选维度筛选数据源 ── */
  const filteredCompetitors = useMemo(() => {
    if (!result?.competitors) return [] as CompetitorItem[];
    const colors = new Set(filterColors);
    const sizes = new Set(filterSizes);
    const styles = new Set(filterStyles);
    return result.competitors.filter(c => {
      if (colors.size && !colors.has(c.color || '')) return false;
      if (sizes.size && !sizes.has(c.size || '')) return false;
      if (styles.size && !styles.has(c.style || '')) return false;
      return true;
    });
  }, [result, filterColors, filterSizes, filterStyles]);

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>
          <AimOutlined style={{ marginRight: 8 }} />竞品发现
        </Title>
        <Text type="secondary">通过 Amazon 搜索发现竞品，按价格过滤并排除自有 ASIN</Text>
      </div>

      <Card size="small" style={{ marginBottom: 16, borderRadius: 12 }}>
        <Row gutter={[16, 12]} align="middle">
          <Col xs={24} sm={6}>
            <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>本品 ASIN</Text>
            <Input size="small" placeholder="ASIN（10位）" value={asin}
              onChange={e => setAsin(e.target.value.toUpperCase())} maxLength={10} />
          </Col>
          <Col xs={12} sm={3}>
            <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>站点</Text>
            <Select size="small" value={marketplace} onChange={setMarketplace} style={{ width: '100%' }}
              options={['US','UK','DE','JP','CA','FR','IT','ES'].map(v => ({ label: v, value: v }))} />
          </Col>
          <Col xs={12} sm={4}>
            <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>
              价格浮动 ±{priceTolerance}%
            </Text>
            <Slider min={5} max={100} step={5} value={priceTolerance}
              onChange={v => setPriceTolerance(v)} />
          </Col>
          <Col xs={12} sm={3}>
            <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>最多返回</Text>
            <InputNumber size="small" min={1} max={100} value={maxResults}
              onChange={v => setMaxResults(v || 20)} style={{ width: '100%' }} />
          </Col>
          <Col xs={12} sm={3}>
            <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>
              抓取详情
            </Text>
            <Space size={4} align="center">
              <Switch size="small" checked={withDetails} onChange={setWithDetails} />
              <Text type="secondary" style={{ fontSize: 11 }}>
                {withDetails ? '开' : '关'}
              </Text>
            </Space>
          </Col>
          <Col xs={24} sm={2} style={{ textAlign: 'right' }}>
            <Button type="primary" icon={<ThunderboltOutlined />} loading={loading}
              disabled={asin.trim().length !== 10} onClick={handleDiscover}
              style={{ marginTop: 18 }}>
              发现竞品
            </Button>
          </Col>
        </Row>
      </Card>

      {loading && (
        <Card style={{ borderRadius: 12, textAlign: 'center', padding: 40 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}>
            <Text type="secondary">正在 Amazon 搜索竞品（可切换页面，任务不会丢失）...</Text>
          </div>
        </Card>
      )}

      {result && !loading && (
        <>
          {result.error && (
            <Alert message="提示" description={result.error} type="warning" showIcon
              style={{ marginBottom: 16 }} />
          )}

          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 12 }}>
                <Statistic title="本品 ASIN" value={result.source_asin}
                  valueStyle={{ fontSize: 14, fontFamily: 'monospace' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 12 }}>
                <Statistic title="本品价格" value={result.source_avg_price ?? '-'}
                  prefix={<DollarOutlined />} precision={2} valueStyle={{ fontSize: 14 }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 12 }}>
                <Statistic title="发现竞品" value={result.total_found}
                  prefix={<TrophyOutlined />}
                  valueStyle={{ fontSize: 14, color: result.total_found > 0 ? '#52c41a' : '#8c8c8c' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 12 }}>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Button type="link" icon={<EyeOutlined />}
                    onClick={() => openDetail(result.source_asin)} block>
                    查看本品详情
                  </Button>
                  <Button type="link" size="small" icon={<LinkOutlined />}
                    href={getAmazonUrl(result.source_asin, marketplace)} target="_blank" block
                    style={{ fontSize: 11 }}>
                    在 Amazon 查看
                  </Button>
                </Space>
              </Card>
            </Col>
          </Row>

          {result.competitors.length > 0 ? (
            <>
              {/* 维度筛选：颜色 / 尺寸 / 款式 */}
              {((result.available_colors?.length || 0)
                + (result.available_sizes?.length || 0)
                + (result.available_styles?.length || 0)) > 0 && (
                <Card size="small" style={{ borderRadius: 12, marginBottom: 12 }}
                  styles={{ body: { padding: '10px 14px' } }}>
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space align="center" size={6} wrap>
                      <Text strong style={{ fontSize: 12 }}>筛选维度</Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        （勾选后只保留命中对应颜色/尺寸/款式的竞品）
                      </Text>
                      {(filterColors.length + filterSizes.length + filterStyles.length) > 0 && (
                        <Button type="link" size="small" style={{ padding: 0, height: 'auto' }}
                          onClick={() => { setFilterColors([]); setFilterSizes([]); setFilterStyles([]); }}>
                          清空筛选
                        </Button>
                      )}
                    </Space>
                    {(result.available_colors?.length || 0) > 0 && (
                      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                        <Tag color="magenta" style={{ marginTop: 2, flexShrink: 0 }}>颜色</Tag>
                        <Checkbox.Group
                          value={filterColors}
                          onChange={v => setFilterColors(v as string[])}
                          style={{ flex: 1 }}
                        >
                          <Space size={[8, 4]} wrap>
                            {result.available_colors!.map(c => (
                              <Checkbox key={c} value={c}>{c}</Checkbox>
                            ))}
                          </Space>
                        </Checkbox.Group>
                      </div>
                    )}
                    {(result.available_sizes?.length || 0) > 0 && (
                      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                        <Tag color="geekblue" style={{ marginTop: 2, flexShrink: 0 }}>尺寸</Tag>
                        <Checkbox.Group
                          value={filterSizes}
                          onChange={v => setFilterSizes(v as string[])}
                          style={{ flex: 1 }}
                        >
                          <Space size={[8, 4]} wrap>
                            {result.available_sizes!.map(s => (
                              <Checkbox key={s} value={s}>{s}</Checkbox>
                            ))}
                          </Space>
                        </Checkbox.Group>
                      </div>
                    )}
                    {(result.available_styles?.length || 0) > 0 && (
                      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                        <Tag color="purple" style={{ marginTop: 2, flexShrink: 0 }}>款式</Tag>
                        <Checkbox.Group
                          value={filterStyles}
                          onChange={v => setFilterStyles(v as string[])}
                          style={{ flex: 1 }}
                        >
                          <Space size={[8, 4]} wrap>
                            {result.available_styles!.map(s => (
                              <Checkbox key={s} value={s}>{s}</Checkbox>
                            ))}
                          </Space>
                        </Checkbox.Group>
                      </div>
                    )}
                  </Space>
                </Card>
              )}

              <Card size="small" title={
                <Space><TrophyOutlined style={{ color: '#fa8c16' }} /><span>竞品列表</span>
                  <Tag color="orange">{result.total_found} 条</Tag>
                  {(filterColors.length + filterSizes.length + filterStyles.length) > 0 && (
                    <Tag color="blue">筛选后 {filteredCompetitors.length} 条</Tag>
                  )}
                </Space>
              } style={{ borderRadius: 12 }}>
                {filteredCompetitors.length > 0 ? (
                  <Table
                    dataSource={filteredCompetitors}
                    columns={columns}
                    rowKey="asin"
                    size="middle"
                    pagination={{ pageSize: 15, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
                  />
                ) : (
                  <Empty description={'当前筛选条件下没有匹配的竞品，可减少勾选或点击"清空筛选"'} />
                )}
              </Card>
            </>
          ) : !result.error && (
            <Card style={{ borderRadius: 12, textAlign: 'center', padding: 40 }}>
              <Empty description="未发现符合条件的竞品，可尝试放宽价格范围" />
            </Card>
          )}
        </>
      )}

      {!result && !loading && (
        <Card style={{ borderRadius: 12, textAlign: 'center', padding: 60 }}>
          <AimOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
          <div style={{ marginTop: 16 }}>
            <Text type="secondary">输入 ASIN 后点击"发现竞品"</Text>
          </div>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 11 }}>
              搜索逻辑：获取本品信息 → Amazon 搜索同类商品 → 价格过滤 → 排除自有 ASIN（dim 表）
            </Text>
          </div>
        </Card>
      )}

      <ProductDetailModal
        asin={detailAsin}
        marketplace={marketplace}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      />
    </div>
  );
}
