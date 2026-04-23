"""sql_to_index 常量与环境变量配置"""
import os

# STI 分析库：Apache Doris / StarRocks 等均可用 MySQL 客户端连接，端口常见 9030
STI_DB_HOST = os.getenv("STI_DB_HOST", "10.0.10.24")
STI_DB_PORT = int(os.getenv("STI_DB_PORT", "9030"))
STI_DB_USER = os.getenv("STI_DB_USER", "root")
STI_DB_PASSWORD = os.getenv("STI_DB_PASSWORD", "")
STI_DB_NAME = os.getenv("STI_DB_NAME", "dw_leang")
STI_DB_CHARSET = os.getenv("STI_DB_CHARSET", "utf8mb4")

STI_LLM_API_KEY = os.getenv("STI_LLM_API_KEY", "")
STI_LLM_BASE_URL = os.getenv("STI_LLM_BASE_URL", "")
STI_LLM_MODEL = os.getenv("STI_LLM_MODEL", "gpt-3.5-turbo")

# 多模型列表（MODEL0~MODEL9），共享同一 API Key / Base URL
STI_LLM_MODELS: list[dict] = []
for _i in range(10):
    _m = os.getenv(f"STI_LLM_MODEL{_i}", "")
    if _m:
        STI_LLM_MODELS.append({"index": _i, "model": _m})

STI_LLM_FALLBACK_API_KEY = os.getenv("STI_LLM_FALLBACK_API_KEY", "")
STI_LLM_FALLBACK_BASE_URL = os.getenv("STI_LLM_FALLBACK_BASE_URL", "")
STI_LLM_FALLBACK_MODEL = os.getenv("STI_LLM_FALLBACK_MODEL", "qwen3-max")

STI_FEISHU_APP_ID = os.getenv("STI_FEISHU_APP_ID", "")
STI_FEISHU_APP_SECRET = os.getenv("STI_FEISHU_APP_SECRET", "")

FORBIDDEN_SQL_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "REPLACE", "GRANT", "REVOKE", "RENAME", "LOAD",
    "CALL", "EXECUTE", "EXEC", "KILL", "FLUSH", "PURGE",
    "RESET", "SHUTDOWN", "SET", "INTO OUTFILE", "INTO DUMPFILE",
]

MAX_MEMORY_ROUNDS = 10
SESSION_TTL = 3600 * 2
SESSION_MAX = 200
