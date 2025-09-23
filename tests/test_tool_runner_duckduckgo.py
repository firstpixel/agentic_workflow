# tests/test_tool_runner_duckduckgo.py
import pytest

from src.core.workflow_manager import WorkflowManager
from src.core.agent import AgentConfig
from src.agents.tool_runner import ToolRunnerAgent
from src.tools.duckduckgo_scraper import DuckDuckGoScraper


@pytest.fixture
def wm_toolrunner():
    tr = ToolRunnerAgent(AgentConfig(
        name="ToolRunner",
        model_config={
            "mode": "deterministic",
            "tools": {
                "duckduckgo": {
                    "enabled": True,
                    "timeout": 5,
                    "delay": 0.0,
                    "max_results_limit": 5,
                    "allow_actions": ["search", "scrape", "search_and_scrape"]
                }
            }
        }
    ))
    graph = {"ToolRunner": []}
    agents = {"ToolRunner": tr}
    return WorkflowManager(graph, agents)


def test_search_and_scrape_success(monkeypatch, wm_toolrunner):
    # Mock search + content
    def fake_search(self, query, max_results):
        return [
            {"title": "A", "url": "https://a.test/", "snippet": "sa"},
            {"title": "B", "url": "https://b.test/", "snippet": "sb"},
        ][:max_results]

    def fake_content(self, url):
        return f"content for {url}"

    monkeypatch.setattr(DuckDuckGoScraper, "search_duckduckgo", fake_search, raising=True)
    monkeypatch.setattr(DuckDuckGoScraper, "extract_content", fake_content, raising=True)

    res = wm_toolrunner.run_workflow("ToolRunner", {
        "tool": "duckduckgo.search_and_scrape",
        "args": {"query": "test", "max_results": 2}
    })

    assert len(res) == 1
    r = res[0]
    assert r.success is True
    assert r.output["tool_used"] == "duckduckgo"
    assert r.output["action"] == "search_and_scrape"
    items = r.output["results"]
    assert isinstance(items, list) and len(items) == 2
    assert all("content" in x for x in items)


def test_invalid_action_denied(wm_toolrunner):
    res = wm_toolrunner.run_workflow("ToolRunner", {
        "tool": "duckduckgo.not_an_action",
        "args": {"query": "x"}
    })
    assert len(res) == 1
    r = res[0]
    assert r.success is False
    assert "not allowed" in (r.output.get("error", "") + "")


def test_max_results_limit_enforced(monkeypatch, wm_toolrunner):
    recorded = {"max_seen": None}

    def fake_search(self, query, max_results):
        recorded["max_seen"] = max_results
        return [{"title": "A", "url": "https://a.test/", "snippet": "sa"}]

    def fake_content(self, url):
        return "ok"

    monkeypatch.setattr(DuckDuckGoScraper, "search_duckduckgo", fake_search, raising=True)
    monkeypatch.setattr(DuckDuckGoScraper, "extract_content", fake_content, raising=True)

    res = wm_toolrunner.run_workflow("ToolRunner", {
        "tool": "duckduckgo.search_and_scrape",
        "args": {"query": "x", "max_results": 999}
    })

    assert res[0].success is True
    # Tool config limit = 5 (see fixture)
    assert recorded["max_seen"] == 5
