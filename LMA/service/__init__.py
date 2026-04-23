from LMA.service.embeddingService import embedding_service
from LMA.service.milvusService import milvus_service
from LMA.service.retrievalService import retrieval_service
from LMA.service.textService import text_service


def get_text_service():
    return text_service


def get_embedding_service():
    return embedding_service


def get_milvus_service():
    return milvus_service


def get_retrieval_service():
    return retrieval_service
