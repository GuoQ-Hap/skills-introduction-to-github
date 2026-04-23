from pathlib import Path

from LMA.ai.embedding.leangState import (
    ChunkStrategy,
    LeangApiParams,
    LeangState,
    SourceKind,
)
from LMA.constants import sanitize_collection_name
from LMA.core.embeddingCore import LeangEmbeddingCore


def ingest_file(
    file_path: str | Path,
    kind: SourceKind,
    *,
    collection_name: str | None = None,
    chunk_strategy: ChunkStrategy = ChunkStrategy.FIXED,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> dict:
    state = LeangState(
        api_params=LeangApiParams(
            source_kind=kind,
            collection_name=sanitize_collection_name(collection_name),
            chunk_strategy=chunk_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    )
    state.file_info.file_path = str(file_path)
    state.file_info.file_name = Path(file_path).name
    result = LeangEmbeddingCore().run(state)
    ok = result.embedding_result.inserted > 0
    return {
        "ok": ok,
        "inserted": result.embedding_result.inserted,
        "message": result.embedding_result.message,
    }
