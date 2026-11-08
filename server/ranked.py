"""Ranked (ELO) mode — business logic, mirrors ``server.challenge`` style.

Everything is driven by :class:`server.ranked_rules.RankedSettings`; the
server's tunable values come from :func:`ranked_settings_from_config`. ``now``
is always passed in as an argument for testability, and all date comparisons
go through ``ranked_rules.as_utc``.

The map ``picker`` is an injected callable
``picker(star_min, star_max, exclude_beatmap_ids) -> dict | None`` returning
``{"beatmap_id", "beatmapset_id", "beatmap_title", "artist", "version",
"stars", "length", "download_url"}`` (or ``None`` when no maps match).
:func:`ranked_picker` adapts ``server.beatmap_picker`` to this shape; tests use
a fake picker.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import ServerConfig
from server.database import RankedChallenge, RankedState, Score, User
from server.dates import today_str
from server.ranked_rules import (
    DEFAULT_SETTINGS,
    DEFAULT_TIERS,
    RankedSettings,
    apply_delta,
    as_utc,
    evaluate,
    normalize_grade,
    progress_to_next,
    star_ladder,
    star_range,
    star_window,
    sub_rank,
    tier_for,
    timeout_seconds,
)


class RankedError(Exception):
    """Base error for ranked operations."""


class RankedNoMaps(RankedError):
    """No eligible maps were found for the requested star range."""


class RankedRerollLimit(RankedError):
    """Daily reroll limit reached."""


# Statuses that mean a challenge is no longer open.
CLOSED_STATUSES = {"passed", "failed", "surrendered", "expired", "rerolled"}

Picker = Callable[[float, Optional[float], Optional[list[int]]], Any]


def ranked_settings_from_config(config: ServerConfig) -> RankedSettings:
    """Build a :class:`RankedSettings` from the server config (step 4)."""
    return RankedSettings(
        tiers=DEFAULT_TIERS,
        elo_floor=config.ranked_elo_floor,
        start_elo=config.ranked_start_elo,
        acc_reward_table=config.ranked_acc_reward_table,
        fail_delta=config.ranked_fail_delta,
        nf_ht_penalty=config.ranked_nf_ht_penalty,
        ez_bonus_stars_low=config.ranked_ez_bonus_stars_low,
        ez_bonus_low=config.ranked_ez_bonus_low,
        ez_bonus_stars_high=config.ranked_ez_bonus_stars_high,
        ez_bonus_high=config.ranked_ez_bonus_high,
        clamp_min=config.ranked_clamp_min,
        clamp_max=config.ranked_clamp_max,
        reroll_penalty=config.ranked_reroll_penalty,
        daily_reroll_limit=config.ranked_daily_reroll_limit,
        recent_exclude=config.ranked_recent_exclude,
        star_window=config.ranked_star_window,
        time_tolerance_seconds=config.ranked_time_tolerance_seconds,
        timeout_multiplier=config.ranked_timeout_multiplier,
        timeout_min_seconds=config.ranked_timeout_min_seconds,
        expiry_grace_seconds=config.ranked_expiry_grace_seconds,
    )


def _statuses_for(config: ServerConfig, star_min: float) -> tuple[str, ...]:
    if star_min >= config.ranked_high_star_threshold:
        return tuple(
            s.strip()
            for s in config.ranked_high_star_statuses.split(",")
            if s.strip()
        )
    return ("ranked",)


def ranked_picker(config: ServerConfig, local_ids: Optional[list[int]] = None) -> Picker:
    """Adapter: ``server.beatmap_picker`` -> ranked picker callable."""
    from server.beatmap_picker import fetch_challenge_maps, fetch_personal_challenge_maps

    async def picker(lo: float, hi: Optional[float], exclude: Optional[list[int]] = None):
        exclude = set(exclude or [])
        kwargs = dict(
            min_stars=lo,
            max_stars=hi,
            min_length=config.ranked_min_length_seconds,
            max_length=config.ranked_max_length_seconds,
            statuses=_statuses_for(config, lo),
        )
        try:
            if local_ids:
                maps = await fetch_personal_challenge_maps(
                    config, local_ids, count=5, **kwargs
                )
            else:
                maps = await fetch_challenge_maps(config, count=5, **kwargs)
        except Exception:
            return None
        for m in maps:
            if m["beatmap_id"] not in exclude:
                return m
        return None

    return picker


async def _call_picker(picker: Picker, lo: float, hi: Optional[float], exclude: Optional[list[int]]):
    data = picker(lo, hi, exclude)
    if inspect.isawaitable(data):
        data = await data
    return data


async def get_or_create_state(
    db: AsyncSession, user: User, settings: RankedSettings = DEFAULT_SETTINGS
) -> RankedState:
    """Lazily create the user's RankedState with the starting ELO."""
    state = await db.get(RankedState, user.id)
    if state is None:
        state = RankedState(user_id=user.id, elo=settings.start_elo)
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state


async def get_active_challenge(db: AsyncSession, user_id: int) -> Optional[RankedChallenge]:
    result = await db.execute(
        select(RankedChallenge).where(
            RankedChallenge.user_id == user_id,
            RankedChallenge.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def _recent_beatmap_ids(db: AsyncSession, user_id: int, limit: int) -> list[int]:
    result = await db.execute(
        select(RankedChallenge.beatmap_id)
        .where(RankedChallenge.user_id == user_id)
        .order_by(RankedChallenge.id.desc())
        .limit(limit)
    )
    return [row[0] for row in result.all() if row[0]]


async def _last_settled(db: AsyncSession, user_id: int) -> Optional[RankedChallenge]:
    result = await db.execute(
        select(RankedChallenge)
        .where(
            RankedChallenge.user_id == user_id,
            RankedChallenge.status.in_(CLOSED_STATUSES),
        )
        .order_by(RankedChallenge.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _window_payload(elo: int, settings: RankedSettings) -> dict:
    """API shape for the continuous window (hundredths) and the sub-rank."""
    lo, hi, target = star_window(elo, settings)
    return {
        "star_window": {
            "min": round(lo, 2),
            "max": round(hi, 2),
            "target": round(target, 2),
        },
        "sub_rank": sub_rank(elo, settings),
    }


async def _pick_map(
    db: AsyncSession,
    user_id: int,
    picker: Picker,
    elo: int,
    settings: RankedSettings,
) -> dict:
    """Pick a map using the widening ladder, recent-exclusion retry.

    Order: the whole ladder (h, 2h, 4h, whole tier) with the recent maps
    excluded; then the whole ladder again without the exclusion; only then
    raise ``RankedNoMaps`` (nothing is persisted by the caller in that case).
    """
    exclude = await _recent_beatmap_ids(db, user_id, settings.recent_exclude)
    ladder = star_ladder(elo, settings)
    for lo, hi in ladder:
        data = await _call_picker(picker, lo, hi, exclude)
        if data is not None:
            return data
    for lo, hi in ladder:
        data = await _call_picker(picker, lo, hi, None)
        if data is not None:
            return data
    raise RankedNoMaps("не нашлось карт в диапазоне")


def _challenge_from_data(
    user_id: int, data: dict, now: datetime, settings: RankedSettings
) -> RankedChallenge:
    length = int(data.get("length") or data.get("length_sec") or 0)
    return RankedChallenge(
        user_id=user_id,
        beatmap_id=int(data.get("beatmap_id") or 0),
        beatmapset_id=int(data.get("beatmapset_id") or 0),
        beatmap_title=data.get("beatmap_title") or "",
        artist=data.get("artist") or "",
        version=data.get("version") or "",
        stars=float(data.get("stars") or 0.0),
        length_sec=length,
        download_url=data.get("download_url") or "",
        issued_at=as_utc(now),
        deadline_at=as_utc(now) + timedelta(seconds=timeout_seconds(length, settings)),
        status="active",
    )


async def _close_challenge(
    db: AsyncSession,
    challenge: RankedChallenge,
    status: str,
    delta: int,
    *,
    result_score_id: Optional[int] = None,
    mods: str = "",
    grade: str = "",
    accuracy: float = 0.0,
    now: datetime,
    settings: RankedSettings = DEFAULT_SETTINGS,
) -> bool:
    """Idempotently close an active challenge; True only if THIS call closed it.

    Uses a guarded ``UPDATE ... WHERE status='active'`` and checks rowcount so
    two concurrent settlements cannot both apply their ELO delta. Does not
    commit — the caller controls the transaction.
    """
    state = await db.get(RankedState, challenge.user_id)
    if state is None:
        state = RankedState(user_id=challenge.user_id, elo=settings.start_elo)
        db.add(state)
        await db.flush()

    elo_after = apply_delta(state.elo, delta, settings)
    result = await db.execute(
        update(RankedChallenge)
        .where(RankedChallenge.id == challenge.id, RankedChallenge.status == "active")
        .values(
            status=status,
            result_score_id=result_score_id,
            mods=mods,
            grade=grade,
            accuracy=accuracy,
            elo_delta=delta,
            elo_after=elo_after,
            settled_at=as_utc(now),
        )
    )
    if result.rowcount == 0:
        return False

    state.elo = elo_after
    await db.flush()
    return True


async def settle_expired(
    db: AsyncSession, user: User, now: datetime, settings: RankedSettings = DEFAULT_SETTINGS
) -> Optional[RankedChallenge]:
    """Lazily close an expired active challenge (delta = fail_delta, -60)."""
    active = await get_active_challenge(db, user.id)
    if active is None:
        return None
    grace = timedelta(seconds=settings.expiry_grace_seconds)
    if as_utc(now) > as_utc(active.deadline_at) + grace:
        await _close_challenge(db, active, "expired", settings.fail_delta, now=now, settings=settings)
        await db.commit()
        return await db.get(RankedChallenge, active.id)
    return None


async def issue(
    db: AsyncSession,
    user: User,
    picker: Picker,
    now: datetime,
    settings: RankedSettings = DEFAULT_SETTINGS,
) -> RankedChallenge:
    """Issue a new challenge, or return the existing active one."""
    state = await get_or_create_state(db, user, settings)

    active = await get_active_challenge(db, user.id)
    if active is not None:
        await settle_expired(db, user, now, settings)
        active = await get_active_challenge(db, user.id)
        if active is not None:
            return active

    data = await _pick_map(db, user.id, picker, state.elo, settings)
    challenge = _challenge_from_data(user.id, data, now, settings)
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)
    return challenge


async def surrender(
    db: AsyncSession, user: User, now: datetime, settings: RankedSettings = DEFAULT_SETTINGS
) -> Optional[RankedChallenge]:
    active = await get_active_challenge(db, user.id)
    if active is None:
        return None
    await _close_challenge(db, active, "surrendered", settings.fail_delta, now=now, settings=settings)
    await db.commit()
    return await db.get(RankedChallenge, active.id)


async def reroll(
    db: AsyncSession,
    user: User,
    picker: Picker,
    now: datetime,
    settings: RankedSettings = DEFAULT_SETTINGS,
) -> RankedChallenge:
    """Reroll the active challenge: -reroll_penalty ELO, capped at the floor."""
    active = await get_active_challenge(db, user.id)
    if active is None:
        raise RankedError("нет активного задания")

    state = await get_or_create_state(db, user, settings)
    today = today_str()
    if state.reroll_date != today:
        state.rerolls_today = 0
        state.reroll_date = today
    if state.rerolls_today >= settings.daily_reroll_limit:
        raise RankedRerollLimit("дневной лимит рероллов исчерпан")

    # Pick the new map first (using the ELO *before* the reroll penalty); a
    # picker failure must not deduct ELO or close the current challenge.
    data = await _pick_map(db, user.id, picker, state.elo, settings)

    closed = await _close_challenge(
        db, active, "rerolled", settings.reroll_penalty, now=now, settings=settings
    )
    if not closed:
        # Another request already closed it; do not proceed.
        return await db.get(RankedChallenge, active.id)

    state.rerolls_today += 1
    new_challenge = _challenge_from_data(user.id, data, now, settings)
    db.add(new_challenge)
    await db.commit()
    await db.refresh(new_challenge)
    return new_challenge


def _matches_map(challenge: RankedChallenge, score: Score) -> bool:
    """Whether ``score`` is for the challenge's map.

    When the score has a ``beatmap_id`` (> 0), it decides alone — a mismatch is
    "not the map" and we never fall back to the title. The title is only used
    when the score's beatmap_id is unknown (0 / None).
    """
    if score.beatmap_id and score.beatmap_id > 0:
        return challenge.beatmap_id == score.beatmap_id
    return bool(score.beatmap_title) and score.beatmap_title == challenge.beatmap_title


async def settle_from_db(
    db: AsyncSession, user: User, now: datetime, settings: RankedSettings = DEFAULT_SETTINGS
) -> Optional[RankedChallenge]:
    """Settle the active challenge from the earliest eligible score in the DB.

    Scans the user's scores matching the challenge (same map rule as
    ``_matches_map``) within ``[issued_at - tolerance, deadline_at]`` and not
    later than ``now``, ordered by ``played_at``, and closes the challenge with
    the first pass/fail verdict (invalid scores are skipped). Does not commit —
    the caller controls the transaction.
    """
    active = await get_active_challenge(db, user.id)
    if active is None:
        return None

    now_utc = as_utc(now)
    deadline = as_utc(active.deadline_at)
    grace = timedelta(seconds=settings.expiry_grace_seconds)
    if now_utc > deadline + grace:
        return None

    issued = as_utc(active.issued_at)
    tol = timedelta(seconds=settings.time_tolerance_seconds)
    lower = issued - tol

    # Rough SQL pre-filter (naive UTC matches SQLite storage), re-verified below.
    result = await db.execute(
        select(Score)
        .where(
            Score.user_id == user.id,
            Score.played_at >= lower.replace(tzinfo=None),
            Score.played_at <= deadline.replace(tzinfo=None),
        )
        .order_by(Score.played_at.asc(), Score.id.asc())
    )
    for s in result.scalars().all():
        played = as_utc(s.played_at)
        if not (lower <= played <= deadline) or played > now_utc:
            continue
        if not _matches_map(active, s):
            continue
        verdict, delta = evaluate(s.rank, s.accuracy, s.mods, active.stars, settings)
        if verdict == "invalid":
            continue
        status = "failed" if verdict == "fail" else "passed"
        await _close_challenge(
            db,
            active,
            status,
            delta,
            result_score_id=s.id,
            mods=s.mods or "",
            grade=normalize_grade(s.rank),
            accuracy=float(s.accuracy or 0.0),
            now=now,
            settings=settings,
        )
        return await db.get(RankedChallenge, active.id)
    return None


async def try_settle(
    db: AsyncSession,
    user: User,
    score: Score,
    now: datetime,
    settings: RankedSettings = DEFAULT_SETTINGS,
) -> Optional[RankedChallenge]:
    """Settle the active challenge after a new score is submitted.

    The just-submitted ``score`` is already persisted by the caller; settling
    goes through :func:`settle_from_db` so earlier, out-of-order scores are
    settled with first (not just the one that just arrived). Does not commit —
    the caller controls the transaction (the ``submit_score`` hook wraps this
    in a savepoint).
    """
    return await settle_from_db(db, user, now, settings)


async def serialize(
    db: AsyncSession, user: User, now: datetime, settings: RankedSettings = DEFAULT_SETTINGS
) -> dict:
    """Full ranked view for the user (ELO, tier, progress, active challenge)."""
    state = await get_or_create_state(db, user, settings)
    await settle_expired(db, user, now, settings)

    active = await get_active_challenge(db, user.id)
    tier = tier_for(state.elo, settings.tiers)
    progress = progress_to_next(state.elo, settings.tiers)
    lo, hi = star_range(state.elo, settings.tiers)

    active_payload = None
    if active is not None:
        seconds_left = int((as_utc(active.deadline_at) - as_utc(now)).total_seconds())
        active_payload = {
            "id": active.id,
            "beatmap_id": active.beatmap_id,
            "beatmapset_id": active.beatmapset_id,
            "title": active.beatmap_title,
            "artist": active.artist,
            "version": active.version,
            "stars": active.stars,
            "length_sec": active.length_sec,
            "download_url": active.download_url,
            "issued_at": as_utc(active.issued_at).isoformat() if active.issued_at else None,
            "deadline_at": as_utc(active.deadline_at).isoformat() if active.deadline_at else None,
            "seconds_left": max(0, seconds_left),
            "condition": (
                "оценка C и выше: награда по таблице точности; "
                "фейл, сдача и таймаут — штраф"
            ),
        }

    last = await _last_settled(db, user.id)
    last_payload = None
    if last is not None:
        last_payload = {
            "id": last.id,
            "beatmap_id": last.beatmap_id,
            "title": last.beatmap_title,
            "stars": last.stars,
            "status": last.status,
            "grade": last.grade,
            "accuracy": last.accuracy,
            "mods": last.mods,
            "elo_delta": last.elo_delta,
            "elo_after": last.elo_after,
            "settled_at": as_utc(last.settled_at).isoformat() if last.settled_at else None,
        }

    return {
        "elo": state.elo,
        "tier": tier.name,
        "progress": progress,
        "star_range": {"min": lo, "max": hi},
        **_window_payload(state.elo, settings),
        "acc_reward_table": list(settings.acc_reward_table),
        "reroll_penalty": settings.reroll_penalty,
        "fail_delta": settings.fail_delta,
        "rerolls_used_today": state.rerolls_today,
        "rerolls_left": max(0, settings.daily_reroll_limit - state.rerolls_today),
        "active": active_payload,
        "last_result": last_payload,
    }


async def _aggregate(db: AsyncSession, user_id: int) -> dict:
    """One SQL pass over a user's closed challenges (no row-by-row loading)."""
    result = await db.execute(
        select(
            func.count(RankedChallenge.id),
            func.coalesce(
                func.sum(case((RankedChallenge.status == "passed", 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            RankedChallenge.status.in_(
                                ("failed", "surrendered", "expired")
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(case((RankedChallenge.status == "rerolled", 1), else_=0)), 0
            ),
            # Win/loss/draw are defined by the stored delta (before the ELO
            # floor is applied) and never include rerolled challenges.
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                RankedChallenge.status != "rerolled",
                                RankedChallenge.elo_delta > 0,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                RankedChallenge.status != "rerolled",
                                RankedChallenge.elo_delta < 0,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                RankedChallenge.status != "rerolled",
                                RankedChallenge.elo_delta == 0,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.max(
                case(
                    (RankedChallenge.status == "passed", RankedChallenge.accuracy),
                    else_=None,
                )
            ),
            func.avg(
                case(
                    (RankedChallenge.status == "passed", RankedChallenge.accuracy),
                    else_=None,
                )
            ),
            func.max(
                case(
                    (RankedChallenge.status == "passed", RankedChallenge.stars),
                    else_=None,
                )
            ),
            func.max(RankedChallenge.elo_delta),
        ).where(
            RankedChallenge.user_id == user_id,
            RankedChallenge.status.in_(CLOSED_STATUSES),
        )
    )
    (
        total,
        passed,
        failed,
        rerolled,
        wins,
        losses,
        draws,
        best_acc,
        avg_acc,
        hardest,
        best_gain,
    ) = result.one()
    return {
        "total": int(total or 0),
        "passed": int(passed or 0),
        "failed": int(failed or 0),
        "rerolled": int(rerolled or 0),
        "wins": int(wins or 0),
        "losses": int(losses or 0),
        "draws": int(draws or 0),
        "best_acc": best_acc,
        "avg_acc": avg_acc,
        "hardest": hardest,
        "best_gain": max(0, int(best_gain or 0)),
    }


def _win_rate(wins: int, losses: int, draws: int) -> float:
    denom = wins + losses + draws
    return round(wins / denom, 4) if denom > 0 else 0.0


async def stats(
    db: AsyncSession, user: User, settings: RankedSettings = DEFAULT_SETTINGS
) -> dict:
    """Aggregated Ranked statistics for a user (SQL aggregates, no full scan)."""
    state = await get_or_create_state(db, user, settings)
    tier = tier_for(state.elo, settings.tiers)
    progress = progress_to_next(state.elo, settings.tiers)

    agg = await _aggregate(db, user.id)

    last_result = await db.execute(
        select(RankedChallenge)
        .where(
            RankedChallenge.user_id == user.id,
            RankedChallenge.status.in_(CLOSED_STATUSES),
        )
        .order_by(RankedChallenge.id.desc())
        .limit(5)
    )
    last_results = [
        {
            "id": c.id,
            "title": c.beatmap_title,
            "stars": c.stars,
            "outcome": c.status,
            "delta": c.elo_delta,
            "accuracy": c.accuracy,
            "date": as_utc(c.settled_at).isoformat() if c.settled_at else None,
        }
        for c in last_result.scalars().all()
    ]

    return {
        "enabled": True,
        "total_settled": agg["total"],
        "passed": agg["passed"],
        "failed": agg["failed"],
        "rerolled": agg["rerolled"],
        "wins": agg["wins"],
        "losses": agg["losses"],
        "draws": agg["draws"],
        "win_rate": _win_rate(agg["wins"], agg["losses"], agg["draws"]),
        "best_accuracy": agg["best_acc"],
        "avg_accuracy": agg["avg_acc"],
        "hardest_passed_stars": agg["hardest"],
        "best_elo_gain": agg["best_gain"],
        "current_elo": state.elo,
        "tier": tier.name,
        "progress": progress,
        **_window_payload(state.elo, settings),
        "acc_reward_table": list(settings.acc_reward_table),
        "last_results": last_results,
    }


async def public_stats(
    db: AsyncSession, user: User, settings: RankedSettings = DEFAULT_SETTINGS
) -> dict:
    """Read-only public Ranked stats for a player (no active challenge, no writes).

    A player with no RankedState is reported at the starting ELO without
    creating a row (unlike :func:`stats`, which lazily creates state).
    """
    state = await db.get(RankedState, user.id)
    elo = state.elo if state is not None else settings.start_elo
    tier = tier_for(elo, settings.tiers)
    progress = progress_to_next(elo, settings.tiers)

    agg = await _aggregate(db, user.id)

    recent = await db.execute(
        select(RankedChallenge)
        .where(
            RankedChallenge.user_id == user.id,
            RankedChallenge.status.in_(CLOSED_STATUSES),
        )
        .order_by(RankedChallenge.id.desc())
        .limit(20)
    )
    last_results = [
        {
            "beatmap_id": c.beatmap_id,
            "beatmapset_id": c.beatmapset_id,
            "title": c.beatmap_title,
            "stars": c.stars,
            "length_sec": c.length_sec,
            "version": c.version,
            "status": c.status,
            "elo_delta": c.elo_delta,
            "accuracy": c.accuracy,
            "grade": c.grade,
            "mods": c.mods,
            "settled_at": as_utc(c.settled_at).isoformat() if c.settled_at else None,
        }
        for c in recent.scalars().all()
    ]

    # First closed challenge's creation time -> the start point date.
    start_created = (
        await db.execute(
            select(
                func.min(
                    func.coalesce(RankedChallenge.created_at, RankedChallenge.issued_at)
                )
            ).where(
                RankedChallenge.user_id == user.id,
                RankedChallenge.status.in_(CLOSED_STATUSES),
            )
        )
    ).scalar()

    # Up to 99 settled points, leaving room for the prepended start point so the
    # total stays within the 100-point limit.
    history = await db.execute(
        select(RankedChallenge.settled_at, RankedChallenge.elo_after)
        .where(
            RankedChallenge.user_id == user.id,
            RankedChallenge.status.in_(CLOSED_STATUSES),
            RankedChallenge.settled_at.is_not(None),
        )
        .order_by(RankedChallenge.id.desc())
        .limit(99)
    )
    points = [
        {"date": as_utc(settled_at).isoformat(), "elo_after": elo_after}
        for settled_at, elo_after in history.all()
    ][::-1]  # chronological ascending for a chart
    if start_created is not None:
        points.insert(
            0,
            {
                "date": as_utc(start_created).isoformat(),
                "elo_after": settings.start_elo,
                "label": "старт",
            },
        )
    elo_history = points

    return {
        "tier": tier.name,
        "current_elo": elo,
        "progress": progress,
        **_window_payload(elo, settings),
        "tier_thresholds": [
            {"name": t.name, "min_elo": t.min_elo} for t in settings.tiers
        ],
        "passed": agg["passed"],
        "failed": agg["failed"],
        "wins": agg["wins"],
        "losses": agg["losses"],
        "draws": agg["draws"],
        "win_rate": _win_rate(agg["wins"], agg["losses"], agg["draws"]),
        "best_accuracy": agg["best_acc"],
        "avg_accuracy": agg["avg_acc"],
        "hardest_passed_stars": agg["hardest"],
        "best_elo_gain": agg["best_gain"],
        "last_results": last_results,
        "elo_history": elo_history,
    }
