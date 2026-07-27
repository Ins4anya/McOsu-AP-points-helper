from dataclasses import dataclass, field
from typing import Optional

from .models import OsuScore, BeatmapMeta, PPResult

SCALE = 0.1

DENSITY_THRESHOLD = 2.0
DENSITY_STEP = 0.04
DENSITY_CAP = 0.30

AIM_RATIO_THRESHOLD = 1.0
AIM_STEP = 0.08
AIM_CAP = 0.15

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
    accuracy: float
    acc_mult: float
    combo_ratio: float
    miss_penalty: float
    density: float
    density_bonus: float
    stars_aim: float
    stars_speed: float
    aim_ratio: float
    aim_bonus: float
    mod_mult: float
    mods_str: str
    grade: str
    rank_bonus: float
    ap: float


def _has_bit(mods: int, bit: int) -> bool:
    return bool(mods & bit)


def _mod_multiplier(mods: int) -> float:
    mult = 1.0
    for bit, bonus in MOD_BONUSES.items():
        if _has_bit(mods, bit):
            mult += bonus
    if _has_bit(mods, 1 << 9):
        mult -= MOD_BONUSES.get(1 << 6, 0)
    return mult


def _mods_to_string(mods: int) -> str:
    if mods == 0:
        return "NM"
    MODS_BITMAP = {
        1 << 0: "NF", 1 << 1: "EZ", 1 << 2: "TD", 1 << 3: "HD",
        1 << 4: "HR", 1 << 5: "SD", 1 << 6: "DT", 1 << 7: "RX",
        1 << 8: "HT", 1 << 9: "NC", 1 << 10: "FL", 1 << 11: "AU",
        1 << 12: "SO", 1 << 13: "AP", 1 << 14: "PF", 1 << 15: "4K",
        1 << 16: "5K", 1 << 17: "6K", 1 << 18: "7K", 1 << 19: "8K",
        1 << 20: "FI", 1 << 21: "RN", 1 << 22: "CN", 1 << 23: "TP",
        1 << 24: "9K", 1 << 25: "KC", 1 << 26: "1K", 1 << 27: "3K",
        1 << 28: "2K", 1 << 29: "V2", 1 << 30: "MR",
    }
    result = []
    for bit, name in MODS_BITMAP.items():
        if mods & bit:
            result.append(name)
    if "NC" in result and "DT" in result:
        result.remove("DT")
    if "PF" in result and "SD" in result:
        result.remove("SD")
    return "+" + "".join(result)


def _calculate_grade(count300: int, total_hits: int, count50: int, misses: int, mods: int) -> str:
    has_silver = _has_bit(mods, 1 << 3) or _has_bit(mods, 1 << 10)
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
            accuracy=0, acc_mult=0, combo_ratio=0,
            miss_penalty=0, density=0, density_bonus=0,
            stars_aim=0, stars_speed=0, aim_ratio=0, aim_bonus=0,
            mod_mult=0, mods_str="", grade="D", rank_bonus=0, ap=0,
        )

    base_value = total_hits * effective_sr * SCALE
    acc_mult = accuracy ** 1.2
    raw_combo_ratio = (
        score.max_combo / score.max_possible_combo
        if score.max_possible_combo > 0
        else 1.0
    )
    combo_ratio = raw_combo_ratio ** 0.5
    miss_penalty = max(0.0, 1.0 - MISS_PENALTY_FACTOR * score.count_miss / total_hits)
    density = total_hits / meta.length if meta.length > 0 else 0.0
    density_bonus = min(max(0.0, (density - DENSITY_THRESHOLD) * DENSITY_STEP), DENSITY_CAP)

    stars_aim = pp_result.stars_aim_mods if (pp_result and pp_result.stars_aim_mods) else score.stars_aim
    stars_speed = pp_result.stars_speed_mods if (pp_result and pp_result.stars_speed_mods) else score.stars_speed
    aim_ratio = stars_aim / max(stars_speed, 0.01)
    aim_bonus = min(max(0.0, (aim_ratio - AIM_RATIO_THRESHOLD) * AIM_STEP), AIM_CAP)

    mod_mult = _mod_multiplier(score.mods)
    mods_str = _mods_to_string(score.mods)
    grade = _calculate_grade(score.count300, total_hits, score.count50, score.count_miss, score.mods)
    rank_bonus = RANK_BONUSES.get(grade, 0.0)

    ap = max(0.0, base_value * acc_mult * combo_ratio * miss_penalty
             * mod_mult * (1.0 + density_bonus) * (1.0 + aim_bonus) * (1.0 + rank_bonus))

    return APBreakdown(
        total_hits=total_hits,
        star_rating=effective_sr,
        base_value=base_value,
        accuracy=accuracy,
        acc_mult=acc_mult,
        combo_ratio=combo_ratio,
        miss_penalty=miss_penalty,
        density=density,
        density_bonus=density_bonus,
        stars_aim=stars_aim,
        stars_speed=stars_speed,
        aim_ratio=aim_ratio,
        aim_bonus=aim_bonus,
        mod_mult=mod_mult,
        mods_str=mods_str,
        grade=grade,
        rank_bonus=rank_bonus,
        ap=ap,
    )
