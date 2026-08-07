import sqlite3
from datetime import datetime
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
    timestamp INTEGER NOT NULL,
    player_name TEXT,
    created_at TEXT DEFAULT (datetime('now'))
)
"""

CREATE_DAILY = """
CREATE TABLE IF NOT EXISTS daily_ap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT UNIQUE NOT NULL,
    total_ap REAL NOT NULL DEFAULT 0,
    scores_count INTEGER NOT NULL DEFAULT 0,
    best_score_ap REAL NOT NULL DEFAULT 0
)
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(CREATE_SCORES)
        self.conn.executescript(CREATE_DAILY)
        self._migrate()
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _migrate(self):
        existing = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(scores)").fetchall()
        }
        for col in ("num_circles", "num_sliders", "num_spinners", "object_weight"):
            if col not in existing:
                self.conn.execute(f"ALTER TABLE scores ADD COLUMN {col} INTEGER DEFAULT 0")

    def is_duplicate(self, score: OsuScore, accuracy: float) -> bool:
        mods_str = self._mods_to_string(score.mods)
        cur = self.conn.execute(
            """SELECT COUNT(*) FROM scores
               WHERE beatmap_md5 = ?
                 AND mods = ?
                 AND max_combo = ?
                 AND ROUND(accuracy, 4) = ROUND(?, 4)
                 AND ROUND(pp, 1) = ROUND(?, 1)""",
            (score.beatmap_md5, mods_str, score.max_combo, accuracy, score.pp),
        )
        return cur.fetchone()[0] > 0

    def insert_score(
        self,
        score: OsuScore,
        meta: BeatmapMeta,
        accuracy: float,
        grade: str,
        ap: float,
    ) -> bool:
        if self.is_duplicate(score, accuracy):
            return False

        total_hits = score.count300 + score.count100 + score.count50 + score.count_miss
        mods_str = self._mods_to_string(score.mods)
        title = f"{meta.artist} - {meta.title} [{meta.difficulty}]"
        date = datetime.utcfromtimestamp(score.timestamp).strftime("%Y-%m-%d")

        self.conn.execute(
            """INSERT INTO scores
               (beatmap_title, beatmap_md5, score, max_combo,
                count300, count100, count50, count_miss,
                accuracy, grade, mods, pp, ap,
                total_hits, star_rating, length_sec,
                num_circles, num_sliders, num_spinners, object_weight,
                timestamp, player_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title, score.beatmap_md5, score.score, score.max_combo,
                score.count300, score.count100, score.count50, score.count_miss,
                accuracy, grade, mods_str, score.pp, ap,
                total_hits, meta.star_rating, meta.length,
                meta.num_circles, meta.num_sliders, meta.num_spinners, meta.object_weight,
                score.timestamp, score.player_name,
            ),
        )

        self.conn.commit()
        return True

    def get_scores_by_date(self, date: str) -> list[sqlite3.Row]:
        start = datetime.strptime(date, "%Y-%m-%d").timestamp()
        end = start + 86400
        cur = self.conn.execute(
            "SELECT * FROM scores WHERE timestamp >= ? AND timestamp < ? ORDER BY ap DESC",
            (int(start), int(end)),
        )
        return cur.fetchall()

    def get_daily_summary(self) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT date, total_ap, scores_count, best_score_ap FROM daily_ap ORDER BY date DESC"
        )
        return cur.fetchall()

    def get_recent_scores(self, limit: int = 50) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM scores ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    def get_all_scores(self) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM scores ORDER BY timestamp ASC"
        )
        return cur.fetchall()

    @staticmethod
    def _mods_to_string(mods: int) -> str:
        if mods == 0:
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
        return "+" + "".join(result)
