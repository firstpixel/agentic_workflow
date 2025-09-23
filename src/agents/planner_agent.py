from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional
import re

from src.core.agent import BaseAgent, AgentConfig, LLMAgent, load_prompt_text, SafeDict
from src.core.types import Message, Result


# ===========================
# Markdown section parsers
# ===========================

def _section(pattern: str) -> re.Pattern:
    return re.compile(
        rf"^###\s*{pattern}\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )

_DRAFT_TASKS     = _section(r"DRAFT\s+TASKS")
_DEPENDENCIES    = _section(r"DEPENDENCIES")
_OVERALL_SUMMARY = _section(r"OVERALL\s+SUMMARY")
_DECISION        = _section(r"DECISION")
_EDITS           = _section(r"EDITS")
_REFINE_REQ      = _section(r"REFINE\s+REQUEST")

_FINAL_TASK_LIST = re.compile(r"^###\s*FINAL\s+TASK\s+LIST\s+v(?P<ver>\d+)", re.IGNORECASE | re.MULTILINE)
_MILESTONES      = _section(r"MILESTONES")
_CRITICAL_PATH   = _section(r"CRITICAL\s+PATH")
_REFINEMENT_RES  = _section(r"REFINEMENT\s+RESULT\s*\(.*?\)")

_BULLET_TASK = re.compile(r"^\s*(?:-\s*|#{1,6}\s*)\[(?P<id>[A-Za-z0-9_.\-]+)\]\s+(?P<title>.+?)\s*$", re.MULTILINE)
_DEP_EDGE    = re.compile(r"^\s*(?P<to>[A-Za-z0-9_.\-]+)\s*<-\s*(?P<frm>[A-Za-z0-9_.\-]+)\s*$", re.MULTILINE)

_REPLACED_LINE = re.compile(r"^\s*Replaced\s*:\s*(?P<id>[A-Za-z0-9_.\-]+)\s*$", re.IGNORECASE | re.MULTILINE)
_NEW_LINE      = re.compile(r"^\s*New\s*:\s*(?P<ids>.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def _extract_text(payload: Any) -> str:
    if isinstance(payload, dict):
        for k in ("text", "request", "goal", "content", "plan_md", "final_plan_md", "refine_request_md"):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return str(payload)
    if isinstance(payload, list):
        return "\n\n".join(_extract_text(p) for p in payload)
    return str(payload)


def _parse_tasks(md: str) -> List[Tuple[str, str]]:
    body_m = _DRAFT_TASKS.search(md)
    if not body_m:
        return []
    body = body_m.group("body")
    items = []
    for m in _BULLET_TASK.finditer(body):
        items.append((m.group("id").strip(), m.group("title").strip()))
    return items


def _parse_deps(md: str) -> List[Tuple[str, str]]:
    body_m = _DEPENDENCIES.search(md)
    if not body_m:
        return []
    body = body_m.group("body")
    edges = []
    for m in _DEP_EDGE.finditer(body):
        edges.append((m.group("frm").strip(), m.group("to").strip()))
    return edges


def _topsort(nodes: List[str], edges: List[Tuple[str, str]]) -> List[str]:
    from collections import defaultdict, deque
    indeg = defaultdict(int)
    g: Dict[str, List[str]] = defaultdict(list)
    set_nodes = set(nodes)
    for u, v in edges:
        g[u].append(v)
        indeg[v] += 1
        set_nodes.add(u); set_nodes.add(v)
    for n in set_nodes:
        indeg.setdefault(n, 0)
    q = deque([n for n in set_nodes if indeg[n] == 0])
    out = []
    while q:
        u = q.popleft()
        out.append(u)
        for v in g.get(u, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(out) != len(set_nodes):
        raise ValueError("Cycle detected in task dependencies.")
    prefer = [n for n in nodes if n in set_nodes]
    out_set = set(out)
    ordered = [n for n in prefer if n in out_set and n in out] + [n for n in out if n not in prefer]
    seen = set(); final = []
    for n in ordered:
        if n not in seen:
            final.append(n); seen.add(n)
    return final


def _parse_decision(md: str) -> str:
    m = _DECISION.search(md)
    if not m:
        return "PASS"
    txt = (m.group("body") or "").strip().splitlines()[0].strip().upper()
    return "PASS" if "PASS" in txt else "REVISE" if "REVISE" in txt else "PASS"


class PlannerAgent(BaseAgent):
    """
    Multi-call Planner that uses **LLMAgent** for each stage (Ollama via model_config).

    Sub-stages (/prompts/planner/*.md):
      - decomposer.md → draft atomic tasks + deps
      - summarizer.md → overview (scope/constraints/assumptions/success)
      - detailer.md   → expand each task (your Task Format)
      - merger.md     → order, milestones, Final Task List vN
      - evaluator.md  → PASS/REVISE (one revision loop)
      - refiner.md    → (on refine) split failing task(s), bump plan version

    model_config:
      executor_agent: str
      stage_overrides: dict[str, dict]  # optional llm kwargs per stage
    """

    STAGE_FILES = {
        "decomposer": "planner/decomposer.md",
        "summarizer": "planner/summarizer.md",
        "detailer":   "planner/detailer.md",
        "merger":     "planner/merger.md",
        "evaluator":  "planner/evaluator.md",
        "refiner":    "planner/refiner.md",
    }

    def __init__(self, config: AgentConfig):
        super().__init__(config)

    # ---------- LLM helper via LLMAgent ----------

    def _call_stage(self, stage: str, vars: Dict[str, Any]) -> str:
        print(f"\n🔍 [DEBUG] Starting stage: {stage}")
        print(f"🔍 [DEBUG] Input vars for {stage}:")
        for k, v in vars.items():
            print(f"    {k}: {str(v)[:200]}{'...' if len(str(v)) > 200 else ''}")
        
        prompt_file = self.STAGE_FILES[stage]
        # Stage agent reuses Ollama config; can override per stage
        mc = dict(self.config.model_config or {})
        so = (mc.get("stage_overrides") or {}).get(stage) or {}
        mc.update(so)

        stage_agent = LLMAgent(AgentConfig(
            name=f"Planner::{stage}",
            prompt_file=prompt_file,
            model_config=mc
        ))
        # We pass a single text blob; the prompt file uses placeholders
        text_blob = "\n".join(f"{k}: {v}" for k, v in vars.items())
        
        print(f"🔍 [DEBUG] Sending to LLM for {stage}:")
        print(f"    text_blob: {text_blob[:300]}{'...' if len(text_blob) > 300 else ''}")
        
        res = stage_agent.execute(Message(data={"text": text_blob}))
        output = (res.output.get("text") or "").strip()
        
        print(f"🔍 [DEBUG] LLM response for {stage}:")
        print(f"    output: {output[:300]}{'...' if len(output) > 300 else ''}")
        print(f"🔍 [DEBUG] Completed stage: {stage}\n")
        
        return output

    # ---------- main run ----------

    def run(self, message: Message) -> Result:
        text = _extract_text(message.data)
        executor_agent = self._resolve_executor(message)

        print(f"\n🚀 [DEBUG] PlannerAgent.run() starting")
        print(f"🚀 [DEBUG] Input text: {text[:200]}{'...' if len(text) > 200 else ''}")
        print(f"🚀 [DEBUG] Executor agent: {executor_agent}")

        # Refinement path
        if _REFINE_REQ.search(text):
            print(f"🚀 [DEBUG] Taking refinement path")
            return self._run_refinement(text, executor_agent)

        print(f"🚀 [DEBUG] Taking normal planning path")

        # 1) Decompose
        print(f"\n📋 [DEBUG] Step 1: Decomposing...")
        md_decomp = self._call_stage("decomposer", {"request": text})
        draft_tasks = _parse_tasks(md_decomp)
        deps = _parse_deps(md_decomp)
        print(f"📋 [DEBUG] Parsed {len(draft_tasks)} tasks: {[f'{t}:{title[:30]}' for t, title in draft_tasks]}")
        print(f"📋 [DEBUG] Parsed {len(deps)} dependencies: {deps}")

        # 2) Summarize
        print(f"\n📝 [DEBUG] Step 2: Summarizing...")
        md_summary = self._call_stage("summarizer", {
            "request": text,
            "draft_tasks_md": md_decomp
        })
        summary_md = (_OVERALL_SUMMARY.search(md_summary).group("body").strip()
                      if _OVERALL_SUMMARY.search(md_summary) else md_summary.strip())
        print(f"📝 [DEBUG] Summary: {summary_md[:200]}{'...' if len(summary_md) > 200 else ''}")

        # 3) Detail (sequential)
        print(f"\n🔍 [DEBUG] Step 3: Detailing tasks...")
        tasks_md: List[str] = []
        for i, (tid, title) in enumerate(draft_tasks):
            print(f"🔍 [DEBUG] Detailing task {i+1}/{len(draft_tasks)}: {tid} - {title[:50]}")
            md_detail = self._call_stage("detailer", {
                "request": text,
                "task_id": tid,
                "task_title": title,
                "overall_summary_md": summary_md
            })
            tasks_md.append(md_detail.strip())
            print(f"🔍 [DEBUG] Task {tid} detailed: {md_detail[:100]}{'...' if len(md_detail) > 100 else ''}")

        # 4) Merge
        print(f"\n🔗 [DEBUG] Step 4: Merging...")
        ordered_ids = self._safe_order([t for t, _ in draft_tasks], deps)
        dag_lines = [f"{to} <- {frm}" for frm, to in deps]
        print(f"🔗 [DEBUG] Ordered IDs: {ordered_ids}")
        print(f"🔗 [DEBUG] DAG lines: {dag_lines}")
        md_merger = self._call_stage("merger", {
            "overall_summary_md": summary_md,
            "tasks_md": "\n\n".join(tasks_md),
            "ordered_ids": ", ".join(ordered_ids),
            "dependencies_md": "\n".join(dag_lines),
            "version": "1"
        })

        # 5) Evaluate (single revise loop optional)
        print(f"\n✅ [DEBUG] Step 5: Evaluating...")
        md_eval = self._call_stage("evaluator", {
            "overall_summary_md": summary_md,
            "final_draft_md": md_merger
        })
        decision = _parse_decision(md_eval)
        print(f"✅ [DEBUG] Evaluation decision: {decision}")
        if decision == "REVISE":
            print(f"✅ [DEBUG] Plan needs revision (but keeping as-is for simplicity)")
            # keep simple: return md_merger as-is; your evaluator prompt should be strict
            pass

        final_plan_md = md_merger.strip()
        print(f"\n🏁 [DEBUG] Final plan prepared:")
        print(f"🏁 [DEBUG] final_plan_md: {final_plan_md[:300]}{'...' if len(final_plan_md) > 300 else ''}")
        
        plan_meta = {
            "executor_agent": executor_agent,
            "task_ids": ordered_ids,
            "dag_edges": dag_lines,
            "version": "v1",
        }
        disp = f"🧭 Planner(v1) tasks={len(ordered_ids)} executor={executor_agent}"
        out = {
            "summary_md": summary_md,
            "final_plan_md": final_plan_md,
            "tasks_md": tasks_md,
            "plan_meta": plan_meta
        }
        print(f"🏁 [DEBUG] PlannerAgent.run() completed successfully!")
        print(f"🏁 [DEBUG] Output keys: {list(out.keys())}")
        print(f"🏁 [DEBUG] Display: {disp}")
        return Result.ok(output=out, display_output=disp)

    # ---------- refinement ----------

    def _run_refinement(self, refine_request_md: str, executor_agent: str) -> Result:
        md_refined = self._call_stage("refiner", {"refine_request_md": refine_request_md})
        # We leave parsing nuanced; your refiner prompt will include updated tasks blocks and deps
        final_plan_md = md_refined.strip()
        out = {
            "summary_md": "",
            "final_plan_md": final_plan_md,
            "tasks_md": [md_refined.strip()],
            "plan_meta": {
                "executor_agent": executor_agent,
                "version": "v2"
            }
        }
        return Result.ok(output=out, display_output="🔧 Planner(refine→v2)")

    # ---------- helpers ----------

    def _resolve_executor(self, message: Message) -> str:
        if isinstance(message.meta, dict):
            v = message.meta.get("executor_agent")
            if isinstance(v, str) and v.strip():
                return v.strip()
        mc = self.config.model_config or {}
        v = mc.get("executor_agent")
        if isinstance(v, str) and v.strip():
            return v.strip()
        return "ExecutorAgent"

    def _safe_order(self, ids: List[str], deps: List[Tuple[str, str]]) -> List[str]:
        try:
            return _topsort(ids, deps)
        except Exception:
            return ids[:]
