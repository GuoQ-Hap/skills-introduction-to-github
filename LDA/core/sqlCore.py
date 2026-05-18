from __future__ import annotations

import re
import time
from datetime import date, datetime
from decimal import Decimal
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
from LDA.skills.jsonSchemaReaderSkill import json_schema_reader_skill

logger = service_logger


class LLMNLPtoSQL:

    def __init__(self):
        self.memory: List[Dict[str, Any]] = []
        self._persist_session_id: Optional[str] = None
        self._persist_user_id: Optional[str] = None
        self._query_start: float = 0.0
        self._memory_hydrated: bool = False
        self._preferred_model: Optional[str] = None

    # ==================== 鏃堕棿涓婁笅鏂?====================

    @staticmethod
    def _get_time_context() -> Dict[str, str]:
        now = datetime.now()
        if now.month == 1:
            last_month = f"{now.year - 1}年12月"
        else:
            last_month = f"{now.year}年{now.month - 1}月"
        return {
            "current_time": now.strftime("%Y年%m月%d日 %H:%M:%S（%A）"),
            "this_year": str(now.year),
            "this_month": f"{now.year}年{now.month}月",
            "last_month": last_month,
            "today": now.strftime("%Y-%m-%d"),
        }

    # ==================== 璁板繂绠＄悊 ====================

    def hydrate_from_db(self, session_id: str) -> None:
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
            logger.warning("STI 浠?llm_memory 鎭㈠澶辫触: %s", e)

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
            logger.warning("STI 鎸佷箙鍖栬蹇嗗け璐? %s", e)

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
        lines = ["## 历史对话记忆（最近查询，可用于理解用户上下文）"]
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

    # ==================== 鎰忓浘璇嗗埆 ====================

    def classify_intent(self, user_input: str) -> str:
        cleaned = user_input.strip()
        chat_patterns = [
            r"^(你好|您好|hello|hi|hey|嗨|哈喽)",
            r"^(谢谢|感谢|thanks|thank)",
            r"^(再见|拜拜|bye|退出)",
            r"^(你是谁|你叫什么|介绍一下你自己)",
            r"^(你能做什么|你会什么|有什么功能|怎么用|帮助|help)",
            r"^(好的|嗯|OK|ok|收到|明白了|知道了)$",
            r"^(早上好|下午好|晚上好|早安|晚安)",
            r"^(辛苦了|厉害|不错|棒)",
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
                "SKU", "ASIN", "FBA", "价格", "花费", "成本",
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

    # ==================== LLM 璋冪敤锛堢粺涓€璧版ā鍨嬫睜锛?====================

    def _call_llm(self, messages: List[Dict], temperature: float = 0.1) -> str:
        return model_pool.call_llm(
            messages=messages,
            temperature=temperature,
            max_tokens=4096,
            timeout=60,
            _log_module="sti",
            preferred_model=self._preferred_model,
        )

    # ==================== 鑱婂ぉ ====================

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

    # ==================== SQL 鐢熸垚 ====================

    def _build_schema_context(self, matched_tables: List[Dict]) -> str:
        if not matched_tables:
            return "-- 鏈壘鍒板€欓€夎〃"
        parts = []
        for t in matched_tables[:5]:
            table_name = t["table"]
            profile = json_schema_reader_skill.get_table_profile(table_name, max_columns=120)
            if profile:
                parts.append(json_schema_reader_skill.profile_to_schema_context(profile))
        return "\n\n".join(parts)

    @staticmethod
    def _clean_llm_sql(raw: str) -> str:
        sql = raw.strip()
        if sql.startswith("```"):
            sql = re.sub(r"^```(?:sql)?\s*", "", sql)
            sql = re.sub(r"\s*```$", "", sql)
        sql = sql.replace("\u2018", "'").replace("\u2019", "'")  # ' '
        sql = sql.replace("\u201C", '"').replace("\u201D", '"')  # " "
        sql = sql.replace("\uFF07", "'")  # 锛囧叏瑙掑崟寮曞彿
        return sql.strip()

    def _build_restriction_prompt(self) -> str:
        restrictions = getattr(self, "_data_restrictions", {})
        if not restrictions:
            return ""
        field_names = {
            "store_name": "店铺(store_name)",
            "brand": "品牌(brand)",
            "salesman": "运营(salesman)",
            "category_2": "类目(category_2)",
            "country_code": "国家(country_code)",
            "sales_apartment": "销售部门(sales_apartment)",
        }
        parts = []
        for field, values in restrictions.items():
            if values:
                label = field_names.get(field, field)
                vals = "、".join(f"'{v}'" for v in values)
                parts.append(f"  - {label} 只能查询这些值：{vals}")
        if not parts:
            return ""
        return (
            "\n\n⚠️【强制数据访问限制 - 必须遵守】\n"
            "以下字段的查询结果必须通过 WHERE 条件限定在授权范围内。"
            "无论用户问什么，都必须加上这些过滤条件：\n"
            + "\n".join(parts)
        )

    @staticmethod
    def _apply_data_restrictions_sql(sql: str, restrictions: Optional[Dict[str, List]]) -> str:
        if not restrictions or not sql or not sql.strip():
            return sql
        s = sql.strip()
        if s.startswith("--"):
            return sql

        candidate_clauses: List[tuple[str, str]] = []
        for field, values in restrictions.items():
            if not field or not isinstance(values, (list, tuple)):
                continue
            fname = str(field).strip()
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", fname):
                continue
            esc: List[str] = []
            for v in values:
                if v is None:
                    continue
                t = str(v).strip().replace("'", "''")
                if t:
                    esc.append(t)
            if not esc:
                continue
            in_list = ", ".join(f"'{x.lower()}'" for x in esc)
            column_ref = LLMNLPtoSQL._restriction_column_ref(s, fname)
            clause = f"LOWER(TRIM(CAST({column_ref} AS STRING))) IN ({in_list})"
            candidate_clauses.append((fname.lower(), clause))

        if not candidate_clauses:
            return sql

        where_sql = " AND ".join(clause for _, clause in candidate_clauses)
        injected = LLMNLPtoSQL._inject_restrictions_into_sql(s, where_sql)
        if injected and injected != s:
            ok, reason = db_service.validate_sql_safety(injected)
            if ok:
                return injected
            logger.warning("内层注入数据权限后未通过安全校验，将尝试外层包装: %s", reason)

        clauses: List[str] = []
        available_cols: set[str] = set()
        inner = s.rstrip(";").strip()
        probe_sql = f"SELECT * FROM (\n{inner}\n) AS _sti_probe LIMIT 0"
        ok_probe, _ = db_service.validate_sql_safety(probe_sql)
        if ok_probe:
            try:
                probe_cols, _ = db_service.execute_sql(probe_sql)
                available_cols = {str(c).lower() for c in (probe_cols or [])}
            except Exception as e:
                logger.warning("权限列探测失败，跳过外层权限注入: %s", e)

        for fname, clause in candidate_clauses:
            if fname in available_cols:
                clauses.append(clause)

        if not clauses:
            logger.warning("数据权限无法注入，阻断本次查询。restrictions=%s sql=%s", restrictions, sql[:500])
            return "-- Safety Block: 数据权限过滤无法生效，已阻断本次查询"

        where_sql = " AND ".join(clauses)
        wrapped = f"SELECT * FROM (\n{inner}\n) AS _sti_restr_sub WHERE {where_sql}"
        ok, reason = db_service.validate_sql_safety(wrapped)
        if not ok:
            logger.warning("包装权限 SQL 后未通过安全校验: %s", reason)
            return f"-- Safety Block: 数据权限过滤无法生效: {reason}"
        return wrapped

    @staticmethod
    def _restriction_column_ref(sql: str, field: str) -> str:
        if re.search(r"\bfrom\s+product_30d\s+p\b", sql, flags=re.IGNORECASE):
            return f"p.`{field}`"
        return f"`{field}`"

    @staticmethod
    def _inject_restrictions_into_sql(sql: str, where_sql: str) -> str:
        body = sql.strip().rstrip(";").strip()
        if not body:
            return sql

        lower = body.lower()
        depth = 0
        insert_at = len(body)
        has_top_level_where = False
        where_at: Optional[int] = None
        i = 0
        while i < len(body):
            ch = body[i]
            if ch == "'":
                i += 1
                while i < len(body):
                    if body[i] == "'" and i + 1 < len(body) and body[i + 1] == "'":
                        i += 2
                        continue
                    if body[i] == "'":
                        break
                    i += 1
            elif ch == '"':
                i += 1
                while i < len(body) and body[i] != '"':
                    i += 1
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif depth == 0:
                if re.match(r"\bwhere\b", lower[i:]):
                    has_top_level_where = True
                    if where_at is None:
                        where_at = i
                if re.match(r"\b(group\s+by|having|order\s+by|limit|offset|union)\b", lower[i:]):
                    insert_at = i
                    break
            i += 1

        head = body[:insert_at].rstrip()
        tail = body[insert_at:].lstrip()
        if has_top_level_where and where_at is not None and where_at < insert_at:
            prefix = body[:where_at].rstrip()
            condition = body[where_at + len("where"):insert_at].strip()
            return f"{prefix} WHERE ({condition}) AND {where_sql}" + (f" {tail}" if tail else "")
        connector = " AND " if has_top_level_where else " WHERE "
        return f"{head}{connector}{where_sql}" + (f" {tail}" if tail else "")


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
        restriction_prompt = self._build_restriction_prompt()

        system_parts = [SQL_SYSTEM_PROMPT.format(
            company_profile=COMPANY_PROFILE,
            schema_context=schema_ctx,
            current_time=time_ctx["current_time"],
            this_month=time_ctx["this_month"],
            last_month=time_ctx["last_month"],
        )]
        if restriction_prompt:
            system_parts.append(restriction_prompt)
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

    # ==================== 缁撴灉鍒嗘瀽 ====================

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

    # ==================== 鎵ц ====================

    @staticmethod
    def _execute(sql: str) -> Tuple[List[str], List[Dict], Optional[str]]:
        try:
            columns, rows = db_service.execute_sql(sql)
            return columns, rows, None
        except Exception as e:
            return [], [], str(e)

    @staticmethod
    def _serialize_cell(value: Any) -> Any:
        if value is None or isinstance(value, (int, float, str, bool)):
            return value
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return str(value)

    @classmethod
    def _serialize_rows(cls, rows: List[Dict], *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        selected_rows = rows if limit is None else rows[:limit]
        return [
            {str(k): cls._serialize_cell(v) for k, v in row.items()}
            for row in selected_rows
        ]

    # ==================== 涓诲叆鍙?====================

    def query(
        self,
        user_input: str,
        *,
        session_id: str,
        user_id: Optional[str] = None,
        preferred_model: Optional[str] = None,
        data_restrictions: Optional[Dict[str, List]] = None,
    ) -> Dict[str, Any]:
        # Full query pipeline.
        self._persist_session_id = session_id or None
        self._persist_user_id = user_id
        self._preferred_model = preferred_model
        self._query_start = time.time()
        self._data_restrictions = data_restrictions or {}

        result: Dict[str, Any] = {
            "query": user_input, "sql": None, "matched_tables": [],
            "data": None, "analysis": None, "error": None, "attempts": 0,
        }

        intent = self.classify_intent(user_input)
        logger.info("鏌ヨ: %s, 鎰忓浘: %s", user_input[:50], intent)

        # ---- 鑱婂ぉ ----
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

        # ---- 璺熻繘 ----
        if intent == "followup":
            last = self._get_last_result()
            if last:
                try:
                    analysis = self.analyze_results(
                        user_input, last["sql"], last["columns"], last["rows"]
                    )
                    result.update(sql=last["sql"], analysis=analysis, data={
                        "columns": last["columns"], "row_count": last["row_count"],
                        "rows": self._serialize_rows(last["rows"]),
                    })
                    self._add_memory(
                        user_input, last["sql"], last["row_count"],
                        analysis, last["columns"], last["rows"],
                        intent="followup",
                    )
                except Exception as e:
                    result["error"] = f"Analysis failed: {e}"
                return result

        # ---- 鐢熸垚 SQL ----
        try:
            sql, matched = self.generate_sql(user_input)
        except Exception as e:
            result["error"] = f"LLM 璋冪敤澶辫触: {e}"
            return result

        sql = self._apply_data_restrictions_sql(sql, getattr(self, "_data_restrictions", None))

        result["sql"] = sql
        result["matched_tables"] = [
            {"table": t["table"], "description": t["description"], "layer": t["layer"]}
            for t in matched[:5]
        ]

        if sql.startswith("--"):
            if "数据权限过滤无法生效" in sql:
                result["error"] = sql
                return result
            last = self._get_last_result()
            if last and self.memory:
                try:
                    analysis = self.analyze_results(
                        user_input, last["sql"], last["columns"], last["rows"]
                    )   
                    result.update(sql=last["sql"], analysis=analysis, data={
                        "columns": last["columns"], "row_count": last["row_count"],
                        "rows": self._serialize_rows(last["rows"]),
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

        # ---- 鎵ц锛堝崟娆★紝涓嶉噸璇曚笉淇锛?----
        columns, rows, err = self._execute(sql)
        result["attempts"] = 1
        if err:
            result["error"] = err
            return result

        result["data"] = {
            "columns": columns,
            "rows": self._serialize_rows(rows),
            "row_count": len(rows),
        }

        # ---- 鍒嗘瀽 ----
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

