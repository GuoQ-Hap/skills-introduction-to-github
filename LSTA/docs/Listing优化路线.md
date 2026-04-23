# Amazon Listing 优化路线说明

本文档描述本仓库 **LSTA（lAi_listing）** 模块中 Listing 优化的推荐业务流程、策略选择与关键能力边界，便于产品、运营与研发对齐「从拉数到上架闭环」的使用方式。

实现入口：`LSTA/api/listingApi.py`（HTTP）、`LSTA/core/listingCore.py`（编排与 LLM 调用）、`LSTA/prompt/listingPrompt.py`（提示词与合规约束）。

API 统一前缀：`/lsta`（见 `LSTA/router/router.py`）。

---

## 1. 总体目标

在合规前提下，围绕 **曝光（搜索/索引）** 与 **转化（详情页说服）** 两条主线，对 **标题、五点、描述、后台搜索词** 进行结构化产出或迭代；可选接入 **竞品参考、评论洞察、广告三维诊断、流量词校验** 等增强信号。

---

## 2. 推荐业务路线（端到端）

下列顺序为常见「从诊断到定稿」路径，可按实际需要裁剪。

| 阶段 | 目的 | 典型接口 / 能力 |
|------|------|-----------------|
| **① 取数** | 拉取 ASIN 当前 Listing 与基础商品信息，供后续分析与优化共用 | `POST /lsta/fetch` |
| **② 增强取数（可选）** | 一次拿到产品 + 三维诊断 + 流量词 + 评论分析摘要，减少前端多次往返 | `POST /lsta/fetch-with-diagnostics` |
| **③ 诊断 / 评判（可选）** | 用四维框架看问题在哪一维，指导选策略与改稿重点 | `POST /lsta/analyze`（诊断报告）、`POST /lsta/evaluate`（结构化评分） |
| **④ 竞品发现（可选）** | 为优化提示词注入竞品 Listing 文本，做差异化 | 见 `listingApi` 中竞品发现相关路由与 `competitorDiscoveryService` |
| **⑤ 主优化** | 按策略生成完整或分模块（sections）Listing | `POST /lsta/optimize` |
| **⑥ 多候选择优（可选）** | 并行生成多版文案，四维评分 + 转化向自由打分，按三维诊断动态加权选最优 | `POST /lsta/optimize` 且请求体 `variant_count` > 1（见 `ListingOptimizer.optimize_multi`） |
| **⑦ 流量词闭环（可选）** | 优化后对流量词相关性做分析；弱相关词可由用户决策后再微调 | 流量词检查 / `POST /lsta/apply-traffic-decisions` 等 |
| **⑧ 人工迭代** | 根据运营反馈局部改稿 | `POST /lsta/refine` |
| **⑨ 下游（可选）** | 向量入库或推 ERP | `POST /lsta/embed`、`POST /lsta/submit-to-lingxing` |

**核心引擎数据流（简化）**：获取/校验 `ProductData` → 组装提示词（含 FAB/标准模板、竞品块、颜色与评论等注入）→ `ModelPoolService` 调用 LLM → 解析 JSON →（可选）流量词分析与关键词缺失告警。

---

## 3. 优化策略怎么选（含与当前实现的差异）

请求体里虽有 `optimize_strategy`（`OptimizeStrategy` 枚举）与 `custom_params`，但 **`ListingOptimizer.optimize()` 当前实现只按 `enable_fab` 二分**：`True` → `build_enhanced_optimize_prompt`（`_optimize_enhanced_with_data`）；`False` → `build_optimize_prompt`（`_optimize_with_data`）。**`optimize_strategy`、`custom_params` 未参与分支**，仓库里虽已存在 `COSMO_OPTIMIZE_PROMPT`、`CTR_OPTIMIZE_PROMPT`、`_optimize_cosmo_with_data`、`_optimize_custom_with_data` 等函数/模板，**主入口尚未接线**；多候选时同样如此（`optimize_multi` 只是把 `optimize_strategy` 原样传给 `optimize`，后者未使用）。

下表描述的是 **提示词库中已定义的模板**（便于后续把 `optimize_strategy` 接到 `optimize()` 上），**不等同于当前线上生成路径已切换模板**。

| 策略值（API） | 侧重点（设计意图） | 对应提示词/构建函数（代码中） |
|----------------|-------------------|------------------------------|
| `standard` | 经典 SEO 向 Listing | `build_optimize_prompt` |
| `cosmo` | 四维协同 | `COSMO_OPTIMIZE_PROMPT` / `_optimize_cosmo_with_data` |
| `ctr` / `cvr` / `traffic` | 点击 / 转化 / 流量宽度 | `CTR_OPTIMIZE_PROMPT` / `CVR_OPTIMIZE_PROMPT` / `TRAFFIC_OPTIMIZE_PROMPT`，经 `_optimize_focused_with_data` |
| `custom` | 自定义指令 | `build_custom_optimize_prompt` / `_optimize_custom_with_data` |

**FAB 增强（当前实际生效的二选一之一）**：`enable_fab=true` 时走 `build_enhanced_optimize_prompt`（COSMO + FAB + 可选 `review_analysis` 评论洞察块等）；`enable_fab=false` 时走标准 `build_optimize_prompt`。

---

## 4. 合规与表达红线（全局）

系统提示 `build_system_prompt` 中对模型有 **硬性禁令**，所有策略与迭代（含 `refine`）均需遵守，包括但不限于：

- 不在文案中做 **明确时长/无理由类售后承诺**、**销量/畅销表述**、**评分条数类社会证明**、**未经证实的排名第一类断言** 等（详见 `listingPrompt.py` 中禁令条款）。
- **人群风格适配**：按「目标受众 / 修改意见」在「专业数据 ↔ 场景情感」之间调权重。

运营侧应把「想写的促销话术」先翻译成 **可验证的产品事实与场景利益**，再交给模型扩展。

---

## 5. 分模块优化与输入增强

- **分模块**：`optimize_sections` 传 `title` / `bullet_points` / `description` / `search_terms` 子集时，未选中模块在提示词中明确为「保持原样」。
- **竞品**：`competitor_products` 传入后，提示词会追加「竞品 Listing 参考」段落，要求取长补短、差异化。
- **颜色**：`color` 或库表字段注入时，在受众/提示中要求 **保留真实颜色**，避免模型改色或省略。
- **关键词勾选**：优化完成后引擎会校验 `target_keywords` 是否出现在标题+五点+描述正文中；缺失会在 `optimization_notes` 末尾追加告警（见 `listingCore.optimize`）。

---

## 6. 多候选（Best-of-N）与加权逻辑

当 `variant_count` ∈ [2, 10] 时，`optimize_multi` 会：

1. **并行生成** N 份候选，每份附加不同「创作风格」指令（见 `_VARIANT_STYLES`，如情感共鸣、功能驱动、长尾覆盖等）。
2. **并行评分**：每候选同时跑 **四维结构化评判** 与 **转化向自由打分**。
3. **综合排序**：`composite_score = 曝光分 × w1 + 转化分 × w2`，其中 `w1/w2` 由 **三维诊断**（CTR/CVR/流量变化）命中情况决定（仅流量问题偏重曝光、仅转化问题偏重转化、其余 0.5/0.5）。
4. **流量词分析**仅对最优候选执行，控制成本。

适用场景：重要 ASIN、策略取舍不一时，用数据化排序减少「单抽」方差。

---

## 7. 工程与稳定性说明（实施侧必读）

- **模型路由**：统一经模型池调用，主模型失败可切换备用（见 `listingCore` 头部说明）。
- **限流**：全局 `_LlmRateLimiter`（最小间隔 + 线程安全），多候选并发受 `LLM_MAX_CONCURRENCY` 约束，避免触发供应商限频后大面积降级。
- **会话记忆**：部分接口会调用 `_persist_lsta` 写入 `llm_memory`，便于审计与联调（见 `listingApi`）。

---

## 8. 文档与代码索引

| 主题 | 路径 |
|------|------|
| HTTP 路由与请求体 | `LSTA/api/listingApi.py` |
| 优化 / 诊断 / 评分 / 多候选 | `LSTA/core/listingCore.py` |
| 提示词模板与默认值 | `LSTA/prompt/listingPrompt.py` |
| 请求/响应模型 | `LSTA/models/listingState.py` |

---

## 9. 一次性生成 10 个优化（`variant_count = 10`）——你传了什么、Prompt 里有什么、模型回了什么

以下均指 **`POST /lsta/optimize`**，且请求体 **`variant_count` 为 2～10**（含 10）时走 `listing_optimizer.optimize_multi` 的路径。

### 9.1 HTTP 请求体里，哪些字段会进「生成」用的 Prompt

与单次优化相同，会进入（或影响）**每一条候选**生成提示词的字段主要包括（见 `ListingOptimizeRequest` 与 `optimize_listing` 组装的 `common_kwargs`）：

| 字段 | 作用 |
|------|------|
| `asin` / `marketplace` | 拉取或校验 `ProductData`；写入 Prompt 中「原始产品数据」区块 |
| `product_data` | 若传入则跳过抓取，直接作为 Prompt 里的当前标题/五点/描述等 |
| `target_keywords` | 拼成逗号分隔串写入「用户指定的重点关键词」 |
| `target_audience` | 写入「目标受众 / 修改意见」；**多候选时每条还会再追加一段风格指令**（见 9.2） |
| `language` | 决定输出语言说明句（如 English / 日本語） |
| `prompt_overrides` | 覆盖 `PROMPT_DEFAULTS` 中可配置片段，再参与 `build_system_prompt` |
| `competitor_products` | 拼成「竞品 Listing 参考」块（增强路径与标准路径都会在对应 builder 里带上） |
| `enable_fab` | 选择 **增强** 或 **标准** 整套生成模板（见第 3 节） |
| `review_analysis` | 仅在 `enable_fab=true` 时交给 `build_enhanced_optimize_prompt`，无则传 `None`（函数内可处理） |
| `optimize_sections` | 仅在 **`enable_fab=false`** 时传入 `_optimize_with_data`，控制只优化部分模块并在解析后回填未改字段；**FAB 增强路径当前未把 `optimize_sections` 传给增强 builder**（多选 FAB 时等于全量优化） |
| `color` | 若非空（或接口内自动查库），在调用 `optimize` 前拼进 `target_audience` 开头：要求保留真实颜色 |

**`model` / `eval_model`**：分别作为生成阶段与评分阶段 `model_pool.call_llm` 的 `preferred_model`（评分默认回退到与生成相同模型，除非单独传 `eval_model`）。

**`tri_dim`**：不写入生成 Prompt；用于 **候选排序权重**（见第 6 节）。`variant_count > 1` 且前端未带 `tri_dim` 时，接口会尝试 `_query_tri_dim` 兜底。

### 9.2 10 条候选之间，Prompt **哪里不同**

- **相同部分**：同一 `ProductData`、同一套 `build_system_prompt`、同一 `enable_fab` 分支下的主模板（增强或标准）、相同的 `target_keywords` / 竞品 / 颜色前缀等。
- **不同部分**：仅 **`target_audience` 末尾追加** `_build_variant_directive` 生成的段落，格式为：「本次为候选 k/10」「请采用【风格名】创作风格：…」。风格名在 `ListingOptimizer._VARIANT_STYLES` 共 10 种，**按候选下标对 10 取模循环**；因此 **第 1～10 号候选各对应一种风格**，第 11 个若存在才会与第 1 个风格重复（当前上限 10）。

### 9.3 传给 LLM 的「消息」长什么样（生成阶段）

代码里**没有单独的 Chat `system` role**，而是把身份与禁令写在 **同一条 `user` 消息的 `content` 字符串最前面**：

```text
messages = [{"role": "user", "content": <整段 prompt 字符串>}]
```

该字符串逻辑上包含：

1. **`build_system_prompt(...)`** 产出块（身份、公司信息、能力、**合规禁令**、人群风格说明等）。
2. **任务与产品事实**：`build_enhanced_optimize_prompt(...)` 或 `build_optimize_prompt(...)` 拼出的 ASIN、站点、标题、五点、描述、类目、BSR、价格、评论分析/竞品等。
3. **「目标受众」段**：含你传的 `target_audience` + **该候选独有**的风格指令（仅 `variant_count > 1` 时）。

调用参数（生成）大致为：

- `enable_fab=true`：`temperature=0.7`，`max_tokens=8192`，`timeout=360`
- `enable_fab=false`：`temperature=0.7`，`max_tokens=4096`，`timeout=300`

多候选时，内部对单次生成设 `skip_traffic_analysis=True`，故 **生成阶段不会做流量词分析**；生成结束后再统一评分，最后只对 **综合最优** 调用一次 `analyze_traffic_words`（主要走 `traffic_word_service` 规则/数据校验，**不保证额外调 LLM**）。

### 9.4 模型在「生成」阶段应返回什么、后端解析成什么

模型被要求输出 **纯 JSON**（无 markdown 代码围栏），字段与 `_parse_optimize_response` 一致，解析为 `OptimizedListing`：

| JSON 字段 | 后端字段 |
|-----------|----------|
| `title` | `title` |
| `bullet_points` | `bullet_points`（数组，恰好 5 条由 Prompt 约束） |
| `description` | `description` |
| `search_terms` | `search_terms` |
| `optimization_notes` | `optimization_notes` |

若返回无法解析的文本，会走容错/部分恢复逻辑（见 `listingCore` 中 `_extract_json`、`_recover_partial_listing`）。

### 9.5 「评分」阶段：每个候选再传什么、传出什么

每个成功生成的候选会构造 **`_build_synthetic_product`**：用优化后的标题/五点/描述替换原 `ProductData` 对应字段，其余如品牌、类目、评分等仍用原品，用于「像真实详情页一样」被评判。

对每个候选 **并行两次** LLM（同一候选内两路并行）：

| 调用 | Prompt 模板 | 主要输入 | 模型期望输出 | 解析结果 |
|------|--------------|----------|--------------|----------|
| 曝光评分 | `EVALUATE_LISTING_PROMPT` | 合成 Listing + `search_terms`（优先用候选的 `search_terms`） | 含 `scores`（COSMO/关键词/Rufus/IDQ 子分与总分）等 JSON | `EvaluateScores`、`overall_summary`、`priority_actions` 等 |
| 转化评分 | `FREE_FORM_EVALUATE_PROMPT` | 同上合成 Listing + `search_terms` | 含 `total`（0～100）及 summary/strengths 等 JSON | `FreeFormScore` |

温度：`temperature=0.2`；四维评判 `max_tokens=8192`，无因素评分 `max_tokens=1024`。

随后计算 `composite_score = total_score × weight_expose + free_form_score.total × weight_conversion`，**`variants` 列表按该分降序**；`optimized` 字段为排序后的 **首条**（综合最优）；`best_variant_index` 为 **0**（排序后最优总在索引 0）。`tri_dim_hit` 带回权重与命中说明。

### 9.6 HTTP 响应体（你最终拿到什么）

`ListingOptimizeResponse`（节选语义）：

- **`original`**：抓取或传入的 `ProductData`。
- **`optimized`**：最优候选的 `OptimizedListing`（与 `variants[0].listing` 一致，且可能带 **`word_analysis`**，仅最优候选会做流量词分析）。
- **`variants`**：长度最多 10 的 `OptimizedVariant` 列表；每项含 `variant_index`、`listing`、四维 `scores`/`total_score`、`free_form_score`、`composite_score`、`is_best`、`generate_error`/`evaluate_error` 等。
- **`best_variant_index`**：多候选时为 **0**（实现上排序后固定写 0）。
- **`tri_dim_hit`**：加权规则与是否命中流量/转化异常。

### 9.7 LLM 调用次数粗算（`variant_count = 10`）

- **生成**：最多 10 次（每候选 1 次；失败也会占一次调用尝试）。
- **评分**：每成功候选 **2** 次 LLM（曝光四维评判 + 转化无因素评分，**同一候选内两路并行**），10 个都成功则约 20 次。
- **收尾**：对最优执行 `analyze_traffic_words`，当前实现以 `traffic_word_service` 为主，**一般不计入上述 LLM 次数**。

合计约 **30 次 LLM**（10 生成 + 20 评分，无失败时），且受 `LLM_MAX_CONCURRENCY` 与最小调用间隔节流，**不会 10 路生成无节制并发**。

---

*若后续前端或运营流程有固定 SOP，可在本节追加「截图 + 字段填写示例」而不必改引擎代码。*
