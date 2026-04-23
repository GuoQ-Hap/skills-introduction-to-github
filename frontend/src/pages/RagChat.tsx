import { useState, useRef, useEffect } from 'react';
import {
  Card,
  Input,
  Button,
  Typography,
  Space,
  Spin,
  Tag,
  Empty,
  Collapse,
  Tabs,
  Upload,
  Select,
  InputNumber,
  Table,
  message,
  Row,
  Col,
  Statistic,
  Badge,
  Tooltip,
  Divider,
  Progress,
} from 'antd';
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  UploadOutlined,
  EyeOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  InboxOutlined,
  ReloadOutlined,
  ScissorOutlined,
  ClearOutlined,
} from '@ant-design/icons';
import type { UploadFile as AntUploadFile } from 'antd';
import { lmaApi, getCurrentUsername, getUserScopedKey } from '../api';
import { useChatCache } from '../hooks/useChatCache';
import ModelSelector from '../components/ModelSelector';
import { RAINBOW, BTN_RAINBOW } from '../layouts/MainLayout';

const { Text, Paragraph } = Typography;
const { Dragger } = Upload;
const RAG_COLOR = RAINBOW[3];
const R = BTN_RAINBOW;

// ════════════════════════════════════════════════════════════════
// Tab 1: 智能问答
// ════════════════════════════════════════════════════════════════

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: { source: string; content: string }[];
  loading?: boolean;
  error?: boolean;
}

function ChatTab() {
  const username = getCurrentUsername();
  const chatKey = getUserScopedKey('lma_chat');
  const sessionKey = getUserScopedKey('lma_session_id');
  const modelKey = getUserScopedKey('lma_model');

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
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleModelChange = (v: string | undefined) => {
    setSelectedModel(v);
    if (v) localStorage.setItem(modelKey, v);
    else localStorage.removeItem(modelKey);
  };

  const handleSend = async () => {
    const question = input.trim();
    if (!question || loading) return;
    setInput('');
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: question },
      { role: 'assistant', content: '', loading: true },
    ]);
    setLoading(true);
    try {
      const res = await lmaApi.chat({ session_id: sessionId, question, model: selectedModel });
      const d = res.data as any;
      const answer = d?.data?.answer || d?.answer || '未获取到回答';
      const sources = d?.data?.sources || d?.sources || [];
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: answer, sources };
        return next;
      });
    } catch (e: any) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: e.message || '请求失败', error: true };
        return next;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 200px)' }}>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
        {messages.length === 0 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            <Empty description={<Text type="secondary">基于知识库的智能问答，输入问题获取 AI 回答</Text>} />
          </div>
        )}
        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: 16,
              padding: '0 8px',
            }}
          >
            <div style={{ maxWidth: '80%' }}>
              <div
                style={{
                  display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
                  flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                }}
              >
                <div
                  style={{
                    width: 30, height: 30, borderRadius: '50%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: msg.role === 'user'
                      ? `linear-gradient(135deg, ${RAG_COLOR.from}, ${RAG_COLOR.to})`
                      : `linear-gradient(135deg, ${RAG_COLOR.to}, ${RAG_COLOR.from})`,
                    color: '#fff', fontSize: 13,
                  }}
                >
                  {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {msg.role === 'user' ? '你' : 'AI 助手'}
                </Text>
              </div>
              <div
                style={{
                  padding: '12px 16px',
                  borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                    background: msg.role === 'user' ? `linear-gradient(135deg, ${RAG_COLOR.from}, ${RAG_COLOR.to})` : '#fff',
                  color: msg.role === 'user' ? '#fff' : msg.error ? '#EF4444' : '#1f2937',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
                }}
              >
                {msg.loading ? (
                  <Space><Spin size="small" /><Text type="secondary">AI 正在思考中...</Text></Space>
                ) : (
                  <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap', color: 'inherit', lineHeight: 1.7 }}>
                    {msg.content}
                  </Paragraph>
                )}
              </div>
              {msg.sources && msg.sources.length > 0 && (
                <Collapse
                  size="small" style={{ marginTop: 8, borderRadius: 10 }}
                  items={[{
                    key: '1',
                    label: <Text type="secondary" style={{ fontSize: 12 }}>参考来源 ({msg.sources.length} 条)</Text>,
                    children: (
                      <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                        {msg.sources.map((s, i) => (
                          <div key={i} style={{ padding: '8px 0', borderBottom: i < msg.sources!.length - 1 ? '1px solid #f5f5f5' : 'none' }}>
                            <Tag color="blue">{s.source || `来源 ${i + 1}`}</Tag>
                            <Paragraph ellipsis={{ rows: 3, expandable: true, symbol: '展开' }} style={{ fontSize: 12, margin: 0, color: '#666' }}>
                              {s.content}
                            </Paragraph>
                          </div>
                        ))}
                      </div>
                    ),
                  }]}
                />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div style={{ borderTop: '1px solid #f0f0f0', padding: '12px 0 0' }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
          <ModelSelector value={selectedModel} onChange={handleModelChange} style={{ flex: 1, maxWidth: 260 }} />
          {messages.length > 0 && (
            <Button size="small" icon={<ClearOutlined />} onClick={clearCache} type="text" style={{ color: '#999' }}>
              清空对话
            </Button>
          )}
        </div>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            size="large" placeholder="输入你的问题..." value={input}
            onChange={(e) => setInput(e.target.value)} onPressEnter={handleSend}
            disabled={loading} style={{ borderRadius: '10px 0 0 10px' }}
          />
          <Button type="primary" size="large" icon={<SendOutlined />} onClick={handleSend}
            loading={loading} style={{ borderRadius: '0 10px 10px 0', background: R[3] }}>发送</Button>
        </Space.Compact>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// Tab 2: 文档管理 — 上传 / 在线拆分预览 / 入库
// ════════════════════════════════════════════════════════════════

interface ChunkItem {
  index: number;
  length: number;
  content: string;
}

function DocTab() {
  const [fileList, setFileList] = useState<AntUploadFile[]>([]);
  const [sourceKind, setSourceKind] = useState('unstructured');
  const [chunkStrategy, setChunkStrategy] = useState('fixed');
  const [chunkSize, setChunkSize] = useState<number>(800);
  const [chunkOverlap, setChunkOverlap] = useState<number>(100);
  const [collectionName, setCollectionName] = useState('');

  const [previewLoading, setPreviewLoading] = useState(false);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [chunks, setChunks] = useState<ChunkItem[]>([]);
  const [previewMeta, setPreviewMeta] = useState<{ total_chars: number; chunk_count: number } | null>(null);
  const [activeChunk, setActiveChunk] = useState<number | null>(null);

  const buildFormData = () => {
    if (!fileList.length || !fileList[0].originFileObj) return null;
    const fd = new FormData();
    fd.append('file', fileList[0].originFileObj);
    fd.append('source_kind', sourceKind);
    fd.append('chunk_strategy', chunkStrategy);
    if (chunkSize) fd.append('chunk_size', String(chunkSize));
    if (chunkOverlap !== undefined) fd.append('chunk_overlap', String(chunkOverlap));
    return fd;
  };

  const handlePreview = async () => {
    const fd = buildFormData();
    if (!fd) { message.warning('请先选择文件'); return; }
    setPreviewLoading(true);
    setChunks([]);
    setPreviewMeta(null);
    try {
      const res = await lmaApi.previewChunks(fd);
      const d = (res.data as any)?.data;
      if (d) {
        setChunks(d.chunks || []);
        setPreviewMeta({ total_chars: d.total_chars, chunk_count: d.chunk_count });
        message.success(`拆分完成：${d.chunk_count} 个分块`);
      } else {
        message.error((res.data as any)?.msg || '预览失败');
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleIngest = async () => {
    const fd = buildFormData();
    if (!fd) { message.warning('请先选择文件'); return; }
    if (collectionName.trim()) fd.append('collection_name', collectionName.trim());
    setIngestLoading(true);
    try {
      const res = await lmaApi.ingest(fd);
      const d = res.data as any;
      if (d?.code === 200 || d?.data?.inserted) {
        message.success(`入库成功：写入 ${d.data?.inserted || 0} 条到 ${d.data?.collection || '默认集合'}`);
        setChunks([]);
        setPreviewMeta(null);
        setFileList([]);
      } else {
        message.error(d?.msg || '入库失败');
      }
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setIngestLoading(false);
    }
  };

  return (
    <div>
      <Row gutter={[20, 20]}>
        <Col xs={24} lg={10}>
          <Card
            title={<Space><UploadOutlined />文件上传</Space>}
            style={{ borderRadius: 12, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}
          >
            <Dragger
              fileList={fileList}
              beforeUpload={() => false}
              onChange={({ fileList: fl }) => setFileList(fl.slice(-1))}
              maxCount={1}
              accept=".pdf,.txt,.md,.csv,.json,.html,.htm"
              style={{ borderRadius: 10 }}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">点击或拖拽文件到此区域</p>
              <p className="ant-upload-hint">支持 PDF、TXT、Markdown 等文本格式</p>
            </Dragger>

            <Divider style={{ margin: '16px 0' }} />

            <Space style={{ width: '100%', flexWrap: 'wrap' }} size={[12, 12]}>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>文件类型</Text>
                <Select
                  value={sourceKind} onChange={setSourceKind}
                  style={{ width: 160, display: 'block', marginTop: 4 }}
                  options={[
                    { value: 'unstructured', label: '通用文本' },
                    { value: 'pdf_formatted', label: 'PDF 格式化' },
                  ]}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>切分策略</Text>
                <Select
                  value={chunkStrategy} onChange={setChunkStrategy}
                  style={{ width: 160, display: 'block', marginTop: 4 }}
                  options={[
                    { value: 'fixed', label: '固定滑窗' },
                    { value: 'smart', label: '智能切分' },
                  ]}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>块大小</Text>
                <InputNumber
                  value={chunkSize} onChange={(v) => setChunkSize(v || 800)}
                  min={100} max={10000} step={100}
                  style={{ width: 120, display: 'block', marginTop: 4 }}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>重叠</Text>
                <InputNumber
                  value={chunkOverlap} onChange={(v) => setChunkOverlap(v ?? 100)}
                  min={0} max={2000} step={50}
                  style={{ width: 120, display: 'block', marginTop: 4 }}
                />
              </div>
            </Space>

            <Divider style={{ margin: '16px 0' }} />

            <div style={{ marginBottom: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>目标集合（留空使用默认）</Text>
              <Input
                value={collectionName} onChange={(e) => setCollectionName(e.target.value)}
                placeholder="leang_documents" style={{ marginTop: 4 }}
              />
            </div>

            <Space style={{ width: '100%' }}>
              <Button
                icon={<ScissorOutlined />} onClick={handlePreview}
                loading={previewLoading} disabled={!fileList.length}
                style={{ borderColor: RAINBOW[1].from, color: RAINBOW[1].from }}
              >
                拆分预览
              </Button>
              <Button
                type="primary" icon={<CloudUploadOutlined />} onClick={handleIngest}
                loading={ingestLoading} disabled={!fileList.length}
                style={{ background: R[4] }}
              >
                向量化入库
              </Button>
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            title={
              <Space>
                <EyeOutlined />
                拆分预览
                {previewMeta && (
                  <Tag color="orange">{previewMeta.chunk_count} 块 · {previewMeta.total_chars.toLocaleString()} 字符</Tag>
                )}
              </Space>
            }
            style={{ borderRadius: 12, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', height: '100%' }}
            styles={{ body: { maxHeight: 'calc(100vh - 260px)', overflowY: 'auto' } }}
          >
            {previewLoading && (
              <div style={{ textAlign: 'center', padding: 60 }}><Spin tip="正在拆分文档..." /></div>
            )}

            {!previewLoading && chunks.length === 0 && (
              <Empty description={<Text type="secondary">上传文件后点击「拆分预览」查看分块效果</Text>} />
            )}

            {!previewLoading && chunks.length > 0 && (
              <div>
                <div style={{ marginBottom: 12 }}>
                  <Progress
                    percent={100} showInfo={false} size="small"
                    strokeColor={{ from: '#E65100', to: '#FF9800' }}
                  />
                  <Row gutter={16} style={{ marginTop: 8 }}>
                    <Col span={8}>
                      <Statistic title="总块数" value={chunks.length} valueStyle={{ fontSize: 20 }} />
                    </Col>
                    <Col span={8}>
                      <Statistic title="平均长度" value={Math.round(chunks.reduce((s, c) => s + c.length, 0) / chunks.length)} suffix="字符" valueStyle={{ fontSize: 20 }} />
                    </Col>
                    <Col span={8}>
                      <Statistic title="总字符" value={previewMeta?.total_chars || 0} valueStyle={{ fontSize: 20 }} />
                    </Col>
                  </Row>
                </div>

                <Divider style={{ margin: '12px 0' }} />

                {chunks.map((chunk) => (
                  <Card
                    key={chunk.index}
                    size="small"
                    style={{
                      marginBottom: 8,
                      borderRadius: 8,
                      border: activeChunk === chunk.index ? `2px solid ${RAG_COLOR.from}` : '1px solid #f0f0f0',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onClick={() => setActiveChunk(activeChunk === chunk.index ? null : chunk.index)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <Space>
                        <Tag color="orange">#{chunk.index + 1}</Tag>
                        <Text type="secondary" style={{ fontSize: 12 }}>{chunk.length} 字符</Text>
                      </Space>
                    </div>
                    <Paragraph
                      ellipsis={activeChunk !== chunk.index ? { rows: 3 } : false}
                      style={{ margin: 0, fontSize: 13, lineHeight: 1.8, color: '#374151' }}
                    >
                      {chunk.content}
                    </Paragraph>
                  </Card>
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// Tab 3: 知识库管理 — Milvus 集合列表 / 数据浏览
// ════════════════════════════════════════════════════════════════

interface CollectionInfo {
  name: string;
  num_entities: number;
  description: string;
}

function KBTab() {
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedCol, setSelectedCol] = useState<string | null>(null);
  const [colData, setColData] = useState<any[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [dataOffset, setDataOffset] = useState(0);
  const DATA_PAGE = 20;

  const fetchCollections = async () => {
    setLoading(true);
    try {
      const res = await lmaApi.collections();
      const d = (res.data as any)?.data;
      setCollections(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCollections(); }, []);

  const fetchData = async (name: string, offset: number) => {
    setDataLoading(true);
    try {
      const res = await lmaApi.collectionData(name, offset, DATA_PAGE);
      const d = (res.data as any)?.data;
      setColData(d?.rows || []);
      setDataOffset(offset);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setDataLoading(false);
    }
  };

  const handleSelect = (name: string) => {
    setSelectedCol(name);
    setDataOffset(0);
    fetchData(name, 0);
  };

  const totalEntities = collections.reduce((s, c) => s + Math.max(c.num_entities, 0), 0);

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card style={{ borderRadius: 12, border: 'none', boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}>
            <Statistic title="集合数量" value={collections.length} prefix={<DatabaseOutlined />} />
          </Card>
        </Col>
        <Col span={8}>
          <Card style={{ borderRadius: 12, border: 'none', boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}>
            <Statistic title="总实体数" value={totalEntities} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col span={8}>
          <Card style={{ borderRadius: 12, border: 'none', boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}>
            <Button icon={<ReloadOutlined />} onClick={fetchCollections} loading={loading} style={{ marginTop: 8 }}>
              刷新列表
            </Button>
          </Card>
        </Col>
      </Row>

      <Row gutter={[20, 20]}>
        <Col xs={24} lg={8}>
          <Card
            title="集合列表"
            style={{ borderRadius: 12, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}
            styles={{ body: { padding: 0 } }}
            loading={loading}
          >
            {collections.length === 0 && !loading && (
              <Empty style={{ padding: 24 }} description="暂无集合" />
            )}
            {collections.map((col) => (
              <div
                key={col.name}
                onClick={() => handleSelect(col.name)}
                style={{
                  padding: '14px 16px',
                  cursor: 'pointer',
                  borderBottom: '1px solid #f5f5f5',
                  background: selectedCol === col.name ? '#FFF3E0' : 'transparent',
                  transition: 'background 0.2s',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <Text strong>{col.name}</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {col.num_entities >= 0 ? `${col.num_entities.toLocaleString()} 条` : '无法加载'}
                    </Text>
                  </div>
                  <Badge
                    status={col.num_entities >= 0 ? 'success' : 'error'}
                    text={<Text style={{ fontSize: 12 }}>{col.num_entities >= 0 ? '在线' : '异常'}</Text>}
                  />
                </div>
              </div>
            ))}
          </Card>
        </Col>

        <Col xs={24} lg={16}>
          <Card
            title={
              selectedCol
                ? <Space><DatabaseOutlined />{selectedCol}<Tag color="orange">{collections.find((c) => c.name === selectedCol)?.num_entities?.toLocaleString() || 0} 条</Tag></Space>
                : '数据浏览'
            }
            style={{ borderRadius: 12, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}
          >
            {!selectedCol && (
              <Empty description={<Text type="secondary">点击左侧集合查看数据</Text>} />
            )}
            {selectedCol && (
              <>
                <Table
                  dataSource={colData}
                  loading={dataLoading}
                  rowKey="id"
                  size="small"
                  scroll={{ x: 800 }}
                  pagination={false}
                  columns={[
                    { title: 'ID', dataIndex: 'id', width: 80 },
                    { title: '文件名', dataIndex: 'file_name', width: 160, ellipsis: true },
                    { title: '块序号', dataIndex: 'chunk_index', width: 80 },
                    { title: '类型', dataIndex: 'source_type', width: 100 },
                    {
                      title: '文本内容', dataIndex: 'text', ellipsis: true,
                      render: (t: string) => (
                        <Tooltip title={t} placement="topLeft" overlayStyle={{ maxWidth: 500 }}>
                          <Text style={{ fontSize: 12 }}>{t}</Text>
                        </Tooltip>
                      ),
                    },
                  ]}
                />
                <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    显示 {dataOffset + 1} - {dataOffset + colData.length} 条
                  </Text>
                  <Space>
                    <Button
                      size="small" disabled={dataOffset === 0}
                      onClick={() => fetchData(selectedCol, Math.max(0, dataOffset - DATA_PAGE))}
                    >
                      上一页
                    </Button>
                    <Button
                      size="small" disabled={colData.length < DATA_PAGE}
                      onClick={() => fetchData(selectedCol, dataOffset + DATA_PAGE)}
                    >
                      下一页
                    </Button>
                  </Space>
                </div>
              </>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// 主页面
// ════════════════════════════════════════════════════════════════

export default function RagChat() {
  return (
    <Card
      style={{
        borderRadius: 14,
        border: 'none',
        boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
        minHeight: 'calc(100vh - 64px - 48px)',
      }}
      styles={{ body: { padding: '8px 24px 24px' } }}
    >
      <Tabs
        defaultActiveKey="chat"
        items={[
          {
            key: 'chat',
            label: <Space><RobotOutlined />智能问答</Space>,
            children: <ChatTab />,
          },
          {
            key: 'doc',
            label: <Space><FileTextOutlined />文档管理</Space>,
            children: <DocTab />,
          },
          {
            key: 'kb',
            label: <Space><DatabaseOutlined />知识库管理</Space>,
            children: <KBTab />,
          },
        ]}
      />
    </Card>
  );
}
