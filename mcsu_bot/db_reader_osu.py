import shutil
import struct
import tempfile
from pathlib import Path

from .models import OsuScore

TICKS_AT_UNIX_EPOCH = 621355968000000000
TICKS_PER_SECOND = 10000000


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


def _read_byte(data: bytes, offset: int) -> tuple[int, int]:
    return data[offset], offset + 1


def _read_db(db_path: Path) -> bytes:
    """Read scores.db directly. Uses copy as fallback if direct read fails."""
    try:
        with open(db_path, "rb") as f:
            return f.read()
    except PermissionError:
        pass
    # Fallback: copy via temp file (locked by osu!)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
        shutil.copy2(str(db_path), tmp_path)
    try:
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _ticks_to_unix(ticks: int) -> int:
    return int((ticks - TICKS_AT_UNIX_EPOCH) / TICKS_PER_SECOND)


def _try_read_string(data: bytes, offset: int, label: str = "") -> tuple[str | None, int]:
    """Read osu string with diagnostic info on failure."""
    try:
        return _read_osu_string(data, offset)
    except ValueError as e:
        ctx = data[max(0, offset - 8):offset + 16]
        raise ValueError(
            f"{e} at offset {offset} ({label}). "
            f"Context: {ctx.hex(' ')}"
        ) from None


def _skip_mod_info(data: bytes, offset: int, mods: int) -> int:
    """Advance past optional Target Practice double."""
    if mods & (1 << 23):
        offset += 8
    return offset


MIN_OSU_VERSION = 20150204


def _check_header(data: bytes, path: Path):
    """Validate that the file looks like a real osu! stable scores.db."""
    if len(data) < 8:
        raise ValueError(
            f"File too small ({len(data)} bytes) — not a valid scores.db"
        )
    version, _ = _read_int(data, 0)
    if version < MIN_OSU_VERSION or version > 21000101:
        raise ValueError(
            f"Unrecognized scores.db version {version} — "
            f"expected between {MIN_OSU_VERSION} and 21000101. "
            f"The file at '{path}' may be from McOsu or another source."
        )


def read_all_scores_osu(db_path: Path, gamemode: int = 0) -> list[OsuScore]:
    """Parse osu! stable scores.db.

    Format documented at:
    https://github.com/ppy/osu/wiki/Legacy-database-file-structure#scoresdb
    """
    data = _read_db(db_path)
    _check_header(data, db_path)
    offset = 0
    version, offset = _read_int(data, offset)
    num_beatmaps, offset = _read_int(data, offset)

    scores: list[OsuScore] = []

    try:
        for _ in range(num_beatmaps):
            if offset >= len(data):
                break
            md5, offset = _try_read_string(data, offset, "beatmap md5 hash")
            if md5 is None or len(md5) < 32:
                break
            num_scores, offset = _read_int(data, offset)
            for _ in range(num_scores):
                if offset >= len(data):
                    break
                mode, offset = _read_byte(data, offset)
                offset += 4  # skip score/replay version (Int)

                if mode != gamemode:
                    bm_md5, offset = _try_read_string(data, offset, "skip bm md5")
                    _, offset = _try_read_string(data, offset, "skip player")
                    _, offset = _try_read_string(data, offset, "skip replay md5")
                    offset += 6 * 2
                    offset += 4
                    offset += 2
                    offset += 1
                    mods, offset = _read_int(data, offset)
                    _, offset = _try_read_string(data, offset, "skip lifebar")
                    offset += 8
                    offset += 4
                    offset += 8
                    offset = _skip_mod_info(data, offset, mods)
                    continue

                bm_md5, offset = _try_read_string(data, offset, "score bm md5")
                player_name, offset = _try_read_string(data, offset, "score player")
                _, offset = _try_read_string(data, offset, "score replay md5")

                num300s, offset = _read_short(data, offset)
                num100s, offset = _read_short(data, offset)
                num50s, offset = _read_short(data, offset)
                num_gekis, offset = _read_short(data, offset)
                num_katus, offset = _read_short(data, offset)
                num_misses, offset = _read_short(data, offset)

                score_val, offset = _read_int(data, offset)
                max_combo, offset = _read_short(data, offset)
                perfect_byte, offset = data[offset], offset + 1
                perfect = perfect_byte != 0

                mods, offset = _read_int(data, offset)

                _, offset = _try_read_string(data, offset, "score lifebar")

                timestamp_ticks, offset = _read_long(data, offset)

                _, offset = _read_int(data, offset)

                _, offset = _read_long(data, offset)

                offset = _skip_mod_info(data, offset, mods)

                timestamp = _ticks_to_unix(timestamp_ticks)

                score_obj = OsuScore(
                    beatmap_md5=bm_md5 or md5,
                    score=score_val,
                    max_combo=max_combo,
                    count300=num300s,
                    count100=num100s,
                    count50=num50s,
                    count_miss=num_misses,
                    count_geki=num_gekis,
                    count_katu=num_katus,
                    mods=mods,
                    perfect=perfect,
                    timestamp=timestamp,
                    player_name=player_name or "",
                    pp=0.0,
                    max_possible_combo=0,
                    num_slider_breaks=0,
                    num_hit_objects=0,
                    stars_aim=0.0,
                    stars_speed=0.0,
                )
                scores.append(score_obj)
    except Exception as e:
        ctx_start = max(0, offset - 16)
        ctx_end = min(len(data), offset + 32)
        header_hex = data[:8].hex(" ")
        first_md5_marker = data[8:9].hex() if len(data) > 8 else "?"
        raise ValueError(
            f"Header: version={version}, num_beatmaps={num_beatmaps}, "
            f"file_size={len(data)}\n"
            f"Raw header: {header_hex} | first md5 marker: {first_md5_marker}\n"
            f"Offset {offset} context: {data[ctx_start:ctx_end].hex(' ')}\n"
            f"Error: {e}"
        ) from None

    return scores


def read_latest_score_osu(db_path: Path, gamemode: int = 0) -> OsuScore:
    """Read most recent score from osu! stable scores.db."""
    all_scores = read_all_scores_osu(db_path, gamemode)
    if not all_scores:
        raise ValueError("No scores found in osu! scores.db")
    return max(all_scores, key=lambda s: s.timestamp)
