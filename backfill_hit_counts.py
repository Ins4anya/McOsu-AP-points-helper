import sqlite3
import sys
from pathlib import Path

AP_DB = Path(__file__).resolve().parent / "scores_ap.db"
SRV_DB = Path(__file__).resolve().parent / "scores_server.db"

APPLY = "--apply" in sys.argv


def norm_mods(mods: str) -> str:
    m = (mods or "").strip()
    if m.startswith("+"):
        m = m[1:]
    m = "".join(m.split())
    return m or "NM"


def combo_key(md5, mods, mc):
    return f"{md5}|{norm_mods(mods)}|{mc}"


def main():
    ap = sqlite3.connect(str(AP_DB))
    ap.row_factory = sqlite3.Row
    srv = sqlite3.connect(str(SRV_DB))
    srv.row_factory = sqlite3.Row

    # client: combo_key -> list of hit-count tuples
    client = {}
    for row in ap.execute(
        "SELECT beatmap_md5, mods, max_combo, count300, count100, count50, count_miss FROM scores"
    ):
        key = combo_key(row["beatmap_md5"], row["mods"], row["max_combo"])
        client.setdefault(key, []).append((
            row["count300"] or 0,
            row["count100"] or 0,
            row["count50"] or 0,
            row["count_miss"] or 0,
        ))
    ap.close()

    rows = srv.execute(
        "SELECT id, md5, mods, max_combo FROM scores "
        "WHERE (count300 + count100 + count50 + count_miss) = 0"
    ).fetchall()

    updated = 0
    missing = 0
    for r in rows:
        key = combo_key(r["md5"], r["mods"], r["max_combo"])
        candidates = client.get(key)
        if not candidates:
            missing += 1
            continue
        c300, c100, c50, cmiss = candidates[0]
        if APPLY:
            srv.execute(
                "UPDATE scores SET count300=?, count100=?, count50=?, count_miss=? WHERE id=?",
                (c300, c100, c50, cmiss, r["id"]),
            )
        updated += 1

    if APPLY:
        srv.commit()
    srv.close()

    print(
        f"{'Applied' if APPLY else 'Dry-run'}: {updated} rows updated, {missing} not found in scores_ap.db"
    )


if __name__ == "__main__":
    main()
