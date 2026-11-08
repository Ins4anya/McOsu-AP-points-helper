"""Backfill aim/stars/density for scores synced before those fields existed.

Bulk-synced scores (``sync_all_scores``) were stored on the server with
``aim = 0`` and ``density = 0``, so ``server.skills`` silently drops them.
This script re-runs rosu on each map's local ``.osu`` file (looked up by md5
in the osu! Songs folder) to fill in ``aim`` (mod-adjusted aim stars),
``stars`` (mod-adjusted total stars) and ``density``.

Scores whose map isn't found locally are skipped (they stay out of the
skills radar until re-synced from the client).

Usage:
    python backfill_skills.py            # dry run
    python backfill_skills.py --apply    # write changes
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from mcsu_bot.mods import parse_mods_string
from mcsu_bot.models import OsuScore
from mcsu_bot.osu_api import _build_md5_index
from mcsu_bot.pp_calculator import calculate_pp

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "config.json"
AP_DB = BASE / "scores_ap.db"
SRV_DB = BASE / "scores_server.db"

APPLY = "--apply" in sys.argv


def _load_paths() -> tuple[Path | None, Path]:
    songs_dir: Path | None = None
    cache_dir = BASE / "cache" / "osu_files"
    if CONFIG.exists():
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        raw_songs = data.get("songs_dir")
        if raw_songs:
            p = Path(raw_songs)
            songs_dir = p if p.is_absolute() else (BASE / p)
        raw_cache = data.get("osu_cache_dir", "cache/osu_files")
        p = Path(raw_cache)
        cache_dir = p if p.is_absolute() else (BASE / p)
    return songs_dir, cache_dir


def main() -> None:
    songs_dir, cache_dir = _load_paths()

    # Map length per md5, from the client's local scores DB (for density).
    lengths: dict[str, int] = {}
    if AP_DB.exists():
        conn = sqlite3.connect(str(AP_DB))
        conn.row_factory = sqlite3.Row
        try:
            for r in conn.execute(
                "SELECT beatmap_md5, MAX(length_sec) AS length_sec "
                "FROM scores WHERE beatmap_md5 != '' GROUP BY beatmap_md5"
            ):
                if r["beatmap_md5"] and r["length_sec"]:
                    lengths[r["beatmap_md5"]] = int(r["length_sec"])
        finally:
            conn.close()

    # md5 -> .osu path index (reused across runs).
    md5_index: dict[str, str] = {}
    if songs_dir and songs_dir.exists():
        index_path = cache_dir / "md5_index.json"
        if index_path.exists():
            try:
                md5_index = json.loads(index_path.read_text(encoding="utf-8"))
            except Exception:
                md5_index = {}
        if not md5_index:
            md5_index = _build_md5_index(songs_dir, index_path)

    conn = sqlite3.connect(str(SRV_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, md5, mods, max_combo, count300, count100, count50, "
            "count_miss, speed_mult, eff_cs, eff_ar, eff_od, eff_hp "
            "FROM scores WHERE aim = 0 OR aim IS NULL"
        ).fetchall()

        to_update = 0
        skipped = 0
        for r in rows:
            md5 = r["md5"] or ""
            osu_path = md5_index.get(md5)
            if not osu_path or not Path(osu_path).exists():
                skipped += 1
                continue
            try:
                osu_bytes = Path(osu_path).read_bytes()
            except OSError:
                skipped += 1
                continue

            speed_mult = r["speed_mult"] or 1.0
            score = OsuScore(
                beatmap_md5=md5,
                score=0,
                max_combo=r["max_combo"] or 0,
                count300=r["count300"] or 0,
                count100=r["count100"] or 0,
                count50=r["count50"] or 0,
                count_miss=r["count_miss"] or 0,
                count_geki=0,
                count_katu=0,
                mods=parse_mods_string(r["mods"] or ""),
                perfect=False,
                timestamp=0,
                pp=0.0,
                speed_mult=speed_mult if speed_mult > 0 else None,
                cs=r["eff_cs"] or 0.0,
                ar=r["eff_ar"] or 0.0,
                od=r["eff_od"] or 0.0,
                hp=r["eff_hp"] or 0.0,
            )
            pp_result = calculate_pp(osu_bytes, score)

            total_hits = (
                (r["count300"] or 0)
                + (r["count100"] or 0)
                + (r["count50"] or 0)
                + (r["count_miss"] or 0)
            )
            rate = speed_mult if speed_mult > 0 else 1.0
            length = lengths.get(md5, 0)
            effective_length = length / rate if length > 0 and rate > 0 else 0.0
            density = total_hits / effective_length if effective_length > 0 else 0.0

            to_update += 1
            if APPLY:
                conn.execute(
                    "UPDATE scores SET aim = ?, stars = ?, density = ? WHERE id = ?",
                    (
                        pp_result.stars_aim_mods,
                        pp_result.star_rating_mods,
                        density,
                        r["id"],
                    ),
                )

        if APPLY:
            conn.commit()

        print(f"Server DB:  {SRV_DB}")
        print(f"Songs dir:  {songs_dir or '(not set)'}")
        print(f"Candidates: {len(rows)} (aim == 0)")
        print(f"To update:  {to_update}")
        print(f"Skipped:    {skipped} (no local .osu)")
        print("Applied." if APPLY else "Dry run — pass --apply to write changes.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
