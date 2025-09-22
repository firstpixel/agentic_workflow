from __future__ import annotations
from typing import Any, Dict, Optional, List, Protocol
import os, requests, re

from src.core.agent import BaseAgent, AgentConfig, load_prompt_text, SafeDict
from src.core.types import Message, Result


class LLMCallable(Protocol):
    def __call__(self, prompt: str, **kwargs) -> str: ...


# ---------- Parsers de Markdown ----------

# Captura a seção "### REWRITTEN QUERY" até o próximo heading "### ..."
_REWRITTEN = re.compile(
    r"^###\s*REWRITTEN\s+QUERY\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL
)
# Captura rationale em bullets (opcional)
_RATIONALE = re.compile(
    r"^###\s*RATIONALE\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL
)

def _extract_rewritten_query(md: str) -> str:
    m = _REWRITTEN.search(md or "")
    if not m:
        return ""
    # pega somente a primeira linha “útil”
    body = (m.group("body") or "").strip()
    # remove bullets se houver
    lines = [ln.strip(" -•\t") for ln in body.splitlines() if ln.strip()]
    return lines[0] if lines else ""

def _extract_rationale(md: str) -> List[str]:
    m = _RATIONALE.search(md or "")
    if not m:
        return []
    body = (m.group("body") or "").strip()
    bullets = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        s = s.lstrip("-• \t")
        if s:
            bullets.append(s)
    return bullets


# ---------- QueryRewriter Agent ----------

class QueryRewriterAgent(BaseAgent):
    """
    Reescreve a query usando prompt em Markdown:
      - Requer model_config["prompt_file"] apontando para prompts/query_rewriter.md
      - Usa Ollama (ou um llm_fn injetado) para gerar Markdown
      - Faz parsing do Markdown e retorna:
          output = {"query": <rewritten>, "rationale": [...], "md": <raw>}
    Entrada esperada: Message.data com "question" OU "query".
    Opcional: "hints_md" (string) para enriquecer o prompt.
    """

    def __init__(self, config: AgentConfig, llm_fn: Optional[LLMCallable] = None):
        super().__init__(config)
        self.llm_fn = llm_fn or self._default_ollama

    # ---- default: Ollama /api/chat ----
    def _default_ollama(self, prompt: str, **kwargs) -> str:
        mc = self.config.model_config or {}
        model = mc.get("model", os.getenv("OLLAMA_MODEL", "llama3"))
        options = mc.get("options", {})
        timeout = float(mc.get("timeout_sec", 120.0))
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

        url = f"{host}/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role":"system","content":"You are a helpful assistant."},
                {"role":"user","content": prompt}
            ],
            "stream": False
        }
        if isinstance(options, dict) and options:
            payload["options"] = options

        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        msg = (data or {}).get("message") or {}
        content = msg.get("content")
        if content:
            return content

        # fallback para /api/generate
        gen_url = f"{host}/api/generate"
        gen_payload = {"model": model, "prompt": prompt, "stream": False}
        if isinstance(options, dict) and options:
            gen_payload["options"] = options
        r2 = requests.post(gen_url, json=gen_payload, timeout=timeout)
        r2.raise_for_status()
        d2 = r2.json()
        return (d2 or {}).get("response", "") or ""

    def _build_prompt(self, message: Message) -> str:
        mc = self.config.model_config or {}
        prompt_file = mc.get("prompt_file")
        if not prompt_file:
            raise ValueError("QueryRewriterAgent: model_config['prompt_file'] is required (e.g., 'query_rewriter.md').")

        # question/hints
        d = message.data if isinstance(message.data, dict) else {}
        question = d.get("question") or d.get("query") or str(message.data)
        hints_md = d.get("hints_md") or d.get("contexts_md") or ""

        tmpl = load_prompt_text(prompt_file)
        if not tmpl:
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

        return tmpl.format_map(SafeDict({"question": question, "hints_md": hints_md}))

    def run(self, message: Message) -> Result:
        prompt = self._build_prompt(message)
        md = self.llm_fn(prompt, **(self.config.model_config or {}))

        rewritten = _extract_rewritten_query(md)
        rationale = _extract_rationale(md)

        if not rewritten:
            # se o LLM não respondeu no formato correto, devolve o original (com nota)
            original = ""
            if isinstance(message.data, dict):
                original = message.data.get("question") or message.data.get("query") or ""
            rewritten = original or ""
            disp = "✏️ Rewriter: fallback (format mismatch)"
        else:
            disp = f"✏️ Rewriter → {rewritten[:80]}"

        out = {"query": rewritten, "rationale": rationale, "md": md}
        return Result.ok(output=out, display_output=disp)
