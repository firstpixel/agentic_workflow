# core/event_bus.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import threading
import time
import uuid

from src.config.settings import get_settings

EventHandler = Callable[[str, Dict[str, Any]], None]

@dataclass
class Subscription:
    channel: str
    handler: EventHandler
    once: bool = False

class EventBus:
    """
    EventBus local in-memory (thread-safe).
    API:
      - subscribe(channel, handler) -> sub_id
      - subscribe_once(channel, handler) -> sub_id
      - unsubscribe(sub_id)
      - publish(channel, payload)
      - wait_for(channel, predicate, timeout_sec) -> payload | None
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._subs: Dict[str, Dict[str, Subscription]] = {}
        self._ev = threading.Event()

    # --- subs ---
    def subscribe(self, channel: str, handler: EventHandler) -> str:
        sub_id = str(uuid.uuid4())
        with self._lock:
            self._subs.setdefault(channel, {})
            self._subs[channel][sub_id] = Subscription(channel, handler, once=False)
        return sub_id

    def subscribe_once(self, channel: str, handler: EventHandler) -> str:
        sub_id = str(uuid.uuid4())
        with self._lock:
            self._subs.setdefault(channel, {})
            self._subs[channel][sub_id] = Subscription(channel, handler, once=True)
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        with self._lock:
            for ch in list(self._subs.keys()):
                if sub_id in self._subs[ch]:
                    del self._subs[ch][sub_id]
                    if not self._subs[ch]:
                        del self._subs[ch]
                    return

    # --- publish ---
    def publish(self, channel: str, payload: Dict[str, Any]) -> None:
        to_call: List[Subscription] = []
        with self._lock:
            subs = self._subs.get(channel, {})
            to_call = list(subs.values())
        # Call outside lock
        to_remove: List[str] = []
        for s in to_call:
            try:
                s.handler(channel, payload)
            except Exception:
                # não propaga erro do handler
                pass
            if s.once:
                to_remove.append((s.channel, s))
        # limpeza dos once
        if to_remove:
            with self._lock:
                for ch, s in to_remove:
                    for sub_id, sub in list(self._subs.get(ch, {}).items()):
                        if sub is s:
                            del self._subs[ch][sub_id]
                    if ch in self._subs and not self._subs[ch]:
                        del self._subs[ch]
        # aciona waiters
        self._ev.set()
        self._ev.clear()

    # --- wait ---
    def wait_for(self, channel: str, predicate: Callable[[Dict[str, Any]], bool], timeout_sec: float = 30.0) -> Optional[Dict[str, Any]]:
        """
        Bloqueia até que um evento no 'channel' satisfaça o predicate.
        Implementação simples: usamos subscribe_once + Event + polling leve.
        """
        result: Dict[str, Any] = {}
        flag = {"done": False}

        def _handler(_ch: str, payload: Dict[str, Any]):
            if predicate(payload):
                result.update(payload)
                flag["done"] = True

        sub_id = self.subscribe(channel, _handler)
        start = time.time()
        try:
            while (time.time() - start) < timeout_sec:
                if flag["done"]:
                    return result
                self._ev.wait(timeout=0.05)
            return None
        finally:
            self.unsubscribe(sub_id)


# singleton do EventBus
_bus: Optional[EventBus] = None

def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        settings = get_settings()
        if not settings.eventbus_enabled:
            # mesmo quando "desligado", servimos um bus local (no-op)
            _bus = EventBus()
        else:
            _bus = EventBus()
    return _bus
