"""Tests for server.beatmap_picker query behaviour (no real osu! API)."""
from __future__ import annotations

import asyncio

from server.beatmap_picker import (
    _eligible,
    fetch_challenge_maps,
    fetch_personal_challenge_maps,
)
from server.config import ServerConfig


def _run(coro):
    return asyncio.run(coro)


def _config() -> ServerConfig:
    return ServerConfig(osu_client_id="id", osu_client_secret="secret")


def _patch(monkeypatch, calls):
    async def fake_token(config):
        return "token"

    async def fake_search_page(client, headers, q, status, page=None):
        calls.append((q, status, page))
        return []

    monkeypatch.setattr("server.beatmap_picker.get_osu_client_token", fake_token)
    monkeypatch.setattr("server.beatmap_picker._search_page", fake_search_page)


def test_daily_challenge_uses_legacy_query(monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    _run(fetch_challenge_maps(_config(), count=3))
    assert calls, "expected at least one search request"
    for q, status, _page in calls:
        assert status == "ranked"
        assert "stars" not in q
        assert len(q) == 2  # random 2-char query


def test_ranked_uses_star_query(monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    _run(fetch_challenge_maps(_config(), count=1, min_stars=5.0, max_stars=6.0))
    assert calls, "expected at least one search request"
    for q, status, page in calls:
        assert "stars>=5" in q
        assert "stars<6" in q
        assert status == "ranked"
        assert page == 1


def test_ranked_top_tier_no_upper_bound(monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    _run(fetch_challenge_maps(_config(), count=1, min_stars=9.0, max_stars=None))
    for q, _status, _page in calls:
        assert "stars>=9" in q
        assert "stars<" not in q  # no upper bound


def test_eligible_exclusive_vs_inclusive():
    bm = {"difficulty_rating": 7.0, "total_length": 120, "mode": "osu"}
    # Legacy daily challenge: 7.0 is allowed (inclusive upper bound).
    assert _eligible(bm, 4.0, 7.0, 0, 600, exclusive_max=False) is True
    # Ranked: 7.0 is rejected (exclusive upper bound).
    assert _eligible(bm, 4.0, 7.0, 0, 600, exclusive_max=True) is False


def test_personal_picker_scans_whole_library(monkeypatch):
    """An eligible map must be found even if it sits beyond the old 25-map sample."""
    local_ids = list(range(1, 501))
    eligible_bid = 450

    async def fake_token(config):
        return "token"

    async def fake_lookup(client, headers, bid):
        if bid == eligible_bid:
            return {
                "id": bid,
                "version": "Insane",
                "difficulty_rating": 5.0,
                "total_length": 120,
                "mode": "osu",
                "beatmapset": {"id": 100, "artist": "Artist", "title": "Title"},
            }
        return None

    async def fake_fetch_challenge_maps(config, count=5, **kwargs):
        return []  # no random filler for this test

    monkeypatch.setattr("server.beatmap_picker.get_osu_client_token", fake_token)
    monkeypatch.setattr("server.beatmap_picker._lookup_beatmap", fake_lookup)
    monkeypatch.setattr(
        "server.beatmap_picker.fetch_challenge_maps", fake_fetch_challenge_maps
    )

    result = _run(fetch_personal_challenge_maps(_config(), local_ids, count=5))
    assert [m["beatmap_id"] for m in result] == [eligible_bid]
