"""Unit tests for the pure Ranked tab presentation helpers (no NiceGUI)."""
from __future__ import annotations

import pytest

from mcsu_gui.tabs.ranked_view import (
    ACCENT,
    CARD_BG,
    INSET_BG,
    MUTED,
    NEGATIVE,
    PAGE_BG,
    POSITIVE,
    TEXT,
    TIER_COLORS,
    TIER_SHAPES,
    delta_color,
    format_accuracy,
    format_delta,
    format_reward_accuracy,
    format_stars,
    is_me_row,
    outcome_icon,
    place_color,
    pretty_title,
    progress_detail,
    shape_states,
    star_range_text,
    sub_rank_segments,
    tier_color,
    tier_shape,
    tier_shape_svg,
    wld_values,
    window_geometry,
    window_text,
)


def _luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]

    def linear(channel: float) -> float:
        return (
            channel / 12.92
            if channel <= 0.03928
            else ((channel + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = (linear(c) for c in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(foreground: str, background: str) -> float:
    high, low = sorted(
        [_luminance(foreground), _luminance(background)], reverse=True
    )
    return (high + 0.05) / (low + 0.05)


def test_palette_contrast_is_at_least_4_5():
    foregrounds = [TEXT, MUTED, ACCENT, POSITIVE, NEGATIVE, *TIER_COLORS.values()]
    for background in (PAGE_BG, CARD_BG, INSET_BG):
        for foreground in foregrounds:
            assert _contrast(foreground, background) >= 4.5, (
                f"{foreground} on {background}"
            )


# --------------------------------------------------------------------------- #
# Palette
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", list(TIER_COLORS))
def test_tier_color_known(name):
    assert tier_color(name) == TIER_COLORS[name]


def test_tier_color_unknown_falls_back_to_muted():
    assert tier_color(None) == MUTED
    assert tier_color("") == MUTED
    assert tier_color("Неизвестное") == MUTED


def test_place_color():
    assert place_color(1) == TIER_COLORS["Золото"]
    assert place_color(2) == TIER_COLORS["Серебро"]
    assert place_color(3) == TIER_COLORS["Бронза"]
    assert place_color(4) == MUTED
    assert place_color(None) == MUTED


@pytest.mark.parametrize("name,shape", list(TIER_SHAPES.items()))
def test_tier_shape_known(name, shape):
    assert tier_shape(name) == shape


def test_tier_shape_unknown_falls_back_to_square():
    assert tier_shape(None) == "square"
    assert tier_shape("Неизвестное") == "square"


def test_every_tier_has_color_and_shape_in_app_and_bot():
    from mcsu_bot.embed_builder import (
        TIER_COLORS as BOT_COLORS,
        TIER_SHAPES as BOT_SHAPES,
    )
    from server.ranked_rules import DEFAULT_TIERS

    names = [tier.name for tier in DEFAULT_TIERS]
    assert len(names) == len(set(names))
    for name in names:
        assert name in TIER_COLORS, name
        assert name in TIER_SHAPES, name
        assert name in BOT_COLORS, name
        assert name in BOT_SHAPES, name
        assert BOT_COLORS[name] == TIER_COLORS[name], name
    assert set(TIER_COLORS) == set(names)
    assert set(TIER_SHAPES) == set(names)
    assert set(BOT_COLORS) == set(names)
    assert set(BOT_SHAPES) == set(names)


def test_shape_states_marker_for_null_sub_rank():
    # Базовый and Легенда have no sub_rank: one filled figure, no empties.
    assert shape_states("Базовый", None) == [True]
    assert shape_states("Легенда", None) == [True]


def test_shape_states_sub_rank_boundaries():
    assert shape_states("Алмаз", {"filled": 1, "total": 4}) == [
        True, False, False, False,
    ]
    assert shape_states("Алмаз", {"filled": 2, "total": 4}) == [
        True, True, False, False,
    ]
    assert shape_states("Алмаз", {"filled": 3, "total": 4}) == [
        True, True, True, False,
    ]
    assert shape_states("Алмаз", {"filled": 4, "total": 4}) == [
        True, True, True, True,
    ]
    assert shape_states("Алмаз", {"filled": 9, "total": 4}) == [
        True, True, True, True,
    ]


def test_tier_shape_svg_filled_and_empty():
    filled = tier_shape_svg("Алмаз", filled=True, size=20)
    assert 'width="20"' in filled
    assert TIER_COLORS["Алмаз"] in filled
    assert "M4 2h8l3 4-7 8-7-8z" in filled
    assert filled.count("<path") == 1

    empty = tier_shape_svg("Алмаз", filled=False, size=18)
    assert "#1f2347" in empty
    assert "#3a4070" in empty
    assert TIER_COLORS["Алмаз"] not in empty


def test_tier_shape_svg_unknown_tier_is_square():
    svg = tier_shape_svg("Неизвестное")
    assert "<rect" in svg
    assert MUTED in svg


# --------------------------------------------------------------------------- #
# Sub-rank squares
# --------------------------------------------------------------------------- #


def test_sub_rank_segments():
    assert sub_rank_segments({"filled": 2, "total": 4}) == (2, 4)
    assert sub_rank_segments({"filled": 0, "total": 4}) == (0, 4)
    assert sub_rank_segments({"filled": 9, "total": 4}) == (4, 4)
    assert sub_rank_segments({"filled": -3, "total": 4}) == (0, 4)


def test_sub_rank_segments_null_or_broken():
    assert sub_rank_segments(None) == (0, 0)
    assert sub_rank_segments({}) == (0, 0)
    assert sub_rank_segments({"filled": 2}) == (0, 0)
    assert sub_rank_segments({"filled": "x", "total": 4}) == (0, 0)


# --------------------------------------------------------------------------- #
# Window geometry
# --------------------------------------------------------------------------- #


def test_window_geometry_center():
    geo = window_geometry(
        {"min": 6.24, "max": 6.54, "target": 6.39}, 6.0, 7.0
    )
    assert geo == pytest.approx({"left": 24.0, "width": 30.0, "marker": 39.0})


def test_window_geometry_clamps_upper_overhang():
    # Platinum 1499 ELO: the window crosses the 6★ tier border.
    geo = window_geometry(
        {"min": 5.848, "max": 6.148, "target": 5.998}, 5.0, 6.0
    )
    assert geo["left"] == pytest.approx(84.8)
    assert geo["width"] == pytest.approx(15.2)
    assert geo["marker"] == pytest.approx(99.8)


def test_window_geometry_clamps_lower_overhang():
    geo = window_geometry(
        {"min": 4.7, "max": 5.1, "target": 4.9}, 5.0, 6.0
    )
    assert geo["left"] == pytest.approx(0.0)
    assert geo["width"] == pytest.approx(10.0)
    assert geo["marker"] == pytest.approx(0.0)


def test_window_geometry_spanning_both_edges():
    geo = window_geometry(
        {"min": 4.0, "max": 7.0, "target": 5.5}, 5.0, 6.0
    )
    assert geo == pytest.approx({"left": 0.0, "width": 100.0, "marker": 50.0})


def test_window_geometry_base_full_range():
    geo = window_geometry(
        {"min": 0.5, "max": 1.0, "target": 0.75}, 0.5, 1.0
    )
    assert geo == pytest.approx({"left": 0.0, "width": 100.0, "marker": 50.0})


def test_window_geometry_inverted_window_is_swapped():
    geo = window_geometry(
        {"min": 6.6, "max": 6.4, "target": 6.5}, 6.0, 7.0
    )
    assert geo["left"] == pytest.approx(40.0)
    assert geo["width"] == pytest.approx(20.0)


def test_window_geometry_none_for_open_or_invalid_span():
    assert window_geometry({"min": 9.0, "max": 9.3}, 9.0, None) is None
    assert window_geometry({"min": 9.0, "max": 9.3}, 9.0, 9.0) is None
    assert window_geometry({"min": 9.0, "max": 9.3}, None, 10.0) is None
    assert window_geometry(None, 5.0, 6.0) is None
    assert window_geometry({"min": None, "max": 9.3}, 9.0, 10.0) is None


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #


def test_format_delta_uses_real_minus():
    assert format_delta(60) == "+60"
    assert format_delta(0) == "0"
    assert format_delta(-15) == "−15"
    assert format_delta(None) == "0"
    assert format_delta("bad") == "0"


def test_delta_color():
    assert delta_color(10) == POSITIVE
    assert delta_color(-10) == NEGATIVE
    assert delta_color(0) == MUTED


def test_format_accuracy():
    assert format_accuracy(0.9732) == "97.32%"
    assert format_accuracy(None) == "—"
    assert format_accuracy("bad") == "—"


def test_format_reward_accuracy():
    assert format_reward_accuracy(0.70) == "70%"
    assert format_reward_accuracy(0.90) == "90%"
    assert format_reward_accuracy(1.0) == "100%"
    assert format_reward_accuracy(None) == "—"


def test_format_stars():
    assert format_stars(5.0) == "★5.00"
    assert format_stars(None) == "—"
    assert format_stars("bad") == "—"


def test_window_text_and_range_text():
    assert window_text({"min": 6.24, "max": 6.54}) == "6.24–6.54★"
    assert window_text(None) == ""
    assert window_text({"min": 6.2}) == ""
    assert star_range_text({"min": 6.0, "max": 7.0}) == "6.00–7.00★"
    assert star_range_text({"min": 9.0, "max": None}) == "9.00+★"
    assert star_range_text(None) == ""


def test_progress_detail():
    assert (
        progress_detail(
            {"next_tier": "Мастер", "points": 193, "span": 500, "percent": 38.6}
        )
        == "193 / 500 до «Мастер» · 38.6%"
    )
    assert progress_detail({"next_tier": None}) == "максимальное звание"
    assert progress_detail(None) == ""


def test_wld_values_normal_response():
    values = wld_values(
        {"wins": 9, "losses": 1, "draws": 0, "win_rate": 0.9}
    )
    assert values == {
        "wins": 9,
        "losses": 1,
        "draws": 0,
        "games": 10,
        "win_rate": pytest.approx(0.9),
    }


def test_wld_values_falls_back_to_passed_failed():
    # Older response without wins/losses/draws: same fallback as !rank.
    values = wld_values(
        {"passed": 9, "failed": 1, "win_rate": 0.9}
    )
    assert (values["wins"], values["losses"], values["draws"]) == (9, 1, 0)
    assert values["games"] == 10
    assert values["win_rate"] == pytest.approx(0.9)


def test_wld_values_computes_rate_when_absent():
    values = wld_values({"passed": 3, "failed": 1})
    assert values["games"] == 4
    assert values["win_rate"] == pytest.approx(0.75)


def test_wld_values_zero_games():
    values = wld_values({"wins": 0, "losses": 0, "draws": 0, "win_rate": 0.7})
    assert values["games"] == 0
    assert values["win_rate"] == 0.0
    assert wld_values(None)["games"] == 0


def test_pretty_title_replaces_first_dash():
    assert pretty_title("Artist - Song [Insane]") == "Artist — Song [Insane]"
    assert pretty_title("A - B - C") == "A — B - C"
    assert pretty_title(None) == ""


def test_is_me_row_case_insensitive():
    row = {"username": "PlayerOne"}
    assert is_me_row(row, "playerone") is True
    assert is_me_row(row, "  PLAYERONE ") is True
    assert is_me_row(row, "other") is False
    assert is_me_row(row, "") is False
    assert is_me_row(None, "playerone") is False


# --------------------------------------------------------------------------- #
# Outcome icon / tooltip
# --------------------------------------------------------------------------- #


def test_outcome_passed_positive():
    outcome = outcome_icon("passed", 30)
    assert outcome["icon"] == "check"
    assert outcome["color"] == POSITIVE
    assert "Пройдено" in outcome["tooltip"]


def test_outcome_passed_negative():
    outcome = outcome_icon("passed", -15)
    assert outcome["icon"] == "check"
    assert outcome["color"] == NEGATIVE
    assert "снизилось" in outcome["tooltip"]


def test_outcome_passed_zero():
    outcome = outcome_icon("passed", 0)
    assert outcome["icon"] == "remove"
    assert outcome["color"] == MUTED


@pytest.mark.parametrize(
    "status,tooltip",
    [
        ("failed", "Фейл"),
        ("surrendered", "Сдача"),
        ("expired", "Таймаут"),
    ],
)
def test_outcome_failures_are_red_crosses(status, tooltip):
    outcome = outcome_icon(status, -60)
    assert outcome["icon"] == "close"
    assert outcome["color"] == NEGATIVE
    assert outcome["tooltip"] == tooltip


def test_outcome_reroll_and_active():
    reroll = outcome_icon("rerolled", -5)
    assert reroll["icon"] == "refresh"
    assert reroll["color"] == MUTED
    active = outcome_icon("active", 0)
    assert active["icon"] == "schedule"
    assert active["color"] == ACCENT


def test_outcome_unknown_is_neutral():
    outcome = outcome_icon("mystery", 0)
    assert outcome["icon"] == "help_outline"
    assert outcome["color"] == MUTED
    assert outcome["tooltip"] == "mystery"
