from __future__ import annotations

from typing import Any, Dict, List, Optional

from pymilvus import AnnSearchRequest, RRFRanker

from Base.Client.milvusClient import MilvusClientSingleton
from Base.Config.setting import settings
from Base.Repository.connections.milvusConnection import MilvusVDBConnection
from LMA.constants import DEFAULT_COLLECTION
from LMA.service.base import service_logger
from LMA.service.embeddingService import embedding_service

logger = service_logger

_OUTPUT_FIELDS = ["text", "file_name", "chunk_index"]


def _collection_has_sparse_field(collection_name: str) -> bool:
    singleton = MilvusClientSingleton()
    for attempt in range(2):
        try:
            cli = singleton.get_client()
            if not cli.has_collection(collection_name):
                return False
            desc = cli.describe_collection(collection_name=collection_name)
            for f in desc.get("fields", []):
                if f.get("name") == "sparse":
                    return True
            return False
        except Exception as e:
            if attempt == 0 and "connection" in str(e).lower():
                logger.warning("检查 sparse 字段时连接断开，重连后重试: %s", e)
                try:
                    singleton.reconnect()
                except Exception:
                    pass
                continue
            logger.warning("检查集合 sparse 字段失败: %s", e)
            return False
    return False


def _normalize_dense_vector(raw: List[Any]) -> List[float]:
    if not raw:
        return []
    first = raw[0]
    if isinstance(first, (int, float)):
        return [float(x) for x in raw]
    return [float(x) for x in first]


def _hit_to_row(hit: Any) -> Optional[Dict[str, Any]]:
    try:
        if isinstance(hit, dict):
            ent = hit.get("entity") or hit
            return {
                "text": ent.get("text", ""),
                "file_name": ent.get("file_name", ""),
                "chunk_index": ent.get("chunk_index", -1),
                "distance": hit.get("distance"),
                "score": hit.get("score"),
            }
        ent = getattr(hit, "entity", None)
        if ent is not None:
            get = getattr(ent, "get", None)
            if callable(get):
                return {
                    "text": get("text") or "",
                    "file_name": get("file_name") or "",
                    "chunk_index": get("chunk_index") if get("chunk_index") is not None else -1,
                    "distance": getattr(hit, "distance", None),
                    "score": getattr(hit, "score", None),
                }
    except Exception as e:
        logger.debug("解析 hit 失败: %s", e)
    return None


def _format_hybrid_results(results: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not results:
        return out
    for hits in results:
        if hits is None:
            continue
        for hit in hits:
            row = _hit_to_row(hit)
            if row and (row.get("text") or "").strip():
                out.append(row)
    return out


def _format_dense_search_results(results: Any) -> List[Dict[str, Any]]:
    if not results:
        return []
    first = results[0] if isinstance(results, list) else results
    out: List[Dict[str, Any]] = []
    for hit in first or []:
        row = _hit_to_row(hit)
        if row and (row.get("text") or "").strip():
            out.append(row)
    return out


class RetrievalService:
    """向量 + BM25（若 schema 支持）混合检索；否则退化为纯向量检索。"""

    def retrieve(
        self,
        question: str,
        collection_name: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        name = collection_name or DEFAULT_COLLECTION
        if not question or not question.strip():
            return []

        dim = settings.milvus.vector_dim or 1024
        raw_emb = embedding_service.embedding_texts([question.strip()], dimensions=dim)
        if not raw_emb:
            logger.warning("问题 embedding 为空")
            return []
        vec = _normalize_dense_vector(raw_emb[0])
        if not vec:
            return []

        prefetch = max(top_k * 2, top_k)

        if _collection_has_sparse_field(name):
            return self._hybrid(question.strip(), vec, name, top_k, prefetch)
        logger.info("集合 %s 无 BM25 sparse 字段，使用纯向量检索", name)
        return self._dense_only(vec, name, top_k)

    def _hybrid(
        self,
        question: str,
        vec: List[float],
        collection_name: str,
        top_k: int,
        prefetch: int,
    ) -> List[Dict[str, Any]]:
        dense_req = AnnSearchRequest(
            data=[vec],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=prefetch,
        )
        sparse_req = AnnSearchRequest(
            data=[question],
            anns_field="sparse",
            param={"metric_type": "BM25", "params": {}},
            limit=prefetch,
        )
        for attempt in range(2):
            try:
                vdb = MilvusVDBConnection()
                results = vdb.hybrid_search(
                    collection_name=collection_name,
                    reqs=[dense_req, sparse_req],
                    limit=top_k,
                    ranker=RRFRanker(),
                    output_fields=_OUTPUT_FIELDS,
                )
                return _format_hybrid_results(results)[:top_k]
            except Exception as e:
                if attempt == 0 and "connection" in str(e).lower():
                    logger.warning("混合检索连接断开，重连后重试: %s", e)
                    try:
                        MilvusClientSingleton().reconnect()
                    except Exception:
                        pass
                    continue
                logger.error("混合检索失败，降级为向量检索: %s", e)
                return self._dense_only(vec, collection_name, top_k)
        return self._dense_only(vec, collection_name, top_k)

    def _dense_only(self, vec: List[float], collection_name: str, top_k: int) -> List[Dict[str, Any]]:
        try:
            raw = MilvusClientSingleton().search(
                collection_name=collection_name,
                data=[vec],
                anns_field="embedding",
                limit=top_k,
                output_fields=_OUTPUT_FIELDS,
            )
            return _format_dense_search_results(raw)[:top_k]
        except Exception as e:
            logger.error("向量检索失败: %s", e)
            return []


retrieval_service = RetrievalService()
