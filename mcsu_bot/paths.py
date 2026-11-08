"""Cross-mode filesystem helpers (source tree vs PyInstaller frozen/onedir).

Two kinds of paths matter:

* ``resource_dir()`` — bundled, read-only files (assets, ``Ranks.txt``,
  templates, ``alembic.ini``).  When frozen these live inside the PyInstaller
  extraction dir (``sys._MEIPASS``); from source they live in the project root.

* ``data_dir()`` — writable state files (``server_token.json``,
  ``scores_ap.db``).  When frozen these live *next to the executable* (the same
  place ``launcher._config_path()`` looks for ``config.json``) so they are
  writable and survive across runs; from source they stay in the project root.

The frozen/source detection mirrors ``launcher._resource_path`` /
``launcher._config_path`` (``sys.frozen`` / ``sys._MEIPASS`` / ``sys.executable``).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Project root when running from source: the parent of this package
# (``mcsu_bot``).  Not used when frozen.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    """True when running from a PyInstaller-frozen executable."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Directory of bundled read-only resources (``sys._MEIPASS`` when frozen)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return _PROJECT_ROOT


def data_dir() -> Path:
    """Directory for writable state files (next to the .exe when frozen)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return _PROJECT_ROOT


def token_file() -> Path:
    return data_dir() / "server_token.json"


def ap_db_file() -> Path:
    return data_dir() / "scores_ap.db"
