"""Unit tests for server.ranked_rules (pure logic, no DB/IO)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from server.ranked_rules import (
    DEFAULT_SETTINGS,
    DEFAULT_TIERS,
    FORBIDDEN_MODS,
    PENALTY_MODS,
    RankedSettings,
    SUB_RANK_SEGMENTS,
    accuracy_reward,
    apply_delta,
    as_utc,
    evaluate,
    has_ez,
    has_forbidden_mods,
    is_within_window,
    normalize_grade,
    parse_mods,
    penalty_mod_count,
    progress_to_next,
    star_ladder,
    star_range,
    star_window,
    sub_rank,
    tier_for,
    timeout_seconds,
)


# --------------------------------------------------------------------------- #
# Tiers / ranks
# --------------------------------------------------------------------------- #

TIER_CASES = [
    (99, "Базовый"),
    (100, "Базовый"),
    (101, "Бронза"),
    (199, "Бронза"),
    (200, "Серебро"),
    (499, "Серебро"),
    (500, "Золото"),
    (999, "Золото"),
    (1000, "Платина"),
    (1499, "Платина"),
    (1500, "Алмаз"),
    (1999, "Алмаз"),
    (2000, "Мастер"),
    (2499, "Мастер"),
    (2500, "Профессионал"),
    (2999, "Профессионал"),
    (3000, "Легенда"),
    (10000, "Легенда"),
]


@pytest.mark.parametrize("elo,expected", TIER_CASES)
def test_tier_boundaries(elo, expected):
    assert tier_for(elo).name == expected


def test_tier_names_are_unique_and_bounds_have_no_holes():
    names = [tier.name for tier in DEFAULT_TIERS]
    assert len(names) == len(set(names))
    assert DEFAULT_TIERS[0].min_elo == 100
    for current, following in zip(DEFAULT_TIERS, DEFAULT_TIERS[1:]):
        assert current.min_elo < following.min_elo
        assert current.max_stars == following.min_stars
    assert DEFAULT_TIERS[-1].name == "Легенда"
    assert DEFAULT_TIERS[-1].min_elo == 3000
    assert DEFAULT_TIERS[-1].max_stars is None


STAR_CASES = [
    (100, (0.5, 1.0)),
    (101, (1.0, 2.0)),
    (200, (2.0, 4.0)),
    (500, (4.0, 5.0)),
    (1000, (5.0, 6.0)),
    (1500, (6.0, 7.0)),
    (2000, (7.0, 8.0)),
    (2500, (8.0, 9.0)),
    (3000, (9.0, None)),
]


@pytest.mark.parametrize("elo,expected", STAR_CASES)
def test_star_range(elo, expected):
    assert star_range(elo) == expected


def test_tier_star_ranges_are_contiguous():
    """The tier table's outer bounds still tile (public tier table only).

    The *actual* window is now continuous and may cross tier borders; this
    test only guards the extreme points shown in the rules table.
    """
    tiers = DEFAULT_TIERS
    for i in range(len(tiers) - 1):
        cur, nxt = tiers[i], tiers[i + 1]
        assert cur.max_stars is not None, f"{cur.name} должна иметь верхнюю границу"
        assert cur.max_stars == nxt.min_stars, (
            f"дыра/перекрытие между {cur.name} ({cur.max_stars}) и {nxt.name} "
            f"({nxt.min_stars})"
        )
        assert nxt.min_stars >= cur.min_stars
    assert tiers[-1].max_stars is None


def test_star_range_two_star_boundary():
    # The 2.0★ boundary: Бронза is [1.0, 2.0) (excludes 2.0), Серебро is
    # [2.0, 4.0) (includes 2.0).
    assert star_range(199) == (1.0, 2.0)   # Бронза
    assert star_range(200) == (2.0, 4.0)   # Серебро


# --------------------------------------------------------------------------- #
# Continuous star window
# --------------------------------------------------------------------------- #


def _approx_window(elo, lo, hi, target=None):
    got_lo, got_hi, got_target = star_window(elo)
    assert got_lo == pytest.approx(lo, abs=1e-9)
    assert got_hi == pytest.approx(hi, abs=1e-9)
    if target is not None:
        assert got_target == pytest.approx(target, abs=1e-9)


def test_star_window_platinum():
    # Платина: 1000..1499 ELO, 5..6★, h = 0.15.
    _approx_window(1000, 4.85, 5.15, 5.0)
    _approx_window(1250, 5.35, 5.65, 5.5)
    _approx_window(1499, 5.848, 6.148, 5.998)


def test_star_window_silver_uses_its_own_width():
    # Серебро spans 300 ELO (200..499) and 2..4★.
    _approx_window(200, 1.85, 2.15, 2.0)
    _approx_window(350, 2.85, 3.15, 3.0)
    _approx_window(499, 3.843333333, 4.143333333, 3.993333333)


def test_star_window_bronze_uses_its_own_width():
    # Бронза spans 99 ELO (101..199) and 1..2★.
    _approx_window(101, 0.85, 1.15, 1.0)
    _approx_window(150, 1.344949495, 1.644949495, 1.494949495)
    _approx_window(199, 1.83989899, 2.13989899, 1.98989899)


def test_star_window_base_is_fixed():
    lo, hi, target = star_window(100)
    assert (lo, hi, target) == pytest.approx((0.5, 1.0, 0.75))
    # Below the floor the first tier still applies (defensive).
    assert star_window(99) == pytest.approx((0.5, 1.0, 0.75))


def test_star_window_legend():
    # Легенда: 9 + (elo - 3000) / 500, capped at 10★.
    _approx_window(3000, 8.85, 9.15, 9.0)
    _approx_window(3250, 9.35, 9.65, 9.5)
    _approx_window(3500, 9.85, 10.15, 10.0)
    # After the cap the window does not move.
    _approx_window(4000, 9.85, 10.15, 10.0)
    _approx_window(5000, 9.85, 10.15, 10.0)
    _approx_window(10000, 9.85, 10.15, 10.0)


def test_star_window_professional_slope_matches_master_at_border():
    """The +1★/500 ELO slope continues across 2999 -> 3000 (Легенда)."""
    inside = star_window(2999)[2] - star_window(2998)[2]
    border = star_window(3000)[2] - star_window(2999)[2]
    assert inside == pytest.approx(1 / 500, abs=1e-9)
    assert border == pytest.approx(inside, abs=1e-9)


def test_star_window_target_is_monotone():
    prev = None
    for elo in range(90, 5001):
        target = star_window(elo)[2]
        if prev is not None:
            assert target >= prev - 1e-12, f"target dropped at ELO {elo}"
        prev = target


@pytest.mark.parametrize(
    "left,right",
    [(99, 100), (100, 101), (199, 200), (499, 500), (999, 1000), (1499, 1500), (2999, 3000)],
)
def test_star_window_is_continuous_at_tier_borders(left, right):
    """No gap/regression at a tier border: the next window overlaps the old one."""
    lo1, hi1, t1 = star_window(left)
    lo2, hi2, t2 = star_window(right)
    assert t2 >= t1 - 1e-12
    assert lo2 >= lo1 - 1e-12
    assert lo2 <= hi1 + 1e-12  # windows overlap (no hole between them)


def test_star_ladder_widens_in_order():
    # Золото at ELO 500: target 4.0.
    ladder = star_ladder(500)
    assert len(ladder) == 4
    expected = [(3.85, 4.15), (3.7, 4.3), (3.4, 4.6), (4.0, 5.0)]
    for (lo, hi), (elo_exp, hi_exp) in zip(ladder, expected):
        assert lo == pytest.approx(elo_exp)
        assert hi == pytest.approx(hi_exp)


def test_star_ladder_base_has_no_ladder():
    assert star_ladder(100) == [(0.5, 1.0)]


def test_star_ladder_legend_ends_with_open_range():
    ladder = star_ladder(4000)
    for got, expected in zip(
        ladder,
        [(9.85, 10.15), (9.7, 10.3), (9.4, 10.6)],
    ):
        assert got == pytest.approx(expected)
    assert ladder[3] == (9.0, None)


def test_star_ladder_has_no_duplicate_ranges():
    # A very wide h makes 4h wider than the tier; the whole-tier step still
    # has a distinct upper bound, so all four entries remain distinct.
    s = RankedSettings(star_window=1.0)
    ladder = star_ladder(500, s)
    assert len(ladder) == len(set(ladder))


# --------------------------------------------------------------------------- #
# Sub-rank indicator
# --------------------------------------------------------------------------- #


def test_sub_rank_none_for_base_and_legend():
    assert sub_rank(100) is None
    assert sub_rank(99) is None
    assert sub_rank(3000) is None
    assert sub_rank(10000) is None


@pytest.mark.parametrize("elo", [101, 200, 500, 1000, 1500, 2000, 2500])
def test_sub_rank_present_for_middle_tiers(elo):
    sub = sub_rank(elo)
    assert sub is not None
    assert sub["total"] == SUB_RANK_SEGMENTS
    assert 1 <= sub["filled"] <= SUB_RANK_SEGMENTS


@pytest.mark.parametrize(
    "elo,filled",
    [
        (200, 1),   # Серебро, 0%
        (275, 2),   # 25%
        (350, 3),   # 50%
        (425, 4),   # 75%
        (499, 4),   # ~100%, capped at 4
        (500, 1),   # Золото, 0%
        (625, 2),
        (750, 3),
        (875, 4),
        (1000, 1),  # Платина, 0%
        (1125, 2),
        (1250, 3),
        (1375, 4),
        (1499, 4),
    ],
)
def test_sub_rank_filled_on_segment_boundaries(elo, filled):
    sub = sub_rank(elo)
    assert sub == {"filled": filled, "total": SUB_RANK_SEGMENTS}


def test_sub_rank_never_empty_on_entry_and_capped_at_end():
    # Any tier entry gives at least one filled segment.
    for elo in (101, 200, 500, 1000, 1500, 2000, 2500):
        assert sub_rank(elo)["filled"] == 1
    # The last integer ELO before the next tier never exceeds the total.
    for elo in (199, 499, 999, 1499, 1999, 2499, 2999):
        assert sub_rank(elo)["filled"] <= SUB_RANK_SEGMENTS


def test_progress_to_next():
    p = progress_to_next(100)
    assert p["tier"] == "Базовый"
    assert p["next_tier"] == "Бронза"
    assert p["next_min_elo"] == 101
    assert p["percent"] == 0.0

    p = progress_to_next(150)  # 50 points into Бронза (101..199)
    assert p["tier"] == "Бронза"
    assert p["points"] == 49
    assert p["next_min_elo"] == 200

    p = progress_to_next(3000)
    assert p["tier"] == "Легенда"
    assert p["next_tier"] is None
    assert p["percent"] == 100.0


# --------------------------------------------------------------------------- #
# ELO floor / start / delta
# --------------------------------------------------------------------------- #

def test_start_elo():
    assert RankedSettings.default().start_elo == 500


def test_apply_delta_floor():
    assert apply_delta(100, -60) == 100
    assert apply_delta(101, -60) == 100
    assert apply_delta(100, -5) == 100  # reroll penalty
    assert apply_delta(100, 60) == 160
    assert apply_delta(90, -60) == 100  # below floor clamps up
    assert apply_delta(105, -3) == 102
    assert apply_delta(500, -60) == 440


# --------------------------------------------------------------------------- #
# Grade normalization
# --------------------------------------------------------------------------- #

def test_normalize_grade():
    assert normalize_grade("X") == "X"
    assert normalize_grade("XH") == "XH"
    assert normalize_grade("S") == "S"
    assert normalize_grade("SH") == "SH"
    assert normalize_grade("A") == "A"
    assert normalize_grade("B") == "B"
    assert normalize_grade("C") == "C"
    assert normalize_grade("D") == "D"
    assert normalize_grade("F") == "F"
    # stable-style aliases
    assert normalize_grade("SS") == "X"
    assert normalize_grade("SSH") == "XH"
    # lowercase / whitespace / missing
    assert normalize_grade("xh") == "XH"
    assert normalize_grade("  s ") == "S"
    assert normalize_grade("") == "D"
    assert normalize_grade(None) == "D"


def test_evaluate_uses_normalized_grade():
    # SS/SSH (stable-style) are treated as passes; the table still decides.
    verdict, delta = evaluate("SS", 0.95, "NM", 5.0)
    assert verdict == "pass"
    assert delta == 30
    assert evaluate("SSH", 0.90, "NM", 5.0) == ("pass", 0)
    assert evaluate("SS", 0.99, "NM", 5.0)[0] == "pass"


# --------------------------------------------------------------------------- #
# Grade: D = fail, C = pass
# --------------------------------------------------------------------------- #

def test_grade_d_is_fail():
    verdict, delta = evaluate("D", 0.99, "NM", 5.0)
    assert verdict == "fail"
    assert delta == -60


def test_grade_below_d_is_fail():
    verdict, delta = evaluate("F", 0.99, "NM", 5.0)
    assert verdict == "fail"
    assert delta == -60


def test_grade_c_is_pass():
    verdict, delta = evaluate("C", 0.95, "NM", 5.0)
    assert verdict == "pass"
    assert delta == 30


def test_grade_c_below_90_is_negative():
    verdict, delta = evaluate("C", 0.80, "NM", 5.0)
    assert verdict == "pass"
    assert delta == -30


def test_fail_ignores_mods():
    for mods in ("+NF", "+HT", "+NFHT", "+EZ", "+EZNF"):
        verdict, delta = evaluate("D", 1.0, mods, 6.0)
        assert verdict == "fail"
        assert delta == -60


# --------------------------------------------------------------------------- #
# NF / HT penalties
# --------------------------------------------------------------------------- #

def test_nf_ht_penalties():
    base = evaluate("S", 0.95, "NM", 5.0)[1]
    assert base == 30
    assert evaluate("S", 0.95, "+NF", 5.0)[1] == base - 10
    assert evaluate("S", 0.95, "+HT", 5.0)[1] == base - 10
    assert evaluate("S", 0.95, "+NFHT", 5.0)[1] == base - 20


def test_penalty_mod_count():
    assert penalty_mod_count("+NF") == 1
    assert penalty_mod_count("+HT") == 1
    assert penalty_mod_count("+NFHT") == 2
    assert penalty_mod_count("NM") == 0


# --------------------------------------------------------------------------- #
# EZ
# --------------------------------------------------------------------------- #

def test_ez_has_no_penalty():
    # Same delta as no mods at a low star rating.
    assert evaluate("S", 0.95, "+EZ", 4.0)[1] == evaluate("S", 0.95, "NM", 4.0)[1] == 30


@pytest.mark.parametrize(
    "stars,expected",
    [
        (4.99, 30),  # below low threshold -> no bonus
        (5.0, 40),   # >= 5.0 -> +10
        (5.99, 40),  # still in [5.0, 6.0)
        (6.0, 50),   # >= 6.0 -> +20
    ],
)
def test_ez_bonus_thresholds(stars, expected):
    verdict, delta = evaluate("S", 0.95, "+EZ", stars)
    assert verdict == "pass"
    assert delta == expected


def test_ez_plus_nf():
    verdict, delta = evaluate("S", 0.95, "+EZNF", 6.0)
    assert verdict == "pass"
    assert delta == 40  # 30 base + 20 EZ - 10 NF


# --------------------------------------------------------------------------- #
# Accuracy reward table
# --------------------------------------------------------------------------- #

def test_accuracy_reward_points():
    s = DEFAULT_SETTINGS
    assert accuracy_reward(0.70, s) == -60
    assert accuracy_reward(0.90, s) == 0
    assert accuracy_reward(1.0, s) == 60


@pytest.mark.parametrize(
    "accuracy,expected",
    [
        (0.91, 6),
        (0.93, 18),
        (0.95, 30),
        (0.97, 42),
        (1.0, 60),
        (0.89, -3),
        (0.85, -15),
        (0.80, -30),
        (0.75, -45),
        (0.70, -60),
    ],
)
def test_accuracy_reward_examples(accuracy, expected):
    assert accuracy_reward(accuracy, DEFAULT_SETTINGS) == expected


def test_accuracy_reward_rounding():
    assert accuracy_reward(0.9091, DEFAULT_SETTINGS) == 5
    assert accuracy_reward(0.9092, DEFAULT_SETTINGS) == 6


def test_accuracy_reward_below_first_and_above_last():
    s = DEFAULT_SETTINGS
    assert accuracy_reward(0.60, s) == -60  # below first point -> minimum
    assert accuracy_reward(1.05, s) == 60   # above last point -> capped


def test_evaluate_reward_100_nm():
    assert evaluate("S", 1.0, "NM", 5.0) == ("pass", 60)


def test_evaluate_reward_100_nf():
    assert evaluate("S", 1.0, "+NF", 5.0) == ("pass", 50)


def test_evaluate_reward_100_ez_6star():
    assert evaluate("S", 1.0, "+EZ", 6.0) == ("pass", 80)


def test_evaluate_reward_95_nf_ht():
    assert evaluate("S", 0.95, "+NFHT", 5.0) == ("pass", 10)


def test_evaluate_reward_90_nf_ht():
    assert evaluate("S", 0.90, "+NFHT", 5.0) == ("pass", -20)


def test_evaluate_reward_70_nf_ht_clamped():
    assert evaluate("S", 0.70, "+NFHT", 5.0) == ("pass", -60)


# --------------------------------------------------------------------------- #
# Clamp [-60, +80]
# --------------------------------------------------------------------------- #

def test_pass_clamp_upper():
    # Reward table whose last point exceeds the clamp max -> clamped to 80.
    s = RankedSettings(acc_reward_table=((0.95, 10), (1.0, 100)))
    verdict, delta = evaluate("S", 1.0, "NM", 5.0, s)
    assert verdict == "pass"
    assert delta == 80


def test_pass_clamp_lower():
    s = RankedSettings(nf_ht_penalty=-20)
    verdict, delta = evaluate("C", 0.5, "+NF", 5.0, s)
    assert verdict == "pass"
    assert delta == -60


# --------------------------------------------------------------------------- #
# Forbidden mods -> invalid
# --------------------------------------------------------------------------- #

def test_forbidden_mods_are_invalid():
    for code in sorted(FORBIDDEN_MODS):
        verdict, delta = evaluate("S", 0.95, "+" + code, 5.0)
        assert verdict == "invalid", code
        assert delta == 0


def test_forbidden_embedded_in_string():
    verdict, _ = evaluate("S", 0.95, "+HDAP", 5.0)  # AP (Autopilot)
    assert verdict == "invalid"


def test_normal_mods_are_not_forbidden():
    assert not has_forbidden_mods("+HDDT")
    assert not has_forbidden_mods("+HDHR")
    assert not has_forbidden_mods("NM")
    assert not has_forbidden_mods("+EZ")


def test_auto_both_spellings():
    # "AU" is what this codebase's MODS_BITMAP emits for Auto; "AT" is the
    # osu! conventional spelling — both must be forbidden.
    assert has_forbidden_mods("+AU")
    assert has_forbidden_mods("+AT")
    assert evaluate("S", 0.95, "+AU", 5.0)[0] == "invalid"
    assert evaluate("S", 0.95, "+AT", 5.0)[0] == "invalid"


# --------------------------------------------------------------------------- #
# Parse mods
# --------------------------------------------------------------------------- #

def test_parse_mods():
    assert parse_mods("NM") == frozenset()
    assert parse_mods("") == frozenset()
    assert parse_mods(None) == frozenset()
    assert parse_mods("+HDDT") == {"HD", "DT"}
    assert parse_mods("+HDDT 1.25x") == {"HD", "DT"}
    assert parse_mods("HDDT") == {"HD", "DT"}  # defensive: no leading "+"
    assert has_ez("+EZ")


# --------------------------------------------------------------------------- #
# Round-trip against the client's canonical mods serializer
# --------------------------------------------------------------------------- #

def test_mods_roundtrip_against_client():
    mods_mod = pytest.importorskip("mcsu_bot.mods")
    bit_of = {name: bit for bit, name in mods_mod.MODS_BITMAP.items()}

    for code in sorted(FORBIDDEN_MODS):
        bit = bit_of.get(code)
        if bit is None:
            # "AT" is not in the client bitmap (client uses "AU"); covered by
            # test_auto_both_spellings above.
            continue
        codes = parse_mods(mods_mod.mods_to_string(bit))
        assert codes & FORBIDDEN_MODS, code

    for code in sorted(PENALTY_MODS):
        bit = bit_of[code]
        codes = parse_mods(mods_mod.mods_to_string(bit))
        assert code in codes

    # EZ is neither forbidden nor penalised, but must be recognised.
    assert has_ez(mods_mod.mods_to_string(bit_of["EZ"]))

    # No mods serialises to "NM" and parses back to an empty set.
    assert mods_mod.mods_to_string(0) == "NM"
    assert parse_mods(mods_mod.mods_to_string(0)) == frozenset()


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #

def test_as_utc_naive():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    out = as_utc(naive)
    assert out.tzinfo is not None
    assert out == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_as_utc_aware():
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    out = as_utc(aware)
    assert out == datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def test_as_utc_none():
    assert as_utc(None) is None


def test_timeout_seconds():
    assert timeout_seconds(100) == 600  # 100 * 3 = 300 -> floored to 600
    assert timeout_seconds(300) == 900  # 300 * 3 = 900
    assert timeout_seconds(0) == 600


def test_within_window_tolerance_both_sides():
    issued = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, 12, 30, 0, tzinfo=timezone.utc)

    # Lower boundary: exactly at issued - 120s is allowed, 121s is not.
    assert is_within_window(issued - timedelta(seconds=120), issued, now) is True
    assert is_within_window(issued - timedelta(seconds=119), issued, now) is True
    assert is_within_window(issued - timedelta(seconds=121), issued, now) is False

    # Upper boundary: not later than "now".
    assert is_within_window(now, issued, now) is True
    assert is_within_window(now + timedelta(seconds=1), issued, now) is False

    # Naive inputs are treated as UTC.
    assert is_within_window(
        issued.replace(tzinfo=None), issued.replace(tzinfo=None), now.replace(tzinfo=None)
    ) is True
