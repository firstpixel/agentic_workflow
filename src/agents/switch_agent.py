from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import json
import re

from src.core.agent import BaseAgent, AgentConfig, LLMAgent
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


def _parse_markdown_response(response: str) -> Optional[Dict[str, Any]]:
    """
    Parse markdown-formatted response from LLM instead of JSON.
    Expected format (flexible):
    ## Route: [route_name] OR ## Route\n[route_name]
    ## Confidence: [0.0-1.0] OR ## Confidence\n[0.0-1.0]
    ## Reasons: [explanation] OR ## Reasons\n[explanation]
    """
    if not response:
        return None
    
    result = {}
    
    # Extract route - handle both same-line and next-line formats
    route_match = re.search(r"##\s*Route\s*[:：]?\s*(.+?)(?=\n|$)", response, re.IGNORECASE)
    if not route_match:
        # Try multi-line format: ## Route\nActualValue
        route_match = re.search(r"##\s*Route\s*[:：]?\s*\n\s*(.+?)(?=\n|$)", response, re.IGNORECASE)
    if route_match:
        result["route"] = route_match.group(1).strip()
    
    # Extract confidence - handle both formats
    conf_match = re.search(r"##\s*Confidence\s*[:：]?\s*([\d.]+)", response, re.IGNORECASE)
    if not conf_match:
        # Try multi-line format: ## Confidence\n0.8
        conf_match = re.search(r"##\s*Confidence\s*[:：]?\s*\n\s*([\d.]+)", response, re.IGNORECASE)
    if conf_match:
        try:
            result["confidence"] = float(conf_match.group(1))
        except ValueError:
            result["confidence"] = 0.0
    else:
        result["confidence"] = 0.0
    
    # Extract reasons - handle both formats
    reasons_match = re.search(r"##\s*Reasons?\s*[:：]?\s*(.+?)(?=##|$)", response, re.IGNORECASE | re.DOTALL)
    if not reasons_match:
        # Try multi-line format: ## Reasons\nActual explanation
        reasons_match = re.search(r"##\s*Reasons?\s*[:：]?\s*\n\s*(.+?)(?=##|$)", response, re.IGNORECASE | re.DOTALL)
    if reasons_match:
        result["reasons"] = reasons_match.group(1).strip()
    else:
        result["reasons"] = ""
    
    return result if "route" in result else None


class SwitchAgent(BaseAgent):
    """
    Hybrid router:
    - Mode 'keywords': uses keyword matching per route.
    - Mode 'llm': asks an LLM to choose the best route (with confidence).
    - Mode 'hybrid' (default): tries LLM first; if confidence < threshold, falls back to 'keywords'.

    Configuration via AgentConfig.model_config:
    {
      "mode": "hybrid" | "llm" | "keywords",
      "confidence_threshold": 0.55,
      "routes": {
         "Billing":  { "keywords": ["bill", "invoice"], "description": "Billing and payments" },
         "Support":  { "keywords": ["error", "failure", "bug"], "description": "Technical support" },
         "Sales":    { "keywords": ["price", "plan", "license"], "description": "Commercial" }
      },
      "default": "Support"
    }

    LLM:
      - Injete via __init__(..., llm_fn=callable) se quiser usar Ollama/OpenAI.
      - Caso não fornecido, o LLM vira um stub que devolve a primeira rota (apenas para dev).
    """

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        # Create internal LLMAgent for consistent Ollama integration
        self.llm_agent = LLMAgent(config)

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
        prompt_file = mc.get("prompt_file") or "switch_agent.md"

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
            "confidence_threshold": conf_thr,
            "prompt_file": prompt_file
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
        Builds a classification prompt and requests an LLM markdown output:
        ## Route: [route_name]
        ## Confidence: [0.0-1.0]  
        ## Reasons: [brief explanation]
        """
        options = []
        for label, spec in cfg["routes"].items():
            options.append({
                "label": label,
                "description": spec.get("description", "") or "",
                "keywords": spec.get("keywords", []) or []
            })

        # Build user prompt with routing options context
        user_prompt = f"""Text to route: {text}

Available routes:
{json.dumps(options, ensure_ascii=False, indent=2)}

Please analyze this text and choose the best route."""

        try:
            # Create a message for new LLMAgent interface
            user_message = Message(data={"user_prompt": user_prompt})
            
            # Use LLMAgent for consistent Ollama integration
            llm_result = self.llm_agent.run(user_message)
            
            if not llm_result.success:
                return None, 0.0, {"llm_error": f"LLM call failed: {llm_result.output}"}
                
            llm_raw = llm_result.output.get("text", "")
        except Exception as e:
            # if LLM unavailable, return None to fall back
            return None, 0.0, {"llm_error": str(e)}

        # Parse markdown format
        parsed = _parse_markdown_response(llm_raw or "")
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
