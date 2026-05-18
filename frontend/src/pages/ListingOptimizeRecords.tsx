import { useEffect, useMemo, useState } from 'react';
import {
  Alert, Button, Card, Col, Drawer, Empty, Image, Input, Row, Space, Spin,
  Tag, Typography, message, Modal,
} from 'antd';
import { DatabaseOutlined, DeleteOutlined, EyeOutlined, ReloadOutlined, SaveOutlined, SearchOutlined } from '@ant-design/icons';
import { listingApi, type ListingOptimizeRecord, type OptimizedListing } from '../api';

const { Text, Title } = Typography;

function fmtMetric(v?: number | null, suffix = '') {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
  return `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
}

function metricDelta(before?: number | null, current?: number | null) {
  if (before === null || before === undefined || current === null || current === undefined) return null;
  return current - before;
}

function MetricBar({
  label, before, current, suffix = '', beforePeriod, currentPeriod,
}: {
  label: string;
  before?: number | null;
  current?: number | null;
  suffix?: string;
  beforePeriod: string;
  currentPeriod: string;
}) {
  const max = Math.max(Math.abs(Number(before || 0)), Math.abs(Number(current || 0)), 1);
  const beforeW = Math.max(4, Math.min(100, Math.abs(Number(before || 0)) / max * 100));
  const currentW = Math.max(4, Math.min(100, Math.abs(Number(current || 0)) / max * 100));
  const delta = metricDelta(before, current);
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '88px minmax(0, 1fr) 96px', gap: 10, alignItems: 'center' }}>
      <Text strong style={{ fontSize: 12 }}>{label}</Text>
      <div>
        <div title={`优化前统计时段：${beforePeriod}`} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
          <span style={{ width: `${beforeW}%`, height: 8, borderRadius: 4, background: '#94a3b8', display: 'inline-block' }} />
          <Text type="secondary" style={{ fontSize: 11 }}>前 {fmtMetric(before, suffix)}</Text>
        </div>
        <div title={`当前统计时段：${currentPeriod}`} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: `${currentW}%`, height: 8, borderRadius: 4, background: '#16a34a', display: 'inline-block' }} />
          <Text style={{ fontSize: 11, color: '#166534' }}>现 {fmtMetric(current, suffix)}</Text>
        </div>
      </div>
      <Tag color={delta == null ? 'default' : delta >= 0 ? 'green' : 'red'}>
        {delta == null ? '无对比' : `${delta >= 0 ? '+' : ''}${fmtMetric(delta, suffix)}`}
      </Tag>
    </div>
  );
}

function ListingText({ title, listing }: { title: string; listing: OptimizedListing }) {
  return (
    <div style={{ minWidth: 0 }}>
      <Text strong>{title}</Text>
      <div style={{ marginTop: 8, fontSize: 12, lineHeight: 1.7 }}>
        <Text strong>标题：</Text>
        <div style={{ whiteSpace: 'pre-wrap', marginBottom: 8 }}>{listing?.title || '-'}</div>
        <Text strong>五点：</Text>
        <ol style={{ paddingLeft: 18, marginTop: 4 }}>
          {(listing?.bullet_points || []).map((x, i) => <li key={i}>{x}</li>)}
        </ol>
        <Text strong>描述：</Text>
        <div style={{ whiteSpace: 'pre-wrap', marginBottom: 8 }}>{listing?.description || '-'}</div>
        <Text strong>Search Terms：</Text>
        <div style={{ whiteSpace: 'pre-wrap' }}>{listing?.search_terms || '-'}</div>
      </div>
    </div>
  );
}

export default function ListingOptimizeRecords() {
  const [asin, setAsin] = useState('');
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<ListingOptimizeRecord[]>([]);
  const [detail, setDetail] = useState<ListingOptimizeRecord | null>(null);
  const [remarkDraft, setRemarkDraft] = useState('');
  const [savingRemark, setSavingRemark] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await listingApi.optimizeRecords({ asin: asin.trim() || undefined, limit: 200 });
      setItems(data.items || []);
    } catch (e: any) {
      message.error(e?.message || '加载优化记录失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    setRemarkDraft(detail?.remark || '');
  }, [detail?.id]);

  const openDetail = (item: ListingOptimizeRecord) => {
    setDetail(item);
    setRemarkDraft(item.remark || '');
  };

  const saveRemark = async () => {
    if (!detail) return;
    setSavingRemark(true);
    try {
      const { data } = await listingApi.updateOptimizeRecordRemark({ id: detail.id, remark: remarkDraft });
      setDetail(data.record);
      setItems(prev => prev.map(item => item.id === detail.id ? data.record : item));
      message.success('备注已保存');
    } catch (e: any) {
      message.error(e?.message || '备注保存失败');
    } finally {
      setSavingRemark(false);
    }
  };

  const deleteRecord = (item: ListingOptimizeRecord) => {
    Modal.confirm({
      title: `删除优化记录 #${item.id}`,
      content: `确认删除 ASIN ${item.asin} 的这条记录？删除后会同步清理该记录关联的 MinIO 图片对象。`,
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        await listingApi.deleteOptimizeRecord({ id: item.id });
        setItems(prev => prev.filter(x => x.id !== item.id));
        if (detail?.id === item.id) setDetail(null);
        message.success('记录已删除');
      },
    });
  };

  const detailPeriods = useMemo(() => {
    if (!detail) return { before: '', current: '' };
    return {
      before: `${detail.metric_start || detail.before_metrics?.metric_start} ~ ${detail.metric_end || detail.before_metrics?.metric_end}`,
      current: `${detail.current_metric_start || detail.current_metrics?.metric_start} ~ ${detail.current_metric_end || detail.current_metrics?.metric_end}`,
    };
  }, [detail]);

  return (
    <div className="market-analysis-page" style={{ padding: 24, maxWidth: 1440, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}><DatabaseOutlined style={{ marginRight: 8 }} />Listing 优化入库记录</Title>
          <Text type="secondary">查看已确认采用的优化文案、图片与 CTR/CVR/流量前后对比。</Text>
        </div>
        <Space>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="按 ASIN 筛选"
            value={asin}
            onChange={e => setAsin(e.target.value.trim())}
            onPressEnter={load}
            style={{ width: 220 }}
          />
          <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>刷新</Button>
        </Space>
      </div>

      {loading && !items.length ? (
        <div style={{ textAlign: 'center', padding: 80 }}><Spin /></div>
      ) : !items.length ? (
        <Empty description="暂无优化入库记录" />
      ) : (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {items.map(item => {
            const beforePeriod = `${item.metric_start || item.before_metrics?.metric_start} ~ ${item.metric_end || item.before_metrics?.metric_end}`;
            const currentPeriod = `${item.current_metric_start || item.current_metrics?.metric_start} ~ ${item.current_metric_end || item.current_metrics?.metric_end}`;
            return (
              <Card key={item.id} size="small" style={{ borderRadius: 8 }}>
                <Row gutter={[16, 12]} align="middle">
                  <Col xs={24} md={5}>
                    <Space direction="vertical" size={4}>
                      <Space wrap>
                        <Tag color="blue">{item.asin}</Tag>
                        <Tag>{item.marketplace}</Tag>
                        {item.variant_rank && <Tag color="gold">候选 {item.variant_rank}/{item.variant_total}</Tag>}
                      </Space>
                      <Text type="secondary" style={{ fontSize: 12 }}>{item.created_at}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        创建人 {item.operator || '-'} / 修改人 {item.updated_by || '-'}
                      </Text>
                      <Text style={{ fontSize: 12 }}>{item.optimization_direction || '未填写优化方向'}</Text>
                      {item.remark && <Text type="secondary" style={{ fontSize: 12 }}>备注：{item.remark.slice(0, 48)}{item.remark.length > 48 ? '...' : ''}</Text>}
                    </Space>
                  </Col>
                  <Col xs={24} md={5}>
                    <Space size={6}>
                      {(item.after_images || item.before_images || []).slice(0, 3).map((img, idx) => (
                        <Image key={idx} src={img.url || img.source_url} width={54} height={54} style={{ objectFit: 'cover', borderRadius: 6 }} />
                      ))}
                    </Space>
                  </Col>
                  <Col xs={24} md={11}>
                    <Space direction="vertical" size={8} style={{ width: '100%' }}>
                      <MetricBar label="CTR" before={item.before_metrics?.ctr} current={item.current_metrics?.ctr} suffix="%" beforePeriod={beforePeriod} currentPeriod={currentPeriod} />
                      <MetricBar label="CVR" before={item.before_metrics?.cvr} current={item.current_metrics?.cvr} suffix="%" beforePeriod={beforePeriod} currentPeriod={currentPeriod} />
                      <MetricBar label="流量" before={item.before_metrics?.traffic} current={item.current_metrics?.traffic} beforePeriod={beforePeriod} currentPeriod={currentPeriod} />
                    </Space>
                  </Col>
                  <Col xs={24} md={3} style={{ textAlign: 'right' }}>
                    <Space direction="vertical" size={8}>
                      <Button icon={<EyeOutlined />} onClick={() => openDetail(item)}>详情对比</Button>
                      <Button danger icon={<DeleteOutlined />} onClick={() => deleteRecord(item)}>删除</Button>
                    </Space>
                  </Col>
                </Row>
              </Card>
            );
          })}
        </Space>
      )}

      <Drawer
        title={detail ? `优化详情对比 - ${detail.asin}` : '优化详情'}
        open={!!detail}
        onClose={() => setDetail(null)}
        width={Math.min(window.innerWidth * 0.9, 1180)}
        destroyOnClose
      >
        {detail && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message={`优化前统计时段：${detailPeriods.before}；当前统计时段：${detailPeriods.current}`}
              description={`创建人：${detail.operator || '-'} / 最近修改人：${detail.updated_by || '-'} / 优化原因：${detail.optimization_reason || '未填写'} / 优化方向：${detail.optimization_direction || '未填写'}`}
            />
            <Card size="small" title="备注">
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Input.TextArea
                  value={remarkDraft}
                  onChange={e => setRemarkDraft(e.target.value)}
                  autoSize={{ minRows: 3, maxRows: 8 }}
                  maxLength={4000}
                  showCount
                  placeholder="可手动修改备注"
                />
                <div style={{ textAlign: 'right' }}>
                  <Button type="primary" icon={<SaveOutlined />} loading={savingRemark} onClick={saveRemark}>保存备注</Button>
                </div>
              </Space>
            </Card>
            <Card size="small" title="指标横向对比">
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <MetricBar label="CTR" before={detail.before_metrics?.ctr} current={detail.current_metrics?.ctr} suffix="%" beforePeriod={detailPeriods.before} currentPeriod={detailPeriods.current} />
                <MetricBar label="CVR" before={detail.before_metrics?.cvr} current={detail.current_metrics?.cvr} suffix="%" beforePeriod={detailPeriods.before} currentPeriod={detailPeriods.current} />
                <MetricBar label="流量" before={detail.before_metrics?.traffic} current={detail.current_metrics?.traffic} beforePeriod={detailPeriods.before} currentPeriod={detailPeriods.current} />
              </Space>
            </Card>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                <Card size="small" title="优化前图片">
                  <Space size={8} wrap>
                    {(detail.before_images || []).map((img, idx) => (
                      <Image key={idx} src={img.url || img.source_url} width={96} height={96} style={{ objectFit: 'cover', borderRadius: 6 }} />
                    ))}
                  </Space>
                </Card>
              </Col>
              <Col xs={24} md={12}>
                <Card size="small" title="优化后图片">
                  <Space size={8} wrap>
                    {(detail.after_images || []).map((img, idx) => (
                      <Image key={idx} src={img.url || img.source_url} width={96} height={96} style={{ objectFit: 'cover', borderRadius: 6 }} />
                    ))}
                  </Space>
                </Card>
              </Col>
            </Row>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}><Card size="small"><ListingText title="优化前文案" listing={detail.before_listing} /></Card></Col>
              <Col xs={24} md={12}><Card size="small"><ListingText title="优化后文案" listing={detail.after_listing} /></Card></Col>
            </Row>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
