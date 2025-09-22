from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Callable
import re

from src.core.agent import AgentConfig, LLMAgent, load_prompt_text, SafeDict
from src.core.workflow_manager import WorkflowManager
from src.eval.metrics import MetricsCollector
from src.core.types import Message

# ---- Parser para o juiz em Markdown ----
_VERDICT = re.compile(r"^###\s*VERDICT\s*\n([^\n]+)", re.IGNORECASE | re.MULTILINE)
_REASONS = re.compile(r"^###\s*REASONS\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)", re.IGNORECASE | re.MULTILINE | re.DOTALL)

def parse_judge_md(md: str) -> Dict[str, Any]:
    verdict = "FAIL"
    m = _VERDICT.search(md or "")
    if m:
        verdict = m.group(1).strip().upper()
    reasons = []
    r = _REASONS.search(md or "")
    if r:
        body = (r.group("body") or "").strip()
        for ln in body.splitlines():
            s = ln.strip().lstrip("-• \t")
            if s:
                reasons.append(s)
    if verdict not in ("PASS", "FAIL"):
        verdict = "FAIL"
    return {"verdict": verdict, "reasons": reasons}

@dataclass
class EvalCase:
    case_id: str
    entry_node: str
    input_data: Dict[str, Any]
    # Para o juiz regex (determinístico)
    required_regex: Optional[str] = None
    # Para o juiz LLM
    case_md: Optional[str] = None

class EvaluationRunner:
    """
    Runner de avaliação:
      - Executa a pipeline várias vezes (cada EvalCase)
      - Coleta métricas por nó em MetricsCollector
      - Faz julgamento por:
         * 'regex': pattern obrigatório na saída final
         * 'llm': usa LLMAgent + prompt_file 'eval_judge.md'
    """
    def __init__(self, wm: WorkflowManager, metrics: MetricsCollector):
        self.wm = wm
        self.metrics = metrics

    def run_case(self, case: EvalCase, final_node_name: Optional[str] = None,
                 judge: str = "regex",
                 llm_model_cfg: Optional[Dict[str,Any]] = None,
                 judge_prompt_file: str = "eval_judge.md") -> Dict[str, Any]:
        # executa
        results = self.wm.run_workflow(case.entry_node, case.input_data)
        # pega última saída textual “final”
        final_text = ""
        for r in reversed(results):
            if isinstance(r.output, dict) and "text" in r.output and isinstance(r.output["text"], str):
                final_text = r.output["text"]
                break

        # julgamento
        verdict, reasons = "FAIL", []
        if judge == "regex" and case.required_regex:
            verdict = "PASS" if re.search(case.required_regex, final_text, re.IGNORECASE) else "FAIL"
        elif judge == "llm":
            # carrega prompt do juiz em arquivo .md
            tmpl = load_prompt_text(judge_prompt_file)
            case_md = case.case_md or ""
            md_prompt = tmpl.format_map(SafeDict({"case_md": case_md, "model_output_md": final_text}))
            judge_agent = LLMAgent(AgentConfig(name="EvalJudge", prompt_file=None, model_config=llm_model_cfg or {}))
            judge_output = judge_agent.llm_fn(md_prompt, **(llm_model_cfg or {}))
            parsed = parse_judge_md(judge_output)
            verdict, reasons = parsed["verdict"], parsed["reasons"]

        return {"case_id": case.case_id, "verdict": verdict, "reasons": reasons, "final_text": final_text}

    def run(self, cases: List[EvalCase], **kwargs) -> List[Dict[str, Any]]:
        results=[]
        for c in cases:
            res=self.run_case(c, **kwargs)
            results.append(res)
        return results
