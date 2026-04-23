from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from admin.model_pool import model_pool
from Base import default_qwen_llm
from Base.Ai.base import SystemMessages, UserMessages
from LMA.constants import DEFAULT_COLLECTION, sanitize_collection_name
from LMA.prompt.qaPrompt import LEANG_RAG_SYSTEM, build_rag_user_message
from LMA.service import get_retrieval_service
from LMA.service.base import service_logger
from LMA.service.llmMemoryHelper import fetch_recent_memory_block, persist_rag_turn

logger = service_logger


def _chunks_to_context(chunks: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    parts: List[str] = []
    used = 0
    for i, c in enumerate(chunks, 1):
        fn = c.get("file_name") or "unknown"
        txt = (c.get("text") or "").strip()
        if not txt:
            continue
        block = f"[{i}] 来源: {fn}\n{txt}\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


class LeangQACore:
    retrieval = get_retrieval_service()

    def ask(
        self,
        question: str,
        *,
        collection_name: Optional[str] = None,
        top_k: int = 5,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        memory_turns: int = 5,
        preferred_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        t0 = time.time()
        coll = sanitize_collection_name(collection_name) or DEFAULT_COLLECTION
        q = (question or "").strip()
        if not q:
            return {"answer": "", "sources": [], "collection": coll, "error": "问题为空"}

        mem_block = ""
        if session_id and memory_turns > 0:
            mem_block = fetch_recent_memory_block(session_id, memory_turns)

        chunks = self.retrieval.retrieve(q, collection_name=coll, top_k=top_k)
        context = _chunks_to_context(chunks)

        user_content = build_rag_user_message(context, q)
        if mem_block:
            user_content = f"{mem_block}\n\n{user_content}"

        messages = [
            SystemMessages(LEANG_RAG_SYSTEM),
            UserMessages(user_content),
        ]
        try:
            if preferred_model:
                raw_msgs = [
                    {"role": "system", "content": LEANG_RAG_SYSTEM},
                    {"role": "user", "content": user_content},
                ]
                answer = model_pool.call_llm(
                    raw_msgs, temperature=0.3, max_tokens=4096,
                    timeout=120, _log_module="lma",
                    preferred_model=preferred_model,
                )
            else:
                answer = default_qwen_llm.chat(messages)
        except Exception as e:
            logger.error("LLM 生成失败: %s", e)
            return {
                "answer": "",
                "sources": chunks,
                "collection": coll,
                "error": str(e),
            }

        sources = [
            {
                "file_name": c.get("file_name"),
                "chunk_index": c.get("chunk_index"),
                "preview": (c.get("text") or "")[:200],
            }
            for c in chunks
        ]
        latency_ms = int((time.time() - t0) * 1000)
        if session_id:
            persist_rag_turn(
                session_id,
                q,
                user_id=user_id,
                assistant_response=answer or "",
                sources=sources,
                collection_name=coll,
                latency_ms=latency_ms,
            )
        return {
            "answer": answer or "",
            "sources": sources,
            "collection": coll,
            "error": None,
        }
