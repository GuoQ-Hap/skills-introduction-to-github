"""leang 子项目常量（可通过环境变量覆盖）"""
import os
import re
from typing import Optional

DEFAULT_COLLECTION = os.getenv("LEANG_MILVUS_COLLECTION", "leang_documents")
# 默认开启 BM25 + sparse（Milvus 2.4+，含 2.6.x）；仅当连接旧版 2.3.x 时设 LEANG_ENABLE_BM25=0
_LEANG_BM25 = os.getenv("LEANG_ENABLE_BM25", "1").strip().lower()
_ENABLE_BM25_OFF = _LEANG_BM25 in ("0", "false", "no", "off")
ENABLE_BM25_HYBRID = not _ENABLE_BM25_OFF
CHUNK_SIZE = int(os.getenv("LEANG_CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("LEANG_CHUNK_OVERLAP", "100"))
# 与 Milvus VARCHAR、embedding 模型维度对齐；文本块最大写入长度
TEXT_FIELD_MAX = 65000


def sanitize_collection_name(value: Optional[str]) -> Optional[str]:
    """
    规范化上传表单里的集合名。
    Swagger/OpenAPI 常把可选字符串示例填成字面量 \"string\"，会导致误建集合名为 string。
    """
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    # 勿把「环境变量名」当集合名（日志里曾出现 default:LEANG_MILVUS_COLLECTION）
    bad = (
        "string",
        "null",
        "none",
        "undefined",
        "leang_milvus_collection",
        "milvus_collection",
    )
    if s.lower() in bad:
        return None
    # Milvus：首字符须为字母或下划线，否则 has_collection 报 code=1100（如误填 "123"）
    if len(s) > 255 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s):
        return None
    return s
