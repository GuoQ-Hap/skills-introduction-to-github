import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Row,
  Col,
  Card,
  Statistic,
  Typography,
  Button,
  Tag,
  Space,
  Spin,
} from 'antd';
import {
  ShoppingOutlined,
  DatabaseOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  MessageOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import { listingApi, stiApi, adminApi, lmaApi } from '../api';
import { RAINBOW, BTN_RAINBOW } from '../layouts/MainLayout';

const { Title, Paragraph, Text } = Typography;
const DASH_COLOR = RAINBOW[0];
const R = BTN_RAINBOW;

/** LEANG 菱形星纹 SVG — 用作背景装饰 */
const GeoPattern = ({ color = DASH_COLOR.from, opacity = 0.06, size = 120, style = {} }: {
  color?: string; opacity?: number; size?: number; style?: React.CSSProperties;
}) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={{ position: 'absolute', opacity, pointerEvents: 'none', ...style }}>
    <g transform="translate(50,50)">
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
        <polygon key={deg} points="0,-42 12,-14 0,-6 -12,-14" fill={color} transform={`rotate(${deg})`} />
      ))}
    </g>
  </svg>
);

interface ServiceStatus {
  name: string;
  status: 'ok' | 'error' | 'loading';
  model?: string;
}

const DASH_CACHE_KEY = 'dash_services';

export default function Dashboard() {
  const navigate = useNavigate();
  const [services, setServices] = useState<ServiceStatus[]>(() => {
    try {
      const cached = sessionStorage.getItem(DASH_CACHE_KEY);
      if (cached) return JSON.parse(cached);
    } catch { /* ignore */ }
    return [
      { name: 'LSTA Listing 优化', status: 'loading' },
      { name: 'LDA 数据查询', status: 'loading' },
      { name: 'LMA 智能问答', status: 'loading' },
      { name: '系统管理', status: 'loading' },
    ];
  });

  useEffect(() => {
    const checks = [
      listingApi.health()
        .then((r: any) => ({ name: 'LSTA Listing 优化', status: 'ok' as const, model: r.data.model }))
        .catch(() => ({ name: 'LSTA Listing 优化', status: 'error' as const })),
      stiApi.health()
        .then((r) => ({ name: 'LDA 数据查询', status: 'ok' as const, model: r.data.model }))
        .catch(() => ({ name: 'LDA 数据查询', status: 'error' as const })),
      lmaApi.health()
        .then(() => ({ name: 'LMA 智能问答', status: 'ok' as const }))
        .catch(() => ({ name: 'LMA 智能问答', status: 'error' as const })),
      adminApi.health()
        .then(() => ({ name: '系统管理', status: 'ok' as const }))
        .catch(() => ({ name: '系统管理', status: 'error' as const })),
    ];
    Promise.all(checks).then(results => {
      setServices(results);
      try { sessionStorage.setItem(DASH_CACHE_KEY, JSON.stringify(results)); } catch { /* ignore */ }
    });
  }, []);

  const okCount = services.filter((s) => s.status === 'ok').length;

  const agentColor = RAINBOW[1];
  const dataColor = RAINBOW[2];
  const ragColor = RAINBOW[3];

  const featureCards = [
    {
      icon: <ShoppingOutlined style={{ fontSize: 28, color: agentColor.from }} />,
      title: 'Listing 智能优化',
      desc: '输入 ASIN，AI 自动获取产品信息并生成优化后的标题、五点描述和搜索词',
      path: '/listing',
      tag: 'LSTA',
      accent: `${agentColor.from}15`,
      border: `${agentColor.to}40`,
    },
    {
      icon: <DatabaseOutlined style={{ fontSize: 28, color: dataColor.from }} />,
      title: '自然语言查数',
      desc: '用自然语言描述需求，AI 自动生成 SQL、执行查询并给出数据分析',
      path: '/query',
      tag: 'LDA',
      accent: `${dataColor.from}15`,
      border: `${dataColor.to}40`,
    },
    {
      icon: <MessageOutlined style={{ fontSize: 28, color: ragColor.from }} />,
      title: '知识库问答',
      desc: '上传文档构建知识库，基于 RAG 检索增强生成进行智能问答',
      path: '/rag',
      tag: 'LMA',
      accent: `${ragColor.from}15`,
      border: `${ragColor.to}40`,
    },
  ];

  return (
    <div>
      {/* Hero */}
      <Card
        style={{
          background: '#fff',
          borderRadius: 16,
          border: '1px solid #f0f0f0',
          marginBottom: 24,
          position: 'relative',
          overflow: 'hidden',
        }}
        styles={{ body: { padding: '36px 40px', position: 'relative', zIndex: 1 } }}
      >
        {/* 装饰星纹 */}
        <GeoPattern size={200} opacity={0.05} style={{ top: -40, right: -30 }} />
        <GeoPattern size={120} opacity={0.04} style={{ bottom: -30, right: 120 }} />
        <GeoPattern size={80} opacity={0.03} style={{ top: 10, right: 280 }} />

        {/* 左边橙色竖条 */}
        <div style={{
          position: 'absolute', left: 0, top: 0, bottom: 0, width: 4,
          background: `linear-gradient(180deg, ${DASH_COLOR.from}, ${DASH_COLOR.to})`,
          borderRadius: '16px 0 0 16px',
        }} />

        <Row align="middle" gutter={24}>
          <Col flex="auto">
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14 }}>
              <img src="/assets/logo.png" alt="LEANG" style={{ height: 36, mixBlendMode: 'multiply' }} />
              <div style={{ width: 1, height: 24, background: '#e0e0e0' }} />
              <Tag
                style={{
                  background: `linear-gradient(135deg, ${DASH_COLOR.from}20, ${DASH_COLOR.to}20)`,
                  border: `1px solid ${DASH_COLOR.to}40`,
                  color: DASH_COLOR.from,
                  borderRadius: 16,
                  padding: '3px 14px',
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                <ThunderboltOutlined /> AI 赋能
              </Tag>
            </div>
            <Title level={3} style={{ color: '#1a1a1a', marginBottom: 8 }}>
              跨境电商智能运营平台
            </Title>
            <Paragraph style={{ color: '#666', fontSize: 14, marginBottom: 0, maxWidth: 480 }}>
              AI 驱动的一站式运营工具 — Listing 智能优化 · 自然语言查数 · 知识库问答
            </Paragraph>
          </Col>
          <Col>
            <Button
              size="large"
              type="primary"
              style={{
                background: R[0],
                fontWeight: 600, borderRadius: 10, height: 46, paddingInline: 28,
              }}
              icon={<ArrowRightOutlined />}
              onClick={() => navigate('/listing')}
            >
              开始使用
            </Button>
          </Col>
        </Row>
      </Card>

      {/* 统计 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <Card style={{ borderRadius: 12, border: '1px solid #f0f0f0' }}>
            <Statistic
              title="服务在线"
              value={okCount}
              suffix={`/ ${services.length}`}
              prefix={<ApiOutlined />}
              styles={{ content: { color: okCount === services.length ? '#43A047' : DASH_COLOR.from } }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card style={{ borderRadius: 12, border: '1px solid #f0f0f0' }}>
            <Statistic
              title="支持站点"
              value={10}
              suffix="个"
              prefix={<ShoppingOutlined />}
              styles={{ content: { color: DASH_COLOR.to } }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card style={{ borderRadius: 12, border: '1px solid #f0f0f0' }}>
            <Statistic
              title="AI 模型"
              value={services.find((s) => s.model)?.model || '-'}
              prefix={<ThunderboltOutlined />}
              styles={{ content: { color: DASH_COLOR.from, fontSize: 18 } }}
            />
          </Card>
        </Col>
      </Row>

      {/* 功能卡片 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <div style={{ width: 3, height: 18, background: DASH_COLOR.from, borderRadius: 2 }} />
        <Title level={5} style={{ marginBottom: 0 }}>AI 核心能力</Title>
      </div>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {featureCards.map((f) => (
          <Col xs={24} md={8} key={f.title}>
            <Card
              hoverable
              onClick={() => navigate(f.path)}
              style={{
                borderRadius: 12, border: `1px solid ${f.border}`,
                height: '100%', position: 'relative', overflow: 'hidden',
              }}
              styles={{ body: { padding: 24 } }}
            >
              <GeoPattern size={80} opacity={0.04} color={f.border} style={{ top: -20, right: -20 }} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12, background: f.accent,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {f.icon}
                </div>
                <Tag color="orange" style={{ borderRadius: 6, fontSize: 11 }}>{f.tag}</Tag>
              </div>
              <Title level={5} style={{ marginBottom: 8, fontSize: 15 }}>{f.title}</Title>
              <Text type="secondary" style={{ fontSize: 13, lineHeight: 1.6 }}>{f.desc}</Text>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 服务状态 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <div style={{ width: 3, height: 18, background: DASH_COLOR.from, borderRadius: 2 }} />
        <Title level={5} style={{ marginBottom: 0 }}>服务状态</Title>
      </div>
      <Card style={{ borderRadius: 12, border: '1px solid #f0f0f0' }}>
        <Space orientation="vertical" size={8} style={{ width: '100%' }}>
          {services.map((s) => (
            <div
              key={s.name}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 16px', background: '#FAFAFA', borderRadius: 8,
              }}
            >
              <Text style={{ fontSize: 14 }}>{s.name}</Text>
              {s.status === 'loading' ? (
                <Spin size="small" />
              ) : s.status === 'ok' ? (
                <Tag icon={<CheckCircleOutlined />} color="success">
                  运行中 {s.model && `· ${s.model}`}
                </Tag>
              ) : (
                <Tag icon={<CloseCircleOutlined />} color="error">离线</Tag>
              )}
            </div>
          ))}
        </Space>
      </Card>
    </div>
  );
}
