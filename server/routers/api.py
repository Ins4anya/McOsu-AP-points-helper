from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth import get_current_user, lookup_beatmap_by_md5
from server.challenge import (
    apply_completion,
    challenge_bonus_total,
    challenge_owner,
    date_str,
    get_or_create_maps,
    local_beatmap_ids,
    serialize_challenge,
    today_str,
)
from server.config import ServerConfig
from server.database import (
    ChallengeBingo,
    ChallengeCompletion,
    DailyChallengeMap,
    RankedChallenge,
    RankedState,
    Score,
    User,
    UserLocalBeatmap,
    get_session,
)
from server.streak import (
    daily_ap_with_bonus,
    revive,
    streak_status,
)
from server.skills import build_skills, build_pool, score_tag, PoolStats
from server.ranked import (
    CLOSED_STATUSES,
    RankedError,
    RankedNoMaps,
    RankedRerollLimit,
    get_active_challenge,
    ranked_picker,
    ranked_settings_from_config,
    issue as ranked_issue,
    public_stats as ranked_public_stats,
    reroll as ranked_reroll,
    serialize as ranked_serialize,
    settle_expired,
    settle_from_db,
    stats as ranked_stats,
    surrender as ranked_surrender,
)
from server.ranked_rules import info as ranked_info, sub_rank, tier_for

router = APIRouter(prefix="/api", tags=["api"])
logger = logging.getLogger(__name__)


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
    total_ap = (result.scalar() or 0.0) + await challenge_bonus_total(
        session, user.id
    )

    result = await session.execute(
        select(func.count(Score.id)).where(Score.user_id == user.id)
    )
    total_scores = result.scalar() or 0

    result = await session.execute(
        select(func.count(ChallengeCompletion.id)).where(
            ChallengeCompletion.user_id == user.id
        )
    )
    challenges_done = result.scalar() or 0

    result = await session.execute(
        select(func.count(ChallengeBingo.id)).where(
            ChallengeBingo.user_id == user.id
        )
    )
    bingos_done = result.scalar() or 0

    challenge_bonus = await challenge_bonus_total(session, user.id)

    daily_ap = await daily_ap_with_bonus(session, user.id)
    best_ap = max(daily_ap.values(), default=0.0)

    goal = user.daily_goal or 0
    goals_done = sum(1 for v in daily_ap.values() if v >= goal) if goal > 0 else 0

    onfire_goal = user.onfire_goal or 0
    onfire_done = (
        sum(1 for v in daily_ap.values() if v >= onfire_goal) if onfire_goal > 0 else 0
    )

    streak_state = await streak_status(session, user)

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
    pool = await build_pool(session, user.id)
    top_scores = [
        {
            "id": s.id,
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
            "max_possible_combo": s.max_possible_combo,
            "count300": s.count300,
            "count100": s.count100,
            "count50": s.count50,
            "count_miss": s.count_miss,
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
            "tag": score_tag(s, pool),
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
        "challenges_done": challenges_done,
        "bingos_done": bingos_done,
        "challenge_bonus_total": round(challenge_bonus, 2),
        "streak": streak_state,
        "daily_goal": goal,
        "goals_done": goals_done,
        "onfire_goal": onfire_goal,
        "onfire_done": onfire_done,
        "source_counts": source_counts,
        "grades": grades,
        "top_scores": top_scores,
        "most_played": most_played,
    }


def serialize_score(s: Score, pool: PoolStats | None = None) -> dict:
    return {
        "id": s.id,
        "beatmap_id": s.beatmap_id,
        "beatmap_title": s.beatmap_title,
        "beatmap_url": s.beatmap_url,
        "mods": s.mods,
        "source": s.source,
        "accuracy": s.accuracy,
        "max_combo": s.max_combo,
        "max_possible_combo": s.max_possible_combo,
        "count300": s.count300,
        "count100": s.count100,
        "count50": s.count50,
        "count_miss": s.count_miss,
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
        "tag": score_tag(s, pool) if pool else "",
        "played_at": s.played_at.isoformat() if s.played_at else None,
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
    pool = await build_pool(session, user_id)
    return [serialize_score(s, pool) for s in result.scalars().all()]


async def daily_rows(session: AsyncSession, user_id: int) -> list[dict]:
    daily_totals = await daily_ap_with_bonus(session, user_id)

    result = await session.execute(
        select(
            func.date(Score.played_at).label("day"),
            func.count(Score.id).label("cnt"),
            func.max(Score.ap).label("best"),
        )
        .where(Score.user_id == user_id, Score.played_at.isnot(None))
        .group_by(func.date(Score.played_at))
    )
    score_info = {day: (cnt, best) for day, cnt, best in result.all()}

    rows = [
        {
            "date": day,
            "total_ap": round(total, 2),
            "scores_count": score_info.get(day, (0, None))[0],
            "best_score_ap": round(score_info.get(day, (0, 0.0))[1] or 0.0, 2),
        }
        for day, total in daily_totals.items()
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



async def _try_complete_challenge(session, config, user, score):
    if not config.daily_challenge_enabled:
        return
    try:
        score_date = date_str(score.played_at) if score.played_at else today_str()
        if score_date != today_str():
            return

        maps = await get_or_create_maps(
            session, config, score_date, challenge_owner(user)
        )
        if not maps:
            return

        match = None
        if score.beatmap_id and score.beatmap_id > 0:
            for m in maps:
                if m.beatmap_id == score.beatmap_id:
                    match = m
                    break
        if match is None:
            for m in maps:
                if score.beatmap_title and score.beatmap_title == m.beatmap_title:
                    match = m
                    break
        if match is None:
            return

        await apply_completion(session, config, user.id, match, score.id)
    except Exception:
        logger.exception("Failed to apply daily challenge completion")


async def _try_settle_ranked(session, config, user, score):
    """Settle an active Ranked challenge against a just-submitted score.

    Runs under the same conditions as ``_try_complete_challenge`` (gated on a
    ``ranked_enabled`` flag; disabled by default until the config flag lands in
    step 4). Wrapped in a savepoint + try/except so a ranked failure never
    breaks the score insert or the response.
    """
    if not getattr(config, "ranked_enabled", False):
        return
    try:
        from server.ranked import try_settle

        now = datetime.now(timezone.utc)
        async with session.begin_nested():
            await try_settle(session, user, score, now)
        await session.commit()
    except Exception:
        logger.exception("Failed to settle ranked challenge")


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

    try:
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
            beatmap_title=str(score_data["beatmap_title"]),
            beatmap_url=beatmap_url,
            md5=score_md5,
            mods=mods,
            source=source,
            accuracy=float(score_data["accuracy"]),
            max_combo=max_combo,
            max_possible_combo=int(score_data["max_possible_combo"]),
            count300=int(score_data.get("count300", 0) or 0),
            count100=int(score_data.get("count100", 0) or 0),
            count50=int(score_data.get("count50", 0) or 0),
            count_miss=int(score_data.get("count_miss", 0) or 0),
            pp=float(score_data["pp"]),
            ap=float(score_data["ap"]),
            rank=str(score_data["rank"])[:8],
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
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid score field: {e}")

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
    await _try_complete_challenge(session, config, current_user, score)
    await _try_settle_ranked(session, config, current_user, score)
    return {"status": "ok", "score_id": score.id}


@router.get("/me/profile")
async def get_profile(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return await build_profile(session, current_user)


@router.get("/me/challenge")
async def get_challenge(
    session: AsyncSession = Depends(get_session),
    config: ServerConfig = Depends(ServerConfig.from_env),
    current_user: User = Depends(get_current_user),
):
    return await serialize_challenge(
        session, config, current_user, today_str()
    )


MAX_LOCAL_BEATMAPS = 100_000


@router.post("/me/local-beatmaps")
async def replace_local_beatmaps(
    payload: dict,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    items = payload.get("beatmaps")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="beatmaps must be a list")
    if len(items) > MAX_LOCAL_BEATMAPS:
        raise HTTPException(status_code=413, detail="Too many beatmaps")

    rows: dict[int, int] = {}
    for item in items:
        try:
            bid = int(item.get("beatmap_id") or 0)
            bsid = int(item.get("beatmapset_id") or 0)
        except (AttributeError, ValueError, TypeError):
            continue
        if bid > 0:
            rows[bid] = bsid

    await session.execute(
        delete(UserLocalBeatmap).where(UserLocalBeatmap.user_id == current_user.id)
    )
    completed_map_ids = select(ChallengeCompletion.challenge_map_id).where(
        ChallengeCompletion.user_id == current_user.id
    )
    await session.execute(
        delete(DailyChallengeMap).where(
            DailyChallengeMap.user_id == current_user.id,
            DailyChallengeMap.date == today_str(),
            DailyChallengeMap.id.not_in(completed_map_ids),
        )
    )
    session.add_all(
        UserLocalBeatmap(user_id=current_user.id, beatmap_id=bid, beatmapset_id=bsid)
        for bid, bsid in rows.items()
    )
    await session.commit()
    return {"count": len(rows)}


@router.post("/me/local-challenge")
async def set_local_challenge(
    payload: dict,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    current_user.use_local_challenge = bool(payload.get("enabled", False))
    await session.commit()
    return {"enabled": current_user.use_local_challenge}


@router.get("/me/streak")
async def get_streak(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return await streak_status(session, current_user)


@router.post("/me/streak/revive")
async def revive_streak(
    session: AsyncSession = Depends(get_session),
    config: ServerConfig = Depends(ServerConfig.from_env),
    current_user: User = Depends(get_current_user),
):
    try:
        return await revive(session, current_user, config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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


@router.get("/me/skills")
async def get_skills(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return await build_skills(session, current_user)


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
    completion_bonus_sq = (
        select(func.coalesce(func.sum(ChallengeCompletion.bonus_ap), 0))
        .where(ChallengeCompletion.user_id == User.id)
        .scalar_subquery()
    )
    bingo_bonus_sq = (
        select(func.coalesce(func.sum(ChallengeBingo.bonus_ap), 0))
        .where(ChallengeBingo.user_id == User.id)
        .scalar_subquery()
    )
    total_ap_expr = (
        func.coalesce(func.sum(Score.ap), 0.0)
        + completion_bonus_sq
        + bingo_bonus_sq
    )
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


@router.get("/players/{osu_id}/skills")
async def get_public_skills(
    osu_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_osu_id(session, osu_id)
    return await build_skills(session, user)


@router.get("/score/{score_id}")
async def get_score(
    score_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Score).where(Score.id == score_id))
    score = result.scalar_one_or_none()
    if score is None:
        raise HTTPException(status_code=404, detail="Score not found")
    pool = await build_pool(session, score.user_id)
    return serialize_score(score, pool)


# --------------------------------------------------------------------------- #
# Ranked (ELO)
# --------------------------------------------------------------------------- #


async def _resolve_local_ids(session: AsyncSession, user: User):
    if getattr(user, "use_local_challenge", False):
        return sorted(await local_beatmap_ids(session, user.id))
    return None


@router.get("/ranked")
async def get_ranked(
    session: AsyncSession = Depends(get_session),
    config: ServerConfig = Depends(ServerConfig.from_env),
    current_user: User = Depends(get_current_user),
):
    if not config.ranked_enabled:
        return {"enabled": False}
    settings = ranked_settings_from_config(config)
    now = datetime.now(timezone.utc)
    # Lazy settlement order: settle_from_db, then settle_expired, then serialize.
    async with session.begin_nested():
        await settle_from_db(session, current_user, now, settings)
    await session.commit()
    await settle_expired(session, current_user, now, settings)
    view = await ranked_serialize(session, current_user, now, settings)
    view["enabled"] = True
    return view


@router.get("/ranked/info")
async def get_ranked_info(config: ServerConfig = Depends(ServerConfig.from_env)):
    if not config.ranked_enabled:
        return {"enabled": False}
    view = ranked_info(ranked_settings_from_config(config))
    view["enabled"] = True
    return view


@router.get("/ranked/stats")
async def get_ranked_stats(
    session: AsyncSession = Depends(get_session),
    config: ServerConfig = Depends(ServerConfig.from_env),
    current_user: User = Depends(get_current_user),
):
    if not config.ranked_enabled:
        return {"enabled": False}
    settings = ranked_settings_from_config(config)
    return await ranked_stats(session, current_user, settings)


@router.post("/ranked/new")
async def post_ranked_new(
    session: AsyncSession = Depends(get_session),
    config: ServerConfig = Depends(ServerConfig.from_env),
    current_user: User = Depends(get_current_user),
):
    if not config.ranked_enabled:
        raise HTTPException(status_code=403, detail="Ranked mode is disabled")
    settings = ranked_settings_from_config(config)
    now = datetime.now(timezone.utc)
    picker = ranked_picker(config, await _resolve_local_ids(session, current_user))
    try:
        await ranked_issue(session, current_user, picker, now, settings)
    except RankedNoMaps as e:
        raise HTTPException(status_code=503, detail=str(e))
    view = await ranked_serialize(session, current_user, now, settings)
    view["enabled"] = True
    return view


@router.post("/ranked/reroll")
async def post_ranked_reroll(
    session: AsyncSession = Depends(get_session),
    config: ServerConfig = Depends(ServerConfig.from_env),
    current_user: User = Depends(get_current_user),
):
    if not config.ranked_enabled:
        raise HTTPException(status_code=403, detail="Ranked mode is disabled")
    settings = ranked_settings_from_config(config)
    now = datetime.now(timezone.utc)
    if await get_active_challenge(session, current_user.id) is None:
        raise HTTPException(status_code=409, detail="нет активного задания")
    picker = ranked_picker(config, await _resolve_local_ids(session, current_user))
    try:
        await ranked_reroll(session, current_user, picker, now, settings)
    except RankedRerollLimit as e:
        raise HTTPException(status_code=429, detail=str(e))
    except RankedNoMaps as e:
        raise HTTPException(status_code=503, detail=str(e))
    view = await ranked_serialize(session, current_user, now, settings)
    view["enabled"] = True
    return view


@router.post("/ranked/surrender")
async def post_ranked_surrender(
    session: AsyncSession = Depends(get_session),
    config: ServerConfig = Depends(ServerConfig.from_env),
    current_user: User = Depends(get_current_user),
):
    if not config.ranked_enabled:
        raise HTTPException(status_code=403, detail="Ranked mode is disabled")
    settings = ranked_settings_from_config(config)
    now = datetime.now(timezone.utc)
    result = await ranked_surrender(session, current_user, now, settings)
    if result is None:
        raise HTTPException(status_code=409, detail="нет активного задания")
    view = await ranked_serialize(session, current_user, now, settings)
    view["enabled"] = True
    return view


@router.get("/ranked/history")
async def get_ranked_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(RankedChallenge)
        .where(RankedChallenge.user_id == current_user.id)
        .order_by(RankedChallenge.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [
        {
            "id": c.id,
            "beatmap_id": c.beatmap_id,
            "beatmapset_id": c.beatmapset_id,
            "title": c.beatmap_title,
            "artist": c.artist,
            "version": c.version,
            "stars": c.stars,
            "length_sec": c.length_sec,
            "status": c.status,
            "grade": c.grade,
            "accuracy": c.accuracy,
            "mods": c.mods,
            "elo_delta": c.elo_delta,
            "elo_after": c.elo_after,
            "issued_at": c.issued_at.isoformat() if c.issued_at else None,
            "settled_at": c.settled_at.isoformat() if c.settled_at else None,
        }
        for c in result.scalars().all()
    ]


@router.get("/ranked/leaderboard")
async def get_ranked_leaderboard(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    # Single grouped query: one row per player, aggregates computed with
    # conditional SUM in the same statement (no per-player subqueries / N+1).
    result = await session.execute(
        select(
            User.osu_id,
            User.username,
            User.avatar_url,
            User.flag,
            RankedState.elo,
            func.coalesce(
                func.sum(case((RankedChallenge.status == "passed", 1), else_=0)), 0
            ).label("passed"),
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
            ).label("failed"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            RankedChallenge.status.in_(
                                ("passed", "failed", "surrendered", "expired")
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("games"),
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
            ).label("wins"),
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
            ).label("losses"),
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
            ).label("draws"),
        )
        .join(RankedState, RankedState.user_id == User.id)
        .join(RankedChallenge, RankedChallenge.user_id == User.id)
        .where(RankedChallenge.status.in_(CLOSED_STATUSES))
        .group_by(
            User.id,
            User.osu_id,
            User.username,
            User.avatar_url,
            User.flag,
            RankedState.elo,
        )
        .order_by(RankedState.elo.desc(), User.id.asc())
        .offset(offset)
        .limit(limit)
    )
    rows = []
    for i, (
        osu_id,
        username,
        avatar_url,
        flag,
        elo,
        passed,
        failed,
        games,
        wins,
        losses,
        draws,
    ) in enumerate(result.all()):
        passed = int(passed or 0)
        failed = int(failed or 0)
        wins = int(wins or 0)
        losses = int(losses or 0)
        draws = int(draws or 0)
        games = int(games or 0)
        rows.append(
            {
                "rank": offset + i + 1,
                "osu_id": osu_id,
                "username": username,
                "avatar_url": avatar_url,
                "flag": flag or "",
                "elo": elo,
                "tier": tier_for(elo).name,
                "sub_rank": sub_rank(elo),
                "games": games,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_rate": round(wins / games, 4) if games > 0 else 0.0,
            }
        )
    return rows


@router.get("/players/{osu_id}/ranked")
async def get_public_ranked(
    osu_id: int,
    config: ServerConfig = Depends(ServerConfig.from_env),
    session: AsyncSession = Depends(get_session),
):
    if not config.ranked_enabled:
        return {"enabled": False}
    user = await get_user_by_osu_id(session, osu_id)
    view = await ranked_public_stats(
        session, user, ranked_settings_from_config(config)
    )
    view["enabled"] = True
    return view
