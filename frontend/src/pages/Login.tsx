import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Alert, Button, Form, Input, Tag, Typography } from 'antd';
import { GlobalOutlined, LockOutlined, ThunderboltOutlined, UserOutlined } from '@ant-design/icons';
import { useAuth } from '../context/AuthContext';

const { Title, Text, Paragraph } = Typography;

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
      const msg = (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        || (err as { message?: string })?.message;
      setError(msg || '登录失败，请检查用户名和密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-visual">
        <Tag className="tech-tag"><GlobalOutlined /> Global Commerce AI OS</Tag>
        <Title level={1}>LEANG AI一体化平台</Title>
        <Paragraph>
          为 LEANG 团队预设从商品、刊登、竞品、评论、数据、知识库到订单履约的智能运营入口。
        </Paragraph>
        <div className="login-signal">
          {['商品中台', 'AI Listing', '竞品洞察', '数据智能', '订单履约'].map(item => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </div>

      <div className="login-panel">
        <div className="login-card">
          <div className="login-logo">
            <div className="ai-brand-mark"><ThunderboltOutlined /></div>
            <div>
              <Title level={3}>欢迎登录</Title>
              <Text>进入 LEANG AI 运营控制台</Text>
            </div>
          </div>

          {error && (
            <Alert
              message={error}
              type="error"
              showIcon
              closable
              onClose={() => setError('')}
              style={{ marginBottom: 18 }}
            />
          )}

          <Form onFinish={handleSubmit} layout="vertical" size="large">
            <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input prefix={<UserOutlined />} placeholder="用户名" />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="密码" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              {loading ? '登录中...' : '登录'}
            </Button>
          </Form>
        </div>
      </div>
    </div>
  );
}
