from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import Score, User

# --- Пороги (константы в коде: config.json содержит секреты и не трогаем) ---

TOP_SCORES_LIMIT = 300        # сколько топовых скоров по AP берётся в расчёт
MIN_VALID_SCORES = 3          # минимум скоров со звёздами, чтобы показывать радар

DENSITY_CAP = 20.0            # cap для мусорных density (глюк length на десктопе)
REL_MARGIN = 1.05             # относительный отрыв от медианы пула
STREAM_STYLE_MARGIN = 1.3     # доля stream должна превышать aim-долю в N раз
STYLE_MIN_SHARE = 0.30        # и занимать не меньше 30% AP

STARS_SCALE = 10.0            # шкала звёзд для нормализации осей
AR_SCALE = 10.0               # шкала AR (0-10)
CS_SCALE = 10.0               # шкала CS (0-10)
ACC_FLOOR = 0.80              # accuracy 80% -> 0 на оси Acc
ACC_CEIL = 1.00               # accuracy 100% -> 100 на оси Acc

AXIS_LABELS = ["Aim", "Speed", "Streams", "AR", "CS", "Acc"]


@dataclass
class PoolStats:
    """Медианы пула топ-300 скоров игрока — базовая линия классификации."""
    med_ratio: float
    med_density: float


def speed_stars(score: Score) -> float:
    """Скоростные звёзды: osu! считает общую звёздность как sqrt(aim^2 + speed^2)."""
    total = float(score.stars or 0.0)
    aim = float(score.aim or 0.0)
    return math.sqrt(max(0.0, total * total - aim * aim))


def aim_ratio(score: Score) -> float:
    """aim/speed; у карт без speed-звёзд — чисто аимовые (очень высокий ratio)."""
    speed = speed_stars(score)
    if speed <= 0:
        return 99.0
    return float(score.aim or 0.0) / speed


def capped_density(score: Score) -> float:
    return min(float(score.density or 0.0), DENSITY_CAP)


def _is_density_bugged(score: Score) -> bool:
    return float(score.density or 0.0) > DENSITY_CAP


def _valid_scores(scores: list[Score]) -> list[Score]:
    """Скора без звёзд/aim (старые импорты) не участвуют в расчётах."""
    return [
        s for s in scores
        if float(s.stars or 0.0) > 0
        and float(s.aim or 0.0) > 0
        and float(s.ap or 0.0) > 0
    ]


def _pool_stats(scores: list[Score]) -> PoolStats:
    ratios = [aim_ratio(s) for s in scores]
    densities = [capped_density(s) for s in scores]
    return PoolStats(
        med_ratio=statistics.median(ratios) if ratios else 0.0,
        med_density=statistics.median(densities) if densities else 0.0,
    )


def classify_score(score: Score, pool: PoolStats) -> str:
    """aim / stream / balanced — относительно медиан пула игрока.

    Мусорные density (> DENSITY_CAP) сразу в balanced.
    """
    if _is_density_bugged(score):
        return "balanced"
    rel_ratio = (
        aim_ratio(score) / pool.med_ratio if pool.med_ratio > 0 else 1.0
    )
    rel_density = (
        capped_density(score) / pool.med_density if pool.med_density > 0 else 1.0
    )
    if rel_ratio >= REL_MARGIN and rel_density < REL_MARGIN:
        return "aim"
    if rel_density >= REL_MARGIN and rel_ratio < REL_MARGIN:
        return "stream"
    return "balanced"


def score_tag(score: Score, pool: PoolStats) -> str:
    """Мелкая метка для таблиц; '' для balanced, чтобы не перегружать."""
    tag = classify_score(score, pool)
    return tag if tag != "balanced" else ""


def _weighted_avg(pairs: list[tuple[float, float]]) -> float:
    """Среднее по весу; пары (value, weight) с value <= 0 пропускаются."""
    total_w = 0.0
    total_v = 0.0
    for value, weight in pairs:
        if value > 0 and weight > 0:
            total_v += value * weight
            total_w += weight
    return total_v / total_w if total_w > 0 else 0.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_skills(scores: list[Score]) -> dict[str, Any]:
    """Профиль скиллов: топ-N скоров по AP с AP-взвешиванием."""
    top = sorted(
        scores, key=lambda s: float(s.ap or 0.0), reverse=True
    )[:TOP_SCORES_LIMIT]
    valid = _valid_scores(top)

    pool = _pool_stats(valid)

    total_ap = sum(float(s.ap or 0.0) for s in valid)
    weights = {id(s): float(s.ap or 0.0) for s in valid}

    def wavg(getter) -> float:
        return _weighted_avg([(getter(s), weights[id(s)]) for s in valid])

    aim_avg = wavg(lambda s: float(s.aim or 0.0))
    speed_avg = wavg(lambda s: speed_stars(s))
    ar_avg = wavg(lambda s: float(s.eff_ar or 0.0))
    cs_avg = wavg(lambda s: float(s.eff_cs or 0.0))
    acc_avg = wavg(lambda s: float(s.accuracy or 0.0))

    stream_ap = sum(
        float(s.ap or 0.0) for s in valid
        if classify_score(s, pool) == "stream"
    )
    aim_ap = sum(
        float(s.ap or 0.0) for s in valid
        if classify_score(s, pool) == "aim"
    )
    stream_share = stream_ap / total_ap if total_ap > 0 else 0.0
    aim_share = aim_ap / total_ap if total_ap > 0 else 0.0

    axes = {
        "aim": _clamp01(aim_avg / STARS_SCALE) * 100,
        "speed": _clamp01(speed_avg / STARS_SCALE) * 100,
        "streams": stream_share * 100,
        "ar": _clamp01(ar_avg / AR_SCALE) * 100,
        "cs": _clamp01(cs_avg / CS_SCALE) * 100,
        "acc": _clamp01((acc_avg - ACC_FLOOR) / (ACC_CEIL - ACC_FLOOR)) * 100,
    }

    # --- бейджи ---
    if ar_avg >= 9.5:
        ar_badge = "High-AR Player"
    elif ar_avg >= 9.0:
        ar_badge = "Medium AR"
    else:
        ar_badge = "Low AR"

    if cs_avg >= 5.0:
        cs_badge = "Small circles"
    elif cs_avg >= 4.0:
        cs_badge = "Normal circles"
    else:
        cs_badge = "Large circles"

    if stream_share >= STYLE_MIN_SHARE and stream_share >= aim_share * STREAM_STYLE_MARGIN:
        style = "Streams"
    elif aim_share >= STYLE_MIN_SHARE and aim_share >= stream_share * STREAM_STYLE_MARGIN:
        style = "Aim"
    else:
        style = "Balanced"

    return {
        "valid": len(valid) >= MIN_VALID_SCORES,
        "samples": len(valid),
        "axes": {k: round(v, 1) for k, v in axes.items()},
        "points": {
            "aim_points": round(aim_avg, 2),
            "speed_points": round(speed_avg, 2),
            "stream_share": round(stream_share, 4),
            "aim_share": round(aim_share, 4),
        },
        "badges": {
            "ar": ar_badge,
            "cs": cs_badge,
            "style": style,
        },
        "specialisation": [style, cs_badge, ar_badge],
    }


async def build_pool(session: AsyncSession, user_id: int) -> PoolStats:
    """Медианы пула для разметки отдельных скоров в таблицах."""
    result = await session.execute(
        select(Score)
        .where(Score.user_id == user_id)
        .order_by(Score.ap.desc())
        .limit(TOP_SCORES_LIMIT)
    )
    return _pool_stats(_valid_scores(list(result.scalars().all())))


async def build_skills(session: AsyncSession, user: User) -> dict[str, Any]:
    result = await session.execute(
        select(Score)
        .where(Score.user_id == user.id)
        .order_by(Score.ap.desc())
        .limit(TOP_SCORES_LIMIT)
    )
    scores = list(result.scalars().all())
    return compute_skills(scores)
