"""sql_to_index FastAPI 接口"""
from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException

from LDA.constants import SESSION_MAX, SESSION_TTL
from LDA.core.sqlCore import LLMNLPtoSQL
from LDA.models.sqlState import (
    STIChatRequest,
    STIChatResponse,
    STIHealthResponse,
    STIMemoryItem,
    STIMemoryResponse,
    STISQLRequest,
    STISQLResponse,
    STITableDetail,
    STITableSearchResult,
)
from LDA.service.base import service_logger
from LDA.service.dbService import db_service
from LDA.service.schemaService import schema_service

logger = service_logger
router = APIRouter()

_sessions: dict[str, dict] = {}
_lock = Lock()


def get_engine(session_id: str) -> LLMNLPtoSQL:
    with _lock:
        now = time.time()
        if session_id in _sessions:
            _sessions[session_id]["last_active"] = now
            return _sessions[session_id]["engine"]

        expired = [s for s, v in _sessions.items() if now - v["last_active"] > SESSION_TTL]
        for s in expired:
            del _sessions[s]
        if len(_sessions) >= SESSION_MAX:
            oldest = sorted(_sessions, key=lambda k: _sessions[k]["last_active"])
            for s in oldest[: len(_sessions) - SESSION_MAX + 1]:
                del _sessions[s]

        engine = LLMNLPtoSQL()
        engine.hydrate_from_db(session_id)
        _sessions[session_id] = {"engine": engine, "created_at": now, "last_active": now}
        return engine


def _serialize(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return str(v)


@router.get("/health", response_model=STIHealthResponse, summary="健康检查")
def health():
    from admin.model_pool import model_pool
    primary = model_pool.primary
    model_name = f"{primary['provider']}:{primary['model']}" if primary else "none"
    return STIHealthResponse(
        status="ok",
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        active_sessions=len(_sessions),
        model=model_name,
    )


@router.post("/chat", response_model=STIChatResponse, summary="主对话接口")
def chat(req: STIChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    engine = get_engine(req.session_id)
    intent = engine.classify_intent(req.message)
    result = engine.query(req.message, session_id=req.session_id, user_id=req.user_id,
                          preferred_model=req.model)

    return STIChatResponse(
        session_id=req.session_id,
        intent=intent,
        query=result.get("query", req.message),
        sql=result.get("sql"),
        matched_tables=result.get("matched_tables", []),
        data=result.get("data"),
        analysis=result.get("analysis"),
        error=result.get("error"),
        attempts=result.get("attempts", 0),
    )


@router.get("/memory/{session_id}", response_model=STIMemoryResponse, summary="查看会话记忆")
def get_memory(session_id: str):
    with _lock:
        session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    items = [
        STIMemoryItem(
            user_query=m["user_query"],
            sql=m.get("sql", ""),
            row_count=m.get("row_count", 0),
            summary=m.get("summary", ""),
        )
        for m in session["engine"].memory
    ]
    return STIMemoryResponse(session_id=session_id, count=len(items), items=items)


@router.delete("/memory/{session_id}", summary="清除会话记忆")
def clear_memory(session_id: str):
    with _lock:
        session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    session["engine"].clear_memory()
    return {"session_id": session_id, "status": "cleared"}


@router.get("/tables", response_model=list[STITableSearchResult], summary="搜索表")
def search_tables(keyword: str):
    results = schema_service.search_tables(keyword)
    return [
        STITableSearchResult(table=r["table"], layer=r.get("layer", ""), description=r.get("description", ""))
        for r in results
    ]


@router.get("/table/{table_name}", response_model=STITableDetail, summary="查看表结构")
def describe_table(table_name: str):
    info = schema_service.describe_table(table_name)
    if not info:
        raise HTTPException(status_code=404, detail=f"表不存在: {table_name}")
    return STITableDetail(
        table=info["table"],
        layer=info.get("layer", ""),
        description=info.get("description", ""),
        columns=info.get("columns", []),
    )


@router.post("/sql", response_model=STISQLResponse, summary="执行原始 SQL（仅 SELECT）")
def execute_sql(req: STISQLRequest):
    is_safe, reason = db_service.validate_sql_safety(req.sql)
    if not is_safe:
        return STISQLResponse(error=f"Safety Block: {reason}")
    try:
        columns, rows = db_service.execute_sql(req.sql)
        serialized = [{k: _serialize(v) for k, v in row.items()} for row in rows]
        return STISQLResponse(columns=columns, rows=serialized, row_count=len(rows))
    except Exception as e:
        return STISQLResponse(error=str(e))
