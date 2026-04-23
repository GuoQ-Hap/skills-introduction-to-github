"""LLM 驱动的 NLP-to-SQL 核心引擎。

流程：意图识别 → (chat/followup/query) →
  query: 关键字匹配 → LLM 生成 SQL → 执行 → 空结果重试 → LLM 分析结果 → 记忆

模型调用统一走 ModelPoolService.call_llm，主模型失败自动切换备用池。
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from admin.model_pool import model_pool
from LDA.constants import MAX_MEMORY_ROUNDS
from LDA.prompt.sqlPrompt import (
    ANALYSIS_SYSTEM_PROMPT,
    CHAT_SYSTEM_PROMPT,
    COMPANY_PROFILE,
    SQL_SYSTEM_PROMPT,
)
from LDA.service.base import service_logger
from LDA.service.dbService import db_service
from LDA.service.maskService import DataMasker
from LDA.service.nlpService import nlp_service
from LDA.service.schemaService import schema_service

logger = service_logger


class LLMNLPtoSQL:
    """大模型驱动的 NLP-to-SQL 引擎（支持重试 + 对话记忆）。

    所有 LLM 调用通过 model_pool.call_llm 统一管理，
    主模型不可用时自动遍历备用池选取可用模型。
    """

    def __init__(self):
        self.memory: List[Dict[str, Any]] = []
        self._persist_session_id: Optional[str] = None
        self._persist_user_id: Optional[str] = None
        self._query_start: float = 0.0
        self._memory_hydrated: bool = False
        self._preferred_model: Optional[str] = None

    # ==================== 时间上下文 ====================

    @staticmethod
    def _get_time_context() -> Dict[str, str]:
        now = datetime.now()
        last_month = (
            f"{now.year - 1}年12月" if now.month == 1 else f"{now.year}年{now.month - 1}月"
        )
        return {
            "current_time": now.strftime("%Y年%m月%d日 %H:%M:%S（%A）"),
            "this_year": str(now.year),
            "this_month": f"{now.year}年{now.month}月",
            "last_month": last_month,
            "today": now.strftime("%Y-%m-%d"),
        }

    # ==================== 记忆管理 ====================

    def hydrate_from_db(self, session_id: str) -> None:
        """新建引擎时从 llm_memory 恢复近期轮次（与进程内 memory 上限一致）。"""
        if self._memory_hydrated:
            return
        self._memory_hydrated = True
        try:
            from Base.Service.memoryDbService import memory_db

            recent = memory_db.get_recent("sti", session_id, limit=MAX_MEMORY_ROUNDS)
            for r in recent:
                cols = r.get("columns_json")
                if not isinstance(cols, list):
                    cols = []
                row_list = r.get("rows_json")
                if not isinstance(row_list, list):
                    row_list = []
                self.memory.append({
                    "user_query": r.get("user_query") or "",
                    "sql": r.get("sql_text") or "",
                    "row_count": int(r.get("row_count") or 0),
                    "summary": (r.get("assistant_response") or "")[:500],
                    "columns": cols,
                    "rows": row_list[:50],
                })
        except Exception as e:
            logger.warning("STI 从 llm_memory 恢复失败: %s", e)

    def _latency_ms(self) -> int:
        return int((time.time() - self._query_start) * 1000) if self._query_start else 0

    def _persist_sti_memory(
        self,
        user_query: str,
        *,
        intent: str,
        assistant_response: Optional[str],
        sql_text: Optional[str] = None,
        row_count: Optional[int] = None,
        columns: Optional[List[str]] = None,
        rows: Optional[List[Dict]] = None,
        matched_tables: Optional[List[Dict]] = None,
    ) -> None:
        if not self._persist_session_id:
            return
        try:
            from Base.Service.memoryDbService import memory_db

            memory_db.save(
                "sti",
                self._persist_session_id,
                user_query,
                user_id=self._persist_user_id,
                assistant_response=assistant_response,
                intent=intent,
                sql_text=sql_text,
                row_count=row_count,
                columns=columns,
                rows=rows,
                matched_tables=matched_tables,
                latency_ms=self._latency_ms(),
            )
        except Exception as e:
            logger.warning("STI 持久化记忆失败: %s", e)

    def _add_memory(
        self,
        user_query: str,
        sql: str,
        row_count: int,
        summary: str,
        columns: Optional[List[str]] = None,
        rows: Optional[List[Dict]] = None,
        *,
        matched_tables: Optional[List[Dict]] = None,
        intent: str = "query",
    ):
        self.memory.append({
            "user_query": user_query,
            "sql": sql,
            "row_count": row_count,
            "summary": summary[:500],
            "columns": columns or [],
            "rows": (rows or [])[:50],
        })
        if len(self.memory) > MAX_MEMORY_ROUNDS:
            self.memory = self.memory[-MAX_MEMORY_ROUNDS:]
        self._persist_sti_memory(
            user_query,
            intent=intent,
            assistant_response=summary[:2000] if summary else None,
            sql_text=sql or None,
            row_count=row_count,
            columns=columns,
            rows=rows,
            matched_tables=matched_tables,
        )

    def _get_last_result(self) -> Optional[Dict[str, Any]]:
        for m in reversed(self.memory):
            if m["rows"]:
                return m
        return None

    def _build_memory_context(self) -> str:
        if not self.memory:
            return ""
        lines = ["## 历史对话记忆（最近的查询，可用于理解用户上下文）"]
        for i, m in enumerate(self.memory[-5:], 1):
            lines.append(
                f"[第{i}轮] 用户: {m['user_query']}\n"
                f"  SQL: {m['sql'][:200]}\n"
                f"  结果: {m['row_count']} 行\n"
                f"  摘要: {m['summary'][:200]}"
            )
        return "\n".join(lines)

    def clear_memory(self):
        self.memory.clear()

    # ==================== 意图识别 ====================

    def classify_intent(self, user_input: str) -> str:
        cleaned = user_input.strip()
        chat_patterns = [
            r"^(你好|您好|hello|hi|hey|嗨|哈喽)",
            r"^(谢谢|感谢|thanks|thank)",
            r"^(再见|拜拜|bye|退出)",
            r"^(你是谁|你叫什么|介绍一下你自己)",
            r"^(你能做什么|你会什么|有什么功能|怎么用|帮助|help)",
            r"^(好的|嗯嗯|OK|ok|收到|明白了|知道了)$",
            r"^(早上好|下午好|晚上好|早安|晚安)",
            r"^(辛苦了|厉害|牛|不错|棒)",
        ]
        for p in chat_patterns:
            if re.search(p, cleaned, re.IGNORECASE):
                return "chat"

        if self._is_followup(cleaned):
            return "followup"

        if len(cleaned) <= 4 and not any(
            kw in cleaned
            for kw in [
                "销售", "库存", "广告", "利润", "退货", "订单",
                "采购", "物流", "目标", "评论", "店铺", "品类",
                "SKU", "ASIN", "FBA", "仓", "花费", "成本",
            ]
        ):
            return "chat"
        return "query"

    def _is_followup(self, text: str) -> bool:
        if not self.memory:
            return False
        followup_patterns = [
            r"^分析", r"^详细",
            r"^再.{0,2}(分析|看看|说说|解释|详细)",
            r"^(帮我|请).{0,2}(分析|解读|总结|说明)",
            r"^(继续|接着|进一步)",
            r"^(什么意思|怎么理解|怎么看|如何解读)",
            r"^(总结|归纳|概括).{0,2}(一下|下)",
            r"^(为什么|原因|解释一下)",
            r"^(好的|嗯|OK).{0,4}(分析|看|说)",
            r"^这个?(数据|结果|情况)",
        ]
        if len(text) <= 8:
            return any(re.search(p, text) for p in followup_patterns)
        return False

    # ==================== LLM 调用（统一走模型池） ====================

    def _call_llm(self, messages: List[Dict], temperature: float = 0.1) -> str:
        """通过模型池统一调用 LLM，主模型失败自动切换到备用池下一个模型。"""
        return model_pool.call_llm(
            messages=messages,
            temperature=temperature,
            max_tokens=4096,
            timeout=60,
            _log_module="sti",
            preferred_model=self._preferred_model,
        )

    # ==================== 聊天 ====================

    def chat(self, user_input: str) -> str:
        time_ctx = self._get_time_context()
        memory_ctx = self._build_memory_context()
        user_parts = [p for p in [memory_ctx, user_input] if p]
        messages = [
            {"role": "system", "content": CHAT_SYSTEM_PROMPT.format(
                company_profile=COMPANY_PROFILE, current_time=time_ctx["current_time"],
            )},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]
        return self._call_llm(messages, temperature=0.5)

    # ==================== SQL 生成 ====================

    def _build_schema_context(self, matched_tables: List[Dict]) -> str:
        if not matched_tables:
            return "-- 未找到候选表"
        parts = []
        for t in matched_tables[:5]:
            table_name = t["table"]
            info = schema_service.tables[table_name]
            lines = [
                f"-- {info['layer']} | {info['description_cn']}",
                f"CREATE TABLE `{table_name}` (",
            ]
            for col in info["columns"]:
                line = f"  `{col['name']}` {col['type']}"
                if col["description_cn"] and col["description_cn"] != col["name"]:
                    line += f"  -- {col['description_cn']}"
                lines.append(line + ",")
            if lines[-1].endswith(","):
                lines[-1] = lines[-1][:-1]
            lines.append(");")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    @staticmethod
    def _clean_llm_sql(raw: str) -> str:
        sql = raw.strip()
        if sql.startswith("```"):
            sql = re.sub(r"^```(?:sql)?\s*", "", sql)
            sql = re.sub(r"\s*```$", "", sql)
        sql = sql.replace("\u2018", "'").replace("\u2019", "'")  # ' '
        sql = sql.replace("\u201C", '"').replace("\u201D", '"')  # " "
        sql = sql.replace("\uFF07", "'")  # ＇全角单引号
        return sql.strip()

    def generate_sql(
        self, user_query: str, exclude_tables: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict]]:
        analysis = nlp_service.analyze_query(user_query)
        matched = analysis["matched_tables"]

        if exclude_tables:
            excluded = set(exclude_tables)
            filtered = [t for t in matched if t["table"] not in excluded]
            matched = filtered or matched

        schema_ctx = self._build_schema_context(matched)
        memory_ctx = self._build_memory_context()
        time_ctx = self._get_time_context()

        system_parts = [SQL_SYSTEM_PROMPT.format(
            company_profile=COMPANY_PROFILE,
            schema_context=schema_ctx,
            current_time=time_ctx["current_time"],
            this_month=time_ctx["this_month"],
            last_month=time_ctx["last_month"],
        )]
        if memory_ctx:
            system_parts.append(memory_ctx)

        messages = [
            {"role": "system", "content": "\n\n".join(system_parts)},
            {"role": "user", "content": user_query},
        ]
        sql = self._clean_llm_sql(self._call_llm(messages, temperature=0.1))

        is_safe, reason = db_service.validate_sql_safety(sql)
        if not is_safe:
            sql = f"-- Safety Block: {reason}"
        return sql, matched

    # ==================== 结果分析 ====================

    def analyze_results(
        self, user_query: str, sql: str, columns: List[str], rows: List[Dict]
    ) -> str:
        display = rows[:50]

        if not display:
            data_text = "查询结果为空，没有返回任何数据。"
        else:
            masker = DataMasker()
            masked_display = masker.mask_rows(columns, display)

            header = " | ".join(columns)
            sep = " | ".join("---" for _ in columns)
            lines = [header, sep]
            for row in masked_display:
                lines.append(" | ".join(row.get(c, "") for c in columns))
            data_text = (
                f"共 {len(rows)} 行数据（展示前 {len(display)} 行）：\n\n"
                + "\n".join(lines)
            )
            if masker.mask_count:
                logger.info("PII 智能脱敏完成，共处理 %d 个敏感值", masker.mask_count)

        memory_ctx = self._build_memory_context()
        user_parts = []
        if memory_ctx:
            user_parts.append(memory_ctx)
        user_parts.append(
            f"## 用户需求\n{user_query}\n\n"
            f"## 执行的 SQL\n```sql\n{sql}\n```\n\n"
            f"## 查询结果\n{data_text}"
        )
        time_ctx = self._get_time_context()
        messages = [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT.format(
                company_profile=COMPANY_PROFILE, current_time=time_ctx["current_time"],
            )},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]
        return self._call_llm(messages, temperature=0.3)

    # ==================== 执行 ====================

    @staticmethod
    def _execute(sql: str) -> Tuple[List[str], List[Dict], Optional[str]]:
        """执行 SQL，返回 (columns, rows, error)。不做重试、不做 LLM 修复。"""
        try:
            columns, rows = db_service.execute_sql(sql)
            return columns, rows, None
        except Exception as e:
            return [], [], str(e)

    # ==================== 主入口 ====================

    def query(
        self,
        user_input: str,
        *,
        session_id: str,
        user_id: Optional[str] = None,
        preferred_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """完整流程：意图识别 → SQL → 执行（单次，不重试） → 分析 → 记忆"""
        self._persist_session_id = session_id or None
        self._persist_user_id = user_id
        self._preferred_model = preferred_model
        self._query_start = time.time()

        result: Dict[str, Any] = {
            "query": user_input, "sql": None, "matched_tables": [],
            "data": None, "analysis": None, "error": None, "attempts": 0,
        }

        intent = self.classify_intent(user_input)
        logger.info("查询: %s, 意图: %s", user_input[:50], intent)

        # ---- 聊天 ----
        if intent == "chat":
            try:
                result["analysis"] = self.chat(user_input)
                self._persist_sti_memory(
                    user_input,
                    intent="chat",
                    assistant_response=result["analysis"],
                )
            except Exception as e:
                result["error"] = f"Chat failed: {e}"
            return result

        # ---- 跟进 ----
        if intent == "followup":
            last = self._get_last_result()
            if last:
                try:
                    analysis = self.analyze_results(
                        user_input, last["sql"], last["columns"], last["rows"]
                    )
                    result.update(sql=last["sql"], analysis=analysis, data={
                        "columns": last["columns"], "row_count": last["row_count"],
                    })
                    self._add_memory(
                        user_input, last["sql"], last["row_count"],
                        analysis, last["columns"], last["rows"],
                        intent="followup",
                    )
                except Exception as e:
                    result["error"] = f"Analysis failed: {e}"
                return result

        # ---- 生成 SQL ----
        try:
            sql, matched = self.generate_sql(user_input)
        except Exception as e:
            result["error"] = f"LLM 调用失败: {e}"
            return result

        result["sql"] = sql
        result["matched_tables"] = [
            {"table": t["table"], "description": t["description"], "layer": t["layer"]}
            for t in matched[:5]
        ]

        if sql.startswith("--"):
            last = self._get_last_result()
            if last and self.memory:
                try:
                    analysis = self.analyze_results(
                        user_input, last["sql"], last["columns"], last["rows"]
                    )
                    result.update(sql=last["sql"], analysis=analysis, data={
                        "columns": last["columns"], "row_count": last["row_count"],
                    })
                    self._add_memory(
                        user_input, last["sql"], last["row_count"],
                        analysis, last["columns"], last["rows"],
                        intent="followup",
                    )
                    return result
                except Exception:
                    pass
            result["error"] = sql
            return result

        # ---- 执行（单次，不重试不修复） ----
        columns, rows, err = self._execute(sql)
        result["attempts"] = 1
        if err:
            result["error"] = err
            return result

        result["data"] = {"columns": columns, "row_count": len(rows)}

        # ---- 分析 ----
        try:
            analysis = self.analyze_results(user_input, result["sql"], columns, rows)
        except Exception as e:
            result["error"] = f"Analysis failed: {e}"
            return result

        result["analysis"] = analysis
        summary = analysis[:500] if analysis else f"SQL: {sql}, rows: {len(rows)}"
        self._add_memory(
            user_input,
            sql,
            len(rows),
            summary,
            columns,
            rows,
            matched_tables=result.get("matched_tables"),
            intent="query",
        )
        return result
