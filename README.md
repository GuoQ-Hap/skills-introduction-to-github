# RIC-Train - 凌昂 AI 智能服务平台

RIC-Train 是面向跨境电商运营的 AI 工作台，集成 Listing 优化、自然语言查数、RAG 知识问答、广告与市场分析、库存监控和周度发货计划等能力。后端基于 FastAPI，前端基于 React + Vite + Ant Design。

## 核心模块

| 模块 | 目录 | API 前缀 | 主要能力 |
| --- | --- | --- | --- |
| Auth | `auth/` | `/auth` | 登录、鉴权、用户权限 |
| Admin | `admin/` | `/admin/api` | 模型池、系统管理 |
| Base | `Base/` | - | 配置、数据库、LLM、日志等基础能力 |
| LMA | `LMA/` | `/lma` | RAG 文档检索问答、飞书机器人 |
| LDA | `LDA/` | `/lda` | 自然语言转 SQL、查数、SQL 安全校验 |
| LSTA | `LSTA/` | `/lsta` | Amazon Listing 优化、竞品发现、评价分析、市场分析 |
| LAA | `LAA/` | `/laa` | 广告策略与运营分析能力 |
| Frontend | `frontend/` | - | 统一 Web 工作台 |

## 常用页面

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `/` | Dashboard | 首页看板 |
| `/inventory` | 库存监控分析 | 库存底表校验、发货/采购量验证、周度发货计划导出 |
| `/listing` | Listing 优化 | Listing 文案优化、候选版本、竞品/流量词辅助 |
| `/listing-records` | Listing 优化入库记录 | 查看已确认采用的优化记录和前后指标 |
| `/reviews` | Review 分析 | 评价解析与优化建议 |
| `/competitors` | 竞品发现 | 竞品搜索、过滤和对比 |
| `/market-analysis` | 市场分析 | 市场、类目、竞品分析 |
| `/positioning` | 产品定位 | 产品定位与卖点分析 |
| `/ads` | 广告策略 | 广告诊断与策略辅助 |
| `/query` | 数据查询 | 自然语言查数 |
| `/analysis` | 数据分析 | SQL/指标分析 |
| `/rag` | 知识问答 | 文档知识库问答 |
| `/system` | 系统状态 | 模型池、服务状态 |
| `/users` | 用户管理 | 用户与权限管理 |

## 目录结构

```text
.
├── main.py                    # FastAPI 主入口，挂载各业务模块
├── version.py                 # 应用版本信息
├── requirements.txt           # Python 依赖
├── docker-compose.yml         # 后端 + Nginx 部署编排
├── Dockerfile                 # 后端镜像
├── Dockerfile.nginx           # 前端/Nginx 镜像
├── nginx.conf                 # Nginx 反向代理配置
├── Base/                      # 基础设施：配置、DB、LLM、日志
├── auth/                      # 登录鉴权
├── admin/                     # 管理后台接口
├── LMA/                       # RAG 知识问答
├── LDA/                       # 自然语言查数
├── LSTA/                      # Listing/运营相关能力
├── LAA/                       # 广告/运营分析相关能力
├── frontend/                  # React 前端
├── scraper_proxy/             # 抓取代理服务
├── docs/                      # 文档
├── ops/                       # 运维脚本/配置
└── logs/                      # 本地日志目录
```

## 环境要求

- Python 3.11+ 推荐
- Node.js 20+ 推荐
- npm 10+ 推荐
- 可访问项目依赖的数据源：MySQL/Doris、Redis、Milvus、对象存储、飞书应用等

## 环境配置

复制生产模板并填写真实配置：

```bash
cp .env.production .env
```

关键配置分组：

- `DB_*`：业务库连接
- `STI_DB_*`：LDA 查数使用的 Doris/MySQL 协议连接
- `DASHSCOPE_API_KEY`、`QWEN_*`、`DEEPSEEK_*`、`STI_LLM_*`：模型服务
- `REDIS_*`：缓存
- `MILVUS_*`：向量库
- `MINIO_*`、`TC_*`：对象存储
- `FEISHU_*`、`STI_FEISHU_*`：飞书机器人

注意：不要提交 `.env`、真实密钥、数据库密码和本地导出的 Excel/CSV 数据。

## 本地启动

### 后端

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

后端接口地址：

- API：`http://localhost:8001`
- Swagger：`http://localhost:8001/docs`
- OpenAPI：`http://localhost:8001/openapi.json`

如果你希望使用 `8000` 端口，也可以这样启动：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

同时需要让前端代理指向 `8000`：

```bash
cd frontend
$env:VITE_API_TARGET="http://127.0.0.1:8000"
npm run dev
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

默认访问：

- 前端：`http://localhost:3000`
- 默认代理后端：`http://127.0.0.1:8001`

### 常用开发命令

```bash
# 前端生产构建
cd frontend
npm run build

# 前端 lint
cd frontend
npm run lint

# Python 语法检查示例
python -m py_compile main.py
python -m py_compile LSTA/service/listingOptimizeRecordService.py
```

## Docker 部署

```bash
docker compose up -d --build
```

服务说明：

- `app`：FastAPI 后端，容器内监听 `8000`
- `nginx`：前端静态资源与反向代理，对外暴露 `80`

部署前请检查：

- `.env` 是否已按服务器环境填写
- `docker-compose.yml` 中挂载路径、共享目录、账号信息是否适配当前环境
- 外部数据库、Redis、Milvus、对象存储是否可从容器访问

## 库存与周度发货计划

库存监控分析页面位于 `/inventory`，核心使用 `ads_lingxing_all_warehouse_new_v1` 作为库存监控底表来源，支持：

- 查询全部并校验
- 一键验证发货量
- 一键验证采购量
- 导入备货规则
- 下载周度发货计划
- 按基准日期、首周发货日、款式、半箱供应商等条件计算

周度发货计划导出会尽量对齐模板表头，并输出发货时间、渠道、整箱/半箱规则、库存核对、待配货量等字段。临时对比文件和导出结果建议放在 `outputs/` 或本地下载目录，不进入 Git。

## Listing 优化记录

Listing 优化页面位于 `/listing`，记录页位于 `/listing-records`，支持：

- 多候选 Listing 文案生成
- 竞品、流量词、Search Terms 辅助
- 采用记录入库
- CTR/CVR/流量前后对比

指标来源依赖广告/销售明细表。若记录页展示 `无对比` 或当前指标为空，优先检查源表最新日期、ASIN/站点匹配和当前日期窗口是否超出可用数据范围。

## SQL 安全与查数

LDA 模块通过 `/lda` 提供自然语言查数能力。页面侧和后端都会做 SQL 安全限制，常见约束包括：

- 禁止危险 DDL/DML
- 限制多语句和高风险关键字
- 大批量查询应优先调整查询顺序、条件下推和中间结果规模

需要全量查询时，不要通过减少业务结果行数来“优化”；优先优化 SQL 的 join 顺序、预聚合、字段裁剪和索引命中。

## 提交前检查

建议提交前至少执行：

```bash
cd frontend
npm run build

cd ..
python -m py_compile main.py
```

如果只改了某个 Python 服务文件，可以额外检查该文件：

```bash
python -m py_compile LSTA/service/listingOptimizeRecordService.py
```

## Git 注意事项

不要提交以下内容：

- `.env`、真实密钥、账号密码
- `venv/`、`node_modules/`、`frontend/dist/`
- Excel/CSV/数据库导出文件
- `out/`、`outputs/`、`tmp_*` 等临时分析产物
- 日志和缓存文件

当前 `.gitignore` 已覆盖大部分临时文件，但新增目录前仍建议先 `git status --short` 检查。

## 参考文档

- [ARCHITECTURE.md](ARCHITECTURE.md)：整体架构说明
- [AUTO_ALARM.md](AUTO_ALARM.md)：自动预警说明
- `LSTA/docs/`：Listing 模块相关文档
