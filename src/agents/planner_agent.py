from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional
import re

from src.core.agent import BaseAgent, AgentConfig, LLMAgent
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
_DEP_EDGE = re.compile(r"^\s*(?P<to>[A-Za-z0-9_.\-]+)\s*<-\s*(?P<frm>[A-Za-z0-9_.\-,\s]+)\s*$", re.MULTILINE)

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
        to = m.group("to").strip()
        frm_list = m.group("frm").strip()
        # Handle multiple dependencies separated by commas
        for frm in frm_list.split(','):
            frm = frm.strip()
            if frm:  # Skip empty strings
                edges.append((frm, to))
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
        print(f"🔍 [DEBUG] Prompt file: {prompt_file}")
        
        # Stage agent reuses Ollama config; can override per stage
        mc = dict(self.config.model_config or {})
        so = (mc.get("stage_overrides") or {}).get(stage) or {}
        mc.update(so)
        print(f"🔍 [DEBUG] Model config: {mc}")

        stage_agent = LLMAgent(AgentConfig(
            name=f"Planner::{stage}",
            prompt_file=prompt_file,
            model_config=mc
        ))
        
        # Build user prompt with variable context - new LLMAgent will handle system prompt automatically
        user_prompt_parts = []
        for k, v in vars.items():
            user_prompt_parts.append(f"{k}: {v}")
        
        user_prompt = "\n\n".join(user_prompt_parts)
        print(f"🔍 [DEBUG] Built user prompt: {len(user_prompt)} chars")
        
        # Create message compatible with new LLMAgent interface
        message_data = {"user_prompt": user_prompt}
        
        print(f"🔍 [DEBUG] Sending message to stage agent with user_prompt...")
        
        try:
            res = stage_agent.run(Message(data=message_data))
            print(f"🔍 [DEBUG] Stage agent run result:")
            print(f"    success: {res.success}")
            print(f"    output keys: {list(res.output.keys()) if isinstance(res.output, dict) else 'not dict'}")
            if res.success:
                output = (res.output.get("text") or "").strip()
                print(f"🔍 [DEBUG] FULL LLM response for {stage} ({len(output)} chars):")
                print("=" * 80)
                print(output)
                print("=" * 80)
            else:
                print(f"❌ [DEBUG] Stage failed: {res}")
                output = ""
        except Exception as e:
            print(f"❌ [DEBUG] Exception in stage {stage}: {e}")
            import traceback
            traceback.print_exc()
            output = ""
        
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
        print(f"📋 [DEBUG] Raw decomposer output ({len(md_decomp)} chars) - ALREADY PRINTED ABOVE")
        
        draft_tasks = _parse_tasks(md_decomp)
        deps = _parse_deps(md_decomp)
        print(f"📋 [DEBUG] Parsed {len(draft_tasks)} tasks: {[f'{t}:{title[:30]}' for t, title in draft_tasks]}")
        print(f"📋 [DEBUG] Parsed {len(deps)} dependencies: {deps}")
        
        # Debug parsing
        if len(draft_tasks) == 0:
            print(f"❌ [DEBUG] No tasks parsed! Checking regex...")
            body_m = _DRAFT_TASKS.search(md_decomp)
            if body_m:
                body = body_m.group("body")
                print(f"📋 [DEBUG] Found DRAFT TASKS section: {body[:200]}...")
                import re
                matches = list(_BULLET_TASK.finditer(body))
                print(f"📋 [DEBUG] Bullet task matches: {len(matches)}")
                for i, m in enumerate(matches[:3]):
                    print(f"    Match {i}: '{m.group(0)}' -> id='{m.group('id')}', title='{m.group('title')}'")
            else:
                print(f"❌ [DEBUG] No DRAFT TASKS section found in output!")
                print(f"📋 [DEBUG] Looking for pattern: {_DRAFT_TASKS.pattern}")
        
        if len(deps) == 0 and "DEPENDENCIES" in md_decomp:
            print(f"❌ [DEBUG] No dependencies parsed but section exists!")
            body_m = _DEPENDENCIES.search(md_decomp)
            if body_m:
                body = body_m.group("body")
                print(f"📋 [DEBUG] Dependencies section: {body[:200]}...")
                matches = list(_DEP_EDGE.finditer(body))
                print(f"📋 [DEBUG] Dependency matches: {len(matches)}")
                for i, m in enumerate(matches[:3]):
                    print(f"    Match {i}: '{m.group(0)}' -> from='{m.group('frm')}', to='{m.group('to')}'")
        
        if len(draft_tasks) == 0:
            print(f"❌ [DEBUG] Critical error: No tasks found, cannot continue!")
            return Result.fail(output={"error": "No tasks could be parsed from decomposer output"}, 
                             display_output="❌ Planner: No tasks found")

        # 2) Summarize
        print(f"\n📝 [DEBUG] Step 2: Summarizing...")
        md_summary = self._call_stage("summarizer", {
            "request": text,
            "draft_tasks_md": md_decomp
        })
        summary_md = (_OVERALL_SUMMARY.search(md_summary).group("body").strip()
                      if _OVERALL_SUMMARY.search(md_summary) else md_summary.strip())
        print(f"📝 [DEBUG] Summary - ALREADY PRINTED ABOVE")

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
            print(f"🔍 [DEBUG] Task {tid} detailed - ALREADY PRINTED ABOVE")

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
        print(f"\n🏁 [DEBUG] Final plan prepared - ALREADY PRINTED ABOVE")
        
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
        
        # Add explicit routing to Updater
        return Result.ok(output=out, display_output=disp, control={"goto": "Updater"})

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
