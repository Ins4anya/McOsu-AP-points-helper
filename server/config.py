from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from server.ranked_rules import DEFAULT_ACC_REWARD_TABLE

_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r, using default %r", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r, using default %r", name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    v = raw.strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    logger.warning("Invalid %s=%r, using default %r", name, raw, default)
    return default


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = "sqlite+aiosqlite:///scores_server.db"

    osu_client_id: str = ""
    osu_client_secret: str = ""
    osu_redirect_uri: str = "http://localhost:8000/auth/callback"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 30

    site_url: str = "http://localhost:8000"

    daily_challenge_enabled: bool = True
    daily_challenge_maps: int = 5
    daily_challenge_per_map_bonus: int = 200
    daily_challenge_bingo_bonus: int = 500
    daily_challenge_min_stars: float = 4.0
    daily_challenge_max_stars: float = 7.0
    daily_challenge_max_length: int = 600

    # Ranked (ELO)
    ranked_enabled: bool = False
    ranked_elo_floor: int = 100
    ranked_start_elo: int = 500
    ranked_acc_reward_table: tuple = DEFAULT_ACC_REWARD_TABLE
    ranked_fail_delta: int = -60
    ranked_nf_ht_penalty: int = -10
    ranked_clamp_min: int = -60
    ranked_clamp_max: int = 80
    ranked_ez_bonus_stars_low: float = 5.0
    ranked_ez_bonus_low: int = 10
    ranked_ez_bonus_stars_high: float = 6.0
    ranked_ez_bonus_high: int = 20
    ranked_time_tolerance_seconds: int = 120
    ranked_timeout_multiplier: float = 3.0
    ranked_timeout_min_seconds: int = 600
    ranked_expiry_grace_seconds: int = 300
    ranked_reroll_penalty: int = -5
    ranked_daily_reroll_limit: int = 3
    ranked_recent_exclude: int = 20
    ranked_star_window: float = 0.15
    ranked_min_length_seconds: int = 60
    ranked_max_length_seconds: int = 600
    ranked_high_star_threshold: float = 7.0
    ranked_high_star_statuses: str = "ranked,loved"

    @classmethod
    def from_env(cls) -> "ServerConfig":
        c = cls(
            host=os.getenv("HOST", cls.host),
            port=int(os.getenv("PORT", str(cls.port))),
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            osu_client_id=os.getenv("OSU_CLIENT_ID", cls.osu_client_id),
            osu_client_secret=os.getenv("OSU_CLIENT_SECRET", cls.osu_client_secret),
            osu_redirect_uri=os.getenv("OSU_REDIRECT_URI", cls.osu_redirect_uri),
            jwt_secret=os.getenv("JWT_SECRET", cls.jwt_secret),
            site_url=os.getenv("SITE_URL", cls.site_url),
            daily_challenge_enabled=os.getenv(
                "DAILY_CHALLENGE_ENABLED", str(cls.daily_challenge_enabled)
            ).lower()
            in ("1", "true", "yes", "on"),
            daily_challenge_maps=int(
                os.getenv("DAILY_CHALLENGE_MAPS", str(cls.daily_challenge_maps))
            ),
            daily_challenge_per_map_bonus=int(
                os.getenv(
                    "DAILY_CHALLENGE_PER_MAP_BONUS",
                    str(cls.daily_challenge_per_map_bonus),
                )
            ),
            daily_challenge_bingo_bonus=int(
                os.getenv(
                    "DAILY_CHALLENGE_BINGO_BONUS",
                    str(cls.daily_challenge_bingo_bonus),
                )
            ),
            daily_challenge_min_stars=float(
                os.getenv(
                    "DAILY_CHALLENGE_MIN_STARS", str(cls.daily_challenge_min_stars)
                )
            ),
            daily_challenge_max_stars=float(
                os.getenv(
                    "DAILY_CHALLENGE_MAX_STARS", str(cls.daily_challenge_max_stars)
                )
            ),
            daily_challenge_max_length=int(
                os.getenv(
                    "DAILY_CHALLENGE_MAX_LENGTH",
                    str(cls.daily_challenge_max_length),
                )
            ),
        )
        _apply_ranked_env(c)
        return c


def _checked(ok: bool, value, default, name: str):
    if ok:
        return value
    logger.warning("Invalid ranked config %s=%r, using default %r", name, value, default)
    return default


def _parse_acc_reward_table(raw: str):
    """Parse "0.70:-60,0.90:0,1.0:60" into ((acc, reward), ...), or None on error."""
    points = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            acc_s, reward_s = part.split(":", 1)
            points.append((float(acc_s.strip()), int(reward_s.strip())))
        except (ValueError, TypeError):
            return None
    return tuple(points)


def _valid_acc_reward_table(points) -> bool:
    """Reward table must have >=2 points, strictly increasing accuracy,
    non-decreasing reward, first accuracy > 0 and last accuracy <= 1.0.

    Rewards may be negative (below 90% accuracy the score loses ELO).
    """
    if not points or len(points) < 2:
        return False
    for i in range(len(points) - 1):
        if points[i][0] >= points[i + 1][0]:  # accuracy strictly increasing
            return False
        if points[i][1] > points[i + 1][1]:  # reward non-decreasing
            return False
    if points[0][0] <= 0:
        return False
    if points[-1][0] > 1.0:
        return False
    return True


def _apply_ranked_env(c: ServerConfig) -> None:
    """Parse and validate RANKED_* env vars, falling back to defaults (no crash)."""
    cls = ServerConfig

    c.ranked_enabled = _env_bool("RANKED_ENABLED", cls.ranked_enabled)

    c.ranked_elo_floor = _env_int("RANKED_ELO_FLOOR", cls.ranked_elo_floor)
    c.ranked_start_elo = _env_int("RANKED_START_ELO", cls.ranked_start_elo)
    if c.ranked_elo_floor > c.ranked_start_elo:
        logger.warning(
            "Invalid ranked config: elo_floor=%r > start_elo=%r; using defaults",
            c.ranked_elo_floor, c.ranked_start_elo,
        )
        c.ranked_elo_floor, c.ranked_start_elo = cls.ranked_elo_floor, cls.ranked_start_elo

    fail_delta = _env_int("RANKED_FAIL_DELTA", cls.ranked_fail_delta)
    c.ranked_fail_delta = _checked(fail_delta <= 0, fail_delta, cls.ranked_fail_delta, "ranked_fail_delta")
    nf_ht = _env_int("RANKED_NF_HT_PENALTY", cls.ranked_nf_ht_penalty)
    c.ranked_nf_ht_penalty = _checked(nf_ht <= 0, nf_ht, cls.ranked_nf_ht_penalty, "ranked_nf_ht_penalty")
    reroll = _env_int("RANKED_REROLL_PENALTY", cls.ranked_reroll_penalty)
    c.ranked_reroll_penalty = _checked(reroll <= 0, reroll, cls.ranked_reroll_penalty, "ranked_reroll_penalty")

    c.ranked_clamp_min = _env_int("RANKED_CLAMP_MIN", cls.ranked_clamp_min)
    c.ranked_clamp_max = _env_int("RANKED_CLAMP_MAX", cls.ranked_clamp_max)
    if c.ranked_clamp_min > c.ranked_clamp_max:
        logger.warning(
            "Invalid ranked config: clamp_min=%r > clamp_max=%r; using defaults",
            c.ranked_clamp_min, c.ranked_clamp_max,
        )
        c.ranked_clamp_min, c.ranked_clamp_max = cls.ranked_clamp_min, cls.ranked_clamp_max

    c.ranked_ez_bonus_stars_low = _env_float(
        "RANKED_EZ_BONUS_STARS_LOW", cls.ranked_ez_bonus_stars_low
    )
    c.ranked_ez_bonus_low = _env_int("RANKED_EZ_BONUS_LOW", cls.ranked_ez_bonus_low)
    c.ranked_ez_bonus_stars_high = _env_float(
        "RANKED_EZ_BONUS_STARS_HIGH", cls.ranked_ez_bonus_stars_high
    )
    c.ranked_ez_bonus_high = _env_int("RANKED_EZ_BONUS_HIGH", cls.ranked_ez_bonus_high)

    raw_table = os.getenv("RANKED_ACC_REWARD_TABLE", "")
    if raw_table:
        parsed = _parse_acc_reward_table(raw_table)
        if parsed is None or not _valid_acc_reward_table(parsed):
            logger.warning(
                "Invalid ranked config RANKED_ACC_REWARD_TABLE=%r; using default", raw_table
            )
            c.ranked_acc_reward_table = cls.ranked_acc_reward_table
        else:
            c.ranked_acc_reward_table = parsed

    c.ranked_time_tolerance_seconds = _env_int(
        "RANKED_TIME_TOLERANCE_SECONDS", cls.ranked_time_tolerance_seconds
    )
    mult = _env_float("RANKED_TIMEOUT_MULTIPLIER", cls.ranked_timeout_multiplier)
    c.ranked_timeout_multiplier = _checked(mult > 0, mult, cls.ranked_timeout_multiplier, "ranked_timeout_multiplier")
    c.ranked_timeout_min_seconds = _env_int(
        "RANKED_TIMEOUT_MIN_SECONDS", cls.ranked_timeout_min_seconds
    )
    c.ranked_expiry_grace_seconds = _env_int(
        "RANKED_EXPIRY_GRACE_SECONDS", cls.ranked_expiry_grace_seconds
    )

    limit = _env_int("RANKED_DAILY_REROLL_LIMIT", cls.ranked_daily_reroll_limit)
    c.ranked_daily_reroll_limit = _checked(limit >= 0, limit, cls.ranked_daily_reroll_limit, "ranked_daily_reroll_limit")
    c.ranked_recent_exclude = _env_int("RANKED_RECENT_EXCLUDE", cls.ranked_recent_exclude)
    star_window = _env_float("RANKED_STAR_WINDOW", cls.ranked_star_window)
    c.ranked_star_window = _checked(
        0.0 < star_window <= 1.0,
        star_window,
        cls.ranked_star_window,
        "ranked_star_window",
    )

    c.ranked_min_length_seconds = _env_int(
        "RANKED_MIN_LENGTH_SECONDS", cls.ranked_min_length_seconds
    )
    c.ranked_max_length_seconds = _env_int(
        "RANKED_MAX_LENGTH_SECONDS", cls.ranked_max_length_seconds
    )
    if c.ranked_min_length_seconds >= c.ranked_max_length_seconds:
        logger.warning(
            "Invalid ranked config: min_length=%r >= max_length=%r; using defaults",
            c.ranked_min_length_seconds, c.ranked_max_length_seconds,
        )
        c.ranked_min_length_seconds = cls.ranked_min_length_seconds
        c.ranked_max_length_seconds = cls.ranked_max_length_seconds

    c.ranked_high_star_threshold = _env_float(
        "RANKED_HIGH_STAR_THRESHOLD", cls.ranked_high_star_threshold
    )
    c.ranked_high_star_statuses = os.getenv(
        "RANKED_HIGH_STAR_STATUSES", cls.ranked_high_star_statuses
    )
