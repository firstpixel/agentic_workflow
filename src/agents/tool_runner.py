# src/agents/tool_runner.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, List, Callable
from dataclasses import dataclass
import re

from src.core.agent import BaseAgent, AgentConfig
from src.core.types import Message, Result
from src.tools.duckduckgo_scraper import DuckDuckGoScraper


@dataclass
class ToolSpec:
    name: str
    actions: Tuple[str, ...]
    enabled: bool = True


class ToolRunnerAgent(BaseAgent):
    """
    Generic tool runner with an allow-listed registry.

    Inputs supported:
      1) Markdown directive (preferred, no JSON):
         ```tool
         duckduckgo.search_and_scrape
         query: site:example.com Example Domain
         max_results: 2
         ```

         Or:
         ```tool
         tool: duckduckgo
         action: load_url
         url: https://example.com
         ```

      2) Deterministic dict:
         {"tool": "duckduckgo.search_and_scrape", "args": {"query":"...", "max_results":2}}

    Output:
      - Result.output: programmatic dict for downstream agents
      - Result.display_output: full Markdown report for humans
    """

    def __init__(self, config: AgentConfig, llm_fn: Optional[Callable] = None):
        self.config = config
        self.llm_fn = llm_fn

        ddg_cfg = (self.config.model_config or {}).get("tools", {}).get("duckduckgo", {}) or {}
        self.registry: Dict[str, ToolSpec] = {
            "duckduckgo": ToolSpec(
                name="duckduckgo",
                actions=("search", "scrape", "search_and_scrape", "load_url"),
                enabled=bool(ddg_cfg.get("enabled", True)),
            )
        }

    # ---------- Public Agent API ----------

    def execute(self, payload: Message) -> Result:
        selection = self._select_from_payload(payload)

        if not selection["ok"]:
            return Result(
                success=False,
                output={"error": selection["error"]},
                metrics={"agent": self.config.name, "reason": "selection_failed"},
                display_output=self._md_error(selection["error"])
            )

        tool = selection["tool"]
        action = selection["action"]
        args = selection["args"]

        # Dispatch to concrete tool
        try:
            if tool == "duckduckgo":
                result = self._run_duckduckgo(action, args)
            else:
                return Result(
                    success=False,
                    output={"error": f"Unknown tool: {tool}"},
                    metrics={"agent": self.config.name},
                    display_output=self._md_error(f"Unknown tool: {tool}")
                )
        except Exception as e:
            msg = f"Tool execution error: {e}"
            return Result(
                success=False,
                output={"error": msg, "tool": tool, "action": action},
                metrics={"agent": self.config.name},
                display_output=self._md_error(msg)
            )

        shaped = {
            "tool_used": tool,
            "action": action,
            "args": args,
            "results": result
        }
        md = self._md_report(tool, action, args, result)

        return Result(
            success=True,
            output=shaped,
            metrics={"agent": self.config.name, "count": len(result) if isinstance(result, list) else 1},
            display_output=md
        )

    # ---------- Selection ----------

    def _select_from_payload(self, payload: Message) -> Dict[str, Any]:
        data = payload.data
        # Markdown directive (preferred)—string input
        if isinstance(data, str):
            parsed = self._parse_markdown_directive(data)
            if not parsed["ok"]:
                return parsed
            return self._validate_selection(parsed["tool"], parsed["action"], parsed["args"])

        # Deterministic dict input for flows
        if isinstance(data, dict):
            tool_str = data.get("tool")
            action = data.get("action")
            args = data.get("args", {}) or {}
            if tool_str and "." in tool_str and not action:
                tool, action = tool_str.split(".", 1)
            else:
                tool = (tool_str or "")
            if not tool or not action:
                return {"ok": False, "error": "Missing 'tool' and/or 'action'."}
            return self._validate_selection(tool, action, args)

        return {"ok": False, "error": "Unsupported payload format. Provide a Markdown tool block or a dict."}

    def _validate_selection(self, tool: str, action: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool not in self.registry:
            return {"ok": False, "error": f"Tool '{tool}' not registered."}
        spec = self.registry[tool]
        if not spec.enabled:
            return {"ok": False, "error": f"Tool '{tool}' is disabled."}
        if action not in spec.actions:
            return {"ok": False, "error": f"Action '{action}' not allowed for tool '{tool}'."}
        return {"ok": True, "tool": tool, "action": action, "args": args}

    # ---------- Markdown directive parsing ----------

    def _parse_markdown_directive(self, text: str) -> Dict[str, Any]:
        """
        Accepts a fenced block like:

        ```tool
        duckduckgo.search_and_scrape
        query: python site:example.com
        max_results: 2
        ```

        Or:

        ```tool
        tool: duckduckgo
        action: load_url
        url: https://example.com
        ```
        """
        block = self._extract_fenced_block(text)
        if not block:
            return {"ok": False, "error": "No ```tool block found in Markdown."}

        # First non-empty line can be "tool.action" or a "key: value"
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            return {"ok": False, "error": "Empty ```tool block."}

        tool = ""
        action = ""
        args: Dict[str, Any] = {}

        first = lines[0]
        if ":" not in first and "." in first:
            # format: duckduckgo.search_and_scrape
            tool, action = first.split(".", 1)
            kv_lines = lines[1:]
        else:
            kv_lines = lines

        # Parse simple key: value pairs (no JSON/YAML dependency)
        for ln in kv_lines:
            if ":" not in ln:
                continue
            k, v = [x.strip() for x in ln.split(":", 1)]
            if k in ("tool", "name"):
                tool = v
            elif k in ("action",):
                action = v
            elif k in ("query", "url"):
                args[k] = v
            elif k == "urls":
                # comma-separated list
                args[k] = [u.strip() for u in v.split(",") if u.strip()]
            elif k == "max_results":
                try:
                    args[k] = int(v)
                except ValueError:
                    args[k] = v  # leave as-is; validation later
            else:
                # pass-through as string
                args[k] = v

        if not tool or not action:
            return {"ok": False, "error": "Missing tool/action in ```tool block."}

        return {"ok": True, "tool": tool, "action": action, "args": args}

    @staticmethod
    def _extract_fenced_block(text: str) -> Optional[str]:
        m = re.search(r"```tool\s+(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        return m.group(1) if m else None

    # ---------- Concrete bindings ----------

    def _run_duckduckgo(self, action: str, args: Dict[str, Any]) -> Any:
        cfg = (self.config.model_config or {}).get("tools", {}).get("duckduckgo", {}) or {}
        timeout = int(cfg.get("timeout", 10))
        delay = float(cfg.get("delay", 1.0))
        max_limit = int(cfg.get("max_results_limit", 20))

        scraper = DuckDuckGoScraper(timeout=timeout, delay=delay)

        if action == "search":
            query = _require_str(args, "query")
            max_results = min(int(args.get("max_results", 10)), max_limit)
            return scraper.search_duckduckgo(query=query, max_results=max_results)

        if action == "scrape":
            urls = _require_list_of_str(args, "urls")
            out = []
            for i, u in enumerate(urls, 1):
                out.append(scraper.load_url(u))
                if i < len(urls) and delay > 0:
                    import time as _t
                    _t.sleep(delay)
            return out

        if action == "load_url":
            url = _require_str(args, "url")
            return scraper.load_url(url)

        if action == "search_and_scrape":
            query = _require_str(args, "query")
            max_results = min(int(args.get("max_results", 10)), max_limit)
            return scraper.scrape_search_results(query=query, max_results=max_results)

        raise ValueError(f"Unsupported action for duckduckgo: {action}")

    # ---------- Markdown renderers ----------

    def _md_report(self, tool: str, action: str, args: Dict[str, Any], result: Any) -> str:
        hdr = f"# ToolRunner Result\n\n**Tool:** `{tool}`  \n**Action:** `{action}`\n"
        if args:
            hdr += "\n**Args:**\n" + "\n".join([f"- `{k}`: {args[k]}" for k in args]) + "\n"

        if tool == "duckduckgo":
            if action == "search":
                return hdr + self._md_search_list(result)
            if action in ("scrape", "search_and_scrape"):
                return hdr + self._md_scrape_sections(result)
            if action == "load_url":
                return hdr + self._md_single_page(result)

        # default fallback
        return hdr + "\n```\n" + str(result) + "\n```"

    @staticmethod
    def _md_search_list(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "\n_No results._\n"
        md = "\n## Search Results\n\n"
        for i, it in enumerate(items, 1):
            md += f"{i}. [{it.get('title','(no title)')}]({it.get('url','')}) — {it.get('snippet','')}\n"
        return md

    @staticmethod
    def _md_scrape_sections(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "\n_No scraped content._\n"
        md = "\n## Scraped Pages\n\n"
        for i, it in enumerate(items, 1):
            title = it.get("title") or it.get("url", "(no title)")
            url = it.get("url", "")
            content = it.get("content", "")
            md += f"### {i}. {title}\n\n"
            if url:
                md += f"**URL:** {url}\n\n"
            md += content + "\n\n---\n\n"
        return md

    @staticmethod
    def _md_single_page(obj: Dict[str, Any]) -> str:
        url = obj.get("url", "")
        content = obj.get("content", "")
        md = "\n## Page Content\n\n"
        if url:
            md += f"**URL:** {url}\n\n"
        md += content + "\n"
        return md

    @staticmethod
    def _md_error(err: str) -> str:
        return f"# ToolRunner Error\n\n> {err}\n"


# ---------- small arg helpers ----------

def _require_str(d: Dict[str, Any], key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"Argument '{key}' must be a non-empty string.")
    return v.strip()


def _require_list_of_str(d: Dict[str, Any], key: str) -> List[str]:
    v = d.get(key)
    if not isinstance(v, list) or any(not isinstance(x, str) or not x.strip() for x in v):
        raise ValueError(f"Argument '{key}' must be a list of non-empty strings.")
    return [x.strip() for x in v]
