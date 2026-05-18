import { useState, useEffect, useCallback } from 'react';
import {
  Table, Button, Modal, Form, Input, Select, Switch,
  Space, Tag, Typography, Popconfirm, message, Card,
  Badge, Tooltip, Row, Col, Statistic, Checkbox, Divider,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  UserOutlined, CrownOutlined, TeamOutlined, SafetyCertificateOutlined,
  ApartmentOutlined, FilterOutlined,
} from '@ant-design/icons';
import { useAuth, PERMISSION_LEVELS, PERMISSION_COLORS } from '../context/AuthContext';
import api, { stiApi } from '../api';

const { Title, Text } = Typography;

interface UserRecord {
  username: string;
  display_name: string;
  permission_level: number;
  permission_name: string;
  enabled: boolean;
  custom_permissions?: string[] | null;
  data_restrictions?: Record<string, string[]> | null;
}

const RESTRICTION_FIELDS = [
  { key: 'store_name', label: '店铺', placeholder: '选择或搜索店铺，留空表示不限' },
  { key: 'brand', label: '品牌', placeholder: '选择或搜索品牌，留空表示不限' },
  { key: 'salesman', label: '运营', placeholder: '选择或搜索运营，留空表示不限' },
  { key: 'category_2', label: '类目', placeholder: '选择或搜索类目，留空表示不限' },
  { key: 'country_code', label: '国家', placeholder: '选择国家，留空表示不限' },
  { key: 'sales_apartment', label: '销售部门', placeholder: '选择部门，留空表示不限' },
];

// 各字段从数据库加载可选值的 SQL
const RESTRICTION_FIELD_SQL: Record<string, string> = {
  // 与三维诊断主查询字段来源保持一致（ads 表），避免选项值与实际数据不匹配导致“查不到”。
  store_name: "SELECT DISTINCT store_name AS val FROM ads_lingxing_sc_sales_daily_new WHERE store_name IS NOT NULL AND store_name != '' ORDER BY store_name LIMIT 300",
  brand: "SELECT DISTINCT brand AS val FROM dim_lingxing_product_info WHERE brand IS NOT NULL AND brand != '' ORDER BY brand LIMIT 300",
  salesman: "SELECT DISTINCT salesman AS val FROM dim_lingxing_product_info WHERE salesman IS NOT NULL AND salesman != '' ORDER BY salesman LIMIT 300",
  category_2: "SELECT DISTINCT category_2 AS val FROM ads_lingxing_sc_sales_daily_new WHERE category_2 IS NOT NULL AND category_2 != '' ORDER BY category_2 LIMIT 300",
  country_code: "SELECT DISTINCT country_code AS val FROM ads_lingxing_sc_sales_daily_new WHERE country_code IS NOT NULL AND country_code != '' ORDER BY country_code LIMIT 100",
  sales_apartment: "SELECT DISTINCT sales_apartment AS val FROM dim_lingxing_product_info WHERE sales_apartment IS NOT NULL AND sales_apartment != '' ORDER BY sales_apartment LIMIT 100",
};

const FEATURES = [
  {
    key: 'agent', label: 'LEANG-AGENT', desc: 'Listing优化、评论分析、竞品发现',
    color: '#FF9800', bg: '#FFF3E0',
  },
  {
    key: 'data', label: 'LEANG-DATA', desc: '数据查询、数据分析',
    color: '#4CAF50', bg: '#E8F5E9',
  },
  {
    key: 'rag', label: 'LEANG-RAG', desc: '智能问答知识库',
    color: '#42A5F5', bg: '#E3F2FD',
  },
  {
    key: 'system', label: '系统管理', desc: '系统状态监控',
    color: '#AB47BC', bg: '#F3E5F5',
  },
  {
    key: 'admin', label: '用户管理', desc: '用户账户与权限',
    color: '#f5222d', bg: '#FFF1F0',
  },
];

const LEVEL_FEATURES: Record<number, string[]> = {
  1: [],
  2: ['agent'],
  3: ['agent', 'data'],
  4: ['agent', 'data', 'rag'],
  5: ['agent', 'data', 'rag', 'system', 'admin'],
};

export default function UserManagement() {
  useAuth();
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserRecord | null>(null);
  const [checkedFeatures, setCheckedFeatures] = useState<string[]>([]);
  const [dataRestrictions, setDataRestrictions] = useState<Record<string, string[]>>({});
  const [restrictionOptions, setRestrictionOptions] = useState<Record<string, { label: string; value: string }[]>>({});
  const [restrictionLoading, setRestrictionLoading] = useState<Record<string, boolean>>({});
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

  const loadRestrictionOptionsForField = useCallback((fieldKey: string) => {
    const sql = RESTRICTION_FIELD_SQL[fieldKey];
    if (!sql || restrictionOptions[fieldKey] || restrictionLoading[fieldKey]) return;
    setRestrictionLoading(prev => ({ ...prev, [fieldKey]: true }));
    stiApi.execSql(sql)
      .then(res => {
        const opts = (res.data.rows || [])
          .map((r: Record<string, unknown>) => {
            const val = String(r.val ?? '').trim();
            return val ? { label: val, value: val } : null;
          })
          .filter(Boolean) as { label: string; value: string }[];
        setRestrictionOptions(prev => ({ ...prev, [fieldKey]: opts }));
      })
      .catch(() => {})
      .finally(() => setRestrictionLoading(prev => ({ ...prev, [fieldKey]: false })));
  }, [restrictionLoading, restrictionOptions]);

  const openCreate = () => {
    setEditingUser(null);
    form.resetFields();
    form.setFieldsValue({ permission_level: 1, enabled: true });
    setCheckedFeatures(LEVEL_FEATURES[1]);
    setDataRestrictions({});
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
    setCheckedFeatures(
      user.custom_permissions != null
        ? user.custom_permissions
        : LEVEL_FEATURES[user.permission_level] ?? [],
    );
    setDataRestrictions(user.data_restrictions ?? {});
    setModalOpen(true);
  };

  const handleLevelChange = (level: number) => {
    setCheckedFeatures(LEVEL_FEATURES[level] ?? []);
  };

  const handleSubmit = async (values: {
    username?: string;
    password?: string;
    display_name: string;
    permission_level: number;
    enabled: boolean;
  }) => {
    const levelDefault = LEVEL_FEATURES[values.permission_level] ?? [];
    const isDefault =
      checkedFeatures.length === levelDefault.length &&
      checkedFeatures.every(f => levelDefault.includes(f));
    const custom_permissions = isDefault ? null : checkedFeatures;

    // 过滤掉空数组的限制字段
    const cleanRestrictions = Object.fromEntries(
      Object.entries(dataRestrictions).filter(([, v]) => v && v.length > 0)
    );
    // 清空限制时显式传 {}，确保后端把旧 data_restrictions 真正删除。
    const data_restrictions = Object.keys(cleanRestrictions).length > 0 ? cleanRestrictions : {};

    try {
      if (editingUser) {
        await api.put(`/auth/users/${editingUser.username}`, {
          display_name: values.display_name,
          permission_level: values.permission_level,
          enabled: values.enabled,
          password: values.password || undefined,
          custom_permissions,
          data_restrictions,
        });
        message.success('用户更新成功');
      } else {
        await api.post('/auth/users', {
          username: values.username,
          password: values.password,
          display_name: values.display_name,
          permission_level: values.permission_level,
          enabled: values.enabled,
          custom_permissions,
          data_restrictions,
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
        <Space wrap>
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
          {record.custom_permissions != null && (
            <Tooltip title={`自定义功能：${record.custom_permissions.length > 0 ? record.custom_permissions.join('、') : '无'}`}>
              <Tag icon={<ApartmentOutlined />} color="cyan" style={{ borderRadius: 6, cursor: 'help' }}>
                自定义
              </Tag>
            </Tooltip>
          )}
          {record.data_restrictions && Object.keys(record.data_restrictions).length > 0 && (
            <Tooltip title={
              Object.entries(record.data_restrictions)
                .filter(([, v]) => v.length > 0)
                .map(([k, v]) => {
                  const f = RESTRICTION_FIELDS.find(f => f.key === k);
                  return `${f?.label ?? k}: ${v.join('、')}`;
                }).join(' | ')
            }>
              <Tag icon={<FilterOutlined />} color="orange" style={{ borderRadius: 6, cursor: 'help' }}>
                字段限制
              </Tag>
            </Tooltip>
          )}
        </Space>
      ),
      sorter: (a: UserRecord, b: UserRecord) => a.permission_level - b.permission_level,
    },
    {
      title: '可访问功能',
      key: 'features',
      render: (_: unknown, record: UserRecord) => {
        const perms = record.custom_permissions != null
          ? record.custom_permissions
          : LEVEL_FEATURES[record.permission_level] ?? [];
        if (perms.length === 0) return <Text type="secondary" style={{ fontSize: 12 }}>仅用户导航</Text>;
        return (
          <Space wrap size={4}>
            {FEATURES.filter(f => perms.includes(f.key)).map(f => (
              <Tag key={f.key} style={{
                borderRadius: 4, fontSize: 11, margin: 0,
                color: f.color, background: f.bg, borderColor: f.color + '40',
              }}>
                {f.label}
              </Tag>
            ))}
          </Space>
        );
      },
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

  const levelDefault = LEVEL_FEATURES[form.getFieldValue('permission_level')] ?? [];
  const isCustomized =
    checkedFeatures.length !== levelDefault.length ||
    checkedFeatures.some(f => !levelDefault.includes(f));

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
        width={520}
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

          {/* 预设等级 */}
          <Form.Item
            name="permission_level"
            label={
              <Space>
                <span>预设权限等级</span>
                <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                  选择后自动填充下方功能权限，可手动调整
                </Text>
              </Space>
            }
            rules={[{ required: true, message: '请选择权限等级' }]}
          >
            <Select placeholder="选择权限等级" onChange={handleLevelChange}>
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

          {/* 功能权限复选框 */}
          <div style={{
            border: `1px solid ${isCustomized ? '#1677ff' : '#f0f0f0'}`,
            borderRadius: 10,
            padding: '12px 14px',
            background: isCustomized ? '#f0f7ff' : '#fafafa',
            marginBottom: 16,
            transition: 'all 0.2s',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <Text strong style={{ fontSize: 13 }}>
                <ApartmentOutlined style={{ marginRight: 6, color: '#1677ff' }} />
                功能权限
                {isCustomized && (
                  <Tag color="blue" style={{ marginLeft: 8, fontSize: 11 }}>已自定义</Tag>
                )}
              </Text>
              <Button
                size="small"
                type="link"
                style={{ padding: 0, fontSize: 12 }}
                onClick={() => setCheckedFeatures(LEVEL_FEATURES[form.getFieldValue('permission_level')] ?? [])}
              >
                重置为预设
              </Button>
            </div>
            <Divider style={{ margin: '0 0 10px' }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {FEATURES.map(f => {
                const checked = checkedFeatures.includes(f.key);
                return (
                  <div
                    key={f.key}
                    onClick={() => setCheckedFeatures(prev =>
                      checked ? prev.filter(k => k !== f.key) : [...prev, f.key]
                    )}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '8px 12px', borderRadius: 8, cursor: 'pointer',
                      background: checked ? f.bg : '#fff',
                      border: `1px solid ${checked ? f.color + '60' : '#eee'}`,
                      transition: 'all 0.15s',
                    }}
                  >
                    <Checkbox checked={checked} onChange={() => {}} />
                    <div style={{ flex: 1 }}>
                      <Text strong style={{ fontSize: 13, color: checked ? f.color : '#333' }}>
                        {f.label}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                        {f.desc}
                      </Text>
                    </div>
                    {checked && (
                      <Tag style={{
                        background: f.color, color: '#fff', border: 'none',
                        borderRadius: 4, fontSize: 11,
                      }}>
                        已授权
                      </Tag>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* 数据查询字段限制 */}
          <div style={{
            border: `1px solid ${Object.values(dataRestrictions).some(v => v.length > 0) ? '#FF9800' : '#f0f0f0'}`,
            borderRadius: 10,
            padding: '12px 14px',
            background: Object.values(dataRestrictions).some(v => v.length > 0) ? '#FFF8E1' : '#fafafa',
            marginBottom: 16,
            transition: 'all 0.2s',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <Text strong style={{ fontSize: 13 }}>
                <FilterOutlined style={{ marginRight: 6, color: '#FF9800' }} />
                数据查询字段限制
                <Text type="secondary" style={{ fontSize: 11, marginLeft: 8, fontWeight: 400 }}>
                  留空表示不限，填写后该用户查询时自动过滤
                </Text>
              </Text>
              <Button
                size="small"
                type="link"
                danger
                style={{ padding: 0, fontSize: 12 }}
                onClick={() => setDataRestrictions({})}
              >
                清空全部
              </Button>
            </div>
            <Divider style={{ margin: '0 0 10px' }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {RESTRICTION_FIELDS.map(f => (
                <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Text style={{ minWidth: 60, fontSize: 12, color: '#555', flexShrink: 0 }}>
                    {f.label}：
                  </Text>
                  <Select
                    mode="multiple"
                    size="small"
                    style={{ flex: 1 }}
                    placeholder={f.placeholder}
                    value={dataRestrictions[f.key] ?? []}
                    onChange={vals => setDataRestrictions(prev => ({ ...prev, [f.key]: vals }))}
                    loading={restrictionLoading[f.key]}
                    options={restrictionOptions[f.key] ?? []}
                    showSearch
                    filterOption={(input, opt) =>
                      String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())
                    }
                    allowClear
                    maxTagCount="responsive"
                    notFoundContent={restrictionLoading[f.key] ? '加载中...' : '暂无数据'}
                    onDropdownVisibleChange={(open) => {
                      if (open) loadRestrictionOptionsForField(f.key);
                    }}
                  />
                </div>
              ))}
            </div>
          </div>

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
