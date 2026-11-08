"""Tests for mcsu_bot.paths — cross-mode (source vs frozen) path resolution."""
from __future__ import annotations

import sys
from pathlib import Path

from mcsu_bot import paths


def test_source_paths(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    root = paths._PROJECT_ROOT
    assert paths.is_frozen() is False
    assert paths.data_dir() == root
    assert paths.resource_dir() == root
    assert paths.token_file() == root / "server_token.json"
    assert paths.ap_db_file() == root / "scores_ap.db"


def test_frozen_data_dir(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:/release/McOsuTracker.exe")
    monkeypatch.setattr(sys, "_MEIPASS", "C:/release/McOsuTracker/_internal", raising=False)

    assert paths.is_frozen() is True
    # Writable state lives next to the .exe, not in the extraction dir.
    assert paths.data_dir() == Path("C:/release")
    assert paths.token_file() == Path("C:/release/server_token.json")
    assert paths.ap_db_file() == Path("C:/release/scores_ap.db")


def test_frozen_resource_dir(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:/release/McOsuTracker.exe")
    monkeypatch.setattr(sys, "_MEIPASS", "C:/release/McOsuTracker/_internal", raising=False)

    # Bundled read-only resources live inside _MEIPASS when frozen.
    assert paths.resource_dir() == Path("C:/release/McOsuTracker/_internal")


def test_frozen_resource_dir_fallback_to_exe_dir(monkeypatch):
    # _MEIPASS may be absent in some edge cases -> fall back to the exe dir.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:/release/McOsuTracker.exe")
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert paths.resource_dir() == Path("C:/release")
