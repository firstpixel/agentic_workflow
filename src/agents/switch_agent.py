from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable, Tuple
import json
import re

from src.core.agent import BaseAgent, AgentConfig
from src.core.types import Message, Result


def _extract_text(payload: Any) -> str:
    """
    Extrai texto de 'payload' com heurística robusta.
    Aceita dicts do tipo {"text": "..."} / {"query": "..."} / {"prompt": "..."}.
    Caso contrário, converte para string.
    """
    if isinstance(payload, dict):
        for k in ("text", "query", "prompt", "input", "message"):
            if k in payload and isinstance(payload[k], str):
                return payload[k]
    if isinstance(payload, list):
        # concatena textos se vier de um join/fan-in
        return "\n".join(_extract_text(x) for x in payload)
    return str(payload)


def _score_keywords(text: str, keywords: List[str]) -> int:
    """
    Scoring simples: soma 1 por keyword presente (case-insensitive).
    Pode ser substituído por TF-IDF, BM25, etc. no futuro.
    """
    t = text.casefold()
    score = 0
    for kw in keywords:
        if kw and kw.casefold() in t:
            score += 1
    return score


def _safe_json_parse(s: str) -> Optional[Dict[str, Any]]:
    """
    Tenta parsear JSON de forma resiliente. Se falhar, tenta extrair um bloco {...}.
    """
    s = s.strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    # tenta capturar o maior bloco JSON
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


class SwitchAgent(BaseAgent):
    """
    Roteador híbrido:
    - Modo 'keywords': usa correspondência de palavras-chave por rota.
    - Modo 'llm': pergunta a um LLM qual rota escolher (com confiança).
    - Modo 'hybrid' (padrão): tenta LLM; se confiança < threshold, cai para 'keywords'.

    Configuração via AgentConfig.model_config:
    {
      "mode": "hybrid" | "llm" | "keywords",
      "confidence_threshold": 0.55,
      "routes": {
         "Billing":  { "keywords": ["boleto", "fatura"], "description": "Cobrança e pagamentos" },
         "Support":  { "keywords": ["erro", "falha", "bug"], "description": "Suporte técnico" },
         "Sales":    { "keywords": ["preço", "plano", "licença"], "description": "Comercial" }
      },
      "default": "Support"
    }

    LLM:
      - Injete via __init__(..., llm_fn=callable) se quiser usar Ollama/OpenAI.
      - Caso não fornecido, o LLM vira um stub que devolve a primeira rota (apenas para dev).
    """

    def __init__(self, config: AgentConfig, llm_fn: Optional[Callable[..., str]] = None):
        super().__init__(config)
        self.llm_fn = llm_fn or self._stub_llm

    # ------------------------ API principal ----------------------------

    def run(self, message: Message) -> Result:
        cfg = self._read_config()
        user_text = _extract_text(message.data)

        # 1) Decide modo
        mode = cfg["mode"]
        chosen: Optional[str] = None
        used_mode = mode
        confidence = 0.0
        details: Dict[str, Any] = {}

        if mode in ("llm", "hybrid"):
            chosen, confidence, details = self._route_with_llm(user_text, cfg)
            if chosen and chosen in cfg["routes"] and confidence >= cfg["confidence_threshold"]:
                return self._emit(chosen, used_mode, confidence, details)

            # fallback para keywords
            if mode == "hybrid":
                used_mode = "keywords"

        if mode == "keywords" or used_mode == "keywords":
            chosen, kw_scores = self._route_with_keywords(user_text, cfg)
            details.update({"keyword_scores": kw_scores})
            if not chosen:
                chosen = cfg["default"]

        return self._emit(chosen, used_mode, confidence, details)

    # ------------------------ Métodos internos -------------------------

    def _emit(self, route: Optional[str], mode_used: str,
              confidence: float, details: Dict[str, Any]) -> Result:
        route = route or ""
        disp = f"🔀 Routed to: {route}  (mode={mode_used}, conf={confidence:.2f})"
        out = {"route": route, "mode": mode_used, "confidence": confidence, "details": details}
        # crucial: usar control.goto para que o WorkflowManager pule para o nó escolhido
        return Result.ok(output=out, display_output=disp, control={"goto": route})

    def _read_config(self) -> Dict[str, Any]:
        mc = self.config.model_config or {}
        routes = mc.get("routes", {})
        if not isinstance(routes, dict) or not routes:
            raise ValueError("SwitchAgent: 'routes' (dict) é obrigatório em model_config")

        default_route = mc.get("default", next(iter(routes.keys())))
        mode = (mc.get("mode") or "hybrid").lower()
        if mode not in ("hybrid", "llm", "keywords"):
            mode = "hybrid"

        conf_thr = float(mc.get("confidence_threshold", 0.55))

        # normaliza keywords
        norm_routes: Dict[str, Dict[str, Any]] = {}
        for label, spec in routes.items():
            kws = []
            desc = ""
            if isinstance(spec, dict):
                kws = spec.get("keywords", []) or []
                desc = spec.get("description", "") or ""
            elif isinstance(spec, list):
                kws = spec
            norm_routes[label] = {"keywords": kws, "description": desc}

        return {
            "routes": norm_routes,
            "default": default_route,
            "mode": mode,
            "confidence_threshold": conf_thr
        }

    def _route_with_keywords(self, text: str, cfg: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, int]]:
        scores: Dict[str, int] = {}
        for label, spec in cfg["routes"].items():
            kws = spec.get("keywords", []) or []
            scores[label] = _score_keywords(text, kws)
        # escolhe o maior score; em empate, prioriza ordem de definição
        best = None
        best_score = -1
        for label in cfg["routes"].keys():
            sc = scores[label]
            if sc > best_score:
                best = label
                best_score = sc
        if best_score <= 0:
            return None, scores
        return best, scores

    def _route_with_llm(self, text: str, cfg: Dict[str, Any]) -> Tuple[Optional[str], float, Dict[str, Any]]:
        """
        Constrói um prompt de classificação e solicita ao LLM uma saída JSON:
        { "route": "<UMA_DAS_OPCOES>", "confidence": 0.0..1.0, "reasons": "curto" }
        """
        options = []
        for label, spec in cfg["routes"].items():
            options.append({
                "label": label,
                "description": spec.get("description", "") or "",
                "keywords": spec.get("keywords", []) or []
            })

        # Prompt enxuto, sem raciocínio oculto; pedimos resposta JSON direta.
        prompt = (
            "You are a strict router that selects exactly ONE route for the user request.\n"
            "Pick the best matching option among the provided routes.\n"
            "Return ONLY a compact JSON object with: route (string), confidence (0..1), reasons (short string).\n\n"
            f"USER_REQUEST:\n{text}\n\n"
            f"ROUTE_OPTIONS:\n{json.dumps(options, ensure_ascii=False)}\n\n"
            'RESPONSE_FORMAT:\n{"route": "LABEL_FROM_OPTIONS", "confidence": 0.0, "reasons": "short"}'
        )

        try:
            llm_raw = self.llm_fn(prompt, **self.config.model_config)
        except Exception as e:
            # se LLM indisponível, retorna None para cair no fallback
            return None, 0.0, {"llm_error": str(e)}

        parsed = _safe_json_parse(llm_raw or "")
        if not parsed or "route" not in parsed:
            return None, 0.0, {"llm_raw": llm_raw, "parse": "failed"}

        route = parsed.get("route")
        conf = parsed.get("confidence", 0.0)
        try:
            conf = float(conf)
        except Exception:
            conf = 0.0

        reasons = parsed.get("reasons", "")
        details = {"llm_raw": llm_raw, "parsed": {"route": route, "confidence": conf, "reasons": reasons}}
        return route, conf, details

    # ------------------------ LLM STUB --------------------------------

    def _stub_llm(self, prompt: str, **kwargs) -> str:
        """
        Stub para desenvolvimento sem LLM conectado: sempre retorna a PRIMEIRA rota.
        Produz JSON válido para as funções de parse funcionarem.
        """
        routes = kwargs.get("routes") or kwargs.get("model_config", {}).get("routes")
        first_label = ""
        if isinstance(routes, dict) and routes:
            first_label = next(iter(routes.keys()))
        return json.dumps({"route": first_label, "confidence": 0.01, "reasons": "stub"})
