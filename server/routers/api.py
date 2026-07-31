from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth import get_current_user
from server.database import Score, User, get_session

router = APIRouter(prefix="/api", tags=["api"])


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
    acc_r4 = round(float(score_data["accuracy"]), 4)
    pp_r1 = round(float(score_data["pp"]), 1)

    result = await session.execute(
        select(Score).where(
            Score.user_id == current_user.id,
            Score.md5 == score_md5,
            Score.mods == mods,
            Score.max_combo == max_combo,
        )
    )
    for existing in result.scalars():
        if (
            round(existing.accuracy, 4) == acc_r4
            and round(existing.pp, 1) == pp_r1
        ):
            return {"status": "duplicate", "score_id": None}

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
        density=float(score_data.get("density", 0.0)),
        aim=float(score_data.get("aim", 0.0)),
        stars=float(score_data.get("stars", 0.0)),
        ar=float(score_data.get("ar", 0.0)),
        played_at=played_at,
    )
    session.add(score)
    await session.commit()
    await session.refresh(score)
    return {"status": "ok", "score_id": score.id}


@router.get("/me/profile")
async def get_profile(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(func.sum(Score.ap)).where(Score.user_id == current_user.id)
    )
    total_ap = result.scalar() or 0.0

    result = await session.execute(
        select(func.count(Score.id)).where(Score.user_id == current_user.id)
    )
    total_scores = result.scalar() or 0

    result = await session.execute(
        select(Score.played_at, Score.ap).where(Score.user_id == current_user.id)
    )
    daily_ap: dict[str, float] = {}
    for played_at, ap in result.all():
        day = played_at.date().isoformat() if played_at else "unknown"
        daily_ap[day] = daily_ap.get(day, 0.0) + (ap or 0.0)
    best_ap = max(daily_ap.values(), default=0.0)

    goal = current_user.daily_goal or 0
    goals_done = sum(1 for v in daily_ap.values() if v >= goal) if goal > 0 else 0

    result = await session.execute(
        select(Score.source, func.count(Score.id))
        .where(Score.user_id == current_user.id)
        .group_by(Score.source)
    )
    source_counts = {"mcsu": 0, "api": 0}
    for source, count in result.all():
        source_counts[str(source)] = count

    result = await session.execute(
        select(Score.rank, func.count(Score.id))
        .where(Score.user_id == current_user.id)
        .group_by(Score.rank)
    )
    grades = {"XH": 0, "X": 0, "SH": 0, "S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
    for rank, count in result.all():
        g = str(rank).strip().upper()
        if g in grades:
            grades[g] = count

    result = await session.execute(
        select(Score)
        .where(Score.user_id == current_user.id)
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
        "osu_id": current_user.osu_id,
        "username": current_user.username,
        "avatar_url": current_user.avatar_url,
        "total_ap": round(total_ap, 2),
        "best_ap": round(best_ap, 2),
        "games": total_scores,
        "daily_goal": goal,
        "goals_done": goals_done,
        "source_counts": source_counts,
        "grades": grades,
        "top_scores": top_scores,
    }


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
    result = await session.execute(
        select(Score).where(Score.user_id == current_user.id)
    )
    scores = result.scalars().all()

    if date:
        scores = [s for s in scores if (s.played_at or datetime.min).date().isoformat() == date]
        scores.sort(key=lambda s: s.ap, reverse=True)
    else:
        scores.sort(key=lambda s: s.played_at or datetime.min, reverse=True)
        scores = scores[offset:offset + limit]

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


@router.get("/me/daily")
async def get_daily(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(Score.played_at, Score.ap).where(Score.user_id == current_user.id)
    )
    daily: dict[str, list[float]] = {}
    for played_at, ap in result.all():
        day = played_at.date().isoformat() if played_at else "unknown"
        daily.setdefault(day, []).append(ap or 0.0)

    rows = []
    for day, values in daily.items():
        rows.append(
            {
                "date": day,
                "total_ap": round(sum(values), 2),
                "scores_count": len(values),
                "best_score_ap": round(max(values), 2),
            }
        )
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


@router.get("/me/ap-history")
async def get_ap_history(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(Score.played_at, Score.ap).where(
            Score.user_id == current_user.id,
            Score.played_at >= since,
        )
    )
    daily: dict[str, float] = {}
    for played_at, ap in result.all():
        day = played_at.date().isoformat() if played_at else "unknown"
        daily[day] = daily.get(day, 0.0) + (ap or 0.0)
    items = sorted(daily.items())
    return {
        "labels": [d for d, _ in items],
        "values": [round(v, 2) for _, v in items],
    }
