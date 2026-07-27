import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Optional

import aiohttp

from .models import BeatmapMeta


def _parse_osu_header(osu_bytes: bytes) -> dict:
    text = osu_bytes.decode("utf-8", errors="replace")
    result = {}
    section = None

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if ":" not in line:
            continue

        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()

        if section == "Metadata":
            result[key] = val
        elif section == "Difficulty":
            try:
                result[key] = float(val)
            except ValueError:
                pass
        elif section == "TimingPoints" and "BPM" not in result:
            parts = line.split(",")
            if len(parts) >= 7 and parts[6] == "1":
                beat_length = float(parts[1])
                if beat_length > 0:
                    result["BPM"] = 60000.0 / beat_length
        elif section == "HitObjects" and "LastHitTime" not in result:
            parts = line.split(",")
            if len(parts) >= 3:
                try:
                    obj_time = int(parts[2])
                    result["LastHitTime"] = obj_time
                except ValueError:
                    pass

    return result


def _build_meta_from_osu(osu_bytes: bytes) -> Optional[BeatmapMeta]:
    parsed = _parse_osu_header(osu_bytes)

    artist = parsed.get("Artist", "")
    title = parsed.get("Title", "")
    version = parsed.get("Version", "")
    creator = parsed.get("Creator", "")

    if not artist or not title:
        return None

    cs = parsed.get("CircleSize", 0)
    ar = parsed.get("ApproachRate", 0)
    od = parsed.get("OverallDifficulty", 0)
    hp = parsed.get("HPDrainRate", 0)
    bpm = parsed.get("BPM", 0)

    last_time = parsed.get("LastHitTime", 0)
    length = last_time // 1000

    return BeatmapMeta(
        artist=artist,
        title=title,
        difficulty=version,
        creator=creator,
        bpm=bpm,
        cs=cs,
        ar=ar,
        od=od,
        hp=hp,
        length=length,
    )


def _build_md5_index(songs_dir: Path, index_path: Path):
    index = {}
    for d in songs_dir.iterdir():
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.suffix.lower() != ".osu":
                continue
            try:
                content = f.read_bytes()
                file_md5 = hashlib.md5(content).hexdigest()
                index[file_md5] = str(f.absolute())
            except Exception:
                continue
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return index


class OsuAPI:
    def __init__(self, client_id: str, client_secret: str, cache_dir: Path, songs_dir: Optional[Path] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.songs_dir = songs_dir
        self._index_path = cache_dir / "md5_index.json"

        self._token: Optional[str] = None
        self._token_expiry: float = 0
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _ensure_token(self):
        if self._token and time.time() < self._token_expiry:
            return
        session = await self._get_session()
        async with session.post(
            "https://osu.ppy.sh/oauth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
                "scope": "public",
            },
        ) as resp:
            data = await resp.json()
            self._token = data["access_token"]
            self._token_expiry = time.time() + data["expires_in"] - 60

    def _find_local_osu_by_md5(self, md5: str) -> Optional[bytes]:
        if not self.songs_dir or not self.songs_dir.exists():
            return None

        index = {}
        if self._index_path.exists():
            try:
                index = json.loads(self._index_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        if md5 in index:
            path = Path(index[md5])
            if path.exists():
                return path.read_bytes()

        index = _build_md5_index(self.songs_dir, self._index_path)
        if md5 in index:
            path = Path(index[md5])
            if path.exists():
                return path.read_bytes()

        return None

    def lookup_beatmap_local(self, md5: str) -> Optional[BeatmapMeta]:
        osu_bytes = self._find_local_osu_by_md5(md5)
        if osu_bytes is None:
            return None

        meta = _build_meta_from_osu(osu_bytes)
        if meta is None:
            return None

        try:
            import rosu_pp_py as rpp
            beatmap = rpp.Beatmap(bytes=osu_bytes)
            perf = rpp.Performance(mods=0)
            attrs = perf.calculate(beatmap)
            meta.star_rating = attrs.difficulty.stars
        except Exception:
            meta.star_rating = 0.0

        return meta

    async def lookup_beatmap(self, md5: str) -> Optional[BeatmapMeta]:
        await self._ensure_token()
        session = await self._get_session()
        async with session.get(
            f"https://osu.ppy.sh/api/v2/beatmaps/lookup?checksum={md5}",
            headers={"Authorization": f"Bearer {self._token}"},
        ) as resp:
            if resp.status == 404:
                return await asyncio.to_thread(self.lookup_beatmap_local, md5)
            if resp.status != 200:
                text = await resp.text()
                raise ValueError(f"osu! API lookup failed ({resp.status}): {text}")
            raw = await resp.json()

        bmset = raw["beatmapset"]
        return BeatmapMeta(
            beatmap_id=raw["id"],
            beatmapset_id=raw["beatmapset_id"],
            artist=bmset["artist"],
            title=bmset["title"],
            difficulty=raw["version"],
            creator=bmset["creator"],
            bpm=raw["bpm"],
            cs=raw["cs"],
            ar=raw["ar"],
            od=raw["accuracy"],
            hp=raw["drain"],
            star_rating=raw["difficulty_rating"],
            length=raw["total_length"],
            bg_url=bmset["covers"]["card@2x"],
            cover_url=bmset["covers"]["cover@2x"],
            map_url=f"https://osu.ppy.sh/beatmapsets/{raw['beatmapset_id']}#osu/{raw['id']}",
            status=raw["status"],
        )

    async def download_beatmap_file(self, beatmap_id: int = 0, beatmapset_id: int = 0, md5: str = "") -> bytes:
        cache_name = f"{beatmap_id}.osu" if beatmap_id else f"{md5}.osu"
        cache_path = self.cache_dir / cache_name
        if cache_path.exists():
            return cache_path.read_bytes()

        if self.songs_dir is not None and self.songs_dir.exists():
            search_dirs = []
            if beatmapset_id:
                search_dirs = [d for d in self.songs_dir.iterdir() if d.is_dir() and d.name.startswith(f"{beatmapset_id} ")]
            if not search_dirs:
                search_dirs = [d for d in self.songs_dir.iterdir() if d.is_dir()]

            for d in search_dirs:
                for f in d.iterdir():
                    if f.suffix.lower() != ".osu":
                        continue
                    content = f.read_bytes()
                    if md5 and hashlib.md5(content).hexdigest() == md5:
                        cache_path.write_bytes(content)
                        return content
                    if beatmap_id and f"BeatmapID:{beatmap_id}" in content.decode("utf-8", errors="replace"):
                        cache_path.write_bytes(content)
                        return content

        raise ValueError(
            f".osu file for beatmap #{beatmap_id or md5} not found locally. "
            "Set 'songs_dir' in config.json to your osu! Songs folder."
        )

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
