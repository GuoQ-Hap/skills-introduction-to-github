import { useState, useEffect, useCallback } from 'react';
import {
  Table, Button, Modal, Form, Input, Select, Switch,
  Space, Tag, Typography, Popconfirm, message, Card,
  Badge, Tooltip, Row, Col, Statistic,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  UserOutlined, CrownOutlined, TeamOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons';
import { useAuth, PERMISSION_LEVELS, PERMISSION_COLORS } from '../context/AuthContext';
import api from '../api';

const { Title, Text } = Typography;

interface UserRecord {
  username: string;
  display_name: string;
  permission_level: number;
  permission_name: string;
  enabled: boolean;
}

export default function UserManagement() {
  useAuth();
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserRecord | null>(null);
  const [form] = Form.useForm();

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/auth/users');
      setUsers(res.data);
    } catch {
      message.error('获取用户列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const openCreate = () => {
    setEditingUser(null);
    form.resetFields();
    form.setFieldsValue({ permission_level: 1, enabled: true });
    setModalOpen(true);
  };

  const openEdit = (user: UserRecord) => {
    setEditingUser(user);
    form.setFieldsValue({
      display_name: user.display_name,
      permission_level: user.permission_level,
      enabled: user.enabled,
      password: '',
    });
    setModalOpen(true);
  };

  const handleSubmit = async (values: {
    username?: string;
    password?: string;
    display_name: string;
    permission_level: number;
    enabled: boolean;
  }) => {
    try {
      if (editingUser) {
        await api.put(`/auth/users/${editingUser.username}`, {
          display_name: values.display_name,
          permission_level: values.permission_level,
          enabled: values.enabled,
          password: values.password || undefined,
        });
        message.success('用户更新成功');
      } else {
        await api.post('/auth/users', {
          username: values.username,
          password: values.password,
          display_name: values.display_name,
          permission_level: values.permission_level,
          enabled: values.enabled,
        });
        message.success('用户创建成功');
      }
      setModalOpen(false);
      fetchUsers();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(msg || '操作失败');
    }
  };

  const handleDelete = async (username: string) => {
    try {
      await api.delete(`/auth/users/${username}`);
      message.success('用户已删除');
      fetchUsers();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(msg || '删除失败');
    }
  };

  const levelCounts = PERMISSION_LEVELS.map(pl => ({
    ...pl,
    count: users.filter(u => u.permission_level === pl.value).length,
  }));

  const columns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      render: (v: string) => (
        <Space>
          <UserOutlined style={{ color: '#999' }} />
          <Text strong>{v}</Text>
          {v === 'leangadmin' && (
            <Tag icon={<CrownOutlined />} color="gold">内置管理员</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '显示名称',
      dataIndex: 'display_name',
      key: 'display_name',
    },
    {
      title: '权限等级',
      dataIndex: 'permission_level',
      key: 'permission_level',
      render: (level: number, record: UserRecord) => (
        <Space>
          <div style={{
            width: 22, height: 22, borderRadius: 5,
            background: PERMISSION_COLORS[level],
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: 11, fontWeight: 700,
          }}>
            {level}
          </div>
          <Tag color={PERMISSION_COLORS[level]} style={{ borderRadius: 6 }}>
            {record.permission_name}
          </Tag>
        </Space>
      ),
      sorter: (a: UserRecord, b: UserRecord) => a.permission_level - b.permission_level,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Badge
          status={enabled ? 'success' : 'default'}
          text={<Text style={{ color: enabled ? '#52c41a' : '#999' }}>{enabled ? '启用' : '禁用'}</Text>}
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: UserRecord) => (
        <Space>
          <Tooltip title="编辑用户">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => openEdit(record)}
              style={{ color: '#1677ff' }}
            />
          </Tooltip>
          {record.username !== 'leangadmin' && (
            <Popconfirm
              title="确认删除"
              description={`确定要删除用户 "${record.display_name}" 吗？`}
              onConfirm={() => handleDelete(record.username)}
              okText="删除"
              okType="danger"
              cancelText="取消"
            >
              <Tooltip title="删除用户">
                <Button type="text" icon={<DeleteOutlined />} danger />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '0 4px' }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0, marginBottom: 4 }}>
          <TeamOutlined style={{ marginRight: 8, color: '#f5222d' }} />
          用户授权管理
        </Title>
        <Text type="secondary">管理系统用户账户及其权限等级</Text>
      </div>

      {/* 统计卡片 */}
      <Row gutter={12} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <Card size="small" style={{ borderRadius: 10, background: 'linear-gradient(135deg, #f5f5f5, #fafafa)' }}>
            <Statistic
              title={<Text style={{ fontSize: 12 }}>总用户数</Text>}
              value={users.length}
              prefix={<TeamOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small" style={{ borderRadius: 10, background: 'linear-gradient(135deg, #fff7e6, #fffbe6)' }}>
            <Statistic
              title={<Text style={{ fontSize: 12 }}>已启用</Text>}
              value={users.filter(u => u.enabled).length}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        {levelCounts.slice(0, 4).map(pl => (
          <Col span={4} key={pl.value}>
            <Card size="small" style={{ borderRadius: 10 }}>
              <Statistic
                title={<Text style={{ fontSize: 11 }}>{pl.label}</Text>}
                value={pl.count}
                valueStyle={{ color: PERMISSION_COLORS[pl.value], fontSize: 20 }}
                prefix={<SafetyCertificateOutlined />}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* 工具栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openCreate}
            style={{
              background: 'linear-gradient(135deg, #f5222d, #ff4d4f)',
              border: 'none',
              borderRadius: 8,
              boxShadow: '0 2px 8px rgba(245,34,45,0.3)',
            }}
          >
            新增用户
          </Button>
          <Button icon={<ReloadOutlined />} onClick={fetchUsers} loading={loading} style={{ borderRadius: 8 }}>
            刷新
          </Button>
        </Space>
        <Text type="secondary" style={{ fontSize: 12 }}>
          共 {users.length} 个用户
        </Text>
      </div>

      <Table
        dataSource={users}
        columns={columns}
        rowKey="username"
        loading={loading}
        pagination={{ pageSize: 10, showSizeChanger: false }}
        style={{ borderRadius: 12, overflow: 'hidden' }}
        rowClassName={(record) => record.enabled ? '' : 'user-disabled'}
      />

      <Modal
        title={
          <Space>
            {editingUser ? <EditOutlined /> : <PlusOutlined />}
            {editingUser ? `编辑用户：${editingUser.display_name}` : '新增用户'}
          </Space>
        }
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        width={480}
        styles={{ body: { paddingTop: 16 } }}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          {!editingUser && (
            <Form.Item
              name="username"
              label="用户名"
              rules={[
                { required: true, message: '请输入用户名' },
                { pattern: /^[a-zA-Z0-9_]+$/, message: '只能包含字母、数字和下划线' },
                { min: 3, message: '用户名至少3个字符' },
              ]}
            >
              <Input prefix={<UserOutlined />} placeholder="登录用户名（字母/数字/下划线）" />
            </Form.Item>
          )}

          <Form.Item
            name="display_name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="用户显示名称" />
          </Form.Item>

          <Form.Item
            name="password"
            label={editingUser ? '新密码（留空不修改）' : '密码'}
            rules={editingUser ? [] : [{ required: true, message: '请输入密码' }, { min: 6, message: '密码至少6位' }]}
          >
            <Input.Password placeholder={editingUser ? '留空则不修改密码' : '至少6位'} />
          </Form.Item>

          <Form.Item
            name="permission_level"
            label="权限等级"
            rules={[{ required: true, message: '请选择权限等级' }]}
          >
            <Select placeholder="选择权限等级">
              {PERMISSION_LEVELS.map(pl => (
                <Select.Option key={pl.value} value={pl.value}>
                  <Space>
                    <div style={{
                      width: 16, height: 16, borderRadius: 4,
                      background: PERMISSION_COLORS[pl.value],
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      color: '#fff', fontSize: 10, fontWeight: 700,
                    }}>
                      {pl.value}
                    </div>
                    <strong>{pl.label}</strong>
                    <Text type="secondary" style={{ fontSize: 12 }}>— {pl.description}</Text>
                  </Space>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="enabled" label="账户状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setModalOpen(false)}>取消</Button>
              <Button
                type="primary"
                htmlType="submit"
                style={{ background: 'linear-gradient(135deg, #f5222d, #ff4d4f)', border: 'none' }}
              >
                {editingUser ? '保存修改' : '创建用户'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
