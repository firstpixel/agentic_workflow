# src/app/flows_tools.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List

from src.core.workflow_manager import WorkflowManager
from src.core.agent import AgentConfig
from src.agents.tool_runner import ToolRunnerAgent


@dataclass
class FlowBundle:
    graph: Dict[str, List[str]]
    agents: Dict[str, object]
    node_policies: Dict[str, Dict[str, object]]

    def manager(self) -> WorkflowManager:
        return WorkflowManager(self.graph, self.agents, metrics=None, node_policies=self.node_policies)


def make_duckduckgo_tool_flow() -> FlowBundle:
    tr = ToolRunnerAgent(AgentConfig(
        name="ToolRunner",
        model_config={
            "mode": "deterministic",   # we parse Markdown deterministically too
            "tools": {
                "duckduckgo": {
                    "enabled": True,
                    "timeout": 10,
                    "delay": 0.0,
                    "max_results_limit": 10,
                    "allow_actions": ["search", "scrape", "search_and_scrape", "load_url"]
                }
            }
        }
    ))
    graph = {"ToolRunner": []}
    agents = {"ToolRunner": tr}
    return FlowBundle(graph=graph, agents=agents, node_policies={})


def run_toolrunner_duckduckgo_demo():
    print("\n" + "=" * 60)
    print("🧪 DEMO — ToolRunner (DuckDuckGo via Markdown directives)")
    print("=" * 60)

    fb = make_duckduckgo_tool_flow()
    wm = fb.manager()

    md_search = """```tool
duckduckgo.search_and_scrape
query: site:google.com Example Domain
max_results: 1
```"""

    md_single = """```tool
tool: duckduckgo
action: load_url
url: https://globo.com/
```"""

    for name, payload in [("search_and_scrape", md_search), ("load_url", md_single)]:
        print(f"\n--- {name} ---")
        results = wm.run_workflow("ToolRunner", payload)
        for r in results:
            print(r.display_output or r.output)
