import { useMemo, useState, type ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Layout, Typography, Tag, Tooltip, Avatar, Dropdown, Badge } from 'antd';
import {
  AimOutlined,
  AlertOutlined,
  ApartmentOutlined,
  ApiOutlined,
  AppstoreOutlined,
  BankOutlined,
  BarChartOutlined,
  BulbOutlined,
  CloudServerOutlined,
  CommentOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DownOutlined,
  EditOutlined,
  ExperimentOutlined,
  FundOutlined,
  HomeOutlined,
  InboxOutlined,
  LineChartOutlined,
  LockOutlined,
  LogoutOutlined,
  MessageOutlined,
  NodeIndexOutlined,
  PartitionOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  ShopOutlined,
  TagOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  TruckOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useAuth, PERMISSION_COLORS } from '../context/AuthContext';
import { APP_STAGE, APP_VERSION } from '../api';

const { Sider, Header, Content } = Layout;
const { Text } = Typography;

export const RAINBOW = [
  { from: '#1D9BF0', to: '#00E5FF' },
  { from: '#5B7CFA', to: '#21D4FD' },
  { from: '#00C2A8', to: '#68F5D2' },
  { from: '#8B5CF6', to: '#38BDF8' },
  { from: '#F59E0B', to: '#22D3EE' },
];

export const BTN_RAINBOW = RAINBOW.map(c => `linear-gradient(135deg, ${c.from}, ${c.to})`);
export const BTN_RAINBOW_DARK = RAINBOW.map(c => `linear-gradient(135deg, ${c.to}, ${c.from})`);

interface NavChild {
  key: string;
  label: string;
  icon: ReactNode;
  status?: 'ready' | 'planned';
}

interface NavGroup {
  id: string;
  title: string;
  subtitle: string;
  icon: ReactNode;
  colorIdx: number;
  minLevel: number;
  children: NavChild[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    id: 'cockpit',
    title: '公司经营驾驶舱',
    subtitle: '总览',
    icon: <DashboardOutlined />,
    colorIdx: 0,
    minLevel: 1,
    children: [
      { key: '/', label: '经营总览', icon: <HomeOutlined />, status: 'ready' },
      { key: '/architecture', label: '工作中心', icon: <PartitionOutlined />, status: 'planned' },
    ],
  },
  {
    id: 'operations',
    title: '供应链管理',
    subtitle: '库存 采购 物流',
    icon: <TruckOutlined />,
    colorIdx: 2,
    minLevel: 2,
    children: [
      { key: '/inventory', label: '库存健康与预警', icon: <InboxOutlined />, status: 'planned' },
      { key: '/supply-chain', label: '供应链履约监控', icon: <TruckOutlined />, status: 'planned' },
      { key: '/procurement', label: '采购与供应商协同', icon: <ApartmentOutlined />, status: 'planned' },
      { key: '/warehouse', label: '仓储物流看板', icon: <AlertOutlined />, status: 'planned' },
    ],
  },
  {
    id: 'ai-growth',
    title: '运营增长',
    subtitle: '选品 Listing 竞品',
    icon: <RobotOutlined />,
    colorIdx: 2,
    minLevel: 2,
    children: [
      { key: '/listing?tab=optimize', label: 'Listing 优化中心', icon: <EditOutlined />, status: 'ready' },
      { key: '/listing-records', label: 'Listing 优化记录', icon: <DatabaseOutlined />, status: 'ready' },
      { key: '/listing?tab=analyze', label: 'Listing 诊断中心', icon: <BarChartOutlined />, status: 'ready' },
      { key: '/listing?tab=batch', label: '批量运营优化', icon: <AppstoreOutlined />, status: 'ready' },
      { key: '/reviews', label: '评论洞察分析', icon: <CommentOutlined />, status: 'ready' },
      { key: '/competitors', label: '竞品情报中心', icon: <AimOutlined />, status: 'ready' },
      { key: '/market-analysis', label: '市场分析', icon: <LineChartOutlined />, status: 'ready' },
      { key: '/positioning', label: '产品定位分析', icon: <TagOutlined />, status: 'ready' },
      { key: '/ads', label: '广告投放策略', icon: <ExperimentOutlined />, status: 'ready' },
    ],
  },
  {
    id: 'finance-agent',
    title: '财务管理',
    subtitle: '利润 成本 回款',
    icon: <BankOutlined />,
    colorIdx: 4,
    minLevel: 2,
    children: [
      { key: '/finance-agent/profit', label: '经营利润分析', icon: <FundOutlined />, status: 'planned' },
      { key: '/finance-agent/cost', label: '成本核算中心', icon: <BarChartOutlined />, status: 'planned' },
      { key: '/finance-agent/cashflow', label: '回款与现金流', icon: <LineChartOutlined />, status: 'planned' },
    ],
  },
  {
    id: 'product-agent',
    title: '产品管理',
    subtitle: '选品 开发 上新',
    icon: <ShopOutlined />,
    colorIdx: 1,
    minLevel: 2,
    children: [
      { key: '/product-agent/selection', label: '市场选品研究', icon: <BulbOutlined />, status: 'planned' },
      { key: '/product-agent/development', label: '产品开发管理', icon: <ShopOutlined />, status: 'planned' },
      { key: '/product-agent/listing', label: '新品上架管理', icon: <ApiOutlined />, status: 'planned' },
    ],
  },
  {
    id: 'hr-agent',
    title: '组织人事',
    subtitle: '招聘 绩效 组织',
    icon: <TeamOutlined />,
    colorIdx: 3,
    minLevel: 2,
    children: [
      { key: '/hr-agent/recruiting', label: '招聘与入职', icon: <UserOutlined />, status: 'planned' },
      { key: '/hr-agent/performance', label: '绩效管理', icon: <ThunderboltOutlined />, status: 'planned' },
      { key: '/hr-agent/org', label: '组织发展', icon: <ApartmentOutlined />, status: 'planned' },
    ],
  },
  {
    id: 'data-ai',
    title: '数据与知识智能',
    subtitle: 'BI RAG 工作流',
    icon: <CloudServerOutlined />,
    colorIdx: 3,
    minLevel: 3,
    children: [
      { key: '/query', label: '自然语言查数', icon: <DatabaseOutlined />, status: 'ready' },
      { key: '/analysis', label: '经营数据分析', icon: <LineChartOutlined />, status: 'ready' },
      { key: '/rag', label: '企业知识库', icon: <MessageOutlined />, status: 'ready' },
      { key: '/workflow', label: '自动化工作流', icon: <NodeIndexOutlined />, status: 'planned' },
    ],
  },
  {
    id: 'governance',
    title: '系统治理',
    subtitle: '权限 模型 安全',
    icon: <SafetyCertificateOutlined />,
    colorIdx: 4,
    minLevel: 5,
    children: [
      { key: '/system', label: '系统状态', icon: <SettingOutlined />, status: 'ready' },
      { key: '/users', label: '用户与权限', icon: <UserOutlined />, status: 'ready' },
      { key: '/modelops', label: '模型与提示词治理', icon: <BulbOutlined />, status: 'planned' },
    ],
  },
];

const flatItems = NAV_GROUPS.flatMap(group => group.children);

function getActiveKey(pathname: string, search: string) {
  if (pathname === '/listing') {
    const tab = new URLSearchParams(search).get('tab') || 'optimize';
    return `/listing?tab=${tab}`;
  }
  return flatItems.find(item => item.key === pathname)?.key
    || flatItems.find(item => item.key.startsWith(pathname))?.key
    || pathname;
}

function platformPath(key: string) {
  const [path, qs] = key.split('?');
  return qs ? `${path}?${qs}` : path;
}

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout, canAccess } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [openGroups, setOpenGroups] = useState<Set<string>>(
    () => new Set(NAV_GROUPS.map(group => group.id)),
  );

  const userPermLevel = user?.permission_level ?? 1;
  const activeKey = getActiveKey(location.pathname, location.search);
  const activeItem = flatItems.find(item => item.key === activeKey);

  const navGroups = useMemo(() => NAV_GROUPS.filter(group => {
    if (group.id === 'cockpit') return true;
    if (group.id === 'ai-growth') return canAccess('agent');
    if (group.id === 'data-ai') return canAccess('data') || canAccess('rag');
    if (group.id === 'governance') return canAccess('system') || canAccess('admin');
    return userPermLevel >= group.minLevel;
  }), [canAccess, userPermLevel]);

  const toggleGroup = (groupId: string) => {
    setOpenGroups(prev => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  const userMenuItems = [
    {
      key: 'profile',
      label: (
        <div style={{ minWidth: 180 }}>
          <div style={{ fontWeight: 700, color: '#DFF7FF' }}>{user?.display_name}</div>
          <div style={{ fontSize: 12, color: '#86A8BD', marginTop: 2 }}>@{user?.username}</div>
          <Tag style={{ marginTop: 8, borderColor: '#1E6B8C', color: '#AEEBFF', background: '#092031' }}>
            Lv.{userPermLevel} {user?.permission_name}
          </Tag>
        </div>
      ),
      disabled: true,
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
      onClick: () => { logout(); navigate('/login'); },
    },
  ];

  return (
    <Layout className="ai-shell">
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        width={286}
        collapsedWidth={78}
        className="ai-sider"
        trigger={null}
      >
        <div className="ai-brand" onClick={() => navigate('/')}>
          <div className="ai-brand-mark">
            <ThunderboltOutlined />
          </div>
          {!collapsed && (
            <div>
              <div className="ai-brand-title">LEANG AI一体化平台</div>
              <div className="ai-brand-subtitle">Company Intelligence OS</div>
            </div>
          )}
        </div>

        <div className="ai-nav">
          {navGroups.map(group => {
            const activeInGroup = group.children.some(item => item.key === activeKey);
            const tone = RAINBOW[group.colorIdx];
            const isOpen = !collapsed && (openGroups.has(group.id) || activeInGroup);
            const groupButton = (
              <button
                type="button"
                className={`ai-nav-group-title ${activeInGroup ? 'is-active' : ''} ${isOpen ? 'is-open' : ''}`}
                style={{
                  '--nav-from': tone.from,
                  '--nav-to': tone.to,
                } as React.CSSProperties}
                onClick={() => collapsed ? setCollapsed(false) : toggleGroup(group.id)}
              >
                <span className="ai-nav-group-icon" style={{ color: tone.to }}>{group.icon}</span>
                {!collapsed && (
                  <>
                    <span className="ai-nav-group-copy">
                      <strong>{group.title}</strong>
                      <em>{group.subtitle}</em>
                    </span>
                    <DownOutlined className="ai-nav-group-arrow" />
                  </>
                )}
              </button>
            );
            return (
              <div className="ai-nav-group" key={group.id}>
                {collapsed ? (
                  <Tooltip title={group.title} placement="right">{groupButton}</Tooltip>
                ) : groupButton}
                {isOpen && (
                  <div className="ai-nav-sublist">
                    {group.children.map(item => {
                    const isActive = item.key === activeKey;
                    const navItem = (
                      <button
                        type="button"
                        className={`ai-nav-item ${isActive ? 'is-active' : ''}`}
                        style={{
                          '--nav-from': tone.from,
                          '--nav-to': tone.to,
                        } as React.CSSProperties}
                        onClick={() => navigate(platformPath(item.key))}
                      >
                        <span className="ai-nav-icon">{item.icon}</span>
                        {!collapsed && (
                          <>
                            <span className="ai-nav-label">{item.label}</span>
                            {item.status === 'planned' && <span className="ai-nav-chip">预设</span>}
                          </>
                        )}
                      </button>
                    );
                    return collapsed ? (
                      <Tooltip key={item.key} title={item.label} placement="right">{navItem}</Tooltip>
                    ) : <div key={item.key}>{navItem}</div>;
                  })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Sider>

      <Layout className="ai-main">
        <Header className="ai-header">
          <div>
            <Text className="ai-current-title">{activeItem?.label || '经营总览'}</Text>
            <div className="ai-current-subtitle">LEANG 公司级 AI 运营控制台</div>
          </div>
          <div className="ai-header-actions">
            <Tag className="ai-version">{APP_VERSION} {APP_STAGE}</Tag>
            <Tag className="ai-powered"><ThunderboltOutlined /> AI Powered</Tag>
            <button type="button" className="ai-collapse" onClick={() => setCollapsed(v => !v)}>
              {collapsed ? '展开' : '收起'}
            </button>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight" trigger={['click']}>
              <div className="ai-user">
                <Badge dot color={PERMISSION_COLORS[userPermLevel]} offset={[-4, 28]}>
                  <Avatar
                    size={34}
                    style={{ background: `linear-gradient(135deg, ${PERMISSION_COLORS[userPermLevel]}, #16B8FF)` }}
                    icon={userPermLevel === 5 ? <LockOutlined /> : <UserOutlined />}
                  >
                    {user?.display_name?.[0]?.toUpperCase()}
                  </Avatar>
                </Badge>
                <span>{user?.display_name}</span>
              </div>
            </Dropdown>
          </div>
        </Header>

        <Content className="ai-content">
          <div className="ai-content-grid" />
          <div className="page-transition">
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
