import logging
import queue
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("mcsu.overlay")


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
    overlay_enabled: bool = False
    overlay_osu_id: Optional[int] = None
    overlay_url: str = ""
    bus: EventBus = field(default_factory=EventBus)


bus = EventBus()

OVERLAY_BASE = "http://127.0.0.1:8001"


def resolve_overlay_url(state: AppState) -> str | None:
    """Resolve the local overlay URL for the current username (offline mode).

    Returns ``None`` when the player is not present in the local DB yet or the
    local API is not reachable. The caller is expected to show a placeholder
    and retry.
    """
    if state.overlay_osu_id:
        url = f"{OVERLAY_BASE}/overlay/{state.overlay_osu_id}"
        state.overlay_url = url
        return url

    wanted = (state.username or "").strip()
    if not wanted:
        log.warning("Overlay: username is empty, nothing to look up")
        print("DEBUG: resolve_overlay_url: username is empty", flush=True)
        return None

    import httpx

    try:
        resp = httpx.get(f"{OVERLAY_BASE}/api/players", timeout=5)
    except Exception as e:
        log.warning("Overlay: local API not reachable (%s)", e)
        print(f"DEBUG: /api/players request failed: {e}", flush=True)
        return None

    print(f"DEBUG: API /api/players response status: {resp.status_code}", flush=True)
    if resp.status_code != 200:
        log.warning("Overlay: /api/players returned HTTP %s", resp.status_code)
        return None

    try:
        players = resp.json()
    except Exception:
        log.warning("Overlay: invalid JSON from /api/players")
        print("DEBUG: /api/players returned invalid JSON", flush=True)
        return None

    print(f"DEBUG: Players list: {players}", flush=True)

    target = wanted.lower()
    for player in players:
        name = str(player.get("username") or player.get("name") or "").strip().lower()
        if name == target:
            raw_id = player.get("osu_id") or player.get("id")
            try:
                osu_id = int(raw_id)
            except (TypeError, ValueError):
                log.warning("Overlay: player '%s' has invalid id %r", wanted, raw_id)
                print(f"DEBUG: player '{wanted}' has invalid id {raw_id!r}", flush=True)
                return None
            state.overlay_osu_id = osu_id
            url = f"{OVERLAY_BASE}/overlay/{osu_id}"
            state.overlay_url = url
            print(f"DEBUG: resolved osu_id={osu_id} -> {url}", flush=True)
            return url

    log.warning("Overlay: player '%s' not found in local DB", wanted)
    print(f"DEBUG: player '{wanted}' not found. Wanted='{target}', "
          f"available={[p.get('username') or p.get('name') for p in players]}", flush=True)
    bus.emit("log", f"Overlay: player '{wanted}' not found in local DB")
    return None