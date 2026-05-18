import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, Col, Row, Space, Spin, Statistic, Tag, Typography } from 'antd';
import {
  ApiOutlined,
  ArrowRightOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  RobotOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { adminApi, listingApi, lmaApi, stiApi } from '../api';

const { Title, Paragraph, Text } = Typography;

interface ServiceStatus {
  name: string;
  status: 'ok' | 'error' | 'loading';
  model?: string;
}

const DASH_CACHE_KEY = 'ai_platform_dash_services';

const architecture = [
  { title: '运营增长', desc: 'Listing、评论、竞品、定位、广告建议和多语言内容生成。', state: '已接入' },
  { title: '供应链管理', desc: '库存、采购、供应商、在途、仓储、物流节点和异常状态追踪。', state: '预设' },
  { title: '财务管理', desc: '利润、成本、回款、现金流、费用归因和经营风险提醒。', state: '预设' },
  { title: '产品管理', desc: '选品、产品开发、规格资料、上新刊登和上市准备。', state: '预设' },
  { title: '组织人事', desc: '招聘、绩效、组织发展、人才盘点和入职流程。', state: '预设' },
  { title: '数据与知识智能', desc: '自然语言查数、经营指标看板、知识库问答和自动化工作流。', state: '部分接入' },
];

const flowSteps = ['工作中心', '运营增长', '供应链管理', '财务管理', '产品管理', '组织人事', '数据智能', '经营复盘'];

export default function Dashboard() {
  const navigate = useNavigate();
  const [services, setServices] = useState<ServiceStatus[]>(() => {
    try {
      const cached = sessionStorage.getItem(DASH_CACHE_KEY);
      if (cached) return JSON.parse(cached);
    } catch { /* ignore */ }
    return [
      { name: 'AI Listing 工厂', status: 'loading' },
      { name: '数据查询引擎', status: 'loading' },
      { name: '企业知识库', status: 'loading' },
      { name: '系统治理服务', status: 'loading' },
    ];
  });

  useEffect(() => {
    const checks = [
      listingApi.health()
        .then((r: any) => ({ name: 'AI Listing 工厂', status: 'ok' as const, model: r.data?.model }))
        .catch(() => ({ name: 'AI Listing 工厂', status: 'error' as const })),
      stiApi.health()
        .then((r) => ({ name: '数据查询引擎', status: 'ok' as const, model: r.data?.model }))
        .catch(() => ({ name: '数据查询引擎', status: 'error' as const })),
      lmaApi.health()
        .then(() => ({ name: '企业知识库', status: 'ok' as const }))
        .catch(() => ({ name: '企业知识库', status: 'error' as const })),
      adminApi.health()
        .then(() => ({ name: '系统治理服务', status: 'ok' as const }))
        .catch(() => ({ name: '系统治理服务', status: 'error' as const })),
    ];
    Promise.all(checks).then(result => {
      setServices(result);
      try { sessionStorage.setItem(DASH_CACHE_KEY, JSON.stringify(result)); } catch { /* ignore */ }
    });
  }, []);

  const okCount = services.filter(item => item.status === 'ok').length;
  const primaryModel = useMemo(() => services.find(item => item.model)?.model || '待连接', [services]);

  return (
    <div className="dashboard-page">
      <section className="tech-hero">
        <div className="tech-hero-copy">
          <Tag className="tech-tag"><ThunderboltOutlined /> LEANG Company Intelligence OS</Tag>
          <Title level={1}>LEANG AI一体化平台</Title>
          <Paragraph>
            预设 LEANG 工作中心：运营、供应链、财务、产品、人事、数据智能和系统治理先形成统一前端入口。
          </Paragraph>
          <Space size={12} wrap>
            <Button type="primary" size="large" icon={<RobotOutlined />} onClick={() => navigate('/listing?tab=optimize')}>
              进入 AI Listing 工厂
            </Button>
            <Button size="large" icon={<ArrowRightOutlined />} onClick={() => navigate('/architecture')}>
              查看工作中心
            </Button>
          </Space>
        </div>
        <div className="tech-orbit" aria-hidden="true">
          <div className="orbit-core"><GlobalOutlined /></div>
          <span style={{ '--i': 0 } as React.CSSProperties}>运营</span>
          <span style={{ '--i': 1 } as React.CSSProperties}>产品</span>
          <span style={{ '--i': 2 } as React.CSSProperties}>财务</span>
          <span style={{ '--i': 3 } as React.CSSProperties}>供应链</span>
          <span style={{ '--i': 4 } as React.CSSProperties}>数据</span>
          <span style={{ '--i': 5 } as React.CSSProperties}>人事</span>
        </div>
      </section>

      <Row gutter={[16, 16]} className="metric-row">
        <Col xs={24} md={8}>
          <Card className="tech-card">
            <Statistic title="在线服务" value={okCount} suffix={`/ ${services.length}`} prefix={<ApiOutlined />} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="tech-card">
            <Statistic title="预设公司域" value={14} suffix="个" prefix={<CloudServerOutlined />} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="tech-card">
            <Statistic title="主模型" value={primaryModel} prefix={<ThunderboltOutlined />} valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
      </Row>

      <div className="section-head">
        <div>
          <Text className="eyebrow">COMPANY BLUEPRINT</Text>
          <Title level={3}>LEANG 整体架构预设</Title>
        </div>
        <Tag className="blue-tag">前端已预设</Tag>
      </div>

      <Row gutter={[16, 16]}>
        {architecture.map((item) => (
          <Col xs={24} md={12} xl={8} key={item.title}>
            <Card className="module-card" hoverable>
              <div className="module-card-index">★</div>
              <Tag className={item.state === '已接入' ? 'ready-tag' : 'planned-tag'}>{item.state}</Tag>
              <Title level={4}>{item.title}</Title>
              <Paragraph>{item.desc}</Paragraph>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card className="tech-card" title={<span><BarChartOutlined /> 公司经营链路</span>}>
            <div className="flow-line company-flow">
              {flowSteps.map(step => (
                <div className="flow-node" key={step}>{step}</div>
              ))}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card className="tech-card" title={<span><DatabaseOutlined /> 服务状态</span>}>
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              {services.map(service => (
                <div className="service-row" key={service.name}>
                  <span>{service.name}</span>
                  {service.status === 'loading' ? <Spin size="small" /> : (
                    <Tag icon={<CheckCircleOutlined />} color={service.status === 'ok' ? 'cyan' : 'red'}>
                      {service.status === 'ok' ? `运行中${service.model ? ` / ${service.model}` : ''}` : '待连接'}
                    </Tag>
                  )}
                </div>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
