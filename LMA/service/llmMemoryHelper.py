"""Leang 与统一表 llm_memory 的读写（module=leang）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from LMA.service.base import service_logger

logger = service_logger

MODULE_LEANG = "LMA"


def format_recent_memory_block(rows: List[Dict[str, Any]], max_chars: int = 4000) -> str:
    if not rows:
        return ""
    lines = ["## 近期对话记忆（同一 session，便于理解指代与上下文）"]
    used = 0
    for i, r in enumerate(rows, 1):
        u = (r.get("user_query") or "")[:400]
        a = (r.get("assistant_response") or "")[:600]
        block = f"[{i}] 用户: {u}\n    助手: {a}\n"
        if used + len(block) > max_chars:
            break
        lines.append(block)
        used += len(block)
    return "\n".join(lines)


def fetch_recent_memory_block(session_id: str, limit: int) -> str:
    if not session_id or limit <= 0:
        return ""
    try:
        from Base.Service.memoryDbService import memory_db

        rows = memory_db.get_recent(MODULE_LEANG, session_id, limit=limit)
        return format_recent_memory_block(rows)
    except Exception as e:
        logger.warning("Leang 读取 llm_memory 失败: %s", e)
        return ""


def persist_rag_turn(
    session_id: str,
    user_query: str,
    *,
    user_id: Optional[str] = None,
    assistant_response: Optional[str] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
    collection_name: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> None:
    if not session_id:
        return
    try:
        from Base.Service.memoryDbService import memory_db

        memory_db.save(
            MODULE_LEANG,
            session_id,
            user_query,
            user_id=user_id,
            assistant_response=assistant_response,
            intent="rag_chat",
            sources=sources,
            collection_name=collection_name,
            latency_ms=latency_ms,
        )
    except Exception as e:
        logger.warning("Leang 写入 llm_memory 失败: %s", e)
