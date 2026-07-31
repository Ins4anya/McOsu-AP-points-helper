import asyncio
import threading
from pathlib import Path
from dataclasses import dataclass

from mcsu_bot.models import OsuScore, BeatmapMeta, PPResult
from mcsu_bot.db_reader import read_latest_score as read_latest_score_mcsu
from mcsu_bot.pp_calculator import calculate_pp
from mcsu_bot.ap_calculator import calculate_ap, explain_ap, APBreakdown, _calculate_grade
from mcsu_bot.osu_api import OsuAPI, _api_score_to_osu_score
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


class OsuApiScoreFetcher(threading.Thread):
    def __init__(self, config, osu_username, on_done, on_status=None):
        super().__init__(daemon=True)
        self.config = config
        self.osu_username = osu_username
        self.on_done = on_done
        self.on_status = on_status or (lambda msg: None)

    def run(self):
        result = ScoreFetchResult()
        self.on_status(f"Fetching latest score for '{self.osu_username}' from osu! API...")

        async def _fetch():
            api = OsuAPI(
                self.config.osu_client_id,
                self.config.osu_client_secret,
                self.config.osu_cache_dir,
                self.config.songs_dir,
            )
            try:
                raw_scores = await api.get_recent_scores(self.osu_username)
                if not raw_scores:
                    return None, "No recent scores found"

                api_score = raw_scores[0]
                score = _api_score_to_osu_score(api_score)

                beatmap_id = api_score.get("beatmap", {}).get("id")
                if not beatmap_id:
                    return None, "No beatmap ID in API response"

                meta = await api.lookup_beatmap_by_id(beatmap_id)
                if meta is None:
                    return None, "Beatmap not found on osu! servers"

                osu_file = None
                if self.config.songs_dir:
                    try:
                        osu_file = await api.download_beatmap_file(
                            meta.beatmap_id or 0, meta.beatmapset_id or 0, ""
                        )
                    except Exception:
                        osu_file = None

                return (api_score, score, meta, osu_file), None
            finally:
                await api.close()

        try:
            loop = asyncio.new_event_loop()
            data, error = loop.run_until_complete(_fetch())
            loop.close()
        except Exception as e:
            result.error = f"osu! API error: {e}"
            self.on_done(result)
            return

        if error:
            result.error = error
            self.on_done(result)
            return

        api_score, score, meta, osu_file = data

        if osu_file:
            try:
                pp_result = calculate_pp(osu_file, score)
            except Exception:
                pp_result = PPResult(
                    pp=score.pp,
                    accuracy=sum((
                        score.count300 * 300 + score.count100 * 100 + score.count50 * 50
                    )) / max(1, sum((
                        score.count300 + score.count100 + score.count50 + score.count_miss
                    )) * 300),
                    star_rating_mods=meta.star_rating,
                )
        else:
            total_hits = score.count300 + score.count100 + score.count50 + score.count_miss
            acc = (300 * score.count300 + 100 * score.count100 + 50 * score.count50) / (300 * total_hits) if total_hits > 0 else 1.0
            pp_result = PPResult(
                pp=score.pp,
                accuracy=acc,
                star_rating_mods=meta.star_rating,
            )

        score.max_possible_combo = pp_result.max_combo
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
    def __init__(self, poll_fn, on_new_score, last_marker=None, poll_interval=3.0):
        super().__init__(daemon=True)
        self.poll_fn = poll_fn
        self.on_new_score = on_new_score
        self.last_marker = last_marker
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.wait(self.poll_interval):
            try:
                marker = self.poll_fn()
            except Exception:
                continue
            if marker is None:
                continue
            if self.last_marker is not None and marker != self.last_marker:
                self.last_marker = marker
                self.on_new_score()
            elif self.last_marker is None:
                self.last_marker = marker

    def stop(self):
        self._stop_event.set()


class OsuApiAutoScanWorker(AutoScanWorker):
    def __init__(self, config, username, on_new_score, poll_interval=3.0):
        self.config = config
        self.username = username
        self._api = None
        self._loop = None
        super().__init__(
            poll_fn=self._poll,
            on_new_score=on_new_score,
            poll_interval=poll_interval,
        )

    def _poll(self):
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        if self._api is None:
            self._api = OsuAPI(
                self.config.osu_client_id,
                self.config.osu_client_secret,
                self.config.osu_cache_dir,
                self.config.songs_dir,
            )
        return self._loop.run_until_complete(self._fetch_latest_id())

    async def _fetch_latest_id(self):
        scores = await self._api.get_recent_scores(self.username)
        if not scores:
            return None
        return scores[0].get("id")

    def stop(self):
        if self._loop is not None and not self._loop.is_closed():
            try:
                if self._api is not None:
                    self._loop.run_until_complete(self._api.close())
            except Exception:
                pass
            self._loop.close()
        super().stop()
