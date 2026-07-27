import shutil
import struct
import tempfile
from pathlib import Path
from .models import OsuScore


def _read_uleb128(data: bytes, offset: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            break
    return result, offset


def _read_osu_string(data: bytes, offset: int) -> tuple[str | None, int]:
    marker = data[offset]
    offset += 1
    if marker == 0x00:
        return None, offset
    if marker != 0x0B:
        raise ValueError(f"Unknown osu string marker: {marker:#04x}")
    length, offset = _read_uleb128(data, offset)
    if length == 0:
        return "", offset
    raw = data[offset:offset + length]
    return raw.decode("utf-8", errors="replace"), offset + length


def _read_int(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from("<i", data, offset)[0], offset + 4


def _read_short(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from("<h", data, offset)[0], offset + 2


def _read_long(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from("<q", data, offset)[0], offset + 8


def _read_float(data: bytes, offset: int) -> tuple[float, int]:
    return struct.unpack_from("<f", data, offset)[0], offset + 4


def _read_byte(data: bytes, offset: int) -> tuple[int, int]:
    return data[offset], offset + 1


def _copy_db(db_path: Path) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
        shutil.copy2(str(db_path), tmp_path)
    try:
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _parse_score(
    data: bytes, offset: int, md5: str, version: int, score_version: int
) -> tuple[OsuScore, int]:
    gamemode, offset = _read_byte(data, offset)
    unix_timestamp, offset = _read_long(data, offset)
    player_name, offset = _read_osu_string(data, offset)

    num300s, offset = _read_short(data, offset)
    num100s, offset = _read_short(data, offset)
    num50s, offset = _read_short(data, offset)
    num_gekis, offset = _read_short(data, offset)
    num_katus, offset = _read_short(data, offset)
    num_misses, offset = _read_short(data, offset)

    score_val, offset = _read_long(data, offset)
    max_combo, offset = _read_short(data, offset)
    mods_legacy, offset = _read_int(data, offset)

    num_slider_breaks, offset = _read_short(data, offset)
    pp, offset = _read_float(data, offset)
    _unstable_rate, offset = _read_float(data, offset)
    _hit_error_min, offset = _read_float(data, offset)
    _hit_error_max, offset = _read_float(data, offset)
    _stars_total, offset = _read_float(data, offset)
    stars_aim, offset = _read_float(data, offset)
    stars_speed, offset = _read_float(data, offset)
    _speed_mult, offset = _read_float(data, offset)
    _cs, offset = _read_float(data, offset)
    _ar, offset = _read_float(data, offset)
    _od, offset = _read_float(data, offset)
    _hp, offset = _read_float(data, offset)

    max_possible_combo = 0
    num_hit_objects = 0
    if score_version > 20180722:
        max_possible_combo, offset = _read_int(data, offset)
        num_hit_objects, offset = _read_int(data, offset)
        _num_circles, offset = _read_int(data, offset)

    _experimental_mods, offset = _read_osu_string(data, offset)

    if gamemode != 0x00 and not (version > 20210103 and score_version > 20190103):
        return None, offset

    perfect = (max_possible_combo > 0 and max_combo > 0 and max_combo >= max_possible_combo)

    score = OsuScore(
        beatmap_md5=md5,
        score=score_val,
        max_combo=max_combo,
        count300=num300s,
        count100=num100s,
        count50=num50s,
        count_miss=num_misses,
        count_geki=num_gekis,
        count_katu=num_katus,
        mods=mods_legacy,
        perfect=perfect,
        timestamp=unix_timestamp,
        player_name=player_name or "",
        pp=pp,
        max_possible_combo=max_possible_combo,
        num_slider_breaks=num_slider_breaks,
        num_hit_objects=num_hit_objects,
        stars_aim=stars_aim,
        stars_speed=stars_speed,
    )
    return score, offset


def read_all_scores(db_path: Path) -> list[OsuScore]:
    data = _copy_db(db_path)
    offset = 0
    version, offset = _read_int(data, offset)
    num_beatmaps, offset = _read_int(data, offset)

    scores: list[OsuScore] = []

    for _ in range(num_beatmaps):
        if offset >= len(data):
            break
        md5, offset = _read_osu_string(data, offset)
        if md5 is None or len(md5) < 32:
            break
        num_scores, offset = _read_int(data, offset)
        for _ in range(num_scores):
            if offset >= len(data):
                break
            score_version, offset = _read_int(data, offset)
            result, offset = _parse_score(data, offset, md5, version, score_version)
            if result is not None:
                scores.append(result)

    return scores


def read_latest_score(db_path: Path) -> OsuScore:
    all_scores = read_all_scores(db_path)
    if not all_scores:
        raise ValueError("No scores found in scores.db")
    return max(all_scores, key=lambda s: s.timestamp)
