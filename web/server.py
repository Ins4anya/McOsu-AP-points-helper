import sys
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STATIC_DIR = Path(__file__).resolve().parent / "static"

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_DB_PATH = BASE_DIR / "scores_ap.db"

config_path = BASE_DIR / "config.json"
if config_path.exists():
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    raw = cfg.get("ap_db_path")
    DB_PATH = Path(raw) if raw else DEFAULT_DB_PATH
else:
    DB_PATH = DEFAULT_DB_PATH

conn: Optional[sqlite3.Connection] = None


def get_db() -> sqlite3.Connection:
    global conn
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    global conn
    if conn:
        conn.close()

app = FastAPI(title="McOsu AP Tracker", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/daily")
async def get_daily():
    db = get_db()
    try:
        cur = db.execute("""
            SELECT
                DATE(timestamp, 'unixepoch') as date,
                ROUND(SUM(ap), 2) as total_ap,
                COUNT(*) as scores_count,
                ROUND(MAX(ap), 2) as best_score_ap
            FROM scores
            GROUP BY date
            ORDER BY date DESC
        """)
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


@app.get("/api/scores")
async def get_scores(date: str = Query(...)):
    start = datetime.strptime(date, "%Y-%m-%d").timestamp()
    end = start + 86400
    db = get_db()
    try:
        cur = db.execute(
            "SELECT * FROM scores WHERE timestamp >= ? AND timestamp < ? ORDER BY ap DESC",
            (int(start), int(end)),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


@app.get("/api/profile")
async def get_profile(goal: int = Query(0), source: str = Query("mcsu")):
    db = get_db()
    try:
        stats = db.execute(
            "SELECT COALESCE(SUM(ap),0) as total_ap, COUNT(*) as play_count FROM scores"
        ).fetchone()

        all_pps = [r[0] for r in db.execute("SELECT pp FROM scores WHERE pp > 0").fetchall()]
        all_pps.sort(reverse=True)
        weighted_pp = sum(pp * (0.95 ** i) for i, pp in enumerate(all_pps))

        grades = db.execute(
            "SELECT grade, COUNT(*) as cnt FROM scores WHERE grade != '' GROUP BY grade"
        ).fetchall()

        top = db.execute(
            "SELECT beatmap_title, score, accuracy, grade, mods, max_combo, pp, ap, timestamp "
            "FROM scores ORDER BY ap DESC LIMIT 5"
        ).fetchall()
    except sqlite3.OperationalError:
        return JSONResponse({"error": "no data"}, status_code=200)

    player_name = "Unknown"

    grades_dict = {"XH": 0, "X": 0, "SH": 0, "S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
    for g in grades:
        gl = g["grade"].strip().upper()
        if gl in grades_dict:
            grades_dict[gl] = g["cnt"]

    goals_completed = 0
    if goal > 0:
        try:
            cur = db.execute(
                """SELECT COUNT(*) FROM (
                    SELECT DATE(timestamp, 'unixepoch') as d
                    FROM scores GROUP BY d HAVING SUM(ap) >= ?
                )""",
                (goal,),
            )
            goals_completed = cur.fetchone()[0]
        except sqlite3.OperationalError:
            pass

    return {
        "player_name": player_name,
        "total_ap": round(stats["total_ap"], 1),
        "weighted_pp": round(weighted_pp, 1),
        "play_count": stats["play_count"],
        "goals_completed": goals_completed,
        "grades": grades_dict,
        "top_scores": [dict(t) for t in top],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
