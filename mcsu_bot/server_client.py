from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Optional

import httpx

from .paths import token_file

TOKEN_FILE = token_file()


def _save_token(server_url: str, token: str):
    data = {"server_url": server_url, "token": token}
    TOKEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_token() -> dict:
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"server_url": "", "token": ""}


def _clear_token():
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def open_login(server_url: str):
    webbrowser.open(f"{server_url.rstrip('/')}/auth/login")


def check_auth(server_url: str) -> bool:
    data = _load_token()
    return data.get("server_url") == server_url and bool(data.get("token"))


def _server_api_url(server_url: str) -> str:
    return f"{server_url.rstrip('/')}/api"


def sync_score(server_url: str, score_data: dict) -> tuple[bool, str]:
    data = _load_token()
    if data.get("server_url") != server_url:
        return False, "Not authenticated to this server"
    token = data.get("token", "")
    if not token:
        return False, "No auth token"

    url = f"{_server_api_url(server_url)}/scores"
    try:
        resp = httpx.post(
            url,
            json=score_data,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code == 200:
            status = resp.json().get("status", "ok")
            if status == "duplicate":
                return True, "Already on server"
            return True, "Score synced"
        elif resp.status_code == 401:
            _clear_token()
            return False, "Token expired — re-login required"
        else:
            detail = resp.json().get("detail", resp.text)
            return False, f"Server error: {detail}"
    except httpx.TimeoutException:
        return False, "Server timeout"
    except httpx.ConnectError:
        return False, "Cannot connect to server"
    except Exception as e:
        return False, f"Error: {e}"


def sync_local_beatmaps(server_url: str, beatmaps: list[dict]) -> tuple[bool, str]:
    data = _load_token()
    if data.get("server_url") != server_url:
        return False, "Not authenticated to this server"
    token = data.get("token", "")
    if not token:
        return False, "No auth token"

    url = f"{_server_api_url(server_url)}/me/local-beatmaps"
    try:
        resp = httpx.post(
            url,
            json={"beatmaps": beatmaps},
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        if resp.status_code == 200:
            return True, f"Library synced: {resp.json().get('count', 0)} beatmaps"
        elif resp.status_code == 401:
            _clear_token()
            return False, "Token expired — re-login required"
        else:
            detail = resp.json().get("detail", resp.text)
            return False, f"Server error: {detail}"
    except httpx.TimeoutException:
        return False, "Server timeout"
    except httpx.ConnectError:
        return False, "Cannot connect to server"
    except Exception as e:
        return False, f"Error: {e}"


def save_server_token(server_url: str, token: str):
    _save_token(server_url, token)


def get_server_url() -> str:
    return _load_token().get("server_url", "")


def get_saved_token() -> str:
    return _load_token().get("token", "")


def sync_all_scores(
    server_url: str,
    ap_db_path: Path,
    source: str = "mcsu",
    on_progress: callable = None,
) -> tuple[int, int, int, list[str]]:
    data = _load_token()
    if data.get("server_url") != server_url:
        return 0, 0, 0, ["Not authenticated to this server"]
    token = data.get("token", "")
    if not token:
        return 0, 0, 0, ["No auth token"]

    from .database import Database

    db = Database(Path(ap_db_path))
    try:
        db.connect()
        rows = db.get_all_scores()
    except Exception as e:
        return 0, 0, 1, [f"DB error: {e}"]
    finally:
        db.close()

    from datetime import datetime, timezone

    total = len(rows)
    synced, duplicate, failed = 0, 0, 0
    errors: list[str] = []

    def _payload(row) -> dict:
        mods = str(row["mods"] or "NM")
        return {
            "beatmap_id": 0,
            "beatmap_title": row["beatmap_title"] or "Unknown",
            "beatmap_url": "",
            "mods": mods or "NM",
            "source": source,
            "accuracy": float(row["accuracy"] or 0.0),
            "max_combo": int(row["max_combo"] or 0),
            "max_possible_combo": int(row["max_combo"] or 0),
            "count300": int(row["count300"] or 0),
            "count100": int(row["count100"] or 0),
            "count50": int(row["count50"] or 0),
            "count_miss": int(row["count_miss"] or 0),
            "pp": float(row["pp"] or 0.0),
            "ap": float(row["ap"] or 0.0),
            "rank": row["grade"] or "D",
            "density": 0.0,
            "aim": 0.0,
            "stars": float(row["star_rating"] or 0.0),
            "ar": 0.0,
            "md5": row["beatmap_md5"] or "",
            "speed_mult": float(row["speed_mult"] or 1.0),
            "eff_cs": float(row["eff_cs"] or 0.0),
            "eff_ar": float(row["eff_ar"] or 0.0),
            "eff_od": float(row["eff_od"] or 0.0),
            "eff_hp": float(row["eff_hp"] or 0.0),
            "played_at": datetime.fromtimestamp(
                int(row["timestamp"]), tz=timezone.utc
            ).isoformat(),
        }

    for i, row in enumerate(rows, start=1):
        if on_progress:
            on_progress(i, total)
        ok, msg = sync_score(server_url, _payload(row))
        if ok:
            if msg == "Already on server":
                duplicate += 1
            else:
                synced += 1
        else:
            failed += 1
            errors.append(f"{row['beatmap_title']}: {msg}")
            if msg.startswith("Token expired"):
                remaining = total - i
                failed += remaining
                errors.append(f"Остановлено: осталось не отправлено {remaining} скоров")
                break

    return synced, duplicate, failed, errors


def parse_login_link(text: str) -> tuple[str, str]:
    text = text.strip()
    if not text:
        return "", ""
    if "?token=" in text:
        base, _, query = text.partition("?token=")
        base = base.rstrip("/")
        if base.endswith("/profile"):
            base = base[: -len("/profile")]
        token = query.split("&", 1)[0].strip()
        return base, token
    if text.startswith("eyJ"):
        return "", text
    return "", ""


# --------------------------------------------------------------------------- #
# Ranked (ELO)
# --------------------------------------------------------------------------- #

RANKED_ERRORS = {
    503: "Нет подходящих карт в этом диапазоне",
    429: "Лимит рероллов на сегодня исчерпан",
    409: "Нет активного задания",
}


def _ranked_request(
    server_url: str,
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
) -> tuple[bool, object]:
    data = _load_token()
    if data.get("server_url") != server_url:
        return False, "Not authenticated to this server"
    token = data.get("token", "")
    if not token:
        return False, "No auth token"

    url = f"{_server_api_url(server_url)}{path}"
    try:
        resp = httpx.request(
            method,
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code == 200:
            return True, resp.json()
        if resp.status_code == 401:
            _clear_token()
            return False, "Token expired — re-login required"
        return False, _ranked_error_text(resp.status_code, resp)
    except httpx.TimeoutException:
        return False, "Server timeout"
    except httpx.ConnectError:
        return False, "Cannot connect to server"
    except Exception as e:
        return False, f"Error: {e}"


def _ranked_error_text(status_code: int, resp) -> str:
    if status_code in RANKED_ERRORS:
        return RANKED_ERRORS[status_code]
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    return f"Server error: {detail}"


def get_ranked(server_url: str) -> tuple[bool, object]:
    return _ranked_request(server_url, "GET", "/ranked")


def get_ranked_stats(server_url: str) -> tuple[bool, object]:
    return _ranked_request(server_url, "GET", "/ranked/stats")


def ranked_new(server_url: str) -> tuple[bool, object]:
    return _ranked_request(server_url, "POST", "/ranked/new")


def ranked_reroll(server_url: str) -> tuple[bool, object]:
    return _ranked_request(server_url, "POST", "/ranked/reroll")


def ranked_surrender(server_url: str) -> tuple[bool, object]:
    return _ranked_request(server_url, "POST", "/ranked/surrender")


def get_ranked_history(
    server_url: str, limit: int = 20, offset: int = 0
) -> tuple[bool, object]:
    return _ranked_request(
        server_url, "GET", "/ranked/history", params={"limit": limit, "offset": offset}
    )


def get_ranked_leaderboard(server_url: str, limit: int = 50) -> tuple[bool, object]:
    return _ranked_request(
        server_url, "GET", "/ranked/leaderboard", params={"limit": limit}
    )
