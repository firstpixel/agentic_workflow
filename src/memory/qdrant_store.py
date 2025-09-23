from __future__ import annotations
from typing import List, Dict, Any, Optional
import os, uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from src.config.settings import get_settings

from .embeddings import OllamaEmbeddings

class QdrantVectorStore:
    def __init__(self, url: str | None = None, collection: str = "agentic_docs",
                 embed_model: str | None = None):
        if url is None:
            settings = get_settings()
            self.url = settings.qdrant_url
        else:
            self.url = url
        self.collection = collection
        self.client = QdrantClient(url=self.url)
        self.embedder = OllamaEmbeddings(model=embed_model)

    def _ensure_collection(self, dim: int):
        if self.collection not in [c.name for c in self.client.get_collections().collections]:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
            )

    def index_texts(self, items: List[Dict[str,Any]]):
        """
        items: [{"id": "...", "text": "...", "meta": {...}}, ...]
        """
        texts=[it["text"] for it in items]
        vecs=self.embedder.embed(texts)
        if not vecs: return
        dim=len(vecs[0])
        self._ensure_collection(dim)
        points=[]
        for it,vec in zip(items,vecs):
            pid=it.get("id") or str(uuid.uuid4())
            points.append(PointStruct(id=pid, vector=vec, payload={"text": it["text"], "meta": it.get("meta",{})}))
        self.client.upsert(collection_name=self.collection, points=points)

    def search(self, query_text: str, top_k: int = 5, filter_: Optional[Any] = None) -> List[Dict[str,Any]]:
        qvec=self.embedder.embed([query_text])[0]
        # Use the newer query_points API
        res=self.client.query_points(collection_name=self.collection, query=qvec, limit=top_k, query_filter=filter_)
        out=[]
        for r in res.points:
            payload=r.payload or {}
            out.append({"text": payload.get("text",""), "score": float(r.score), "meta": payload.get("meta",{})})
        return out
