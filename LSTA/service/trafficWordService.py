"""流量词判定服务：查询 ABA / SQR 报告数据库判断关键词是否为流量词。

流量词定义：在 aba_report 表（按 start_date 筛选上月至今）或
sqr_report 表（按 report_date 筛选上月至今）中存在记录的搜索词。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pymysql

from LSTA.constants import (
    ABA_DB_CHARSET,
    ABA_DB_HOST,
    ABA_DB_NAME,
    ABA_DB_PASSWORD,
    ABA_DB_PORT,
    ABA_DB_USER,
    SQR_DB_CHARSET,
    SQR_DB_HOST,
    SQR_DB_NAME,
    SQR_DB_PASSWORD,
    SQR_DB_PORT,
    SQR_DB_USER,
)
from LSTA.service.base import service_logger

logger = service_logger


def _last_month_start() -> date:
    today = date.today()
    first_of_month = today.replace(day=1)
    return (first_of_month - timedelta(days=1)).replace(day=1)


class TrafficWordService:
    """批量查询关键词在 ABA / SQR 报告中的流量数据。"""

    def _aba_connect(self) -> pymysql.Connection:
        return pymysql.connect(
            host=ABA_DB_HOST, port=ABA_DB_PORT,
            user=ABA_DB_USER, password=ABA_DB_PASSWORD,
            database=ABA_DB_NAME, charset=ABA_DB_CHARSET,
            connect_timeout=10, read_timeout=120,
        )

    def _sqr_connect(self) -> pymysql.Connection:
        return pymysql.connect(
            host=SQR_DB_HOST, port=SQR_DB_PORT,
            user=SQR_DB_USER, password=SQR_DB_PASSWORD,
            database=SQR_DB_NAME, charset=SQR_DB_CHARSET,
            connect_timeout=10, read_timeout=60,
        )

    def _query_aba(self, words: List[str]) -> Dict[str, Dict[str, Any]]:
        """查询 ABA 报告：返回 {word: {search_rank, start_date, ...}}"""
        if not words:
            return {}
        result: Dict[str, Dict[str, Any]] = {}
        since = _last_month_start()
        try:
            conn = self._aba_connect()
            try:
                cur = conn.cursor(pymysql.cursors.DictCursor)
                placeholders = ",".join(["%s"] * len(words))
                sql = (
                    f"SELECT search_term, MIN(search_rank) AS best_rank, "
                    f"MAX(start_date) AS latest_date, COUNT(*) AS record_count "
                    f"FROM aba_report "
                    f"WHERE search_term IN ({placeholders}) "
                    f"AND start_date >= %s "
                    f"GROUP BY search_term"
                )
                cur.execute(sql, [*words, since])
                for row in cur.fetchall():
                    term = row["search_term"]
                    result[term.lower()] = {
                        "search_rank": row["best_rank"],
                        "latest_date": str(row["latest_date"]) if row["latest_date"] else None,
                        "record_count": row["record_count"],
                        "source": "aba",
                    }
            finally:
                conn.close()
        except Exception as e:
            logger.warning("ABA 数据库查询失败: %s", e)
        return result

    def _query_sqr(self, words: List[str]) -> Dict[str, Dict[str, Any]]:
        """查询 SQR 报告：返回 {word: {search_query_count, report_date, ...}}"""
        if not words:
            return {}
        result: Dict[str, Dict[str, Any]] = {}
        since = _last_month_start()
        try:
            conn = self._sqr_connect()
            try:
                cur = conn.cursor(pymysql.cursors.DictCursor)
                placeholders = ",".join(["%s"] * len(words))
                sql = (
                    f"SELECT search_query, SUM(search_query_count) AS sqc, "
                    f"MAX(report_date) AS latest_date, COUNT(*) AS record_count "
                    f"FROM sqr_report "
                    f"WHERE search_query IN ({placeholders}) "
                    f"AND report_date >= %s "
                    f"GROUP BY search_query"
                )
                cur.execute(sql, [*words, since])
                for row in cur.fetchall():
                    term = row["search_query"]
                    result[term.lower()] = {
                        "search_query_count": int(row["sqc"] or 0),
                        "latest_date": str(row["latest_date"]) if row["latest_date"] else None,
                        "record_count": row["record_count"],
                        "source": "sqr",
                    }
            finally:
                conn.close()
        except Exception as e:
            logger.warning("SQR 数据库查询失败: %s", e)
        return result

    @staticmethod
    def extract_words_from_listing(
        title: str, bullet_points: List[str], description: str, search_terms: str,
    ) -> List[str]:
        """从 Listing 各板块提取有意义的英文词组和单词。"""
        all_text = " ".join([
            title,
            " ".join(bullet_points),
            description,
            search_terms,
        ])
        tokens = re.findall(r"[a-zA-Z][a-zA-Z'-]*[a-zA-Z]|[a-zA-Z]", all_text)
        stopwords = {
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "can", "shall", "it", "its",
            "this", "that", "these", "those", "not", "no", "nor", "as", "if",
            "than", "so", "up", "out", "about", "into", "over", "after", "your",
            "our", "we", "you", "they", "them", "their", "my", "me", "he", "she",
            "his", "her", "all", "each", "every", "both", "few", "more", "most",
            "other", "some", "such", "only", "own", "same", "also", "just", "any",
        }
        unique: dict[str, str] = {}
        for t in tokens:
            low = t.lower()
            if low not in stopwords and len(low) >= 2:
                if low not in unique:
                    unique[low] = t
        return list(unique.values())

    @staticmethod
    def extract_phrases_from_listing(
        title: str, bullet_points: List[str], description: str, search_terms: str,
    ) -> List[str]:
        """提取 2~4 词组成的短语用于流量词匹配。"""
        all_text = " ".join([title, " ".join(bullet_points), description, search_terms])
        tokens = re.findall(r"[a-zA-Z][a-zA-Z'-]*[a-zA-Z]|[a-zA-Z]", all_text)
        phrases: dict[str, str] = {}
        for n in (2, 3, 4):
            for i in range(len(tokens) - n + 1):
                phrase = " ".join(tokens[i:i + n])
                low = phrase.lower()
                if low not in phrases:
                    phrases[low] = phrase
        return list(phrases.values())

    def check_words(
        self,
        words: List[str],
        include_phrases: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """批量检查词汇是否为流量词。

        返回 {word_lower: {is_traffic: bool, aba: {...}, sqr: {...}}}
        """
        all_terms = [w.lower() for w in words]
        unique_terms = list(set(all_terms))

        aba_data = self._query_aba(unique_terms)
        sqr_data = self._query_sqr(unique_terms)

        result: Dict[str, Dict[str, Any]] = {}
        for term in unique_terms:
            low = term.lower()
            aba_info = aba_data.get(low)
            sqr_info = sqr_data.get(low)
            is_traffic = bool(aba_info or sqr_info)
            result[low] = {
                "is_traffic": is_traffic,
                "aba": aba_info,
                "sqr": sqr_info,
            }
        return result

    def batch_check_listing(
        self,
        title: str,
        bullet_points: List[str],
        description: str,
        search_terms: str,
        target_keywords: List[str],
    ) -> Dict[str, Any]:
        """对整个 Listing 进行流量词分析。

        策略：SQR 表较小（50 万行）优先全量查询；
        ABA 表极大（2000 万行、无索引）仅查询目标关键词和 SQR 命中词。

        返回:
        - traffic_words: 被识别为流量词的列表
        - keyword_words: 用户指定的目标关键词
        - total_words_checked: 总检查词数
        """
        single_words = self.extract_words_from_listing(
            title, bullet_points, description, search_terms,
        )
        phrases = self.extract_phrases_from_listing(
            title, bullet_points, description, search_terms,
        )
        all_candidates = list(set(
            [w.lower() for w in single_words] + [p.lower() for p in phrases]
        ))

        SQR_BATCH = 200
        sqr_all: Dict[str, Dict[str, Any]] = {}
        for i in range(0, len(all_candidates), SQR_BATCH):
            batch = all_candidates[i:i + SQR_BATCH]
            sqr_all.update(self._query_sqr(batch))

        sqr_hits = set(sqr_all.keys())
        kw_lower = {kw.lower() for kw in target_keywords}
        aba_candidates = list(sqr_hits | kw_lower | set(all_candidates[:30]))

        ABA_BATCH = 20
        aba_all: Dict[str, Dict[str, Any]] = {}
        for i in range(0, len(aba_candidates), ABA_BATCH):
            batch = aba_candidates[i:i + ABA_BATCH]
            aba_all.update(self._query_aba(batch))

        traffic_words = []
        for word in all_candidates:
            low = word.lower()
            aba_info = aba_all.get(low)
            sqr_info = sqr_all.get(low)
            if aba_info or sqr_info:
                traffic_words.append({
                    "word": low,
                    "aba": aba_info,
                    "sqr": sqr_info,
                })

        traffic_words.sort(
            key=lambda x: (
                x.get("aba", {}).get("search_rank", 999999) if x.get("aba") else 999999,
                -(x.get("sqr", {}).get("search_query_count", 0) if x.get("sqr") else 0),
            )
        )

        return {
            "traffic_words": traffic_words,
            "keyword_words": list(kw_lower),
            "total_words_checked": len(all_candidates),
            "traffic_word_count": len(traffic_words),
        }


traffic_word_service = TrafficWordService()
