"""Tests for server.config ranked_* env validation."""
from __future__ import annotations

import pytest

from server.config import ServerConfig
from server.ranked_rules import DEFAULT_ACC_REWARD_TABLE


def _cfg() -> ServerConfig:
    return ServerConfig.from_env()


# --------------------------------------------------------------------------- #
# Code defaults
# --------------------------------------------------------------------------- #


def test_ranked_code_defaults():
    c = ServerConfig()
    assert c.ranked_start_elo == 500
    assert c.ranked_elo_floor == 100
    assert c.ranked_fail_delta == -60
    assert c.ranked_nf_ht_penalty == -10
    assert c.ranked_reroll_penalty == -5
    assert c.ranked_star_window == 0.15
    assert c.ranked_clamp_min == -60
    assert c.ranked_clamp_max == 80
    assert c.ranked_ez_bonus_low == 10
    assert c.ranked_ez_bonus_high == 20
    assert c.ranked_acc_reward_table == DEFAULT_ACC_REWARD_TABLE


def test_ranked_acc_threshold_is_gone(monkeypatch):
    # RANKED_ACC_THRESHOLD is no longer read; the setting no longer exists.
    monkeypatch.setenv("RANKED_ACC_THRESHOLD", "0.9")
    assert not hasattr(_cfg(), "ranked_acc_threshold")


# --------------------------------------------------------------------------- #
# Env validation
# --------------------------------------------------------------------------- #


def test_ranked_fail_delta_nonpositive(monkeypatch):
    monkeypatch.setenv("RANKED_FAIL_DELTA", "5")
    assert _cfg().ranked_fail_delta == -60  # default, invalid (positive)


def test_ranked_nf_ht_penalty_nonpositive(monkeypatch):
    monkeypatch.setenv("RANKED_NF_HT_PENALTY", "5")
    assert _cfg().ranked_nf_ht_penalty == -10  # default, invalid (positive)


def test_ranked_reroll_penalty_nonpositive(monkeypatch):
    monkeypatch.setenv("RANKED_REROLL_PENALTY", "2")
    assert _cfg().ranked_reroll_penalty == -5  # default, invalid (positive)


def test_ranked_clamp_min_le_max(monkeypatch):
    monkeypatch.setenv("RANKED_CLAMP_MIN", "30")
    monkeypatch.setenv("RANKED_CLAMP_MAX", "20")
    c = _cfg()
    assert c.ranked_clamp_min == -60
    assert c.ranked_clamp_max == 80


def test_ranked_elo_floor_le_start(monkeypatch):
    monkeypatch.setenv("RANKED_ELO_FLOOR", "200")
    monkeypatch.setenv("RANKED_START_ELO", "100")
    c = _cfg()
    assert c.ranked_elo_floor == 100
    assert c.ranked_start_elo == 500


def test_ranked_min_length_lt_max(monkeypatch):
    monkeypatch.setenv("RANKED_MIN_LENGTH_SECONDS", "700")
    monkeypatch.setenv("RANKED_MAX_LENGTH_SECONDS", "600")
    c = _cfg()
    assert c.ranked_min_length_seconds == 60
    assert c.ranked_max_length_seconds == 600


def test_ranked_timeout_multiplier_positive(monkeypatch):
    monkeypatch.setenv("RANKED_TIMEOUT_MULTIPLIER", "0")
    assert _cfg().ranked_timeout_multiplier == 3.0


def test_ranked_daily_reroll_limit_nonnegative(monkeypatch):
    monkeypatch.setenv("RANKED_DAILY_REROLL_LIMIT", "-1")
    assert _cfg().ranked_daily_reroll_limit == 3


def test_ranked_valid_values_accepted(monkeypatch):
    monkeypatch.setenv("RANKED_FAIL_DELTA", "-20")
    monkeypatch.setenv("RANKED_TIMEOUT_MULTIPLIER", "2.0")
    monkeypatch.setenv("RANKED_DAILY_REROLL_LIMIT", "5")
    c = _cfg()
    assert c.ranked_fail_delta == -20
    assert c.ranked_timeout_multiplier == 2.0
    assert c.ranked_daily_reroll_limit == 5


def test_ranked_enabled_flag(monkeypatch):
    monkeypatch.setenv("RANKED_ENABLED", "true")
    assert _cfg().ranked_enabled is True
    monkeypatch.setenv("RANKED_ENABLED", "false")
    assert _cfg().ranked_enabled is False


# --------------------------------------------------------------------------- #
# Star window (RANKED_STAR_WINDOW)
# --------------------------------------------------------------------------- #


def test_ranked_star_window_default(monkeypatch):
    monkeypatch.delenv("RANKED_STAR_WINDOW", raising=False)
    assert ServerConfig().ranked_star_window == 0.15
    assert _cfg().ranked_star_window == 0.15


@pytest.mark.parametrize("raw", ["0", "-0.1", "1.1", "2", "abc", "nan", "inf"])
def test_ranked_star_window_invalid_uses_default(monkeypatch, raw):
    monkeypatch.setenv("RANKED_STAR_WINDOW", raw)
    assert _cfg().ranked_star_window == 0.15


@pytest.mark.parametrize("raw,expected", [("0.15", 0.15), ("0.5", 0.5), ("1.0", 1.0)])
def test_ranked_star_window_valid_accepted(monkeypatch, raw, expected):
    monkeypatch.setenv("RANKED_STAR_WINDOW", raw)
    assert _cfg().ranked_star_window == expected


# --------------------------------------------------------------------------- #
# Accuracy reward table (RANKED_ACC_REWARD_TABLE)
# --------------------------------------------------------------------------- #

DEFAULT_TABLE = ((0.70, -60), (0.90, 0), (1.0, 60))


def test_acc_reward_table_default(monkeypatch):
    monkeypatch.delenv("RANKED_ACC_REWARD_TABLE", raising=False)
    assert _cfg().ranked_acc_reward_table == DEFAULT_TABLE


def test_acc_reward_table_valid_with_negative_rewards(monkeypatch):
    monkeypatch.setenv("RANKED_ACC_REWARD_TABLE", "0.70:-60,0.90:0,1.0:60")
    assert _cfg().ranked_acc_reward_table == ((0.70, -60), (0.90, 0), (1.0, 60))


def test_acc_reward_table_first_below_old_threshold_is_valid(monkeypatch):
    # The old "first point >= 95%" rule was removed.
    monkeypatch.setenv("RANKED_ACC_REWARD_TABLE", "0.90:10,1.0:20")
    assert _cfg().ranked_acc_reward_table == ((0.90, 10), (1.0, 20))


def test_acc_reward_table_single_point(monkeypatch):
    monkeypatch.setenv("RANKED_ACC_REWARD_TABLE", "0.95:10")
    assert _cfg().ranked_acc_reward_table == DEFAULT_TABLE  # needs >= 2 points


def test_acc_reward_table_accuracy_not_increasing(monkeypatch):
    monkeypatch.setenv("RANKED_ACC_REWARD_TABLE", "0.95:10,0.95:20")
    assert _cfg().ranked_acc_reward_table == DEFAULT_TABLE


def test_acc_reward_table_reward_decreasing(monkeypatch):
    monkeypatch.setenv("RANKED_ACC_REWARD_TABLE", "0.90:20,1.0:10")
    assert _cfg().ranked_acc_reward_table == DEFAULT_TABLE


def test_acc_reward_table_first_accuracy_not_positive(monkeypatch):
    monkeypatch.setenv("RANKED_ACC_REWARD_TABLE", "0.0:10,1.0:20")
    assert _cfg().ranked_acc_reward_table == DEFAULT_TABLE


def test_acc_reward_table_last_above_one(monkeypatch):
    monkeypatch.setenv("RANKED_ACC_REWARD_TABLE", "0.95:10,1.1:20")
    assert _cfg().ranked_acc_reward_table == DEFAULT_TABLE


def test_acc_reward_table_malformed(monkeypatch):
    monkeypatch.setenv("RANKED_ACC_REWARD_TABLE", "garbage")
    assert _cfg().ranked_acc_reward_table == DEFAULT_TABLE
