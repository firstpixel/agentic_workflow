# tests/test_retries_and_fallbacks.py

import pytest
from src.app.flows_retries import make_retries_fallback_flow

def test_exception_retry_eventual_success():
    fb = make_retries_fallback_flow(exc_fail_times=1, exc_retries=2)
    wm = fb.manager(metrics=None)
    results = wm.run_workflow("Start", {"request": "x"})
    history = wm.get_retry_history()

    exc_events = history.get("Exc", [])
    assert any(e["event"] == "exception" for e in exc_events)
    assert any(e["event"] == "retry_enqueued" for e in exc_events)
    assert not any(e["event"] == "fallback" for e in exc_events)

    terminal_outs = [r.output for r in results if isinstance(r.output, dict) and r.output.get("agent") == "Terminal"]
    assert len(terminal_outs) >= 1


def test_failed_result_retry_eventual_success():
    fb = make_retries_fallback_flow(fail_fail_times=1, fail_retries=2)
    wm = fb.manager(metrics=None)
    results = wm.run_workflow("Start", {"request": "y"})
    history = wm.get_retry_history()

    fail_events = history.get("Fail", [])
    assert any(e["event"] == "failed_result" for e in fail_events)
    assert any(e["event"] == "retry_enqueued" for e in fail_events)
    assert not any(e["event"] == "fallback" for e in fail_events)

    terminal_outs = [r.output for r in results if isinstance(r.output, dict) and r.output.get("agent") == "Terminal"]
    assert len(terminal_outs) >= 1


def test_fallback_after_retries_exhausted_for_failed_result():
    fb = make_retries_fallback_flow(failhard_fail_times=3, failhard_retries=1)
    wm = fb.manager(metrics=None)
    results = wm.run_workflow("Start", {"request": "z"})
    history = wm.get_retry_history()

    hard_events = history.get("FailHard", [])
    assert any(e["event"] == "failed_result" for e in hard_events)
    assert any(e["event"] == "retry_enqueued" for e in hard_events)
    assert any(e["event"] == "fallback" for e in hard_events)

    terminal_outs = [r.output for r in results if isinstance(r.output, dict) and r.output.get("agent") == "Terminal"]
    assert len(terminal_outs) >= 1

    # At least one terminal output should include a batch list
    assert any(isinstance(o.get("final_batch"), list) and len(o["final_batch"]) >= 1 for o in terminal_outs)
