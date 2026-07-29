import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class Config:
    discord_token: str
    osu_client_id: str
    osu_client_secret: str
    scores_db_path: Path
    osu_cache_dir: Path
    songs_dir: Optional[Path]
    cfg_dir: Optional[Path] = None
    source: str = "mcsu"
    command_prefix: str = "!"
    ap_db_path: Optional[Path] = None
    osu_username: str = ""


def load_config(path: str = "config.json") -> Config:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    songs_dir = data.get("songs_dir")
    ap_db_path = data.get("ap_db_path")
    cfg_dir = data.get("cfg_dir")
    scores_db_path = Path(data["scores_db_path"])
    if cfg_dir is None:
        cfg_dir = scores_db_path.parent / "cfg"
    return Config(
        discord_token=data["discord_token"],
        osu_client_id=data["osu_client_id"],
        osu_client_secret=data["osu_client_secret"],
        scores_db_path=scores_db_path,
        osu_cache_dir=Path(data.get("osu_cache_dir", "cache/osu_files")),
        songs_dir=Path(songs_dir) if songs_dir else None,
        cfg_dir=Path(cfg_dir),
        command_prefix=data.get("command_prefix", "!"),
        ap_db_path=Path(ap_db_path) if ap_db_path else None,
        osu_username=data.get("osu_username", ""),
    )
