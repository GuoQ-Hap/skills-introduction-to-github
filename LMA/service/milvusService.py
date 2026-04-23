from typing import Any, Dict, List

from pymilvus import CollectionSchema, DataType, FieldSchema, Function, FunctionType

from Base.Client.milvusClient import MilvusClientSingleton
from Base.Config.setting import settings
from LMA.constants import DEFAULT_COLLECTION, ENABLE_BM25_HYBRID, TEXT_FIELD_MAX
from LMA.service.base import service_logger

logger = service_logger


class MilvusService:
    # Milvus 2.4+：含 sparse 的集合在 load 前必须为 sparse 建索引，否则 load_collection 报 65535。
    _dense_index_params = [
        {
            "field_name": "embedding",
            "index_type": "HNSW",
            "metric_type": "COSINE",
            "params": {"M": 8, "efConstruction": 64},
        },
    ]
    _sparse_bm25_index = {
        "field_name": "sparse",
        "index_type": "SPARSE_INVERTED_INDEX",
        "metric_type": "BM25",
        "params": {
            "inverted_index_algo": "DAAT_MAXSCORE",
            "bm25_k1": 1.2,
            "bm25_b": 0.75,
        },
    }

    @staticmethod
    def _schema(dim: int) -> CollectionSchema:
        if ENABLE_BM25_HYBRID:
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
                FieldSchema(
                    name="text",
                    dtype=DataType.VARCHAR,
                    max_length=TEXT_FIELD_MAX,
                    enable_match=True,
                    enable_analyzer=True,
                ),
                FieldSchema(name="sparse", dtype=DataType.SPARSE_FLOAT_VECTOR),
                FieldSchema(name="source_type", dtype=DataType.VARCHAR, max_length=32),
                FieldSchema(name="chunk_index", dtype=DataType.INT32),
                FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=512),
            ]
            schema = CollectionSchema(fields=fields, description="leang + BM25 (需 Milvus 2.4+)")
            schema.add_function(
                Function(
                    name="leang_text_bm25",
                    input_field_names=["text"],
                    output_field_names=["sparse"],
                    function_type=FunctionType.BM25,
                )
            )
            return schema

        # Milvus 2.3.x：仅稠密向量 + 文本，不建 sparse/BM25，避免 CreateIndex 与进程 SIGABRT
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=TEXT_FIELD_MAX),
            FieldSchema(name="source_type", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="chunk_index", dtype=DataType.INT32),
            FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=512),
        ]
        return CollectionSchema(fields=fields, description="leang dense-only (兼容 Milvus 2.3)")

    def ensure_collection(self, collection_name: str | None = None) -> str:
        name = collection_name or DEFAULT_COLLECTION
        if not ENABLE_BM25_HYBRID:
            logger.info(
                "leang 稠密-only（已设置 LEANG_ENABLE_BM25=0，用于兼容 Milvus 2.3.x）"
            )
        dim = settings.milvus.vector_dim or 1024
        client = MilvusClientSingleton()
        index_params = (
            [*self._dense_index_params, self._sparse_bm25_index]
            if ENABLE_BM25_HYBRID
            else self._dense_index_params
        )
        client.create_collection(
            collection_name=name,
            schema=self._schema(dim),
            index_params=index_params,
            description="leang embeddings",
        )
        return name

    def _try_ensure_sparse_bm25_index(self, collection_name: str) -> None:
        if not ENABLE_BM25_HYBRID:
            return
        raw = MilvusClientSingleton().get_client()
        try:
            existing = raw.list_indexes(collection_name=collection_name, field_name="sparse")
            if existing:
                return
        except Exception as e:
            logger.debug("list_indexes(sparse): %s", e)

        try:
            p = self._sparse_bm25_index
            idx = raw.prepare_index_params()
            idx.add_index(
                field_name=p["field_name"],
                index_type=p["index_type"],
                metric_type=p["metric_type"],
                params=p["params"],
            )
            raw.create_index(collection_name=collection_name, index_params=idx)
            logger.info("✅ sparse BM25 索引已创建: %s", collection_name)
        except Exception as e:
            logger.warning(
                "sparse BM25 索引创建失败，混合检索将仅用向量通道: %s",
                e,
            )

    def insert_rows(self, rows: List[Dict[str, Any]], collection_name: str | None = None) -> Dict[str, Any]:
        name = collection_name or DEFAULT_COLLECTION
        data: List[Dict[str, Any]] = []
        for row in rows:
            data.append(
                {
                    "text": (row.get("text") or "")[:TEXT_FIELD_MAX],
                    "embedding": row["embedding"],
                    "source_type": (row.get("source_type") or "")[:32],
                    "chunk_index": int(row.get("chunk_index", 0)),
                    "file_name": (row.get("file_name") or "")[:512],
                }
            )
        client = MilvusClientSingleton()
        res = client.insert(collection_name=name, data=data)
        if res.get("success"):
            try:
                client.get_client().flush(collection_name=name)
            except Exception as e:
                logger.warning("Milvus flush 失败，控制台可能延迟显示: %s", e)
            self._try_ensure_sparse_bm25_index(name)
        return res


milvus_service = MilvusService()
