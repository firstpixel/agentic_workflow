from __future__ import annotations
from typing import Dict, Any, Tuple, List
import re

EMAIL_RE   = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE   = re.compile(r"(?:(?:\+?\d{1,3})?[\s\-\.]?)?(?:\(?\d{2,4}\)?[\s\-\.]?)?\d{3,4}[\s\-\.]?\d{3,4}")
CARD_RE    = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
# Ajuste ou adicione padrões conforme seu domínio/região

def redact_pii(text: str) -> Tuple[str, Dict[str, int], List[str]]:
    """
    Redação determinística de PII comum.
    Retorna: (texto_redigido, contagens, lista_markdown_pii)
    """
    counts = {"email": 0, "phone": 0, "card": 0}
    md_lines: List[str] = []

    def repl_email(m):
        counts["email"] += 1
        md_lines.append(f"- EMAIL: `{m.group(0)}`")
        return "[[REDACTED:EMAIL]]"

    def repl_phone(m):
        s = m.group(0)
        # Evita redigir sequências muito curtas (ruído)
        if len(re.sub(r"\D", "", s)) < 8:
            return s
        counts["phone"] += 1
        md_lines.append(f"- PHONE: `{s}`")
        return "[[REDACTED:PHONE]]"

    def repl_card(m):
        s = m.group(0)
        digits = re.sub(r"\D", "", s)
        if len(digits) < 13:
            return s
        counts["card"] += 1
        md_lines.append(f"- CARD: `{s}`")
        return "[[REDACTED:CARD]]"

    red = EMAIL_RE.sub(repl_email, text)
    red = CARD_RE.sub(repl_card, red)
    red = PHONE_RE.sub(repl_phone, red)

    return red, counts, md_lines


# -------- Parsers para o Markdown do moderador --------

import re as _re

_DECISION = _re.compile(r"^###\s*DECISION\s*\n([^\n]+)", _re.IGNORECASE | _re.MULTILINE)
_REASONS  = _re.compile(r"^###\s*REASONS\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)", _re.IGNORECASE | _re.MULTILINE | _re.DOTALL)

def parse_moderation_md(md: str) -> Dict[str, Any]:
    dec = "ALLOW"
    m = _DECISION.search(md or "")
    if m:
        dec = m.group(1).strip().upper()

    reasons: List[str] = []
    r = _REASONS.search(md or "")
    if r:
        body = (r.group("body") or "").strip()
        for ln in body.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            ln = ln.lstrip("-• \t")
            if ln:
                reasons.append(ln)

    if dec not in ("ALLOW", "REDACT", "BLOCK"):
        dec = "ALLOW"

    return {"decision": dec, "reasons": reasons}
