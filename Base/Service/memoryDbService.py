"""统一 LLM 对话记忆服务 — 持久化到 MySQL (Ai_memory 库)

所有子模块（LMA / LDA）的对话记忆统一存储在 llm_memory 表中，
通过 module + session_id 区分不同来源和会话。

设计原则：
  - 数据库中的记忆**永不自动清除**，只有用户在后台管理手动操作才会删除
  - 内存缓存仅用于当前会话的热读加速，不决定持久化
  - 深度回忆：跨会话、跨模块检索历史记忆，为 LLM 提供更丰富的上下文
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from Base.Client.mysqlClient import MySQLClient

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `llm_memory` (
    `id`                BIGINT AUTO_INCREMENT PRIMARY KEY,
    `module`            VARCHAR(32)   NOT NULL             COMMENT '模块: sti / leang',
    `session_id`        VARCHAR(128)  NOT NULL             COMMENT '会话ID',
    `user_id`           VARCHAR(128)  DEFAULT NULL         COMMENT '用户ID(可选)',
    `user_query`        TEXT          NOT NULL             COMMENT '用户原始问题',
    `assistant_response`TEXT          DEFAULT NULL         COMMENT 'AI回复/分析摘要',
    `intent`            VARCHAR(32)   DEFAULT NULL         COMMENT '意图: query/chat/followup/ask',
    `sql_text`          TEXT          DEFAULT NULL         COMMENT '执行的SQL (STI)',
    `row_count`         INT           DEFAULT NULL         COMMENT '返回行数 (STI)',
    `columns_json`      JSON          DEFAULT NULL         COMMENT '返回列名 (STI)',
    `rows_json`         JSON          DEFAULT NULL         COMMENT '返回数据行 (STI, 最多50行)',
    `matched_tables`    JSON          DEFAULT NULL         COMMENT '匹配的表 (STI)',
    `sources_json`      JSON          DEFAULT NULL         COMMENT '检索来源 (Leang)',
    `collection_name`   VARCHAR(128)  DEFAULT NULL         COMMENT 'Milvus集合 (Leang)',
    `extra`             JSON          DEFAULT NULL         COMMENT '扩展字段',
    `latency_ms`        INT           DEFAULT NULL         COMMENT '响应耗时(毫秒)',
    `user_liked`        TINYINT(1)    DEFAULT 0            COMMENT '用户觉得赞（1=赞）',
    `user_disliked`     TINYINT(1)    DEFAULT 0            COMMENT '用户觉得差（1=差）',
    `user_comment`      TEXT          DEFAULT NULL         COMMENT '用户评论/反馈意见',
    `created_at`        DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_mod_sess`   (`module`, `session_id`),
    INDEX `idx_sess_time`  (`session_id`, `created_at`),
    INDEX `idx_mod_time`   (`module`, `created_at`),
    FULLTEXT INDEX `ft_query_resp` (`user_query`, `assistant_response`) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM 对话记忆统一存储（永久保留）';
"""

# 老库自动补列（向后兼容已存在的表）
_FEEDBACK_COLUMNS = [
    ("user_liked",    "TINYINT(1) DEFAULT 0    COMMENT '用户觉得赞（1=赞）'"),
    ("user_disliked", "TINYINT(1) DEFAULT 0    COMMENT '用户觉得差（1=差）'"),
    ("user_comment",  "TEXT       DEFAULT NULL COMMENT '用户评论/反馈意见'"),
]

_table_ensured = False


def _ensure_table():
    global _table_ensured
    if _table_ensured:
        return
    try:
        client = MySQLClient()
        client.execute_sync(CREATE_TABLE_SQL)
        # 旧库无反馈字段则补列（错误吞掉，不阻塞主流程）
        try:
            existing = client.execute_sync(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'llm_memory'"
            ) or []
            cols = {r["COLUMN_NAME"] for r in existing}
            for name, ddl in _FEEDBACK_COLUMNS:
                if name not in cols:
                    client.execute_sync(
                        f"ALTER TABLE `llm_memory` ADD COLUMN `{name}` {ddl}"
                    )
                    logger.info("llm_memory: 新增列 %s", name)
        except Exception as inner:
            logger.warning("llm_memory 列迁移失败（忽略）: %s", inner)
        client.close()
        _table_ensured = True
        logger.info("llm_memory 表已就绪")
    except Exception as e:
        logger.error("创建 llm_memory 表失败: %s", e)


def _json_dumps(obj) -> Optional[str]:
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return None


_STOPWORDS = frozenset(
    "的 了 吗 呢 吧 啊 在 是 有 和 与 或 到 从 把 被 让 给 用 "
    "我 你 他 她 它 我们 你们 他们 这 那 什么 怎么 怎样 如何 "
    "一个 一些 可以 能 会 就 也 都 还 又 再 很 太 更 最 "
    "the a an is are was were do does did of to in for on with".split()
)


def _extract_keywords(text: str, max_kw: int = 8) -> List[str]:
    """从自然语言中提取关键词，用于深度回忆搜索。"""
    tokens = re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+", text)
    keywords = []
    for t in tokens:
        if t.lower() in _STOPWORDS or len(t) < 2:
            continue
        keywords.append(t)
        if len(keywords) >= max_kw:
            break
    return keywords


class MemoryDbService:
    """统一的记忆读写服务（永久存储，按需检索）"""

    def __init__(self):
        _ensure_table()

    # ═══════════════════════ 写入 ═══════════════════════

    def save(
        self,
        module: str,
        session_id: str,
        user_query: str,
        *,
        user_id: Optional[str] = None,
        assistant_response: Optional[str] = None,
        intent: Optional[str] = None,
        sql_text: Optional[str] = None,
        row_count: Optional[int] = None,
        columns: Optional[List[str]] = None,
        rows: Optional[List[Dict]] = None,
        matched_tables: Optional[List[Dict]] = None,
        sources: Optional[List[Dict]] = None,
        collection_name: Optional[str] = None,
        extra: Optional[Dict] = None,
        latency_ms: Optional[int] = None,
    ) -> Optional[int]:
        """写入一条记忆，返回自增ID。数据库永久保留，不做自动清除。"""
        sql = """
        INSERT INTO `llm_memory`
            (`module`, `session_id`, `user_id`, `user_query`, `assistant_response`,
             `intent`, `sql_text`, `row_count`, `columns_json`, `rows_json`,
             `matched_tables`, `sources_json`, `collection_name`, `extra`, `latency_ms`)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        trimmed_rows = (rows or [])[:50] if rows else None
        trimmed_resp = assistant_response[:2000] if assistant_response else None
        params = (
            module, session_id, user_id, user_query, trimmed_resp,
            intent, sql_text, row_count,
            _json_dumps(columns), _json_dumps(trimmed_rows),
            _json_dumps(matched_tables), _json_dumps(sources),
            collection_name, _json_dumps(extra), latency_ms,
        )
        try:
            client = MySQLClient()
            client.execute_sync(sql, params)
            result = client.execute_sync("SELECT LAST_INSERT_ID() AS id")
            client.close()
            return result[0]["id"] if result else None
        except Exception as e:
            logger.error("保存记忆失败: %s", e)
            return None

    # ═══════════════════════ 即时记忆：当前会话最近N轮 ═══════════════════════

    def get_recent(
        self,
        module: str,
        session_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取某会话最近 N 条记忆（按时间正序）"""
        sql = """
        SELECT * FROM (
            SELECT * FROM `llm_memory`
            WHERE `module` = %s AND `session_id` = %s
            ORDER BY `id` DESC LIMIT %s
        ) t ORDER BY t.`id` ASC
        """
        try:
            client = MySQLClient()
            rows = client.execute_sync(sql, (module, session_id, limit))
            client.close()
            return [self._deserialize_row(r) for r in (rows or [])]
        except Exception as e:
            logger.error("读取记忆失败: %s", e)
            return []

    # ═══════════════════════ 深度回忆：跨会话/跨模块关键词检索 ═══════════════════════

    def deep_recall(
        self,
        query: str,
        *,
        module: Optional[str] = None,
        exclude_session: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """深度回忆 — 从全量历史记忆中检索与 query 相关的记录。

        策略：
        1. 先尝试 MySQL FULLTEXT（ngram）全文搜索，按相关度排序
        2. 如果全文索引不可用或无结果，fallback 到 LIKE 关键词匹配
        结果排除当前会话（已由即时记忆覆盖），避免重复。
        """
        keywords = _extract_keywords(query)
        if not keywords:
            return []

        results = self._fulltext_recall(query, module, exclude_session, limit)
        if not results:
            results = self._keyword_recall(keywords, module, exclude_session, limit)
        return results

    def _fulltext_recall(
        self, query: str, module: Optional[str], exclude_session: Optional[str], limit: int
    ) -> List[Dict[str, Any]]:
        """使用 FULLTEXT 索引进行深度回忆。"""
        where_parts = ["MATCH(`user_query`, `assistant_response`) AGAINST (%s IN NATURAL LANGUAGE MODE)"]
        params: list = [query]
        if module:
            where_parts.append("`module` = %s")
            params.append(module)
        if exclude_session:
            where_parts.append("`session_id` != %s")
            params.append(exclude_session)

        sql = f"""
        SELECT *,
               MATCH(`user_query`, `assistant_response`) AGAINST (%s IN NATURAL LANGUAGE MODE) AS relevance
        FROM `llm_memory`
        WHERE {' AND '.join(where_parts)}
        ORDER BY relevance DESC
        LIMIT %s
        """
        params_full = [query] + params + [limit]
        try:
            client = MySQLClient()
            rows = client.execute_sync(sql, tuple(params_full))
            client.close()
            return [self._deserialize_row(r) for r in (rows or [])]
        except Exception as e:
            logger.debug("全文检索失败（可能索引不可用），将 fallback 到关键词: %s", e)
            return []

    def _keyword_recall(
        self, keywords: List[str], module: Optional[str], exclude_session: Optional[str], limit: int
    ) -> List[Dict[str, Any]]:
        """关键词 LIKE 匹配 fallback。"""
        like_parts = []
        params: list = []
        for kw in keywords[:5]:
            like_parts.append("(`user_query` LIKE %s OR `assistant_response` LIKE %s)")
            params.extend([f"%{kw}%", f"%{kw}%"])

        where = " OR ".join(like_parts)
        extra_where = ""
        if module:
            extra_where += " AND `module` = %s"
            params.append(module)
        if exclude_session:
            extra_where += " AND `session_id` != %s"
            params.append(exclude_session)

        sql = f"""
        SELECT * FROM `llm_memory`
        WHERE ({where}){extra_where}
        ORDER BY `id` DESC
        LIMIT %s
        """
        params.append(limit)
        try:
            client = MySQLClient()
            rows = client.execute_sync(sql, tuple(params))
            client.close()
            return [self._deserialize_row(r) for r in (rows or [])]
        except Exception as e:
            logger.error("关键词回忆失败: %s", e)
            return []

    # ═══════════════════════ 全量搜索（后台管理用） ═══════════════════════

    def search(
        self,
        keyword: str,
        *,
        module: Optional[str] = None,
        session_id: Optional[str] = None,
        intent: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """全量搜索 — 供后台管理面板查询所有记忆。"""
        where_parts = []
        params: list = []

        if keyword:
            where_parts.append("(`user_query` LIKE %s OR `assistant_response` LIKE %s OR `sql_text` LIKE %s)")
            params.extend([f"%{keyword}%"] * 3)
        if module:
            where_parts.append("`module` = %s")
            params.append(module)
        if session_id:
            where_parts.append("`session_id` = %s")
            params.append(session_id)
        if intent:
            where_parts.append("`intent` = %s")
            params.append(intent)
        if date_from:
            where_parts.append("`created_at` >= %s")
            params.append(date_from)
        if date_to:
            where_parts.append("`created_at` <= %s")
            params.append(date_to + " 23:59:59")

        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        count_sql = f"SELECT COUNT(*) AS cnt FROM `llm_memory` {where_clause}"
        data_sql = f"""
        SELECT * FROM `llm_memory` {where_clause}
        ORDER BY `id` DESC LIMIT %s OFFSET %s
        """
        params_data = list(params) + [limit, offset]

        try:
            client = MySQLClient()
            cnt_result = client.execute_sync(count_sql, tuple(params))
            total = cnt_result[0]["cnt"] if cnt_result else 0
            rows = client.execute_sync(data_sql, tuple(params_data))
            client.close()
            return {
                "total": total,
                "items": [self._deserialize_row(r) for r in (rows or [])],
            }
        except Exception as e:
            logger.error("搜索记忆失败: %s", e)
            return {"total": 0, "items": []}

    # ═══════════════════════ 会话列表 ═══════════════════════

    def get_sessions(
        self,
        module: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """获取所有会话摘要列表。"""
        where = "WHERE `module` = %s" if module else ""
        params_w: list = [module] if module else []

        count_sql = f"""
        SELECT COUNT(DISTINCT `session_id`) AS cnt FROM `llm_memory` {where}
        """
        data_sql = f"""
        SELECT `module`, `session_id`,
               COUNT(*) AS memory_count,
               MIN(`created_at`) AS first_active,
               MAX(`created_at`) AS last_active,
               (SELECT `user_query` FROM `llm_memory` m2
                WHERE m2.`module` = m1.`module` AND m2.`session_id` = m1.`session_id`
                ORDER BY m2.`id` DESC LIMIT 1) AS last_query
        FROM `llm_memory` m1 {where}
        GROUP BY `module`, `session_id`
        ORDER BY MAX(`id`) DESC
        LIMIT %s OFFSET %s
        """
        try:
            client = MySQLClient()
            cnt_result = client.execute_sync(count_sql, tuple(params_w))
            total = cnt_result[0]["cnt"] if cnt_result else 0
            rows = client.execute_sync(data_sql, tuple(params_w + [limit, offset]))
            client.close()
            items = []
            for r in (rows or []):
                for dt_key in ("first_active", "last_active"):
                    if isinstance(r.get(dt_key), datetime):
                        r[dt_key] = r[dt_key].isoformat()
                items.append(r)
            return {"total": total, "items": items}
        except Exception as e:
            logger.error("查询会话列表失败: %s", e)
            return {"total": 0, "items": []}

    # ═══════════════════════ 单条详情 ═══════════════════════

    def get_by_id(self, memory_id: int) -> Optional[Dict[str, Any]]:
        sql = "SELECT * FROM `llm_memory` WHERE `id` = %s"
        try:
            client = MySQLClient()
            rows = client.execute_sync(sql, (memory_id,))
            client.close()
            if rows:
                return self._deserialize_row(rows[0])
            return None
        except Exception as e:
            logger.error("获取记忆详情失败: %s", e)
            return None

    # ═══════════════════════ 最后一条有数据的记录 ═══════════════════════

    def get_last_with_data(self, module: str, session_id: str) -> Optional[Dict[str, Any]]:
        """获取最近一条有 rows_json 的记忆（用于 STI followup）"""
        sql = """
        SELECT * FROM `llm_memory`
        WHERE `module` = %s AND `session_id` = %s AND `rows_json` IS NOT NULL
        ORDER BY `id` DESC LIMIT 1
        """
        try:
            client = MySQLClient()
            rows = client.execute_sync(sql, (module, session_id))
            client.close()
            if rows:
                return self._deserialize_row(rows[0])
            return None
        except Exception as e:
            logger.error("读取记忆失败: %s", e)
            return None

    # ═══════════════════════ 用户反馈（点赞/差劲/评论） ═══════════════════════

    def update_feedback(
        self,
        memory_id: int,
        *,
        liked: Optional[bool] = None,
        disliked: Optional[bool] = None,
        comment: Optional[str] = None,
        feedback_by: Optional[str] = None,
    ) -> bool:
        """更新指定记忆的用户反馈字段。

        - liked / disliked 互斥：写一边自动清零另一边，避免同条同时点赞+踩。
        - comment：None 表示不修改；空字符串表示清空已有评论。
        - feedback_by：操作人 username，会合并写入 extra JSON（key: feedback_by）。
        - 任意一个参数有效即触发更新。
        """
        sets: list[str] = []
        params: list = []

        if liked is True:
            sets.extend(["`user_liked` = 1", "`user_disliked` = 0"])
        elif liked is False:
            sets.append("`user_liked` = 0")

        if disliked is True:
            sets.extend(["`user_disliked` = 1", "`user_liked` = 0"])
        elif disliked is False:
            sets.append("`user_disliked` = 0")

        if comment is not None:
            sets.append("`user_comment` = %s")
            params.append(comment[:2000] if comment else None)

        # 将反馈人写入 extra 的 feedback_by 字段（JSON_SET 方式原地合并）
        if feedback_by:
            sets.append(
                "`extra` = JSON_SET(COALESCE(`extra`, '{}'), '$.feedback_by', %s)"
            )
            params.append(feedback_by)

        if not sets:
            return False

        sql = f"UPDATE `llm_memory` SET {', '.join(sets)} WHERE `id` = %s"
        params.append(memory_id)
        try:
            client = MySQLClient()
            result = client.execute_sync(sql, tuple(params))
            client.close()
            affected = result[0]["affected_rows"] if result else 0
            return affected > 0
        except Exception as e:
            logger.error("更新记忆反馈失败 id=%s: %s", memory_id, e)
            return False

    # ═══════════════════════ 清除（仅后台管理手动调用） ═══════════════════════

    def clear_session(self, module: str, session_id: str) -> int:
        """手动清除指定会话记忆。仅后台管理页面调用，引擎代码不应自动调用。"""
        sql = "DELETE FROM `llm_memory` WHERE `module` = %s AND `session_id` = %s"
        try:
            client = MySQLClient()
            result = client.execute_sync(sql, (module, session_id))
            client.close()
            return result[0]["affected_rows"] if result else 0
        except Exception as e:
            logger.error("清除记忆失败: %s", e)
            return 0

    # ═══════════════════════ 分页查询（后台管理用） ═══════════════════════

    def list_all(
        self,
        module: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        where_parts = []
        params: list = []
        if module:
            where_parts.append("`module` = %s")
            params.append(module)
        if session_id:
            where_parts.append("`session_id` = %s")
            params.append(session_id)

        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        count_sql = f"SELECT COUNT(*) AS cnt FROM `llm_memory` {where_clause}"
        data_sql = f"""
        SELECT * FROM `llm_memory` {where_clause}
        ORDER BY `id` DESC LIMIT %s OFFSET %s
        """
        params_data = params + [limit, offset]

        try:
            client = MySQLClient()
            cnt_result = client.execute_sync(count_sql, tuple(params))
            total = cnt_result[0]["cnt"] if cnt_result else 0
            rows = client.execute_sync(data_sql, tuple(params_data))
            client.close()
            return {
                "total": total,
                "items": [self._deserialize_row(r) for r in (rows or [])],
            }
        except Exception as e:
            logger.error("查询记忆列表失败: %s", e)
            return {"total": 0, "items": []}

    # ═══════════════════════ 统计 ═══════════════════════

    def get_stats(self) -> Dict[str, Any]:
        sql = """
        SELECT `module`, COUNT(*) AS cnt,
               COUNT(DISTINCT `session_id`) AS sessions,
               MAX(`created_at`) AS last_active
        FROM `llm_memory` GROUP BY `module`
        """
        total_sql = "SELECT COUNT(*) AS total FROM `llm_memory`"
        try:
            client = MySQLClient()
            rows = client.execute_sync(sql)
            total_r = client.execute_sync(total_sql)
            client.close()
            return {
                "total_memories": total_r[0]["total"] if total_r else 0,
                "modules": [
                    {
                        "module": r["module"],
                        "memory_count": r["cnt"],
                        "session_count": r["sessions"],
                        "last_active": r["last_active"].isoformat() if isinstance(r["last_active"], datetime) else str(r["last_active"]),
                    }
                    for r in (rows or [])
                ],
            }
        except Exception as e:
            logger.error("统计记忆失败: %s", e)
            return {"total_memories": 0, "modules": []}

    def get_lsta_stats(self) -> Dict[str, Any]:
        """LSTA 专项统计：优化次数、点赞、差劲、评论数量。"""
        sqls = {
            "optimize_count": (
                "SELECT COUNT(*) AS v FROM `llm_memory` "
                "WHERE `module`='lsta' AND `intent`='optimize'"
            ),
            "refine_count": (
                "SELECT COUNT(*) AS v FROM `llm_memory` "
                "WHERE `module`='lsta' AND `intent`='refine'"
            ),
            "liked_count": (
                "SELECT COUNT(*) AS v FROM `llm_memory` "
                "WHERE `module`='lsta' AND `user_liked`=1"
            ),
            "disliked_count": (
                "SELECT COUNT(*) AS v FROM `llm_memory` "
                "WHERE `module`='lsta' AND `user_disliked`=1"
            ),
            "comment_count": (
                "SELECT COUNT(*) AS v FROM `llm_memory` "
                "WHERE `module`='lsta' "
                "AND `user_comment` IS NOT NULL AND `user_comment` != ''"
            ),
            "total_lsta": (
                "SELECT COUNT(*) AS v FROM `llm_memory` WHERE `module`='lsta'"
            ),
        }
        result: Dict[str, Any] = {}
        try:
            client = MySQLClient()
            for key, sql in sqls.items():
                rows = client.execute_sync(sql)
                result[key] = rows[0]["v"] if rows else 0
            client.close()
        except Exception as e:
            logger.error("LSTA 统计失败: %s", e)
            result = {k: 0 for k in sqls}
        return result

    # ═══════════════════════ 反序列化 ═══════════════════════

    @staticmethod
    def _deserialize_row(row: Dict) -> Dict[str, Any]:
        for json_key in ("columns_json", "rows_json", "matched_tables", "sources_json", "extra"):
            val = row.get(json_key)
            if isinstance(val, str):
                try:
                    row[json_key] = json.loads(val)
                except Exception:
                    pass
        if isinstance(row.get("created_at"), datetime):
            row["created_at"] = row["created_at"].isoformat()
        return row


memory_db = MemoryDbService()
