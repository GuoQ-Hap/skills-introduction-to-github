"""数据库连接与 SQL 执行服务（Apache Doris 等，MySQL 协议）"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

import pymysql

from LDA.constants import (
    FORBIDDEN_SQL_KEYWORDS,
    STI_DB_CHARSET,
    STI_DB_HOST,
    STI_DB_NAME,
    STI_DB_PASSWORD,
    STI_DB_PORT,
    STI_DB_USER,
)
from LDA.service.base import service_logger

logger = service_logger


class DBService:
    """STI 分析库（Doris/MySQL 协议）：连接管理、SQL 安全校验与执行。"""

    def _connect(self) -> pymysql.Connection:
        return pymysql.connect(
            host=STI_DB_HOST,
            port=STI_DB_PORT,
            user=STI_DB_USER,
            password=STI_DB_PASSWORD,
            database=STI_DB_NAME,
            charset=STI_DB_CHARSET,
        )

    def fetch_tables(self) -> List[str]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def fetch_columns(self, table_name: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SHOW FULL COLUMNS FROM `{table_name}`")
            columns = cursor.fetchall()
            return [
                {
                    "name": col[0],
                    "type": col[1],
                    "collation": col[2],
                    "null": col[3],
                    "key": col[4],
                    "default": col[5],
                    "extra": col[6],
                    "comment": col[8] if len(col) > 8 else "",
                }
                for col in columns
            ]
        finally:
            conn.close()

    @staticmethod
    def validate_sql_safety(sql: str) -> Tuple[bool, str]:
        """校验 SQL 安全性，只允许 SELECT 查询。"""
        cleaned = re.sub(r"--[^\n]*", "", sql)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
        cleaned = cleaned.strip().rstrip(";").strip()

        if not cleaned:
            return False, "SQL 为空"

        first_keyword = cleaned.split()[0].upper() if cleaned.split() else ""
        if first_keyword not in ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH"):
            return False, f"禁止执行 {first_keyword} 语句，仅允许 SELECT/WITH 查询"

        if first_keyword == "WITH":
            body_after_cte = re.sub(r'\bWITH\b.*\bAS\b\s*\(', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
            tokens = body_after_cte.strip().split()
            has_select = any(t.upper() == 'SELECT' for t in tokens)
            if not has_select:
                return False, "WITH 语句必须以 SELECT 结尾"

        upper_sql = cleaned.upper()
        for kw in FORBIDDEN_SQL_KEYWORDS:
            pattern = r'\b' + kw.replace(' ', r'\s+') + r'\b'
            if re.search(pattern, upper_sql):
                if kw == "SET" and first_keyword == "SELECT":
                    continue
                return False, f"检测到禁止关键字: {kw}"

        if "INTO OUTFILE" in upper_sql or "INTO DUMPFILE" in upper_sql:
            return False, "禁止使用 INTO OUTFILE/DUMPFILE 导出数据"

        if ";" in cleaned:
            return False, "禁止多语句执行（检测到分号）"

        return True, "OK"

    def execute_sql(self, sql: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """执行 SQL（强制安全校验），返回 (columns, rows)。"""
        is_safe, reason = self.validate_sql_safety(sql)
        if not is_safe:
            raise PermissionError(f"[Safety Block] {reason}\nSQL: {sql}")

        conn = self._connect()
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            return columns, list(rows)
        finally:
            conn.close()


db_service = DBService()
