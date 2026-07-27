from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import discord

from .models import OsuScore, BeatmapMeta, PPResult

MODS_BITMAP: dict[int, str] = {
    1 << 0: "NF", 1 << 1: "EZ", 1 << 2: "TD", 1 << 3: "HD",
    1 << 4: "HR", 1 << 5: "SD", 1 << 6: "DT", 1 << 7: "RX",
    1 << 8: "HT", 1 << 9: "NC", 1 << 10: "FL", 1 << 11: "AU",
    1 << 12: "SO", 1 << 13: "AP", 1 << 14: "PF", 1 << 15: "4K",
    1 << 16: "5K", 1 << 17: "6K", 1 << 18: "7K", 1 << 19: "8K",
    1 << 20: "FI", 1 << 21: "RN", 1 << 22: "CN", 1 << 23: "TP",
    1 << 24: "9K", 1 << 25: "KC", 1 << 26: "1K", 1 << 27: "3K",
    1 << 28: "2K", 1 << 29: "V2", 1 << 30: "MR",
}

HD_BIT = 1 << 3
HR_BIT = 1 << 4
DT_BIT = 1 << 6
NC_BIT = 1 << 9
FL_BIT = 1 << 10


def _has_bit(mods: int, bit: int) -> bool:
    return bool(mods & bit)


def _ar_to_ms(ar: float) -> float:
    return 1800 - 120 * ar if ar <= 5 else 1950 - 150 * ar


def _ms_to_ar(ms: float) -> float:
    return (1800 - ms) / 120 if ms > 1200 else (1950 - ms) / 150


def _od_to_ms(od: float) -> float:
    return 80 - 6 * od


def _ms_to_od(ms: float) -> float:
    return (80 - ms) / 6


def apply_mods_to_stats(ar: float, od: float, cs: float, hp: float, bpm: float, mods: int):
    has_dt = _has_bit(mods, DT_BIT) or _has_bit(mods, NC_BIT)

    if has_dt:
        bpm *= 1.5
        ar = _ms_to_ar(_ar_to_ms(ar) / 1.5)
        od = _ms_to_od(_od_to_ms(od) / 1.5)

    if _has_bit(mods, HR_BIT):
        cs = min(cs * 1.3, 10)
        ar = min(ar * 1.4, 10)
        od = min(od * 1.4, 10)
        hp = min(hp * 1.4, 10)

    if _has_bit(mods, 1 << 1):
        cs = max(cs * 0.5, 0)
        ar = max(ar * 0.5, 0)
        od = max(od * 0.5, 0)
        hp = max(hp * 0.5, 0)

    return ar, od, cs, hp, bpm


def mods_to_string(mods: int) -> str:
    if mods == 0:
        return ""
    result: list[str] = []
    for bit, name in MODS_BITMAP.items():
        if mods & bit:
            result.append(name)
    if "NC" in result and "DT" in result:
        result.remove("DT")
    if "PF" in result and "SD" in result:
        result.remove("SD")
    return "+" + "".join(result)


def calculate_rank(count300: int, total_hits: int, count50: int, misses: int, mods: int) -> str:
    has_silver = bool(mods & HD_BIT) or bool(mods & FL_BIT)
    no_misses = misses == 0

    p300 = count300 / total_hits if total_hits > 0 else 0
    p50 = count50 / total_hits if total_hits > 0 else 0

    if p300 >= 1.0:
        return "rankingXHsmall" if has_silver else "rankingXsmall"

    if no_misses and p300 > 0.9 and p50 <= 0.01:
        return "rankingSHsmall" if has_silver else "rankingSsmall"

    if no_misses:
        if p300 > 0.8:
            return "rankingAsmall"
        if p300 > 0.7:
            return "rankingBsmall"
    else:
        if p300 > 0.9:
            return "rankingAsmall"
        if p300 > 0.8:
            return "rankingBsmall"

    if p300 > 0.6:
        return "rankingCsmall"
    return "rankingDsmall"


def format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


class EmojiSet:
    def __init__(self, ranks_txt: Optional[Path] = None):
        self.rank: dict[str, str] = {}
        self.hit300: str = ""
        self.hit100: str = ""
        self.hit50: str = ""
        self.hit0: str = ""
        self.arrow: str = ""
        self.loaded = False

        if ranks_txt and ranks_txt.exists():
            self._parse(ranks_txt.read_text(encoding="utf-8"))

    def _parse(self, text: str):
        pattern = re.compile(r"<:(\w+):(\d+)>")
        for m in pattern.finditer(text):
            name, eid = m.group(1), m.group(2)
            full = f"<:{name}:{eid}>"
            if name.startswith("ranking"):
                self.rank[name] = full
            elif name == "hit300":
                self.hit300 = full
            elif name == "hit100":
                self.hit100 = full
            elif name == "hit50":
                self.hit50 = full
            elif name == "hit0":
                self.hit0 = full
            elif name == "arrowgeneric":
                self.arrow = full
        self.loaded = True

    def rank_emoji(self, rank_name: str) -> str:
        return self.rank.get(rank_name, rank_name)

    def hit_display(self, n300: int, n100: int, n50: int, miss: int) -> str:
        return (
            f"[{self.hit300}{n300}"
            f"/{self.hit100}{n100}"
            f"/{self.hit50}{n50}"
            f"/{self.hit0}{miss}]"
        )


EMOJIS = EmojiSet()


def build_embed(
    score: OsuScore,
    meta: BeatmapMeta,
    pp_result: PPResult,
    *,
    ap: float = 0,
    try_number: int = 1,
    ranks_txt: Optional[Path] = None,
) -> discord.Embed:
    if not EMOJIS.loaded and ranks_txt:
        EMOJIS._parse(ranks_txt.read_text(encoding="utf-8"))

    arrow = EMOJIS.arrow or "▸"
    bullet = "•"

    mods_str = mods_to_string(score.mods)
    title = f"{meta.artist} - {meta.title} [{meta.difficulty}]"
    if mods_str:
        title += f" {mods_str}"
    display_sr = pp_result.star_rating_mods if pp_result.star_rating_mods > 0 else meta.star_rating
    title += f" ★{display_sr:.2f}"

    total_hits = score.count300 + score.count100 + score.count50 + score.count_miss
    rank_name = calculate_rank(score.count300, total_hits, score.count50, score.count_miss, score.mods)
    rank_emoji = EMOJIS.rank_emoji(rank_name)

    acc_pct = pp_result.accuracy * 100
    pp_line = f"{rank_emoji} {arrow} **{ap:.0f} AP**"
    pp_line += f" {arrow} **{pp_result.pp:.2f}pp**"
    if not score.perfect:
        pp_line += f" ({pp_result.pp_fc:.2f}pp for {acc_pct:.2f}% FC)"
    pp_line += f" {arrow} {acc_pct:.2f}%"

    score_line = f"{arrow} {score.score:,}  {arrow}  x{score.max_combo}/{pp_result.max_combo}"

    hits_text = EMOJIS.hit_display(score.count300, score.count100, score.count50, score.count_miss)
    hits_line = f"{arrow} {hits_text}"

    length_str = format_duration(meta.length)
    mod_ar, mod_od, mod_cs, mod_hp, mod_bpm = apply_mods_to_stats(
        meta.ar, meta.od, meta.cs, meta.hp, meta.bpm, score.mods
    )
    stats_line = (
        f"{arrow} {length_str}"
        f" {arrow} {int(mod_bpm)}"
        f" {arrow} AR{mod_ar:.1f} OD{mod_od:.1f} HP{mod_hp:.1f} CS{mod_cs:.1f}"
    )

    color = _rank_color(rank_name)
    embed = discord.Embed(title=title, url=meta.map_url or None, color=color)
    embed.description = f"{pp_line}\n{score_line}\n{hits_line}\n{stats_line}"
    if meta.cover_url:
        embed.set_image(url=meta.cover_url)
    embed.set_footer(text=f"Try #{try_number}  {bullet}  On McOsu local scores  {bullet}  Today at")
    embed.timestamp = discord.utils.utcnow()

    return embed


def _rank_color(rank_name: str) -> discord.Color:
    palette = {
        "rankingXHsmall": discord.Color(0xFFD700),
        "rankingXsmall": discord.Color(0xFFD700),
        "rankingSHsmall": discord.Color(0xFF69B4),
        "rankingSsmall": discord.Color(0xFF69B4),
        "rankingAsmall": discord.Color(0x00FF7F),
        "rankingBsmall": discord.Color(0x1E90FF),
        "rankingCsmall": discord.Color(0xFF4500),
        "rankingDsmall": discord.Color(0xFF0000),
    }
    return palette.get(rank_name, discord.Color.blue())
