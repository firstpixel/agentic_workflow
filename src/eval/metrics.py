from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import time, csv, io

@dataclass
class NodeRecord:
    run_id: str
    node: str
    start_ts: float
    end_ts: float
    success: bool
    attempt: int = 1
    latency_sec: float = 0.0
    control: str = ""
    prompt_chars: int = 0
    output_chars: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

class MetricsCollector:
    """
    Coleta eventos por nó e permite exportar CSV/JSON in-memory.
    Integra-se ao WorkflowManager via hooks on_start/on_end.
    """
    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or f"run-{int(time.time()*1000)}"
        self._open_nodes: Dict[str, float] = {}
        self.records: List[NodeRecord] = []

    # --- Hooks (chamados pelo WorkflowManager) ---
    def on_start_node(self, node: str):
        self._open_nodes[node] = time.time()

    def on_end_node(self, node: str, result: Dict[str, Any]):
        st = self._open_nodes.pop(node, time.time())
        et = time.time()
        metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
        control = result.get("control", {}) if isinstance(result, dict) else {}
        output = result.get("output", {}) if isinstance(result, dict) else {}

        rec = NodeRecord(
            run_id=self.run_id,
            node=node,
            start_ts=st,
            end_ts=et,
            success=bool(result.get("success", True)),
            attempt=int(metrics.get("attempt", 1) or 1),
            latency_sec=float(metrics.get("latency_sec", et-st)),
            control=";".join([k for k,v in (control or {}).items() if v]),
            prompt_chars=int(metrics.get("prompt_chars", 0) or 0),
            output_chars=int(metrics.get("output_chars", 0) or 0),
            extra={"has_output_text": bool(isinstance(output, dict) and ("text" in output))}
        )
        self.records.append(rec)

    # --- Export helpers ---
    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(list(NodeRecord.__dataclass_fields__.keys()))
        for r in self.records:
            writer.writerow([
                r.run_id, r.node, r.start_ts, r.end_ts, r.success, r.attempt,
                r.latency_sec, r.control, r.prompt_chars, r.output_chars, r.extra
            ])
        return buf.getvalue()

    def summary(self) -> Dict[str, Any]:
        total = len(self.records)
        ok = sum(1 for r in self.records if r.success)
        return {
            "run_id": self.run_id,
            "total_nodes": total,
            "success_rate": (ok/total) if total else 0.0,
            "avg_latency_sec": sum(r.latency_sec for r in self.records)/total if total else 0.0
        }
