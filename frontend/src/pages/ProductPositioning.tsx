import { useRef, useState } from 'react';
import { Alert, Button, Card, Col, Image, Input, List, Row, Tag, Typography, message } from 'antd';
import {
  BulbOutlined,
  DeleteOutlined,
  SearchOutlined,
  StarOutlined,
  TeamOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { laaApi, type LAACandidateItem, type LAAMatchResult } from '../api';

const { Text, Paragraph } = Typography;

function CandidateList({ items, color }: { items: LAACandidateItem[]; color: string }) {
  if (!items?.length) return <Text type="secondary">暂无候选结果</Text>;
  return (
    <List
      size="small"
      dataSource={items.slice(0, 3)}
      renderItem={(item) => (
        <List.Item style={{ paddingInline: 0 }}>
          <div style={{ width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <Tag color={color}>{item.score ?? 0}</Tag>
              <Text strong>{item.name || '-'}</Text>
            </div>
            {item.reason && <Paragraph style={{ marginBottom: 0, fontSize: 13 }}>{item.reason}</Paragraph>}
          </div>
        </List.Item>
      )}
    />
  );
}

export default function ProductPositioning() {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [imageUrl, setImageUrl] = useState('');
  const [imageBase64, setImageBase64] = useState('');
  const [brand, setBrand] = useState('');
  const [comment, setComment] = useState('');
  const [color, setColor] = useState('');
  const [size, setSize] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<LAAMatchResult | null>(null);

  const onPickImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setImageBase64(String(reader.result || ''));
      setError('');
    };
    reader.onerror = () => message.error('读取图片失败');
    reader.readAsDataURL(file);
    e.currentTarget.value = '';
  };

  const clearImage = () => {
    setImageUrl('');
    setImageBase64('');
  };

  const handleMatch = async () => {
    if (!imageUrl.trim() && !imageBase64.trim()) {
      message.warning('请提供图片 URL 或上传图片');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const mergedComment = `品牌: ${brand.trim() || '未提供'}\n${comment.trim() || '未提供评论'}`;
      const { data } = await laaApi.match({
        image_url: imageUrl.trim() || undefined,
        image_base64: imageBase64.trim() || undefined,
        comment: mergedComment,
        color: color.trim() || '未提供',
        size: size.trim() || '未提供',
      });
      setResult(data.result || null);
    } catch (e: any) {
      const msg = e?.message || '产品定位失败';
      setError(msg);
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Row gutter={24}>
      <Col xs={24} lg={8}>
        <Card title="产品定位输入" style={{ borderRadius: 14, position: 'sticky', top: 104 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <Input
              placeholder="图片 URL（可选）"
              value={imageUrl}
              onChange={(e) => setImageUrl(e.target.value)}
            />
            <Button icon={<UploadOutlined />} onClick={() => fileRef.current?.click()}>
              上传
            </Button>
            <Button icon={<DeleteOutlined />} danger disabled={!imageUrl && !imageBase64} onClick={clearImage}>
              删除
            </Button>
            <input ref={fileRef} type="file" accept="image/*" onChange={onPickImage} style={{ display: 'none' }} />
          </div>

          {(imageBase64 || imageUrl) && (
            <div style={{ marginBottom: 10 }}>
              <Image
                src={imageBase64 || imageUrl}
                alt="positioning-preview"
                width={96}
                height={96}
                style={{ objectFit: 'cover', borderRadius: 8, border: '1px solid rgba(79, 211, 255, 0.22)' }}
              />
            </div>
          )}

          <Input placeholder="品牌（选填）" value={brand} onChange={(e) => setBrand(e.target.value)} style={{ marginBottom: 8 }} />
          <Input.TextArea
            rows={4}
            placeholder="评论 / 商品描述（选填）"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            style={{ marginBottom: 8 }}
          />
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <Input placeholder="颜色（选填）" value={color} onChange={(e) => setColor(e.target.value)} />
            <Input placeholder="尺寸（选填）" value={size} onChange={(e) => setSize(e.target.value)} />
          </div>

          <Button type="primary" block icon={<SearchOutlined />} loading={loading} onClick={handleMatch}>
            {loading ? '定位中...' : '生成产品定位'}
          </Button>
        </Card>
      </Col>

      <Col xs={24} lg={16}>
        {error && (
          <Alert
            type="error"
            showIcon
            message="产品定位失败"
            description={error}
            style={{ marginBottom: 16, borderRadius: 12 }}
          />
        )}

        <Card title="产品定位结果" style={{ borderRadius: 14 }}>
          {!result ? (
            <Text type="secondary">请输入左侧信息后点击“生成产品定位”。</Text>
          ) : (
            <>
              <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                <Col xs={24} md={8}>
                  <Card size="small" title={<span><TeamOutlined /> 最佳人群</span>}>
                    <Tag color="blue">{result.best_audience || '-'}</Tag>
                  </Card>
                </Col>
                <Col xs={24} md={8}>
                  <Card size="small" title={<span><StarOutlined /> 最佳场景</span>}>
                    <Tag color="purple">{result.best_scene || '-'}</Tag>
                  </Card>
                </Col>
                <Col xs={24} md={8}>
                  <Card size="small" title={<span><BulbOutlined /> 核心卖点</span>}>
                    <Tag color="cyan">{result.best_selling_point || '待生成'}</Tag>
                    {!!result.best_selling_point_score && (
                      <Tag color="gold" style={{ marginTop: 8 }}>{result.best_selling_point_score}</Tag>
                    )}
                  </Card>
                </Col>
              </Row>

              {result.best_selling_point_reason && (
                <Card size="small" title="卖点原因" style={{ marginBottom: 16 }}>
                  <Paragraph style={{ marginBottom: 0 }}>{result.best_selling_point_reason}</Paragraph>
                </Card>
              )}

              {result.insight && (
                <Card size="small" title="综合洞察" style={{ marginBottom: 16 }}>
                  <Paragraph style={{ marginBottom: 0 }}>{result.insight}</Paragraph>
                </Card>
              )}

              <Row gutter={[16, 16]}>
                <Col xs={24} lg={8}>
                  <Card size="small" title="卖点候选">
                    <CandidateList items={result.best_selling_point_candidates || []} color="cyan" />
                  </Card>
                </Col>
                <Col xs={24} lg={8}>
                  <Card size="small" title="人群候选">
                    <CandidateList items={result.audience_candidates || []} color="geekblue" />
                  </Card>
                </Col>
                <Col xs={24} lg={8}>
                  <Card size="small" title="场景候选">
                    <CandidateList items={result.scene_candidates || []} color="magenta" />
                  </Card>
                </Col>
              </Row>
            </>
          )}
        </Card>
      </Col>
    </Row>
  );
}
