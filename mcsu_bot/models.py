from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OsuScore:
    beatmap_md5: str
    score: int
    max_combo: int
    count300: int
    count100: int
    count50: int
    count_miss: int
    count_geki: int
    count_katu: int
    mods: int
    perfect: bool
    timestamp: int
    player_name: str = ""
    pp: float = 0.0
    max_possible_combo: int = 0
    num_slider_breaks: int = 0
    num_hit_objects: int = 0
    stars_aim: float = 0.0
    stars_speed: float = 0.0


@dataclass
class BeatmapMeta:
    beatmap_id: Optional[int] = None
    beatmapset_id: Optional[int] = None
    artist: str = ""
    title: str = ""
    difficulty: str = ""
    creator: str = ""
    bpm: float = 0.0
    cs: float = 0.0
    ar: float = 0.0
    od: float = 0.0
    hp: float = 0.0
    star_rating: float = 0.0
    length: int = 0  # seconds
    num_circles: int = 0
    num_sliders: int = 0
    num_spinners: int = 0
    object_weight: int = 0
    bg_url: str = ""
    cover_url: str = ""
    map_url: str = ""
    status: str = ""


@dataclass
class PPResult:
    pp: float = 0.0
    pp_fc: float = 0.0
    accuracy: float = 0.0
    max_combo: int = 0
    star_rating_mods: float = 0.0
    stars_aim_mods: float = 0.0
    stars_speed_mods: float = 0.0


@dataclass
class GradeCounts:
    x: int = 0
    xh: int = 0
    s: int = 0
    sh: int = 0
    a: int = 0
    b: int = 0
    c: int = 0
    d: int = 0


@dataclass
class PlayerProfile:
    player_name: str = ""
    play_count: int = 0
    total_pp: float = 0.0
    weighted_pp: float = 0.0
    avg_accuracy: float = 0.0
    best_accuracy: float = 0.0
    max_combo: int = 0
    grades: GradeCounts = field(default_factory=GradeCounts)
