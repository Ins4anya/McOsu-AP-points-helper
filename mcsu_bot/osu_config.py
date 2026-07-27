import os
import configparser
from pathlib import Path
from typing import Optional


def find_osu_dir() -> Optional[Path]:
    """Try to locate the osu! stable installation directory."""
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        path = Path(localappdata) / "osu!"
        if path.is_dir():
            return path

    appdata = os.environ.get("APPDATA")
    if appdata:
        path = Path(appdata) / "osu!"
        if path.is_dir():
            return path

    program_files = Path("C:/Program Files/osu!")
    if program_files.is_dir():
        return program_files

    return None


def find_osu_scores_db() -> Optional[Path]:
    """Return path to osu! stable scores.db if it exists."""
    d = find_osu_dir()
    if d is None:
        return None
    p = d / "scores.db"
    return p if p.is_file() else None


def parse_osu_cfg(cfg_path: Optional[Path] = None) -> dict[str, str]:
    """Parse osu!.cfg and return key config values.

    The osu!.cfg file uses Windows INI-like format.
    """
    if cfg_path is None:
        d = find_osu_dir()
        if d is None:
            return {}
        cfg_path = d / "osu!.cfg"

    if not cfg_path.is_file():
        return {}

    values: dict[str, str] = {}

    parser = configparser.ConfigParser()
    try:
        parser.read(str(cfg_path), encoding="utf-8")
    except Exception:
        pass

    # Main section (unnamed or [Main])
    if parser.sections():
        section = parser[parser.sections()[0]]
        for key in ("Username", "OsuPath", "EditorFont"):
            if key in section:
                values[key] = section[key]

    # Fallback: read raw lines to catch settings outside sections
    try:
        text = cfg_path.read_text(encoding="utf-8")
    except Exception:
        return values

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("[") or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            if k not in values:
                values[k] = v

    return values


def read_player_name_osu(cfg_dir: Optional[Path] = None) -> str:
    """Read the player name from osu!.cfg."""
    if cfg_dir is not None:
        cfg_path = cfg_dir / "osu!.cfg"
        vals = parse_osu_cfg(cfg_path)
    else:
        vals = parse_osu_cfg()

    return vals.get("Username", "")
