"""SQR 搜索词搜索量按需查询（单条，避免全库扫描）。

用于前端悬停展示：仅对当前词执行聚合 SUM(search_query_count)，
并带进程内 TTL 缓存，减轻超大 sqr_report 表压力。
"""
from __future__ import annotations

import os
import threading
import time
from datetime import date, timedelta
from typing import Any, Dict, Tuple

import pymysql

from LSTA.constants import (
    SQR_DB_CHARSET,
    SQR_DB_HOST,
    SQR_DB_NAME,
    SQR_DB_PASSWORD,
    SQR_DB_PORT,
    SQR_DB_USER,
)
from LSTA.service.base import service_logger

logger = service_logger

_CACHE_TTL_SEC = float(os.environ.get("LSTA_SQR_VOLUME_CACHE_TTL", "1800"))  # 默认 30 分钟
_CACHE_MAX = int(os.environ.get("LSTA_SQR_VOLUME_CACHE_MAX", "5000"))


def _last_month_start() -> date:
    today = date.today()
    first_of_month = today.replace(day=1)
    return (first_of_month - timedelta(days=1)).replace(day=1)


def classify_sqr_volume(total: int) -> Tuple[str, str]:
    """按搜索量分级：A~F（与产品约定区间一致）。"""
    if total >= 300_000:
        return "A", "A：搜索量30W+"
    if total >= 200_000:
        return "B", "B：搜索量20-30W"
    if total >= 100_000:
        return "C", "C：搜索量10-20W"
    if total >= 50_000:
        return "D", "D：搜索量5-10W"
    if total >= 10_000:
        return "E", "E：搜索量1-5W"
    return "F", "F：搜索量＜1W"


class SqrSearchVolumeService:
    """单条搜索词 SQR 搜索量查询 + 分级。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._order: list[str] = []  # LRU 近似：满时删最旧 key

    def _connect(self) -> pymysql.Connection:
        return pymysql.connect(
            host=SQR_DB_HOST,
            port=SQR_DB_PORT,
            user=SQR_DB_USER,
            password=SQR_DB_PASSWORD,
            database=SQR_DB_NAME,
            charset=SQR_DB_CHARSET,
            connect_timeout=10,
            read_timeout=60,
        )

    def _cache_get(self, key: str) -> Dict[str, Any] | None:
        now = time.time()
        with self._lock:
            ent = self._cache.get(key)
            if not ent:
                return None
            ts, payload = ent
            if now - ts > _CACHE_TTL_SEC:
                del self._cache[key]
                try:
                    self._order.remove(key)
                except ValueError:
                    pass
                return None
            return payload

    def _cache_set(self, key: str, payload: Dict[str, Any]) -> None:
        now = time.time()
        with self._lock:
            if key in self._cache:
                try:
                    self._order.remove(key)
                except ValueError:
                    pass
            self._cache[key] = (now, payload)
            self._order.append(key)
            while len(self._order) > _CACHE_MAX:
                old = self._order.pop(0)
                self._cache.pop(old, None)

    def query_one(self, term: str) -> Dict[str, Any]:
        """查询单个词的 SQR 搜索量汇总并分级。

        查询策略：
        - 仅一条等值条件 + 时间下界，便于命中 (search_query, report_date) 等索引；
        - 不做 LIKE / 全表扫描；
        - 结果进程内缓存。
        """
        raw = (term or "").strip()
        if not raw:
            raise ValueError("搜索词不能为空")
        if len(raw) > 500:
            raise ValueError("搜索词过长（最多 500 字符）")

        cache_key = raw.casefold()
        hit = self._cache_get(cache_key)
        if hit is not None:
            return {**hit, "cached": True}

        since = _last_month_start()
        # 主路径：等值匹配（与流量词服务 batch 查询一致）
        sql = (
            "SELECT COALESCE(SUM(search_query_count), 0) AS sqc "
            "FROM sqr_report "
            "WHERE search_query = %s AND report_date >= %s"
        )
        total = 0
        try:
            conn = self._connect()
            try:
                cur = conn.cursor(pymysql.cursors.DictCursor)
                cur.execute(sql, (raw, since))
                row = cur.fetchone()
                total = int(row["sqc"] or 0) if row else 0
                # 若区分大小写导致未命中，再尝试一次大小写不敏感（仍带日期，范围远小于全表）
                if total == 0 and raw != raw.lower():
                    cur.execute(
                        "SELECT COALESCE(SUM(search_query_count), 0) AS sqc "
                        "FROM sqr_report "
                        "WHERE LOWER(search_query) = LOWER(%s) AND report_date >= %s",
                        (raw, since),
                    )
                    row2 = cur.fetchone()
                    total = int(row2["sqc"] or 0) if row2 else 0
            finally:
                conn.close()
        except Exception as e:
            logger.warning("SQR 单条搜索量查询失败 term=%r: %s", raw[:80], e)
            raise RuntimeError(f"SQR 查询失败: {e}") from e

        grade, grade_label = classify_sqr_volume(total)
        payload = {
            "term": raw,
            "total_search_count": total,
            "grade": grade,
            "grade_label": grade_label,
            "since_date": str(since),
            "cached": False,
        }
        self._cache_set(cache_key, payload)
        return payload

    def query_many(self, terms: list[str], *, limit: int = 500) -> dict[str, dict[str, Any]]:
        """对多词做一次分组聚合查询（LOWER 对齐），每请求最多 limit 个不重复词。

        返回 dict：key 为小写搜索词，value 为与 query_one 相同结构的字典（含 term 原文样例）。
        """
        cap = min(limit, 500)
        ordered_pairs: list[tuple[str, str]] = []  # (raw, casefold)
        seen_cf: set[str] = set()
        for t in terms:
            raw = (t or "").strip()
            if not raw or len(raw) > 500:
                continue
            cf = raw.casefold()
            if cf in seen_cf:
                continue
            seen_cf.add(cf)
            ordered_pairs.append((raw, cf))
            if len(ordered_pairs) >= cap:
                break

        since = _last_month_start()
        since_s = str(since)
        out: dict[str, dict[str, Any]] = {}

        need_sql: list[tuple[str, str]] = []
        for raw, cf in ordered_pairs:
            hit = self._cache_get(cf)
            if hit is not None:
                pl = {**hit, "cached": True, "term": hit.get("term") or raw, "since_date": since_s}
                out[cf] = pl
            else:
                need_sql.append((raw, cf))

        if not need_sql:
            return out

        uniq_lower = list({cf for _, cf in need_sql})
        placeholders = ",".join(["%s"] * len(uniq_lower))
        sql = (
            f"SELECT LOWER(TRIM(search_query)) AS sqk, COALESCE(SUM(search_query_count), 0) AS sqc "
            f"FROM sqr_report WHERE report_date >= %s AND LOWER(TRIM(search_query)) IN ({placeholders}) "
            f"GROUP BY LOWER(TRIM(search_query))"
        )
        agg: dict[str, int] = {}
        try:
            conn = self._connect()
            try:
                cur = conn.cursor(pymysql.cursors.DictCursor)
                cur.execute(sql, [since, *uniq_lower])
                for row in cur.fetchall():
                    k = (row.get("sqk") or "").strip().lower()
                    if k:
                        agg[k] = int(row.get("sqc") or 0)
            finally:
                conn.close()
        except Exception as e:
            logger.warning("SQR 批量搜索量查询失败: %s", e)
            raise RuntimeError(f"SQR 批量查询失败: {e}") from e

        for raw, cf in need_sql:
            total = int(agg.get(cf, 0))
            grade, grade_label = classify_sqr_volume(total)
            payload = {
                "term": raw,
                "total_search_count": total,
                "grade": grade,
                "grade_label": grade_label,
                "since_date": since_s,
                "cached": False,
            }
            self._cache_set(cf, payload)
            out[cf] = payload

        return out


sqr_search_volume_service = SqrSearchVolumeService()
