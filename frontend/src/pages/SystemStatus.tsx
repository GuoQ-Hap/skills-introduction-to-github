import { useEffect, useState } from 'react';
import {
  Row,
  Col,
  Card,
  Typography,
  Tag,
  Spin,
  Space,
  Descriptions,
  Alert,
  Button,
  Divider,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  ApiOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  ShoppingOutlined,
} from '@ant-design/icons';
import { listingApi, stiApi, adminApi, lmaApi } from '../api';
import { RAINBOW } from '../layouts/MainLayout';

const SYS_COLOR = RAINBOW[4];

const { Title, Text } = Typography;

interface HealthInfo {
  key: string;
  name: string;
  icon: React.ReactNode;
  status: 'ok' | 'error' | 'loading';
  data?: Record<string, unknown>;
  error?: string;
}

export default function SystemStatus() {
  const [services, setServices] = useState<HealthInfo[]>([]);
  const [loadingAll, setLoadingAll] = useState(false);

  const fetchAll = async () => {
    setLoadingAll(true);
    setServices([
      { key: 'lsta', name: 'LSTA Listing 优化服务', icon: <ShoppingOutlined />, status: 'loading' },
      { key: 'lda', name: 'LDA 数据查询服务', icon: <DatabaseOutlined />, status: 'loading' },
      { key: 'lma', name: 'LMA 智能问答服务', icon: <ApiOutlined />, status: 'loading' },
      { key: 'admin', name: '系统管理服务', icon: <CloudServerOutlined />, status: 'loading' },
    ]);

    const results = await Promise.all([
      listingApi
        .health()
        .then((r: any) => ({
          key: 'lsta',
          name: 'LSTA Listing 优化服务',
          icon: <ShoppingOutlined />,
          status: 'ok' as const,
          data: r.data,
        }))
        .catch((e: any) => ({
          key: 'lsta',
          name: 'LSTA Listing 优化服务',
          icon: <ShoppingOutlined />,
          status: 'error' as const,
          error: e.message,
        })),
      stiApi
        .health()
        .then((r: any) => ({
          key: 'lda',
          name: 'LDA 数据查询服务',
          icon: <DatabaseOutlined />,
          status: 'ok' as const,
          data: r.data,
        }))
        .catch((e: any) => ({
          key: 'lda',
          name: 'LDA 数据查询服务',
          icon: <DatabaseOutlined />,
          status: 'error' as const,
          error: e.message,
        })),
      lmaApi
        .health()
        .then((r: any) => ({
          key: 'lma',
          name: 'LMA 智能问答服务',
          icon: <ApiOutlined />,
          status: 'ok' as const,
          data: r.data,
        }))
        .catch((e: any) => ({
          key: 'lma',
          name: 'LMA 智能问答服务',
          icon: <ApiOutlined />,
          status: 'error' as const,
          error: e.message,
        })),
      adminApi
        .health()
        .then((r: any) => ({
          key: 'admin',
          name: '系统管理服务',
          icon: <CloudServerOutlined />,
          status: 'ok' as const,
          data: r.data,
        }))
        .catch((e: any) => ({
          key: 'admin',
          name: '系统管理服务',
          icon: <CloudServerOutlined />,
          status: 'error' as const,
          error: e.message,
        })),
    ]);

    setServices(results);
    setLoadingAll(false);
    try {
      const cacheable = results.map(r => ({ ...r, icon: undefined }));
      sessionStorage.setItem('sys_status_cache', JSON.stringify(cacheable));
    } catch { /* ignore */ }
  };

  const iconMap: Record<string, React.ReactNode> = {
    lsta: <ShoppingOutlined />, lda: <DatabaseOutlined />,
    lma: <ApiOutlined />, admin: <CloudServerOutlined />,
  };

  useEffect(() => {
    try {
      const cached = sessionStorage.getItem('sys_status_cache');
      if (cached) {
        const parsed: HealthInfo[] = JSON.parse(cached);
        setServices(parsed.map(s => ({ ...s, icon: iconMap[s.key] || <ApiOutlined /> })));
      }
    } catch { /* ignore */ }
    fetchAll();
  }, []);

  const okCount = services.filter((s) => s.status === 'ok').length;
  const total = services.length;

  return (
    <div>
      <Row gutter={[20, 20]} style={{ marginBottom: 24 }}>
        <Col span={24}>
          <Card
            style={{
              borderRadius: 14,
              border: 'none',
              boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
              background:
                okCount === total
                  ? `linear-gradient(135deg, ${SYS_COLOR.from}, ${SYS_COLOR.to})`
                  : `linear-gradient(135deg, ${SYS_COLOR.to}, ${SYS_COLOR.from})`,
            }}
            styles={{ body: { padding: '24px 32px' } }}
          >
            <Row align="middle" justify="space-between">
              <Col>
                <Space size={16}>
                  <ApiOutlined style={{ fontSize: 28, color: '#fff' }} />
                  <div>
                    <Title level={4} style={{ color: '#fff', marginBottom: 4 }}>
                      系统状态总览
                    </Title>
                    <Text style={{ color: 'rgba(255,255,255,0.85)' }}>
                      {okCount === total
                        ? '所有服务运行正常'
                        : `${okCount} / ${total} 个服务在线`}
                    </Text>
                  </div>
                </Space>
              </Col>
              <Col>
                <Button
                  icon={<ReloadOutlined />}
                  loading={loadingAll}
                  onClick={fetchAll}
                  style={{
                    background: 'rgba(255,255,255,0.2)',
                    border: '1px solid rgba(255,255,255,0.3)',
                    color: '#fff',
                    borderRadius: 10,
                  }}
                >
                  刷新
                </Button>
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>

      <Row gutter={[20, 20]}>
        {services.map((svc) => (
          <Col xs={24} md={8} key={svc.key}>
            <Card
              style={{
                borderRadius: 14,
                border: 'none',
                boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                height: '100%',
              }}
              styles={{ body: { padding: 24 } }}
            >
              <Space size={12} style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
                <Space>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 10,
                      background: svc.status === 'ok' ? '#D1FAE5' : svc.status === 'error' ? '#FEE2E2' : '#F3F4F6',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 18,
                      color: svc.status === 'ok' ? '#10B981' : svc.status === 'error' ? '#EF4444' : '#9CA3AF',
                    }}
                  >
                    {svc.icon}
                  </div>
                  <div>
                    <Text strong>{svc.name}</Text>
                  </div>
                </Space>
                {svc.status === 'loading' ? (
                  <Spin size="small" />
                ) : svc.status === 'ok' ? (
                  <Tag icon={<CheckCircleOutlined />} color="success">
                    运行中
                  </Tag>
                ) : (
                  <Tag icon={<CloseCircleOutlined />} color="error">
                    离线
                  </Tag>
                )}
              </Space>

              {svc.status === 'ok' && svc.data && (
                <Descriptions column={1} size="small" style={{ marginTop: 8 }}>
                  {Object.entries(svc.data).map(([k, v]) => (
                    <Descriptions.Item key={k} label={k}>
                      <Text code style={{ fontSize: 12 }}>
                        {String(v)}
                      </Text>
                    </Descriptions.Item>
                  ))}
                </Descriptions>
              )}

              {svc.status === 'error' && svc.error && (
                <Alert
                  type="error"
                  message={svc.error}
                  showIcon
                  style={{ marginTop: 8, borderRadius: 8, fontSize: 12 }}
                />
              )}
            </Card>
          </Col>
        ))}
      </Row>

      <Divider />

      <Card
        title="环境信息"
        style={{
          borderRadius: 14,
          border: 'none',
          boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
        }}
      >
        <Descriptions column={{ xs: 1, sm: 2 }} bordered size="small">
          <Descriptions.Item label="前端框架">React 19 + TypeScript + Ant Design 5</Descriptions.Item>
          <Descriptions.Item label="后端框架">FastAPI + Python 3.13</Descriptions.Item>
          <Descriptions.Item label="支持站点">US / UK / DE / JP / CA / FR / IT / ES / AU / MX</Descriptions.Item>
          <Descriptions.Item label="数据查询引擎">Apache Doris (StarRocks)</Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );
}
