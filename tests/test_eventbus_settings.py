import os
from src.core.event_bus import get_event_bus
from src.config.settings import get_settings, reset_settings

def test_settings_load_and_eventbus_basic(monkeypatch):
    # Define alguns envs e recarrega settings
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:1b")
    monkeypatch.setenv("PROMPT_DIR", "/tmp/prompts")
    monkeypatch.setenv("EVENTBUS_ENABLED", "true")
    
    # Reset settings to pick up new environment variables
    reset_settings()
    s = get_settings()
    # Asserções básicas
    assert s.ollama_model.startswith("llama3.2:1b")
    assert s.prompt_dir == "/tmp/prompts"
    assert s.eventbus_enabled is True

    # EventBus básico
    bus = get_event_bus()
    received = {}

    def handler(ch, payload):
        received["ch"] = ch
        received.update(payload)

    # subscribe/publish
    sub_id = bus.subscribe("test.channel", handler)
    bus.publish("test.channel", {"x": 1, "y": "ok"})
    assert received.get("x") == 1 and received.get("y") == "ok"
    assert received.get("ch") == "test.channel"

    # once
    count = {"n": 0}
    def handler_once(_ch, _p):
        count["n"] += 1
    bus.subscribe_once("test.once", handler_once)
    bus.publish("test.once", {})
    bus.publish("test.once", {})
    assert count["n"] == 1

    # wait_for
    import threading
    import time
    
    def later():
        time.sleep(0.1)  # small delay to allow wait_for to start
        bus.publish("wait.topic", {"flag": True})
    
    # Start the later() function in a separate thread
    thread = threading.Thread(target=later)
    thread.start()
    
    res = bus.wait_for("wait.topic", lambda p: p.get("flag") is True, timeout_sec=2.0)
    thread.join()  # Wait for thread to complete
    assert res and res.get("flag") is True
