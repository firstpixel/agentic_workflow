from __future__ import annotations
from typing import List, Dict, Any
from .mongo_stm import MongoSTM
from .qdrant_store import QdrantVectorStore

class MemoryManager:
    def __init__(self, stm: MongoSTM, ltm: QdrantVectorStore):
        self.stm = stm
        self.ltm = ltm

    # STM
    def stm_add(self, session_id: str, role: str, content: str, meta: Dict[str,Any]|None=None):
        self.stm.add(session_id, role, content, meta)

    def stm_recent(self, session_id: str, limit: int=10) -> List[Dict[str,Any]]:
        return self.stm.recent(session_id, limit)

    # LTM / RAG
    def index_document(self, text: str, meta: Dict[str,Any]|None=None):
        self.ltm.index_texts([{"text": text, "meta": meta or {}}])

    def search_context(self, query: str, top_k: int=5) -> List[Dict[str,Any]]:
        return self.ltm.search(query, top_k=top_k)
