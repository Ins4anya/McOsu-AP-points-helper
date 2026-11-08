"""Pure rules for the Ranked (ELO) mode. No IO, no DB.

Everything here is a pure function of its inputs so it can be unit-tested
without a database or network. The tunable values are bundled in
:class:`RankedSettings`; the defaults match the spec and are kept here as
constants, while ``server.config.ServerConfig`` can override them (step 4).

Mods codes are taken from ``mcsu_bot/mods.py`` MODS_BITMAP. "Auto" is labelled
``AU`` there, but osu! itself uses ``AT``; both spellings are treated as the
forbidden Auto mod.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

# --------------------------------------------------------------------------- #
# Mods
# --------------------------------------------------------------------------- #

# Forbidden mods (any of these makes a score invalid for a Ranked challenge).
# Relax / Autopilot / Auto / Cinema / Target Practice / SpunOut.
FORBIDDEN_MODS = frozenset({"RX", "AP", "AU", "AT", "CN", "TP", "SO"})

# Mods that each apply a fixed penalty on a *pass* (NF, HT).
PENALTY_MODS = frozenset({"NF", "HT"})

# EZ has no penalty but can grant a bonus on high-star maps.
EZ = "EZ"


def parse_mods(mods: Optional[str]) -> frozenset[str]:
    """Parse a canonical mods string into a set of 2-letter codes.

    Accepts ``"NM"``, ``"+HDDT"``, ``"+HDDT 1.25x"`` (and defensively a bare
    ``"HDDT"``). The leading ``+`` and any trailing rate tag are ignored; the
    remaining token is chunked into 2-letter codes (uppercased).
    """
    if not mods:
        return frozenset()
    s = str(mods).strip()
    if not s or s.upper() == "NM":
        return frozenset()
    s = s.lstrip("+")
    # Drop any trailing "<rate>x" tag (the canonical form separates it by a
    # space, e.g. "+HDDT 1.25x").
    token = s.split()[0] if s.split() else s
    codes = set()
    for i in range(0, len(token) - 1, 2):
        codes.add(token[i : i + 2].upper())
    return frozenset(codes)


def has_forbidden_mods(mods: Optional[str]) -> bool:
    return bool(parse_mods(mods) & FORBIDDEN_MODS)


def penalty_mod_count(mods: Optional[str]) -> int:
    return len(parse_mods(mods) & PENALTY_MODS)


def has_ez(mods: Optional[str]) -> bool:
    return EZ in parse_mods(mods)


# Human-readable labels for the forbidden mods (the "Auto" alias AU/AT is shown
# once, as "Auto"). Used by the public rules info endpoint.
FORBIDDEN_MOD_LABELS: tuple[tuple[str, str], ...] = (
    ("RX", "Relax"),
    ("AP", "Autopilot"),
    ("AT", "Auto"),
    ("CN", "Cinema"),
    ("TP", "Target Practice"),
    ("SO", "SpunOut"),
)


# --------------------------------------------------------------------------- #
# Tiers / ranks
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Tier:
    name: str
    min_elo: int
    min_stars: float
    max_stars: Optional[float]  # None = no upper bound


# Default tier table (lower ELO bound inclusive, star range = [min, max)).
DEFAULT_TIERS: tuple[Tier, ...] = (
    Tier("Базовый", 100, 0.5, 1.0),
    Tier("Бронза", 101, 1.0, 2.0),
    Tier("Серебро", 200, 2.0, 4.0),
    Tier("Золото", 500, 4.0, 5.0),
    Tier("Платина", 1000, 5.0, 6.0),
    Tier("Алмаз", 1500, 6.0, 7.0),
    Tier("Мастер", 2000, 7.0, 8.0),
    Tier("Профессионал", 2500, 8.0, 9.0),
    Tier("Легенда", 3000, 9.0, None),
)


def tier_for(elo: int, tiers: tuple[Tier, ...] = DEFAULT_TIERS) -> Tier:
    """Highest tier whose lower bound is <= ``elo`` (falls back to the first)."""
    current = tiers[0]
    for t in tiers:
        if elo >= t.min_elo:
            current = t
        else:
            break
    return current


def star_range(
    elo: int, tiers: tuple[Tier, ...] = DEFAULT_TIERS
) -> tuple[float, Optional[float]]:
    """The tier's outer star bounds (used for the public tier table)."""
    t = tier_for(elo, tiers)
    return t.min_stars, t.max_stars


# Number of sub-rank segments shown next to the tier (4 = 25% each). The
# indicator is server-side only; clients must not recompute it.
SUB_RANK_SEGMENTS = 4

# Legend tier: the target moves 1★ per 500 ELO and stops at 10★.
PRO_STAR_STEP_ELO = 500.0
PRO_STAR_CAP = 10.0


def _tier_index(tier: Tier, tiers: tuple[Tier, ...]) -> int:
    try:
        return tiers.index(tier)
    except ValueError:  # pragma: no cover - defensive, tiers are the configured tuple
        return 0


def star_window(
    elo: int, settings: Optional["RankedSettings"] = None
) -> tuple[float, float, float]:
    """Continuous star window for the player's current ELO.

    Returns ``(lo, hi, target)`` where the window is ``[lo, hi)`` (lower bound
    inclusive, upper exclusive) and ``target`` is its centre before ``h`` is
    applied. The window is *not* clipped to the tier's star bounds: at tier
    borders it deliberately continues into the neighbouring range.

    Special cases:

    * The first tier (Базовый) has a fixed window ``[min_stars, max_stars)``
      and no formula.
    * The last (open-ended) tier moves its target 1★ per 500 ELO, capped at
      10★; the window stops moving after the cap.
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    tier = tier_for(elo, settings.tiers)
    idx = _tier_index(tier, settings.tiers)
    h = float(settings.star_window)

    if idx == 0:
        lo = float(tier.min_stars)
        hi = float(tier.max_stars if tier.max_stars is not None else tier.min_stars + 1.0)
        return lo, hi, (lo + hi) / 2.0

    nxt = settings.tiers[idx + 1] if idx + 1 < len(settings.tiers) else None
    if nxt is not None and tier.max_stars is not None:
        span_elo = nxt.min_elo - tier.min_elo
        span_stars = float(tier.max_stars) - float(tier.min_stars)
        target = float(tier.min_stars)
        if span_elo > 0:
            target += (elo - tier.min_elo) / span_elo * span_stars
    else:
        # Open-ended top tier (Легенда).
        target = float(tier.min_stars) + (elo - tier.min_elo) / PRO_STAR_STEP_ELO
        target = min(PRO_STAR_CAP, target)

    return target - h, target + h, target


def star_ladder(
    elo: int, settings: Optional["RankedSettings"] = None
) -> list[tuple[float, Optional[float]]]:
    """Star ranges to try, in widening order (h, 2h, 4h, whole tier).

    Базовый has no ladder: only its fixed window is returned. The last range
    is the tier's own ``[min_stars, max_stars)`` (``None`` upper bound for
    Легенда). Exact duplicates are dropped while order is preserved.
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    tier = tier_for(elo, settings.tiers)
    idx = _tier_index(tier, settings.tiers)
    if idx == 0:
        hi = tier.max_stars if tier.max_stars is not None else None
        return [(float(tier.min_stars), hi)]

    h = float(settings.star_window)
    _lo, _hi, target = star_window(elo, settings)
    windows: list[tuple[float, Optional[float]]] = [
        (max(0.0, target - h), target + h),
        (max(0.0, target - 2 * h), target + 2 * h),
        (max(0.0, target - 4 * h), target + 4 * h),
        (
            float(tier.min_stars),
            None if tier.max_stars is None else float(tier.max_stars),
        ),
    ]

    out: list[tuple[float, Optional[float]]] = []
    for window in windows:
        if window not in out:
            out.append(window)
    return out


def sub_rank(
    elo: int, settings: Optional["RankedSettings"] = None
) -> Optional[dict]:
    """Four-segment progress indicator inside the current tier.

    ``filled`` is 1..4 (never 0 when entering a tier, capped at 4 at the end).
    Returns ``None`` for Базовый and the open-ended Легенда.
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    tier = tier_for(elo, settings.tiers)
    idx = _tier_index(tier, settings.tiers)
    if idx == 0 or idx + 1 >= len(settings.tiers) or tier.max_stars is None:
        return None

    nxt = settings.tiers[idx + 1]
    span = nxt.min_elo - tier.min_elo
    if span <= 0:  # pragma: no cover - defensive, valid tiers always span
        return None

    fraction = (elo - tier.min_elo) / span
    fraction = max(0.0, min(1.0, fraction))
    filled = min(SUB_RANK_SEGMENTS, int(fraction * SUB_RANK_SEGMENTS) + 1)
    return {"filled": filled, "total": SUB_RANK_SEGMENTS}


def progress_to_next(
    elo: int, tiers: tuple[Tier, ...] = DEFAULT_TIERS
) -> dict:
    """Progress of ``elo`` within its tier towards the next tier."""
    tier = tier_for(elo, tiers)
    idx = tiers.index(tier)
    nxt = tiers[idx + 1] if idx + 1 < len(tiers) else None
    if nxt is None:
        return {
            "tier": tier.name,
            "min_elo": tier.min_elo,
            "next_tier": None,
            "next_min_elo": None,
            "points": max(0, elo - tier.min_elo),
            "points_to_next": None,
            "span": None,
            "percent": 100.0,
        }
    span = nxt.min_elo - tier.min_elo
    points = max(0, elo - tier.min_elo)
    return {
        "tier": tier.name,
        "min_elo": tier.min_elo,
        "next_tier": nxt.name,
        "next_min_elo": nxt.min_elo,
        "points": points,
        "points_to_next": max(0, nxt.min_elo - elo),
        "span": span,
        "percent": round(100.0 * points / span, 1) if span > 0 else 100.0,
    }


# --------------------------------------------------------------------------- #
# Settlements / delta
# --------------------------------------------------------------------------- #

# Grades that count as a pass (C and above).
PASS_GRADES = frozenset({"C", "B", "A", "S", "SH", "X", "XH"})

# osu! stable spellings -> this codebase's lazer-style names.
GRADE_ALIASES = {"SS": "X", "SSH": "XH"}

# Accuracy reward breakpoints: (accuracy, reward). Linear interpolation between
# points, rounded half-up. Below the first point the reward is the first
# point's reward; above the last point it is capped at the last point's reward.
# Rewards may be negative: below 90% accuracy the score loses ELO.
DEFAULT_ACC_REWARD_TABLE: tuple[tuple[float, int], ...] = (
    (0.70, -60),
    (0.90, 0),
    (1.0, 60),
)


def normalize_grade(grade: Optional[str]) -> str:
    """Normalise a raw grade string to the canonical set.

    Maps osu! stable ``SS``/``SSH`` to ``X``/``XH``, uppercases, and treats a
    missing grade as ``D`` (a fail). Unknown values pass through unchanged and
    will be treated as a fail (they are not in ``PASS_GRADES``).
    """
    g = (grade or "").strip().upper()
    if not g:
        return "D"
    return GRADE_ALIASES.get(g, g)


@dataclass(frozen=True)
class RankedSettings:
    tiers: tuple[Tier, ...] = DEFAULT_TIERS

    elo_floor: int = 100
    start_elo: int = 500

    acc_reward_table: tuple[tuple[float, int], ...] = DEFAULT_ACC_REWARD_TABLE
    fail_delta: int = -60
    nf_ht_penalty: int = -10  # per mod (NF, HT)
    ez_bonus_stars_low: float = 5.0
    ez_bonus_low: int = 10
    ez_bonus_stars_high: float = 6.0
    ez_bonus_high: int = 20
    clamp_min: int = -60
    clamp_max: int = 80

    reroll_penalty: int = -5
    daily_reroll_limit: int = 3
    recent_exclude: int = 20

    # Half-width of the continuous star window: window = [target - h, target + h).
    star_window: float = 0.15

    time_tolerance_seconds: int = 120
    timeout_multiplier: float = 3.0
    timeout_min_seconds: int = 600
    expiry_grace_seconds: int = 300

    @classmethod
    def default(cls) -> "RankedSettings":
        return cls()


DEFAULT_SETTINGS = RankedSettings.default()


def info(settings: RankedSettings = DEFAULT_SETTINGS) -> dict:
    """Public description of the Ranked rules (no secrets, no internal state)."""
    tiers = []
    for i, t in enumerate(settings.tiers):
        nxt = settings.tiers[i + 1] if i + 1 < len(settings.tiers) else None
        tiers.append(
            {
                "name": t.name,
                "min_elo": t.min_elo,
                "next_min_elo": nxt.min_elo if nxt else None,
                "min_stars": t.min_stars,
                "max_stars": t.max_stars,
            }
        )
    return {
        "tiers": tiers,
        "acc_reward_table": [list(p) for p in settings.acc_reward_table],
        "fail_delta": settings.fail_delta,
        "nf_ht_penalty": settings.nf_ht_penalty,
        "ez_bonus": {
            "stars_low": settings.ez_bonus_stars_low,
            "bonus_low": settings.ez_bonus_low,
            "stars_high": settings.ez_bonus_stars_high,
            "bonus_high": settings.ez_bonus_high,
        },
        "clamp": {"min": settings.clamp_min, "max": settings.clamp_max},
        "start_elo": settings.start_elo,
        "elo_floor": settings.elo_floor,
        "timeout": {
            "tolerance_seconds": settings.time_tolerance_seconds,
            "multiplier": settings.timeout_multiplier,
            "min_seconds": settings.timeout_min_seconds,
            "grace_seconds": settings.expiry_grace_seconds,
        },
        "reroll": {
            "penalty": settings.reroll_penalty,
            "daily_limit": settings.daily_reroll_limit,
        },
        "star_window": settings.star_window,
        "sub_rank_segments": SUB_RANK_SEGMENTS,
        "forbidden_mods": [
            {"code": code, "name": name} for code, name in FORBIDDEN_MOD_LABELS
        ],
    }


def _round_half_up(value: float) -> int:
    """Round half-up, guarding against binary-float noise before rounding."""
    return math.floor(round(value, 6) + 0.5)


def accuracy_reward(accuracy: float, settings: RankedSettings) -> int:
    """Reward for any pass, from the accuracy breakpoints.

    Linear interpolation between breakpoints, rounded half-up. Below the first
    point the reward is the first point's reward; above the last point it is
    capped at the last point's reward. Rewards may be negative.
    """
    table = settings.acc_reward_table
    acc = float(accuracy)
    first_acc, first_reward = table[0]
    last_acc, last_reward = table[-1]
    if acc <= first_acc:
        return first_reward
    if acc >= last_acc:
        return last_reward
    for i in range(len(table) - 1):
        a0, r0 = table[i]
        a1, r1 = table[i + 1]
        if a0 <= acc <= a1:
            if a1 == a0:
                return r0
            t = (acc - a0) / (a1 - a0)
            return _round_half_up(r0 + t * (r1 - r0))
    return last_reward


def evaluate(
    grade: str,
    accuracy: float,
    mods: Optional[str],
    stars: float,
    settings: RankedSettings = DEFAULT_SETTINGS,
) -> tuple[str, int]:
    """Evaluate one score against the rules.

    Returns ``(verdict, delta)`` where verdict is one of:

    * ``"invalid"`` — forbidden mod present; the challenge is left active.
    * ``"fail"``    — grade D or below (or surrender/timeout); always exactly
      ``fail_delta`` (-60), mods do not apply.
    * ``"pass"``    — grade C and above; the accuracy-table reward always
      applies, then mods, then clamped to [clamp_min, clamp_max].
    """
    codes = parse_mods(mods)
    if codes & FORBIDDEN_MODS:
        return ("invalid", 0)

    g = normalize_grade(grade)
    if g not in PASS_GRADES:
        return ("fail", settings.fail_delta)

    delta = accuracy_reward(accuracy, settings)
    delta += settings.nf_ht_penalty * len(codes & PENALTY_MODS)

    if EZ in codes:
        if float(stars) >= settings.ez_bonus_stars_high:
            delta += settings.ez_bonus_high
        elif float(stars) >= settings.ez_bonus_stars_low:
            delta += settings.ez_bonus_low

    delta = max(settings.clamp_min, min(settings.clamp_max, delta))
    return ("pass", delta)


def apply_delta(
    elo: int, delta: int, settings: RankedSettings = DEFAULT_SETTINGS
) -> int:
    """Apply ``delta`` to ``elo``, never dropping below ``elo_floor``."""
    return max(settings.elo_floor, int(elo) + int(delta))


# --------------------------------------------------------------------------- #
# Time helpers (pure)
# --------------------------------------------------------------------------- #


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalise a datetime to timezone-aware UTC.

    Naive datetimes are treated as UTC (SQLite/SQLAlchemy ``DateTime`` without
    ``timezone=True`` returns naive datetimes).
    """
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def timeout_seconds(
    length_sec: int, settings: RankedSettings = DEFAULT_SETTINGS
) -> int:
    """Challenge timeout: map length * multiplier, floored at the minimum."""
    length = int(length_sec or 0)
    return max(int(length * settings.timeout_multiplier), settings.timeout_min_seconds)


def is_within_window(
    played_at: datetime,
    issued_at: datetime,
    now: datetime,
    settings: RankedSettings = DEFAULT_SETTINGS,
) -> bool:
    """True if ``played_at`` is in [issued_at - tolerance, now]."""
    p = as_utc(played_at)
    i = as_utc(issued_at)
    n = as_utc(now)
    tol = timedelta(seconds=settings.time_tolerance_seconds)
    return (i - tol) <= p <= n
