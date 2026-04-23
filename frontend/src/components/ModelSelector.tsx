import { Select, Tag, Tooltip } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import { useModels } from '../hooks/useModels';

interface Props {
  value?: string;
  onChange?: (value: string | undefined) => void;
  style?: React.CSSProperties;
  size?: 'small' | 'middle' | 'large';
  placeholder?: string;
}

export default function ModelSelector({ value, onChange, style, size, placeholder }: Props) {
  const { models, loading, verifying } = useModels();

  if (!models.length && !loading && !verifying) return null;

  return (
    <Select
      value={value || undefined}
      onChange={onChange}
      placeholder={verifying ? '模型池验证中…' : (placeholder || '默认模型')}
      allowClear
      loading={loading || verifying}
      disabled={verifying && models.length === 0}
      style={{ minWidth: size === 'small' ? 120 : 180, ...style }}
      size={size || 'middle'}
      suffixIcon={<ThunderboltOutlined style={{ color: '#F57C00' }} />}
      options={models.map((m) => ({
        value: m.id,
        label: (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Tooltip title={m.id}>
              <span style={{ fontSize: 13 }}>{m.provider_name}</span>
            </Tooltip>
            <span style={{ color: '#999', fontSize: 11 }}>{m.model}</span>
            {m.is_primary && <Tag color="orange" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>主</Tag>}
          </span>
        ),
      }))}
    />
  );
}
