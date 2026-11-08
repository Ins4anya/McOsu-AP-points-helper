from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import discord

from .ap_calculator import AIM_FOCUSED_RATIO, APBreakdown
from .formatting import format_signed
from .models import OsuScore, BeatmapMeta, PPResult, PlayerProfile
from .mods import (
    DT_BIT,
    EZ_BIT,
    FL_BIT,
    HD_BIT,
    HR_BIT,
    NC_BIT,
    has_mod,
    mods_to_string,
)


def _ar_to_ms(ar: float) -> float:
    return 1800 - 120 * ar if ar <= 5 else 1950 - 150 * ar


def _ms_to_ar(ms: float) -> float:
    return (1800 - ms) / 120 if ms > 1200 else (1950 - ms) / 150


def _od_to_ms(od: float) -> float:
    return 80 - 6 * od


def _ms_to_od(ms: float) -> float:
    return (80 - ms) / 6


def apply_mods_to_stats(ar: float, od: float, cs: float, hp: float, bpm: float, mods: int):
    has_dt = has_mod(mods, DT_BIT) or has_mod(mods, NC_BIT)

    if has_dt:
        bpm *= 1.5
        ar = _ms_to_ar(_ar_to_ms(ar) / 1.5)
        od = _ms_to_od(_od_to_ms(od) / 1.5)

    if has_mod(mods, HR_BIT):
        cs = min(cs * 1.3, 10)
        ar = min(ar * 1.4, 10)
        od = min(od * 1.4, 10)
        hp = min(hp * 1.4, 10)

    if has_mod(mods, EZ_BIT):
        cs = max(cs * 0.5, 0)
        ar = max(ar * 0.5, 0)
        od = max(od * 0.5, 0)
        hp = max(hp * 0.5, 0)

    return ar, od, cs, hp, bpm


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

    mods_str = mods_to_string(score.mods, getattr(score, "speed_mult", None))
    title = f"{meta.artist} - {meta.title} [{meta.difficulty}]"
    if mods_str != "NM":
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
    speed_mult = getattr(score, "speed_mult", None)
    if speed_mult is not None and speed_mult > 0 and getattr(score, "cs", 0) > 0:
        eff_length = int(round(meta.length / speed_mult))
        length_str = format_duration(eff_length)
        mod_ar, mod_od, mod_cs, mod_hp = score.ar, score.od, score.cs, score.hp
        mod_bpm = meta.bpm * speed_mult if meta.bpm > 0 else 0
    else:
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


def _ap_verdict(bd: APBreakdown) -> tuple[str, str]:
    if bd.aim_ratio >= AIM_FOCUSED_RATIO:
        vtype = "Aim-focused map"
    elif bd.aim_ratio <= 0.85:
        vtype = "Speed / stream-focused map"
    elif bd.density >= 6:
        vtype = "Dense map"
    else:
        vtype = "Balanced map"

    sr = bd.star_rating
    if sr < 3:
        diff = "easy"
    elif sr < 5:
        diff = "moderate"
    elif sr < 7:
        diff = "hard"
    else:
        diff = "very hard"

    acc = bd.accuracy * 100
    if acc >= 97:
        acc_word = "excellent accuracy"
    elif acc >= 93:
        acc_word = "good accuracy"
    elif acc >= 88:
        acc_word = "average accuracy"
    else:
        acc_word = "low accuracy"

    bonuses = []
    if bd.aim_bonus > 0:
        bonuses.append(f"+{bd.aim_bonus*100:.0f}% aim")
    if bd.density_bonus > 0:
        bonuses.append(f"+{bd.density_bonus*100:.0f}% density")
    if bd.score_bonus > 0:
        bonuses.append(f"+{bd.score_bonus*100:.0f}% score")
    if bd.rank_bonus > 0:
        bonuses.append(f"+{bd.rank_bonus*100:.0f}% {bd.grade}")
    if bd.mod_mult > 1:
        bonuses.append(f"+{(bd.mod_mult-1)*100:.0f}% mods")

    desc = f"{vtype} · {diff} difficulty · {acc_word}."
    if bonuses:
        desc += " Active bonuses: " + ", ".join(bonuses) + "."
    else:
        desc += " No active bonuses."
    return vtype, desc


def build_ap_breakdown_embed(
    bd: APBreakdown,
    score: OsuScore,
    meta: BeatmapMeta,
) -> discord.Embed:
    title = f"{meta.artist} - {meta.title} [{meta.difficulty}]"
    embed = discord.Embed(
        title=f"AP Breakdown — {title}",
        url=meta.map_url or None,
        color=discord.Color(0x66BBFF),
    )

    objects_txt = str(bd.object_weight) if bd.object_weight > 0 else str(bd.total_hits)
    if bd.object_weight > 0 and bd.num_sliders:
        objects_txt += f"  ({bd.num_circles}+2×{bd.num_sliders})"

    embed.add_field(
        name="Base",
        value=(
            f"Objects: **{objects_txt}**\n"
            f"Star Rating: **{bd.star_rating:.2f}★**\n"
            f"Base AP: **{bd.base_value:.1f}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="Performance",
        value=(
            f"Accuracy: **{bd.accuracy*100:.2f}%**\n"
            f"Combo: **{bd.combo_ratio*100:.1f}%**\n"
            f"Misses: **{bd.count_miss}**\n"
            f"Mods: **{bd.mods_str}**\n"
            f"Grade: **{bd.grade}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="Bonuses",
        value=(
            f"Density: **{bd.density:.1f} obj/s** → **+{bd.density_bonus*100:.1f}%**\n"
            f"Aim ratio: **{bd.aim_ratio:.2f}** → **+{bd.aim_bonus*100:.1f}%**\n"
            f"Score: **{bd.score:,}** → **+{bd.score_bonus*100:.1f}%**\n"
            f"Mods: **×{bd.mod_mult:.2f}**\n"
            f"Rank: **+{bd.rank_bonus*100:.1f}%**"
        ),
        inline=False,
    )

    vtype, verdict_desc = _ap_verdict(bd)
    embed.add_field(name="Total AP", value=f"**{bd.ap:.0f} AP**", inline=False)
    embed.set_footer(text=f"{vtype} • {verdict_desc}")

    if meta.cover_url:
        embed.set_image(url=meta.cover_url)
    embed.timestamp = discord.utils.utcnow()
    return embed


def build_profile_embed(profile: PlayerProfile, display_name: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"Профиль: {display_name}",
        color=discord.Color(0xFFD700),
    )
    embed.add_field(
        name="Статистика",
        value=(
            f"Взвешенный PP: **{profile.weighted_pp:,.0f}**\n"
            f"Сырой PP: **{profile.total_pp:,.0f}**\n"
            f"Игр: **{profile.play_count:,}**\n"
            f"Средняя точность: **{profile.avg_accuracy*100:.2f}%**\n"
            f"Лучшая точность: **{profile.best_accuracy*100:.2f}%**\n"
            f"Макс. комбо: **{profile.max_combo:,}x**"
        ),
        inline=False,
    )
    g = profile.grades
    embed.add_field(
        name="Грейды",
        value=(
            f"XH **{g.xh}**  X **{g.x}**  SH **{g.sh}**  S **{g.s}**\n"
            f"A **{g.a}**  B **{g.b}**  C **{g.c}**  D **{g.d}**"
        ),
        inline=False,
    )
    return embed


def _score_row_title(row) -> str:
    title = row["beatmap_title"] or "Unknown map"
    mods = row["mods"] or "NM"
    return f"{title} {mods}"


def build_top_embed(scores, limit: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"Топ-{limit} скоров по AP",
        color=discord.Color(0xFFD700),
    )
    lines = []
    for i, row in enumerate(scores, start=1):
        played = datetime.fromtimestamp(row["timestamp"]).strftime("%d.%m %H:%M")
        lines.append(
            f"**{i}.** {_score_row_title(row)}\n"
            f"　• **{row['ap']:.0f} AP** • {row['pp']:.2f}pp • "
            f"{row['accuracy']*100:.2f}% • {row['grade']} • x{row['max_combo']} • {played}"
        )
    embed.description = "\n".join(lines) if lines else "Скоров пока нет."
    return embed


def build_best_embed(row) -> discord.Embed:
    embed = discord.Embed(
        title=f"Лучший скор — {_score_row_title(row)}",
        color=discord.Color(0xFFD700),
    )
    played = datetime.fromtimestamp(row["timestamp"]).strftime("%d.%m.%Y %H:%M")
    embed.description = (
        f"**{row['ap']:.0f} AP** • {row['pp']:.2f}pp • "
        f"{row['accuracy']*100:.2f}% • {row['grade']} • x{row['max_combo']}\n"
        f"Играно: {played}"
    )
    embed.timestamp = discord.utils.utcnow()
    return embed


def build_daily_embed(summary, date_label: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"AP за {date_label}",
        color=discord.Color(0x66BBFF),
    )
    embed.description = (
        f"Суммарный AP: **{summary['total_ap']:.0f}**\n"
        f"Скоров: **{summary['count']}**\n"
        f"Лучший AP: **{summary['best_ap']:.0f}**"
    )
    embed.timestamp = discord.utils.utcnow()
    return embed


# --------------------------------------------------------------------------- #
# Ranked (ELO)
# --------------------------------------------------------------------------- #


def _progress_bar(percent: float, width: int = 10) -> str:
    """A text progress bar (▰/▱) for a 0..100 percent value."""
    pct = max(0.0, min(100.0, float(percent or 0.0)))
    filled = int(round(pct / 100.0 * width))
    return "▰" * filled + "▱" * (width - filled)


TIER_COLORS = {
    "Базовый": "#a3a9cf",
    "Бронза": "#cd7f32",
    "Серебро": "#cbd5e1",
    "Золото": "#fbbf24",
    "Платина": "#5eead4",
    "Алмаз": "#7dd3fc",
    "Мастер": "#c084fc",
    "Профессионал": "#f87171",
    "Легенда": "#fbcfe8",
}
FALLBACK_TIER_COLOR = "#a3a9cf"

# Discord-safe text stand-ins for the app/site figures.
# Diamond has no gem silhouette in common fonts; 💎 is the filled stand-in
# and ◇ the empty one (to be verified in a live Discord client).
TIER_SHAPES = {
    "Базовый": ("▲", "△"),
    "Бронза": ("▲", "△"),
    "Серебро": ("■", "□"),
    "Золото": ("■", "□"),
    "Платина": ("◆", "◇"),
    "Алмаз": ("💎", "◇"),
    "Мастер": ("★", "☆"),
    "Профессионал": ("★", "☆"),
    "Легенда": ("●", "○"),
}
FALLBACK_TIER_SHAPE = ("■", "□")


def tier_color(tier: str) -> str:
    return TIER_COLORS.get(str(tier or ""), FALLBACK_TIER_COLOR)


def tier_symbols(tier: str) -> tuple[str, str]:
    return TIER_SHAPES.get(str(tier or ""), FALLBACK_TIER_SHAPE)


def sub_rank_symbols(tier: str, sub) -> str:
    """Filled/empty tier symbols; null sub_rank draws one filled marker."""
    filled_symbol, empty_symbol = tier_symbols(tier)
    if not isinstance(sub, dict):
        return filled_symbol
    try:
        total = max(0, int(sub.get("total") or 0))
        filled = int(sub.get("filled") or 0)
    except (TypeError, ValueError):
        return filled_symbol
    if total <= 0:
        return filled_symbol
    filled = max(0, min(total, filled))
    return filled_symbol * filled + empty_symbol * (total - filled)


def build_ranked_embed(
    stats: dict, active: Optional[dict] = None, display_name: str = ""
) -> discord.Embed:
    """Build a ``!rank`` embed from ``GET /api/ranked/stats`` data."""
    tier = stats.get("tier", "?")
    elo = stats.get("current_elo", 0)
    progress = stats.get("progress") or {}
    percent = progress.get("percent", 0.0)
    next_tier = progress.get("next_tier")

    title = f"Ranked — {tier}" if not display_name else f"{display_name} · {tier}"
    embed = discord.Embed(
        title=title, color=discord.Color(int(tier_color(tier).lstrip("#"), 16))
    )

    elo_line = f"**{elo} ELO**  {_progress_bar(percent)}  {percent:.0f}%"
    symbols = sub_rank_symbols(tier, stats.get("sub_rank"))
    if symbols:
        elo_line = f"{symbols}  " + elo_line
    if next_tier:
        elo_line += f" → {next_tier}"
    embed.add_field(name="Звание", value=elo_line, inline=False)

    window = stats.get("star_window")
    if isinstance(window, dict) and window.get("min") is not None and window.get("max") is not None:
        embed.add_field(
            name="Окно ★",
            value=f"{float(window['min']):.2f}–{float(window['max']):.2f}★",
            inline=True,
        )

    passed = int(stats.get("passed", 0))
    failed = int(stats.get("failed", 0))
    rerolled = int(stats.get("rerolled", 0))
    wins = stats.get("wins")
    losses = stats.get("losses")
    draws = stats.get("draws")
    if wins is None or losses is None or draws is None:
        # Older server without the new counters: fall back to pass/fail.
        wins, losses, draws = passed, failed, 0
    wins, losses, draws = int(wins or 0), int(losses or 0), int(draws or 0)
    win_rate = float(stats.get("win_rate", 0.0))
    embed.add_field(
        name="W / L / D",
        value=(
            f"**{wins}** / **{losses}** / **{draws}**  (роллов: {rerolled})"
        ),
        inline=True,
    )
    embed.add_field(name="Win rate", value=f"**{win_rate * 100:.1f}%**", inline=True)

    best_acc = stats.get("best_accuracy")
    avg_acc = stats.get("avg_accuracy")
    if best_acc is not None or avg_acc is not None:
        parts = []
        if best_acc is not None:
            parts.append(f"лучшая {best_acc * 100:.2f}%")
        if avg_acc is not None:
            parts.append(f"средняя {avg_acc * 100:.2f}%")
        acc_txt = ", ".join(parts)
    else:
        acc_txt = "—"
    embed.add_field(name="Точность", value=acc_txt, inline=True)

    hardest = stats.get("hardest_passed_stars")
    embed.add_field(
        name="Сложнейшая пройденная",
        value=f"★{hardest:.2f}" if hardest is not None else "—",
        inline=True,
    )
    embed.add_field(
        name="Лучший прирост",
        value=f"{format_signed(stats.get('best_elo_gain', 0))} ELO",
        inline=True,
    )

    table = stats.get("acc_reward_table") or []
    if table:
        hint = "  ".join(
            f"{acc * 100:.0f}%→{format_signed(reward)}" for acc, reward in table
        )
        embed.add_field(name="Награда за точность", value=hint, inline=False)

    last = stats.get("last_results") or []
    if last:
        lines = []
        for r in last:
            acc = r.get("accuracy")
            acc_txt = f" {acc * 100:.2f}%" if acc is not None else ""
            lines.append(
                f"{r.get('outcome', '?')} · {r.get('title', '?')} · "
                f"★{r.get('stars', 0):.2f}{acc_txt} · "
                f"{format_signed(r.get('delta', 0))}"
            )
        embed.add_field(name="Последние 5", value="\n".join(lines), inline=False)

    if active:
        value = (
            f"{active.get('title', '?')} · ★{active.get('stars', 0):.2f}"
        )
        condition = str(active.get("condition") or "").strip()
        if condition:
            value += f" · {condition}"
        embed.add_field(name="Активное задание", value=value, inline=False)

    embed.timestamp = discord.utils.utcnow()
    return embed
