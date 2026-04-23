import uuid
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    PDF_FORMATTED = "pdf_formatted"
    UNSTRUCTURED = "unstructured"


class ChunkStrategy(str, Enum):
    """文本切分策略：固定滑窗 vs 智能（段落/句子优先递归切分）。"""

    FIXED = "fixed"
    SMART = "smart"


class LeangApiParams(BaseModel):
    collection_name: Optional[str] = Field(None, description="Milvus 集合名")
    source_kind: SourceKind = Field(..., description="文件来源类型")
    chunk_strategy: ChunkStrategy = Field(
        ChunkStrategy.FIXED,
        description="切分策略：fixed=固定字符滑窗；smart=智能（段落/中英文句读优先）",
    )
    chunk_size: Optional[int] = Field(None, ge=1, description="块大小字符数，空则使用环境默认")
    chunk_overlap: Optional[int] = Field(None, ge=0, description="块重叠字符数，空则使用环境默认")


class LeangFileInfo(BaseModel):
    file_path: Optional[str] = Field(None, description="本地临时文件路径")
    file_name: Optional[str] = Field(None, description="原文件名")


class LeangEmbeddingResult(BaseModel):
    inserted: int = Field(0, description="成功插入条数")
    message: str = Field("", description="执行结果消息")
    collection_name: Optional[str] = Field(None, description="目标集合名")


class LeangChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    collection_name: Optional[str] = Field(
        None,
        description="检索集合名；空则使用 LEANG_MILVUS_COLLECTION",
    )
    top_k: int = Field(5, ge=1, le=50, description="混合检索返回并送入大模型的片段条数")
    session_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="会话 ID；相同 ID 会读写 llm_memory 近期轮次",
    )
    user_id: Optional[str] = Field(None, description="可选用户标识，写入 llm_memory")
    memory_turns: int = Field(
        5,
        ge=0,
        le=20,
        description="从 llm_memory 拉取本 session 最近几条作为短期记忆；0=关闭",
    )
    model: Optional[str] = Field(None, description="指定模型 provider:model，空则使用默认模型")


class LeangState(BaseModel):
    api_params: LeangApiParams
    file_info: LeangFileInfo = Field(default_factory=LeangFileInfo)
    embedding_result: LeangEmbeddingResult = Field(default_factory=LeangEmbeddingResult)

    @property
    def file_basename(self) -> str:
        if self.file_info.file_name:
            return self.file_info.file_name
        if self.file_info.file_path:
            return Path(self.file_info.file_path).name
        return "unknown"
