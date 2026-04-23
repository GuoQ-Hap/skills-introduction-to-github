"""后台管理系统 - 服务层

提供仪表盘、配置管理、日志管理、模型管理、数据库管理等核心功能。
"""
from __future__ import annotations

import logging
import os
import platform
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from Base.Config.setting import Settings, get_settings, settings
from Base.RicUtils.pathUtils import find_project_root

logger = logging.getLogger(__name__)

PROJECT_ROOT = find_project_root()
LOG_DIR = PROJECT_ROOT / "logs"
ENV_PATH = PROJECT_ROOT / ".env"

_start_time = time.time()


# ══════════════════════════════════════════════
# 仪表盘
# ══════════════════════════════════════════════

def get_system_info() -> Dict[str, Any]:
    proc = psutil.Process(os.getpid())
    mem = proc.memory_info()
    total_mem = psutil.virtual_memory()
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "pid": os.getpid(),
        "uptime_seconds": int(time.time() - _start_time),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "cpu_count": psutil.cpu_count(),
        "memory_used_mb": round(mem.rss / 1024 / 1024, 1),
        "memory_percent": round(proc.memory_percent(), 1),
        "total_memory_mb": round(total_mem.total / 1024 / 1024, 0),
        "total_memory_percent": total_mem.percent,
        "disk_usage_percent": psutil.disk_usage("/").percent if os.name != "nt" else psutil.disk_usage("C:\\").percent,
        "thread_count": proc.num_threads(),
        "timestamp": datetime.now().isoformat(),
    }


def check_service_health() -> List[Dict[str, Any]]:
    _urllib3_log = logging.getLogger("urllib3")
    _prev_level = _urllib3_log.level
    _urllib3_log.setLevel(logging.ERROR)
    try:
        results = []
        results.append(_check_mysql())
        results.append(_check_redis())
        results.append(_check_milvus())
        results.append(_check_sti_db())
        results.append(_check_minio())
        return results
    finally:
        _urllib3_log.setLevel(_prev_level)


def _check_mysql() -> Dict[str, Any]:
    try:
        from Base.Client.mysqlClient import MySQLClient
        client = MySQLClient()
        client.connect()
        client.close()
        return {"name": "MySQL", "status": "healthy", "message": f"{settings.mysql.host}:{settings.mysql.port}/{settings.mysql.name}"}
    except Exception as e:
        return {"name": "MySQL", "status": "error", "message": str(e)[:200]}


def _check_redis() -> Dict[str, Any]:
    try:
        import redis
        r = redis.Redis(
            host=settings.redis.host, port=settings.redis.port,
            db=settings.redis.db, password=settings.redis.password, socket_timeout=3,
        )
        r.ping()
        r.close()
        return {"name": "Redis", "status": "healthy", "message": f"{settings.redis.host}:{settings.redis.port}/{settings.redis.db}"}
    except Exception as e:
        return {"name": "Redis", "status": "error", "message": str(e)[:200]}


def _check_milvus() -> Dict[str, Any]:
    try:
        from pymilvus import MilvusClient
        ms = settings.milvus
        if ms.uri:
            uri = ms.uri
        else:
            host = ms.host or "localhost"
            port = ms.port or 19530
            protocol = "https" if ms.secure else "http"
            uri = f"{protocol}://{host}:{port}"
        token = f"{ms.user}:{ms.password}" if ms.user and ms.password else None
        client = MilvusClient(uri=uri, token=token, db_name=ms.database or "default", timeout=5)
        client.list_collections()
        client.close()
        return {"name": "Milvus", "status": "healthy", "message": f"{uri} / {ms.database}"}
    except Exception as e:
        return {"name": "Milvus", "status": "error", "message": str(e)[:200]}


def _check_sti_db() -> Dict[str, Any]:
    try:
        import pymysql
        from LDA.constants import STI_DB_HOST, STI_DB_PORT, STI_DB_USER, STI_DB_PASSWORD, STI_DB_NAME
        conn = pymysql.connect(
            host=STI_DB_HOST, port=STI_DB_PORT, user=STI_DB_USER,
            password=STI_DB_PASSWORD, database=STI_DB_NAME, connect_timeout=5,
        )
        conn.close()
        return {"name": "STI DB (Doris)", "status": "healthy", "message": f"{STI_DB_HOST}:{STI_DB_PORT}/{STI_DB_NAME}"}
    except Exception as e:
        return {"name": "STI DB (Doris)", "status": "error", "message": str(e)[:200]}


def _check_minio() -> Dict[str, Any]:
    try:
        if not settings.minio.endpoint:
            return {"name": "MinIO", "status": "unconfigured", "message": "未配置"}
        import urllib3
        from minio import Minio
        http = urllib3.PoolManager(timeout=3, retries=urllib3.Retry(total=0))
        client = Minio(settings.minio.endpoint, access_key=settings.minio.access_key,
                       secret_key=settings.minio.secret_key, secure=False, http_client=http)
        client.list_buckets()
        return {"name": "MinIO", "status": "healthy", "message": settings.minio.endpoint}
    except Exception as e:
        return {"name": "MinIO", "status": "error", "message": str(e)[:200]}


# ══════════════════════════════════════════════
# 配置管理 — 分类预设体系
# ══════════════════════════════════════════════

def _read_env_value(key: str) -> str:
    """从 .env 文件读取原始值"""
    if not ENV_PATH.exists():
        return os.getenv(key, "")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return os.getenv(key, "")


def get_config_presets() -> List[Dict[str, Any]]:
    """返回分类的配置预设，每条都带有 env_key、label、当前值、类型提示"""
    categories = []

    # ─── AI 模型配置 ───
    categories.append({
        "category": "ai",
        "title": "AI 模型配置",
        "icon": "robot",
        "groups": [
            {
                "group": "DashScope / 通义千问",
                "description": "阿里云 DashScope 通义系列模型配置",
                "items": [
                    {"env_key": "DASHSCOPE_API_KEY", "label": "API Key", "type": "password", "value": _read_env_value("DASHSCOPE_API_KEY")},
                    {"env_key": "QWEN_BASE_URL", "label": "Base URL", "type": "url", "value": _read_env_value("QWEN_BASE_URL"), "placeholder": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
                    {"env_key": "QWEN_DEFAULT_MODEL", "label": "默认模型", "type": "select", "value": _read_env_value("QWEN_DEFAULT_MODEL"),
                     "options": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-long", "qwen2.5-72b-instruct", "qwen2.5-32b-instruct", "qwen2.5-14b-instruct", "qwen2.5-7b-instruct", "qwen3-max", "qwen3-plus", "qvq-max-2025-03-25"]},
                    {"env_key": "QWEN_EMBEDDING_MODEL_NAME", "label": "Embedding 模型", "type": "select", "value": _read_env_value("QWEN_EMBEDDING_MODEL_NAME"),
                     "options": ["text-embedding-v3", "text-embedding-v2", "text-embedding-v1"]},
                    {"env_key": "QWEN_ASR_MODEL_NAME", "label": "ASR 语音识别模型", "type": "text", "value": _read_env_value("QWEN_ASR_MODEL_NAME"), "placeholder": "qwen-audio-turbo"},
                    {"env_key": "QWEN_OCR_MODEL_NAME", "label": "OCR 图像识别模型", "type": "text", "value": _read_env_value("QWEN_OCR_MODEL_NAME"), "placeholder": "qwen-vl-plus"},
                    {"env_key": "DSC_API_URL", "label": "DashScope API URL (旧)", "type": "url", "value": _read_env_value("DSC_API_URL")},
                ],
            },
            {
                "group": "DeepSeek",
                "description": "DeepSeek 系列大模型配置",
                "items": [
                    {"env_key": "DEEPSEEK_API_KEY", "label": "API Key", "type": "password", "value": _read_env_value("DEEPSEEK_API_KEY")},
                    {"env_key": "DEEPSEEK_BASE_URL", "label": "Base URL", "type": "url", "value": _read_env_value("DEEPSEEK_BASE_URL"), "placeholder": "https://api.deepseek.com/v1"},
                    {"env_key": "DEEPSEEK_DEFAULT_MODEL", "label": "默认模型", "type": "select", "value": _read_env_value("DEEPSEEK_DEFAULT_MODEL"),
                     "options": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"]},
                ],
            },
            {
                "group": "STI 主模型",
                "description": "SQL-to-Index 自然语言查数使用的 LLM",
                "items": [
                    {"env_key": "STI_LLM_API_KEY", "label": "API Key", "type": "password", "value": _read_env_value("STI_LLM_API_KEY")},
                    {"env_key": "STI_LLM_BASE_URL", "label": "Base URL", "type": "url", "value": _read_env_value("STI_LLM_BASE_URL")},
                    {"env_key": "STI_LLM_MODEL", "label": "模型名称", "type": "select", "value": _read_env_value("STI_LLM_MODEL"),
                     "options": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "qwen-plus", "qwen-max", "qwen3-max"]},
                ],
            },
            {
                "group": "STI 备用模型",
                "description": "主模型失败时的降级备用",
                "items": [
                    {"env_key": "STI_LLM_FALLBACK_API_KEY", "label": "API Key", "type": "password", "value": _read_env_value("STI_LLM_FALLBACK_API_KEY")},
                    {"env_key": "STI_LLM_FALLBACK_BASE_URL", "label": "Base URL", "type": "url", "value": _read_env_value("STI_LLM_FALLBACK_BASE_URL")},
                    {"env_key": "STI_LLM_FALLBACK_MODEL", "label": "模型名称", "type": "select", "value": _read_env_value("STI_LLM_FALLBACK_MODEL"),
                     "options": ["qwen3-max", "qwen-plus", "qwen-max", "deepseek-chat", "gpt-4o"]},
                ],
            },
            {
                "group": "LLM 通用",
                "description": "LLM 调用通用参数",
                "items": [
                    {"env_key": "LLM_TIMEOUT", "label": "超时时间 (秒)", "type": "number", "value": _read_env_value("LLM_TIMEOUT"), "placeholder": "30"},
                ],
            },
        ],
    })

    # ─── 数据库配置 ───
    categories.append({
        "category": "database",
        "title": "数据库配置",
        "icon": "database",
        "groups": [
            {
                "group": "MySQL 主库",
                "description": "应用主数据库连接",
                "items": [
                    {"env_key": "DB_HOST", "label": "主机", "type": "text", "value": _read_env_value("DB_HOST"), "placeholder": "localhost"},
                    {"env_key": "DB_PORT", "label": "端口", "type": "number", "value": _read_env_value("DB_PORT"), "placeholder": "3306"},
                    {"env_key": "DB_USER", "label": "用户名", "type": "text", "value": _read_env_value("DB_USER")},
                    {"env_key": "DB_PASSWORD", "label": "密码", "type": "password", "value": _read_env_value("DB_PASSWORD")},
                    {"env_key": "DB_NAME", "label": "数据库名", "type": "text", "value": _read_env_value("DB_NAME")},
                    {"env_key": "DB_CHARSET", "label": "字符集", "type": "text", "value": _read_env_value("DB_CHARSET"), "placeholder": "utf8mb4"},
                ],
            },
            {
                "group": "STI 分析库 (Apache Doris)",
                "description": "SQL-to-Index 数据分析用数据库（MySQL 协议）",
                "items": [
                    {"env_key": "STI_DB_HOST", "label": "主机", "type": "text", "value": _read_env_value("STI_DB_HOST"), "placeholder": "10.0.10.24"},
                    {"env_key": "STI_DB_PORT", "label": "端口", "type": "number", "value": _read_env_value("STI_DB_PORT"), "placeholder": "9030"},
                    {"env_key": "STI_DB_USER", "label": "用户名", "type": "text", "value": _read_env_value("STI_DB_USER")},
                    {"env_key": "STI_DB_PASSWORD", "label": "密码", "type": "password", "value": _read_env_value("STI_DB_PASSWORD")},
                    {"env_key": "STI_DB_NAME", "label": "数据库名", "type": "text", "value": _read_env_value("STI_DB_NAME")},
                    {"env_key": "STI_DB_CHARSET", "label": "字符集", "type": "text", "value": _read_env_value("STI_DB_CHARSET"), "placeholder": "utf8mb4"},
                ],
            },
            {
                "group": "Redis",
                "description": "缓存数据库",
                "items": [
                    {"env_key": "REDIS_HOST", "label": "主机", "type": "text", "value": _read_env_value("REDIS_HOST"), "placeholder": "localhost"},
                    {"env_key": "REDIS_PORT", "label": "端口", "type": "number", "value": _read_env_value("REDIS_PORT"), "placeholder": "6379"},
                    {"env_key": "REDIS_DB", "label": "数据库编号", "type": "number", "value": _read_env_value("REDIS_DB"), "placeholder": "0"},
                    {"env_key": "REDIS_PASSWORD", "label": "密码", "type": "password", "value": _read_env_value("REDIS_PASSWORD")},
                ],
            },
            {
                "group": "Milvus 向量数据库",
                "description": "向量检索服务",
                "items": [
                    {"env_key": "MILVUS_HOST", "label": "主机", "type": "text", "value": _read_env_value("MILVUS_HOST")},
                    {"env_key": "MILVUS_PORT", "label": "端口", "type": "number", "value": _read_env_value("MILVUS_PORT"), "placeholder": "19530"},
                    {"env_key": "MILVUS_URI", "label": "URI (优先于 host:port)", "type": "url", "value": _read_env_value("MILVUS_URI")},
                    {"env_key": "MILVUS_USER", "label": "用户名", "type": "text", "value": _read_env_value("MILVUS_USER")},
                    {"env_key": "MILVUS_PASSWORD", "label": "密码", "type": "password", "value": _read_env_value("MILVUS_PASSWORD")},
                    {"env_key": "MILVUS_DATABASE", "label": "数据库", "type": "text", "value": _read_env_value("MILVUS_DATABASE"), "placeholder": "default"},
                    {"env_key": "MILVUS_COLLECTION_NAME", "label": "默认 Collection", "type": "text", "value": _read_env_value("MILVUS_COLLECTION_NAME")},
                    {"env_key": "MILVUS_VECTOR_DIM", "label": "向量维度", "type": "number", "value": _read_env_value("MILVUS_VECTOR_DIM"), "placeholder": "1024"},
                ],
            },
            {
                "group": "Base Module 库",
                "description": "Base 模块独立数据库",
                "items": [
                    {"env_key": "BASE_DB_NAME", "label": "数据库名", "type": "text", "value": _read_env_value("BASE_DB_NAME")},
                ],
            },
        ],
    })

    # ─── API / 服务配置 ───
    categories.append({
        "category": "api",
        "title": "API / 第三方服务",
        "icon": "api",
        "groups": [
            {
                "group": "飞书机器人 (Leang)",
                "description": "Leang RAG 模块的飞书机器人配置",
                "items": [
                    {"env_key": "FEISHU_APP_ID", "label": "App ID", "type": "text", "value": _read_env_value("FEISHU_APP_ID")},
                    {"env_key": "FEISHU_APP_SECRET", "label": "App Secret", "type": "password", "value": _read_env_value("FEISHU_APP_SECRET")},
                    {"env_key": "FEISHU_COLLECTION_NAME", "label": "Collection 名称", "type": "text", "value": _read_env_value("FEISHU_COLLECTION_NAME")},
                ],
            },
            {
                "group": "飞书机器人 (STI)",
                "description": "SQL-to-Index 模块的飞书机器人配置",
                "items": [
                    {"env_key": "STI_FEISHU_APP_ID", "label": "App ID", "type": "text", "value": _read_env_value("STI_FEISHU_APP_ID")},
                    {"env_key": "STI_FEISHU_APP_SECRET", "label": "App Secret", "type": "password", "value": _read_env_value("STI_FEISHU_APP_SECRET")},
                ],
            },
            {
                "group": "邮箱",
                "description": "邮件发送配置",
                "items": [
                    {"env_key": "SENDER_EMAIL", "label": "发件人邮箱", "type": "text", "value": _read_env_value("SENDER_EMAIL")},
                    {"env_key": "EMAIL_PASSWORD", "label": "邮箱密码/授权码", "type": "password", "value": _read_env_value("EMAIL_PASSWORD")},
                ],
            },
        ],
    })

    # ─── 存储配置 ───
    categories.append({
        "category": "storage",
        "title": "对象存储",
        "icon": "cloud-server",
        "groups": [
            {
                "group": "MinIO",
                "description": "MinIO 对象存储服务",
                "items": [
                    {"env_key": "MINIO_ENDPOINT", "label": "Endpoint", "type": "text", "value": _read_env_value("MINIO_ENDPOINT")},
                    {"env_key": "MINIO_ACCESS_KEY", "label": "Access Key", "type": "text", "value": _read_env_value("MINIO_ACCESS_KEY")},
                    {"env_key": "MINIO_SECRET_KEY", "label": "Secret Key", "type": "password", "value": _read_env_value("MINIO_SECRET_KEY")},
                    {"env_key": "MINIO_ASR_TEXT_BUCKET_NAME", "label": "ASR Bucket", "type": "text", "value": _read_env_value("MINIO_ASR_TEXT_BUCKET_NAME")},
                ],
            },
            {
                "group": "腾讯云 COS",
                "description": "腾讯云对象存储",
                "items": [
                    {"env_key": "TC_SECRET_ID", "label": "Secret ID", "type": "password", "value": _read_env_value("TC_SECRET_ID")},
                    {"env_key": "TC_SECRET_KEY", "label": "Secret Key", "type": "password", "value": _read_env_value("TC_SECRET_KEY")},
                    {"env_key": "TC_REGION", "label": "Region", "type": "text", "value": _read_env_value("TC_REGION"), "placeholder": "ap-guangzhou"},
                    {"env_key": "TC_TOKEN", "label": "Token (可选)", "type": "password", "value": _read_env_value("TC_TOKEN")},
                    {"env_key": "TC_BUCKET_NAME", "label": "Bucket", "type": "text", "value": _read_env_value("TC_BUCKET_NAME")},
                    {"env_key": "TC_PROXY_HTTP_IP", "label": "HTTP 代理", "type": "text", "value": _read_env_value("TC_PROXY_HTTP_IP")},
                    {"env_key": "TC_PROXY_HTTPS_IP", "label": "HTTPS 代理", "type": "text", "value": _read_env_value("TC_PROXY_HTTPS_IP")},
                ],
            },
        ],
    })

    # ─── 应用配置 ───
    categories.append({
        "category": "app",
        "title": "应用配置",
        "icon": "setting",
        "groups": [
            {
                "group": "日志",
                "description": "应用日志配置",
                "items": [
                    {"env_key": "LOG_LEVEL", "label": "日志级别", "type": "select", "value": _read_env_value("LOG_LEVEL") or "INFO",
                     "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
                ],
            },
            {
                "group": "Leang RAG 模块",
                "description": "RAG 文档检索与问答参数",
                "items": [
                    {"env_key": "LEANG_MILVUS_COLLECTION", "label": "默认 Collection", "type": "text", "value": _read_env_value("LEANG_MILVUS_COLLECTION"), "placeholder": "leang_documents"},
                    {"env_key": "LEANG_ENABLE_BM25", "label": "启用 BM25 混合检索", "type": "select", "value": _read_env_value("LEANG_ENABLE_BM25") or "1", "options": ["1", "0"]},
                    {"env_key": "LEANG_CHUNK_SIZE", "label": "分块大小", "type": "number", "value": _read_env_value("LEANG_CHUNK_SIZE"), "placeholder": "800"},
                    {"env_key": "LEANG_CHUNK_OVERLAP", "label": "分块重叠", "type": "number", "value": _read_env_value("LEANG_CHUNK_OVERLAP"), "placeholder": "100"},
                ],
            },
            {
                "group": "FFmpeg",
                "description": "音视频处理工具路径",
                "items": [
                    {"env_key": "FFMPEG_PATH", "label": "FFmpeg 路径", "type": "text", "value": _read_env_value("FFMPEG_PATH")},
                ],
            },
            {
                "group": "HTTP",
                "description": "HTTP 请求参数",
                "items": [
                    {"env_key": "HTTP_TIMEOUT", "label": "请求超时 (秒)", "type": "number", "value": _read_env_value("HTTP_TIMEOUT"), "placeholder": "360"},
                ],
            },
        ],
    })

    return categories


def save_config_batch(items: List[Dict[str, str]]) -> Dict[str, Any]:
    """批量保存配置到 .env 文件并重载"""
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")

    content = ENV_PATH.read_text(encoding="utf-8")
    updated = []
    for item in items:
        key, value = item["key"], item["value"]
        if not key:
            continue
        pattern = rf'^{re.escape(key)}\s*=.*$'
        new_line = f'{key}={value}'
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
        else:
            content = content.rstrip() + f'\n{new_line}\n'
        os.environ[key] = value
        updated.append(key)

    ENV_PATH.write_text(content, encoding="utf-8")

    import Base.Config.setting as setting_mod
    setting_mod._settings = None
    setting_mod.settings = setting_mod.get_settings()

    return {"success": True, "updated": updated, "count": len(updated)}


def update_env_variable(key: str, value: str) -> bool:
    result = save_config_batch([{"key": key, "value": value}])
    return result.get("success", False)


# ══════════════════════════════════════════════
# 日志管理
# ══════════════════════════════════════════════

def list_log_files() -> List[Dict[str, Any]]:
    if not LOG_DIR.exists():
        return []
    files = []
    for f in sorted(LOG_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file():
            stat = f.stat()
            files.append({
                "name": f.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return files


def read_log_file(filename: str, lines: int = 500, search: Optional[str] = None, level: Optional[str] = None, offset: int = 0) -> Dict[str, Any]:
    filepath = LOG_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        return {"error": f"日志文件不存在: {filename}", "lines": [], "total": 0}

    all_lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
    filtered = all_lines
    if level:
        level_upper = level.upper()
        filtered = [l for l in filtered if f" {level_upper} " in l or f" - {level_upper} - " in l]
    if search:
        search_lower = search.lower()
        filtered = [l for l in filtered if search_lower in l.lower()]

    total = len(filtered)
    if offset == 0:
        result_lines = filtered[-lines:] if lines < total else filtered
    else:
        end = total - offset
        start = max(0, end - lines)
        result_lines = filtered[start:end] if end > 0 else []

    return {"lines": result_lines, "total": total, "filename": filename}


def tail_log_file(filename: str, n: int = 100) -> List[str]:
    filepath = LOG_DIR / filename
    if not filepath.exists():
        return []
    with open(filepath, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        buf_size = min(size, n * 200)
        f.seek(max(0, size - buf_size))
        data = f.read().decode("utf-8", errors="replace")
    return data.splitlines()[-n:]


def change_log_level(level: str) -> bool:
    level_upper = level.upper()
    numeric = getattr(logging, level_upper, None)
    if numeric is None:
        return False
    logging.getLogger().setLevel(numeric)
    logger.info("日志级别已切换为: %s", level_upper)
    return True


# ══════════════════════════════════════════════
# 模型管理 — 预设大模型列表
# ══════════════════════════════════════════════

MODEL_PRESETS: List[Dict[str, Any]] = [
    # ── 通义千问 ──
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qwen3-max", "type": "chat", "context": 131072, "tags": ["推荐", "思考"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qwen3-plus", "type": "chat", "context": 131072, "tags": ["快速"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qwen-max", "type": "chat", "context": 32768, "tags": ["稳定"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qwen-plus", "type": "chat", "context": 131072, "tags": ["性价比"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qwen-turbo", "type": "chat", "context": 131072, "tags": ["极速", "低成本"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qwen-long", "type": "chat", "context": 1000000, "tags": ["超长文"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qwen2.5-72b-instruct", "type": "chat", "context": 131072, "tags": ["开源"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qwen2.5-32b-instruct", "type": "chat", "context": 131072, "tags": ["开源"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qvq-max-2025-03-25", "type": "vision", "context": 32768, "tags": ["多模态", "视觉"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qwen-vl-plus", "type": "vision", "context": 8192, "tags": ["多模态"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "qwen-vl-max", "type": "vision", "context": 32768, "tags": ["多模态"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "text-embedding-v3", "type": "embedding", "context": 8192, "tags": ["向量化"]},
    {"provider": "dashscope", "provider_name": "通义千问 (DashScope)", "model": "text-embedding-v2", "type": "embedding", "context": 2048, "tags": ["向量化"]},
    # ── DeepSeek ──
    {"provider": "deepseek", "provider_name": "DeepSeek", "model": "deepseek-chat", "type": "chat", "context": 65536, "tags": ["推荐", "强推理"]},
    {"provider": "deepseek", "provider_name": "DeepSeek", "model": "deepseek-coder", "type": "chat", "context": 65536, "tags": ["代码"]},
    {"provider": "deepseek", "provider_name": "DeepSeek", "model": "deepseek-reasoner", "type": "chat", "context": 65536, "tags": ["深度思考"]},
    # ── OpenAI ──
    {"provider": "openai", "provider_name": "OpenAI", "model": "gpt-4o", "type": "chat", "context": 128000, "tags": ["强大", "多模态"]},
    {"provider": "openai", "provider_name": "OpenAI", "model": "gpt-4o-mini", "type": "chat", "context": 128000, "tags": ["快速", "低成本"]},
    {"provider": "openai", "provider_name": "OpenAI", "model": "gpt-4-turbo", "type": "chat", "context": 128000, "tags": ["稳定"]},
    {"provider": "openai", "provider_name": "OpenAI", "model": "gpt-3.5-turbo", "type": "chat", "context": 16384, "tags": ["低成本"]},
    {"provider": "openai", "provider_name": "OpenAI", "model": "o1", "type": "chat", "context": 200000, "tags": ["深度推理"]},
    {"provider": "openai", "provider_name": "OpenAI", "model": "o1-mini", "type": "chat", "context": 128000, "tags": ["推理", "快速"]},
    # ── Anthropic ──
    {"provider": "anthropic", "provider_name": "Anthropic (Claude)", "model": "claude-3-opus-20240229", "type": "chat", "context": 200000, "tags": ["最强"]},
    {"provider": "anthropic", "provider_name": "Anthropic (Claude)", "model": "claude-3-sonnet-20240229", "type": "chat", "context": 200000, "tags": ["均衡"]},
    {"provider": "anthropic", "provider_name": "Anthropic (Claude)", "model": "claude-3-haiku-20240307", "type": "chat", "context": 200000, "tags": ["极速"]},
    {"provider": "anthropic", "provider_name": "Anthropic (Claude)", "model": "claude-3.5-sonnet-20241022", "type": "chat", "context": 200000, "tags": ["推荐"]},
    # ── 智谱 ──
    {"provider": "zhipu", "provider_name": "智谱 AI (GLM)", "model": "glm-4-plus", "type": "chat", "context": 128000, "tags": ["国产"]},
    {"provider": "zhipu", "provider_name": "智谱 AI (GLM)", "model": "glm-4", "type": "chat", "context": 128000, "tags": ["国产"]},
    {"provider": "zhipu", "provider_name": "智谱 AI (GLM)", "model": "glm-4-flash", "type": "chat", "context": 128000, "tags": ["快速", "免费"]},
    # ── 月之暗面 ──
    {"provider": "moonshot", "provider_name": "月之暗面 (Kimi)", "model": "moonshot-v1-128k", "type": "chat", "context": 128000, "tags": ["超长文"]},
    {"provider": "moonshot", "provider_name": "月之暗面 (Kimi)", "model": "moonshot-v1-32k", "type": "chat", "context": 32000, "tags": ["均衡"]},
    {"provider": "moonshot", "provider_name": "月之暗面 (Kimi)", "model": "moonshot-v1-8k", "type": "chat", "context": 8000, "tags": ["快速"]},
]


def get_model_presets() -> List[Dict[str, Any]]:
    return MODEL_PRESETS


def list_models() -> List[Dict[str, Any]]:
    models = []
    models.append({
        "provider": "dashscope", "provider_name": "通义千问 (DashScope)",
        "model": settings.dashscope.default_model or "未配置",
        "base_url": settings.dashscope.base_url or "未配置",
        "configured": bool(settings.dashscope.api_key and settings.dashscope.base_url),
        "capabilities": ["chat", "streaming", "embedding", "ocr", "asr"],
        "extra_models": {
            "embedding": settings.dashscope.embedding_model_name,
            "asr": settings.dashscope.asr_model_name,
            "ocr": settings.dashscope.ocr_model_name,
        },
    })
    models.append({
        "provider": "deepseek", "provider_name": "DeepSeek",
        "model": settings.deepseek.default_model or "未配置",
        "base_url": settings.deepseek.base_url or "未配置",
        "configured": bool(settings.deepseek.api_key and settings.deepseek.base_url),
        "capabilities": ["chat", "streaming"],
        "extra_models": {},
    })
    try:
        from LDA.constants import STI_LLM_MODEL, STI_LLM_BASE_URL, STI_LLM_API_KEY, STI_LLM_FALLBACK_MODEL, STI_LLM_FALLBACK_BASE_URL
        models.append({
            "provider": "sti", "provider_name": "STI 主模型",
            "model": STI_LLM_MODEL, "base_url": STI_LLM_BASE_URL,
            "configured": bool(STI_LLM_API_KEY and STI_LLM_BASE_URL),
            "capabilities": ["nlp-to-sql"], "extra_models": {},
        })
        models.append({
            "provider": "sti_fallback", "provider_name": "STI 备用模型",
            "model": STI_LLM_FALLBACK_MODEL, "base_url": STI_LLM_FALLBACK_BASE_URL,
            "configured": bool(STI_LLM_FALLBACK_BASE_URL),
            "capabilities": ["nlp-to-sql-fallback"], "extra_models": {},
        })
    except Exception:
        pass
    return models


def test_model(provider: str, prompt: str, model: Optional[str] = None, api_key: Optional[str] = None, base_url: Optional[str] = None) -> Dict[str, Any]:
    start = time.time()
    try:
        if provider in ("dashscope", "qwen"):
            from Base.Ai.llms.qwenLlm import QwenLlm
            kwargs = {}
            if model:
                kwargs["model"] = model
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            llm = QwenLlm(**kwargs) if kwargs else QwenLlm()
            result = llm.invoke(prompt)
            elapsed = round(time.time() - start, 2)
            return {"success": True, "response": result, "model": llm.model, "elapsed_seconds": elapsed}

        elif provider in ("deepseek", "openai", "anthropic", "zhipu", "moonshot", "sti", "custom"):
            from openai import OpenAI
            _api_key = api_key or (settings.deepseek.api_key if provider == "deepseek" else None)
            _base_url = base_url or (settings.deepseek.base_url if provider == "deepseek" else None)
            if provider == "sti":
                from LDA.constants import STI_LLM_API_KEY, STI_LLM_BASE_URL, STI_LLM_MODEL
                _api_key = api_key or STI_LLM_API_KEY
                _base_url = base_url or STI_LLM_BASE_URL
                model = model or STI_LLM_MODEL
            if not _api_key or not _base_url:
                return {"success": False, "error": f"请提供 {provider} 的 API Key 和 Base URL"}

            _model = model or (settings.deepseek.default_model if provider == "deepseek" else "gpt-3.5-turbo")
            client = OpenAI(api_key=_api_key, base_url=_base_url)
            resp = client.chat.completions.create(
                model=_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024, timeout=60,
            )
            elapsed = round(time.time() - start, 2)
            content = resp.choices[0].message.content or ""
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return {"success": True, "response": content, "model": _model, "elapsed_seconds": elapsed}

        else:
            return {"success": False, "error": f"未知的 provider: {provider}"}
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        return {"success": False, "error": str(e), "elapsed_seconds": elapsed}


# ══════════════════════════════════════════════
# 数据库管理
# ══════════════════════════════════════════════

def get_db_connections() -> List[Dict[str, Any]]:
    conns = [
        {"name": "主数据库 (MySQL)", "type": "mysql", "host": settings.mysql.host, "port": settings.mysql.port, "database": settings.mysql.name, "user": settings.mysql.user},
    ]
    try:
        from LDA.constants import STI_DB_HOST, STI_DB_PORT, STI_DB_NAME, STI_DB_USER
        conns.append({"name": "STI 分析库 (Doris)", "type": "doris", "host": STI_DB_HOST, "port": STI_DB_PORT, "database": STI_DB_NAME, "user": STI_DB_USER})
    except Exception:
        pass
    conns.append({"name": "Redis", "type": "redis", "host": settings.redis.host, "port": settings.redis.port, "database": str(settings.redis.db), "user": ""})
    conns.append({"name": "Milvus 向量库", "type": "milvus", "host": settings.milvus.host, "port": settings.milvus.port, "database": settings.milvus.database, "user": settings.milvus.user or ""})
    return conns


def execute_admin_sql(sql: str, db_type: str = "mysql") -> Dict[str, Any]:
    try:
        if db_type == "mysql":
            from Base.Client.mysqlClient import MySQLClient
            client = MySQLClient()
            result = client.execute_sync(sql)
            client.close()
            return {"success": True, "data": result or [], "row_count": len(result) if result else 0}
        elif db_type in ("doris", "starrocks"):
            from LDA.service.dbService import db_service
            is_safe, reason = db_service.validate_sql_safety(sql)
            if not is_safe:
                return {"success": False, "error": f"安全检查未通过: {reason}"}
            columns, rows = db_service.execute_sql(sql)
            from LDA.api.sqlApi import _serialize
            serialized = [{k: _serialize(v) for k, v in row.items()} for row in rows]
            return {"success": True, "data": serialized, "columns": columns, "row_count": len(rows)}
        else:
            return {"success": False, "error": f"不支持的数据库类型: {db_type}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_mysql_tables(db_type: str = "mysql") -> List[str]:
    try:
        if db_type == "mysql":
            from Base.Client.mysqlClient import MySQLClient
            client = MySQLClient()
            result = client.execute_sync("SHOW TABLES")
            client.close()
            if result:
                return [list(row.values())[0] for row in result]
        elif db_type in ("doris", "starrocks"):
            from LDA.service.dbService import db_service
            _, rows = db_service.execute_sql("SHOW TABLES")
            return [list(row.values())[0] for row in rows]
    except Exception as e:
        logger.warning("获取表列表失败: %s", e)
    return []


# ══════════════════════════════════════════════
# Milvus
# ══════════════════════════════════════════════

def list_milvus_collections() -> List[Dict[str, Any]]:
    try:
        from pymilvus import connections, utility, Collection
        alias = f"admin_list_{int(time.time())}"
        connections.connect(alias=alias, host=settings.milvus.host, port=settings.milvus.port,
                            user=settings.milvus.user or "", password=settings.milvus.password or "",
                            db_name=settings.milvus.database or "default", timeout=5)
        names = utility.list_collections(using=alias)
        result = []
        for name in names:
            try:
                col = Collection(name, using=alias)
                col.load()
                result.append({"name": name, "num_entities": col.num_entities, "description": col.description or ""})
            except Exception:
                result.append({"name": name, "num_entities": -1, "description": "无法加载"})
        connections.disconnect(alias)
        return result
    except Exception as e:
        return [{"name": "error", "num_entities": -1, "description": str(e)[:200]}]


# ══════════════════════════════════════════════
# 路由
# ══════════════════════════════════════════════

def get_api_routes(app) -> List[Dict[str, str]]:
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            routes.append({"path": route.path, "methods": list(route.methods), "name": route.name or ""})
    return routes
