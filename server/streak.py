from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import ServerConfig
from server.database import (
    ChallengeBingo,
    ChallengeCompletion,
    DailyChallengeMap,
    Score,
    StreakRevival,
)
from server.dates import today_str


def _shift_day(day: str, n: int) -> str:
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (d + timedelta(days=n)).strftime("%Y-%m-%d")


def compute_status(
    daily_ap: dict,
    goal: int,
    revived_count: int,
    closed_days: set[str] | None = None,
) -> dict:
    if goal <= 0:
        return {
            "enabled": False,
            "current_streak": 0,
            "last_day": "",
            "next_missed_day": "",
            "payload_balance": 0,
            "missing_days": 0,
        }

    closed_days = closed_days or set()
    met = {d for d, ap in daily_ap.items() if ap >= goal} | closed_days
    today = today_str()

    # current streak, counting backward from today (or yesterday for grace),
    # bridging up to `revived_count` gaps.
    cursor = today if today in met else _shift_day(today, -1)
    last_day = ""
    next_missed_day = ""
    streak = 0
    if cursor in met:
        last_day = cursor
        gaps_used = 0
        while True:
            if cursor in met:
                streak += 1
            else:
                if gaps_used < revived_count:
                    gaps_used += 1
                    streak += 1
                else:
                    next_missed_day = cursor
                    break
            cursor = _shift_day(cursor, -1)

    # reserve: each 2x day banks one credit
    earned = sum(1 for ap in daily_ap.values() if ap >= 2 * goal)
    balance = max(0, earned - revived_count)

    # missing days: non-met calendar days in [first_play .. yesterday]
    days = sorted(daily_ap.keys())
    missing_total = 0
    if days:
        cursor = days[0]
        yesterday = _shift_day(today, -1)
        while cursor <= yesterday:
            if cursor not in met:
                missing_total += 1
            cursor = _shift_day(cursor, 1)
    missing = max(0, missing_total - revived_count)

    return {
        "enabled": True,
        "current_streak": streak,
        "last_day": last_day,
        "next_missed_day": next_missed_day,
        "payload_balance": balance,
        "missing_days": missing,
    }


async def daily_ap_map(session: AsyncSession, user_id: int) -> dict:
    result = await session.execute(
        select(
            func.date(Score.played_at).label("day"),
            func.sum(Score.ap).label("total"),
        )
        .where(Score.user_id == user_id, Score.played_at.isnot(None))
        .group_by(func.date(Score.played_at))
    )
    daily = {day: float(total or 0.0) for day, total in result.all()}
    return daily


async def daily_ap_with_bonus(session: AsyncSession, user_id: int) -> dict:
    daily = await daily_ap_map(session, user_id)

    completion_daily = await session.execute(
        select(
            func.date(ChallengeCompletion.completed_at).label("day"),
            func.sum(ChallengeCompletion.bonus_ap).label("total"),
        )
        .where(ChallengeCompletion.user_id == user_id)
        .group_by(func.date(ChallengeCompletion.completed_at))
    )
    for day, total in completion_daily.all():
        daily[day] = daily.get(day, 0.0) + float(total or 0.0)

    bingo_daily = await session.execute(
        select(
            func.date(ChallengeBingo.completed_at).label("day"),
            func.sum(ChallengeBingo.bonus_ap).label("total"),
        )
        .where(ChallengeBingo.user_id == user_id)
        .group_by(func.date(ChallengeBingo.completed_at))
    )
    for day, total in bingo_daily.all():
        daily[day] = daily.get(day, 0.0) + float(total or 0.0)

    return daily


async def challenge_closed_days(session: AsyncSession, user_id: int) -> set[str]:
    closed: set[str] = set()

    result = await session.execute(
        select(ChallengeBingo.date).where(ChallengeBingo.user_id == user_id)
    )
    closed.update(result.scalars().all())

    required = ServerConfig.from_env().daily_challenge_maps
    result = await session.execute(
        select(DailyChallengeMap.date, func.count(ChallengeCompletion.id))
        .join(ChallengeCompletion, ChallengeCompletion.challenge_map_id == DailyChallengeMap.id)
        .where(ChallengeCompletion.user_id == user_id)
        .group_by(DailyChallengeMap.date)
        .having(func.count(ChallengeCompletion.id) >= required)
    )
    closed.update(day for day, _count in result.all())
    return closed


async def revived_count(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count(StreakRevival.id)).where(StreakRevival.user_id == user_id)
    )
    return int(result.scalar() or 0)


async def streak_status(session: AsyncSession, user: object) -> dict:
    goal = getattr(user, "daily_goal", 0) or 0
    if goal <= 0:
        return compute_status({}, goal, 0)
    daily_ap = await daily_ap_with_bonus(session, user.id)
    rc = await revived_count(session, user.id)
    closed = await challenge_closed_days(session, user.id)
    return compute_status(daily_ap, goal, rc, closed)


async def revive(session: AsyncSession, user: object, config: ServerConfig) -> dict:
    goal = getattr(user, "daily_goal", 0) or 0
    if goal <= 0:
        raise ValueError("Daily goal is not set")

    daily_ap = await daily_ap_with_bonus(session, user.id)
    rc = await revived_count(session, user.id)
    closed = await challenge_closed_days(session, user.id)
    status = compute_status(daily_ap, goal, rc, closed)

    if status["payload_balance"] < 1:
        raise ValueError("Недостаточно накопленных 2x-дней для восстановления")
    if status["missing_days"] < 1:
        raise ValueError("Нет пропущенных дней для восстановления")

    session.add(
        StreakRevival(
            user_id=user.id,
            missed_date=status.get("next_missed_day") or today_str(),
            streak_after=status["current_streak"] + 1,
        )
    )
    await session.commit()

    rc = await revived_count(session, user.id)
    closed = await challenge_closed_days(session, user.id)
    return compute_status(daily_ap, goal, rc, closed)
