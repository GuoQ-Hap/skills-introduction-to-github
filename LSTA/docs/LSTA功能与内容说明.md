# LSTA 模块功能与内容说明

本文档对仓库内 **LSTA（Listing Smart Tuning Agent / lAi_listing）** 模块的能力、HTTP 接口、数据模型、服务层与配置作系统说明，便于产品、运营与研发查阅。

**API 统一前缀**：`/lsta`（由 `LSTA/router/router.py` 注册）。

**主入口**：根应用 `main.py` 中 `init_listing_router(app)`；亦可独立启动 `uvicorn LSTA.main:app --host 0.0.0.0 --port 8003`。

---

## 1. 模块定位与能力概览

LSTA 面向 **Amazon 跨境电商 Listing**，在合规前提下提供：

| 能力域 | 说明 |
|--------|------|
| **数据抓取** | 按 ASIN + 站点拉取标题、五点、描述、类目、价格、评论摘要等（`amazonService`，可选 SP-API / 代理） |
| **LLM 优化** | 生成或迭代标题、五点、描述、后台搜索词；支持 FAB 增强、竞品参考、评论洞察、分模块优化、多候选择优 |
| **四维诊断与评分** | 基于 COSMO / 关键词 / Rufus / IDQ 框架的诊断报告与结构化打分 |
| **广告与数据侧** | 三维诊断（Doris/LDA）、流量词（ABA/SQR MySQL）、SQR 搜索量档位、搜索词相关性 Excel 链路 |
| **运营闭环** | 流量词决策后 Refine、Milvus 向量入库（LMA）、领星 ERP 推送 |
| **辅助** | 评论分析、竞品发现、批量翻译（hover）、异步任务与进度 |

---

## 2. 目录结构与职责

| 路径 | 职责 |
|------|------|
| `LSTA/main.py` | 独立 FastAPI 应用；启动时可跑 `model_pool` 自检 |
| `LSTA/router/router.py` | 将 `listingApi` 的 `APIRouter` 挂到前缀 `/lsta` |
| `LSTA/api/listingApi.py` | 全部 HTTP 路由、`_persist_lsta` 会话持久化、后台任务入口 |
| `LSTA/core/listingCore.py` | `ListingOptimizer`：fetch / optimize / optimize_multi / analyze / evaluate / refine / 流量词分析与相关性评估 |
| `LSTA/prompt/listingPrompt.py` | 系统提示、各策略模板、`PROMPT_DEFAULTS`、合规禁令 |
| `LSTA/models/listingState.py` | Pydantic 请求/响应与枚举 |
| `LSTA/constants.py` | 站点域名/语言、代理与 DB 环境变量、抓取超时与重试 |
| `LSTA/service/*.py` | 亚马逊抓取、流量词、三维 SQL、产品颜色、SQR 量、搜索词推荐、评论分析、竞品发现、领星、异步任务等 |

**跨包依赖（典型）**：

- `admin.model_pool`：统一 LLM 调用与主备切换  
- `LDA.service.dbService`：三维诊断 SQL 执行（Doris）  
- `LMA.service.embeddingService` / `milvusService`：`/embed`  
- `Base.Service.memoryDbService`：`_persist_lsta` 写入 `llm_memory`  

---

## 3. HTTP 接口一览

以下方法若无特殊说明，路径均为 **`/lsta` + 下表路径**。

### 3.1 健康与配置

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/health` | 返回 `ok`、当前时间、模型池主模型 `provider:model`（`LAIHealthResponse`） |
| GET | `/prompt-defaults` | 返回 `PROMPT_DEFAULTS` 字典，供前端配置面板展示与覆盖 |

### 3.2 产品数据与诊断聚合

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/fetch` | 仅抓取 Amazon 产品数据，**不调用 LLM**。请求：`FetchProductRequest`（`asin` 10 位、`marketplace`）。响应：`ProductData` |
| POST | `/fetch-with-diagnostics` | 并行：产品 + 三维诊断（Doris）+ 流量词批量检查 + 库表颜色；若有流量词再跑 **LLM 相关性判定**（`assess_traffic_relevance`）。响应：`FetchDiagnosticsResponse`（含 `product`、`tri_dim`、`traffic_words`、`db_color` 等） |

**三维诊断 SQL 单一来源**：

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/tri-dim-diagnostic-sql` | 返回与 `triDimSqlService` 一致的 `data_sql`，可选 `count_sql`。供前端 LDA `execSql` 与后端共用，参数见 `TriDimDiagnosticSqlRequest`（`date_range`、`asin`、`page`、`page_size`、`dims`、`thresholds`、`row_filter`、`include_count_sql`） |

### 3.3 Listing 优化、诊断、评判与迭代

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/optimize` | 主优化。支持传入 `product_data` 跳过抓取；`variant_count` 2～10 时走 **`optimize_multi`**（多风格并行生成 + 四维曝光分 + 转化分 + 按三维诊断加权 `composite_score` 择优）。同步接口内 **`skip_traffic_analysis=True`**，不在此接口内做完整流量词分析。可选：`prompt_overrides`、`optimize_sections`、`competitor_products`、`custom_params`、`enable_fab`、`review_analysis`、`color`、`tri_dim`（多候选排序用） |
| POST | `/analyze` | 四维诊断报告（文本 `analysis` + 可选 `scores` / `evaluate_analysis` / `overall_summary` / `priority_actions`） |
| POST | `/evaluate` | 独立四维评判，结构化 `scores` + `analysis` + `raw_output` 等，不拼装长 Markdown 诊断主文 |
| POST | `/refine` | 根据 `user_feedback` 对当前标题/五点/描述/搜索词做针对性修改 |

**持久化**：上述写操作类接口在成功后会调用 `_persist_lsta`，将摘要写入 `llm_memory`（失败仅打日志，不阻断业务）。

### 3.4 流量词

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/check-traffic-words` | 支持 `words` 列表 **或** 整段 Listing 文本；结合 ABA/SQR；若提供 `product_title`/`product_category` 会走 `analyze_traffic_words`（含 LLM 相关性），否则返回规则侧 `WordAnalysis` |
| POST | `/apply-traffic-decisions` | 用户对弱相关词 `decisions`（保留/移除）及 `replacements`；无移除时原样返回；有移除时拼装反馈文本后调用 `refine` |

### 3.5 向量库与 ERP

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/embed` | 将完整 Listing 文本 embedding 后写入 Milvus 集合 **`listing`**（依赖 LMA） |
| GET | `/lingxing/status` | `{ "configured": bool }`，依赖环境变量 `LINGXING_APP_ID` / `LINGXING_APP_SECRET` |
| POST | `/submit-to-lingxing` | 推送标题/五点/描述/搜索词到领星 ERP（未配置返回 503） |

### 3.6 异步任务

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/task/submit` | `action`：`optimize` \| `analyze` \| `discover_competitors` \| `review_analysis` \| `fetch_product` \| `fetch_reviews`；立即返回 `task_id` |
| GET | `/task/{task_id}` | 轮询状态：`pending` / `running` / `completed` / `failed`；`partial_result` 用于多候选进度 |
| GET | `/tasks` | 当前内存中的任务列表 |
| DELETE | `/task/{task_id}` | 删除任务记录 |

**`fetch_product` 后台任务**较同步 `/fetch-with-diagnostics` 额外并行 **评论分析**（有评论时），响应字段含 `review_analysis`。

### 3.7 搜索词与 SQR

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/search-term-recommend` | ASIN → `leang_product_info`（MSKU、店铺）→ 共享目录 Excel → 搜索词 + 相关性等级；可选 `relevance_filter` |
| POST | `/sqr-search-volume` | **单词** SQR `search_query_count` 汇总 + A～F 档位；进程内 TTL 缓存（环境变量 `LSTA_SQR_VOLUME_CACHE_TTL` / `LSTA_SQR_VOLUME_CACHE_MAX`） |
| POST | `/sqr-search-volumes` | **批量**（每请求最多 **500** 个不重复词），单次聚合 SQL |

### 3.8 评论分析、竞品、翻译

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/review-analysis` | LLM 分析评论列表（最多 100 条），输出痛点/卖点/核心特点等 `ReviewAnalysisResult` |
| POST | `/discover-competitors` | 通过 Amazon 搜索发现竞品；价格容差、条数、`with_details`、颜色/尺寸/款式过滤、`min_review_count` 等；亦可 `task/submit` + `discover_competitors` |
| POST | `/translate` | 批量翻译（默认目标简体中文），**固定使用模型池中的 `gpt-4o-mini`**；单次最多 **20** 条文本；返回 JSON 数组译文 |

---

## 4. 核心数据模型摘要（`listingState.py`）

### 4.1 枚举与策略

- **`OptimizeStrategy`**：`standard` / `cosmo` / `ctr` / `cvr` / `traffic` / `custom`  
- **重要实现说明**：当前 `optimize()` 主路径按 **`enable_fab` 二分**（FAB 增强 vs 标准 SEO）；`optimize_strategy` 与 `custom_params` **尚未接入**主分支选择逻辑，仓库内虽已存在对应提示词与函数，接线情况以 `Listing优化路线.md` 为准。多候选 `optimize_multi` 同样将策略字段传入但未改变上述二分行为。

### 4.2 产品与诊断

- **`ProductData`**：`asin`、`marketplace`、`title`、`brand`、`price`、`bullet_points`、`description`、`reviews`（Top Reviews，最多约 10 条）等  
- **`TriDimDiagnostic`**：CTR/CVR/会话变化、库存、优化建议文案、MSKU、店铺、类目、销量额等  
- **`TrafficWordItem` / `TrafficWordDetail`**：词、ABA/SQR 指标、`relevance`（如 clear/fuzzy/broad/unknown）、理由等  
- **`FetchDiagnosticsResponse`**：聚合产品 + `tri_dim` + `traffic_words` + 可选 `review_analysis` + `db_color`  

### 4.3 优化结果与多候选

- **`OptimizedListing`**：标题、五点、描述、`search_terms`、`optimization_notes`、可选 `word_analysis`  
- **`OptimizedVariant`**：单候选 + `EvaluateScores` / `total_score` / `FreeFormScore` / `composite_score` / `is_best` / 错误字段  
- **`ListingOptimizeResponse`**：`original`、`optimized`、多候选时 `variants`、`best_variant_index`、`tri_dim_hit`  

### 4.4 四维评分结构

- **`EvaluateScores`**：`cosmo`、`keywords`、`rufus`、`idq` 各子项 + **`total`（0～100）**  
- 子模型如 **`CosmoScore`**（实体关系、意图映射等五项各 0～5）等  

### 4.5 其他请求体

- **`ListingOptimizeRequest`**：含 `session_id`、`model`、`eval_model`、`variant_count`（1～10）、`tri_dim`、`color` 等  
- **`TrafficWordDecisionRequest`**：`decisions`、`replacements`、当前 Listing 字段  
- **`TaskSubmitRequest`**：按 `action` 绑定对应 `*_params`  
- **`CompetitorDiscoveryRequest`** / **`TranslateRequest`** 等见源码字段说明  

---

## 5. 核心引擎行为（`listingCore.py` 摘要）

- **`fetch`**：校验并返回 `ProductData`（内部 `_fetch_and_validate`）。  
- **`optimize`**：组装提示词 → `model_pool.call_llm` → 解析 JSON 为 `OptimizedListing`；若 **`skip_traffic_analysis=False`**（同步 `/optimize` 传入为 True）会附加流量词分析与目标词缺失告警；`color` 会注入到受众提示前缀。  
- **`optimize_multi`**：并行多候选生成（每候选不同风格指令）→ 每候选并行「四维评判 + 转化评分」→ 按 **`tri_dim` 命中** 动态设置曝光/转化权重 → 排序后 **`optimized` 取最优**，并对最优做一次流量词分析。受 **`LLM_MAX_CONCURRENCY`** 与 **`_LlmRateLimiter`** 节流。  
- **`analyze` / `evaluate` / `refine`**：各自独立 prompt 与解析路径。  
- **`analyze_traffic_words`** / **`assess_traffic_relevance`**：与 `trafficWordService` 及 LLM 配合。  

**模型消息形态**：优化类调用将系统身份与禁令写在 **单条 `user` 消息** 的 content 前缀（非独立 `system` role），详见 `Listing优化路线.md` 第 9 节。

---

## 6. 服务层说明

| 服务文件 | 作用 |
|----------|------|
| `amazonService.py` | Amazon 页面或 SP-API 抓取；使用 `constants` 中代理与超时 |
| `trafficWordService.py` | ABA/SQR MySQL；`check_words` / `batch_check_listing` |
| `triDimSqlService.py` | 三维诊断 Doris SQL 生成（与 `/tri-dim-diagnostic-sql`、抓取侧 `_query_tri_dim` 同源） |
| `productDimService.py` | `leang_product_info.colour` 等产品维度查询 |
| `sqrSearchVolumeService.py` | SQR 搜索量单条/批量查询与缓存 |
| `searchTermRecommendService.py` | MSKU + Excel 搜索词推荐 |
| `reviewAnalysisService.py` | 评论 LLM 分析 |
| `competitorDiscoveryService.py` | 搜索页竞品发现与可选详情抓取 |
| `lingxingService.py` | 领星 API 提交 |
| `taskService.py` | 内存任务存储、线程执行、`update_partial` 进度 |
| `base.py` | `service_logger` |

---

## 7. 提示词可配置项（`PROMPT_DEFAULTS`）

`GET /lsta/prompt-defaults` 与优化请求体 `prompt_overrides` 可覆盖的键包括：

- **`core_capabilities`**：模型自我描述的核心能力段落  
- **`company_info`**：服务公司背景（默认凌昂科技业务说明）  
- **`bullet_rules`**：五点结构与风格规则  
- **`description_rules`**：描述长度与结构规则  

`build_system_prompt` 另含 **Amazon 政策向硬性禁令**（禁售后时长承诺、禁销量/评分数据夸大、禁未经证实的 No.1 等）及 **人群风格适配** 说明；所有生成与 `refine` 均应遵守。

---

## 8. 环境变量与常量（`constants.py` 摘要）

| 类别 | 变量示例 | 说明 |
|------|----------|------|
| 站点 | `MARKETPLACE_DOMAINS` / `MARKETPLACE_LANGUAGES` | 域名与默认语言映射 |
| 抓取 | `LAI_SCRAPER_PROXY_URL`、`LAI_SCRAPER_API_KEY`、`LAI_HTTP_PROXY` | 代理优先级见文件注释 |
| SP-API | `SP_API_*` | 配置后优先用于取数 |
| 通用 | `LAI_FETCH_TIMEOUT`、`LAI_FETCH_MAX_RETRIES`、`LAI_DEFAULT_MARKETPLACE` | 超时、重试、默认站点 |
| ABA/SQR DB | `ABA_REPORT_DB_*`、`SQR_REPORT_DB_*` | MySQL 连接流量词报表库 |
| SQR 缓存 | `LSTA_SQR_VOLUME_CACHE_TTL`、`LSTA_SQR_VOLUME_CACHE_MAX` | 搜索量接口缓存 |

---

## 9. 前端与联调提示

- 前端 `vite.config.ts` 可将 `/lsta` 代理到后端（如 `localhost:8000`）。  
- `frontend/src/api/index.ts` 封装了各 LSTA 路径的 TypeScript 调用。  
- Listing 优化页等使用 `sessionStorage` 键如 `lsta_result`、`lsta_prompt_overrides`、`lsta_batch_rows`、`lsta_model` 等缓存状态。  
- `TaskContext` 使用 `lsta_bg_tasks` 管理后台任务展示。  

---

## 10. 推荐业务流程（简版）

1. **`POST /lsta/fetch`** 或 **`/fetch-with-diagnostics`**（一次拿齐诊断与流量词）  
2. 可选 **`/analyze`** / **`/evaluate`** 看短板  
3. 可选竞品 **`/discover-competitors`** 写入优化请求的 `competitor_products`  
4. **`POST /lsta/optimize`**（重要 ASIN 可 `variant_count`>1 择优）  
5. 可选 **`/check-traffic-words`** + **`/apply-traffic-decisions`**  
6. 人工 **`/refine`**  
7. 可选 **`/embed`**、**`/submit-to-lingxing`**  

长耗时或需进度条时改用 **`/task/submit`** 轮询 **`/task/{id}`**。

---

## 11. 相关文档索引

| 文档 | 内容 |
|------|------|
| `LSTA/docs/LSTA模块架构与接口调用链.md` | 文件依赖与按请求跳转顺序 |
| `LSTA/docs/Listing优化路线.md` | 策略说明、合规、多候选细节、与实现差异 |
| `docs/listing-optimize-flow-graph.md` | Mermaid 调用关系图 |
| `docs/liting优化业务流程和系统架构.md` | 系统级架构与接口表 |

---

*文档依据仓库源码整理；接口与字段以 `LSTA/api/listingApi.py` 与 `LSTA/models/listingState.py` 为准，若代码变更请以实际为准。*
