import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, File, Form, Query, UploadFile

from Base.Config.setting import settings
from Base.RicUtils.fileUtils import save_upload_file_to_temp
from Base.RicUtils.httpUtils import HttpResponse
from LMA.ai.embedding.leangState import (
    ChunkStrategy,
    LeangApiParams,
    LeangChatRequest,
    LeangState,
    SourceKind,
)
from LMA.constants import CHUNK_OVERLAP, CHUNK_SIZE, DEFAULT_COLLECTION, sanitize_collection_name
from LMA.core.embeddingCore import LeangEmbeddingCore
from LMA.core.qaCore import LeangQACore
from LMA.service import get_text_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ────────────────────── 健康检查 ──────────────────────

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "module": "LMA",
        "default_collection": DEFAULT_COLLECTION,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }


# ────────────────────── 文档拆分预览（不入库） ──────────────────────

@router.post("/preview-chunks")
async def preview_chunks(
    file: UploadFile = File(...),
    source_kind: str = Form("unstructured", description="pdf_formatted 或 unstructured"),
    chunk_strategy: str = Form(ChunkStrategy.FIXED.value, description="fixed / smart"),
    chunk_size: Optional[int] = Form(None, description="块大小"),
    chunk_overlap: Optional[int] = Form(None, description="重叠"),
):
    """上传文件 → 提取文本 → 按参数拆分 → 返回分块预览，不写入 Milvus。"""
    file_path = await save_upload_file_to_temp(file, use_original_filename=False)
    try:
        try:
            kind = SourceKind(source_kind)
        except ValueError:
            return HttpResponse.error(msg=f"无效 source_kind: {source_kind}")
        try:
            strat = ChunkStrategy(chunk_strategy)
        except ValueError:
            return HttpResponse.error(msg=f"无效 chunk_strategy: {chunk_strategy}")

        ts = get_text_service()
        text = ts.load_text(file_path, kind)
        if not text or not text.strip():
            return HttpResponse.error(msg="无法提取文本内容")

        size = chunk_size or CHUNK_SIZE
        overlap = chunk_overlap if chunk_overlap is not None else CHUNK_OVERLAP
        chunks = ts.split_text(text, strat, size, overlap)

        return HttpResponse.ok(data={
            "file_name": file.filename,
            "total_chars": len(text),
            "chunk_count": len(chunks),
            "chunk_strategy": strat.value,
            "chunk_size": size,
            "chunk_overlap": overlap,
            "chunks": [
                {"index": i, "length": len(c), "content": c}
                for i, c in enumerate(chunks)
            ],
        })
    finally:
        if os.path.exists(file_path):
            os.unlink(file_path)


# ────────────────────── 文档入库 ──────────────────────

@router.post("/ingest")
async def embedding_ingest(
    file: UploadFile = File(...),
    source_kind: str = Form(..., description="pdf_formatted 或 unstructured"),
    collection_name: Optional[str] = Form(
        None,
        description="可选；留空则用 LEANG_MILVUS_COLLECTION（勿填 Swagger 示例 string）",
    ),
    chunk_strategy: str = Form(
        ChunkStrategy.FIXED.value,
        description="fixed=固定字符滑窗；smart=智能（段落/句读优先）",
    ),
    chunk_size: Optional[int] = Form(None, description="块大小，空则使用 LEANG_CHUNK_SIZE"),
    chunk_overlap: Optional[int] = Form(None, description="重叠，空则使用 LEANG_CHUNK_OVERLAP"),
):
    file_path = await save_upload_file_to_temp(file, use_original_filename=False)
    try:
        kind = SourceKind(source_kind)
    except ValueError:
        if os.path.exists(file_path):
            os.unlink(file_path)
        return HttpResponse.error(msg=f"无效 source_kind: {source_kind}")
    try:
        strat = ChunkStrategy(chunk_strategy)
    except ValueError:
        if os.path.exists(file_path):
            os.unlink(file_path)
        allowed = [e.value for e in ChunkStrategy]
        return HttpResponse.error(msg=f"无效 chunk_strategy: {chunk_strategy}，允许: {allowed}")

    try:
        state = LeangState(
            api_params=LeangApiParams(
                source_kind=kind,
                collection_name=sanitize_collection_name(collection_name),
                chunk_strategy=strat,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
        )
        state.file_info.file_path = file_path
        state.file_info.file_name = file.filename
        result = LeangEmbeddingCore().run(state)
        if result.embedding_result.inserted > 0:
            return HttpResponse.ok(
                data={
                    "inserted": result.embedding_result.inserted,
                    "collection": result.embedding_result.collection_name,
                    "chunk_strategy": result.api_params.chunk_strategy.value,
                },
                msg=result.embedding_result.message,
            )
        return HttpResponse.error(msg=result.embedding_result.message)
    finally:
        if os.path.exists(file_path):
            os.unlink(file_path)


# ────────────────────── RAG 问答 ──────────────────────

@router.post("/chat")
async def leang_chat(body: LeangChatRequest):
    result = LeangQACore().ask(
        body.question,
        collection_name=sanitize_collection_name(body.collection_name),
        top_k=body.top_k,
        session_id=body.session_id,
        user_id=body.user_id,
        memory_turns=body.memory_turns,
        preferred_model=body.model,
    )
    if result.get("error"):
        return HttpResponse.error(msg=str(result["error"]))
    return HttpResponse.ok(
        data={
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
            "collection": result.get("collection"),
            "session_id": body.session_id,
        },
        msg="success.",
    )


# ────────────────────── Milvus 集合管理 ──────────────────────

@router.get("/collections")
async def list_collections():
    """列出所有 Milvus 集合及其实体数量。"""
    try:
        from pymilvus import connections, utility, Collection
        alias = f"lma_list_{int(time.time())}"
        ms = settings.milvus
        host = ms.host or "localhost"
        port = ms.port or 19530
        connections.connect(
            alias=alias, host=host, port=port,
            user=ms.user or "", password=ms.password or "",
            db_name=ms.database or "default", timeout=5,
        )
        names = utility.list_collections(using=alias)
        result = []
        for name in sorted(names):
            try:
                col = Collection(name, using=alias)
                col.load()
                result.append({
                    "name": name,
                    "num_entities": col.num_entities,
                    "description": col.description or "",
                })
            except Exception:
                result.append({"name": name, "num_entities": -1, "description": "无法加载"})
        connections.disconnect(alias)
        return HttpResponse.ok(data=result)
    except Exception as e:
        logger.error("列出 Milvus 集合失败: %s", e)
        return HttpResponse.error(msg=str(e))


@router.get("/collection/{collection_name}")
async def collection_detail(collection_name: str):
    """获取集合详情：字段 schema、实体数量等。"""
    try:
        from pymilvus import connections, Collection
        alias = f"lma_detail_{int(time.time())}"
        ms = settings.milvus
        connections.connect(
            alias=alias, host=ms.host or "localhost", port=ms.port or 19530,
            user=ms.user or "", password=ms.password or "",
            db_name=ms.database or "default", timeout=5,
        )
        col = Collection(collection_name, using=alias)
        col.load()
        fields = []
        for f in col.schema.fields:
            info = {"name": f.name, "dtype": str(f.dtype), "is_primary": f.is_primary}
            if hasattr(f, "params") and f.params:
                info["params"] = {k: v for k, v in f.params.items()}
            fields.append(info)
        data = {
            "name": collection_name,
            "num_entities": col.num_entities,
            "description": col.description or "",
            "fields": fields,
        }
        connections.disconnect(alias)
        return HttpResponse.ok(data=data)
    except Exception as e:
        logger.error("获取集合详情失败: %s", e)
        return HttpResponse.error(msg=str(e))


@router.get("/collection/{collection_name}/data")
async def collection_data(
    collection_name: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """分页浏览集合中的数据（仅返回标量字段，不返回向量）。"""
    try:
        from pymilvus import connections, Collection
        alias = f"lma_data_{int(time.time())}"
        ms = settings.milvus
        connections.connect(
            alias=alias, host=ms.host or "localhost", port=ms.port or 19530,
            user=ms.user or "", password=ms.password or "",
            db_name=ms.database or "default", timeout=5,
        )
        try:
            col = Collection(collection_name, using=alias)
            col.load()
            scalar_fields = [
                f.name for f in col.schema.fields
                if f.dtype.name not in ("FLOAT_VECTOR", "BINARY_VECTOR", "SPARSE_FLOAT_VECTOR", "FLOAT16_VECTOR", "BFLOAT16_VECTOR")
            ]
            res = col.query(
                expr="",
                output_fields=scalar_fields,
                offset=offset,
                limit=limit,
            )
            return HttpResponse.ok(data={
                "collection": collection_name,
                "offset": offset,
                "limit": limit,
                "count": len(res),
                "rows": res,
            })
        finally:
            connections.disconnect(alias)
    except Exception as e:
        logger.error("查询集合数据失败: %s", e)
        return HttpResponse.error(msg=str(e))


@router.delete("/collection/{collection_name}")
async def drop_collection(collection_name: str):
    """删除指定 Milvus 集合。"""
    try:
        from pymilvus import connections, utility
        alias = f"lma_drop_{int(time.time())}"
        ms = settings.milvus
        connections.connect(
            alias=alias, host=ms.host or "localhost", port=ms.port or 19530,
            user=ms.user or "", password=ms.password or "",
            db_name=ms.database or "default", timeout=5,
        )
        try:
            utility.drop_collection(collection_name, using=alias)
        finally:
            connections.disconnect(alias)
        return HttpResponse.ok(msg=f"集合 {collection_name} 已删除")
    except Exception as e:
        logger.error("删除集合失败: %s", e)
        return HttpResponse.error(msg=str(e))
