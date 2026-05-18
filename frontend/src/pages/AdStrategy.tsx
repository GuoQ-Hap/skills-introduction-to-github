import { useMemo, useState } from 'react';
import {
  Alert, Button, Card, Col, Input, InputNumber, Row, Space, Statistic, Table,
  Tag, Typography, message,
} from 'antd';
import {
  BarChartOutlined, CheckCircleOutlined, ClockCircleOutlined, DollarOutlined,
  ExperimentOutlined, RiseOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { listingApi, type AdStrategyActionSuggestion, type AdStrategyAnalyzeResponse } from '../api';

const { Text, Title } = Typography;

function pct(v?: number) {
  if (!v) return '0.00%';
  return `${(v * 100).toFixed(2)}%`;
}

function num(v?: number) {
  return Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

const ACTION_LABELS: Record<string, string> = {
  add_exact_or_raise_bid: '加精准/提竞价',
  negative_or_lower_bid: '否词/降竞价',
  optimize_ctr_or_reduce: '优化CTR/降弱流量',
  pause_product_ad: '暂停商品广告',
  add_product_target: '新增商品投放',
};

const compactNumberStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  height: 42,
  padding: '0 12px',
  border: '1px solid rgba(122, 205, 232, 0.28)',
  borderRadius: 8,
  background: 'rgba(1, 12, 25, 0.72)',
} as const;

const compactUnitStyle = {
  flexShrink: 0,
  whiteSpace: 'nowrap',
  color: '#d9f6ff',
  fontWeight: 700,
} as const;

export default function AdStrategy() {
  const [asin, setAsin] = useState('');
  const [sku, setSku] = useState('');
  const [storeName, setStoreName] = useState('');
  const [countryCode, setCountryCode] = useState('');
  const [days, setDays] = useState(30);
  const [feedbackDays, setFeedbackDays] = useState(7);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AdStrategyAnalyzeResponse | null>(null);

  const analyze = async () => {
    setLoading(true);
    try {
      const { data } = await listingApi.adStrategyAnalyze({
        asin: asin.trim(),
        sku: sku.trim(),
        store_name: storeName.trim(),
        country_code: countryCode.trim(),
        days,
        feedback_days: feedbackDays,
        limit: 100,
      });
      setResult(data);
      message.success('广告策略分析完成');
    } catch (e: any) {
      message.error(e.message || '分析失败');
    } finally {
      setLoading(false);
    }
  };

  const recordAction = async (row: AdStrategyActionSuggestion) => {
    try {
      await listingApi.createAdStrategyAction({
        ...row,
        action_date: new Date().toISOString().slice(0, 10),
      });
      message.success('已记录投放动作，后续可按反馈周期复盘');
      analyze();
    } catch (e: any) {
      message.error(e.message || '记录失败');
    }
  };

  const actionColumns = useMemo(() => [
    {
      title: '建议动作',
      width: 150,
      render: (_: any, r: AdStrategyActionSuggestion) => (
        <Space direction="vertical" size={2}>
          <Tag color="cyan">{ACTION_LABELS[r.action_type] || r.action_type}</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.entity_type}</Text>
        </Space>
      ),
    },
    {
      title: '对象',
      render: (_: any, r: AdStrategyActionSuggestion) => (
        <Space direction="vertical" size={2}>
          <Text strong>{r.entity_value || r.asin}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {r.asin} {r.sku && ` / ${r.sku}`}
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {r.campaign_name || r.campaign_id}
          </Text>
        </Space>
      ),
    },
    {
      title: '指标',
      width: 220,
      render: (_: any, r: AdStrategyActionSuggestion) => (
        <Space size={[6, 4]} wrap>
          <Tag>曝光 {num(r.metrics.impressions)}</Tag>
          <Tag>点击 {num(r.metrics.clicks)}</Tag>
          <Tag>订单 {num(r.metrics.orders)}</Tag>
          <Tag>ACOS {pct(r.metrics.acos)}</Tag>
        </Space>
      ),
    },
    {
      title: '原因',
      dataIndex: 'reason',
      render: (v: string, r: AdStrategyActionSuggestion) => (
        <Space direction="vertical" size={2}>
          <Text>{v}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.before_value} → {r.after_value}</Text>
        </Space>
      ),
    },
    {
      title: '反馈周期',
      width: 90,
      render: (_: any, r: AdStrategyActionSuggestion) => `${r.feedback_days}天`,
    },
    {
      title: '操作',
      width: 110,
      render: (_: any, r: AdStrategyActionSuggestion) => (
        <Button size="small" type="primary" onClick={() => recordAction(r)}>
          记录动作
        </Button>
      ),
    },
  ], []);

  return (
    <div className="market-analysis-page" style={{ padding: 24, maxWidth: 1440, margin: '0 auto' }}>
      <div style={{ marginBottom: 20 }}>
        <Title level={4} style={{ margin: 0 }}>
          <ExperimentOutlined style={{ marginRight: 8 }} />广告投放策略
        </Title>
        <Text type="secondary">按时间维度读取领星 SP 数据，生成投放动作，并对已记录动作做前后周期反馈。</Text>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} md={4}><Input placeholder="ASIN，可空" value={asin} onChange={e => setAsin(e.target.value.trim())} /></Col>
          <Col xs={24} md={4}><Input placeholder="SKU，可空" value={sku} onChange={e => setSku(e.target.value)} /></Col>
          <Col xs={24} md={4}><Input placeholder="店铺，可空" value={storeName} onChange={e => setStoreName(e.target.value)} /></Col>
          <Col xs={12} md={3}><Input placeholder="国家" value={countryCode} onChange={e => setCountryCode(e.target.value.toUpperCase())} /></Col>
          <Col xs={12} md={3}>
            <div style={compactNumberStyle}>
              <InputNumber
                min={7}
                max={180}
                value={days}
                onChange={v => setDays(v || 30)}
                controls={false}
                bordered={false}
                style={{ flex: 1, minWidth: 56 }}
              />
              <span style={compactUnitStyle}>分析天</span>
            </div>
          </Col>
          <Col xs={12} md={3}>
            <div style={compactNumberStyle}>
              <InputNumber
                min={3}
                max={30}
                value={feedbackDays}
                onChange={v => setFeedbackDays(v || 7)}
                controls={false}
                bordered={false}
                style={{ flex: 1, minWidth: 56 }}
              />
              <span style={compactUnitStyle}>反馈天</span>
            </div>
          </Col>
          <Col xs={12} md={3} style={{ textAlign: 'right' }}>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={loading}
              onClick={analyze}
              style={{ width: '100%', height: 42 }}
            >
              开始分析
            </Button>
          </Col>
        </Row>
      </Card>

      {result && (
        <>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={`分析周期 ${result.date_start} ~ ${result.date_end}，对比周期 ${result.compare_start} ~ ${result.compare_end}`}
            description={`动作记录表：${result.target_table}`}
          />
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} md={6}><Card size="small"><Statistic title="曝光" value={result.current.impressions} prefix={<BarChartOutlined />} /></Card></Col>
            <Col xs={12} md={6}><Card size="small"><Statistic title="花费" value={result.current.cost} precision={2} prefix={<DollarOutlined />} /></Card></Col>
            <Col xs={12} md={6}><Card size="small"><Statistic title="订单" value={result.current.orders} prefix={<CheckCircleOutlined />} /></Card></Col>
            <Col xs={12} md={6}><Card size="small"><Statistic title="ACOS" value={(result.current.acos || 0) * 100} precision={2} suffix="%" prefix={<RiseOutlined />} /></Card></Col>
          </Row>

          <Card size="small" title={<Space><ThunderboltOutlined />本轮建议动作</Space>} style={{ marginBottom: 16 }}>
            <Table
              rowKey={(r: AdStrategyActionSuggestion, idx) => `${r.action_type}-${r.entity_type}-${r.entity_value}-${idx}`}
              columns={actionColumns}
              dataSource={result.recommended_actions}
              pagination={{ pageSize: 10, showSizeChanger: true }}
            />
          </Card>

          <Card size="small" title={<Space><ClockCircleOutlined />已记录动作反馈</Space>}>
            {result.action_feedback?.length ? (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                {result.action_feedback.map((item, idx) => (
                  <Card key={idx} size="small">
                    <Space direction="vertical" size={4}>
                      <Space wrap>
                        <Tag color={item.status === 'evaluated' ? 'green' : 'orange'}>{item.status}</Tag>
                        <Text strong>{item.action?.action_type}</Text>
                        <Text type="secondary">{item.action?.entity_value || item.action?.asin}</Text>
                      </Space>
                      <Text>{item.summary}</Text>
                      {item.before && item.after && (
                        <Text type="secondary">
                          前：订单 {item.before.orders} / ACOS {pct(item.before.acos)}
                          {' '}→ 后：订单 {item.after.orders} / ACOS {pct(item.after.acos)}
                        </Text>
                      )}
                    </Space>
                  </Card>
                ))}
              </Space>
            ) : (
              <Text type="secondary">暂无已记录动作反馈。先在建议动作中点击“记录动作”，到反馈周期后自动对比。</Text>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
