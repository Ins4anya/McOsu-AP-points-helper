"""Normalise the server's stored mods to the canonical client format.

After the client's mods serialisation was unified (single '+' prefix), old
bulk-synced scores on the server may still store mods without the leading
'+' (e.g. "HDDT" instead of "+HDDT"). Because ``score_key`` is derived from
the raw mods string, such rows would be treated as brand-new scores if the
client re-syncs them, producing duplicates.

This script rewrites non-"NM" mods to the canonical "+..." form, recomputes
``score_key`` and removes any duplicates that collapse onto the same
(user_id, score_key). It only touches the server database (scores_server.db).

Usage:
    python -m server.backfill_normalize_mods          # dry run
    python -m server.backfill_normalize_mods --apply  # write changes
"""
from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

SRV_DB = Path(__file__).resolve().parent.parent / "scores_server.db"
APPLY = "--apply" in sys.argv


def normalize_mods(mods: str) -> str:
    m = (mods or "").strip()
    if not m or m == "NM":
        return "NM"
    if not m.startswith("+"):
        m = "+" + m
    return m


def make_score_key(md5: str, mods: str, max_combo: int, accuracy: float, pp: float) -> str:
    payload = f"{md5}|{mods}|{max_combo}|{round(accuracy, 4)}|{round(pp, 1)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def main() -> None:
    conn = sqlite3.connect(str(SRV_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")

    rows = conn.execute(
        "SELECT id, user_id, md5, mods, max_combo, accuracy, pp, score_key "
        "FROM scores"
    ).fetchall()

    plan: dict[int, tuple[str, str]] = {}
    for r in rows:
        new_mods = normalize_mods(r["mods"] or "")
        new_key = make_score_key(
            r["md5"] or "",
            new_mods,
            r["max_combo"] or 0,
            r["accuracy"] or 0.0,
            r["pp"] or 0.0,
        )
        plan[r["id"]] = (new_mods, new_key)

    # Group by (user_id, new_key): keep the smallest id in each group, the
    # rest are duplicates that collapse after normalisation.
    by_key: dict[tuple[int, str], list[int]] = {}
    for r in rows:
        _, new_key = plan[r["id"]]
        by_key.setdefault((r["user_id"], new_key), []).append(r["id"])
    keep = {min(ids) for ids in by_key.values()}

    to_update = 0
    to_delete = 0
    for r in rows:
        new_mods, new_key = plan[r["id"]]
        if r["id"] not in keep:
            to_delete += 1
            continue
        if new_mods != (r["mods"] or "") or new_key != (r["score_key"] or ""):
            to_update += 1

    print(f"Server DB: {SRV_DB}")
    print(f"Rows total:  {len(rows)}")
    print(f"To update:   {to_update}")
    print(f"To delete:   {to_delete}")

    if APPLY:
        for r in rows:
            if r["id"] not in keep:
                conn.execute("DELETE FROM scores WHERE id = ?", (r["id"],))
                continue
            new_mods, new_key = plan[r["id"]]
            conn.execute(
                "UPDATE scores SET mods = ?, score_key = ? WHERE id = ?",
                (new_mods, new_key, r["id"]),
            )
        conn.commit()
        print("Applied.")
    else:
        print("Dry run — pass --apply to write changes.")

    conn.close()


if __name__ == "__main__":
    main()
