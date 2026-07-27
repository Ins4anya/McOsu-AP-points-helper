from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import db_reader
from . import db_reader_osu
from .osu_config import read_player_name_osu
from .embed_builder import calculate_rank
from .models import GradeCounts, OsuScore, PlayerProfile


def read_player_name(cfg_dir: Path | str) -> Optional[str]:
    cfg_file = Path(cfg_dir) / "osu.cfg"
    if not cfg_file.exists():
        return None
    for line in cfg_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("name "):
            return line.split(" ", 1)[1]
    return None


def _accuracy(score: OsuScore) -> float:
    total = score.count300 + score.count100 + score.count50 + score.count_miss
    if total == 0:
        return 0.0
    points = score.count300 * 300 + score.count100 * 100 + score.count50 * 50
    return points / (total * 300)


def calculate_profile(scores_db: Path, cfg_dir: Optional[Path] = None,
                      source: str = "mcsu") -> PlayerProfile:
    if source == "osu":
        all_scores = db_reader_osu.read_all_scores_osu(scores_db)
        name = read_player_name_osu(cfg_dir) if cfg_dir else ""
    else:
        all_scores = db_reader.read_all_scores(scores_db)
        name = read_player_name(cfg_dir) if cfg_dir else None

    profile = PlayerProfile(player_name=name or "")
    profile.play_count = len(all_scores)

    if not all_scores:
        return profile

    total_acc = 0.0
    max_combo = 0
    best_acc = 0.0
    total_pp = 0.0
    max_combo = 0
    grades = GradeCounts()

    for s in all_scores:
        acc = _accuracy(s)
        total_acc += acc
        total_pp += s.pp
        best_acc = max(best_acc, acc)
        max_combo = max(max_combo, s.max_combo)

        total_hits = s.count300 + s.count100 + s.count50 + s.count_miss
        rank = calculate_rank(s.count300, total_hits, s.count50, s.count_miss, s.mods)
        if rank == "rankingXsmall":
            grades.x += 1
        elif rank == "rankingXHsmall":
            grades.xh += 1
        elif rank == "rankingSsmall":
            grades.s += 1
        elif rank == "rankingSHsmall":
            grades.sh += 1
        elif rank == "rankingAsmall":
            grades.a += 1
        elif rank == "rankingBsmall":
            grades.b += 1
        elif rank == "rankingCsmall":
            grades.c += 1
        elif rank == "rankingDsmall":
            grades.d += 1

    profile.total_pp = total_pp
    profile.avg_accuracy = total_acc / len(all_scores)
    profile.best_accuracy = best_acc
    profile.max_combo = max_combo
    profile.grades = grades

    pps = sorted([s.pp for s in all_scores], reverse=True)
    weighted = sum(pp * (0.95 ** i) for i, pp in enumerate(pps))
    profile.weighted_pp = weighted

    return profile
