from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from server.beatmap_picker import fetch_challenge_maps, fetch_personal_challenge_maps
from server.config import ServerConfig
from server.database import (
    ChallengeBingo,
    ChallengeCompletion,
    DailyChallengeMap,
    User,
    UserLocalBeatmap,
)
from server.dates import date_str, today_str


def challenge_owner(user: User) -> int:
    return user.id if user.use_local_challenge else 0


async def get_maps(
    session: AsyncSession, date: str, owner: int = 0
) -> list[DailyChallengeMap]:
    result = await session.execute(
        select(DailyChallengeMap)
        .where(
            DailyChallengeMap.date == date,
            DailyChallengeMap.user_id == owner,
        )
        .order_by(DailyChallengeMap.slot)
    )
    return list(result.scalars().all())


async def local_beatmap_ids(session: AsyncSession, user_id: int) -> set[int]:
    result = await session.execute(
        select(UserLocalBeatmap.beatmap_id).where(UserLocalBeatmap.user_id == user_id)
    )
    return {int(bid) for bid in result.scalars().all()}


async def get_or_create_maps(
    session: AsyncSession, config: ServerConfig, date: str, owner: int = 0
) -> list[DailyChallengeMap]:
    if not config.daily_challenge_enabled:
        return []

    # Retry a few times: two concurrent requests may both observe "no maps"
    # and both insert; the loser hits IntegrityError and simply re-reads the
    # winner's rows on the next pass instead of returning an empty set.
    for _ in range(3):
        maps = await get_maps(session, date, owner)
        if maps:
            return maps

        if owner:
            local_ids = sorted(await local_beatmap_ids(session, owner))
            fetched = await fetch_personal_challenge_maps(
                config, local_ids, config.daily_challenge_maps
            )
        else:
            fetched = await fetch_challenge_maps(config, config.daily_challenge_maps)
        if not fetched:
            return []

        for slot, data in enumerate(fetched):
            session.add(
                DailyChallengeMap(
                    user_id=owner,
                    date=date,
                    slot=slot,
                    beatmap_id=data["beatmap_id"],
                    beatmapset_id=data["beatmapset_id"],
                    beatmap_title=data["beatmap_title"],
                    version=data["version"],
                    stars=data["stars"],
                    length=data["length"],
                    beatmap_url=data["beatmap_url"],
                    download_url=data["download_url"],
                )
            )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            continue

        return await get_maps(session, date, owner)

    return await get_maps(session, date, owner)


async def serialize_challenge(
    session: AsyncSession, config: ServerConfig, user: User, date: str
) -> dict:
    if not config.daily_challenge_enabled:
        return {"enabled": False}

    owner = challenge_owner(user)
    maps = await get_or_create_maps(session, config, date, owner)
    if not maps:
        return {"enabled": False}

    user_id = user.id
    map_ids = [m.id for m in maps]
    result = await session.execute(
        select(ChallengeCompletion).where(
            ChallengeCompletion.user_id == user_id,
            ChallengeCompletion.challenge_map_id.in_(map_ids),
        )
    )
    completions = {c.challenge_map_id: c for c in result.scalars().all()}

    result = await session.execute(
        select(ChallengeBingo).where(
            ChallengeBingo.user_id == user_id,
            ChallengeBingo.date == date,
        )
    )
    bingo = result.scalar_one_or_none()

    local_ids = await local_beatmap_ids(session, user_id)

    maps_payload = []
    for m in maps:
        c = completions.get(m.id)
        maps_payload.append(
            {
                "slot": m.slot,
                "beatmap_id": m.beatmap_id,
                "beatmapset_id": m.beatmapset_id,
                "title": m.beatmap_title,
                "version": m.version,
                "stars": m.stars,
                "length": m.length,
                "beatmap_url": m.beatmap_url,
                "download_url": m.download_url,
                "downloaded": m.beatmap_id in local_ids,
                "done": c is not None,
                "completed_score_id": c.score_id if c else None,
            }
        )

    completed_count = sum(1 for p in maps_payload if p["done"])
    return {
        "enabled": True,
        "date": date,
        "personal": bool(owner),
        "local_count": len(local_ids),
        "bonus_per_map": config.daily_challenge_per_map_bonus,
        "bingo_bonus": config.daily_challenge_bingo_bonus,
        "maps": maps_payload,
        "completed_count": completed_count,
        "bingo_done": bingo is not None,
    }


async def challenge_bonus_total(session: AsyncSession, user_id: int) -> float:
    result = await session.execute(
        select(func.coalesce(func.sum(ChallengeCompletion.bonus_ap), 0)).where(
            ChallengeCompletion.user_id == user_id
        )
    )
    completion_bonus = result.scalar() or 0

    result = await session.execute(
        select(func.coalesce(func.sum(ChallengeBingo.bonus_ap), 0)).where(
            ChallengeBingo.user_id == user_id
        )
    )
    bingo_bonus = result.scalar() or 0

    return float(completion_bonus) + float(bingo_bonus)


async def apply_completion(
    session: AsyncSession,
    config: ServerConfig,
    user_id: int,
    challenge_map: DailyChallengeMap,
    score_id: int,
) -> dict:
    existing = await session.execute(
        select(ChallengeCompletion).where(
            ChallengeCompletion.user_id == user_id,
            ChallengeCompletion.challenge_map_id == challenge_map.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return {"completed": False, "bingo": False}

    session.add(
        ChallengeCompletion(
            user_id=user_id,
            challenge_map_id=challenge_map.id,
            score_id=score_id,
            bonus_ap=config.daily_challenge_per_map_bonus,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return {"completed": False, "bingo": False}

    date = challenge_map.date
    maps = await get_maps(session, date, challenge_map.user_id)
    result = await session.execute(
        select(ChallengeCompletion).where(
            ChallengeCompletion.user_id == user_id,
            ChallengeCompletion.challenge_map_id.in_([m.id for m in maps]),
        )
    )
    completed_ids = {c.challenge_map_id for c in result.scalars().all()}
    all_done = bool(maps) and all(m.id in completed_ids for m in maps)

    bingo_awarded = False
    if all_done:
        existing_bingo = await session.execute(
            select(ChallengeBingo).where(
                ChallengeBingo.user_id == user_id,
                ChallengeBingo.date == date,
            )
        )
        if existing_bingo.scalar_one_or_none() is None:
            session.add(
                ChallengeBingo(
                    user_id=user_id,
                    date=date,
                    bonus_ap=config.daily_challenge_bingo_bonus,
                )
            )
            try:
                await session.commit()
                bingo_awarded = True
            except IntegrityError:
                await session.rollback()

    return {"completed": True, "bingo": bingo_awarded}
