import asyncio
import threading
from pathlib import Path
from dataclasses import dataclass

from mcsu_bot.models import OsuScore, BeatmapMeta, PPResult
from mcsu_bot.db_reader import read_latest_score as read_latest_score_mcsu
from mcsu_bot.db_reader_osu import read_latest_score_osu
from mcsu_bot.pp_calculator import calculate_pp
from mcsu_bot.ap_calculator import calculate_ap, explain_ap, APBreakdown, _calculate_grade
from mcsu_bot.osu_api import OsuAPI
from mcsu_bot.database import Database


@dataclass
class ScoreFetchResult:
    success: bool = False
    error: str = ""
    score: OsuScore = None
    meta: BeatmapMeta = None
    pp_result: PPResult = None
    ap: float = 0.0
    breakdown: APBreakdown = None
    grade: str = ""
    duplicate: bool = False
    inserted: bool = False


def _get_latest_score(config):
    if getattr(config, "source", "mcsu") == "osu":
        return read_latest_score_osu(config.scores_db_path)
    return read_latest_score_mcsu(config.scores_db_path)


class ScoreFetcher(threading.Thread):
    def __init__(self, config, on_done, on_status=None):
        super().__init__(daemon=True)
        self.config = config
        self.on_done = on_done
        self.on_status = on_status or (lambda msg: None)

    def run(self):
        result = ScoreFetchResult()
        source = getattr(self.config, "source", "mcsu")
        self.on_status(f"Reading latest score from {'osu!' if source == 'osu' else 'McOsu'}...")
        try:
            score = _get_latest_score(self.config)
        except Exception as e:
            result.error = f"Failed to read scores.db: {e}"
            self.on_done(result)
            return

        try:
            api = OsuAPI(
                self.config.osu_client_id,
                self.config.osu_client_secret,
                self.config.osu_cache_dir,
                self.config.songs_dir,
            )

            if api.songs_dir and api.songs_dir.exists() and not api._index_path.exists():
                self.on_status("Building song index (first scan, this may take a minute)...")

            loop = asyncio.new_event_loop()
            meta = loop.run_until_complete(api.lookup_beatmap(score.beatmap_md5))
            loop.run_until_complete(api.close())
            loop.close()
        except Exception as e:
            result.error = f"osu! API error: {e}"
            self.on_done(result)
            return

        if meta is None:
            result.error = "Beatmap not found on osu! servers"
            self.on_done(result)
            return

        try:
            api2 = OsuAPI(
                self.config.osu_client_id,
                self.config.osu_client_secret,
                self.config.osu_cache_dir,
                self.config.songs_dir,
            )
            loop = asyncio.new_event_loop()
            osu_file = loop.run_until_complete(
                api2.download_beatmap_file(meta.beatmap_id or 0, meta.beatmapset_id or 0, score.beatmap_md5)
            )
            loop.run_until_complete(api2.close())
            loop.close()
        except Exception as e:
            result.error = f"Failed to download .osu file: {e}"
            self.on_done(result)
            return

        try:
            pp_result = calculate_pp(osu_file, score)
        except Exception as e:
            result.error = f"Failed to calculate PP: {e}"
            self.on_done(result)
            return

        result.score = score
        result.meta = meta
        result.pp_result = pp_result
        total_hits = score.count300 + score.count100 + score.count50 + score.count_miss
        result.grade = _calculate_grade(score.count300, total_hits, score.count50, score.count_miss, score.mods)
        result.ap = calculate_ap(score, meta, pp_result.accuracy, pp_result.star_rating_mods, pp_result)
        result.breakdown = explain_ap(score, meta, pp_result.accuracy, pp_result.star_rating_mods, pp_result)
        result.success = True

        db_path = self.config.ap_db_path or (Path(__file__).resolve().parent.parent.parent / "scores_ap.db")
        db = Database(db_path)
        try:
            db.connect()
            result.inserted = db.insert_score(score, meta, pp_result.accuracy, result.grade, result.ap)
            if not result.inserted:
                result.duplicate = True
        except Exception as e:
            result.error = f"DB error: {e}"
        finally:
            db.close()

        self.on_done(result)


class AutoScanWorker(threading.Thread):
    def __init__(self, scores_db_path, config, on_new_score, last_timestamp=None, poll_interval=3.0):
        super().__init__(daemon=True)
        self.scores_db_path = Path(scores_db_path)
        self.config = config
        self.on_new_score = on_new_score
        self.last_timestamp = last_timestamp
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.wait(self.poll_interval):
            try:
                latest = _get_latest_score(self.config)
            except Exception:
                continue
            if self.last_timestamp is not None and latest.timestamp > self.last_timestamp:
                self.last_timestamp = latest.timestamp
                self.on_new_score()
            elif self.last_timestamp is None:
                self.last_timestamp = latest.timestamp

    def stop(self):
        self._stop_event.set()
