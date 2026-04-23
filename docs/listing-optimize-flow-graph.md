# Listing 优化 — 图形化调用结构

本文用 **Mermaid** 图描述前后端与 LSTA 模块的调用关系，便于对照代码逐项修正。

> 渲染方式：GitHub / GitLab / VS Code（Markdown 预览）/ Cursor 均可显示 Mermaid。

---

## 1. 总览：分层与依赖

```mermaid
flowchart TB
  subgraph FE["前端"]
    P["ListingOptimize.tsx"]
    API["frontend/src/api/index.ts\nlistingApi.*"]
  end

  subgraph GW["网关"]
    M["main.py\ninit_listing_router → /lsta"]
  end

  subgraph LSTA_API["LSTA 接口层"]
    R["LSTA/router/router.py\nprefix=/lsta"]
    LA["LSTA/api/listingApi.py"]
  end

  subgraph CORE["LSTA 核心"]
    LC["LSTA/core/listingCore.py\nListingOptimizer / listing_optimizer"]
    PR["LSTA/prompt/listingPrompt.py"]
    MD["LSTA/models/listingState.py"]
  end

  subgraph SVC["LSTA 服务"]
    AM["amazonService.py\n抓取 ProductData"]
    TW["trafficWordService.py\nABA/SQR MySQL"]
    TK["taskService.py\n后台任务"]
    LX["lingxingService.py"]
    STR["searchTermRecommendService.py"]
  end

  subgraph EXT["外部能力"]
    MP["admin/model_pool.py\ncall_llm"]
    DB["LDA/service/dbService.py\nDoris 三维诊断 SQL"]
    MV["LMA embedding + Milvus\n/embed"]
  end

  P --> API
  API --> M
  M --> R --> LA
  LA --> LC
  LC --> PR
  LA --> MD
  LC --> AM
  LC --> TW
  LA --> TK
  LA --> LX
  LA --> STR
  LC --> MP
  LA --> DB
  LA --> MV
```

---

## 2. 产品获取 + 三维诊断 + 流量词

**HTTP**：`POST /lsta/fetch-with-diagnostics`

```mermaid
sequenceDiagram
  participant FE as 前端 listingApi
  participant API as listingApi.py
  participant LO as listing_optimizer
  participant AM as amazon_service
  participant POOL as ThreadPoolExecutor
  participant TRI as _query_tri_dim
  participant TW as traffic_word_service
  participant DB as db_service Doris
  participant LLM as model_pool

  FE->>API: fetch-with-diagnostics
  API->>LO: fetch(asin, mp)
  LO->>AM: fetch → ProductData

  par 并行
    API->>POOL: submit _fetch_tri_dim
    POOL->>TRI: _query_tri_dim(asin)
    TRI->>DB: execute_sql(ads_lingxing...)
    DB-->>TRI: TriDimDiagnostic | null
  and
    API->>POOL: submit _fetch_traffic_words
    POOL->>TW: batch_check_listing(title, bullets, desc, "", [])
    TW-->>POOL: traffic_words 列表
  end

  API->>LO: assess_traffic_relevance(词串, product) 若 traffic_items 非空
  LO->>LLM: call_llm 内联 prompt
  LLM-->>LO: JSON assessments
  API-->>FE: FetchDiagnosticsResponse
```

```mermaid
flowchart LR
  A[listing_optimizer.fetch] --> B[_fetch_and_validate]
  B --> C[amazon_service.fetch]
  C --> C1[SP-API]
  C --> C2[虚拟机代理]
  C --> C3[ScraperAPI / 直连重试]
```

---

## 3. Listing 优化（主路径）

**HTTP**：`POST /lsta/optimize`  
**注意**：接口层固定 `skip_traffic_analysis=True`，不在此接口内跑 `analyze_traffic_words`。

```mermaid
flowchart TD
  START([POST /lsta/optimize]) --> REQ[ListingOptimizeRequest]
  REQ --> OPT[listing_optimizer.optimize]

  OPT --> PD{product_data?}
  PD -->|有| USE[使用传入 ProductData]
  PD -->|无| FETCH[_fetch_and_validate → amazon_service]

  USE --> STRAT{optimize_strategy}
  FETCH --> STRAT

  STRAT -->|standard| P1[build_system_prompt + build_optimize_prompt]
  STRAT -->|cosmo| P2[COSMO_OPTIMIZE_PROMPT]
  STRAT -->|ctr| P3[CTR_OPTIMIZE_PROMPT]
  STRAT -->|cvr| P4[CVR_OPTIMIZE_PROMPT]
  STRAT -->|traffic| P5[TRAFFIC_OPTIMIZE_PROMPT]
  STRAT -->|custom| P6[build_custom_optimize_prompt]

  P1 --> FAB{enable_fab?}
  P2 --> FAB
  P3 --> FAB
  P4 --> FAB
  P5 --> FAB
  P6 --> FAB
  FAB -->|是| FAB2[append_fab_to_prompt]
  FAB -->|否| LLM
  FAB2 --> LLM[model_pool.call_llm]
  LLM --> PARSE[_parse_optimize_response]
  PARSE --> SEC{optimize_sections?}
  SEC -->|有| MERGE[未选板块回填原 product 字段]
  SEC -->|无| OUT
  MERGE --> OUT([ListingOptimizeResponse])
```

---

## 4. 四维诊断分析

**HTTP**：`POST /lsta/analyze`

```mermaid
flowchart TD
  A([POST /lsta/analyze]) --> B[listing_optimizer.analyze]
  B --> C[_analyze_with_data]
  C --> D[_evaluate_with_data]
  D --> E[EVALUATE_LISTING_PROMPT.format]
  E --> F[model_pool.call_llm]
  F --> G[_parse_evaluate_response]
  G --> H[拼装 Markdown: 综合评判 / 得分 / 各维详情 / 优先行动]
  H --> I([ListingAnalyzeResponse])
```

**独立评判接口**：`POST /lsta/evaluate` 直接走 `_evaluate_with_data`，不拼装长 Markdown。

---

## 5. 迭代修改与流量词决策

```mermaid
flowchart TD
  subgraph Refine["POST /lsta/refine"]
    R1[refine_listing] --> R2[listing_optimizer.refine]
    R2 --> R3[REFINE_LISTING_PROMPT]
    R3 --> R4[call_llm]
    R4 --> R5[_parse_optimize_response]
  end

  subgraph TrafficDec["POST /lsta/apply-traffic-decisions"]
    T1[apply_traffic_decisions]
    T1 --> T2{有 removals?}
    T2 -->|否| T3[直接返回当前 OptimizedListing]
    T2 -->|是| T4[拼 user_feedback 文本]
    T4 --> T5[listing_optimizer.refine 同左]
  end
```

---

## 6. 流量词检查

**HTTP**：`POST /lsta/check-traffic-words`

```mermaid
flowchart TD
  Q([check_traffic_words]) --> W{请求体}
  W -->|words 列表| C1[traffic_word_service.check_words]
  W -->|Listing 文本| C2[batch_check_listing]
  W -->|无有效输入| ERR[返回 error]

  C1 --> PC{product_title/category?}
  C2 --> PC
  PC -->|是| AT[listing_optimizer.analyze_traffic_words]
  PC -->|否| MANUAL[手工组装 WordAnalysis]
  AT --> TW2[batch_check_listing 内部]
  AT --> TAG[按 target_keywords 打 relevance]
```

---

## 7. 后台任务

```mermaid
stateDiagram-v2
  [*] --> pending: POST /lsta/task/submit
  pending --> running: task_store.run_in_thread
  running --> completed: _run_optimize_task / _run_analyze_task 成功
  running --> failed: 异常
  completed --> [*]: GET /lsta/task/:id 取结果
```

---

## 8. 其他接口一览（简图）

```mermaid
flowchart LR
  E["POST /lsta/embed"] --> MV[Milvus + embedding_service]
  L["POST /lsta/submit-to-lingxing"] --> LX[lingxing_service]
  S["POST /lsta/search-term-recommend"] --> EX[Excel + MySQL MSKU 匹配]
  H["GET /lsta/health"] --> MP[model_pool.primary]
  D["GET /lsta/prompt-defaults"] --> PR[PROMPT_DEFAULTS]
```

---

## 9. 关键源码锚点（便于跳转）

| 层级 | 路径 |
|------|------|
| 应用挂载 | `main.py` → `init_listing_router` |
| 路由前缀 | `LSTA/router/router.py` → `/lsta` |
| HTTP 实现 | `LSTA/api/listingApi.py` |
| 优化/诊断/精炼 | `LSTA/core/listingCore.py` |
| Prompt | `LSTA/prompt/listingPrompt.py` |
| 模型与数据模型 | `admin/model_pool.py`、`LSTA/models/listingState.py` |
| 抓取 | `LSTA/service/amazonService.py` |
| 流量词 DB | `LSTA/service/trafficWordService.py` |
| 三维诊断 SQL | `listingApi.py` 内 `_query_tri_dim` + `LDA/service/dbService.py` |
| 前端封装 | `frontend/src/api/index.ts`（`listingApi`） |
| 前端页面 | `frontend/src/pages/ListingOptimize.tsx` |

---

## 10. 图例说明

- **实线箭头**：同步调用或数据流向。  
- **sequence / state**：强调时序与任务状态。  
- **optimize_strategy**：枚举定义见 `LSTA/models/listingState.py` 中 `OptimizeStrategy`。

如需把本图与旧文档合并，可参考同目录下的 `liting优化业务流程和系统架构.md`（文件名含笔误，合并时请统一命名）。
