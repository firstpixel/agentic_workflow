"""
ALL AGENTS - Comprehensive Collection of Agentic Workflow Patterns

This file contains all agent implementations from the agentic workflow system,
providing a complete reference for AI agent patterns including:

1. EchoAgent - Simple echo functionality
2. SwitchAgent - Hybrid routing (keyword + LLM)
3. CriticAgent - Content evaluation and feedback
4. FanOutAgent - Parallel execution branching
5. JoinAgent - Result aggregation
6. RAGRetrieverAgent - Retrieval Augmented Generation
7. QueryRewriterAgent - Query optimization for retrieval
8. GuardrailsAgent - PII redaction and content moderation
9. ApprovalGateAgent - Human-in-the-loop approval workflows

Each agent demonstrates different patterns and can be used as building blocks
for complex agentic workflows.

Usage:
    from all_agents import SwitchAgent, CriticAgent, etc.
    
Dependencies:
    - src.core.agent (BaseAgent, AgentConfig, LLMAgent, etc.)
    - src.core.types (Message, Result)
    - src.memory.memory_manager (MemoryManager)
    - src.guardrails.guardrails (PII functions)
"""

from __future__ import annotations
import uuid
import json
import re
import os
import requests
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Callable, Protocol

from src.core.agent import BaseAgent, AgentConfig, LLMAgent, LLMCallable, load_prompt_text, SafeDict
from src.core.types import Message, Result
from src.memory.memory_manager import MemoryManager
from src.guardrails.guardrails import redact_pii, parse_moderation_md


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _extract_text(payload: Any) -> str:
    """
    Extract text from various payload formats with robust heuristics.
    Accepts dicts like {"text": "..."} / {"query": "..."} / {"prompt": "..."}.
    Otherwise, converts to string.
    """
    if isinstance(payload, dict):
        for k in ("text", "query", "prompt", "input", "message", "content", "draft", "answer", "output"):
            if k in payload and isinstance(payload[k], str):
                return payload[k]
        return json.dumps(payload, ensure_ascii=False)[:8000]
    if isinstance(payload, list):
        # concatenate texts if coming from a join/fan-in
        return "\n".join(_extract_text(x) for x in payload)
    return str(payload)


def _extract_textish(x: Any) -> str:
    """
    Extract reasonable textual representation from join branch items.
    Looks for common keys; otherwise, str(x).
    """
    if isinstance(x, dict):
        for k in ("text", "content", "answer", "output", "echo"):
            v = x.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return str(x)
    return str(x)


def _score_keywords(text: str, keywords: List[str]) -> int:
    """
    Simple scoring: sum 1 per keyword present (case-insensitive).
    Can be replaced by TF-IDF, BM25, etc. in the future.
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
    Expected format:
    ## Route: [route_name]
    ## Confidence: [0.0-1.0]
    ## Reasons: [explanation]
    """
    if not response:
        return None
    
    result = {}
    
    # Extract route
    route_match = re.search(r"##\s*Route\s*[:：]\s*(.+)", response, re.IGNORECASE)
    if route_match:
        result["route"] = route_match.group(1).strip()
    
    # Extract confidence
    conf_match = re.search(r"##\s*Confidence\s*[:：]\s*([\d.]+)", response, re.IGNORECASE)
    if conf_match:
        try:
            result["confidence"] = float(conf_match.group(1))
        except ValueError:
            result["confidence"] = 0.0
    else:
        result["confidence"] = 0.0
    
    # Extract reasons
    reasons_match = re.search(r"##\s*Reasons?\s*[:：]\s*(.+?)(?=##|$)", response, re.IGNORECASE | re.DOTALL)
    if reasons_match:
        result["reasons"] = reasons_match.group(1).strip()
    else:
        result["reasons"] = ""
    
    return result if "route" in result else None


def _md_context(snips: List[Dict[str,Any]]) -> str:
    """Format context snippets as markdown."""
    lines = []
    for i, s in enumerate(snips, start=1):
        meta = s.get("meta", {})
        tag = meta.get("tag", f"C{i}")
        lines.append(f"#### [{tag}]")
        lines.append(s.get("text", "").strip())
        lines.append("")
    return "\n".join(lines).strip()


# =============================================================================
# MARKDOWN PARSERS FOR CRITIC AGENT
# =============================================================================

_MD_DECISION = re.compile(r"^###\s*DECISION\s*\n([^\n]+)", re.IGNORECASE|re.MULTILINE)
_MD_SCORE = re.compile(r"^###\s*SCORE\s*\n([0-9]+(\.[0-9]+)?)", re.IGNORECASE|re.MULTILINE)

def _parse_markdown_critic(md: str) -> Dict[str, Any]:
    """Parse critic agent markdown response."""
    decision = "REVISE"
    m = _MD_DECISION.search(md or "")
    if m:
        decision = m.group(1).strip().upper()
    s = _MD_SCORE.search(md or "")
    score = float(s.group(1)) if s else 0.0
    return {"decision": decision, "score": score, "raw": md}


# =============================================================================
# QUERY REWRITER PARSERS
# =============================================================================

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
    """Extract rewritten query from markdown."""
    m = _REWRITTEN.search(md or "")
    if not m:
        return ""
    # pega somente a primeira linha "útil"
    body = (m.group("body") or "").strip()
    # remove bullets se houver
    lines = [ln.strip(" -•\t") for ln in body.splitlines() if ln.strip()]
    return lines[0] if lines else ""

def _extract_rationale(md: str) -> List[str]:
    """Extract rationale bullets from markdown."""
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


# =============================================================================
# AGENT IMPLEMENTATIONS
# =============================================================================

class EchoAgent(BaseAgent):
    """
    Simple echo agent that returns the input data.
    Useful for testing and debugging workflows.
    
    Configuration: None required
    
    Input: Any data
    Output: {"echo": "echo(<data>)"}
    """
    
    def run(self, message: Message) -> Result:
        text = f"echo({message.data})"
        return Result.ok(output={"echo": text}, display_output=text)


class SwitchAgent(BaseAgent):
    """
    Hybrid router that can use keyword matching, LLM routing, or both.
    
    Modes:
    - 'keywords': uses keyword matching per route
    - 'llm': asks an LLM to choose the best route (with confidence)
    - 'hybrid' (default): tries LLM first; if confidence < threshold, falls back to keywords
    
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
    
    Input: {"text": "user query"}
    Output: {"route": "chosen_route", "mode": "used_mode", "confidence": 0.0-1.0, "details": {...}}
    Control: {"goto": "chosen_route"}
    """

    def __init__(self, config: AgentConfig, llm_fn: LLMCallable):
        super().__init__(config)
        self.llm_fn = llm_fn

    def run(self, message: Message) -> Result:
        cfg = self._read_config()
        user_text = _extract_text(message.data)

        # 1) Decide mode
        mode = cfg["mode"]
        chosen: Optional[str] = None
        used_mode = mode
        confidence = 0.0
        details: Dict[str, Any] = {}

        if mode in ("llm", "hybrid"):
            chosen, confidence, details = self._route_with_llm(user_text, cfg)
            if chosen and chosen in cfg["routes"] and confidence >= cfg["confidence_threshold"]:
                return self._emit(chosen, used_mode, confidence, details)

            # fallback to keywords
            if mode == "hybrid":
                used_mode = "keywords"

        if mode == "keywords" or used_mode == "keywords":
            chosen, kw_scores = self._route_with_keywords(user_text, cfg)
            details.update({"keyword_scores": kw_scores})
            if not chosen:
                chosen = cfg["default"]

        return self._emit(chosen, used_mode, confidence, details)

    def _emit(self, route: Optional[str], mode_used: str,
              confidence: float, details: Dict[str, Any]) -> Result:
        route = route or ""
        disp = f"🔀 Routed to: {route}  (mode={mode_used}, conf={confidence:.2f})"
        out = {"route": route, "mode": mode_used, "confidence": confidence, "details": details}
        # crucial: use control.goto so WorkflowManager jumps to chosen node
        return Result.ok(output=out, display_output=disp, control={"goto": route})

    def _read_config(self) -> Dict[str, Any]:
        mc = self.config.model_config or {}
        routes = mc.get("routes", {})
        if not isinstance(routes, dict) or not routes:
            raise ValueError("SwitchAgent: 'routes' (dict) is required in model_config")

        default_route = mc.get("default", next(iter(routes.keys())))
        mode = (mc.get("mode") or "hybrid").lower()
        if mode not in ("hybrid", "llm", "keywords"):
            mode = "hybrid"

        conf_thr = float(mc.get("confidence_threshold", 0.55))
        prompt_file = mc.get("prompt_file") or "switch_agent.md"

        # normalize keywords
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
        # choose highest score; in tie, prioritize definition order
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
        Builds a classification prompt and requests an LLM markdown output.
        """
        try:
            prompt_file = cfg.get("prompt_file", "switch_agent.md")
            template = load_prompt_text(prompt_file)
            if not template:
                raise FileNotFoundError(f"Missing prompt file: {prompt_file}")

            # build route options
            options_md = []
            for label, spec in cfg["routes"].items():
                desc = spec.get("description", "")
                kws = spec.get("keywords", [])
                kws_str = ", ".join(kws) if kws else "(no keywords)"
                options_md.append(f"- **{label}**: {desc} (keywords: {kws_str})")

            context = SafeDict({
                "user_text": text,
                "options_md": "\n".join(options_md)
            })
            prompt = template.format_map(context)

            # call LLM
            mc = self.config.model_config or {}
            raw = self.llm_fn(prompt, **mc)
            
            # parse markdown response
            parsed = _parse_markdown_response(raw)
            if not parsed:
                return None, 0.0, {"llm_raw": raw, "parse": "failed"}

            route = parsed.get("route", "").strip()
            confidence = float(parsed.get("confidence", 0.0))
            
            return route, confidence, {"llm_raw": raw, "parse": "success", "parsed": parsed}

        except Exception as e:
            return None, 0.0, {"error": str(e), "parse": "failed"}


class CriticAgent(BaseAgent):
    """
    Evaluates content using Markdown format (not JSON). 
    If DECISION=PASS, continues; otherwise, requests repeat.
    
    Configuration via model_config:
    {
      "rubric": ["Clarity", "Adherence", "Correctness"],
      "threshold": 7.5,  # score threshold (0-10)
      "max_iters": 2,    # maximum iterations
      "next_on_pass": "NextNode",  # optional
      "prompt_file": "critic_agent.md"
    }
    
    Input: {"text": "content to evaluate"}
    Output: {"decision": "PASS|REVISE", "score": 8.0, "iteration": 0, "rubric": [...]}
    Control: {"goto": "next_on_pass"} | {"repeat": True} | {}
    """
    
    def __init__(self, config: AgentConfig, llm_fn: LLMCallable):
        super().__init__(config)
        self.llm_fn = llm_fn

    def run(self, message: Message) -> Result:
        mc = self.config.model_config or {}
        rubric = mc.get("rubric") or ["Clearness", "Adherence", "Correctness"]
        threshold = float(mc.get("threshold", 7.5))
        max_iters = int(mc.get("max_iters", 2))
        next_on_pass = mc.get("next_on_pass")
        prompt_file = mc.get("prompt_file") or "critic_agent.md"

        text = _extract_text(message.data)
        iteration = int(message.meta.get("iteration", 0))

        tmpl = load_prompt_text(prompt_file)
        if not tmpl:
            raise FileNotFoundError(f"Missing prompt file: {prompt_file}")
        
        prompt = tmpl.format_map(SafeDict({
            "rubric_json": json.dumps(rubric, ensure_ascii=False),
            "text": text
        }))

        md = self.llm_fn(prompt, **mc)
        parsed = _parse_markdown_critic(md)
        passed = parsed["decision"] == "PASS" and parsed["score"] >= threshold

        disp = f"🧪 Critic(decision={parsed['decision']}, score={parsed['score']:.2f}, iter={iteration})"
        feedback = {
            "decision": parsed["decision"],
            "score": parsed["score"],
            "iteration": iteration,
            "rubric": rubric
        }

        if passed:
            ctrl = {}
            if next_on_pass:
                ctrl["goto"] = next_on_pass
            return Result.ok(output=feedback, display_output=disp, control=ctrl)

        if iteration >= max_iters:
            return Result.ok(output=feedback, display_output=disp + " | max_iters", control={})
        
        return Result.ok(output=feedback, display_output=disp + " | request repeat", control={"repeat": True})


class FanOutAgent(BaseAgent):
    """
    Produces payloads per branch. Does not use LLM or prompt.
    
    Configuration via model_config:
    {
      "branches": ["TechWriter", "BizWriter"]  # downstream node names in graph
    }
    
    Input: Any data
    Output: {"<next_node>": <payload for that node>}
    If no specific payload is provided, replicates input to all branches.
    """
    
    def run(self, message: Message) -> Result:
        cfg = self.config.model_config or {}
        branches: List[str] = cfg.get("branches") or []
        if not branches:
            raise ValueError("FanOutAgent: define model_config['branches'] with branch list")

        # By default, replicate same input to each branch
        out: Dict[str, Any] = {b: message.data for b in branches}
        disp = f"↗️ FanOut -> {', '.join(branches)}"
        return Result.ok(output=out, display_output=disp)


class JoinAgent(BaseAgent):
    """
    Aggregates results from multiple branches. Does not use LLM or prompt.
    
    Expected input: Message.data can be a LIST (when multiple inputs arrived).
    Output: {"text": <readable concatenation of results>}
    
    Configuration: None required
    """
    
    def run(self, message: Message) -> Result:
        data = message.data
        if not isinstance(data, list):
            # degenerate flow (single item arrived). Still return something useful.
            combined = _extract_textish(data)
        else:
            parts = []
            for i, item in enumerate(data, start=1):
                parts.append(f"[Branch {i}]\n{_extract_textish(item)}")
            combined = "\n\n".join(parts)

        disp = f"🔗 Join ({'multi' if isinstance(message.data, list) else 'single'})"
        return Result.ok(output={"text": combined}, display_output=disp)


class RAGRetrieverAgent(BaseAgent):
    """
    Retrieves contexts from Qdrant (via MemoryManager) and returns ready markdown.
    
    Configuration via model_config:
    {
      "top_k": 5  # number of contexts to retrieve
    }
    
    Input: {"query": "search query"} or {"text": "search text"}
    Output: {"contexts": [...], "contexts_md": "markdown", "question": "original_question"}
    """
    
    def __init__(self, config: AgentConfig, memory: MemoryManager):
        super().__init__(config)
        self.memory = memory

    def run(self, message: Message) -> Result:
        mc = self.config.model_config or {}
        top_k = int(mc.get("top_k", 5))
        query = message.get("query") or message.get("text") or str(message.data)
        snips = self.memory.search_context(query, top_k=top_k)
        ctx_md = _md_context(snips)
        disp = f"📚 RAG: retrieved {len(snips)} snippets"
        
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


class QueryRewriterAgent(BaseAgent):
    """
    Rewrites queries using Markdown prompt for better retrieval.
    
    Configuration via model_config:
    {
      "prompt_file": "query_rewriter.md",
      "model": "llama3",
      "options": {"temperature": 0.1}
    }
    
    Expected input: Message.data with "question" OR "query".
    Optional: "hints_md" (string) to enrich the prompt.
    
    Output: {"query": <rewritten>, "rationale": [...], "md": <raw>}
    """

    def __init__(self, config: AgentConfig, llm_fn: Optional[LLMCallable] = None):
        super().__init__(config)
        self.llm_fn = llm_fn or self._default_ollama

    def _default_ollama(self, prompt: str, **kwargs) -> str:
        """Default Ollama implementation."""
        mc = self.config.model_config or {}
        model = mc.get("model", os.getenv("OLLAMA_MODEL", "llama3"))
        options = mc.get("options", {})
        timeout = float(mc.get("timeout_sec", 120.0))
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

        url = f"{host}/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
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

        # fallback to /api/generate
        gen_url = f"{host}/api/generate"
        gen_payload = {"model": model, "prompt": prompt, "stream": False}
        if isinstance(options, dict) and options:
            gen_payload["options"] = options

        resp2 = requests.post(gen_url, json=gen_payload, timeout=timeout)
        resp2.raise_for_status()
        data2 = resp2.json()
        return (data2 or {}).get("response", "")

    def run(self, message: Message) -> Result:
        mc = self.config.model_config or {}
        prompt_file = mc.get("prompt_file") or "query_rewriter.md"

        # Extract question and hints
        d = message.data if isinstance(message.data, dict) else {}
        question = d.get("question") or d.get("query") or str(message.data)
        hints_md = d.get("hints_md", "")

        # Load and format prompt
        template = load_prompt_text(prompt_file)
        if not template:
            raise FileNotFoundError(f"Missing prompt file: {prompt_file}")

        context = SafeDict({"question": question, "hints_md": hints_md})
        prompt = template.format_map(context)

        # Call LLM
        md = self.llm_fn(prompt, **mc)

        # Parse markdown response
        rewritten = _extract_rewritten_query(md)
        rationale = _extract_rationale(md)

        disp = f"✏️ Rewriter → {rewritten[:50]}{'...' if len(rewritten) > 50 else ''}"
        
        # Preserve original question for downstream
        output = {
            "query": rewritten,
            "rationale": rationale,
            "md": md
        }
        if question:
            output["question"] = question

        return Result.ok(output=output, display_output=disp)


class GuardrailsAgent(BaseAgent):
    """
    Applies PII redaction (deterministic) and moderation via LLM (Markdown).
    
    Configuration via model_config:
    {
      "pii_redact": true,
      "moderation_mode": "hybrid",           # "deterministic" | "llm" | "hybrid"
      "moderation_prompt_file": "moderation.md",
      "model": "llama3",
      "options": {"temperature": 0.0}
    }
    
    Input: {"text": "content to check"}
    Output: {"decision": "ALLOW|REDACT|BLOCK", "text": <sanitized>, "pii": {...}, "reasons": [...], "md": <raw>}
    Control: {"halt": True} if decision == "BLOCK"
    """
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)

    def _extract_text(self, data: Any) -> str:
        if isinstance(data, dict):
            for k in ("text", "prompt", "input", "query", "content", "message"):
                v = data.get(k)
                if isinstance(v, str):
                    return v
        return str(data)

    def run(self, message: Message) -> Result:
        mc = self.config.model_config or {}
        pii_on = bool(mc.get("pii_redact", True))
        mode = (mc.get("moderation_mode") or "hybrid").lower()
        prompt_f = mc.get("moderation_prompt_file") or "moderation.md"

        original_text = self._extract_text(message.data)

        # 1) PII redaction (deterministic)
        red_text, counts, pii_md_list = redact_pii(original_text) if pii_on else (original_text, {"email":0,"phone":0,"card":0}, [])
        pii_md = "\n".join(pii_md_list) if pii_md_list else "(none)"
        decision = "ALLOW"
        reasons = []
        mod_md = ""

        # 2) LLM moderation (Markdown) – via LLMAgent
        use_llm = (mode in ("llm", "hybrid"))
        if use_llm:
            # build internal LLMAgent just for moderation
            llm_cfg = AgentConfig(
                name=f"{self.config.name}::Moderator",
                prompt_file=prompt_f,
                model_config={k: v for k, v in mc.items()}  # includes model/options/timeout
            )
            moderator = LLMAgent(llm_cfg)  # uses Ollama by default
            prompt_input = {"text": original_text, "pii_md": pii_md}
            md_res = moderator.execute(Message(data=prompt_input))
            mod_md = (md_res.output or {}).get("text", "") if md_res.success else ""
            parsed = parse_moderation_md(mod_md)
            decision = parsed["decision"]
            reasons = parsed["reasons"]

        # 3) Pure deterministic mode (or fallback)
        if mode == "deterministic" or (mode == "hybrid" and not use_llm):
            # if found PII -> REDACT, else ALLOW
            decision = "REDACT" if sum(counts.values()) > 0 else "ALLOW"

        # 4) Control + output
        control = {}
        if decision == "BLOCK":
            control["halt"] = True

        sanitized = red_text if decision in ("ALLOW", "REDACT") else ""
        disp = f"🛡️ Guardrails(decision={decision}, pii={counts})"

        out = {
            "decision": decision,
            "text": sanitized,
            "pii": counts,
            "reasons": reasons,
            "md": mod_md
        }
        return Result.ok(output=out, display_output=disp, control=control)


class ApprovalGateAgent(BaseAgent):
    """
    Human-in-the-loop gate with two phases:

    Phase 1 (request): Generates a summary in Markdown (via LLMAgent + prompt .md) and HALTs the flow.
      - input: { "text" | "content" | ... } (any payload with text)
      - output: { "status":"PENDING", "approval_id": "...", "summary_md": "<md>" }
      - control: {"halt": True}

    Phase 2 (decision): Receives human decision and forwards.
      - input: { "approval_id": "...", "human_decision": "APPROVE"|"REJECT", "human_comment": "..."? }
      - output: { "status":"APPROVED"|"REJECTED", ... }
      - control: {"goto": next_on_approve | next_on_reject} or {"halt": True} if reject and no route.

    Configuration via model_config:
    {
      "summary_prompt_file": "approval_request.md",  # prompt for generating summary
      "next_on_approve": "NextNodeName",             # required to advance
      "next_on_reject": "ReworkNodeName",            # optional
      "model": "llama3",
      "options": {"temperature": 0.1}
    }
    """

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        # Store pending requests with their original content
        self._pending_requests: Dict[str, str] = {}

    def _extract_text(self, data: Any) -> str:
        if isinstance(data, dict):
            for k in ("text", "content", "prompt", "input", "query", "message"):
                v = data.get(k)
                if isinstance(v, str):
                    return v
        return str(data)

    def _summarize_for_human(self, content_md: str) -> str:
        mc = self.config.model_config or {}
        prompt_file = mc.get("summary_prompt_file") or "approval_request.md"

        # Reuse LLMAgent with prompt .md (no mock)
        llm_cfg = AgentConfig(
            name=f"{self.config.name}::Summarizer",
            prompt_file=prompt_file,
            model_config=mc
        )
        summarizer = LLMAgent(llm_cfg)
        res = summarizer.execute(Message(data={"content_md": content_md}))
        if res.success and isinstance(res.output, dict):
            return res.output.get("text", "") or ""
        return ""

    def run(self, message: Message) -> Result:
        mc = self.config.model_config or {}
        nxt_ok = mc.get("next_on_approve")
        nxt_no = mc.get("next_on_reject")

        d = message.data if isinstance(message.data, dict) else {}
        human_decision = d.get("human_decision")

        # ---- Phase 2: human decision ----
        if isinstance(human_decision, str):
            dec = human_decision.strip().upper()
            comment = d.get("human_comment", "")
            approval_id = d.get("approval_id", "")
            
            # Retrieve original content
            original_content = self._pending_requests.get(approval_id, "")
            
            if dec == "APPROVE":
                disp = "🧑‍⚖️ Approval: APPROVED"
                ctrl = {}
                if nxt_ok:
                    ctrl["goto"] = nxt_ok
                
                # Combine original content with human feedback
                enhanced_content = original_content
                if comment:
                    enhanced_content += f"\n\nHuman feedback: {comment}"
                
                # Clean up stored request
                if approval_id in self._pending_requests:
                    del self._pending_requests[approval_id]
                
                return Result.ok(
                    output={
                        "status": "APPROVED",
                        "comment": comment,
                        "text": enhanced_content,
                        "message_text": enhanced_content  # For prompt compatibility
                    },
                    display_output=disp,
                    control=ctrl
                )
            else:
                disp = "🧑‍⚖️ Approval: REJECTED"
                ctrl = {}
                if nxt_no:
                    ctrl["goto"] = nxt_no
                else:
                    ctrl["halt"] = True
                
                # Clean up stored request
                if approval_id in self._pending_requests:
                    del self._pending_requests[approval_id]
                    
                return Result.ok(
                    output={"status": "REJECTED", "comment": comment},
                    display_output=disp,
                    control=ctrl
                )

        # ---- Phase 1: generate summary and pause ----
        content_md = self._extract_text(d or message.data)
        summary_md = self._summarize_for_human(content_md)
        approval_id = str(uuid.uuid4())
        
        # Store the original content for later retrieval
        self._pending_requests[approval_id] = content_md

        disp = "🧑‍⚖️ Approval: PENDING (halt)"
        out = {
            "status": "PENDING",
            "approval_id": approval_id,
            "summary_md": summary_md
        }
        return Result.ok(output=out, display_output=disp, control={"halt": True})


# =============================================================================
# EXPORT ALL AGENTS
# =============================================================================

__all__ = [
    "EchoAgent",
    "SwitchAgent", 
    "CriticAgent",
    "FanOutAgent",
    "JoinAgent",
    "RAGRetrieverAgent",
    "QueryRewriterAgent",
    "GuardrailsAgent",
    "ApprovalGateAgent"
]

# =============================================================================
# USAGE EXAMPLES
# =============================================================================

"""
Example usage of the agents:

# 1. Echo Agent
echo = EchoAgent(AgentConfig(name="Echo"))
result = echo.run(Message(data="hello"))
print(result.output)  # {"echo": "echo(hello)"}

# 2. Switch Agent with LLM
def my_llm(prompt, **kwargs):
    # Your LLM implementation here
    return "## Route: Support\\n## Confidence: 0.8\\n## Reasons: Error mentioned"

switch = SwitchAgent(
    AgentConfig(
        name="Router",
        model_config={
            "mode": "hybrid",
            "confidence_threshold": 0.7,
            "routes": {
                "Support": {"keywords": ["error", "bug"], "description": "Technical support"},
                "Sales": {"keywords": ["price", "plan"], "description": "Sales inquiries"}
            },
            "default": "Support"
        }
    ),
    llm_fn=my_llm
)

# 3. Critic Agent
critic = CriticAgent(
    AgentConfig(
        name="Critic",
        model_config={
            "rubric": ["Clarity", "Completeness", "Accuracy"],
            "threshold": 7.0,
            "max_iters": 3,
            "prompt_file": "critic_agent.md"
        }
    ),
    llm_fn=my_llm
)

# 4. RAG Retriever with Memory
from src.memory.memory_manager import MemoryManager
memory = MemoryManager(stm=None, ltm=your_vector_store)
rag = RAGRetrieverAgent(
    AgentConfig(name="Retriever", model_config={"top_k": 5}),
    memory=memory
)

# 5. Guardrails Agent
guardrails = GuardrailsAgent(
    AgentConfig(
        name="Safety",
        model_config={
            "pii_redact": True,
            "moderation_mode": "hybrid",
            "moderation_prompt_file": "moderation.md"
        }
    )
)

# 6. Human-in-the-Loop Approval
approval = ApprovalGateAgent(
    AgentConfig(
        name="Approval",
        model_config={
            "summary_prompt_file": "approval_request.md",
            "next_on_approve": "Writer",
            "next_on_reject": "Rework"
        }
    )
)

# Use these agents in complex workflows with WorkflowManager!
"""



from __future__ import annotations
from typing import Any, Dict, List
import re

from agent import BaseAgent, AgentConfig, LLMAgent, load_prompt_text, SafeDict
from types import Message, Result

# Markdown sections
_DECISION = re.compile(r"^###\s*DECISION\s*\n([^\n]+)", re.IGNORECASE | re.MULTILINE)
_TARGETS  = re.compile(r"^###\s*TARGETS\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)", re.IGNORECASE | re.MULTILINE | re.DOTALL)

def _parse_decision(md: str) -> str:
    m = _DECISION.search(md or "")
    return (m.group(1).strip().upper() if m else "").replace("-", "_")

def _parse_targets(md: str) -> Dict[str, str]:
    out: Dict[str,str] = {}
    m = _TARGETS.search(md or "")
    if not m: return out
    body = (m.group("body") or "")
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        s = s.lstrip("-• \t")
        # Accept formats: "Writer: SIMPLE" or "Writer SIMPLE"
        if ":" in s:
            k, v = s.split(":", 1)
            out[k.strip()] = v.strip().upper().replace("-", "_")
        else:
            parts = s.split()
            if len(parts) >= 2:
                out[parts[0].strip()] = parts[1].strip().upper().replace("-", "_")
    return out
