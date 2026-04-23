"""NLP 分词与关键字匹配服务（jieba + schema 索引）。

整合原 nlp_to_sql.py 中的 NLPtoSQL 分析逻辑。
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

import jieba

from LDA.service.base import service_logger
from LDA.service.schemaService import schema_service

logger = service_logger

# ===================== 意图模式 =====================
INTENT_PATTERNS = {
    "aggregate_sum": {
        "keywords": ["总", "合计", "总计", "汇总", "总共", "一共", "总额", "总量", "累计"],
        "sql_func": "SUM",
    },
    "aggregate_count": {
        "keywords": ["多少", "几个", "数量", "个数", "条数", "几条", "统计数", "计数"],
        "sql_func": "COUNT",
    },
    "aggregate_avg": {
        "keywords": ["平均", "均值", "平均值", "均价"],
        "sql_func": "AVG",
    },
    "aggregate_max": {
        "keywords": ["最大", "最高", "最多", "最贵", "峰值"],
        "sql_func": "MAX",
    },
    "aggregate_min": {
        "keywords": ["最小", "最低", "最少", "最便宜", "最低值"],
        "sql_func": "MIN",
    },
    "list": {
        "keywords": ["列出", "查看", "显示", "展示", "查询", "哪些", "列表", "看看", "有哪些"],
        "sql_func": None,
    },
    "group": {
        "keywords": ["按", "分别", "各个", "每个", "每月", "每天", "每周", "各", "分组", "分类统计"],
        "sql_func": "GROUP BY",
    },
    "sort_desc": {
        "keywords": ["排名", "排行", "前", "TOP", "top", "最高", "降序"],
        "sql_func": "ORDER BY DESC",
    },
    "sort_asc": {
        "keywords": ["最低", "最少", "升序", "从低到高"],
        "sql_func": "ORDER BY ASC",
    },
    "filter_time": {
        "keywords": ["今年", "去年", "上个月", "这个月", "本月", "本周", "最近", "近"],
        "sql_func": "WHERE",
    },
}

TIME_PATTERNS = {
    "今年": "YEAR(CURDATE())",
    "去年": "YEAR(CURDATE()) - 1",
    "本月": ("YEAR(CURDATE())", "MONTH(CURDATE())"),
    "上个月": ("YEAR(CURDATE())", "MONTH(CURDATE()) - 1"),
    "最近7天": "DATE_SUB(CURDATE(), INTERVAL 7 DAY)",
    "最近30天": "DATE_SUB(CURDATE(), INTERVAL 30 DAY)",
    "最近一周": "DATE_SUB(CURDATE(), INTERVAL 7 DAY)",
    "最近一个月": "DATE_SUB(CURDATE(), INTERVAL 30 DAY)",
    "最近三个月": "DATE_SUB(CURDATE(), INTERVAL 90 DAY)",
}

GROUP_DIMENSION_MAP = {
    "店铺": ["store", "store_name"],
    "品类": ["category", "category_level1", "category_level2"],
    "品牌": ["brand"],
    "国家": ["country", "country_code"],
    "站点": ["market", "marketplace_id"],
    "平台": ["platform"],
    "月": ["month", "year_month"],
    "月份": ["month", "year_month"],
    "年": ["year"],
    "周": ["week"],
    "天": ["date", "day", "data_dt", "dt"],
    "日期": ["date", "day", "data_dt", "dt"],
    "销售": ["sales_person", "salesman"],
    "销售人员": ["sales_person", "salesman"],
    "部门": ["department"],
    "组长": ["team_leader"],
    "SKU": ["sku"], "MSKU": ["msku"], "ASIN": ["asin"], "SPU": ["spu"],
}


class NLPService:
    """NLP 分析服务：分词 → 意图识别 → 关键字匹配表/字段。"""

    def __init__(self):
        self._jieba_inited = False

    def _ensure_jieba(self):
        if self._jieba_inited:
            return
        custom_words = [
            "销售额", "销量", "利润", "毛利", "退货率", "转化率",
            "库存", "安全库存", "FBA", "海外仓", "本地仓",
            "广告花费", "广告销售额", "ACoS", "点击率",
            "采购", "补货", "发货", "头程", "尾程",
            "店铺", "品类", "品牌", "国家", "站点",
            "目标", "完成率", "评论", "评分",
            "订单", "退款", "退货", "物流",
            "MSKU", "SKU", "ASIN", "FNSKU", "SPU",
            "最近30天", "最近7天", "本月", "上个月", "今年", "去年",
        ]
        for w in custom_words:
            jieba.add_word(w)
        for kw in schema_service.keyword_index:
            if len(kw) >= 2:
                jieba.add_word(kw)
        self._jieba_inited = True

    def analyze_query(self, user_query: str) -> Dict[str, Any]:
        self._ensure_jieba()
        words = [w.strip() for w in jieba.cut(user_query) if w.strip()]
        return {
            "original_query": user_query,
            "tokens": words,
            "intents": self._detect_intents(user_query),
            "matched_tables": self._match_tables(user_query, words),
            "group_dimensions": self._detect_group_dimensions(user_query),
            "time_filter": self._detect_time_filter(user_query),
            "limit": self._detect_limit(user_query),
        }

    @staticmethod
    def _detect_intents(query: str) -> List[str]:
        intents = set()
        for name, info in INTENT_PATTERNS.items():
            if any(kw in query for kw in info["keywords"]):
                intents.add(name)
        return list(intents)

    def _match_tables(self, query: str, words: List[str]) -> List[Dict[str, Any]]:
        table_scores: Dict[str, float] = defaultdict(float)
        kw_index = schema_service.keyword_index
        tables = schema_service.tables

        for word in words:
            if word in kw_index:
                for t in kw_index[word]:
                    table_scores[t] += 2.0
            for kw, ts in kw_index.items():
                if len(kw) >= 2 and (word in kw or kw in word):
                    for t in ts:
                        table_scores[t] += 1.0

        layer_boost = {"ads_": 2.0, "dws_": 1.8, "dim_": 1.3, "dwd_": 1.2}
        for t in table_scores:
            for prefix, factor in layer_boost.items():
                if t.startswith(prefix):
                    table_scores[t] *= factor
                    break
            if t.startswith("temp_") or t.startswith("tmp_"):
                table_scores[t] *= 0.3

        sorted_tables = sorted(table_scores.items(), key=lambda x: -x[1])
        result = []
        for table_name, score in sorted_tables[:10]:
            info = tables[table_name]
            matched_cols = self._match_columns(info["columns"], query, words)
            result.append({
                "table": table_name,
                "score": round(score, 2),
                "description": info["description_cn"],
                "layer": info["layer"],
                "matched_columns": matched_cols,
            })
        return result

    @staticmethod
    def _match_columns(columns: List[Dict], query: str, words: List[str]) -> List[Dict[str, Any]]:
        matched = []
        for col in columns:
            desc = col["description_cn"]
            name_lower = col["name"].lower()
            score = 0
            for w in words:
                if w in desc:
                    score += 2
                if w.lower() in name_lower:
                    score += 1.5
            if score > 0:
                matched.append({
                    "name": col["name"],
                    "type": col["type"],
                    "description": desc,
                    "score": score,
                })
        matched.sort(key=lambda x: -x["score"])
        return matched[:15]

    @staticmethod
    def _detect_group_dimensions(query: str) -> List[Dict[str, Any]]:
        return [
            {"dimension_cn": dim_cn, "possible_columns": cols}
            for dim_cn, cols in GROUP_DIMENSION_MAP.items()
            if dim_cn in query
        ]

    @staticmethod
    def _detect_time_filter(query: str) -> Optional[Dict[str, Any]]:
        for pattern, expr in TIME_PATTERNS.items():
            if pattern in query:
                return {"pattern": pattern, "sql_expr": expr}
        year_m = re.search(r'(\d{4})年', query)
        if year_m:
            return {"pattern": f"{year_m.group(1)}年", "sql_expr": year_m.group(1)}
        month_m = re.search(r'(\d{1,2})月', query)
        if month_m:
            return {"pattern": f"{month_m.group(1)}月", "sql_expr": month_m.group(1)}
        return None

    @staticmethod
    def _detect_limit(query: str) -> Optional[int]:
        m = re.search(r'(?:前|top|TOP)\s*(\d+)', query)
        return int(m.group(1)) if m else None


nlp_service = NLPService()
