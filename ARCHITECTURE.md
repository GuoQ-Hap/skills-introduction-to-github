# RIC-Train 系统架构与技术文档

> 版本：v1.0 | 更新日期：2026-04-03

---

## 目录

- [1. 系统概述](#1-系统概述)
- [2. 技术栈](#2-技术栈)
- [3. 项目结构](#3-项目结构)
- [4. 功能架构](#4-功能架构)
  - [4.1 LMA — RAG 文档检索问答](#41-lma--rag-文档检索问答)
  - [4.2 LDA — 自然语言查数](#42-lda--自然语言查数)
  - [4.3 Admin — 后台管理系统](#43-admin--后台管理系统)
  - [4.4 Base — 公共基础层](#44-base--公共基础层)
- [5. 数据流](#5-数据流)
- [6. API 接口总览](#6-api-接口总览)
- [7. 模型池与统一 LLM 调用](#7-模型池与统一-llm-调用)
- [8. 记忆系统](#8-记忆系统)
- [9. 配置管理](#9-配置管理)
- [10. 日志系统](#10-日志系统)
- [11. 环境依赖与部署](#11-环境依赖与部署)
  - [11.1 外部服务依赖](#111-外部服务依赖)
  - [11.2 Docker 部署](#112-docker-部署)
  - [11.3 裸机部署](#113-裸机部署)
  - [11.4 .env 配置说明](#114-env-配置说明)
- [12. 维护指南](#12-维护指南)

---

## 1. 系统概述

RIC-Train 是一个基于 FastAPI 的 **AI 智能服务平台**，整合了多个 AI 能力模块：

- **LMA**：RAG（检索增强生成）文档问答引擎，支持文档上传、向量化、混合检索与 LLM 生成回答
- **LDA**：自然语言转 SQL 引擎，用户用自然语言提问，系统自动生成 SQL 查询 StarRocks 数据仓库并分析结果
- **Admin**：统一后台管理系统，提供仪表盘、配置热更新、模型池管理、记忆管理、日志实时查看等运维能力

三个模块共享 **Base 公共基础层**，统一管理数据库连接、LLM 客户端、配置加载、日志系统和工具库。

服务同时集成了 **飞书 WebSocket 长连接机器人**，LMA 和 LDA 各有独立的飞书机器人应用，可通过飞书消息直接交互。

```
┌────────────────────────────────────────────────────────┐
│                    FastAPI (端口 8000)                   │
│                                                        │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   LMA    │  │     LDA      │  │     Admin        │  │
│  │  /lma    │  │    /lda      │  │  /admin + /admin │  │
│  │  RAG问答  │  │  NLP→SQL查数  │  │  /api   后台管理 │  │
│  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘  │
│       │               │                   │            │
│  ┌────┴───────────────┴───────────────────┴────────┐   │
│  │              Base 公共基础层                       │   │
│  │  Config · Client · Service · Ai · Repository    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │          飞书 WebSocket 长连接 (后台线程)           │  │
│  │      FeishuBot (LMA)  +  STIFeishuBot (LDA)      │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
         │          │           │           │
    ┌────┴──┐  ┌───┴───┐  ┌───┴───┐  ┌───┴────┐
    │ MySQL │  │Milvus │  │StarRo │  │ MinIO  │
    │(记忆库)│  │(向量库)│  │ cks   │  │(对象)  │
    └───────┘  └───────┘  └───────┘  └────────┘
```

---

## 2. 技术栈

| 层级 | 技术选型 | 版本 | 说明 |
|------|---------|------|------|
| **语言** | Python | 3.11+ | 主开发语言 |
| **Web 框架** | FastAPI + Uvicorn | 0.118 / 0.23 | 异步 HTTP 服务 |
| **配置管理** | Pydantic Settings | 2.12 | 类型安全的 `.env` 加载 |
| **LLM 客户端** | OpenAI SDK | 2.8 | 统一的 OpenAI 兼容接口 |
| **LLM 提供商** | DashScope / DeepSeek / OpenAI | — | 通义千问系列为主力 |
| **向量数据库** | Milvus | 2.4+ | 文档向量存储与混合检索 |
| **关系数据库** | MySQL (PyMySQL) | 8.0+ | 应用主库、记忆存储 |
| **分析数据库** | StarRocks | — | STI 模块的数据查询源 |
| **对象存储** | MinIO | — | 文件/音频存储 |
| **文本处理** | jieba / NLTK | — | 中文分词、NLP 预处理 |
| **向量化** | DashScope Embedding (text-embedding-v3) | — | 文档向量化 |
| **即时通讯** | 飞书 lark-oapi (WebSocket) | 1.5 | 飞书机器人长连接 |
| **前端** | React 18 + Ant Design 5 (CDN) | — | 后台管理 SPA |
| **容器化** | Docker + Docker Compose | — | 生产部署 |
| **系统监控** | psutil | 7.2 | 进程/系统资源监控 |

---

## 3. 项目结构

```
ric-train-master/
├── main.py                          # 主入口：启动 FastAPI、注册路由、启动飞书机器人和模型池
├── Dockerfile                       # Docker 镜像构建
├── docker-compose.yml               # 容器编排
├── requirements.txt                 # Python 依赖清单
├── .env                             # 环境变量配置（不入仓库）
├── .env.production                  # 生产环境配置模板
├── model_pool.json                  # 模型池运行时状态（自动生成）
│
├── admin/                           # 后台管理系统
│   ├── __init__.py
│   ├── router.py                    # API 路由定义（30+ 端点）
│   ├── service.py                   # 业务逻辑（仪表盘/配置/日志/模型/DB/Milvus）
│   ├── model_pool.py                # 模型池服务（测试/主备切换/统一调用）
│   └── static/
│       └── index.html               # React 单页应用前端
│
├── LMA/                             # RAG 文档检索问答模块
│   ├── constants.py                 # Milvus集合名、分块参数等常量
│   ├── main.py                      # 独立运行入口（可选，端口 8002）
│   ├── pipeline.py                  # 本地入库脚本
│   ├── api/
│   │   └── coreApi.py               # HTTP 接口：文档上传 + RAG 问答
│   ├── core/
│   │   ├── embeddingCore.py          # 文档处理编排：读取→分块→向量化→写入Milvus
│   │   └── qaCore.py                 # RAG 问答核心：检索+LLM生成+记忆
│   ├── service/
│   │   ├── embeddingService.py       # Qwen Embedding 向量化
│   │   ├── milvusService.py          # Milvus 集合管理与写入
│   │   ├── retrievalService.py       # 混合检索（Dense + BM25 + RRF 融合）
│   │   └── textService.py            # PDF/文本加载与智能切分
│   ├── prompt/
│   │   └── qaPrompt.py               # RAG 系统/用户提示词模板
│   ├── feishu/
│   │   └── feishuBot.py              # 飞书机器人（LMA RAG）
│   └── router/
│       └── router.py                 # 路由注册（挂载到 /lma）
│
├── LDA/                             # 自然语言转 SQL 查数模块
│   ├── constants.py                 # StarRocks/LLM/飞书/会话常量
│   ├── core/
│   │   └── sqlCore.py                # NLP→SQL 核心：意图识别→SQL生成→执行→分析→记忆
│   ├── api/
│   │   └── sqlApi.py                 # HTTP 接口：对话/记忆/表结构/SQL执行
│   ├── service/
│   │   ├── dbService.py              # StarRocks 连接、安全校验、查询执行
│   │   ├── schemaService.py          # 数据库表结构索引（schema_index.json）
│   │   ├── nlpService.py             # jieba分词+关键词/意图匹配
│   │   └── maskService.py            # 查询结果 PII 脱敏
│   ├── prompt/
│   │   └── sqlPrompt.py              # SQL 生成/分析/聊天提示词
│   ├── feishu/
│   │   └── feishuBot.py              # 飞书机器人（LDA 数据查询）
│   ├── data/
│   │   ├── schema_index.json         # 表结构中文索引（自动生成）
│   │   └── schema_raw.json           # 原始表结构缓存
│   └── router/
│       └── router.py                 # 路由注册（挂载到 /lda）
│
└── Base/                            # 公共基础层
    ├── __init__.py                  # 导出全局 settings 和默认 Qwen LLM
    ├── Config/
    │   ├── setting.py                # Pydantic Settings 聚合配置（MySQL/LLM/Redis/Milvus...）
    │   └── logConfig.py              # 日志系统（彩色控制台 + 按日轮转文件 + 错误日志分离）
    ├── Client/
    │   ├── mysqlClient.py            # MySQL 同步客户端（DBUtils 连接池）
    │   ├── milvusClient.py           # Milvus 向量库客户端（单例）
    │   ├── minioClient.py            # MinIO 对象存储客户端
    │   ├── redisClient.py            # Redis 客户端
    │   ├── emailClient.py            # 邮件发送客户端
    │   ├── asrClient.py              # 语音识别（ASR）客户端
    │   └── jiebaClient.py            # jieba 分词初始化
    ├── Service/
    │   ├── memoryDbService.py         # 统一 LLM 记忆持久化（llm_memory 表）
    │   ├── aiService.py               # AI 辅助（问题改写等）
    │   ├── llmSessionService.py       # LLM 会话摘要
    │   ├── llmConversationService.py  # 对话持久化与迁移
    │   └── MemoryV1Service.py         # 简易记忆检索
    ├── Ai/
    │   ├── base/
    │   │   ├── baseLlm.py             # LLM 抽象基类（invoke / chat）
    │   │   ├── baseMessages.py        # SystemMessages / UserMessages
    │   │   └── baseEnum.py            # 枚举定义
    │   ├── llms/
    │   │   ├── qwenLlm.py             # 通义千问 LLM 实现
    │   │   └── deepseekLlm.py         # DeepSeek LLM 实现
    │   └── prompt/
    │       └── commonPrompt.py        # 通用提示词
    ├── Repository/                    # ORM / 数据访问层
    │   ├── base/                      # 连接管理器、基础模型
    │   ├── connections/               # MySQL / Postgres / SQLite / Milvus 连接
    │   └── models/                    # DB 模型定义
    ├── RicUtils/                      # 工具库
    │   ├── pathUtils.py               # 项目根路径查找
    │   ├── pdfUtils.py                # PDF 处理
    │   ├── httpUtils.py               # HTTP 响应封装
    │   ├── fileUtils.py               # 文件操作
    │   ├── dateUtils.py               # 日期工具
    │   └── ...                        # 其他工具
    └── Models/                        # 公共数据模型
        ├── BaseLLMSession.py
        └── BaseLLMConversationModel.py
```

---

## 4. 功能架构

### 4.1 LMA — RAG 文档检索问答

**功能**：上传文档 → 自动切分+向量化 → 存入 Milvus → 用户提问时混合检索 → LLM 生成回答

```
用户提问
   │
   ▼
LeangQACore.ask()
   │
   ├─ 1. 深度回忆（检索历史相关记忆）
   ├─ 2. retrievalService.search()
   │     ├─ Dense 向量检索（Milvus）
   │     ├─ BM25 稀疏检索（可选）
   │     └─ RRF 融合排序
   ├─ 3. 构建 RAG Prompt（系统提示 + 检索上下文 + 记忆上下文 + 用户问题）
   ├─ 4. QwenLlm.invoke() → LLM 生成回答
   └─ 5. memoryDbService.save() → 持久化记忆到 MySQL
```

**关键参数**：

| 参数 | 环境变量 | 默认值 | 说明 |
|------|---------|-------|------|
| 默认集合 | `MILVUS_COLLECTION_NAME` | `leang_documents` | Milvus 集合名 |
| 分块大小 | `LEANG_CHUNK_SIZE` | 800 | 文本分块字符数 |
| 分块重叠 | `LEANG_CHUNK_OVERLAP` | 100 | 相邻分块重叠字符 |
| BM25 | `LEANG_ENABLE_BM25` | 1 | 是否启用混合检索 |

### 4.2 LDA — 自然语言查数

**功能**：用户自然语言提问 → 意图识别 → 匹配数据表 → LLM 生成 SQL → 执行查询 StarRocks → LLM 分析结果

```
用户提问："上个月的营收是多少？"
   │
   ▼
LLMNLPtoSQL.process()
   │
   ├─ 1. 意图识别（query/chat/followup）
   │     └─ model_pool.call_llm() → 统一模型池调用
   ├─ 2. [query] nlpService → jieba 分词 + 关键词匹配
   │     └─ schemaService → 查找相关表和字段
   ├─ 3. LLM 生成 SQL
   │     └─ SQL 安全校验（禁止 DROP/DELETE/UPDATE 等）
   ├─ 4. dbService.execute_sql() → 执行查询
   │     └─ 空结果重试（放宽条件重新生成 SQL）
   ├─ 5. maskService → PII 数据脱敏
   ├─ 6. LLM 分析查询结果 → 生成自然语言回答
   └─ 7. memoryDbService.save() → 持久化记忆
```

**关键特性**：
- 所有 LLM 调用通过 `model_pool.call_llm()` 统一管理，主模型不可用时自动切换备用池
- SQL 安全校验：仅允许 SELECT 查询，禁止 DDL/DML 操作
- 查询结果 PII 脱敏：手机号、身份证、银行卡等自动遮蔽
- 空结果智能重试：当查询无结果时自动放宽条件重新查询

### 4.3 Admin — 后台管理系统

**前端技术**：React 18 + Ant Design 5（通过 CDN 加载，无需构建工具）

提供以下管理能力：

| 功能模块 | 说明 |
|---------|------|
| **仪表盘** | CPU/内存/磁盘使用率、线程数、运行时长、各服务健康状态 |
| **配置管理** | 分类展示所有 `.env` 配置项，支持在线编辑并即时生效（热重载） |
| **日志管理** | 日志文件列表、搜索/过滤/分页查看、**实时日志**（2s 轮询尾部） |
| **模型管理** | 预设大模型列表（40+）、在线测试任意模型、查看当前配置 |
| **模型池** | 主模型/备用池/失败列表、全量测试、单独重测、手动调整主备 |
| **数据库** | MySQL/StarRocks 连接查看、表列表浏览、在线 SQL 执行 |
| **Milvus** | 向量集合列表、实体数量查看 |
| **记忆管理** | 全局记忆统计、会话列表、全文搜索、深度回忆、按会话清除 |

**访问地址**：`http://<host>:8000/admin`

### 4.4 Base — 公共基础层

Base 是所有模块的共享底座，提供：

| 子模块 | 职责 |
|--------|------|
| `Config/setting.py` | Pydantic Settings 聚合：从 `.env` 自动加载 MySQL / LLM / Redis / Milvus / MinIO 等全部配置 |
| `Config/logConfig.py` | 日志系统：彩色控制台 + 按日轮转文件（保留30天） + ERROR 级别独立文件 |
| `Client/*` | 各外部服务客户端封装（MySQL / Redis / Milvus / MinIO / Email / ASR） |
| `Ai/base/` | LLM 抽象基类，定义 `invoke(prompt)` 和 `chat(messages)` 接口 |
| `Ai/llms/` | 具体 LLM 实现：QwenLlm（通义千问）、DeepSeekLlm |
| `Service/memoryDbService.py` | 统一记忆持久化到 MySQL `llm_memory` 表 |
| `Repository/` | 通用 ORM 连接管理器（MySQL / Postgres / SQLite / Milvus） |
| `RicUtils/` | 工具库：路径、PDF、HTTP、文件、日期、Excel、装饰器等 |

---

## 5. 数据流

### 5.1 请求链路

```
HTTP 请求 / 飞书消息
        │
        ▼
   FastAPI Router
        │
   ┌────┴────┐
   │         │
/lma/*   /lda/*
   │         │
   ▼         ▼
 qaCore   sqlCore ──→ model_pool.call_llm()
   │         │              │
   │         │         ┌────┼────────────┐
   │         │         │    │            │
   │         │     DashScope DeepSeek  STI模型
   │         │         │
   │         ├─────────┤
   │         │         │
   ▼         ▼         ▼
memoryDbService.save() → MySQL (llm_memory)
```

### 5.2 数据存储分布

| 存储 | 用途 | 数据内容 |
|------|------|---------|
| **MySQL** (主库) | 应用数据 + 对话记忆 | `llm_memory` 表（永久保留）、业务表 |
| **StarRocks** | STI 数据仓库 | 业务数据（供 NLP→SQL 查询） |
| **Milvus** | 向量存储 | Leang 文档向量、BM25 稀疏向量 |
| **MinIO** | 对象存储 | 上传的文件、音频转写文本 |
| **文件系统** | 运行时状态 | `model_pool.json`（模型池状态）、`logs/`（日志） |

---

## 6. API 接口总览

### 主服务 (端口 8000)

#### LMA 模块 `/lma`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/lma/ingest` | 上传文档并入库向量化 |
| POST | `/lma/chat` | RAG 问答 |

#### LDA 模块 `/lda`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/lda/health` | 健康检查 |
| POST | `/lda/chat` | 自然语言查数对话 |
| GET | `/lda/memory/{session_id}` | 查看会话记忆 |
| DELETE | `/lda/memory/{session_id}` | 清除会话记忆 |
| GET | `/lda/tables?keyword=` | 搜索数据表 |
| GET | `/lda/table/{table_name}` | 查看表结构 |
| POST | `/lda/sql` | 直接执行 SQL |

#### Admin 后台管理 `/admin/api`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/dashboard` | 仪表盘数据 |
| GET | `/admin/api/config/presets` | 配置预设列表 |
| POST | `/admin/api/config/save` | 批量保存配置 |
| GET | `/admin/api/logs/files` | 日志文件列表 |
| GET | `/admin/api/logs/read` | 读取日志（搜索/过滤/分页） |
| GET | `/admin/api/logs/tail` | 实时尾部日志 |
| POST | `/admin/api/logs/level` | 动态修改日志级别 |
| GET | `/admin/api/models/list` | 已配置模型列表 |
| GET | `/admin/api/models/presets` | 预设模型库（40+） |
| POST | `/admin/api/models/test` | 在线测试模型 |
| GET | `/admin/api/db/connections` | 数据库连接列表 |
| GET | `/admin/api/db/tables` | 数据表列表 |
| POST | `/admin/api/db/execute` | 执行 SQL |
| GET | `/admin/api/milvus/collections` | Milvus 集合列表 |
| GET | `/admin/api/routes` | 全部路由列表 |
| GET | `/admin/api/pool/status` | 模型池状态 |
| POST | `/admin/api/pool/test-all` | 全量模型测试 |
| POST | `/admin/api/pool/retest` | 单模型重测 |
| POST | `/admin/api/pool/set-primary` | 设为主模型 |
| POST | `/admin/api/pool/add-standby` | 加入备用池 |
| POST | `/admin/api/pool/remove-standby` | 移出备用池 |
| GET | `/admin/api/memory/list` | 记忆列表 |
| GET | `/admin/api/memory/stats` | 记忆统计 |
| GET | `/admin/api/memory/sessions` | 会话列表 |
| GET | `/admin/api/memory/search` | 全文搜索记忆 |
| GET | `/admin/api/memory/recall` | 深度回忆 |
| GET | `/admin/api/memory/detail/{id}` | 记忆详情 |
| DELETE | `/admin/api/memory/clear` | 清除会话记忆 |

#### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/execute_sql` | 根级 SQL 执行（主库） |
| GET | `/admin` | 后台管理前端页面 |

---

## 7. 模型池与统一 LLM 调用

### 7.1 架构

模型池 (`ModelPoolService`) 是系统的 LLM 调用中枢，实现了 **自动健康检测 + 主备切换 + 故障自动恢复**：

```
                 ┌─────────────────┐
                 │  ModelPoolService │
                 │  (单例, 线程安全)  │
                 └───────┬─────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
     │  主模型   │   │ 备用池   │   │ 失败列表 │
     │ primary  │   │ standby │   │ failed  │
     └─────────┘   └─────────┘   └─────────┘
```

### 7.2 工作流程

1. **启动全量测试**：应用启动时，后台线程自动测试所有配置的模型
2. **分类入池**：测试通过 → 备用池（第一个通过的设为主模型）；测试失败 → 失败列表
3. **统一调用** (`call_llm`)：优先使用主模型，失败后依次尝试备用池中的模型
4. **自动提升**：备用模型调用成功后自动提升为新的主模型
5. **状态持久化**：池状态保存到 `model_pool.json`，重启后自动恢复

### 7.3 已集成的模型来源

| 来源 | Provider ID | 配置来源 |
|------|------------|---------|
| 通义千问 (DashScope) | `dashscope` | `DASHSCOPE_API_KEY` + `QWEN_BASE_URL` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL` |
| STI 主模型 | `sti` | `STI_LLM_API_KEY` + `STI_LLM_BASE_URL` |
| STI 备用模型 | `sti_fallback` | `STI_LLM_FALLBACK_API_KEY` + `STI_LLM_FALLBACK_BASE_URL` |

---

## 8. 记忆系统

### 8.1 设计原则

- **永不自动清除**：数据库中的记忆永久保留，仅支持后台管理手动删除
- **按需加载**：内存缓存仅用于当前会话热读加速
- **深度回忆**：跨会话、跨模块的智能检索，为 LLM 提供更丰富的历史上下文

### 8.2 存储结构

所有记忆统一存入 MySQL `llm_memory` 表：

| 字段 | 类型 | 说明 |
|------|------|------|
| `module` | VARCHAR(32) | 模块标识：`sti` / `leang`（历史兼容） |
| `session_id` | VARCHAR(128) | 会话 ID |
| `user_query` | TEXT | 用户原始问题 |
| `assistant_response` | TEXT | AI 回复 |
| `intent` | VARCHAR(32) | 意图：`query` / `chat` / `followup` / `ask` |
| `sql_text` | TEXT | 执行的 SQL（STI 专用） |
| `row_count` | INT | 返回行数（STI 专用） |
| `columns_json` | JSON | 返回列名（STI 专用） |
| `rows_json` | JSON | 返回数据（STI 专用，最多50行） |
| `sources_json` | JSON | 检索来源（Leang 专用） |
| `collection_name` | VARCHAR(128) | Milvus 集合名（Leang 专用） |
| `latency_ms` | INT | 响应耗时 |
| `created_at` | DATETIME | 创建时间 |

索引：`module+session_id`、`session_id+created_at`、`module+created_at`、`FULLTEXT(user_query, assistant_response)`

### 8.3 深度回忆

通过 MySQL 全文索引（ngram parser）实现跨会话智能搜索：

```python
memory_db.deep_recall(
    query="上个月营收",
    module="all",      # 跨模块搜索
    limit=10
)
```

---

## 9. 配置管理

### 9.1 配置加载机制

```
.env 文件
    │
    ▼
BaseEnvSettings (pydantic-settings)
    │
    ├─ MySQLSettings    (env_prefix="DB_")
    ├─ DashScopeSettings (alias 映射)
    ├─ DeepSeekSettings  (alias 映射)
    ├─ RedisSettings    (env_prefix="REDIS_")
    ├─ MilvusSettings   (env_prefix="MILVUS_")
    ├─ MinIOSettings    (env_prefix="MINIO_")
    ├─ TencentCOSSettings (env_prefix="TC_")
    └─ ...更多子配置
    │
    ▼
Settings (聚合单例) → settings = get_settings()
```

### 9.2 热更新

通过后台管理系统修改配置时：
1. 写入 `.env` 文件
2. 设置 `os.environ` 环境变量
3. 重新实例化 `Settings` 单例
4. 即时生效，无需重启

### 9.3 模块常量

`LMA/constants.py` 和 `LDA/constants.py` 中还有部分通过 `os.getenv()` 直接读取的常量（Milvus 集合名、STI 数据库配置等），这些在进程启动时固定，修改后需重启生效。

---

## 10. 日志系统

### 10.1 日志配置

| 输出 | 格式 | 保留策略 |
|------|------|---------|
| 控制台 | 彩色（ANSI） | — |
| `logs/app.log` | 标准文本 | 按日轮转，保留 30 天 |
| `logs/app.error.log` | 标准文本（仅 ERROR+） | 按日轮转，保留 30 天 |

格式：`%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s`

### 10.2 日志级别

- 通过 `.env` 中的 `LOG_LEVEL` 设置初始级别（默认 `INFO`）
- 可在后台管理中**动态切换**日志级别，无需重启
- 支持：`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`

### 10.3 实时日志

后台管理提供实时日志功能，每 2 秒轮询尾部日志，支持：
- 按级别过滤（DEBUG / INFO / WARNING / ERROR）
- 自动滚动 / 暂停
- 可配置显示行数（100 / 200 / 500 / 1000）

---

## 11. 环境依赖与部署

### 11.1 外部服务依赖

| 服务 | 用途 | 是否必须 |
|------|------|---------|
| **MySQL 8.0+** | 应用主库 + 记忆存储 | 必须 |
| **Milvus 2.4+** | 文档向量检索 | Leang 模块必须 |
| **StarRocks** | 数据仓库查询 | STI 模块必须 |
| **MinIO** | 对象存储 | 可选（文件上传/ASR 功能需要） |
| **Redis** | 缓存 | 可选（当前未深度使用） |

### 11.2 Docker 部署

**前置要求**：Docker 20.10+、Docker Compose v2+

```bash
# 1. 准备配置
cp .env.production .env
vi .env    # 填入真实配置

# 2. 创建运行时文件
mkdir -p logs
touch model_pool.json

# 3. 构建并启动
docker compose up -d --build

# 4. 查看日志
docker compose logs -f

# 5. 验证
curl http://localhost:8000/admin
```

**docker-compose.yml** 说明：

| 配置 | 值 | 说明 |
|------|-----|------|
| 端口映射 | `8000:8000` | HTTP 服务 |
| 环境变量 | `env_file: .env` | 注入环境变量 |
| 日志卷 | `./logs:/app/logs` | 持久化日志 |
| 配置卷 | `./.env:/app/.env` | 支持后台配置管理热更新 |
| 状态卷 | `./model_pool.json:/app/model_pool.json` | 模型池状态持久化 |
| 日志策略 | `max-size: 50m, max-file: 3` | Docker 日志限制 |
| 重启策略 | `unless-stopped` | 异常退出自动重启 |

### 11.3 裸机部署

```bash
# 1. 安装系统依赖
sudo apt install -y python3.11 python3.11-venv gcc \
    default-libmysqlclient-dev pkg-config ffmpeg

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 3. 配置
cp .env.production .env && vi .env

# 4. 启动
uvicorn main:app --host 0.0.0.0 --port 8000
```

**systemd 服务**（生产推荐）：

```ini
# /etc/systemd/system/ric-train.service
[Unit]
Description=RIC Train AI Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/ric-train-master
Environment=PATH=/opt/ric-train-master/venv/bin:/usr/bin
ExecStart=/opt/ric-train-master/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now ric-train
```

### 11.4 .env 配置说明

> 参考 `.env.production` 模板，以下为全部配置项分类说明：

#### 数据库

| 变量 | 说明 | 示例 |
|------|------|------|
| `DB_HOST` | MySQL 主机 | `10.0.10.21` |
| `DB_PORT` | MySQL 端口 | `23306` |
| `DB_USER` | MySQL 用户 | `guoqing` |
| `DB_PASSWORD` | MySQL 密码 | `guoqing666` |
| `DB_NAME` | 数据库名 | `ric_ai_base` |
| `DB_CHARSET` | 字符集 | `utf8mb4` |
| `STI_DB_HOST` ~ `STI_DB_CHARSET` | StarRocks 连接 | 同上格式 |

#### AI 模型

| 变量 | 说明 | 示例 |
|------|------|------|
| `DASHSCOPE_API_KEY` | 通义千问 API Key | `sk-xxxx` |
| `QWEN_BASE_URL` | 通义千问 Base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `QWEN_DEFAULT_MODEL` | 默认模型 | `qwen3-max` |
| `QWEN_EMBEDDING_MODEL_NAME` | 向量化模型 | `text-embedding-v3` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | `sk-xxxx` |
| `DEEPSEEK_BASE_URL` | DeepSeek Base URL | `https://api.deepseek.com` |
| `DEEPSEEK_DEFAULT_MODEL` | DeepSeek 默认模型 | `deepseek-chat` |
| `STI_LLM_API_KEY` | STI 主 LLM Key | `sk-xxxx` |
| `STI_LLM_BASE_URL` | STI 主 LLM URL | `https://www.aitokens.link/v1` |
| `STI_LLM_MODEL` | STI 主 LLM 模型 | `gpt-3.5-turbo` |
| `STI_LLM_FALLBACK_*` | STI 备用 LLM | 同上格式 |
| `LLM_TIMEOUT` | LLM 调用超时（秒） | `30` |

#### 向量数据库 (Milvus)

| 变量 | 说明 | 示例 |
|------|------|------|
| `MILVUS_HOST` | 主机 | `10.0.10.106` |
| `MILVUS_PORT` | 端口 | `19530` |
| `MILVUS_URI` | URI（优先级高于 host:port） | `http://10.0.10.106:19530` |
| `MILVUS_USER` / `MILVUS_PASSWORD` | 认证 | `leang` / `Abc123123.` |
| `MILVUS_DATABASE` | 数据库 | `default` |
| `MILVUS_COLLECTION_NAME` | 默认集合 | `leang_documents` |

#### 对象存储

| 变量 | 说明 |
|------|------|
| `MINIO_ENDPOINT` | MinIO 地址 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | MinIO 认证 |
| `TC_SECRET_ID` / `TC_SECRET_KEY` | 腾讯云 COS（可选） |

#### 飞书

| 变量 | 说明 |
|------|------|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | LMA 飞书机器人 |
| `STI_FEISHU_APP_ID` / `STI_FEISHU_APP_SECRET` | LDA 飞书机器人 |

#### 其他

| 变量 | 说明 | 默认 |
|------|------|------|
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `FFMPEG_PATH` | FFmpeg 路径 | 容器内 `/usr/bin/ffmpeg` |

> **Docker 部署注意**：所有服务地址必须使用**内网 IP**，不能用 `localhost`（容器内 localhost 指向容器自身）。

---

## 12. 维护指南

### 12.1 日常运维

| 操作 | 命令 / 方式 |
|------|------------|
| 查看服务状态 | `docker compose ps` 或 `systemctl status ric-train` |
| 查看实时日志 | 后台管理 → 日志管理 → 实时日志 |
| 修改配置 | 后台管理 → 配置管理 → 在线编辑（即时生效） |
| 重启服务 | `docker compose restart` 或 `systemctl restart ric-train` |
| 查看模型状态 | 后台管理 → 模型池 → 查看主备状态 |
| 全量模型测试 | 后台管理 → 模型池 → 全量测试 |
| 切换主模型 | 后台管理 → 模型池 → 设为主模型 |

### 12.2 代码更新

```bash
# Docker 方式
git pull && docker compose up -d --build

# 裸机方式
git pull
source venv/bin/activate
pip install -r requirements.txt    # 如有依赖变化
sudo systemctl restart ric-train
```

### 12.3 数据库维护

- **llm_memory 表**：永久保留，随时间增长。如需清理，通过后台管理的记忆管理模块按会话手动删除
- **MySQL 备份**：建议每日备份 `ric_ai_base` 数据库
- **Milvus**：集合数据通过 Leang `/ingest` 接口管理，支持多集合

### 12.4 日志维护

- 日志自动按日轮转，保留 **30 天**
- 位置：`logs/app.log`（全部）、`logs/app.error.log`（仅 ERROR）
- Docker 容器日志限制：单文件最大 50MB，最多保留 3 个

### 12.5 模型池维护

- `model_pool.json` 持久化模型池状态，重启自动恢复
- 模型 API Key 余额不足时会自动降级到备用模型
- 建议定期在后台管理执行全量测试，确认模型可用性

### 12.6 常见问题排查

| 问题 | 排查方向 |
|------|---------|
| 服务启动失败 | 检查 `.env` 配置（尤其是数据库连接）；检查端口占用 |
| LLM 调用失败 | 后台管理 → 模型池 → 查看失败列表和错误信息 |
| 数据库连接失败 | 确认 IP/端口/密码；Docker 中不要用 `localhost` |
| Milvus 连接失败 | 确认 URI 格式；检查防火墙/安全组 |
| 白屏/前端异常 | 检查 CDN 是否可访问（React / Ant Design）；查看浏览器控制台 |
| 记忆未保存 | 确认 `llm_memory` 表已创建（首次调用时自动建表） |
| 配置修改未生效 | 通过后台管理修改的即时生效；`constants.py` 中的需重启 |

