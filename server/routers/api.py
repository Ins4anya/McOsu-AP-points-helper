from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth import get_current_user
from server.database import Score, User, get_session

router = APIRouter(prefix="/api", tags=["api"])


def make_score_key(
    md5: str, mods: str, max_combo: int, accuracy: float, pp: float
) -> str:
    payload = f"{md5}|{mods}|{max_combo}|{round(accuracy, 4)}|{round(pp, 1)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


async def build_profile(session: AsyncSession, user: User) -> dict:
    result = await session.execute(
        select(func.sum(Score.ap)).where(Score.user_id == user.id)
    )
    total_ap = result.scalar() or 0.0

    result = await session.execute(
        select(func.count(Score.id)).where(Score.user_id == user.id)
    )
    total_scores = result.scalar() or 0

    result = await session.execute(
        select(
            func.date(Score.played_at).label("day"),
            func.sum(Score.ap).label("total"),
        )
        .where(Score.user_id == user.id, Score.played_at.isnot(None))
        .group_by(func.date(Score.played_at))
    )
    daily_ap = {day: float(total) for day, total in result.all()}
    best_ap = max(daily_ap.values(), default=0.0)

    goal = user.daily_goal or 0
    goals_done = sum(1 for v in daily_ap.values() if v >= goal) if goal > 0 else 0

    result = await session.execute(
        select(Score.source, func.count(Score.id))
        .where(Score.user_id == user.id)
        .group_by(Score.source)
    )
    source_counts = {"mcsu": 0, "api": 0}
    for source, count in result.all():
        source_counts[str(source)] = count

    result = await session.execute(
        select(Score.rank, func.count(Score.id))
        .where(Score.user_id == user.id)
        .group_by(Score.rank)
    )
    grades = {"XH": 0, "X": 0, "SH": 0, "S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
    for rank, count in result.all():
        g = str(rank).strip().upper()
        if g in grades:
            grades[g] = count

    result = await session.execute(
        select(Score)
        .where(Score.user_id == user.id)
        .order_by(Score.ap.desc())
        .limit(5)
    )
    top_scores = [
        {
            "beatmap_title": s.beatmap_title,
            "accuracy": s.accuracy,
            "grade": s.rank,
            "mods": s.mods,
            "max_combo": s.max_combo,
            "pp": s.pp,
            "ap": s.ap,
            "source": s.source,
            "played_at": s.played_at.isoformat() if s.played_at else None,
        }
        for s in result.scalars().all()
    ]

    return {
        "osu_id": user.osu_id,
        "username": user.username,
        "avatar_url": user.avatar_url,
        "total_ap": round(total_ap, 2),
        "best_ap": round(best_ap, 2),
        "games": total_scores,
        "daily_goal": goal,
        "goals_done": goals_done,
        "source_counts": source_counts,
        "grades": grades,
        "top_scores": top_scores,
    }


async def list_scores(
    session: AsyncSession,
    user_id: int,
    limit: int = 50,
    offset: int = 0,
    date: str | None = None,
) -> list[dict]:
    stmt = select(Score).where(Score.user_id == user_id)
    if date:
        stmt = stmt.where(
            func.date(Score.played_at) == date
        ).order_by(Score.ap.desc())
    else:
        stmt = stmt.order_by(Score.played_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    scores = result.scalars().all()

    return [
        {
            "id": s.id,
            "beatmap_id": s.beatmap_id,
            "beatmap_title": s.beatmap_title,
            "beatmap_url": s.beatmap_url,
            "mods": s.mods,
            "source": s.source,
            "accuracy": s.accuracy,
            "max_combo": s.max_combo,
            "pp": s.pp,
            "ap": s.ap,
            "grade": s.rank,
            "rank": s.rank,
            "stars": s.stars,
            "played_at": s.played_at.isoformat() if s.played_at else None,
        }
        for s in scores
    ]


async def daily_rows(session: AsyncSession, user_id: int) -> list[dict]:
    result = await session.execute(
        select(
            func.date(Score.played_at).label("day"),
            func.sum(Score.ap).label("total"),
            func.count(Score.id).label("cnt"),
            func.max(Score.ap).label("best"),
        )
        .where(Score.user_id == user_id, Score.played_at.isnot(None))
        .group_by(func.date(Score.played_at))
    )
    rows = [
        {
            "date": day,
            "total_ap": round(total, 2),
            "scores_count": cnt,
            "best_score_ap": round(best, 2),
        }
        for day, total, cnt, best in result.all()
    ]
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


async def get_user_by_osu_id(
    session: AsyncSession, osu_id: int
) -> User:
    result = await session.execute(select(User).where(User.osu_id == osu_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return user


@router.post("/scores")
async def submit_score(
    score_data: dict,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    required = [
        "beatmap_id",
        "beatmap_title",
        "beatmap_url",
        "mods",
        "accuracy",
        "max_combo",
        "max_possible_combo",
        "pp",
        "ap",
        "rank",
        "played_at",
    ]
    for field in required:
        if field not in score_data:
            raise HTTPException(status_code=400, detail=f"Missing field: {field}")

    score_md5 = str(score_data.get("md5", "") or "")[:64]
    mods = str(score_data.get("mods", "NM"))
    max_combo = int(score_data["max_combo"])
    score_key = make_score_key(
        score_md5,
        mods,
        max_combo,
        float(score_data["accuracy"]),
        float(score_data["pp"]),
    )

    try:
        played_at = datetime.fromisoformat(score_data["played_at"])
        if played_at.tzinfo is None:
            played_at = played_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        played_at = datetime.now(timezone.utc)

    score = Score(
        user_id=current_user.id,
        beatmap_id=int(score_data["beatmap_id"]),
        beatmap_title=score_data["beatmap_title"],
        beatmap_url=score_data["beatmap_url"],
        md5=score_md5,
        mods=mods,
        source=str(score_data.get("source", "mcsu"))[:16],
        accuracy=float(score_data["accuracy"]),
        max_combo=int(score_data["max_combo"]),
        max_possible_combo=int(score_data["max_possible_combo"]),
        pp=float(score_data["pp"]),
        ap=float(score_data["ap"]),
        rank=score_data["rank"],
        score_key=score_key,
        density=float(score_data.get("density", 0.0)),
        aim=float(score_data.get("aim", 0.0)),
        stars=float(score_data.get("stars", 0.0)),
        ar=float(score_data.get("ar", 0.0)),
        played_at=played_at,
    )
    session.add(score)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return {"status": "duplicate", "score_id": None}
    await session.commit()
    await session.refresh(score)
    return {"status": "ok", "score_id": score.id}


@router.get("/me/profile")
async def get_profile(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return await build_profile(session, current_user)


@router.get("/me/goal")
async def get_goal(
    current_user: User = Depends(get_current_user),
):
    return {"daily_goal": current_user.daily_goal or 0}


@router.post("/me/goal")
async def set_goal(
    goal_data: dict,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        goal = int(goal_data.get("goal", 0))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="goal must be an integer")
    if goal < 0:
        raise HTTPException(status_code=400, detail="goal cannot be negative")
    current_user.daily_goal = goal
    await session.commit()
    return {"daily_goal": current_user.daily_goal} 


@router.get("/me/scores")
async def get_scores(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    date: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return await list_scores(
        session, current_user.id, limit=limit, offset=offset, date=date
    )


@router.get("/me/daily")
async def get_daily(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return await daily_rows(session, current_user.id)


@router.get("/me/ap-history")
async def get_ap_history(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(
            func.date(Score.played_at).label("day"),
            func.sum(Score.ap).label("total"),
        )
        .where(
            Score.user_id == current_user.id,
            Score.played_at >= since,
        )
        .group_by(func.date(Score.played_at))
    )
    daily = {day: round(float(total), 2) for day, total in result.all()}
    items = sorted(daily.items())
    return {
        "labels": [d for d, _ in items],
        "values": [v for _, v in items],
    }


@router.get("/players")
async def list_players(
    session: AsyncSession = Depends(get_session),
):
    total_ap_expr = func.coalesce(func.sum(Score.ap), 0.0)
    result = await session.execute(
        select(
            User.osu_id,
            User.username,
            User.avatar_url,
            total_ap_expr.label("total_ap"),
            func.count(Score.id).label("games"),
        )
        .select_from(User)
        .outerjoin(Score, Score.user_id == User.id)
        .group_by(User.id, User.osu_id, User.username, User.avatar_url)
        .order_by(total_ap_expr.desc())
    )
    return [
        {
            "osu_id": osu_id,
            "username": username,
            "avatar_url": avatar_url,
            "total_ap": round(total_ap, 2),
            "games": games,
        }
        for osu_id, username, avatar_url, total_ap, games in result.all()
    ]


@router.get("/players/{osu_id}/profile")
async def get_public_profile(
    osu_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_osu_id(session, osu_id)
    return await build_profile(session, user)


@router.get("/players/{osu_id}/scores")
async def get_public_scores(
    osu_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    date: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_osu_id(session, osu_id)
    return await list_scores(
        session, user.id, limit=limit, offset=offset, date=date
    )


@router.get("/players/{osu_id}/daily")
async def get_public_daily(
    osu_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_osu_id(session, osu_id)
    return await daily_rows(session, user.id)
