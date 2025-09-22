# core/utils.py
from __future__ import annotations
from typing import Any, Iterable
import re
import json

_CODE_FENCE_RE = re.compile(r"^```[^\n]*\n|\n```$", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+\n")  # trailing spaces on lines

DISPLAY_MAX = 4000  # evita despejar respostas gigantes na UI/console

PREF_KEYS: Iterable[str] = (
    "display", "display_output", "final", "answer", "text",
    "content", "message", "output", "draft"
)

def extract_text_payload(data: Any) -> str:
    """
    Extrai uma string 'útil' de qualquer payload:
      - dict: tenta chaves preferidas (text, answer, etc); se não, compacta json
      - list/tuple: concatena extratos por item
      - outros: str(...)
    """
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, (list, tuple)):
        parts = [extract_text_payload(x) for x in data]
        return "\n\n".join([p for p in parts if p])
    if isinstance(data, dict):
        # tenta chaves preferidas
        for k in PREF_KEYS:
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v
        # tenta detectar único campo string
        str_fields = [v for v in data.values() if isinstance(v, str) and v.strip()]
        if len(str_fields) == 1:
            return str_fields[0]
        # fallback: json compacto limitado
        try:
            j = json.dumps(data, ensure_ascii=False)
            return j[:DISPLAY_MAX]
        except Exception:
            return str(data)[:DISPLAY_MAX]
    # fallback genérico
    return str(data)[:DISPLAY_MAX]

def strip_code_fences(text: str) -> str:
    """Remove cercas de código simples ```...``` no começo/fim do bloco."""
    if not isinstance(text, str):
        return text
    t = text.strip()
    # remove apenas a cerca de início e fim (não mexe em blocos internos)
    t = _CODE_FENCE_RE.sub("", t)
    return t.strip()

def compact_markdown(text: str) -> str:
    """
    Normaliza artefatos comuns para exibição:
      - remove cercas de código externas
      - comprime múltiplas quebras em duas
      - remove espaços à direita
    """
    if not isinstance(text, str):
        return text
    t = strip_code_fences(text)
    # remove espaços à direita em linhas
    t = _WS_RE.sub("\n", t)
    # normaliza múltiplas linhas em até 2
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def truncate_for_display(text: str, max_len: int = DISPLAY_MAX) -> str:
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"

def to_display(primary: Any = None, fallback: Any = None, max_len: int = DISPLAY_MAX) -> str:
    """
    Constrói uma string amigável para UI/log:
      - usa 'primary' se existir, senão tenta extrair de 'fallback'
      - aplica compactação e truncamento seguro
    """
    raw = ""
    if isinstance(primary, str) and primary.strip():
        raw = primary
    else:
        raw = extract_text_payload(fallback)
    disp = compact_markdown(raw)
    return truncate_for_display(disp, max_len=max_len)
