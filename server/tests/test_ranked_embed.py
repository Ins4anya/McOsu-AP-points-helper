"""Tests for the pure ranked embed builder (no live Discord needed)."""
from __future__ import annotations

import pytest

from mcsu_bot.embed_builder import (
    TIER_COLORS,
    TIER_SHAPES,
    _progress_bar,
    build_ranked_embed,
    sub_rank_symbols,
    tier_color,
    tier_symbols,
)
from mcsu_bot.formatting import format_signed


def test_format_signed():
    assert format_signed(60) == "+60"
    assert format_signed(0) == "0"
    assert format_signed(-15) == "-15"
    assert format_signed(-60) == "-60"


def test_progress_bar():
    assert _progress_bar(0) == "▱" * 10
    assert _progress_bar(50) == "▰" * 5 + "▱" * 5
    assert _progress_bar(100) == "▰" * 10
    assert _progress_bar(33.3) == "▰" * 3 + "▱" * 7


def test_tier_color_and_symbols():
    assert tier_color("Легенда") == "#fbcfe8"
    assert tier_color("Неизвестное") == "#a3a9cf"
    assert tier_symbols("Платина") == ("◆", "◇")
    assert tier_symbols("Неизвестное") == ("■", "□")


def test_every_tier_has_bot_symbols():
    for name, symbols in TIER_SHAPES.items():
        assert len(symbols) == 2
        assert symbols[0] and symbols[1]
    assert set(TIER_COLORS) == set(TIER_SHAPES)


@pytest.mark.parametrize("filled", [1, 2, 3, 4])
def test_sub_rank_symbol_counts_on_boundaries(filled):
    text = sub_rank_symbols("Алмаз", {"filled": filled, "total": 4})
    assert len(text) == 4
    assert text.count("💎") == filled
    assert text.count("◇") == 4 - filled


def test_sub_rank_symbols():
    assert sub_rank_symbols("Базовый", None) == "▲"
    assert sub_rank_symbols("Легенда", None) == "●"
    assert sub_rank_symbols("Золото", {"filled": 2, "total": 4}) == "■■□□"
    assert sub_rank_symbols("Мастер", {"filled": 4, "total": 4}) == "★★★★"
    assert sub_rank_symbols("Алмаз", {"filled": 1, "total": 4}) == "💎◇◇◇"
    assert sub_rank_symbols("Платина", {"filled": 0, "total": 4}) == "◇◇◇◇"
    assert sub_rank_symbols("Платина", {"filled": 9, "total": 4}) == "◆◆◆◆"


def _stats(**overrides):
    base = {
        "tier": "Золото",
        "current_elo": 500,
        "progress": {"percent": 50.0, "next_tier": "Платина"},
        "passed": 3,
        "failed": 1,
        "rerolled": 0,
        "wins": 3,
        "losses": 1,
        "draws": 0,
        "win_rate": 0.75,
        "best_accuracy": 0.98,
        "avg_accuracy": 0.95,
        "hardest_passed_stars": 5.5,
        "best_elo_gain": 20,
        "acc_reward_table": [[0.70, -60], [0.90, 0], [1.0, 60]],
        "last_results": [
            {
                "outcome": "passed",
                "title": "A - B [C]",
                "stars": 5.0,
                "delta": 16,
                "accuracy": 0.97,
            }
        ],
    }
    base.update(overrides)
    return base


def test_build_ranked_embed_fields():
    embed = build_ranked_embed(_stats(), display_name="User")
    assert "Золото" in embed.title
    assert "User" in embed.title

    names = {f.name for f in embed.fields}
    for expected in (
        "Звание",
        "W / L / D",
        "Win rate",
        "Точность",
        "Сложнейшая пройденная",
        "Награда за точность",
        "Последние 5",
    ):
        assert expected in names

    zvan = next(f for f in embed.fields if f.name == "Звание")
    assert "500 ELO" in zvan.value
    assert "50%" in zvan.value
    assert "Платина" in zvan.value

    wr = next(f for f in embed.fields if f.name == "Win rate")
    assert "75.0%" in wr.value

    reward = next(f for f in embed.fields if f.name == "Награда за точность")
    assert "70%→-60" in reward.value
    assert "90%→0" in reward.value
    assert "100%→+60" in reward.value

    wld = next(f for f in embed.fields if f.name == "W / L / D")
    assert "**3** / **1** / **0**" in wld.value


def test_build_ranked_embed_no_last_no_active():
    stats = _stats(
        passed=0,
        failed=0,
        win_rate=0.0,
        best_accuracy=None,
        avg_accuracy=None,
        hardest_passed_stars=None,
        best_elo_gain=0,
        acc_reward_table=[],
        last_results=[],
    )
    embed = build_ranked_embed(stats)
    names = {f.name for f in embed.fields}
    assert "Последние 5" not in names
    assert "Активное задание" not in names
    assert "Награда за точность" not in names
    acc = next(f for f in embed.fields if f.name == "Точность")
    assert acc.value == "—"


def test_build_ranked_embed_active():
    stats = _stats(
        passed=1,
        failed=0,
        win_rate=1.0,
        best_accuracy=0.95,
        avg_accuracy=0.95,
        hardest_passed_stars=5.0,
        best_elo_gain=10,
        last_results=[],
    )
    active = {
        "title": "X - Y [Z]",
        "stars": 4.5,
        "condition": "оценка C и выше: награда по таблице точности",
    }
    embed = build_ranked_embed(stats, active=active)
    names = {f.name for f in embed.fields}
    assert "Активное задание" in names
    field = next(f for f in embed.fields if f.name == "Активное задание")
    assert "X - Y [Z]" in field.value
    assert "таблице точности" in field.value


def test_build_ranked_embed_negative_reward_has_no_plus_minus():
    stats = _stats(
        acc_reward_table=[[0.70, -60], [0.90, 0]],
        last_results=[
            {
                "outcome": "passed",
                "title": "A - B [C]",
                "stars": 5.0,
                "delta": -15,
                "accuracy": 0.80,
            }
        ],
    )
    embed = build_ranked_embed(stats)
    all_values = "\n".join(f.value for f in embed.fields)
    assert "+-" not in all_values
    assert "70%→-60" in all_values
    assert "90%→0" in all_values
    assert "· -15" in all_values


def test_build_ranked_embed_wld_fallback():
    stats = _stats(passed=4, failed=2)
    for key in ("wins", "losses", "draws"):
        stats.pop(key)
    embed = build_ranked_embed(stats)
    wld = next(f for f in embed.fields if f.name == "W / L / D")
    assert "**4** / **2** / **0**" in wld.value


def test_build_ranked_embed_sub_rank_and_window():
    stats = _stats(
        sub_rank={"filled": 2, "total": 4},
        star_window={"min": 5.35, "max": 5.65, "target": 5.5},
    )
    embed = build_ranked_embed(stats)
    zvan = next(f for f in embed.fields if f.name == "Звание")
    assert "■■□□" in zvan.value
    window = next(f for f in embed.fields if f.name == "Окно ★")
    assert window.value == "5.35–5.65★"
    assert embed.color.value == int(TIER_COLORS["Золото"].lstrip("#"), 16)


def test_build_ranked_embed_null_sub_rank_draws_marker():
    stats = _stats(sub_rank=None, star_window=None)
    embed = build_ranked_embed(stats)
    names = {f.name for f in embed.fields}
    assert "Окно ★" not in names
    zvan = next(f for f in embed.fields if f.name == "Звание")
    # A null sub_rank gets exactly one filled figure, no empty ones.
    assert zvan.value == "■  **500 ELO**  " + _progress_bar(50) + "  50% → Платина"


def test_build_ranked_embed_legend_color_and_marker():
    stats = _stats(tier="Легенда", current_elo=3000, sub_rank=None)
    embed = build_ranked_embed(stats)
    zvan = next(f for f in embed.fields if f.name == "Звание")
    assert zvan.value.startswith("●  ")
    assert embed.color.value == int(TIER_COLORS["Легенда"].lstrip("#"), 16)


def test_build_ranked_embed_active_without_condition():
    stats = _stats(last_results=[])
    embed = build_ranked_embed(
        stats, active={"title": "X - Y [Z]", "stars": 4.5, "condition": ""}
    )
    field = next(f for f in embed.fields if f.name == "Активное задание")
    assert field.value == "X - Y [Z] · ★4.50"
    assert "·  ·" not in field.value
