from typing import List

from Base import default_qwen_llm
from Base.Config.setting import settings
from LMA.service.base import service_logger

logger = service_logger


class EmbeddingService:
    def embedding_texts(self, texts: list[str], dimensions: int | None = None) -> List[List[float]]:
        if not texts:
            return []
        dim = dimensions if dimensions is not None else (settings.milvus.vector_dim or 1024)
        vectors: List[List[float]] = []
        for text in texts:
            if not text:
                continue
            raw = default_qwen_llm.embedding(text, dimensions=dim)
            if not raw:
                logger.warning("空 embedding 返回，跳过 chunk")
                continue
            if isinstance(raw[0], (int, float)):
                vectors.append([float(x) for x in raw])
            else:
                vectors.append(raw[0])
        return vectors


embedding_service = EmbeddingService()
