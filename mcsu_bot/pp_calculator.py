import rosu_pp_py as rpp

from .models import OsuScore, PPResult


def calculate_pp(osu_file_bytes: bytes, score: OsuScore, lazer: bool = False) -> PPResult:
    beatmap = rpp.Beatmap(bytes=osu_file_bytes)

    total_hits = score.count300 + score.count100 + score.count50 + score.count_miss
    accuracy = (300 * score.count300 + 100 * score.count100 + 50 * score.count50) / (300 * total_hits) if total_hits > 0 else 1.0

    perf = rpp.Performance(
        mods=score.mods,
        combo=score.max_combo,
        n300=score.count300,
        n100=score.count100,
        n50=score.count50,
        misses=score.count_miss,
        accuracy=accuracy * 100.0,
        lazer=lazer,
    )
    attrs = perf.calculate(beatmap)
    pp = attrs.pp
    max_combo = attrs.difficulty.max_combo
    star_rating_mods = attrs.difficulty.stars
    stars_aim_mods = attrs.difficulty.aim
    stars_speed_mods = attrs.difficulty.speed

    perf_fc = rpp.Performance(
        mods=score.mods,
        combo=attrs.difficulty.max_combo,
        n300=total_hits,
        n100=0,
        n50=0,
        misses=0,
        accuracy=100.0,
        lazer=lazer,
    )
    attrs_fc = perf_fc.calculate(beatmap)
    pp_fc = attrs_fc.pp

    return PPResult(pp=pp, pp_fc=pp_fc, accuracy=accuracy, max_combo=max_combo,
                    star_rating_mods=star_rating_mods,
                    stars_aim_mods=stars_aim_mods, stars_speed_mods=stars_speed_mods)
