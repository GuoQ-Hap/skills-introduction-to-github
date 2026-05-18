from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class STIChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    message: str = Field(..., min_length=1, description="用户自然语言查询")
    user_id: Optional[str] = Field(None, description="可选用户标识，写入 llm_memory")
    model: Optional[str] = Field(None, description="指定模型 provider:model，空则使用主模型")
    data_restrictions: Optional[Dict[str, List[str]]] = Field(
        None,
        description="字段级查询限制，key 为字段名（如 store_name），value 为允许的值列表",
    )


class STIChatResponse(BaseModel):
    session_id: str
    intent: str
    query: str
    sql: Optional[str] = None
    matched_tables: List[Dict[str, Any]] = []
    data: Optional[Dict[str, Any]] = None
    analysis: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0


class STISQLRequest(BaseModel):
    sql: str = Field(..., min_length=1, description="SELECT SQL 语句")


class STISQLResponse(BaseModel):
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []
    row_count: int = 0
    error: Optional[str] = None


class STIMemoryItem(BaseModel):
    user_query: str
    sql: str
    row_count: int
    summary: str


class STIMemoryResponse(BaseModel):
    session_id: str
    count: int
    items: List[STIMemoryItem]


class STITableSearchResult(BaseModel):
    table: str
    layer: str
    description: str


class STITableDetail(BaseModel):
    table: str
    layer: str
    description: str
    columns: List[Dict[str, Any]]


class STIHealthResponse(BaseModel):
    status: str
    time: str
    active_sessions: int
    model: str
