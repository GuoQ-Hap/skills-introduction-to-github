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
} from 'antd';
import {
  SendOutlined,
  DatabaseOutlined,
  UserOutlined,
  RobotOutlined,
  CodeOutlined,
  ClearOutlined,
} from '@ant-design/icons';
import { stiApi, getCurrentUsername, getUserScopedKey } from '../api';
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
      const { data } = await stiApi.chat({
        session_id: sessionId,
        message: text,
        user_id: username,
        model: selectedModel,
      });

      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: data.analysis || data.error || '查询完成',
        sql: data.sql || undefined,
        data: data.data || undefined,
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
    const columns = (data.columns as string[]) || [];
    const rows = (data.rows as Record<string, unknown>[]) || [];
    if (!columns.length) return null;

    const tableColumns = columns.map((col) => ({
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
                  maxWidth: '80%',
                  background: msg.role === 'user' ? `linear-gradient(135deg, ${DATA_COLOR.from}, ${DATA_COLOR.to})` : '#fff',
                  color: msg.role === 'user' ? '#fff' : '#1a1a2e',
                  padding: '12px 16px',
                  borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
                  fontSize: 14,
                  lineHeight: 1.7,
                }}
              >
                {msg.loading ? (
                  <Spin size="small" />
                ) : (
                  <>
                    {msg.intent && (
                      <Tag color="blue" style={{ marginBottom: 6 }}>
                        {msg.intent}
                      </Tag>
                    )}
                    {msg.tables && msg.tables.length > 0 && (
                      <div style={{ marginBottom: 6 }}>
                        {msg.tables.map((t) => (
                          <Tag key={t} color="geekblue" style={{ fontSize: 11 }}>
                            {t}
                          </Tag>
                        ))}
                      </div>
                    )}
                    {msg.sql && (
                      <div
                        style={{
                          background: '#1E1E2E',
                          color: '#A6E3A1',
                          padding: '10px 14px',
                          borderRadius: 8,
                          fontFamily: 'Consolas, "Courier New", monospace',
                          fontSize: 12,
                          marginBottom: 8,
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-all',
                        }}
                      >
                        <CodeOutlined style={{ marginRight: 6 }} />
                        {msg.sql}
                      </div>
                    )}
                    <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                    {msg.data && renderDataTable(msg.data)}
                  </>
                )}
              </div>
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
