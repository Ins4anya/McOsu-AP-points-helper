from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth import get_current_user, lookup_beatmap_by_md5
from server.config import ServerConfig
from server.database import Score, User, get_session

router = APIRouter(prefix="/api", tags=["api"])


def make_score_key(
    md5: str, mods: str, max_combo: int, accuracy: float, pp: float
) -> str:
    payload = f"{md5}|{mods}|{max_combo}|{round(accuracy, 4)}|{round(pp, 1)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()

BANNER_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads"
BANNER_DIR.mkdir(parents=True, exist_ok=True)

MAX_BANNER_BYTES = 10 * 1024 * 1024


def sniff_image_ext(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def banner_url(user_id: int) -> str | None:
    for f in sorted(BANNER_DIR.glob(f"banner_{user_id}.*")):
        return f"/static/uploads/{f.name}?t={int(f.stat().st_mtime)}"
    return None


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

    onfire_goal = user.onfire_goal or 0
    onfire_done = (
        sum(1 for v in daily_ap.values() if v >= onfire_goal) if onfire_goal > 0 else 0
    )

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
            "beatmap_id": s.beatmap_id,
            "beatmap_title": s.beatmap_title,
            "beatmap_url": s.beatmap_url
            or (
                f"https://osu.ppy.sh/beatmaps/{s.beatmap_id}"
                if s.beatmap_id and s.beatmap_id > 0
                else ""
            ),
            "accuracy": s.accuracy,
            "grade": s.rank,
            "mods": s.mods,
            "max_combo": s.max_combo,
            "pp": s.pp,
            "ap": s.ap,
            "stars": s.stars,
            "density": s.density,
            "aim": s.aim,
            "ar": s.ar,
            "speed_mult": s.speed_mult,
            "eff_cs": s.eff_cs,
            "eff_ar": s.eff_ar,
            "eff_od": s.eff_od,
            "eff_hp": s.eff_hp,
            "source": s.source,
            "played_at": s.played_at.isoformat() if s.played_at else None,
        }
        for s in result.scalars().all()
    ]

    result = await session.execute(
        select(
            Score.beatmap_title,
            func.count(Score.id).label("plays"),
            func.max(Score.beatmap_url),
            func.max(Score.beatmap_id),
            func.max(Score.stars),
            func.sum(Score.ap),
        )
        .where(Score.user_id == user.id)
        .group_by(Score.beatmap_title)
        .order_by(func.count(Score.id).desc())
    )
    most_played = [
        {
            "beatmap_title": title,
            "beatmap_url": url
            or (
                f"https://osu.ppy.sh/beatmaps/{beatmap_id}"
                if beatmap_id and beatmap_id > 0
                else ""
            ),
            "beatmap_id": beatmap_id or 0,
            "plays": plays,
            "stars": stars or 0.0,
            "total_ap": round(total_ap, 2),
        }
        for title, plays, url, beatmap_id, stars, total_ap in result.all()
    ]

    return {
        "osu_id": user.osu_id,
        "username": user.username,
        "avatar_url": user.avatar_url,
        "banner_url": banner_url(user.id),
        "flag": user.flag or "",
        "total_ap": round(total_ap, 2),
        "best_ap": round(best_ap, 2),
        "games": total_scores,
        "daily_goal": goal,
        "goals_done": goals_done,
        "onfire_goal": onfire_goal,
        "onfire_done": onfire_done,
        "source_counts": source_counts,
        "grades": grades,
        "top_scores": top_scores,
        "most_played": most_played,
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
            "density": s.density,
            "aim": s.aim,
            "ar": s.ar,
            "speed_mult": s.speed_mult,
            "eff_cs": s.eff_cs,
            "eff_ar": s.eff_ar,
            "eff_od": s.eff_od,
            "eff_hp": s.eff_hp,
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
    config: ServerConfig = Depends(ServerConfig.from_env),
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
    source = str(score_data.get("source", "mcsu"))[:16]
    beatmap_url = str(score_data.get("beatmap_url", "") or "")
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
        beatmap_url=beatmap_url,
        md5=score_md5,
        mods=mods,
        source=source,
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
        speed_mult=float(score_data.get("speed_mult", 1.0)),
        eff_cs=float(score_data.get("eff_cs", 0.0)),
        eff_ar=float(score_data.get("eff_ar", 0.0)),
        eff_od=float(score_data.get("eff_od", 0.0)),
        eff_hp=float(score_data.get("eff_hp", 0.0)),
        played_at=played_at,
    )

    if source == "mcsu" and not beatmap_url and score_md5:
        try:
            meta = await lookup_beatmap_by_md5(config, score_md5)
            if meta:
                score.beatmap_url = meta["map_url"]
                if int(score.beatmap_id) <= 0 and meta.get("beatmap_id"):
                    score.beatmap_id = int(meta["beatmap_id"])
                if not score_data.get("beatmap_title"):
                    score.beatmap_title = meta["title"]
                if not score_data.get("stars"):
                    score.stars = float(meta.get("stars") or 0.0)
        except Exception:
            pass

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
    return {
        "daily_goal": current_user.daily_goal or 0,
        "onfire_goal": current_user.onfire_goal or 0,
    }


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

    onfire_goal = current_user.onfire_goal or 0
    if "onfire_goal" in goal_data:
        try:
            onfire_goal = int(goal_data.get("onfire_goal", 0))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400, detail="onfire_goal must be an integer"
            )
        if onfire_goal < 0:
            raise HTTPException(
                status_code=400, detail="onfire_goal cannot be negative"
            )

    if onfire_goal > 0 and goal > 0 and onfire_goal < goal:
        raise HTTPException(
            status_code=400,
            detail="onfire_goal cannot be less than daily_goal",
        )

    current_user.daily_goal = goal
    current_user.onfire_goal = onfire_goal
    await session.commit()
    return {
        "daily_goal": current_user.daily_goal,
        "onfire_goal": current_user.onfire_goal,
    }


@router.post("/me/flag")
async def set_flag(
    flag_data: dict,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    flag = str(flag_data.get("flag", "")).strip()
    if flag:
        if len(flag) > 32 or not flag.isalnum():
            raise HTTPException(
                status_code=400,
                detail="flag must be an ISO 3166-1 alpha-2 code or a short region slug",
            )
        flag = flag.lower()
    current_user.flag = flag
    await session.commit()
    return {"flag": current_user.flag}


@router.post("/me/banner")
async def upload_banner(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_BANNER_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    ext = sniff_image_ext(data)
    if ext is None:
        raise HTTPException(status_code=400, detail="Unsupported image type (png/jpg/gif/webp)")

    for old in BANNER_DIR.glob(f"banner_{current_user.id}.*"):
        old.unlink(missing_ok=True)

    dest = BANNER_DIR / f"banner_{current_user.id}.{ext}"
    dest.write_bytes(data)
    return {"url": banner_url(current_user.id)}


@router.delete("/me/banner")
async def delete_banner(
    current_user: User = Depends(get_current_user),
):
    removed = False
    for old in BANNER_DIR.glob(f"banner_{current_user.id}.*"):
        old.unlink(missing_ok=True)
        removed = True
    return {"ok": removed}


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
            User.flag,
            total_ap_expr.label("total_ap"),
            func.count(Score.id).label("games"),
        )
        .select_from(User)
        .outerjoin(Score, Score.user_id == User.id)
        .group_by(User.id, User.osu_id, User.username, User.avatar_url, User.flag)
        .order_by(total_ap_expr.desc())
    )
    return [
        {
            "osu_id": osu_id,
            "username": username,
            "avatar_url": avatar_url,
            "flag": flag or "",
            "total_ap": round(total_ap, 2),
            "games": games,
        }
        for osu_id, username, avatar_url, flag, total_ap, games in result.all()
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
