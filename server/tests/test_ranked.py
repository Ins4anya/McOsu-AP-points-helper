"""Tests for server.ranked (ELO mode) against the real 0009 schema."""
from __future__ import annotations

import asyncio
import itertools
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.database import RankedChallenge, RankedState, Score, User
from server.ranked import (
    RankedNoMaps,
    RankedRerollLimit,
    get_or_create_state,
    issue,
    ranked_settings_from_config,
    reroll,
    serialize,
    settle_expired,
    settle_from_db,
    surrender,
    try_settle,
)
from server.ranked_rules import as_utc

SERVER_DIR = Path(__file__).resolve().parents[1]
UTC = timezone.utc

_key_seq = itertools.count()


def dt(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


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
MAP2 = dict(MAP, beatmap_id=11, beatmap_title="Artist - Song [Expert]")


def _migrate(db_path: Path) -> None:
    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")


def run_test(tmp_path, scenario) -> None:
    db_path = tmp_path / "ranked.db"
    _migrate(db_path)

    async def _run() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        Session = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with Session() as db:
                await scenario(db)
        finally:
            await engine.dispose()

    asyncio.run(_run())


async def _user(db, osu_id: int = 1, name: str = "u") -> User:
    u = User(
        osu_id=osu_id,
        username=name,
        avatar_url="",
        osu_access_token="t",
        osu_refresh_token="r",
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _score(
    db,
    user,
    *,
    beatmap_id: int = 10,
    title: str = "Artist - Song [Insane]",
    played_at: datetime,
    grade: str = "S",
    accuracy: float = 0.97,
    mods: str = "NM",
) -> Score:
    s = Score(
        user_id=user.id,
        beatmap_id=beatmap_id,
        beatmap_title=title,
        beatmap_url="",
        mods=mods,
        accuracy=accuracy,
        max_combo=100,
        max_possible_combo=100,
        pp=100.0,
        ap=100.0,
        rank=grade,
        score_key=f"k{next(_key_seq)}",
        played_at=played_at,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


def fixed_picker(maps):
    """Async fake picker: first map whose beatmap_id isn't excluded."""

    async def picker(lo, hi, exclude=None):
        exclude = exclude or []
        for m in maps:
            if m["beatmap_id"] not in exclude:
                return m
        return None

    return picker


def recording_picker(responses):
    """Async fake picker that returns queued responses and records its calls."""
    calls = []

    async def picker(lo, hi, exclude=None):
        calls.append((lo, hi, exclude))
        return responses.pop(0) if responses else None

    return picker, calls


# --------------------------------------------------------------------------- #
# Issue
# --------------------------------------------------------------------------- #

def test_issue_creates_state_and_challenge(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        assert ch.status == "active"
        assert ch.beatmap_id == 10
        assert ch.stars == 5.0
        assert as_utc(ch.issued_at) == now
        st = await get_or_create_state(db, user)
        assert st.elo == 500
    run_test(tmp_path, scenario)


def test_issue_existing_active_returns_it(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch1 = await issue(db, user, fixed_picker([MAP]), now)
        ch2 = await issue(db, user, fixed_picker([MAP2]), now)
        assert ch2.id == ch1.id
        cnt = (await db.execute(
            select(func.count()).select_from(RankedChallenge).where(
                RankedChallenge.user_id == user.id,
                RankedChallenge.status == "active",
            )
        )).scalar()
        assert cnt == 1
    run_test(tmp_path, scenario)


def test_issue_exclude_recent_then_retry_without_exclude(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        # close a challenge on beatmap 10 so it lands in the recent list.
        await issue(db, user, fixed_picker([MAP]), now)
        await surrender(db, user, now)

        # Gold at ELO 500 has a 4-step ladder: four misses with the exclusion,
        # then the fifth call is the first without it.
        picker, calls = recording_picker([None, None, None, None, MAP2])
        ch = await issue(db, user, picker, now)
        assert ch.beatmap_id == 11
        assert 10 in calls[0][2]  # first call excluded the recent beatmap
        assert calls[4][2] is None  # retry without exclusion
    run_test(tmp_path, scenario)


def test_issue_ladder_windows_order(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        picker, calls = recording_picker([None, None, None, MAP2])
        await issue(db, user, picker, now)
        windows = [(round(lo, 2), round(hi, 2)) for lo, hi, _ in calls]
        assert windows == [(3.85, 4.15), (3.7, 4.3), (3.4, 4.6), (4.0, 5.0)]
        assert all(call[2] == [] for call in calls)  # nothing excluded yet
    run_test(tmp_path, scenario)


def test_issue_ladder_base_has_single_window(tmp_path):
    async def scenario(db):
        user = await _user(db)
        st = await get_or_create_state(db, user)
        st.elo = 100
        await db.commit()
        picker, calls = recording_picker([MAP])
        await issue(db, user, picker, dt(2026, 1, 1, 12, 0, 0))
        assert len(calls) == 1
        assert calls[0][0] == pytest.approx(0.5)
        assert calls[0][1] == pytest.approx(1.0)
    run_test(tmp_path, scenario)


def test_issue_ladder_professional_open_upper_bound(tmp_path):
    async def scenario(db):
        user = await _user(db)
        st = await get_or_create_state(db, user)
        st.elo = 4000
        await db.commit()
        picker, calls = recording_picker([None, None, None, MAP])
        await issue(db, user, picker, dt(2026, 1, 1, 12, 0, 0))
        assert len(calls) == 4
        assert calls[3][0] == pytest.approx(9.0)
        assert calls[3][1] is None
    run_test(tmp_path, scenario)


def test_issue_no_maps_raises(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        with pytest.raises(RankedNoMaps):
            await issue(db, user, fixed_picker([]), now)
        # nothing persisted
        cnt = (await db.execute(
            select(func.count()).select_from(RankedChallenge)
        )).scalar()
        assert cnt == 0
    run_test(tmp_path, scenario)


# --------------------------------------------------------------------------- #
# Settle: pass / fail / invalid
# --------------------------------------------------------------------------- #

def test_full_cycle_pass(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        score = await _score(db, user, beatmap_id=10, played_at=now, grade="S", accuracy=0.95)
        await try_settle(db, user, score, now)
        await db.commit()
        ch = await db.get(RankedChallenge, ch.id)
        assert ch.status == "passed"
        assert ch.elo_delta == 30
        assert ch.result_score_id == score.id
        st = await get_or_create_state(db, user)
        assert st.elo == 530
    run_test(tmp_path, scenario)


def test_full_cycle_fail(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        score = await _score(db, user, beatmap_id=10, played_at=now, grade="D", accuracy=0.5)
        await try_settle(db, user, score, now)
        await db.commit()
        ch = await db.get(RankedChallenge, ch.id)
        assert ch.status == "failed"
        assert ch.elo_delta == -60
        st = await get_or_create_state(db, user)
        assert st.elo == 440
    run_test(tmp_path, scenario)


def test_full_cycle_fail_ignores_mods(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        score = await _score(
            db, user, beatmap_id=10, played_at=now, grade="D", accuracy=0.99, mods="+NFHTEZ"
        )
        await try_settle(db, user, score, now)
        await db.commit()
        ch = await db.get(RankedChallenge, ch.id)
        assert ch.status == "failed"
        assert ch.elo_delta == -60
        st = await get_or_create_state(db, user)
        assert st.elo == 440
    run_test(tmp_path, scenario)


def test_forbidden_mod_leaves_active(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        score = await _score(db, user, beatmap_id=10, played_at=now, grade="S", accuracy=0.97, mods="+RX")
        await try_settle(db, user, score, now)
        await db.commit()
        ch = await db.get(RankedChallenge, ch.id)
        assert ch.status == "active"
        st = await get_or_create_state(db, user)
        assert st.elo == 500
    run_test(tmp_path, scenario)


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #

def test_repeated_try_settle_does_not_double_elo(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        score = await _score(db, user, beatmap_id=10, played_at=now, grade="S", accuracy=0.95)
        await try_settle(db, user, score, now)
        await db.commit()
        await try_settle(db, user, score, now)  # no active challenge now
        await db.commit()
        st = await get_or_create_state(db, user)
        assert st.elo == 530  # applied exactly once
    run_test(tmp_path, scenario)


def test_two_sequential_settles_only_one_wins(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        s1 = await _score(db, user, beatmap_id=10, played_at=now, grade="S", accuracy=0.95)
        await try_settle(db, user, s1, now)
        await db.commit()
        s2 = await _score(db, user, beatmap_id=10, played_at=now, grade="S", accuracy=0.95)
        res = await try_settle(db, user, s2, now)
        assert res is None
        st = await get_or_create_state(db, user)
        assert st.elo == 530
    run_test(tmp_path, scenario)


# --------------------------------------------------------------------------- #
# Map / window matching
# --------------------------------------------------------------------------- #

def test_wrong_map_not_settled(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)  # beatmap_id 10
        score = await _score(db, user, beatmap_id=99, played_at=now, grade="S", accuracy=0.97)
        res = await try_settle(db, user, score, now)
        assert res is None
        await db.commit()
        ch = await db.get(RankedChallenge, ch.id)
        assert ch.status == "active"
    run_test(tmp_path, scenario)


def test_tolerance_window_boundary(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        issued = ch.issued_at
        ok = await _score(db, user, beatmap_id=10, played_at=issued - timedelta(seconds=120), grade="S", accuracy=0.97)
        r = await try_settle(db, user, ok, now)
        await db.commit()
        assert r is not None and r.status == "passed"

        ch2 = await issue(db, user, fixed_picker([MAP2]), now)
        bad = await _score(db, user, beatmap_id=11, played_at=ch2.issued_at - timedelta(seconds=121), grade="S", accuracy=0.97)
        r2 = await try_settle(db, user, bad, now)
        assert r2 is None
    run_test(tmp_path, scenario)


# --------------------------------------------------------------------------- #
# settle_from_db
# --------------------------------------------------------------------------- #

def test_same_title_different_beatmap_id_not_settled(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)  # beatmap_id 10, title "Artist - Song [Insane]"
        score = await _score(db, user, beatmap_id=99, title="Artist - Song [Insane]", played_at=now, grade="S", accuracy=0.97)
        res = await settle_from_db(db, user, now)
        assert res is None
        await db.commit()
        ch = await db.get(RankedChallenge, ch.id)
        assert ch.status == "active"
    run_test(tmp_path, scenario)


def test_settle_from_db_score_already_in_db(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        await issue(db, user, fixed_picker([MAP]), now)
        score = await _score(db, user, beatmap_id=10, played_at=now, grade="S", accuracy=0.97)
        # settle_from_db scans the DB (no incoming score passed).
        res = await settle_from_db(db, user, now)
        await db.commit()
        assert res.status == "passed"
        assert res.result_score_id == score.id
    run_test(tmp_path, scenario)


def test_settle_from_db_earliest_played_wins(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        issued = ch.issued_at
        # Inserted in reverse order of played_at.
        await _score(db, user, beatmap_id=10, played_at=issued + timedelta(seconds=60), grade="S", accuracy=0.97)
        early = await _score(db, user, beatmap_id=10, played_at=issued + timedelta(seconds=30), grade="D", accuracy=0.5)
        res = await settle_from_db(db, user, issued + timedelta(seconds=120))
        await db.commit()
        assert res.status == "failed"  # earliest played score (D) wins
        assert res.result_score_id == early.id
    run_test(tmp_path, scenario)


def test_settle_from_db_invalid_skipped(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        issued = ch.issued_at
        await _score(db, user, beatmap_id=10, played_at=issued + timedelta(seconds=10), grade="S", accuracy=0.97, mods="+RX")
        good = await _score(db, user, beatmap_id=10, played_at=issued + timedelta(seconds=20), grade="S", accuracy=0.97)
        res = await settle_from_db(db, user, issued + timedelta(seconds=120))
        await db.commit()
        assert res.status == "passed"
        assert res.result_score_id == good.id  # invalid (RX) skipped
    run_test(tmp_path, scenario)


def test_settle_from_db_out_of_window_ignored(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        issued = ch.issued_at
        await _score(db, user, beatmap_id=10, played_at=issued - timedelta(seconds=300), grade="S", accuracy=0.97)
        res = await settle_from_db(db, user, now)
        assert res is None
        await db.commit()
        ch = await db.get(RankedChallenge, ch.id)
        assert ch.status == "active"
    run_test(tmp_path, scenario)


def test_settle_from_db_repeated_no_double_elo(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        await issue(db, user, fixed_picker([MAP]), now)
        await _score(db, user, beatmap_id=10, played_at=now, grade="S", accuracy=0.95)
        await settle_from_db(db, user, now)
        await db.commit()
        await settle_from_db(db, user, now)  # no active challenge now
        await db.commit()
        st = await get_or_create_state(db, user)
        assert st.elo == 530
    run_test(tmp_path, scenario)


# --------------------------------------------------------------------------- #
# Timeout / grace
# --------------------------------------------------------------------------- #

def test_grace_window_accepts_late_arrival(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        deadline = ch.deadline_at  # now + 600s (length 120 * 3 -> floored to 600)
        played = deadline - timedelta(seconds=60)  # before deadline
        arrive = deadline + timedelta(seconds=200)  # after deadline, within 300s grace
        score = await _score(db, user, beatmap_id=10, played_at=played, grade="S", accuracy=0.97)
        res = await try_settle(db, user, score, arrive)
        await db.commit()
        assert res is not None and res.status == "passed"
    run_test(tmp_path, scenario)


def test_score_after_deadline_not_settled(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        deadline = ch.deadline_at
        played = deadline + timedelta(seconds=10)  # after deadline
        score = await _score(db, user, beatmap_id=10, played_at=played, grade="S", accuracy=0.97)
        res = await try_settle(db, user, score, now)
        assert res is None
        await db.commit()
        ch = await db.get(RankedChallenge, ch.id)
        assert ch.status == "active"
    run_test(tmp_path, scenario)


def test_lazy_expiry(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        ch = await issue(db, user, fixed_picker([MAP]), now)
        later = now + timedelta(seconds=600 + 301)  # past deadline + grace
        result = await settle_expired(db, user, later)
        assert result is not None
        assert result.status == "expired"
        assert result.elo_delta == -60
        st = await get_or_create_state(db, user)
        assert st.elo == 440
    run_test(tmp_path, scenario)


# --------------------------------------------------------------------------- #
# Surrender / reroll
# --------------------------------------------------------------------------- #

def test_surrender(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        await issue(db, user, fixed_picker([MAP]), now)
        res = await surrender(db, user, now)
        assert res.status == "surrendered"
        assert res.elo_delta == -60
        st = await get_or_create_state(db, user)
        assert st.elo == 440
    run_test(tmp_path, scenario)


def test_reroll_penalty_and_new_challenge(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        st = await get_or_create_state(db, user)
        st.elo = 200
        await db.commit()
        old = await issue(db, user, fixed_picker([MAP]), now)
        new = await reroll(db, user, fixed_picker([MAP2]), now)
        assert new.id != old.id and new.status == "active"
        old_ch = await db.get(RankedChallenge, old.id)
        assert old_ch.status == "rerolled"
        assert old_ch.elo_delta == -5
        st = await get_or_create_state(db, user)
        assert st.elo == 195
    run_test(tmp_path, scenario)


def test_reroll_floor_100(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        st = await get_or_create_state(db, user)
        st.elo = 100
        await db.commit()
        await issue(db, user, fixed_picker([MAP]), now)
        new = await reroll(db, user, fixed_picker([MAP2]), now)
        assert new.status == "active"
        st = await get_or_create_state(db, user)
        assert st.elo == 100  # -5 floored
    run_test(tmp_path, scenario)


def test_reroll_daily_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("server.ranked.today_str", lambda: "2026-01-01")
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        st = await get_or_create_state(db, user)
        st.rerolls_today = 3
        st.reroll_date = "2026-01-01"
        await db.commit()
        old = await issue(db, user, fixed_picker([MAP]), now)
        with pytest.raises(RankedRerollLimit):
            await reroll(db, user, fixed_picker([MAP2]), now)
        old_ch = await db.get(RankedChallenge, old.id)
        assert old_ch.status == "active"
        st = await get_or_create_state(db, user)
        assert st.elo == 500
    run_test(tmp_path, scenario)


def test_reroll_reset_on_new_day(tmp_path, monkeypatch):
    monkeypatch.setattr("server.ranked.today_str", lambda: "2026-01-01")
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        st = await get_or_create_state(db, user)
        st.rerolls_today = 3
        st.reroll_date = "2025-12-31"
        await db.commit()
        await issue(db, user, fixed_picker([MAP]), now)
        new = await reroll(db, user, fixed_picker([MAP2]), now)
        assert new.status == "active"
        st = await get_or_create_state(db, user)
        assert st.rerolls_today == 1  # reset then incremented
    run_test(tmp_path, scenario)


def test_reroll_picker_failure_no_elo_change(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        st = await get_or_create_state(db, user)
        st.elo = 200
        await db.commit()
        old = await issue(db, user, fixed_picker([MAP]), now)
        with pytest.raises(RankedNoMaps):
            await reroll(db, user, fixed_picker([]), now)
        old_ch = await db.get(RankedChallenge, old.id)
        assert old_ch.status == "active"
        st = await get_or_create_state(db, user)
        assert st.elo == 200  # unchanged
    run_test(tmp_path, scenario)


def test_reroll_picks_by_elo_before_penalty(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        st = await get_or_create_state(db, user)
        st.elo = 500  # Gold, target 4.0 -> first window [3.85, 4.15)
        await db.commit()
        await issue(db, user, fixed_picker([MAP]), now)

        picker, calls = recording_picker([MAP2])
        await reroll(db, user, picker, now)
        assert calls[0][0] == pytest.approx(3.85)
        assert calls[0][1] == pytest.approx(4.15)
        st = await get_or_create_state(db, user)
        assert st.elo == 495  # penalty applied after the pick
    run_test(tmp_path, scenario)


def test_ranked_settings_from_config_reroll_sign(tmp_path):
    from server.config import ServerConfig

    settings = ranked_settings_from_config(ServerConfig())
    # Sign consistency: config stores signed penalties, no double negation.
    assert settings.reroll_penalty == -5
    assert settings.fail_delta == -60
    assert settings.nf_ht_penalty == -10

    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        st = await get_or_create_state(db, user, settings)
        st.elo = 200
        await db.commit()
        await issue(db, user, fixed_picker([MAP]), now, settings)
        await reroll(db, user, fixed_picker([MAP2]), now, settings)
        st = await get_or_create_state(db, user, settings)
        assert st.elo == 195  # exactly -5 (not -10, not +5)
    run_test(tmp_path, scenario)


# --------------------------------------------------------------------------- #
# Serialize
# --------------------------------------------------------------------------- #

def test_serialize(tmp_path):
    async def scenario(db):
        user = await _user(db)
        now = dt(2026, 1, 1, 12, 0, 0)
        await issue(db, user, fixed_picker([MAP]), now)
        view = await serialize(db, user, now)
        assert view["elo"] == 500
        assert view["tier"] == "Золото"
        assert view["star_range"] == {"min": 4.0, "max": 5.0}
        assert view["star_window"] == {"min": 3.85, "max": 4.15, "target": 4.0}
        assert view["sub_rank"] == {"filled": 1, "total": 4}
        assert view["reroll_penalty"] == -5
        assert view["fail_delta"] == -60
        assert view["active"] is not None
        assert view["active"]["beatmap_id"] == 10
        assert "таблице точности" in view["active"]["condition"]
        assert "95" not in view["active"]["condition"]
        assert view["rerolls_left"] == 3
    run_test(tmp_path, scenario)
