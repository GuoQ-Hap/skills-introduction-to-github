"""搜索词相关性推荐服务：根据 ASIN 查询 MSKU 对应的搜索词相关性结果。

流程：
1. 通过 ASIN 查询 leang_product_info 获取 msku + store_name
2. 在共享文件目录中定位对应的 {msku}.xlsx
3. 读取 Excel 中的 search_term 与 relevance 返回
"""
from __future__ import annotations

import os
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import pymysql
from openpyxl import load_workbook

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

SEARCH_TERM_BASE_DIR = os.environ.get(
    "SEARCH_TERM_BASE_DIR",
    os.path.join(
        "\\\\10.0.10.10", "DASharedFiles",
        "MSKU相关性判断", "搜索词相关性", "3_搜索词相关性结果",
    ),
)

RELEVANCE_ORDER = {
    "高相关": 0, "中高相关": 1, "中相关": 2,
    "中低相关": 3, "低相关": 4,
}

EXCLUDED_RELEVANCE = {"不相关"}


_CACHE_TTL = 600  # 10 分钟


class SearchTermRecommendService:
    """根据 ASIN 从共享目录的搜索词相关性 Excel 中提取推荐结果。"""

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]], Dict[str, int]]] = {}

    def _get_cached(self, file_path: str) -> Optional[Tuple[List[Dict[str, Any]], Dict[str, int]]]:
        entry = self._cache.get(file_path)
        if entry and (time.time() - entry[0]) < _CACHE_TTL:
            return entry[1], entry[2]
        if entry:
            del self._cache[file_path]
        return None

    def _set_cache(
        self, file_path: str,
        all_terms: List[Dict[str, Any]], summary: Dict[str, int],
    ) -> None:
        self._cache[file_path] = (time.time(), all_terms, summary)

    # ── DB ───────────────────────────────────

    def _connect(self) -> pymysql.Connection:
        return pymysql.connect(
            host=STI_DB_HOST,
            port=STI_DB_PORT,
            user=STI_DB_USER,
            password=STI_DB_PASSWORD,
            database=STI_DB_NAME,
            charset=STI_DB_CHARSET,
            connect_timeout=10,
            read_timeout=30,
        )

    def query_msku_by_asin(self, asin: str) -> List[Dict[str, str]]:
        """根据 ASIN 查询 leang_product_info，返回所有匹配的 msku + store_name。"""
        conn = self._connect()
        try:
            cur = conn.cursor(pymysql.cursors.DictCursor)
            cur.execute(
                "SELECT DISTINCT msku, store_name "
                "FROM leang_product_info "
                "WHERE asin = %s AND msku IS NOT NULL AND msku != ''",
                (asin,),
            )
            return list(cur.fetchall())
        finally:
            conn.close()

    # ── 文件搜索 ─────────────────────────────

    @staticmethod
    def _normalize_store(name: str) -> str:
        """统一店铺名中的分隔符以便比较（`_` ↔ `-`）。"""
        return name.replace("_", "-").upper()

    def find_msku_file(
        self, msku: str, store_name: str,
    ) -> Optional[str]:
        """在共享目录下递归搜索 {msku}.xlsx，优先返回 store_name 匹配的结果。

        目录结构层级不固定，可能为：
          base / {大类} / {店铺} / {msku}.xlsx          (2级)
          base / {大类} / {子类} / {店铺} / {msku}.xlsx  (3级)
          base / {大类} / {子类} / {子子类} / {店铺} / ... (更深)
        通过 os.walk 递归搜索，用文件的直接父目录作为店铺名进行匹配。
        """
        target_file = f"{msku}.xlsx"
        target_lower = target_file.lower()
        norm_store = self._normalize_store(store_name)
        candidates: List[Tuple[str, bool]] = []

        try:
            for root, _dirs, files in os.walk(SEARCH_TERM_BASE_DIR):
                for f in files:
                    if f.lower() == target_lower:
                        file_path = os.path.join(root, f)
                        parent_dir = os.path.basename(root)
                        is_match = self._normalize_store(parent_dir) == norm_store
                        candidates.append((file_path, is_match))
        except OSError as e:
            logger.warning("遍历共享目录失败: %s", e)
            return None

        if not candidates:
            return None

        matched = [p for p, m in candidates if m]
        return matched[0] if matched else candidates[0][0]

    # ── Excel 读取 ───────────────────────────

    @staticmethod
    def read_search_terms(file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """从 Excel 读取搜索词，按 search_term 去重并保留最高相关性。

        自动排除"不相关"。

        Returns:
            (all_terms_sorted, summary)
        """
        wb = load_workbook(file_path, read_only=True, data_only=True)
        try:
            ws = wb.active
            ws.reset_dimensions()

            header: List[str] = []
            best: Dict[str, Dict[str, Any]] = {}

            for row in ws.iter_rows(values_only=True):
                if not header:
                    header = [
                        str(c).lower() if c else f"col_{i}"
                        for i, c in enumerate(row)
                    ]
                    continue

                row_dict = dict(zip(header, row))
                search_term = (
                    row_dict.get("search_term")
                    or row_dict.get("search term")
                    or row_dict.get("search_item")
                    or row_dict.get("search item")
                )
                if not search_term:
                    continue

                relevance = str(row_dict.get("relevance", ""))
                if relevance in EXCLUDED_RELEVANCE:
                    continue

                term_key = str(search_term).strip().lower()

                cur_order = RELEVANCE_ORDER.get(relevance, 99)
                existing = best.get(term_key)
                if existing:
                    if RELEVANCE_ORDER.get(existing["relevance"], 99) <= cur_order:
                        continue

                best[term_key] = {
                    "search_term": str(search_term).strip(),
                    "relevance": relevance,
                    "total_score": row_dict.get("total_score"),
                    "size_score": row_dict.get("size_score"),
                    "color_score": row_dict.get("color_score"),
                    "pattern_score": row_dict.get("pattern_score"),
                    "style_score": row_dict.get("style_score"),
                }

            summary = dict(Counter(v["relevance"] for v in best.values()))
            results = list(best.values())
            results.sort(
                key=lambda x: (
                    RELEVANCE_ORDER.get(x["relevance"], 99),
                    -(x["total_score"] or 0),
                ),
            )
            return results, summary
        finally:
            wb.close()

    # ── 文件定位（公共逻辑） ─────────────────

    def _locate_file(self, asin: str) -> Dict[str, Any]:
        """根据 ASIN 定位 Excel 文件，返回中间结果（不读取文件内容）。"""
        rows = self.query_msku_by_asin(asin)
        if not rows:
            logger.warning("搜索词推荐: ASIN=%s 未在 leang_product_info 中找到对应 MSKU", asin)
            return {
                "success": False,
                "message": f"未在 leang_product_info 中找到 ASIN={asin} 对应的 MSKU",
                "msku_info": rows,
            }

        logger.info(
            "搜索词推荐: ASIN=%s 找到 %d 个 MSKU: %s",
            asin, len(rows),
            ", ".join(f"{r['msku']}({r['store_name']})" for r in rows),
        )

        matched_file: Optional[str] = None
        matched_row: Optional[Dict[str, str]] = None
        for row in rows:
            fp = self.find_msku_file(row["msku"], row["store_name"])
            if fp:
                matched_file = fp
                matched_row = row
                break

        if not matched_file or not matched_row:
            logger.warning(
                "搜索词推荐: ASIN=%s 找到 %d 个 MSKU 但无匹配文件: %s",
                asin, len(rows), ", ".join(r["msku"] for r in rows),
            )
            return {
                "success": False,
                "message": (
                    f"ASIN={asin} 找到 {len(rows)} 个 MSKU，"
                    "但均未在搜索词相关性结果目录中找到对应文件"
                ),
                "msku_info": rows,
            }

        path_parts = matched_file.replace("\\", "/").split("/")
        dir_store = path_parts[-2] if len(path_parts) >= 2 else ""

        return {
            "success": True,
            "msku_info": rows,
            "matched_file": matched_file,
            "matched_row": matched_row,
            "matched_dir_store": dir_store,
        }

    # ── 主入口 ───────────────────────────────

    def recommend(
        self,
        asin: str,
        relevance_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """根据 ASIN 获取搜索词相关性推荐。

        "不相关"的搜索词会被自动排除。
        通过 relevance_filter 指定单一等级（如 "高相关"）只返回该等级数据，
        减少传输量；为 None 时返回所有非"不相关"的搜索词。

        Args:
            asin: Amazon ASIN
            relevance_filter: 单一相关性等级，如 "高相关"；为 None 返回全部
        """
        loc = self._locate_file(asin)
        if not loc["success"]:
            return {
                "success": False,
                "message": loc["message"],
                "msku_info": loc["msku_info"],
                "matched_file": None,
                "matched_store": None,
                "search_terms": [],
                "summary": {},
            }

        matched_file = loc["matched_file"]
        matched_row = loc["matched_row"]

        logger.info(
            "ASIN=%s 命中文件: %s (msku=%s, store=%s, filter=%s)",
            asin, matched_file, matched_row["msku"],
            matched_row["store_name"], relevance_filter or "全部",
        )

        cached = self._get_cached(matched_file)
        if cached:
            all_terms, summary = cached
            logger.info("ASIN=%s 使用缓存数据 (%d 条)", asin, len(all_terms))
        else:
            try:
                all_terms, summary = self.read_search_terms(matched_file)
            except Exception as e:
                logger.error("读取 Excel 失败 (%s): %s", matched_file, e)
                return {
                    "success": False,
                    "message": f"读取搜索词文件失败: {e}",
                    "msku_info": loc["msku_info"],
                    "matched_file": matched_file,
                    "matched_store": matched_row["store_name"],
                    "search_terms": [],
                    "summary": {},
                }
            self._set_cache(matched_file, all_terms, summary)

        total_relevant = sum(summary.values())

        if relevance_filter:
            search_terms = [t for t in all_terms if t["relevance"] == relevance_filter]
        else:
            search_terms = []

        return {
            "success": True,
            "message": f"找到 {total_relevant} 条相关搜索词（已排除不相关）",
            "msku_info": loc["msku_info"],
            "matched_msku": matched_row["msku"],
            "matched_store": matched_row["store_name"],
            "matched_dir_store": loc["matched_dir_store"],
            "matched_file": matched_file,
            "summary": summary,
            "total_unique": total_relevant,
            "returned_count": len(search_terms),
            "search_terms": search_terms,
        }


search_term_recommend_service = SearchTermRecommendService()
