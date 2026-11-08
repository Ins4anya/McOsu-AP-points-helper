"""Central osu! mods helpers shared across the client.

Single source of truth for the legacy mods bitmask, its string form and
the DT/NC/HT rate handling. Keeping it here (instead of copying the bitmap
into ``ap_calculator``, ``database``, ``osu_api`` and ``embed_builder``)
guarantees the AP calculator, the local scores database and the sync client
always agree on how mods are serialised — so ``score_key`` values stay
consistent between runs and between client and server.
"""
from typing import Optional

# Legacy osu! mods bitmask: bit index -> short name.
MODS_BITMAP: dict[int, str] = {
    1 << 0: "NF", 1 << 1: "EZ", 1 << 2: "TD", 1 << 3: "HD",
    1 << 4: "HR", 1 << 5: "SD", 1 << 6: "DT", 1 << 7: "RX",
    1 << 8: "HT", 1 << 9: "NC", 1 << 10: "FL", 1 << 11: "AU",
    1 << 12: "SO", 1 << 13: "AP", 1 << 14: "PF", 1 << 15: "4K",
    1 << 16: "5K", 1 << 17: "6K", 1 << 18: "7K", 1 << 19: "8K",
    1 << 20: "FI", 1 << 21: "RN", 1 << 22: "CN", 1 << 23: "TP",
    1 << 24: "9K", 1 << 25: "KC", 1 << 26: "1K", 1 << 27: "3K",
    1 << 28: "2K", 1 << 29: "V2", 1 << 30: "MR",
}

# Reverse lookup used to parse osu! API v2 mods arrays (e.g. ["HD", "DT"]).
MODS_STRING_TO_BIT: dict[str, int] = {name: bit for bit, name in MODS_BITMAP.items()}

# Commonly referenced bit masks.
EZ_BIT = 1 << 1
HD_BIT = 1 << 3
HR_BIT = 1 << 4
DT_BIT = 1 << 6
HT_BIT = 1 << 8
NC_BIT = 1 << 9
FL_BIT = 1 << 10


def has_mod(mods: int, bit: int) -> bool:
    return bool(mods & bit)


def expected_rate(mods: int) -> float:
    """Rate implied by DT/NC/HT mods (1.0 when none of them are set)."""
    if has_mod(mods, DT_BIT) or has_mod(mods, NC_BIT):
        return 1.5
    if has_mod(mods, HT_BIT):
        return 0.75
    return 1.0


def mods_strings_to_int(mods: list[str]) -> int:
    """Convert an osu! API v2 mods list (e.g. ["HD", "DT"]) to a bitmask."""
    bits = 0
    for m in mods:
        bit = MODS_STRING_TO_BIT.get(m)
        if bit is not None:
            bits |= bit
    return bits


def mods_to_string(mods: int, speed_mult: Optional[float] = None) -> str:
    """Canonical mods string: "NM", "+HDDT" or "+HDDT 1.25x".

    A custom rate tag is appended only when ``speed_mult`` differs from the
    rate implied by DT/NC/HT. This is the single serialisation used for
    display, database storage and ``score_key`` deduplication.
    """
    if mods == 0 and (speed_mult is None or abs(speed_mult - 1.0) < 0.005):
        return "NM"

    result = [name for bit, name in MODS_BITMAP.items() if mods & bit]
    if "NC" in result and "DT" in result:
        result.remove("DT")
    if "PF" in result and "SD" in result:
        result.remove("SD")

    tag = ""
    if speed_mult is not None and speed_mult > 0:
        if abs(speed_mult - expected_rate(mods)) >= 0.005:
            tag = f"{speed_mult:g}x"

    if not result and not tag:
        return "NM"
    if not result:
        return f"+{tag}"
    return "+" + "".join(result) + (f" {tag}" if tag else "")


def parse_mods_string(mods: str) -> int:
    """Inverse of :func:`mods_to_string`: parse "+HDDT 1.25x" back to bits.

    Ignores the leading "+" and any trailing rate tag; only the 2-letter mod
    codes are converted to the bitmask.
    """
    s = (mods or "").strip()
    if not s or s == "NM":
        return 0
    s = s.lstrip("+")
    head = s.split()[0] if s.split() else s
    bits = 0
    for i in range(0, len(head), 2):
        bit = MODS_STRING_TO_BIT.get(head[i:i + 2])
        if bit is not None:
            bits |= bit
    return bits
