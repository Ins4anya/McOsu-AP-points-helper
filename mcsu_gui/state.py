import queue
from dataclasses import dataclass, field
from typing import Any, Optional


class EventBus:
    """Thread-safe cross-thread -> UI event dispatch.

    Worker threads call ``emit``; a ``ui.timer`` in the app calls ``drain``
    on the asyncio loop, so UI updates always happen on the right thread.
    """

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._handlers: dict[str, list[tuple[Optional[str], callable]]] = {}

    def subscribe(self, kind: str, handler: callable, key: Optional[str] = None):
        if key is not None:
            self._handlers[kind] = [
                (k, h) for k, h in self._handlers.get(kind, []) if k != key
            ]
        self._handlers.setdefault(kind, []).append((key, handler))

    def emit(self, kind: str, payload: Any = None):
        self._queue.put((kind, payload))

    def drain(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                for _, handler in self._handlers.get(kind, []):
                    handler(payload)
        except queue.Empty:
            pass


@dataclass
class AppState:
    config: Optional[object] = None
    source: str = "mcsu"
    username: str = ""
    server_url: str = ""
    result: Optional[object] = None
    bus: EventBus = field(default_factory=EventBus)


bus = EventBus()