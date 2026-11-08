from dataclasses import dataclass, field
from typing import Optional

from .mods import DT_BIT, FL_BIT, HD_BIT, HT_BIT, NC_BIT, has_mod, mods_to_string
from .models import OsuScore, BeatmapMeta, PPResult

SCALE = 0.1

DENSITY_THRESHOLD = 2.0
DENSITY_STEP = 0.04
DENSITY_CAP = 0.15

AIM_RATIO_THRESHOLD = 1.0
AIM_STEP = 0.50
AIM_CAP = 0.30

AIM_FOCUSED_RATIO = 1.15
SCORE_BONUS_PER_MILLION = 1_000_000
SCORE_BONUS_STEP = 0.01

MISS_PENALTY_FACTOR = 0.3

MOD_BONUSES = {
    1 << 0: 0,
    1 << 1: 0.05,
    1 << 3: 0.08,
    1 << 4: 0.12,
    1 << 6: 0.15,
    1 << 9: 0.15,
    1 << 10: 0.06,
}

RANK_BONUSES = {
    "X": 0.20, "XH": 0.20,
    "S": 0.10, "SH": 0.10,
}


@dataclass
class APBreakdown:
    total_hits: int
    star_rating: float
    base_value: float
    num_circles: int
    num_sliders: int
    num_spinners: int
    object_weight: int
    accuracy: float
    acc_mult: float
    combo_ratio: float
    miss_penalty: float
    count_miss: int
    density: float
    density_bonus: float
    stars_aim: float
    stars_speed: float
    aim_ratio: float
    aim_bonus: float
    score: int
    score_bonus: float
    mod_mult: float
    mods_str: str
    grade: str
    rank_bonus: float
    rate: float
    ap: float


def _mod_multiplier(mods: int, speed_mult: Optional[float] = None) -> float:
    mult = 1.0
    rate = speed_mult if speed_mult is not None and speed_mult > 0 else 1.0
    for bit, bonus in MOD_BONUSES.items():
        if bit in (DT_BIT, HT_BIT, NC_BIT):
            continue
        if has_mod(mods, bit):
            mult += bonus
    if rate != 1.0:
        bonus = 0.15 * (rate - 1.0) / 0.5
        if bonus > 0:
            mult += bonus
    elif speed_mult is None:
        if has_mod(mods, NC_BIT) or has_mod(mods, DT_BIT):
            mult += MOD_BONUSES.get(DT_BIT, 0.15)
    return mult


def _calculate_grade(count300: int, total_hits: int, count50: int, misses: int, mods: int) -> str:
    has_silver = has_mod(mods, HD_BIT) or has_mod(mods, FL_BIT)
    no_misses = misses == 0

    p300 = count300 / total_hits if total_hits > 0 else 0
    p50 = count50 / total_hits if total_hits > 0 else 0

    if p300 >= 1.0:
        return "XH" if has_silver else "X"

    if no_misses and p300 > 0.9 and p50 <= 0.01:
        return "SH" if has_silver else "S"

    if no_misses:
        if p300 > 0.8:
            return "A"
        if p300 > 0.7:
            return "B"
    else:
        if p300 > 0.9:
            return "A"
        if p300 > 0.8:
            return "B"

    if p300 > 0.6:
        return "C"
    return "D"


def calculate_ap(score: OsuScore, meta: BeatmapMeta, accuracy: float,
                 mods_star_rating: float = 0, pp_result: PPResult = None) -> float:
    return explain_ap(score, meta, accuracy, mods_star_rating, pp_result).ap


def explain_ap(score: OsuScore, meta: BeatmapMeta, accuracy: float,
               mods_star_rating: float = 0, pp_result: PPResult = None) -> APBreakdown:
    total_hits = score.count300 + score.count100 + score.count50 + score.count_miss
    effective_sr = mods_star_rating if mods_star_rating > 0 else meta.star_rating
    if total_hits == 0 or effective_sr == 0:
        return APBreakdown(
            total_hits=0, star_rating=0, base_value=0,
            num_circles=0, num_sliders=0, num_spinners=0, object_weight=0,
            accuracy=0, acc_mult=0, combo_ratio=0,
            miss_penalty=0, count_miss=0, density=0, density_bonus=0,
            stars_aim=0, stars_speed=0, aim_ratio=0, aim_bonus=0,
            score=0, score_bonus=0, mod_mult=0, mods_str="", grade="D",
            rank_bonus=0, rate=0, ap=0,
        )

    num_circles = meta.num_circles
    num_sliders = meta.num_sliders
    num_spinners = meta.num_spinners
    object_weight = meta.object_weight
    base_objects = object_weight if object_weight > 0 else total_hits

    rate = score.speed_mult if score.speed_mult is not None and score.speed_mult > 0 else 1.0
    effective_length = meta.length / rate if meta.length > 0 and rate > 0 else meta.length

    base_value = base_objects * effective_sr * SCALE
    acc_mult = accuracy ** 1.2
    raw_combo_ratio = (
        score.max_combo / score.max_possible_combo
        if score.max_possible_combo > 0
        else 1.0
    )
    combo_ratio = raw_combo_ratio ** 0.5
    miss_penalty = max(0.0, 1.0 - MISS_PENALTY_FACTOR * score.count_miss / total_hits)
    density = total_hits / effective_length if effective_length > 0 else 0.0
    density_bonus = min(max(0.0, (density - DENSITY_THRESHOLD) * DENSITY_STEP), DENSITY_CAP)

    stars_aim = pp_result.stars_aim_mods if (pp_result and pp_result.stars_aim_mods) else score.stars_aim
    stars_speed = pp_result.stars_speed_mods if (pp_result and pp_result.stars_speed_mods) else score.stars_speed
    aim_ratio = stars_aim / max(stars_speed, 0.01)
    aim_bonus = min(max(0.0, (aim_ratio - AIM_RATIO_THRESHOLD) * AIM_STEP), AIM_CAP)

    score_bonus = 0.0
    if aim_ratio >= AIM_FOCUSED_RATIO and score.score > 0:
        score_bonus = (score.score / SCORE_BONUS_PER_MILLION) * SCORE_BONUS_STEP

    mod_mult = _mod_multiplier(score.mods, score.speed_mult)
    mods_str = mods_to_string(score.mods, score.speed_mult)
    grade = _calculate_grade(score.count300, total_hits, score.count50, score.count_miss, score.mods)
    rank_bonus = RANK_BONUSES.get(grade, 0.0)

    ap = max(0.0, base_value * acc_mult * combo_ratio * miss_penalty
             * mod_mult * (1.0 + density_bonus) * (1.0 + aim_bonus)
             * (1.0 + score_bonus) * (1.0 + rank_bonus))

    return APBreakdown(
        total_hits=total_hits,
        star_rating=effective_sr,
        base_value=base_value,
        num_circles=num_circles,
        num_sliders=num_sliders,
        num_spinners=num_spinners,
        object_weight=object_weight,
        accuracy=accuracy,
        acc_mult=acc_mult,
        combo_ratio=combo_ratio,
        miss_penalty=miss_penalty,
        count_miss=score.count_miss,
        density=density,
        density_bonus=density_bonus,
        stars_aim=stars_aim,
        stars_speed=stars_speed,
        aim_ratio=aim_ratio,
        aim_bonus=aim_bonus,
        score=score.score,
        score_bonus=score_bonus,
        mod_mult=mod_mult,
        mods_str=mods_str,
        grade=grade,
        rank_bonus=rank_bonus,
        rate=rate,
        ap=ap,
    )
