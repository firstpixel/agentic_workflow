from __future__ import annotations
from typing import Any, Dict, List
from src.core.agent import BaseAgent, AgentConfig
from src.core.types import Message, Result
from src.memory.memory_manager import MemoryManager

def _md_context(snips: List[Dict[str,Any]]) -> str:
    lines=[]
    for i,s in enumerate(snips, start=1):
        meta=s.get("meta",{})
        tag=meta.get("tag",f"C{i}")
        lines.append(f"#### [{tag}]")
        lines.append(s.get("text","").strip())
        lines.append("")
    return "\n".join(lines).strip()

class RAGRetrieverAgent(BaseAgent):
    """
    Recupera contextos do Qdrant (via MemoryManager) e devolve markdown pronto.
    model_config: {"top_k": int}
    """
    def __init__(self, config: AgentConfig, memory: MemoryManager):
        super().__init__(config)
        self.memory = memory

    def run(self, message: Message) -> Result:
        mc=self.config.model_config or {}
        top_k=int(mc.get("top_k",5))
        query = message.get("query") or message.get("text") or str(message.data)
        snips=self.memory.search_context(query, top_k=top_k)
        ctx_md=_md_context(snips)
        disp=f"📚 RAG: retrieved {len(snips)} snippets"
        
        # Preserve the original question for downstream agents
        original_question = None
        if isinstance(message.data, dict):
            # Try to find the original question from various possible keys
            original_question = (message.data.get("question") or 
                               message.data.get("query") or 
                               message.meta.get("root", {}).get("question") if isinstance(message.meta.get("root"), dict) else None)
        
        output = {"contexts": snips, "contexts_md": ctx_md}
        if original_question:
            output["question"] = original_question
            
        return Result.ok(output=output, display_output=disp)
