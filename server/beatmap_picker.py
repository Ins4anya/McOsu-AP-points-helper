from __future__ import annotations

import asyncio
import random
import string

import httpx

from server.auth import get_osu_client_token
from server.config import ServerConfig

SEARCH_URL = "https://osu.ppy.sh/api/v2/beatmapsets/search"
BEATMAP_URL = "https://osu.ppy.sh/api/v2/beatmaps"

_QUERY_CHARS = string.ascii_lowercase + string.digits

# Statuses accepted by the osu! API v2 /beatmapsets/search ``s`` parameter
# (the "ranked" filter already covers legacy "approved" mapsets).
VALID_STATUSES = ("ranked", "loved", "qualified", "pending", "graveyard", "wip")


def _random_query() -> str:
    return "".join(random.choices(_QUERY_CHARS, k=2))


def _eligible(
    beatmap: dict,
    min_stars: float,
    max_stars: float | None,
    min_length: int,
    max_length: int,
    exclusive_max: bool = False,
) -> bool:
    """Client-side filter of a *difficulty* within a set.

    The osu! search filters sets, so a set can match the query while its
    individual difficulties fall outside the range; this re-checks each
    difficulty (stars, mode, length). ``exclusive_max`` controls whether the
    upper star bound is ``<`` (Ranked) or ``<=`` (legacy Daily Challenge).
    """
    stars = beatmap.get("difficulty_rating") or 0.0
    if stars < min_stars:
        return False
    if max_stars is not None:
        if exclusive_max:
            if stars >= max_stars:
                return False
        elif stars > max_stars:
            return False

    length = beatmap.get("total_length") or beatmap.get("hit_length") or 0
    if length <= 0 or length < min_length or length > max_length:
        return False

    mode = beatmap.get("mode")
    if mode not in (None, "osu", 0):
        return False

    return True


def _normalize(beatmap: dict, beatmapset: dict) -> dict:
    beatmap_id = int(beatmap.get("id") or 0)
    beatmapset_id = int(
        beatmapset.get("id") or beatmap.get("beatmapset_id") or 0
    )
    artist = beatmapset.get("artist") or ""
    title = beatmapset.get("title") or ""
    version = beatmap.get("version") or ""
    return {
        "beatmap_id": beatmap_id,
        "beatmapset_id": beatmapset_id,
        "beatmap_title": f"{artist} - {title} [{version}]".strip(),
        "artist": artist,
        "version": version,
        "stars": float(beatmap.get("difficulty_rating") or 0.0),
        "length": int(beatmap.get("total_length") or beatmap.get("hit_length") or 0),
        "beatmap_url": (
            f"https://osu.ppy.sh/beatmapsets/{beatmapset_id}#osu/{beatmap_id}"
        ),
        "download_url": f"https://osu.ppy.sh/beatmapsets/{beatmapset_id}/download",
    }


def _stars_query(min_stars: float, max_stars: float | None) -> str:
    if max_stars is None:
        return f"stars>={min_stars:g}"
    return f"stars>={min_stars:g} stars<{max_stars:g}"


async def _search_page(
    client: httpx.AsyncClient,
    headers: dict,
    q: str,
    status: str,
    page: int | None = None,
) -> list[dict]:
    params = {
        "q": q,
        "m": 0,
        "s": status,
        "nsfw": "false",
        "page": page if page is not None else random.randint(1, 10),
    }
    try:
        resp = await client.get(SEARCH_URL, headers=headers, params=params, timeout=15)
    except Exception:
        return []
    if resp.status_code != 200:
        return []  # skip 4xx / 5xx without crashing
    try:
        data = resp.json()
    except Exception:
        return []
    return data.get("beatmapsets") or []


def _collect(
    beatmapsets: list[dict],
    candidates: list[dict],
    seen: set[int],
    min_stars: float,
    max_stars: float | None,
    min_length: int,
    max_length: int,
    exclusive_max: bool,
) -> None:
    for bmset in beatmapsets:
        for bm in bmset.get("beatmaps") or []:
            bid = int(bm.get("id") or 0)
            if not bid or bid in seen:
                continue
            if not _eligible(
                bm, min_stars, max_stars, min_length, max_length, exclusive_max
            ):
                continue
            seen.add(bid)
            candidates.append(_normalize(bm, bmset))


async def fetch_challenge_maps(
    config: ServerConfig,
    count: int = 5,
    *,
    min_stars: float | None = None,
    max_stars: float | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    statuses: list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    """Fetch ``count`` maps.

    * With no explicit ``min_stars``/``max_stars`` (the Daily Challenge path):
      the legacy behaviour is preserved — random 2-char ``q`` + random page,
      inclusive ``4.0–7.0★`` filter, length ``<= 600``, status ``ranked``.
    * With explicit ``min_stars``/``max_stars`` (the Ranked path): a targeted
      ``q="stars>=X stars<Y"`` query, per-status loop, exclusive upper bound.
    """
    if not config.daily_challenge_enabled:
        return []
    if not config.osu_client_id or not config.osu_client_secret:
        return []

    try:
        token = await get_osu_client_token(config)
    except Exception:
        return []

    headers = {"Authorization": f"Bearer {token}"}
    candidates: list[dict] = []
    seen_ids: set[int] = set()

    legacy = min_stars is None and max_stars is None
    if legacy:
        lo = config.daily_challenge_min_stars
        hi = config.daily_challenge_max_stars
        min_len = 0
        max_len = config.daily_challenge_max_length
        max_attempts = max(count, 1) * 8
        async with httpx.AsyncClient() as client:
            for _ in range(max_attempts):
                if len(candidates) >= count:
                    break
                bmsets = await _search_page(client, headers, _random_query(), "ranked")
                _collect(bmsets, candidates, seen_ids, lo, hi, min_len, max_len, False)
    else:
        lo = float(min_stars)
        hi = float(max_stars) if max_stars is not None else None
        min_len = int(min_length or 0)
        max_len = int(max_length if max_length is not None else config.daily_challenge_max_length)
        statuses = ("ranked",) if statuses is None else tuple(statuses)
        q = _stars_query(lo, hi)
        async with httpx.AsyncClient() as client:
            for status in statuses:
                if status not in VALID_STATUSES:
                    continue
                bmsets = await _search_page(client, headers, q, status, page=1)
                _collect(bmsets, candidates, seen_ids, lo, hi, min_len, max_len, True)

    if len(candidates) <= count:
        return candidates
    return random.sample(candidates, count)


# How many local-library beatmaps to inspect per challenge build. We now scan
# the *whole* library in a shuffled order (stopping as soon as we have enough
# eligible maps) instead of a tiny random sample that could miss every eligible
# map. The limit below is only a safety cap against pathological libraries
# (hundreds of thousands of maps) so a single build can never issue an unbounded
# number of osu! API lookups.
LOCAL_LOOKUP_LIMIT = 1000
LOCAL_LOOKUP_CONCURRENCY = 10


async def _lookup_beatmap(
    client: httpx.AsyncClient, headers: dict, bid: int
) -> dict | None:
    """Return the osu! API v2 beatmap dict for ``bid``, or None on any failure."""
    try:
        resp = await client.get(f"{BEATMAP_URL}/{bid}", headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


async def fetch_personal_challenge_maps(
    config: ServerConfig,
    local_ids: list[int],
    count: int = 5,
    *,
    min_stars: float | None = None,
    max_stars: float | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    statuses: list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    """Fetch challenge maps from the user's local library (with a ranked pool
    fallback), filtered to the requested star range."""
    if not config.daily_challenge_enabled:
        return []

    legacy = min_stars is None and max_stars is None
    if legacy:
        lo = config.daily_challenge_min_stars
        hi = config.daily_challenge_max_stars
        min_len = 0
        max_len = config.daily_challenge_max_length
        statuses = ("ranked",)
    else:
        lo = float(min_stars)
        hi = float(max_stars) if max_stars is not None else None
        min_len = int(min_length or 0)
        max_len = int(max_length if max_length is not None else config.daily_challenge_max_length)
        statuses = ("ranked",) if statuses is None else tuple(statuses)
    exclusive = not legacy

    picked: list[dict] = []
    seen_ids: set[int] = set()

    if local_ids and config.osu_client_id and config.osu_client_secret:
        try:
            token = await get_osu_client_token(config)
        except Exception:
            token = ""
        if token:
            headers = {"Authorization": f"Bearer {token}"}
            ordered = list(local_ids)
            random.shuffle(ordered)
            ordered = ordered[:LOCAL_LOOKUP_LIMIT]
            async with httpx.AsyncClient() as client:
                for i in range(0, len(ordered), LOCAL_LOOKUP_CONCURRENCY):
                    if len(picked) >= count:
                        break
                    chunk = ordered[i : i + LOCAL_LOOKUP_CONCURRENCY]
                    results = await asyncio.gather(
                        *(_lookup_beatmap(client, headers, bid) for bid in chunk)
                    )
                    for bm in results:
                        if len(picked) >= count:
                            break
                        if not bm:
                            continue
                        bmset = bm.get("beatmapset") or {}
                        norm_bid = int(bm.get("id") or 0)
                        if norm_bid in seen_ids or not _eligible(
                            bm, lo, hi, min_len, max_len, exclusive
                        ):
                            continue
                        seen_ids.add(norm_bid)
                        picked.append(_normalize(bm, bmset))

    if len(picked) < count:
        filler = await fetch_challenge_maps(
            config,
            count - len(picked),
            min_stars=lo,
            max_stars=hi,
            min_length=min_len,
            max_length=max_len,
            statuses=statuses,
        )
        for norm in filler:
            if len(picked) >= count:
                break
            if norm["beatmap_id"] not in seen_ids:
                seen_ids.add(norm["beatmap_id"])
                picked.append(norm)

    return picked
