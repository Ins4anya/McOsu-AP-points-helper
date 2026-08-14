import hashlib
import sqlite3
from pathlib import Path
from typing import Optional

from .models import OsuScore, BeatmapMeta


CREATE_SCORES = """
CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    beatmap_title TEXT,
    beatmap_md5 TEXT NOT NULL,
    score INTEGER,
    max_combo INTEGER,
    count300 INTEGER, count100 INTEGER, count50 INTEGER, count_miss INTEGER,
    accuracy REAL, grade TEXT, mods TEXT, pp REAL, ap REAL,
    total_hits INTEGER, star_rating REAL, length_sec INTEGER,
    num_circles INTEGER, num_sliders INTEGER, num_spinners INTEGER, object_weight INTEGER,
    speed_mult REAL DEFAULT 1.0,
    eff_cs REAL DEFAULT 0.0, eff_ar REAL DEFAULT 0.0, eff_od REAL DEFAULT 0.0, eff_hp REAL DEFAULT 0.0,
    timestamp INTEGER NOT NULL,
    player_name TEXT,
    created_at TEXT DEFAULT (datetime('now'))
)
"""

SCHEMA_VERSION = 3

_LEGACY_COLUMNS = ("num_circles", "num_sliders", "num_spinners", "object_weight")


def make_score_key(
    md5: str, mods: str, max_combo: int, accuracy: float, pp: float
) -> str:
    payload = f"{md5}|{mods}|{max_combo}|{round(accuracy, 4)}|{round(pp, 1)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(CREATE_SCORES)
        self._migrate()
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _version(self) -> int:
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def _set_version(self, version: int):
        self.conn.execute(f"PRAGMA user_version = {int(version)}")

    def _migrate(self):
        version = self._version()
        if version < 1:
            existing = {
                row["name"]
                for row in self.conn.execute("PRAGMA table_info(scores)").fetchall()
            }
            for col in _LEGACY_COLUMNS:
                if col not in existing:
                    self.conn.execute(
                        f"ALTER TABLE scores ADD COLUMN {col} INTEGER DEFAULT 0"
                    )
            self._set_version(1)
            version = 1
        if version < 2:
            self._migrate_to_v2()
            self._set_version(2)
            version = 2
        if version < 3:
            self._migrate_to_v3()
            self._set_version(3)
            version = 3

    def _migrate_to_v3(self):
        existing = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(scores)").fetchall()
        }
        for col, ddl in (
            ("speed_mult", "REAL DEFAULT 1.0"),
            ("eff_cs", "REAL DEFAULT 0.0"),
            ("eff_ar", "REAL DEFAULT 0.0"),
            ("eff_od", "REAL DEFAULT 0.0"),
            ("eff_hp", "REAL DEFAULT 0.0"),
        ):
            if col not in existing:
                self.conn.execute(f"ALTER TABLE scores ADD COLUMN {col} {ddl}")

    def _migrate_to_v2(self):
        existing = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(scores)").fetchall()
        }
        if "score_key" not in existing:
            self.conn.execute("ALTER TABLE scores ADD COLUMN score_key TEXT")

        rows = self.conn.execute(
            "SELECT id, beatmap_md5, mods, max_combo, accuracy, pp "
            "FROM scores WHERE score_key IS NULL OR score_key = ''"
        ).fetchall()
        for row in rows:
            key = make_score_key(
                row["beatmap_md5"] or "",
                row["mods"] or "NM",
                row["max_combo"] or 0,
                row["accuracy"] or 0.0,
                row["pp"] or 0.0,
            )
            self.conn.execute(
                "UPDATE scores SET score_key = ? WHERE id = ?", (key, row["id"])
            )

        self.conn.execute(
            """DELETE FROM scores WHERE id NOT IN (
                SELECT MIN(id) FROM scores
                WHERE score_key IS NOT NULL AND score_key != ''
                GROUP BY score_key
            )"""
        )

        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_scores_score_key ON scores(score_key)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scores_timestamp ON scores(timestamp)"
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_scores_ap ON scores(ap)")
        self.conn.execute("DROP TABLE IF EXISTS daily_ap")

    def insert_score(
        self,
        score: OsuScore,
        meta: BeatmapMeta,
        accuracy: float,
        grade: str,
        ap: float,
        commit: bool = True,
    ) -> bool:
        total_hits = score.count300 + score.count100 + score.count50 + score.count_miss
        mods_str = self._mods_to_string(score.mods, score.speed_mult)
        title = f"{meta.artist} - {meta.title} [{meta.difficulty}]"
        key = make_score_key(score.beatmap_md5, mods_str, score.max_combo, accuracy, score.pp)

        cur = self.conn.execute(
            """INSERT OR IGNORE INTO scores
               (beatmap_title, beatmap_md5, score, max_combo,
                count300, count100, count50, count_miss,
                accuracy, grade, mods, pp, ap,
                total_hits, star_rating, length_sec,
                num_circles, num_sliders, num_spinners, object_weight,
                speed_mult, eff_cs, eff_ar, eff_od, eff_hp,
                timestamp, player_name, score_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title, score.beatmap_md5, score.score, score.max_combo,
                score.count300, score.count100, score.count50, score.count_miss,
                accuracy, grade, mods_str, score.pp, ap,
                total_hits, meta.star_rating, meta.length,
                meta.num_circles, meta.num_sliders, meta.num_spinners, meta.object_weight,
                score.speed_mult if score.speed_mult is not None else 1.0,
                score.cs, score.ar, score.od, score.hp,
                score.timestamp, score.player_name, key,
            ),
        )
        if commit:
            self.conn.commit()
        return cur.rowcount > 0

    def get_all_scores(self) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM scores ORDER BY timestamp ASC"
        )
        return cur.fetchall()

    @staticmethod
    def _mods_to_string(mods: int, speed_mult=None) -> str:
        if mods == 0 and (speed_mult is None or abs(speed_mult - 1.0) < 0.005):
            return "NM"
        MODS_BITMAP = {
            1 << 0: "NF", 1 << 1: "EZ", 1 << 2: "TD", 1 << 3: "HD",
            1 << 4: "HR", 1 << 5: "SD", 1 << 6: "DT", 1 << 7: "RX",
            1 << 8: "HT", 1 << 9: "NC", 1 << 10: "FL", 1 << 11: "AU",
            1 << 12: "SO", 1 << 13: "AP", 1 << 14: "PF", 1 << 15: "4K",
            1 << 16: "5K", 1 << 17: "6K", 1 << 18: "7K", 1 << 19: "8K",
            1 << 20: "FI", 1 << 21: "RN", 1 << 22: "CN", 1 << 23: "TP",
            1 << 24: "9K", 1 << 25: "KC", 1 << 26: "1K", 1 << 27: "3K",
            1 << 28: "2K", 1 << 29: "V2", 1 << 30: "MR",
        }
        result = []
        for bit, name in MODS_BITMAP.items():
            if mods & bit:
                result.append(name)
        if "NC" in result and "DT" in result:
            result.remove("DT")
        if "PF" in result and "SD" in result:
            result.remove("SD")
        tag = ""
        if speed_mult is not None and speed_mult > 0:
            expected = 1.5 if (mods & (1 << 6 | 1 << 9)) else (0.75 if (mods & (1 << 8)) else 1.0)
            if abs(speed_mult - expected) >= 0.005:
                tag = f" {speed_mult:g}x"
        base = "+" + "".join(result)
        return base + tag if (result or tag) else "NM"
