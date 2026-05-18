import { useState, useRef, useEffect } from 'react';
import {
  Card,
  Input,
  Button,
  Typography,
  Space,
  Tag,
  Spin,
  Table,
  Collapse,
} from 'antd';
import {
  SendOutlined,
  DatabaseOutlined,
  UserOutlined,
  RobotOutlined,
  CodeOutlined,
  ClearOutlined,
  AimOutlined,
  TableOutlined,
  FileSearchOutlined,
  BarChartOutlined,
  BulbOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import { stiApi, getCurrentUsername, getUserScopedKey, applyLocalDataRestrictions, type SQLExecResponse } from '../api';
import { useAuth } from '../context/AuthContext';
import { useChatCache } from '../hooks/useChatCache';
import ModelSelector from '../components/ModelSelector';
import { RAINBOW, BTN_RAINBOW } from '../layouts/MainLayout';

const { Paragraph } = Typography;
const DATA_COLOR = RAINBOW[2];
const R = BTN_RAINBOW;

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sql?: string;
  data?: Record<string, unknown>;
  intent?: string;
  tables?: string[];
  loading?: boolean;
}

export default function DataQuery() {
  const { user, refreshUser } = useAuth();
  const username = getCurrentUsername();
  const chatKey = getUserScopedKey('lda_chat');
  const sessionKey = getUserScopedKey('lda_session_id');
  const modelKey = getUserScopedKey('lda_model');

  const { messages, setMessages, clearCache } = useChatCache<ChatMessage>(chatKey);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string | undefined>(
    () => localStorage.getItem(modelKey) || undefined,
  );
  const [sessionId] = useState(() => {
    const cached = sessionStorage.getItem(sessionKey);
    if (cached) return cached;
    const id = `${username}_${Array.from(crypto.getRandomValues(new Uint8Array(12)), b => b.toString(16).padStart(2, '0')).join('')}`;
    sessionStorage.setItem(sessionKey, id);
    return id;
  });
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    refreshUser().catch(() => {});
  }, [refreshUser]);

  const handleModelChange = (v: string | undefined) => {
    setSelectedModel(v);
    if (v) localStorage.setItem(modelKey, v);
    else localStorage.removeItem(modelKey);
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    const userMsg: ChatMessage = { role: 'user', content: text };
    const loadingMsg: ChatMessage = { role: 'assistant', content: '', loading: true };
    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setLoading(true);

    try {
      let dataRestrictions = user?.data_restrictions;
      if (dataRestrictions == null) {
        try {
          const raw = localStorage.getItem('leang_user_info');
          if (raw) dataRestrictions = JSON.parse(raw)?.data_restrictions ?? undefined;
        } catch { /* */ }
      }
      const { data } = await stiApi.chat({
        session_id: sessionId,
        message: text,
        user_id: username,
        model: selectedModel,
        data_restrictions: dataRestrictions ?? undefined,
      });

      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: data.analysis || data.error || '查询完成',
        sql: data.sql || undefined,
        data: data.data
          ? (applyLocalDataRestrictions(data.data as unknown as SQLExecResponse) as unknown as Record<string, unknown>)
          : undefined,
        intent: data.intent,
        tables: data.matched_tables?.map((t: any) => t.table || t.name || '').filter(Boolean),
      };

      setMessages((prev) => [...prev.slice(0, -1), assistantMsg]);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { role: 'assistant', content: `请求失败：${e.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const renderDataTable = (data: Record<string, unknown>) => {
    const cols = (data.columns as string[]) || [];
    const rows = (data.rows as Record<string, unknown>[]) || [];
    if (!cols.length) return null;

    const tableColumns = cols.map((col) => ({
      title: col,
      dataIndex: col,
      key: col,
      ellipsis: true,
      width: 150,
    }));

    return (
      <Table
        size="small"
        columns={tableColumns}
        dataSource={rows.map((r, i) => ({ ...r, _key: i }))}
        rowKey="_key"
        scroll={{ x: 'max-content', y: 300 }}
        pagination={{ pageSize: 20, size: 'small' }}
        style={{ marginTop: 8 }}
      />
    );
  };

  const INTENT_LABELS: Record<string, { label: string; color: string }> = {
    query: { label: '数据查询', color: '#4CAF50' },
    chat: { label: '对话交流', color: '#42A5F5' },
    followup: { label: '追问分析', color: '#FF9800' },
  };

  const renderAssistantContent = (msg: ChatMessage) => {
    if (msg.loading) return <Spin size="small" />;

    const { intent, tables, sql, content, data } = msg;
    const intentInfo = INTENT_LABELS[intent || ''] || { label: intent || '', color: '#999' };
    const isQuery = intent === 'query' || (sql && sql.length > 0 && !sql.startsWith('--'));
    const isChat = intent === 'chat';
    const rowCount = (data as { row_count?: number } | undefined)?.row_count;

    return (
      <div>
        {/* ── 查询步骤面板（仅数据查询/追问时展示） ── */}
        {!isChat && (
          <div style={{
            background: '#f8faff',
            border: '1px solid #e6efff',
            borderRadius: 10,
            marginBottom: 10,
            overflow: 'hidden',
          }}>
            {/* 步骤标题行 */}
            <div style={{
              padding: '8px 14px',
              background: 'linear-gradient(135deg, #e8f0fe, #f0f7ff)',
              borderBottom: '1px solid #e6efff',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <FileSearchOutlined style={{ color: '#1677ff', fontSize: 13 }} />
              <span style={{ fontSize: 12, fontWeight: 600, color: '#1677ff' }}>查询流程</span>
            </div>

            <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {/* Step 1 意图识别 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{
                  width: 20, height: 20, borderRadius: '50%',
                  background: intentInfo.color, color: '#fff',
                  fontSize: 10, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>1</div>
                <AimOutlined style={{ color: intentInfo.color, fontSize: 13 }} />
                <span style={{ fontSize: 12, color: '#555', minWidth: 56 }}>意图识别</span>
                <Tag style={{
                  background: intentInfo.color + '15',
                  color: intentInfo.color,
                  border: `1px solid ${intentInfo.color}40`,
                  borderRadius: 10, fontSize: 11, margin: 0,
                }}>
                  {intentInfo.label}
                </Tag>
              </div>

              {/* Step 2 匹配数据表 */}
              {tables && tables.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                  <div style={{
                    width: 20, height: 20, borderRadius: '50%',
                    background: '#4CAF50', color: '#fff',
                    fontSize: 10, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>2</div>
                  <TableOutlined style={{ color: '#4CAF50', fontSize: 13, marginTop: 2 }} />
                  <span style={{ fontSize: 12, color: '#555', minWidth: 56, paddingTop: 1 }}>匹配数据表</span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {tables.map(t => (
                      <Tag key={t} style={{
                        background: '#E8F5E9', color: '#388E3C',
                        border: '1px solid #C8E6C9',
                        borderRadius: 4, fontSize: 11, margin: 0,
                      }}>
                        {t}
                      </Tag>
                    ))}
                  </div>
                </div>
              )}

              {/* Step 3 SQL */}
              {isQuery && sql && !sql.startsWith('--') && (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                  <div style={{
                    width: 20, height: 20, borderRadius: '50%',
                    background: '#AB47BC', color: '#fff',
                    fontSize: 10, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>3</div>
                  <CodeOutlined style={{ color: '#AB47BC', fontSize: 13, marginTop: 2 }} />
                  <span style={{ fontSize: 12, color: '#555', minWidth: 56, paddingTop: 1 }}>生成 SQL</span>
                  <div style={{ flex: 1 }}>
                    <Collapse
                      size="small"
                      ghost
                      style={{ background: 'transparent' }}
                      items={[{
                        key: 'sql',
                        label: <span style={{ fontSize: 11, color: '#AB47BC' }}>查看 SQL</span>,
                        children: (
                          <div style={{
                            background: '#1E1E2E',
                            color: '#A6E3A1',
                            padding: '10px 14px',
                            borderRadius: 8,
                            fontFamily: 'Consolas, "Courier New", monospace',
                            fontSize: 12,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-all',
                          }}>
                            {sql}
                          </div>
                        ),
                      }]}
                    />
                  </div>
                </div>
              )}

              {/* Step 4 执行结果 */}
              {isQuery && rowCount !== undefined && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{
                    width: 20, height: 20, borderRadius: '50%',
                    background: '#FF9800', color: '#fff',
                    fontSize: 10, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>{tables && tables.length > 0 ? 4 : 3}</div>
                  <BarChartOutlined style={{ color: '#FF9800', fontSize: 13 }} />
                  <span style={{ fontSize: 12, color: '#555', minWidth: 56 }}>执行结果</span>
                  <Tag style={{
                    background: '#FFF3E0', color: '#E65100',
                    border: '1px solid #FFCC80',
                    borderRadius: 10, fontSize: 11, margin: 0,
                  }}>
                    返回 <strong>{rowCount}</strong> 行数据
                  </Tag>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── AI 回复正文 ── */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 4 }}>
          {isChat
            ? <MessageOutlined style={{ color: DATA_COLOR.from, fontSize: 13, marginTop: 2 }} />
            : <BulbOutlined style={{ color: DATA_COLOR.from, fontSize: 13, marginTop: 2 }} />
          }
          <span style={{ fontSize: 12, color: '#888', fontWeight: 500 }}>
            {isChat ? 'AI 回复' : 'AI 分析'}
          </span>
        </div>
        <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>{content}</div>
        {data && renderDataTable(data)}
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px - 48px)' }}>
      <Card
        style={{
          flex: 1,
          borderRadius: 14,
          border: 'none',
          boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
        styles={{ body: { flex: 1, display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' } }}
      >
        <div
          ref={listRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '24px 24px 12px',
          }}
        >
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', padding: '80px 20px' }}>
              <DatabaseOutlined style={{ fontSize: 48, color: '#D1D5DB', marginBottom: 16 }} />
              <Paragraph strong style={{ fontSize: 16 }}>
                智能数据查询助手
              </Paragraph>
              <Paragraph type="secondary">
                用自然语言描述你的数据需求，例如：
              </Paragraph>
              <Space orientation="vertical" size={8}>
                {[
                  '查一下上个月美国站销售额前10的ASIN',
                  '本月广告ACoS超过30%的产品有哪些',
                  '最近7天退货率最高的产品',
                ].map((eg) => (
                  <Tag
                    key={eg}
                    style={{
                      cursor: 'pointer',
                      padding: '6px 16px',
                      borderRadius: 20,
                      fontSize: 13,
                    }}
                    color="orange"
                    onClick={() => { setInput(eg); }}
                  >
                    {eg}
                  </Tag>
                ))}
              </Space>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                gap: 12,
                marginBottom: 20,
                flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
              }}
            >
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  background: msg.role === 'user' ? `linear-gradient(135deg, ${DATA_COLOR.from}, ${DATA_COLOR.to})` : `${DATA_COLOR.from}15`,
                  color: msg.role === 'user' ? '#fff' : DATA_COLOR.from,
                }}
              >
                {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
              </div>
              <div
                style={{
                  maxWidth: msg.role === 'user' ? '72%' : '85%',
                  background: msg.role === 'user' ? `linear-gradient(135deg, ${DATA_COLOR.from}, ${DATA_COLOR.to})` : '#fff',
                  color: msg.role === 'user' ? '#fff' : '#1a1a2e',
                  padding: '12px 16px',
                  borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
                  fontSize: 14,
                  lineHeight: 1.7,
                }}
              >
                {msg.role === 'user'
                  ? <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                  : renderAssistantContent(msg)
                }</div>
            </div>
          ))}
        </div>

        <div
          style={{
            padding: '12px 24px 20px',
            borderTop: '1px solid #F3F4F6',
            background: '#FAFAFA',
          }}
        >
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <ModelSelector value={selectedModel} onChange={handleModelChange} style={{ flex: 1, maxWidth: 260 }} />
            {messages.length > 0 && (
              <Button size="small" icon={<ClearOutlined />} onClick={clearCache} type="text" style={{ color: '#999' }}>
                清空对话
              </Button>
            )}
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <Input
              size="large"
              placeholder="输入你的数据查询需求..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={sendMessage}
              disabled={loading}
              style={{ borderRadius: 12 }}
            />
            <Button
              type="primary"
              size="large"
              icon={<SendOutlined />}
              onClick={sendMessage}
              loading={loading}
              style={{
                borderRadius: 12,
                width: 52,
                background: R[2],
              }}
            />
          </div>
        </div>
      </Card>
    </div>
  );
}
