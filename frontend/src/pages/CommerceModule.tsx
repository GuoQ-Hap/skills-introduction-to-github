import { useMemo, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button, Card, Col, Row, Tag, Timeline, Typography } from 'antd';
import {
  ApiOutlined,
  ArrowRightOutlined,
  BankOutlined,
  BarChartOutlined,
  CustomerServiceOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  FileSearchOutlined,
  FundOutlined,
  GlobalOutlined,
  InboxOutlined,
  NodeIndexOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  ThunderboltOutlined,
  TruckOutlined,
} from '@ant-design/icons';

const { Title, Paragraph, Text } = Typography;

interface ModuleConfig {
  title: string;
  label: string;
  icon: ReactNode;
  desc: string;
  capabilities: string[];
  roadmap: string[];
}

const commonRoadmap = ['确定数据模型与字段权限', '接入后端服务和审批流程', '上线监控、告警、日志与自动化任务'];

const moduleMap: Record<string, ModuleConfig> = {
  '/architecture': {
    title: '工作中心',
    label: 'Work Center',
    icon: <DeploymentUnitOutlined />,
    desc: '以工作中心承接各业务域的智能化能力，统一进入运营增长、供应链管理、财务管理、产品管理、组织人事和数据智能工作台。',
    capabilities: ['统一身份权限', '运营增长', '供应链管理', '财务管理', '产品管理', '组织人事'],
    roadmap: ['第一阶段：运营增长、数据查数、知识库稳定上线', '第二阶段：供应链、财务、产品、人事业务域接入', '第三阶段：跨部门流程自动化和经营预测'],
  },
  '/products': {
    title: '商品中心',
    label: 'Product Hub',
    icon: <ShopOutlined />,
    desc: '管理 LEANG SPU/SKU、类目属性、图片素材、价格、库存、合规资料和多语言卖点。',
    capabilities: ['SPU/SKU 档案', '类目属性模板', '素材库与图片质检', '价格策略', '合规资料归档', '多语言内容字段'],
    roadmap: commonRoadmap,
  },
  '/channels': {
    title: '渠道刊登中心',
    label: 'Channel Publishing',
    icon: <ApiOutlined />,
    desc: '预设 Amazon、独立站、TikTok Shop、Temu、Shopee 等渠道刊登、同步、审核和失败重试。',
    capabilities: ['渠道店铺授权', '刊登任务队列', '字段映射规则', '审核状态追踪', '失败重试', '上下架同步'],
    roadmap: commonRoadmap,
  },
  '/orders': {
    title: '订单履约中心',
    label: 'Order Fulfillment',
    icon: <ShoppingCartOutlined />,
    desc: '承接订单、付款、发货、物流轨迹、异常件、退换货和售后处理。',
    capabilities: ['订单聚合', '物流轨迹', '发货规则', '退换货工单', '异常预警', '履约时效分析'],
    roadmap: commonRoadmap,
  },
  '/customers': {
    title: '客户与售后',
    label: 'Customer Service',
    icon: <CustomerServiceOutlined />,
    desc: '预留客户画像、站内信、邮件、售后工单、差评挽回和复购触达。',
    capabilities: ['客户画像', '售后工单', '消息模板', '差评预警', '复购分层', 'AI 客服助手'],
    roadmap: commonRoadmap,
  },
  '/sales': {
    title: '销售管理',
    label: 'Sales Management',
    icon: <FundOutlined />,
    desc: '预设销售目标、商机线索、报价、合同、订单转化、销售预测和团队业绩。',
    capabilities: ['销售目标', '线索池', '商机阶段', '报价合同', '回款跟进', '销售预测'],
    roadmap: commonRoadmap,
  },
  '/inventory': {
    title: '库存健康与预警',
    label: 'Inventory Control',
    icon: <InboxOutlined />,
    desc: '监控库存水位、安全库存、断货风险、滞销库存、补货建议、库存周转和多仓同步。',
    capabilities: ['实时库存水位', '安全库存阈值', '断货风险预警', '滞销库存识别', '补货建议', '库存周转分析'],
    roadmap: ['接入库存与仓库数据', '配置预警阈值和通知策略', '上线补货预测与库存健康评分'],
  },
  '/supply-chain': {
    title: '供应链履约监控',
    label: 'Supply Chain Control',
    icon: <TruckOutlined />,
    desc: '监控采购、供应商、生产、质检、在途、入库、物流和异常节点状态。',
    capabilities: ['供应商状态', '采购订单进度', '生产与质检节点', '在途物流追踪', '延误异常预警', '交付达成率'],
    roadmap: ['接入采购与物流节点', '建立供应商履约评分', '上线延误预测和异常闭环'],
  },
  '/procurement': {
    title: '采购与供应商协同',
    label: 'Procurement Collaboration',
    icon: <TruckOutlined />,
    desc: '管理采购需求、询价比价、采购订单、供应商档案、合同和结算。',
    capabilities: ['采购申请', '询价比价', '采购订单', '供应商档案', '合同管理', '采购成本分析'],
    roadmap: commonRoadmap,
  },
  '/warehouse': {
    title: '仓储物流看板',
    label: 'Warehouse Logistics',
    icon: <DatabaseOutlined />,
    desc: '预设入库、出库、调拨、盘点、库龄、仓储效率和物流轨迹看板。',
    capabilities: ['入库出库', '仓库调拨', '库存盘点', '库龄分析', '仓储效率', '物流轨迹'],
    roadmap: commonRoadmap,
  },
  '/ads': {
    title: '广告投放策略',
    label: 'Advertising Strategy',
    icon: <BarChartOutlined />,
    desc: '预设广告账户、关键词、预算、出价、ACOS/TACOS 和自动调价策略。',
    capabilities: ['广告账户概览', '关键词分层', '预算与出价', '否词建议', '投放实验', 'ROI 归因'],
    roadmap: commonRoadmap,
  },
  '/finance-agent/profit': {
    title: '经营利润分析',
    label: 'Profit Analytics',
    icon: <FundOutlined />,
    desc: '预设利润、毛利、费用、广告成本、平台费用和产品经营质量分析。',
    capabilities: ['利润看板', '毛利拆解', '费用归因', '广告成本分析', 'SKU 盈亏识别', '异常成本预警'],
    roadmap: commonRoadmap,
  },
  '/finance-agent/cost': {
    title: '成本核算中心',
    label: 'Cost Accounting',
    icon: <BarChartOutlined />,
    desc: '预设采购成本、头程、仓储、平台费、广告费和售后成本核算。',
    capabilities: ['采购成本', '物流成本', '仓储成本', '平台费用', '售后成本', '成本趋势'],
    roadmap: commonRoadmap,
  },
  '/finance-agent/cashflow': {
    title: '回款与现金流',
    label: 'Cashflow Management',
    icon: <FundOutlined />,
    desc: '预设回款周期、现金流、账期、付款计划和资金风险提醒。',
    capabilities: ['回款计划', '现金流预测', '账期追踪', '付款提醒', '资金风险', '经营复盘'],
    roadmap: commonRoadmap,
  },
  '/product-agent/selection': {
    title: '市场选品研究',
    label: 'Product Research',
    icon: <ShopOutlined />,
    desc: '预设市场机会、竞品格局、价格带、需求趋势和产品机会评分。',
    capabilities: ['市场机会', '竞品格局', '价格带分析', '需求趋势', '风险识别', '机会评分'],
    roadmap: commonRoadmap,
  },
  '/product-agent/development': {
    title: '产品开发管理',
    label: 'Product Development',
    icon: <ShopOutlined />,
    desc: '预设产品定义、功能规格、打样进度、供应商协同和上市准备。',
    capabilities: ['产品定义', '规格管理', '打样进度', '供应商协同', '合规资料', '上市清单'],
    roadmap: commonRoadmap,
  },
  '/product-agent/listing': {
    title: '新品上架管理',
    label: 'Launch Management',
    icon: <ApiOutlined />,
    desc: '预设新品资料、渠道字段、图片文案、刊登检查和发布流程。',
    capabilities: ['新品资料', '渠道字段', '图片文案', '刊登检查', '发布流程', '失败重试'],
    roadmap: commonRoadmap,
  },
  '/hr-agent/recruiting': {
    title: '招聘与入职',
    label: 'Talent Acquisition',
    icon: <GlobalOutlined />,
    desc: '预设岗位需求、候选人筛选、面试流程、Offer 和入职跟进。',
    capabilities: ['岗位需求', '简历筛选', '面试安排', '候选人评估', 'Offer 跟进', '入职提醒'],
    roadmap: commonRoadmap,
  },
  '/hr-agent/performance': {
    title: '绩效管理',
    label: 'Performance Management',
    icon: <ThunderboltOutlined />,
    desc: '预设目标设定、绩效过程、结果校准、改进计划和团队复盘。',
    capabilities: ['目标设定', '过程跟踪', '绩效校准', '改进计划', '团队复盘', '结果归档'],
    roadmap: commonRoadmap,
  },
  '/hr-agent/org': {
    title: '组织发展',
    label: 'Organization Development',
    icon: <DeploymentUnitOutlined />,
    desc: '预设组织架构、岗位体系、人才盘点、培训计划和组织效率分析。',
    capabilities: ['组织架构', '岗位体系', '人才盘点', '培训计划', '组织效率', '权限协同'],
    roadmap: commonRoadmap,
  },
  '/workflow': {
    title: '自动化工作流',
    label: 'Workflow',
    icon: <NodeIndexOutlined />,
    desc: '把采集、分析、生成、审核、发布、通知、复盘串成可配置工作流。',
    capabilities: ['流程编排', '人工审核节点', '定时任务', '异常通知', '执行日志', 'Webhook 集成'],
    roadmap: commonRoadmap,
  },
  '/modelops': {
    title: '模型与提示词治理',
    label: 'ModelOps',
    icon: <ThunderboltOutlined />,
    desc: '管理模型池、提示词版本、评测集、调用成本、质量回放和权限审计。',
    capabilities: ['模型池状态', '提示词版本', '评测任务', '调用成本', '质量回放', '权限审计'],
    roadmap: commonRoadmap,
  },
};

export default function CommerceModule() {
  const location = useLocation();
  const navigate = useNavigate();
  const config = useMemo(() => moduleMap[location.pathname] || moduleMap['/architecture'], [location.pathname]);

  return (
    <div className="module-page">
      <section className="module-hero">
        <div className="module-hero-icon">{config.icon}</div>
        <div className="module-hero-copy">
          <Tag className="tech-tag">{config.label}</Tag>
          <Title level={1}>{config.title}</Title>
          <Paragraph>{config.desc}</Paragraph>
          <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => navigate('/')}>
            返回经营总览
          </Button>
        </div>
      </section>

      <Row gutter={[16, 16]}>
        {config.capabilities.map((capability) => (
          <Col xs={24} md={12} xl={8} key={capability}>
            <Card className="module-card">
              <div className="module-card-index">★</div>
              <Title level={4}>{capability}</Title>
              <Paragraph>前端入口已预设，等待后端服务、数据模型、权限策略和流程规则接入。</Paragraph>
            </Card>
          </Col>
        ))}
      </Row>

      <Card className="tech-card" style={{ marginTop: 16 }} title={<span><FileSearchOutlined /> 建设路线</span>}>
        <Timeline
          items={config.roadmap.map((item, index) => ({
            color: index === 0 ? 'cyan' : 'blue',
            children: <Text>{item}</Text>,
          }))}
        />
      </Card>

      <Card className="tech-card" style={{ marginTop: 16 }} title={<span><BankOutlined /> 后端接入占位</span>}>
        <Paragraph>
          当前模块先以静态蓝图呈现，后续可按“接口契约、数据模型、权限菜单、审批流程、任务日志、异常告警”的顺序接入真实后端。
        </Paragraph>
        <Tag className="blue-tag"><GlobalOutlined /> LEANG 预留模块</Tag>
      </Card>
    </div>
  );
}
