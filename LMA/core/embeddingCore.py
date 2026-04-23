from LMA.constants import CHUNK_OVERLAP, CHUNK_SIZE, DEFAULT_COLLECTION
from LMA.ai.embedding.leangState import LeangState
from LMA.service import get_embedding_service, get_milvus_service, get_text_service
from LMA.service.base import service_logger

logger = service_logger


class LeangEmbeddingCore:
    text_service = get_text_service()
    embedding_service = get_embedding_service()
    milvus_service = get_milvus_service()

    def run(self, state: LeangState) -> LeangState:
        text = self.text_service.load_text(state.file_info.file_path, state.api_params.source_kind)
        if not text or not text.strip():
            state.embedding_result.message = "无可用文本内容"
            return state

        size = state.api_params.chunk_size or CHUNK_SIZE
        overlap = (
            state.api_params.chunk_overlap
            if state.api_params.chunk_overlap is not None
            else CHUNK_OVERLAP
        )
        chunks = self.text_service.split_text(
            text, state.api_params.chunk_strategy, size, overlap
        )
        if not chunks:
            state.embedding_result.message = "分块后为空"
            return state

        vectors = self.embedding_service.embedding_texts(chunks)
        if len(vectors) != len(chunks):
            state.embedding_result.message = "embedding 数量与分块不一致"
            return state

        collection_name = self.milvus_service.ensure_collection(
            state.api_params.collection_name or DEFAULT_COLLECTION
        )
        rows = []
        for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
            rows.append(
                {
                    "text": chunk,
                    "embedding": vec,
                    "source_type": state.api_params.source_kind.value,
                    "chunk_index": idx,
                    "file_name": state.file_basename,
                }
            )
        insert_result = self.milvus_service.insert_rows(rows, collection_name=collection_name)
        if insert_result.get("success"):
            state.embedding_result.inserted = int(insert_result.get("insert_count", 0))
            state.embedding_result.collection_name = collection_name
            state.embedding_result.message = "ok"
        else:
            state.embedding_result.collection_name = collection_name
            state.embedding_result.message = insert_result.get("error", "写入 Milvus 失败")
        return state
