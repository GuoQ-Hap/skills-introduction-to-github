"""LSTA 模块常量与环境变量配置"""
import os

# Amazon 站点域名映射
MARKETPLACE_DOMAINS = {
    "US": "www.amazon.com",
    "UK": "www.amazon.co.uk",
    "DE": "www.amazon.de",
    "JP": "www.amazon.co.jp",
    "CA": "www.amazon.ca",
    "FR": "www.amazon.fr",
    "IT": "www.amazon.it",
    "ES": "www.amazon.es",
    "AU": "www.amazon.com.au",
    "MX": "www.amazon.com.mx",
}

# 站点对应语言
MARKETPLACE_LANGUAGES = {
    "US": "en",
    "UK": "en",
    "DE": "de",
    "JP": "ja",
    "CA": "en",
    "FR": "fr",
    "IT": "it",
    "ES": "es",
    "AU": "en",
    "MX": "es",
}

# SP-API 配置（可选，配置后优先使用 SP-API 获取产品数据）
SP_API_REFRESH_TOKEN = os.getenv("SP_API_REFRESH_TOKEN", "")
SP_API_CLIENT_ID = os.getenv("SP_API_CLIENT_ID", "")
SP_API_CLIENT_SECRET = os.getenv("SP_API_CLIENT_SECRET", "")
SP_API_AWS_ACCESS_KEY = os.getenv("SP_API_AWS_ACCESS_KEY", "")
SP_API_AWS_SECRET_KEY = os.getenv("SP_API_AWS_SECRET_KEY", "")

# ── 抓取代理配置（按优先级） ──
# 方式 0: 虚拟机抓取代理（自建，独立 IP 出口）
#   格式: http://虚拟机IP:9100
SCRAPER_PROXY_URL = os.getenv("LAI_SCRAPER_PROXY_URL", "")
# 方式 1: ScraperAPI（推荐，自动处理反爬/IP 轮换/验证码）
#   注册: https://www.scraperapi.com  免费额度 5000 次/月
SCRAPER_API_KEY = os.getenv("LAI_SCRAPER_API_KEY", "")
# 方式 2: 通用 HTTP/HTTPS 代理（如 Bright Data、自建代理池）
#   格式: http://user:pass@host:port 或 http://host:port
HTTP_PROXY = os.getenv("LAI_HTTP_PROXY", "")

# LLM 配置（如果未设置，则复用模型池默认配置）
LAI_LLM_API_KEY = os.getenv("LAI_LLM_API_KEY", "")
LAI_LLM_BASE_URL = os.getenv("LAI_LLM_BASE_URL", "")
LAI_LLM_MODEL = os.getenv("LAI_LLM_MODEL", "")

DEFAULT_MARKETPLACE = os.getenv("LAI_DEFAULT_MARKETPLACE", "US")

# 请求超时（秒）
FETCH_TIMEOUT = int(os.getenv("LAI_FETCH_TIMEOUT", "30"))

# 最大重试次数（每次重试会切换 URL 模式、重建 Session、指数退避）
FETCH_MAX_RETRIES = int(os.getenv("LAI_FETCH_MAX_RETRIES", "3"))

# 会话限制
SESSION_TTL = 3600 * 2
SESSION_MAX = 100

# ── ABA / SQR 报告数据库配置 ──
ABA_DB_HOST = os.getenv("ABA_REPORT_DB_HOST", "10.0.37.124")
ABA_DB_PORT = int(os.getenv("ABA_REPORT_DB_PORT", "3306"))
ABA_DB_USER = os.getenv("ABA_REPORT_DB_USER", "user_ygq")
ABA_DB_PASSWORD = os.getenv("ABA_REPORT_DB_PASSWORD", "123456")
ABA_DB_NAME = os.getenv("ABA_REPORT_DB_NAME", "la_data")
ABA_DB_CHARSET = os.getenv("ABA_REPORT_DB_CHARSET", "utf8mb4")

SQR_DB_HOST = os.getenv("SQR_REPORT_DB_HOST", "10.0.37.124")
SQR_DB_PORT = int(os.getenv("SQR_REPORT_DB_PORT", "3306"))
SQR_DB_USER = os.getenv("SQR_REPORT_DB_USER", "user_ygq")
SQR_DB_PASSWORD = os.getenv("SQR_REPORT_DB_PASSWORD", "123456")
SQR_DB_NAME = os.getenv("SQR_REPORT_DB_NAME", "la_data")
SQR_DB_CHARSET = os.getenv("SQR_REPORT_DB_CHARSET", "utf8mb4")
