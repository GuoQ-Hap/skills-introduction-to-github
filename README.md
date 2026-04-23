# RIC-Train — 凌昂 AI 智能服务平台

集 Listing 优化、自然语言查数、RAG 知识问答于一体的跨境电商智能运营平台。

## 模块说明

| 模块 | 目录 | API 前缀 | 功能 |
|------|------|----------|------|
| **LMA** | `LMA/` | `/lma` | RAG 文档检索问答 |
| **LDA** | `LDA/` | `/lda` | 自然语言转 SQL 查数 |
| **LSTA** | `LSTA/` | `/lsta` | Amazon Listing 优化 |
| **Admin** | `admin/` | `/admin` | 后台管理系统 |

## 快速启动

### 1. 后端

```bash
# 安装依赖（首次）
pip install -r requirements.txt

# 启动主服务（端口 8000，包含所有模块）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

也可单独启动子模块：

```bash
# LMA 独立启动（端口 8002）
uvicorn LMA.main:app --host 0.0.0.0 --port 8002 --reload

# LSTA 独立启动（端口 8003）
uvicorn LSTA.main:app --host 0.0.0.0 --port 8003 --reload
```

### 2. 前端

```bash
# 进入前端目录
cd frontend

# 安装依赖（首次）
npm install

# 启动开发服务器（端口 3000，自动代理后端 API）
npm run dev

# 生产构建
npm run build
```

### 3. 同时启动前后端（开发模式）

在两个终端分别执行：

```bash 
# 终端 1 — 后端
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2 — 前端
cd frontend && npm run dev
```

启动后访问：
- 前端界面：http://localhost:3000
- 后端 API：http://localhost:8000
- 后台管理：http://localhost:8000/admin

## 环境配置

复制 `.env.production` 为 `.env` 并填入实际配置：

```bash
cp .env.production .env
```

关键配置项参见 `.env` 文件注释或 `ARCHITECTURE.md` 第 11.4 节。

## Docker 部署

```bash
docker compose up -d --build
```

详细部署说明参见 [ARCHITECTURE.md](ARCHITECTURE.md)。
