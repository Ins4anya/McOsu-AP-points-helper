"""Tests for the /api/ranked* routes (TestClient, no real osu! API calls)."""
from __future__ import annotations

import itertools
import os
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from server.dates import today_str

MAP = {
    "beatmap_id": 10,
    "beatmapset_id": 1,
    "beatmap_title": "Artist - Song [Insane]",
    "artist": "Artist",
    "version": "Insane",
    "stars": 5.0,
    "length": 120,
    "download_url": "https://osu.ppy.sh/beatmapsets/1/download",
}

_FAKE_MAPS = [MAP]

_osu_id_seq = itertools.count(10000)


async def fake_fetch_challenge_maps(config, count=5, **kwargs):
    return list(_FAKE_MAPS)


async def fake_fetch_personal_challenge_maps(config, local_ids, count=5, **kwargs):
    return list(_FAKE_MAPS)


def _restore(name, old):
    if old is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = old


@pytest.fixture(scope="module")
def _env(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("ranked_api") / "server.db"
    old = {
        k: os.environ.get(k)
        for k in (
            "DATABASE_URL",
            "RANKED_ENABLED",
            "DAILY_CHALLENGE_ENABLED",
            "RANKED_START_ELO",
            "RANKED_ELO_FLOOR",
            "RANKED_STAR_WINDOW",
        )
    }
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    os.environ["RANKED_ENABLED"] = "true"
    os.environ["DAILY_CHALLENGE_ENABLED"] = "false"  # keep daily challenge out of these tests
    # Isolate from any RANKED_* values the developer set in server/.env.
    os.environ["RANKED_START_ELO"] = "100"
    os.environ["RANKED_ELO_FLOOR"] = "100"
    os.environ["RANKED_STAR_WINDOW"] = "0.15"
    yield db_path
    for k, v in old.items():
        _restore(k, v)


@pytest.fixture(scope="module")
def app(_env):
    import server.beatmap_picker as bp

    bp.fetch_challenge_maps = fake_fetch_challenge_maps
    bp.fetch_personal_challenge_maps = fake_fetch_personal_challenge_maps

    from server.main import app

    return app


@pytest.fixture(scope="module")
def client(app, _env):
    with TestClient(app) as c:
        yield c, _env


def _auth(db_path, osu_id):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO users "
            "(osu_id, username, avatar_url, osu_access_token, osu_refresh_token) "
            "VALUES (?, ?, '', '', '')",
            (osu_id, f"u{osu_id}"),
        )
        conn.commit()
        uid = conn.execute("SELECT id FROM users WHERE osu_id = ?", (osu_id,)).fetchone()[0]
    finally:
        conn.close()

    from server.auth import create_jwt
    from server.config import ServerConfig

    token = create_jwt(ServerConfig.from_env(), uid)
    return {"Authorization": f"Bearer {token}"}, uid, osu_id


def test_ranked_requires_auth(client):
    c, _ = client
    assert c.get("/api/ranked").status_code == 401
    assert c.post("/api/ranked/new").status_code == 401
    assert c.post("/api/ranked/reroll").status_code == 401
    assert c.post("/api/ranked/surrender").status_code == 401


def test_ranked_full_cycle(client):
    c, db_path = client
    headers, _uid, _osu_id = _auth(db_path, next(_osu_id_seq))

    r = c.post("/api/ranked/new", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["elo"] == 100
    assert body["tier"] == "Базовый"
    assert body["star_window"] == {"min": 0.5, "max": 1.0, "target": 0.75}
    assert body["sub_rank"] is None
    assert body["active"] is not None
    bid = body["active"]["beatmap_id"]

    payload = {
        "beatmap_id": bid,
        "beatmap_title": "Artist - Song [Insane]",
        "beatmap_url": "",
        "mods": "NM",
        "source": "api",
        "accuracy": 0.95,
        "max_combo": 100,
        "max_possible_combo": 100,
        "pp": 100.0,
        "ap": 100.0,
        "rank": "S",
        "played_at": datetime.now(timezone.utc).isoformat(),
    }
    r = c.post("/api/scores", json=payload, headers=headers)
    assert r.status_code == 200

    r = c.get("/api/ranked", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["elo"] == 130  # 95% -> +30 pass
    assert body["active"] is None
    assert body["last_result"]["status"] == "passed"


def test_ranked_new_default_start_elo_500(client, monkeypatch):
    c, db_path = client
    monkeypatch.setenv("RANKED_START_ELO", "500")
    monkeypatch.setenv("RANKED_ELO_FLOOR", "100")
    headers, _uid, _osu_id = _auth(db_path, next(_osu_id_seq))

    r = c.post("/api/ranked/new", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["elo"] == 500
    assert body["tier"] == "Золото"
    assert body["star_range"] == {"min": 4.0, "max": 5.0}
    assert body["star_window"] == {"min": 3.85, "max": 4.15, "target": 4.0}
    assert body["sub_rank"] == {"filled": 1, "total": 4}
    assert body["reroll_penalty"] == -5
    assert body["fail_delta"] == -60


def test_ranked_reroll_limit(client):
    c, db_path = client
    headers, uid, _osu_id = _auth(db_path, next(_osu_id_seq))
    c.post("/api/ranked/new", headers=headers)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE ranked_state SET rerolls_today = 3, reroll_date = ? WHERE user_id = ?",
        (today_str(), uid),
    )
    conn.commit()
    conn.close()

    r = c.post("/api/ranked/reroll", headers=headers)
    assert r.status_code == 429


def test_ranked_surrender(client):
    c, db_path = client
    headers, _uid, _osu_id = _auth(db_path, next(_osu_id_seq))
    c.post("/api/ranked/new", headers=headers)

    r = c.post("/api/ranked/surrender", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is None
    assert body["elo"] == 100  # -60 floored (RANKED_START_ELO=100 in tests)
    assert body["last_result"]["status"] == "surrendered"


def test_ranked_surrender_without_active_409(client):
    c, db_path = client
    headers, _uid, _osu_id = _auth(db_path, next(_osu_id_seq))
    r = c.post("/api/ranked/surrender", headers=headers)
    assert r.status_code == 409


def test_ranked_leaderboard_public(client):
    c, db_path = client
    headers, _uid, osu_id = _auth(db_path, next(_osu_id_seq))
    c.post("/api/ranked/new", headers=headers)
    c.post("/api/ranked/surrender", headers=headers)

    r = c.get("/api/ranked/leaderboard")  # no auth
    assert r.status_code == 200
    rows = r.json()
    assert any(row["osu_id"] == osu_id for row in rows)
    row = next(row for row in rows if row["osu_id"] == osu_id)
    assert "tier" in row and "elo" in row


def test_ranked_new_no_maps_503(client):
    c, db_path = client
    headers, _uid, _osu_id = _auth(db_path, next(_osu_id_seq))
    _FAKE_MAPS.clear()
    try:
        r = c.post("/api/ranked/new", headers=headers)
        assert r.status_code == 503
    finally:
        _FAKE_MAPS.append(MAP)


# --------------------------------------------------------------------------- #
# /api/ranked/stats
# --------------------------------------------------------------------------- #


def _insert_ranked_challenge(
    db_path, uid, status, *, stars=5.0, accuracy=0.95, delta=10, elo_after=None
):
    conn = sqlite3.connect(str(db_path))
    try:
        if elo_after is None:
            elo_after = 100 + delta
        conn.execute(
            "INSERT INTO ranked_challenge "
            "(user_id, beatmap_id, beatmap_title, stars, status, accuracy, elo_delta, elo_after, "
            "issued_at, deadline_at, settled_at) "
            "VALUES (?, 10, 'Artist - Song [Insane]', ?, ?, ?, ?, ?, "
            "'2026-01-01 00:00:00', '2026-01-01 00:10:00', '2026-01-01 00:05:00')",
            (uid, stars, status, accuracy, delta, elo_after),
        )
        conn.commit()
    finally:
        conn.close()


def test_ranked_stats_requires_auth(client):
    c, _ = client
    assert c.get("/api/ranked/stats").status_code == 401


def test_ranked_stats_empty(client):
    c, db_path = client
    headers, _uid, _osu_id = _auth(db_path, next(_osu_id_seq))
    r = c.get("/api/ranked/stats", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["total_settled"] == 0
    assert body["passed"] == 0
    assert body["failed"] == 0
    assert body["rerolled"] == 0
    assert body["wins"] == 0
    assert body["losses"] == 0
    assert body["draws"] == 0
    assert body["win_rate"] == 0.0
    assert body["best_accuracy"] is None
    assert body["current_elo"] == 100
    assert body["tier"] == "Базовый"
    assert body["star_window"] == {"min": 0.5, "max": 1.0, "target": 0.75}
    assert body["sub_rank"] is None
    assert body["last_results"] == []


def test_ranked_stats_mixed(client):
    c, db_path = client
    headers, uid, _osu_id = _auth(db_path, next(_osu_id_seq))
    _insert_ranked_challenge(db_path, uid, "passed", stars=5.0, accuracy=0.95, delta=10)
    _insert_ranked_challenge(db_path, uid, "failed", stars=4.0, accuracy=0.80, delta=-10)
    _insert_ranked_challenge(db_path, uid, "surrendered", stars=6.0, accuracy=0.90, delta=-10)
    _insert_ranked_challenge(db_path, uid, "rerolled", stars=5.5, accuracy=0.0, delta=-2)

    r = c.get("/api/ranked/stats", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["passed"] == 1
    assert body["failed"] == 2  # failed + surrendered
    assert body["rerolled"] == 1
    assert body["wins"] == 1
    assert body["losses"] == 2
    assert body["draws"] == 0
    assert body["total_settled"] == 4
    assert body["win_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert body["best_accuracy"] == pytest.approx(0.95)
    assert body["avg_accuracy"] == pytest.approx(0.95)
    assert body["hardest_passed_stars"] == pytest.approx(5.0)
    assert body["best_elo_gain"] == 10
    assert len(body["last_results"]) == 4


def test_ranked_stats_wld_mixed_and_consistent(client):
    c, db_path = client
    headers, uid, osu_id = _auth(db_path, next(_osu_id_seq))
    _insert_ranked_state(db_path, uid, 100)
    _insert_ranked_challenge(db_path, uid, "passed", delta=30)
    _insert_ranked_challenge(db_path, uid, "passed", delta=0)
    _insert_ranked_challenge(db_path, uid, "passed", delta=-15)
    # Fail at the ELO floor: stored delta is -60, actual ELO stays 100.
    _insert_ranked_challenge(db_path, uid, "failed", delta=-60, elo_after=100)
    _insert_ranked_challenge(db_path, uid, "surrendered", delta=-60, elo_after=100)
    _insert_ranked_challenge(db_path, uid, "expired", delta=-60, elo_after=100)
    _insert_ranked_challenge(db_path, uid, "rerolled", delta=-5, elo_after=100)

    stats_body = c.get("/api/ranked/stats", headers=headers).json()
    public_body = c.get(f"/api/players/{osu_id}/ranked").json()
    rows = c.get("/api/ranked/leaderboard").json()
    row = next(r for r in rows if r["osu_id"] == osu_id)

    for body in (stats_body, public_body, row):
        assert body["wins"] == 1  # only +30
        assert body["losses"] == 4  # pass -15, fail, surrender, timeout
        assert body["draws"] == 1  # pass with delta 0
        assert body["win_rate"] == pytest.approx(1 / 6, abs=1e-4)

    # Existing counters are unchanged; rerolls are counted separately.
    assert stats_body["passed"] == 3
    assert stats_body["failed"] == 3
    assert stats_body["rerolled"] == 1
    assert stats_body["total_settled"] == 7
    assert public_body["passed"] == 3
    assert public_body["failed"] == 3
    # Leaderboard games = all closed challenges except rerolls.
    assert row["games"] == 6


def test_ranked_stats_disabled(client, monkeypatch):
    c, db_path = client
    headers, _uid, _osu_id = _auth(db_path, next(_osu_id_seq))
    monkeypatch.setenv("RANKED_ENABLED", "false")
    r = c.get("/api/ranked/stats", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


# --------------------------------------------------------------------------- #
# /api/ranked/info (public rules)
# --------------------------------------------------------------------------- #


def test_ranked_info(client):
    c, _ = client
    r = c.get("/api/ranked/info")  # no auth
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    # Tier table with ELO + star ranges.
    assert len(body["tiers"]) >= 3
    first = body["tiers"][0]
    assert first["name"] == "Базовый"
    assert "min_elo" in first and "min_stars" in first and "max_stars" in first
    # Accuracy reward + rules present (new table, no threshold).
    assert body["acc_reward_table"] == [[0.70, -60], [0.90, 0], [1.0, 60]]
    assert "acc_threshold" not in body
    assert body["fail_delta"] == -60
    assert body["nf_ht_penalty"] == -10
    assert body["ez_bonus"]["bonus_low"] == 10
    assert body["ez_bonus"]["bonus_high"] == 20
    assert body["clamp"] == {"min": -60, "max": 80}
    assert body["start_elo"] == 100 and body["elo_floor"] == 100  # env override in tests
    assert body["star_window"] == 0.15
    assert body["sub_rank_segments"] == 4
    assert body["timeout"]["tolerance_seconds"] == 120
    assert body["reroll"]["daily_limit"] == 3
    assert body["forbidden_mods"][0]["code"] == "RX"
    # No secrets.
    for key in ("osu_client_id", "osu_client_secret", "jwt_secret", "database_url"):
        assert key not in body


def test_ranked_info_disabled(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("RANKED_ENABLED", "false")
    r = c.get("/api/ranked/info")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


# --------------------------------------------------------------------------- #
# /api/ranked/leaderboard (extended)
# --------------------------------------------------------------------------- #


def _insert_ranked_state(db_path, uid, elo):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO ranked_state (user_id, elo) VALUES (?, ?)", (uid, elo)
        )
        conn.commit()
    finally:
        conn.close()


def test_ranked_leaderboard_extended_and_pagination(client):
    c, db_path = client
    _, uid_a, osu_id_a = _auth(db_path, next(_osu_id_seq))
    _, uid_b, osu_id_b = _auth(db_path, next(_osu_id_seq))
    _insert_ranked_state(db_path, uid_a, 200)
    _insert_ranked_state(db_path, uid_b, 150)
    _insert_ranked_challenge(db_path, uid_a, "passed", stars=5.0, accuracy=0.98, delta=20)
    _insert_ranked_challenge(db_path, uid_b, "failed", stars=4.0, accuracy=0.80, delta=-10)

    r = c.get("/api/ranked/leaderboard")  # no auth
    assert r.status_code == 200
    rows = r.json()
    # The two fresh users have the highest ELO -> they lead the board.
    assert rows[0]["osu_id"] == osu_id_a
    assert rows[0]["elo"] == 200
    assert rows[0]["tier"] == "Серебро"
    assert rows[0]["sub_rank"] == {"filled": 1, "total": 4}
    assert rows[0]["rank"] == 1
    assert rows[0]["games"] == 1
    assert rows[0]["wins"] == 1
    assert rows[0]["losses"] == 0
    assert rows[0]["draws"] == 0
    assert rows[0]["win_rate"] == 1.0
    assert rows[1]["rank"] == 2
    assert rows[1]["osu_id"] == osu_id_b
    assert rows[1]["sub_rank"] == {"filled": 2, "total": 4}
    assert rows[1]["wins"] == 0
    assert rows[1]["losses"] == 1
    assert rows[1]["draws"] == 0
    assert rows[1]["win_rate"] == 0.0

    # Pagination: offset skips the first row and re-ranks.
    r2 = c.get("/api/ranked/leaderboard?limit=1&offset=1")
    assert r2.status_code == 200
    rows2 = r2.json()
    assert len(rows2) == 1
    assert rows2[0]["rank"] == 2
    assert rows2[0]["osu_id"] == osu_id_b


# --------------------------------------------------------------------------- #
# /api/players/{osu_id}/ranked (public player stats)
# --------------------------------------------------------------------------- #


def _insert_ranked_full(
    db_path,
    uid,
    status,
    *,
    stars=5.0,
    accuracy=0.95,
    delta=10,
    elo_after=110,
    grade="S",
    mods="NM",
    beatmapset_id=1,
    version="Insane",
    length_sec=120,
    settled_at="2026-01-01 00:05:00",
):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO ranked_challenge "
            "(user_id, beatmap_id, beatmapset_id, beatmap_title, artist, version, "
            "stars, length_sec, status, accuracy, grade, mods, elo_delta, elo_after, "
            "issued_at, deadline_at, settled_at) "
            "VALUES (?, 10, ?, 'Artist - Song [Insane]', 'Artist', ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "'2026-01-01 00:00:00', '2026-01-01 00:10:00', ?)",
            (
                uid,
                beatmapset_id,
                version,
                stars,
                length_sec,
                status,
                accuracy,
                grade,
                mods,
                delta,
                elo_after,
                settled_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_public_ranked_404(client):
    c, _ = client
    assert c.get("/api/players/99999999/ranked").status_code == 404


def test_public_ranked_empty(client):
    c, db_path = client
    headers, _uid, osu_id = _auth(db_path, next(_osu_id_seq))
    r = c.get(f"/api/players/{osu_id}/ranked")  # no auth
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["current_elo"] == 100  # start ELO, no error
    assert body["tier"] == "Базовый"
    assert body["star_window"] == {"min": 0.5, "max": 1.0, "target": 0.75}
    assert body["sub_rank"] is None
    assert body["passed"] == 0
    assert body["failed"] == 0
    assert body["wins"] == 0
    assert body["losses"] == 0
    assert body["draws"] == 0
    assert body["win_rate"] == 0.0
    assert body["best_accuracy"] is None
    assert body["last_results"] == []
    assert body["elo_history"] == []


def test_public_ranked_mixed(client):
    c, db_path = client
    headers, uid, osu_id = _auth(db_path, next(_osu_id_seq))
    _insert_ranked_state(db_path, uid, 500)
    _insert_ranked_full(
        db_path, uid, "passed", stars=5.0, accuracy=0.98, delta=20, elo_after=520,
        grade="S", mods="HD", beatmapset_id=7, version="Insane", length_sec=120,
        settled_at="2026-01-01 00:05:00",
    )
    _insert_ranked_full(
        db_path, uid, "failed", stars=4.0, accuracy=0.80, delta=-10, elo_after=510,
        grade="D", mods="NM", beatmapset_id=8, version="Hard", length_sec=90,
        settled_at="2026-01-01 00:06:00",
    )
    _insert_ranked_full(
        db_path, uid, "surrendered", stars=6.0, accuracy=0.0, delta=-10, elo_after=500,
        grade="", mods="", beatmapset_id=9, version="Expert", length_sec=150,
        settled_at="2026-01-01 00:07:00",
    )

    r = c.get(f"/api/players/{osu_id}/ranked")  # no auth
    assert r.status_code == 200
    body = r.json()
    assert body["current_elo"] == 500
    assert body["tier"] == "Золото"
    assert body["star_window"] == {"min": 3.85, "max": 4.15, "target": 4.0}
    assert body["sub_rank"] == {"filled": 1, "total": 4}
    assert body["passed"] == 1
    assert body["failed"] == 2  # failed + surrendered
    assert body["wins"] == 1
    assert body["losses"] == 2
    assert body["draws"] == 0
    assert body["win_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert body["best_accuracy"] == pytest.approx(0.98)
    assert body["avg_accuracy"] == pytest.approx(0.98)
    assert body["hardest_passed_stars"] == pytest.approx(5.0)
    assert body["best_elo_gain"] == 20

    # tier_thresholds: public tier table (name + ELO bound) for the chart lines.
    assert body["tier_thresholds"][0] == {"name": "Базовый", "min_elo": 100}
    assert body["tier_thresholds"][-1]["name"] == "Легенда"
    assert all(set(t) == {"name", "min_elo"} for t in body["tier_thresholds"])

    # last_results: full public card fields, most recent first.
    assert len(body["last_results"]) == 3
    lr = body["last_results"][0]
    assert lr["status"] == "surrendered"  # id desc
    for field in (
        "beatmap_id", "beatmapset_id", "title", "stars", "length_sec",
        "version", "status", "elo_delta", "accuracy", "grade", "mods", "settled_at",
    ):
        assert field in lr

    # elo_history: start point first, then chronological ascending.
    assert [h["elo_after"] for h in body["elo_history"]] == [100, 520, 510, 500]
    assert body["elo_history"][0]["label"] == "старт"
    assert body["elo_history"][0]["date"] is not None

    # Nothing private leaks.
    assert "active" not in body
    assert "download_url" not in body
    assert "download_url" not in lr
    for key in ("osu_access_token", "osu_refresh_token"):
        assert key not in body and key not in lr


def test_public_ranked_disabled(client, monkeypatch):
    c, db_path = client
    headers, _uid, osu_id = _auth(db_path, next(_osu_id_seq))
    monkeypatch.setenv("RANKED_ENABLED", "false")
    r = c.get(f"/api/players/{osu_id}/ranked")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


def test_public_ranked_elo_history_start_point(client):
    c, db_path = client
    headers, uid, osu_id = _auth(db_path, next(_osu_id_seq))
    _insert_ranked_state(db_path, uid, 110)
    _insert_ranked_full(
        db_path, uid, "passed", delta=10, elo_after=110,
        settled_at="2026-01-01 00:05:00",
    )

    r = c.get(f"/api/players/{osu_id}/ranked")  # no auth
    assert r.status_code == 200
    hist = r.json()["elo_history"]
    # Start point is first, dated at the first challenge, at the starting ELO.
    assert len(hist) == 2
    assert hist[0]["elo_after"] == 100  # RANKED_START_ELO=100 in tests
    assert hist[0]["label"] == "старт"
    assert hist[0]["date"] is not None
    assert hist[1]["elo_after"] == 110
    assert hist[1].get("label") is None


# --------------------------------------------------------------------------- #
# Pages (/ranked and existing pages still render)
# --------------------------------------------------------------------------- #


def test_ranked_page_200(client):
    c, _ = client
    r = c.get("/ranked")
    assert r.status_code == 200
    text = r.text
    assert "/static/ranked.js" in text
    assert 'href="/ranked"' in text  # nav item
    assert "Ranked" in text


def test_existing_pages_still_200(client):
    c, _ = client
    for path in ("/", "/players", "/profile", "/score/1"):
        assert c.get(path).status_code == 200, path


def test_profile_page_loads_ranked_js(client):
    c, _ = client
    r = c.get("/profile")
    assert r.status_code == 200
    assert "/static/ranked.js" in r.text
    assert 'id="rankedCard"' in r.text
