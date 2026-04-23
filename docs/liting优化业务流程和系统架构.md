# LSTA — Amazon Listing 智能优化系统

> **LSTA**（Listing Smart Tuning Agent）是一套面向 Amazon 跨境电商运营的 Listing 智能优化平台，集成了产品数据抓取、LLM 驱动的文案优化与诊断、流量词分析、四维评分、向量库入库及领星 ERP 同步等全链路能力。

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [目录结构](#2-目录结构)
3. [核心业务流程](#3-核心业务流程)
   - 3.1 [单 ASIN 优化流程](#31-单-asin-优化流程)
   - 3.2 [单 ASIN 诊断流程](#32-单-asin-诊断流程)
   - 3.3 [批量优化流程](#33-批量优化流程)
4. [六大优化策略详解](#4-六大优化策略详解)
5. [四维评分体系](#5-四维评分体系)
6. [流量词分析系统](#6-流量词分析系统)
7. [产品数据抓取机制](#7-产品数据抓取机制)
8. [三维数据诊断](#8-三维数据诊断)
9. [API 接口一览](#9-api-接口一览)
10. [数据模型说明](#10-数据模型说明)
11. [提示词工程](#11-提示词工程)
12. [外部服务集成](#12-外部服务集成)
13. [配置与环境变量](#13-配置与环境变量)
14. [前端交互流程](#14-前端交互流程)

---

## 1. 系统架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                     前端 (React + Ant Design)                 │
│    ListingOptimize.tsx — 优化 / 诊断 / 批量 三大模式          │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTP (JSON)
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                   FastAPI 服务 (端口 8000/8003)               │
│                    路由前缀: /lsta                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              listingApi.py (API 层)                      │ │
│  │  健康检查 / 获取 / 优化 / 诊断 / 评判 / 迭代 / 嵌入 / 提交  │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │           listingCore.py (核心引擎)                       │ │
│  │  ListingOptimizer: fetch / optimize / analyze /          │ │
│  │  evaluate / refine / analyze_traffic_words               │ │
│  └──┬──────────┬──────────┬──────────┬────────────────────┘ │
│     │          │          │          │                        │
│     ▼          ▼          ▼          ▼                        │
│  Amazon     Model      Prompt    Traffic                     │
│  Service    Pool       Templates  Word Svc                   │
│  (抓取)    (LLM 调用)  (提示词)   (流量词)                    │
└──────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
   Amazon 网页     LLM API        ABA/SQR DB      领星 ERP
   / SP-API        (多模型池)      (MySQL)         (Open API)
                                                  Milvus (向量库)
```

**层次职责：**

| 层 | 文件 | 职责 |
|---|---|---|
| 入口 | `main.py` | 创建 FastAPI 应用，启动模型池测试 |
| 路由 | `router/router.py` | 注册 `/lsta` 前缀路由 |
| API | `api/listingApi.py` | HTTP 端点、参数校验、调度核心逻辑 |
| 核心 | `core/listingCore.py` | 业务编排、LLM 调用、JSON 容错解析 |
| 模型 | `models/listingState.py` | Pydantic 数据模型（请求/响应/领域对象） |
| 提示词 | `prompt/listingPrompt.py` | 所有 LLM 提示词模板与构建函数 |
| 服务 | `service/*.py` | Amazon 抓取、流量词查询、领星 ERP、日志 |
| 常量 | `constants.py` | 环境变量读取与默认值 |

---

## 2. 目录结构

```
LSTA/
├── main.py                          # FastAPI 应用入口（独立服务，端口 8003）
├── constants.py                     # 环境变量与常量配置
├── api/
│   └── listingApi.py                # 全部 HTTP 端点实现
├── core/
│   └── listingCore.py               # ListingOptimizer 核心引擎
├── models/
│   └── listingState.py              # Pydantic 数据模型定义
├── prompt/
│   └── listingPrompt.py             # LLM 提示词模板与构建函数
├── router/
│   └── router.py                    # 路由注册（/lsta 前缀）
└── service/
    ├── base.py                      # 统一日志 logger
    ├── amazonService.py             # Amazon 产品数据抓取
    ├── lingxingService.py           # 领星 ERP API 集成
    └── trafficWordService.py        # ABA/SQR 流量词数据库查询
```

---

## 3. 核心业务流程

### 3.1 单 ASIN 优化流程

这是系统最核心的功能，完整流程如下：

```
用户输入 ASIN + 站点
        │
        ▼
┌─────────────────────┐
│  1. 获取产品信息      │ POST /lsta/fetch-with-diagnostics
│  (含三维诊断+流量词)  │
└────────┬────────────┘
         │ 返回：ProductData + TriDimDiagnostic + TrafficWords
         ▼
┌─────────────────────┐
│  2. 用户配置优化参数  │ 前端交互
│  · 竞品 ASIN (≤5)    │
│  · 流量词勾选         │
│  · 修改意见           │
│  · 选择模型           │
│  · 选择优化策略       │
│  · FAB 分析开关       │
│  · 优化范围选择       │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  3. AI 优化生成       │ POST /lsta/optimize
│  LLM 根据策略生成     │
│  优化后的 Listing     │
└────────┬────────────┘
         │ 返回：OptimizedListing (title + bullet_points + description + search_terms)
         ▼
┌─────────────────────┐
│  4. 版本管理与迭代    │
│  · 查看优化结果       │
│  · 对比原始 Listing   │
│  · 基于反馈迭代 Refine│ POST /lsta/refine（最多 3 次）
│  · 对版本进行诊断     │ POST /lsta/analyze
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  5. 后续动作          │
│  · 选入优秀库 (Embed) │ POST /lsta/embed → Milvus 向量库
│  · 提交领星 ERP       │ POST /lsta/submit-to-lingxing
└─────────────────────┘
```

**关键细节：**

- **竞品分析**：用户可添加最多 5 个竞品 ASIN，系统自动抓取竞品数据，在提示词中构建竞品对比分析段落
- **流量词注入**：从 ABA/SQR 数据库查询到的流量词可由用户选择性勾选，作为关键词传入优化提示词
- **编辑产品数据**：获取到的原始产品信息支持在前端手动编辑后再送入优化
- **会话管理**：每次优化生成唯一 `session_id`，迭代 Refine 使用同一 session 保持上下文连贯性

### 3.2 单 ASIN 诊断流程

诊断流程是对现有 Listing 的质量评估，不生成新文案：

```
用户输入 ASIN + 站点
        │
        ▼
┌─────────────────────┐
│  1. 获取产品信息      │ POST /lsta/fetch-with-diagnostics
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  2. AI 诊断分析       │ POST /lsta/analyze
│  LLM 从四个维度评估   │
│  Listing 质量         │
└────────┬────────────┘
         │ 返回：四维评分 + 详细分析 + 优先改进建议
         ▼
┌─────────────────────┐
│  3. 结果展示          │
│  · 雷达图 (四维分数)  │
│  · 各维度详细分析     │
│  · 优先改进行动项     │
│  · 综合评估总结       │
└─────────────────────┘
```

### 3.3 批量优化流程

批量模式支持多 ASIN 并行处理：

```
┌─────────────────────────────────────────────────┐
│  1. 输入多个 ASIN（手动输入 / 导入 Excel/CSV）    │
└────────┬────────────────────────────────────────┘
         ▼
┌─────────────────────────────────────────────────┐
│  2. 批量获取（全部获取）                           │
│     每行独立 fetch，支持逐行配参                    │
└────────┬────────────────────────────────────────┘
         ▼
┌─────────────────────────────────────────────────┐
│  3. 批量操作（可独立或全部执行）                    │
│     · 批量优化 — 每行调用 /lsta/optimize           │
│     · 批量诊断 — 每行调用 /lsta/analyze            │
│     · 批量三维诊断 — SQL 查询广告数据               │
└────────┬────────────────────────────────────────┘
         ▼
┌─────────────────────────────────────────────────┐
│  4. 查看结果 + 迭代 Refine                        │
│     每行可独立展开结果 Drawer                       │
│     原始 vs 优化对比 / 版本管理 / Refine            │
└────────┬────────────────────────────────────────┘
         ▼
┌─────────────────────────────────────────────────┐
│  5. 批量提交领星 ERP                               │
└─────────────────────────────────────────────────┘
```

---

## 4. 六大优化策略详解

系统提供六种不同的优化策略，适用于不同的运营场景：

| 策略 | 枚举值 | 适用场景 | 核心逻辑 |
|---|---|---|---|
| **经典 SEO** | `standard` | 通用优化，平衡搜索排名与转化 | 使用 `build_optimize_prompt` 构建完整提示词，包含 SEO 关键词规则、竞品分析、五点/描述写作规范 |
| **COSMO 四维** | `cosmo` | 深度优化，符合 Amazon COSMO 算法 | 使用 `COSMO_OPTIMIZE_PROMPT` 模板，关注 COSMO 四维度（用户意图、产品属性、使用场景、解决方案） |
| **CTR 优化** | `ctr` | 提升点击率 | 使用 `CTR_OPTIMIZE_PROMPT`，侧重标题吸引力、首图配合文案、价格锚定等点击驱动因素 |
| **CVR 优化** | `cvr` | 提升转化率 | 使用 `CVR_OPTIMIZE_PROMPT`，侧重信任建设、痛点解决、差异化卖点、购买决策降门槛 |
| **流量优化** | `traffic` | 最大化关键词覆盖与搜索流量 | 使用 `TRAFFIC_OPTIMIZE_PROMPT`，注重关键词密度、长尾词覆盖、搜索词最大化利用 |
| **自定义** | `custom` | 完全个性化优化需求 | 使用 `build_custom_optimize_prompt`，支持自定义语气、侧重点、额外指令等参数 |

**策略执行流程（以 `optimize` 方法为例）：**

```python
optimize()
  ├── strategy == "cosmo"   → _optimize_cosmo_with_data()
  ├── strategy == "ctr"     → _optimize_focused_with_data("ctr")
  ├── strategy == "cvr"     → _optimize_focused_with_data("cvr")
  ├── strategy == "traffic" → _optimize_focused_with_data("traffic")
  ├── strategy == "custom"  → _optimize_custom_with_data()
  └── strategy == "standard"→ _optimize_with_data()
```

**FAB 分析增强**：所有策略均可开启 FAB（Feature-Advantage-Benefit）分析模式，在优化前先用 LLM 提取产品的功能-优势-利益点，然后将 FAB 分析结果追加到优化提示词中，生成更具说服力的文案。

---

## 5. 四维评分体系

诊断/评判功能使用四个维度评估 Listing 质量：

| 维度 | 说明 | 评估要点 |
|---|---|---|
| **COSMO** | Amazon COSMO 算法兼容性 | 用户意图覆盖、语义关联、属性完整度、场景匹配 |
| **Keywords** | 关键词优化水平 | 核心词覆盖率、长尾词分布、关键词密度合理性、搜索词利用率 |
| **Rufus** | Amazon Rufus AI 购物助手友好度 | 信息结构化程度、问答式内容覆盖、产品规格完整性 |
| **IDQ** | 信息数据质量 (Information Data Quality) | 五点完整性、描述丰富度、数据一致性、合规性 |

**评分数据结构：**

```
EvaluateScores
├── cosmo_score: int (0-100)
│   └── cosmo_detail: { user_intent, attributes, scenarios, solutions }
├── keywords_score: int (0-100)
│   └── keywords_detail: { coverage, density, distribution, search_terms }
├── rufus_score: int (0-100)
│   └── rufus_detail: { structure, qa_coverage, specs, readability }
└── idq_score: int (0-100)
    └── idq_detail: { bullet_quality, desc_quality, consistency, compliance }
```

诊断结果在前端以**雷达图**和**折叠面板**两种形式展示，并附带**优先改进行动项**和**综合评估总结**。

---

## 6. 流量词分析系统

流量词分析是优化流程的重要辅助环节，帮助运营人员了解关键词覆盖情况：

### 数据源

| 数据源 | 数据库 | 说明 |
|---|---|---|
| **ABA (Amazon Brand Analytics)** | `aba_report` MySQL 库 | 品牌分析搜索词报告，包含搜索频率排名 |
| **SQR (Search Query Report)** | `sqr_report` MySQL 库 | 搜索查询效果报告，包含曝光/点击/转化数据 |

### 分析流程

```
产品获取时 (/fetch-with-diagnostics)
        │
        ▼
TrafficWordService.batch_check_listing()
  ├── 从 Listing 各字段提取词/短语
  ├── 在 ABA 库中查询匹配
  ├── 在 SQR 库中查询匹配
  └── 返回 TrafficWordItem[]（含 source/search_volume/rank 等）
        │
        ▼
前端展示流量词列表，用户勾选要保留的关键词
        │
        ▼
勾选的关键词作为 target_keywords 传入优化接口
```

### LLM 相关性判定

对于从 ABA/SQR 查到的流量词，系统可选调用 LLM 进行相关性评估：

- `analyze_traffic_words()`：分析流量词与产品的关联程度
- `assess_traffic_relevance()`：批量判定词与产品类目的相关性

优化结果中会包含 `word_analysis` 字段，标注每个关键词在优化后文案中的覆盖位置（标题/五点/描述/搜索词），前端以不同颜色高亮展示。

---

## 7. 产品数据抓取机制

`AmazonProductService` 实现了多层容错的产品数据获取：

### 数据源优先级

```
1. SP-API (Amazon Selling Partner API)    ← 最稳定，需商家授权
   │ 失败
   ▼
2. 代理 VM 抓取                           ← 虚拟机代理转发
   │ 失败
   ▼
3. ScraperAPI / HTTP Proxy                ← 第三方抓取服务
   │ 失败
   ▼
4. 直连网页抓取                            ← 最后手段，内置反爬策略
   · 预热 Session
   · 多 URL 模式轮换
   · 随机 User-Agent
   · 指数退避重试
```

### 支持的站点

| 站点代码 | 域名 | 语言 |
|---|---|---|
| US | amazon.com | en |
| UK | amazon.co.uk | en |
| DE | amazon.de | de |
| JP | amazon.co.jp | ja |
| FR | amazon.fr | fr |
| IT | amazon.it | it |
| ES | amazon.es | es |
| CA | amazon.ca | en |
| AU | amazon.com.au | en |
| IN | amazon.in | en |
| MX | amazon.com.mx | es |

### 解析产品信息

从 HTML/API 响应中提取以下字段并封装为 `ProductData`：

- ASIN、标题、品牌、价格、货币、评分、评论数
- 五点描述 (Bullet Points)、产品描述
- 类目、BSR 排名、图片列表、变体信息

---

## 8. 三维数据诊断

三维数据诊断基于 **Doris 广告数据库**的实际运营数据，提供量化的产品表现评估：

| 维度 | 指标 | 对比基准 |
|---|---|---|
| **CTR (点击率)** | 产品 CTR% | 类目平均 CTR% |
| **CVR (转化率)** | 产品 CVR% | 类目平均 CVR% |
| **流量** | 流量变化% | 历史趋势 |

**诊断数据结构 `TriDimDiagnostic`：**

- `product_ctr_pct` / `cat_avg_ctr_pct`：产品与类目平均 CTR 对比
- `product_cvr_pct` / `cat_avg_cvr_pct`：产品与类目平均 CVR 对比
- `sessions_change_pct`：流量变化百分比
- `hit_count`：命中异常维度数量
- `optimization_actions`：自动生成的优化建议
- `msku` / `store_name`：MSKU 与店铺名称

前端在产品卡片顶部以**指标条 (TriDimBar)** 展示摘要，点击可打开 **Drawer** 查看完整 SQL 查询结果表（支持分页）。

---

## 9. API 接口一览

所有接口挂载在 `/lsta` 前缀下：

| 方法 | 路径 | 功能 | 核心调用 |
|---|---|---|---|
| `GET` | `/lsta/health` | 健康检查 | `model_pool.primary` |
| `GET` | `/lsta/prompt-defaults` | 获取默认提示词配置 | `PROMPT_DEFAULTS` |
| `POST` | `/lsta/fetch` | 获取产品数据 | `listing_optimizer.fetch()` |
| `POST` | `/lsta/fetch-with-diagnostics` | 获取产品+三维诊断+流量词 | `fetch()` + `db_service.execute_sql()` + `traffic_word_service.batch_check_listing()` |
| `POST` | `/lsta/optimize` | AI 优化 Listing | `listing_optimizer.optimize()` |
| `POST` | `/lsta/analyze` | AI 诊断分析 | `listing_optimizer.analyze()` |
| `POST` | `/lsta/evaluate` | AI 四维评判 | `listing_optimizer.evaluate()` |
| `POST` | `/lsta/refine` | 迭代精炼 Listing | `listing_optimizer.refine()` |
| `POST` | `/lsta/check-traffic-words` | 流量词检查 | `traffic_word_service.check_words()` |
| `POST` | `/lsta/apply-traffic-decisions` | 应用流量词决策并 Refine | `listing_optimizer.refine()` |
| `POST` | `/lsta/embed` | 入库优秀 Listing 向量库 | `embedding_service` + `milvus_service` |
| `GET` | `/lsta/lingxing/status` | 领星 ERP 配置状态 | `lingxing_service.configured` |
| `POST` | `/lsta/submit-to-lingxing` | 提交到领星 ERP | `lingxing_service.submit_listing()` |

### 关键请求/响应模型

**优化请求 `ListingOptimizeRequest`：**

```
{
  "asin": "B0XXXXXXXX",
  "marketplace": "US",
  "target_keywords": ["keyword1", "keyword2"],
  "target_audience": "家庭主妇",
  "language": "en",
  "optimize_strategy": "standard|cosmo|ctr|cvr|traffic|custom",
  "session_id": "uuid",
  "model": "模型名称",
  "prompt_overrides": { "company_info": "...", "core_capabilities": "..." },
  "product_data": { ... },
  "optimize_sections": ["title", "bullet_points", "description", "search_terms"],
  "competitor_products": [ { ... } ],
  "custom_params": { "tone": "...", "focus": "..." },
  "enable_fab": false
}
```

**优化响应 `ListingOptimizeResponse`：**

```
{
  "original": { ProductData },
  "optimized": {
    "title": "优化后标题",
    "bullet_points": ["优化后五点1", ...],
    "description": "优化后描述",
    "search_terms": "优化后搜索词",
    "word_analysis": { "keyword1": { "locations": [...], "type": "..." } }
  }
}
```

---

## 10. 数据模型说明

核心数据模型定义在 `models/listingState.py`，使用 Pydantic BaseModel：

### 枚举类型

| 枚举 | 值 | 说明 |
|---|---|---|
| `OptimizeStrategy` | `standard` / `cosmo` / `ctr` / `cvr` / `traffic` / `custom` | 六大优化策略 |

### 核心模型

| 模型 | 用途 |
|---|---|
| `ProductData` | 产品信息（ASIN/标题/品牌/价格/评分/五点/描述/类目/BSR/图片/变体） |
| `TriDimDiagnostic` | 三维诊断指标（CTR/CVR/流量变化+对比值） |
| `TrafficWordItem` | 单个流量词条目（词/来源/搜索量/排名） |
| `OptimizedListing` | 优化后 Listing（标题/五点/描述/搜索词 + 词分析） |
| `WordAnalysis` | 关键词覆盖分析（覆盖位置/词类型） |
| `EvaluateScores` | 四维评分（COSMO/Keywords/Rufus/IDQ 各含总分+子项） |
| `EvaluateAnalysis` | 评判综合分析（总结/优先行动/原始输出） |

### 请求/响应模型对

| 请求 | 响应 | 用途 |
|---|---|---|
| `FetchProductRequest` | `ProductData` / `FetchDiagnosticsResponse` | 产品获取 |
| `ListingOptimizeRequest` | `ListingOptimizeResponse` | 优化 |
| `ListingAnalyzeRequest` | `ListingAnalyzeResponse` | 诊断 |
| `ListingEvaluateRequest` | `ListingEvaluateResponse` | 评判 |
| `ListingRefineRequest` | `ListingRefineResponse` | 迭代精炼 |
| `ListingEmbedRequest` | `ListingEmbedResponse` | 向量入库 |
| `LingxingSubmitRequest` | `LingxingSubmitResponse` | 领星提交 |
| `TrafficWordCheckRequest` | `TrafficWordCheckResponse` | 流量词检查 |
| `TrafficWordDecisionRequest` | `ListingRefineResponse` | 流量词决策应用 |

---

## 11. 提示词工程

### 可配置默认值 (`PROMPT_DEFAULTS`)

前端提示词设置面板可覆盖的参数，通过 `sessionStorage` 持久化：

| 键 | 默认内容概述 |
|---|---|
| `company_info` | 凌昂科技公司信息、主营业务、核心产品线、销售市场 |
| `core_capabilities` | A9/COSMO 算法理解、消费者心理、关键词布局、高转化文案 |
| `bullet_rules` | 五点写作规范：5 条 × 150-250 字符、大写关键词开头、覆盖五大维度 |
| `description_rules` | 描述写作规范：300-2000 字符、产品故事、使用场景、SEO 融入 |

### 提示词构建函数

| 函数 | 用途 |
|---|---|
| `build_system_prompt(overrides)` | 构建系统角色提示词（身份+公司+能力） |
| `build_optimize_prompt(...)` | 构建经典 SEO 优化提示词 |
| `build_custom_optimize_prompt(...)` | 构建自定义策略优化提示词 |
| `append_fab_to_prompt(prompt, fab)` | 将 FAB 分析结果追加到提示词 |

### 策略模板常量

| 常量 | 策略 |
|---|---|
| `COSMO_OPTIMIZE_PROMPT` | COSMO 四维算法策略模板 |
| `CTR_OPTIMIZE_PROMPT` | CTR 点击率优化模板 |
| `CVR_OPTIMIZE_PROMPT` | CVR 转化率优化模板 |
| `TRAFFIC_OPTIMIZE_PROMPT` | 流量/关键词覆盖优化模板 |
| `EVALUATE_LISTING_PROMPT` | 四维评判模板 |
| `REFINE_LISTING_PROMPT` | 迭代精炼模板 |
| `FAB_ANALYZE_PROMPT` | FAB 分析模板 |
| `ANALYZE_LISTING_PROMPT` | 诊断分析模板 |

### 多语言支持

系统根据站点自动选择输出语言（`MARKETPLACE_LANGUAGES` 映射），LLM 会以对应语言生成优化文案。

---

## 12. 外部服务集成

### LLM 模型池 (`admin.model_pool`)

- 统一通过 `model_pool.call_llm()` 调用 LLM
- 支持多模型池（主模型失败自动切换备用模型）
- 启动时执行 `model_pool.run_full_test_async()` 验证可用性
- 用户可在前端选择指定模型

### Milvus 向量数据库 (通过 LMA 模块)

- 优化后的优秀 Listing 可通过 `/lsta/embed` 入库
- 使用 `LMA.service.embeddingService` 生成向量
- 使用 `LMA.service.milvusService` 写入 Milvus
- 集合名：`listing`
- 用途：构建优秀案例库，供后续优化参考

### Doris 数据库 (通过 LDA 模块)

- 三维诊断数据来源
- 通过 `LDA.service.dbService.db_service.execute_sql()` 查询
- 前端使用 `buildDiagnosticSQL` 构建查询 SQL

### 内存数据库 (`Base.Service.memoryDbService`)

- 每次优化/诊断/评判结果通过 `_persist_lsta()` 持久化
- 写入 `llm_memory` 表
- 记录意图（optimize/analyze/evaluate 等）、输入输出、时间戳

---

## 13. 配置与环境变量

所有配置通过环境变量注入，在 `constants.py` 中读取：

### LLM 相关

| 变量 | 说明 |
|---|---|
| `LAI_LLM_API_KEY` | LLM API 密钥 |
| `LAI_LLM_BASE_URL` | LLM API 基础 URL |
| `LAI_LLM_MODEL` | 默认 LLM 模型 |

### 流量词数据库

| 变量组 | 说明 |
|---|---|
| `ABA_REPORT_DB_*` | ABA 报告库连接（host/port/user/password/name/charset） |
| `SQR_REPORT_DB_*` | SQR 报告库连接（host/port/user/password/name/charset） |

### 领星 ERP

| 变量 | 说明 |
|---|---|
| `LINGXING_APP_ID` | 领星应用 ID |
| `LINGXING_APP_SECRET` | 领星应用密钥 |
| `LINGXING_API_BASE` | 领星 API 基础 URL（默认 `https://openapi.lingxingerp.com/erp/sc`） |

### 其他

| 变量 | 说明 |
|---|---|
| `LAI_DEFAULT_MARKETPLACE` | 默认站点 |
| `SESSION_TTL` | 会话过期时间 |
| `SESSION_MAX` | 最大会话数 |

---

## 14. 前端交互流程

### 页面入口

通过侧边栏导航进入 `/listing?tab=optimize|analyze|batch`，三种模式共用 `ListingOptimize.tsx` 页面。

### 核心组件

| 组件 | 功能 |
|---|---|
| `ListingOptimize` | 根页面，管理模式切换与全局状态 |
| `usePromptConfig` | 提示词配置 Hook（远程默认值 + 本地覆盖） |
| `PromptSettingsDrawer` | 提示词编辑抽屉（支持 CSV 导入/导出） |
| `EditableProductCard` | 可编辑的产品信息卡片（含 TriDimBar） |
| `TrafficWordSelector` | 流量词选择面板（全选/清空/手动追加） |
| `HighlightedText` | 关键词高亮文本组件 |
| `RadarScoreChart` | 四维评分雷达图 |
| `DimensionPanel` | 评分维度详情折叠面板 |
| `AnalyzeResultCard` | 诊断结果展示卡 |
| `RefinePanel` / `VersionCard` | 版本管理与迭代精炼 |
| `BatchOptimizePanel` | 批量操作面板 |
| `BatchParamEditor` | 批量行参数编辑器 |
| `TriDimTable` | 三维诊断数据表格（分页） |

### 状态管理

- 使用 React `useState` / `useRef` / `useEffect` / `useCallback`，无第三方状态库
- **SessionStorage 持久化**：
  - `lsta_session_id`：优化会话 ID
  - `lsta_model`：选中模型
  - `lsta_prompt_overrides`：提示词覆盖配置
  - `lsta_result_*`：优化/诊断/产品/迭代结果缓存（刷新后恢复）
  - `lsta_batch_rows`：批量行数据
- **并发安全**：通过 `fetchIdRef` 丢弃过期的异步响应

### 用户操作流 (单 ASIN 优化)

```
1. 输入 ASIN (10位) + 选择站点 → 点击"获取产品信息"
2. 查看/编辑产品信息 → 查看三维指标摘要 → 选择流量词
3. [可选] 添加竞品 ASIN → 填写修改意见 → 选择模型
4. 选择优化策略 → 配置优化范围 → [可选] 开启 FAB
5. 点击"开始优化" → 等待 LLM 生成
6. 查看优化结果 → 对比原文 → 查看关键词高亮
7. [可选] 输入反馈 → 点击"迭代修改" (最多 3 次)
8. [可选] 对版本进行诊断 → 查看四维评分雷达图
9. [可选] 选入优秀库 / 提交到领星 ERP
```

---

## 附录：LLM JSON 容错解析

由于 LLM 输出的 JSON 不总是格式正确，`listingCore.py` 实现了多层容错解析机制：

```
LLM 原始输出
    │
    ▼
_extract_json()          # 尝试直接提取 JSON
    │ 失败
    ▼
_repair_incomplete_json() # 修复不完整的 JSON（补全括号等）
    │ 失败
    ▼
_recover_partial_listing() # 用正则从文本中提取各字段片段
    │ 失败
    ▼
返回错误/降级结果
```

这确保了即使 LLM 输出格式异常，系统也能最大程度地提取有用信息。
