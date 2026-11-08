from pathlib import Path

HEADER_BYTES = 16 * 1024


def _read_metadata_ids(path: Path) -> tuple[int, int]:
    with open(path, "rb") as f:
        head = f.read(HEADER_BYTES).decode("utf-8", errors="replace")

    beatmap_id = 0
    beatmapset_id = 0
    in_metadata = False
    for raw in head.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("[") and line.endswith("]"):
            if in_metadata:
                break
            in_metadata = line == "[Metadata]"
            continue
        if not in_metadata or ":" not in line:
            continue
        key, _, val = line.partition(":")
        if key == "BeatmapID":
            beatmap_id = _to_int(val)
        elif key == "BeatmapSetID":
            beatmapset_id = _to_int(val)
    return beatmap_id, beatmapset_id


def _to_int(value: str) -> int:
    try:
        return int(value.strip())
    except ValueError:
        return 0


def scan_songs(songs_dir: Path) -> list[dict]:
    if not songs_dir or not songs_dir.is_dir():
        return []

    found: dict[int, int] = {}
    for folder in songs_dir.iterdir():
        if not folder.is_dir():
            continue
        for osu_file in folder.iterdir():
            if osu_file.suffix.lower() != ".osu":
                continue
            try:
                beatmap_id, beatmapset_id = _read_metadata_ids(osu_file)
            except OSError:
                continue
            if beatmap_id > 0:
                found[beatmap_id] = beatmapset_id

    return [
        {"beatmap_id": bid, "beatmapset_id": bsid} for bid, bsid in found.items()
    ]
