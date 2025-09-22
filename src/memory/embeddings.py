from __future__ import annotations
from typing import List
import os, requests

class OllamaEmbeddings:
    """
    Usa /api/embeddings do Ollama. Defina OLLAMA_EMBED_MODEL (ex.: 'nomic-embed-text').
    """
    def __init__(self, model: str | None = None, host: str | None = None, timeout: float = 60.0):
        self.model = model or os.getenv("OLLAMA_EMBED_MODEL","nomic-embed-text")
        self.host = (host or os.getenv("OLLAMA_HOST","http://localhost:11434")).rstrip("/")
        self.timeout = timeout

    def embed(self, texts: List[str]) -> List[List[float]]:
        out=[]
        url=f"{self.host}/api/embeddings"
        for t in texts:
            resp=requests.post(url,json={"model":self.model,"prompt":t},timeout=self.timeout)
            resp.raise_for_status()
            data=resp.json()
            vec=data.get("embedding",[])
            out.append(vec)
        return out
