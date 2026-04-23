import { useState, useRef, useEffect, useCallback } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Typography, Tag, Tooltip, Avatar, Dropdown, Badge } from 'antd';
import {
  ThunderboltOutlined,
  EditOutlined,
  BarChartOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  LineChartOutlined,
  MessageOutlined,
  RightOutlined,
  RobotOutlined,
  CloudServerOutlined,
  BulbOutlined,
  HomeOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  TeamOutlined,
  LockOutlined,
  CommentOutlined,
  AimOutlined,
} from '@ant-design/icons';
import { useAuth, PERMISSION_COLORS } from '../context/AuthContext';

const { Sider, Content, Header } = Layout;
const { Text } = Typography;

const LeangGeoSVG = ({ size = 40, color = '#F57C00', opacity = 0.12, style = {} }: {
  size?: number; color?: string; opacity?: number; style?: React.CSSProperties;
}) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={{ opacity, ...style }}>
    <g transform="translate(50,50)">
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
        <polygon key={deg} points="0,-42 12,-14 0,-6 -12,-14" fill={color} transform={`rotate(${deg})`} />
      ))}
    </g>
  </svg>
);

/* ══════════════════════════════════════
   彩虹色配置：从上到下 红→橙→绿→蓝→紫
   ══════════════════════════════════════ */

export const RAINBOW = [
  { from: '#FF6B6B', to: '#FF8A65' },   // 0 用户导航     — 红珊瑚
  { from: '#FF9800', to: '#FFB74D' },   // 1 LEANG-AGENT — 橙琥珀
  { from: '#4CAF50', to: '#26A69A' },   // 2 LEANG-DATA  — 绿翡翠
  { from: '#42A5F5', to: '#5C6BC0' },   // 3 LEANG-RAG   — 蓝靛蓝
  { from: '#AB47BC', to: '#7E57C2' },   // 4 系统管理     — 紫罗兰
];

export const BTN_RAINBOW = RAINBOW.map(c => `linear-gradient(135deg, ${c.from}, ${c.to})`);
export const BTN_RAINBOW_DARK = [
  `linear-gradient(135deg, #E05555, #D4714F)`,
  `linear-gradient(135deg, #E08600, #D4993A)`,
  `linear-gradient(135deg, #3D9140, #1E8A7E)`,
  `linear-gradient(135deg, #3189D4, #4A59A8)`,
  `linear-gradient(135deg, #9235A6, #6845AB)`,
];

export const PAGE_COLORS: Record<string, { from: string; to: string }> = {
  '/': RAINBOW[0],
  '/dashboard': RAINBOW[0],
  '/listing-optimize': RAINBOW[1],
  '/listing-optimize?tab=optimize': RAINBOW[1],
  '/listing-optimize?tab=analyze': RAINBOW[1],
  '/listing-optimize?tab=batch': RAINBOW[1],
  '/data-query': RAINBOW[2],
  '/data-analysis': RAINBOW[2],
  '/rag-chat': RAINBOW[3],
  '/system-status': RAINBOW[4],
};

function grad(idx: number) {
  const c = RAINBOW[idx];
  return `linear-gradient(135deg, ${c.from}, ${c.to})`;
}
function gradHover(idx: number) {
  const c = RAINBOW[idx];
  return `linear-gradient(135deg, ${c.to}, ${c.from})`;
}

function lerpColor(a: string, b: string, t: number) {
  const parse = (hex: string) => [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
  const [r1, g1, b1] = parse(a);
  const [r2, g2, b2] = parse(b);
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const bb = Math.round(b1 + (b2 - b1) * t);
  return `#${[r, g, bb].map(v => v.toString(16).padStart(2, '0')).join('')}`;
}

interface NavChild { key: string; label: string; icon: React.ReactNode; }

interface NavGroup {
  id: string;
  title: string;
  icon: React.ReactNode;
  colorIdx: number;
  children?: NavChild[];
  directKey?: string;
}

const ALL_NAV_GROUPS: (NavGroup & { minLevel: number })[] = [
  {
    id: 'home', title: '用户导航', icon: <HomeOutlined />, colorIdx: 0,
    directKey: '/', minLevel: 1,
  },
  {
    id: 'agent', title: 'LEANG-AGENT', icon: <RobotOutlined />, colorIdx: 1, minLevel: 2,
    children: [
      { key: '/listing?tab=optimize', label: 'Listing 优化', icon: <EditOutlined /> },
      { key: '/listing?tab=analyze', label: 'Listing 诊断', icon: <BarChartOutlined /> },
      { key: '/listing?tab=batch', label: '批量优化', icon: <AppstoreOutlined /> },
      { key: '/reviews', label: '评论分析', icon: <CommentOutlined /> },
      { key: '/competitors', label: '竞品发现', icon: <AimOutlined /> },
    ],
  },
  {
    id: 'data', title: 'LEANG-DATA', icon: <CloudServerOutlined />, colorIdx: 2, minLevel: 3,
    children: [
      { key: '/query', label: '数据查询', icon: <DatabaseOutlined /> },
      { key: '/analysis', label: '数据分析', icon: <LineChartOutlined /> },
    ],
  },
  {
    id: 'rag', title: 'LEANG-RAG', icon: <BulbOutlined />, colorIdx: 3, minLevel: 4,
    children: [
      { key: '/rag', label: '智能问答', icon: <MessageOutlined /> },
    ],
  },
  {
    id: 'system', title: '系统管理', icon: <SettingOutlined />, colorIdx: 4,
    directKey: '/system', minLevel: 5,
  },
  {
    id: 'users', title: '用户管理', icon: <TeamOutlined />, colorIdx: 4,
    directKey: '/users', minLevel: 5,
  },
];

const allFlatItems = ALL_NAV_GROUPS.flatMap(g =>
  g.directKey ? [{ key: g.directKey, label: g.title }] : (g.children || []),
);

function getActiveKey(pathname: string, search: string) {
  if (pathname === '/') return '/';
  if (pathname === '/system') return '/system';
  if (pathname === '/users') return '/users';
  if (pathname === '/listing') {
    const tab = new URLSearchParams(search).get('tab') || 'optimize';
    return `/listing?tab=${tab}`;
  }
  const full = pathname + search;
  return allFlatItems.find(i => i.key === full)?.key
    || allFlatItems.find(i => i.key.startsWith(pathname))?.key
    || '';
}

function getActiveGroupId(activeKey: string): string {
  for (const g of ALL_NAV_GROUPS) {
    if (g.directKey === activeKey) return g.id;
    if (g.children?.some(c => c.key === activeKey)) return g.id;
  }
  return '';
}

function childColor(parentIdx: number, nextIdx: number, childI: number, childCount: number) {
  const parentFrom = RAINBOW[parentIdx].from;
  const nextFrom = RAINBOW[Math.min(nextIdx, RAINBOW.length - 1)].from;
  const t = childCount <= 1 ? 0.3 : childI / (childCount - 1) * 0.6 + 0.15;
  return lerpColor(parentFrom, nextFrom, t);
}

function ChildrenWrap({ open, children }: { open: boolean; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (ref.current) setHeight(ref.current.scrollHeight);
  });

  return (
    <div style={{
      overflow: 'hidden',
      maxHeight: open ? (height ?? 300) : 0,
      opacity: open ? 1 : 0,
      transition: 'max-height 0.28s cubic-bezier(.4,0,.2,1), opacity 0.22s ease, margin-top 0.28s ease',
      marginTop: open ? 4 : 0,
    }} ref={ref}>
      {children}
    </div>
  );
}

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [animKey, setAnimKey] = useState(0);
  const prevPath = useRef(location.pathname + location.search);

  const userPermLevel = user?.permission_level ?? 1;
  const navGroups = ALL_NAV_GROUPS.filter(g => g.minLevel <= userPermLevel);

  useEffect(() => {
    const cur = location.pathname + location.search;
    if (cur !== prevPath.current) {
      prevPath.current = cur;
      setAnimKey(k => k + 1);
    }
  }, [location.pathname, location.search]);

  const activeKey = getActiveKey(location.pathname, location.search);
  const activeGroupId = getActiveGroupId(activeKey);
  const activeGroup = navGroups.find(g => g.id === activeGroupId);
  const activeColor = activeGroup ? RAINBOW[activeGroup.colorIdx] : RAINBOW[0];
  const currentTitle = allFlatItems.find(i => i.key === activeKey)?.label || 'LEANG AI';

  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    ALL_NAV_GROUPS.forEach(g => { init[g.id] = true; });
    return init;
  });

  const toggleGroup = useCallback((id: string) => setOpenGroups(prev => ({ ...prev, [id]: !prev[id] })), []);

  const handleNav = (key: string) => {
    const [path, qs] = key.split('?');
    navigate(qs ? `${path}?${qs}` : path);
  };

  const userMenuItems = [
    {
      key: 'profile',
      label: (
        <div style={{ padding: '4px 0' }}>
          <div style={{ fontWeight: 600, marginBottom: 2 }}>{user?.display_name}</div>
          <div style={{ fontSize: 11, color: '#999' }}>@{user?.username}</div>
          <div style={{ marginTop: 6 }}>
            <span style={{
              display: 'inline-block', padding: '1px 8px',
              borderRadius: 4, fontSize: 11, fontWeight: 600,
              background: PERMISSION_COLORS[userPermLevel] + '20',
              color: PERMISSION_COLORS[userPermLevel],
              border: `1px solid ${PERMISSION_COLORS[userPermLevel]}40`,
            }}>
              Lv.{userPermLevel} {user?.permission_name}
            </span>
          </div>
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
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible collapsed={collapsed} onCollapse={setCollapsed}
        width={220} collapsedWidth={64}
        style={{
          background: '#FAFAFA', borderRight: '1px solid #f0f0f0',
          overflow: 'hidden', position: 'sticky', top: 0, height: '100vh',
          display: 'flex', flexDirection: 'column',
        }}
        theme="light"
      >
        <div style={{ position: 'absolute', bottom: 50, left: -10, pointerEvents: 'none' }}>
          <LeangGeoSVG size={120} opacity={0.04} />
        </div>

        {/* Logo */}
        <div style={{
          height: collapsed ? 56 : 72, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 2,
          borderBottom: '1px solid #f0f0f0', padding: '10px 12px',
          flexShrink: 0, transition: 'height 0.2s',
        }}>
          <img src="/assets/logo.png" alt="LEANG"
            style={{ height: collapsed ? 26 : 30, transition: 'height 0.2s', mixBlendMode: 'multiply' }} />
          {!collapsed && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 4,
              color: '#FF9800', fontSize: 9, fontWeight: 600, letterSpacing: 1,
            }}>
              <ThunderboltOutlined style={{ fontSize: 9 }} /> AI 赋能平台
            </div>
          )}
        </div>

        {/* Nav */}
        <div style={{
          flex: 1, overflowY: 'auto', overflowX: 'hidden',
          padding: collapsed ? '10px 6px 60px' : '10px 10px 60px',
        }}>
          {navGroups.map((group, gi) => {
            const isGroupActive = activeGroupId === group.id;
            const isOpen = openGroups[group.id];
            const hasChildren = !!group.children?.length;
            const nextColorIdx = gi < navGroups.length - 1 ? navGroups[gi + 1].colorIdx : group.colorIdx;

            const handleHeaderClick = () => {
              if (group.directKey) handleNav(group.directKey);
              else toggleGroup(group.id);
            };

            /* ── Group header card ── */
            const headerCard = collapsed ? (
              <Tooltip title={group.title} placement="right">
                <div onClick={handleHeaderClick} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  height: 40, borderRadius: 10, cursor: 'pointer',
                  background: grad(group.colorIdx),
                  boxShadow: isGroupActive ? '0 3px 12px rgba(0,0,0,0.18)' : '0 1px 4px rgba(0,0,0,0.08)',
                  transition: 'all 0.25s', marginBottom: 4,
                }}>
                  <span style={{ color: '#fff', fontSize: 17 }}>{group.icon}</span>
                </div>
              </Tooltip>
            ) : (
              <div
                onClick={handleHeaderClick}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 14px', borderRadius: 12, cursor: 'pointer',
                  background: grad(group.colorIdx),
                  boxShadow: isGroupActive ? '0 4px 14px rgba(0,0,0,0.18)' : '0 2px 6px rgba(0,0,0,0.08)',
                  transition: 'all 0.25s', userSelect: 'none',
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLDivElement).style.background = gradHover(group.colorIdx);
                  (e.currentTarget as HTMLDivElement).style.boxShadow = '0 4px 18px rgba(0,0,0,0.22)';
                  (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-1px)';
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLDivElement).style.background = grad(group.colorIdx);
                  (e.currentTarget as HTMLDivElement).style.boxShadow = isGroupActive
                    ? '0 4px 14px rgba(0,0,0,0.18)' : '0 2px 6px rgba(0,0,0,0.08)';
                  (e.currentTarget as HTMLDivElement).style.transform = 'none';
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ color: '#fff', fontSize: 15, display: 'flex', alignItems: 'center' }}>
                    {group.icon}
                  </span>
                  <span style={{ color: '#fff', fontSize: 12, fontWeight: 700, letterSpacing: 1.5 }}>
                    {group.title}
                  </span>
                </div>
                {hasChildren && (
                  <RightOutlined style={{
                    color: 'rgba(255,255,255,0.7)', fontSize: 10,
                    transition: 'transform 0.25s',
                    transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)',
                  }} />
                )}
              </div>
            );

            return (
              <div key={group.id} style={{ marginBottom: 8 }}>
                {headerCard}

                {/* ── Children with interpolated rainbow colors ── */}
                {hasChildren && (
                  <ChildrenWrap open={!collapsed && isOpen}>
                    {group.children!.map((child, ci) => {
                      const isActive = activeKey === child.key;
                      const color = childColor(group.colorIdx, nextColorIdx, ci, group.children!.length);

                      const item = (
                        <div
                          key={child.key}
                          onClick={() => handleNav(child.key)}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 8,
                            padding: collapsed ? '8px 0' : '8px 12px 8px 20px',
                            marginBottom: 2, borderRadius: 8, cursor: 'pointer',
                            justifyContent: collapsed ? 'center' : 'flex-start',
                            background: isActive ? `${color}18` : 'transparent',
                            borderLeft: isActive ? `3px solid ${color}` : '3px solid transparent',
                            transition: 'all 0.15s', position: 'relative',
                          }}
                          onMouseEnter={e => {
                            if (!isActive) {
                              (e.currentTarget as HTMLDivElement).style.background = `${color}0D`;
                              (e.currentTarget as HTMLDivElement).style.borderLeft = `3px solid ${color}60`;
                            }
                          }}
                          onMouseLeave={e => {
                            if (!isActive) {
                              (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                              (e.currentTarget as HTMLDivElement).style.borderLeft = '3px solid transparent';
                            }
                          }}
                        >
                          <span style={{
                            fontSize: collapsed ? 16 : 14, display: 'flex', alignItems: 'center',
                            color: isActive ? color : '#999', transition: 'color 0.15s',
                          }}>
                            {child.icon}
                          </span>
                          {!collapsed && (
                            <span style={{
                              fontSize: 13, fontWeight: isActive ? 600 : 400,
                              color: isActive ? color : '#666', transition: 'color 0.15s',
                            }}>
                              {child.label}
                            </span>
                          )}
                        </div>
                      );
                      return collapsed ? (
                        <Tooltip key={child.key} title={child.label} placement="right">{item}</Tooltip>
                      ) : <div key={child.key}>{item}</div>;
                    })}
                  </ChildrenWrap>
                )}
              </div>
            );
          })}
        </div>
      </Sider>

      <Layout>
        <Header style={{
          background: `linear-gradient(135deg, ${activeColor.from}18, ${activeColor.to}10), #ffffff`,
          padding: '0 32px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          boxShadow: `0 1px 4px ${activeColor.from}20`,
          position: 'sticky', top: 0, zIndex: 100,
          borderBottom: `2px solid ${activeColor.from}30`,
          transition: 'all 0.3s ease',
        }}>
          <Text strong style={{ fontSize: 18, color: activeColor.from }}>{currentTitle}</Text>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <Tag style={{
              background: `linear-gradient(135deg, ${activeColor.from}20, ${activeColor.to}15)`,
              border: `1px solid ${activeColor.from}40`, color: activeColor.from,
              borderRadius: 16, padding: '2px 12px', fontSize: 12, fontWeight: 600,
            }}>
              <ThunderboltOutlined /> AI Powered
            </Tag>
            <div style={{ width: 1, height: 20, background: '#eee' }} />
            <div style={{
              background: `linear-gradient(135deg, ${activeColor.from}18, ${activeColor.to}10)`,
              borderRadius: 6, padding: '2px 6px', display: 'flex', alignItems: 'center',
            }}>
              <img src="/assets/logo.png" alt="LEANG" style={{ height: 22, mixBlendMode: 'multiply' }} />
            </div>
            <div style={{ width: 1, height: 20, background: '#eee' }} />
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight" trigger={['click']}>
              <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Badge
                  dot
                  color={PERMISSION_COLORS[userPermLevel]}
                  offset={[-2, 30]}
                >
                  <Avatar
                    size={32}
                    style={{
                      background: `linear-gradient(135deg, ${PERMISSION_COLORS[userPermLevel]}, ${PERMISSION_COLORS[userPermLevel]}aa)`,
                      fontSize: 13, fontWeight: 700,
                    }}
                    icon={userPermLevel === 5 ? <LockOutlined /> : <UserOutlined />}
                  >
                    {user?.display_name?.[0]?.toUpperCase()}
                  </Avatar>
                </Badge>
                {!collapsed && (
                  <div style={{ lineHeight: 1.2 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#333' }}>
                      {user?.display_name}
                    </div>
                    <div style={{ fontSize: 10, color: PERMISSION_COLORS[userPermLevel] }}>
                      Lv.{userPermLevel} {user?.permission_name}
                    </div>
                  </div>
                )}
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content style={{ margin: 24, minHeight: 'calc(100vh - 64px - 48px)' }}>
          <div key={animKey} className="page-transition">
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
