import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Form, Input, Button, Typography, Alert, Space } from 'antd';
import { UserOutlined, LockOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useAuth } from '../context/AuthContext';

const { Title, Text } = Typography;

const LeangGeoSVG = ({ size = 80, color = '#FF9800', opacity = 0.15 }: {
  size?: number; color?: string; opacity?: number;
}) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={{ opacity }}>
    <g transform="translate(50,50)">
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
        <polygon key={deg} points="0,-42 12,-14 0,-6 -12,-14" fill={color} transform={`rotate(${deg})`} />
      ))}
    </g>
  </svg>
);

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const from = (location.state as { from?: string })?.from || '/';

  const handleSubmit = async (values: { username: string; password: string }) => {
    setLoading(true);
    setError('');
    try {
      await login(values.username, values.password);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || '登录失败，请检查用户名和密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #FFF8F0 0%, #FFF3E0 40%, #F3E5F5 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* 背景装饰 */}
      <div style={{ position: 'absolute', top: -40, left: -40, pointerEvents: 'none' }}>
        <LeangGeoSVG size={200} color="#FF9800" opacity={0.06} />
      </div>
      <div style={{ position: 'absolute', bottom: -60, right: -60, pointerEvents: 'none' }}>
        <LeangGeoSVG size={280} color="#AB47BC" opacity={0.05} />
      </div>
      <div style={{ position: 'absolute', top: '30%', right: '10%', pointerEvents: 'none' }}>
        <LeangGeoSVG size={120} color="#42A5F5" opacity={0.06} />
      </div>

      {/* 登录卡片 */}
      <div style={{
        background: '#ffffff',
        borderRadius: 20,
        padding: '48px 40px',
        width: 400,
        boxShadow: '0 20px 60px rgba(0,0,0,0.1), 0 4px 20px rgba(255,152,0,0.1)',
        position: 'relative',
        zIndex: 1,
      }}>
        {/* Logo 区域 */}
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <div style={{ position: 'relative', display: 'inline-block', marginBottom: 12 }}>
            <img
              src="/assets/logo.png"
              alt="LEANG"
              style={{ height: 52, mixBlendMode: 'multiply' }}
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 4 }}>
            <ThunderboltOutlined style={{ color: '#FF9800', fontSize: 14 }} />
            <Text style={{ color: '#FF9800', fontSize: 11, fontWeight: 700, letterSpacing: 2 }}>
              AI 赋能平台
            </Text>
          </div>
          <Title level={3} style={{ margin: 0, color: '#1a1a1a', fontWeight: 700 }}>
            欢迎登录
          </Title>
          <Text type="secondary" style={{ fontSize: 13, marginTop: 4, display: 'block' }}>
            请使用您的账户凭据登录系统
          </Text>
        </div>

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            closable
            onClose={() => setError('')}
            style={{ marginBottom: 20, borderRadius: 8 }}
          />
        )}

        <Form onFinish={handleSubmit} layout="vertical" size="large">
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined style={{ color: '#bbb' }} />}
              placeholder="用户名"
              style={{ borderRadius: 10, height: 46 }}
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: '#bbb' }} />}
              placeholder="密码"
              style={{ borderRadius: 10, height: 46 }}
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
              style={{
                height: 48,
                borderRadius: 10,
                background: 'linear-gradient(135deg, #FF9800, #FFB74D)',
                border: 'none',
                fontSize: 15,
                fontWeight: 600,
                boxShadow: '0 4px 16px rgba(255,152,0,0.35)',
              }}
            >
              {loading ? '登录中...' : '登 录'}
            </Button>
          </Form.Item>
        </Form>

        <div style={{ marginTop: 28, padding: '16px', background: '#FAFAFA', borderRadius: 10 }}>
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 600 }}>权限等级说明</Text>
            {[
              { level: 1, name: '基础用户', desc: '用户导航' },
              { level: 2, name: '操作员', desc: '+ LEANG-AGENT' },
              { level: 3, name: '分析师', desc: '+ LEANG-DATA' },
              { level: 4, name: '高级用户', desc: '+ LEANG-RAG' },
              { level: 5, name: '超级管理员', desc: '+ 用户管理' },
            ].map(item => (
              <div key={item.level} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 18, height: 18, borderRadius: 4,
                  background: ['#8d8d8d', '#1677ff', '#52c41a', '#722ed1', '#f5222d'][item.level - 1],
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#fff', fontSize: 10, fontWeight: 700, flexShrink: 0,
                }}>
                  {item.level}
                </div>
                <Text style={{ fontSize: 11, color: '#555' }}>
                  <strong>{item.name}</strong>：{item.desc}
                </Text>
              </div>
            ))}
          </Space>
        </div>
      </div>
    </div>
  );
}
