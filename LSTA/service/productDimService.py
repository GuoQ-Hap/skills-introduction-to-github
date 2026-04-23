"""产品维度查询服务：根据 ASIN 从 leang_product_info 读取产品的结构化维度字段。

主要用于：
- 竞品发现：把产品颜色拼接到 Amazon 搜索关键词，提升召回精度
- Listing 优化：把产品颜色提示给 LLM，确保优化文案正确保留颜色属性

数据库：`dw_leang.leang_product_info`
关心字段：`colour`（英文颜色，如 Pink / Orange）、`color`（中文营销名）、`size`、`pattern`、`style`、`material`
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pymysql

from LDA.constants import (
    STI_DB_CHARSET,
    STI_DB_HOST,
    STI_DB_NAME,
    STI_DB_PASSWORD,
    STI_DB_PORT,
    STI_DB_USER,
)
from LSTA.service.base import service_logger

logger = service_logger


def _connect() -> pymysql.Connection:
    return pymysql.connect(
        host=STI_DB_HOST,
        port=STI_DB_PORT,
        user=STI_DB_USER,
        password=STI_DB_PASSWORD,
        database=STI_DB_NAME,
        charset=STI_DB_CHARSET,
        connect_timeout=5,
        read_timeout=10,
    )


def query_product_dim(asin: str) -> Dict[str, str]:
    """根据 ASIN 查询 leang_product_info 中的维度字段。

    同一个 ASIN 在表里可能有多条记录（不同 MSKU/SKU），取最新一条。
    未找到返回空字典。
    """
    if not asin:
        return {}
    try:
        conn = _connect()
        try:
            cur = conn.cursor(pymysql.cursors.DictCursor)
            cur.execute(
                "SELECT colour, color, size, pattern, style, material "
                "FROM leang_product_info "
                "WHERE asin = %s "
                "ORDER BY date DESC "
                "LIMIT 1",
                (asin,),
            )
            row = cur.fetchone()
            if not row:
                return {}
            # 统一去除 NULL / 空白
            return {
                k: (str(v).strip() if v is not None else "")
                for k, v in row.items()
            }
        finally:
            conn.close()
    except Exception as e:
        logger.warning("productDimService: 查询 ASIN=%s 的 leang_product_info 失败: %s", asin, e)
        return {}


def query_product_color(asin: str) -> str:
    """便捷入口：返回产品的英文颜色（优先 `colour`，空则回退到中文 `color`）。"""
    dims = query_product_dim(asin)
    if not dims:
        return ""
    colour = (dims.get("colour") or "").strip()
    if colour:
        return colour
    return (dims.get("color") or "").strip()
