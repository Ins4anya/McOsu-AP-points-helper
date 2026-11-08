"""Pure presentation helpers for the Ranked tab.

No NiceGUI imports here on purpose: everything in this module is a pure
function of the server response, so it can be unit-tested without a display.
The tab itself only paints what these helpers return.
"""
from __future__ import annotations

from typing import Any, Optional

# --------------------------------------------------------------------------- #
# Palette (single source of truth for the tab)
# --------------------------------------------------------------------------- #

PAGE_BG = "#0f1224"
CARD_BG = "#171a33"
CARD_BORDER = "#262a4a"
INSET_BG = "#1d2142"
TRACK_BG = "#1f2347"

TEXT = "#e6e8f5"
MUTED = "#a3a9cf"
ACCENT = "#5aa0e6"
POSITIVE = "#4ade80"
NEGATIVE = "#f87171"
ZERO = MUTED

TIER_COLORS = {
    "Базовый": "#a3a9cf",
    "Бронза": "#cd7f32",
    "Серебро": "#cbd5e1",
    "Золото": "#fbbf24",
    "Платина": "#5eead4",
    "Алмаз": "#7dd3fc",
    "Мастер": "#c084fc",
    "Профессионал": "#f87171",
    "Легенда": "#fbcfe8",
}

# Shape identity per tier (the app draws inline SVG; the site mirrors this).
TIER_SHAPES = {
    "Базовый": "triangle",
    "Бронза": "triangle",
    "Серебро": "square",
    "Золото": "square",
    "Платина": "diamond",
    "Алмаз": "gem",
    "Мастер": "star",
    "Профессионал": "star",
    "Легенда": "circle",
}

FALLBACK_SHAPE = "square"
SHAPE_FILL_EMPTY = "#1f2347"
SHAPE_STROKE_EMPTY = "#3a4070"

SHAPE_MARKUP = {
    "triangle": '<path d="M8 2l7 12H1z"/>',
    "square": '<rect x="2" y="2" width="12" height="12" rx="3"/>',
    "diamond": '<path d="M8 1l7 7-7 7-7-7z"/>',
    "gem": '<path d="M4 2h8l3 4-7 8-7-8z"/>',
    "star": (
        '<path d="M8 1.2l2.1 4.4 4.8.6-3.5 3.3.9 4.8L8 12'
        'l-4.3 2.3.9-4.8L1.1 6.2l4.8-.6z"/>'
    ),
    "circle": '<circle cx="8" cy="8" r="6.5"/>',
}

PLACE_COLORS = {
    1: TIER_COLORS["Золото"],
    2: TIER_COLORS["Серебро"],
    3: TIER_COLORS["Бронза"],
}

STATUS_LABELS = {
    "passed": "Пройдено",
    "failed": "Фейл",
    "surrendered": "Сдача",
    "expired": "Таймаут",
    "rerolled": "Реролл",
    "active": "Активное задание",
}


# --------------------------------------------------------------------------- #
# Small formatting helpers
# --------------------------------------------------------------------------- #


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def tier_color(name: Optional[str]) -> str:
    """Colour for a tier; unknown names fall back to the muted token."""
    return TIER_COLORS.get(str(name or ""), MUTED)


def tier_shape(name: Optional[str]) -> str:
    """Shape key for a tier; unknown names fall back to a square."""
    return TIER_SHAPES.get(str(name or ""), FALLBACK_SHAPE)


def shape_states(tier: Optional[str], sub: Any) -> list[bool]:
    """Boolean fill states for the tier figures.

    Normal tiers use the server's ``sub_rank`` (4 steps by default). When
    ``sub_rank`` is null (Базовый/Легенда) the client draws exactly one filled
    marker of the tier's shape, with no empty figures.
    """
    filled, total = sub_rank_segments(sub)
    if total <= 0:
        return [True] if tier else []
    return [index < filled for index in range(total)]


def tier_shape_svg(tier: Optional[str], filled: bool = True, size: int = 20) -> str:
    """Inline SVG for one tier figure (viewBox 16×16, filled or empty)."""
    shape = tier_shape(tier)
    color = tier_color(tier)
    fill = color if filled else SHAPE_FILL_EMPTY
    stroke = color if filled else SHAPE_STROKE_EMPTY
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(size)}" '
        f'height="{int(size)}" viewBox="0 0 16 16" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1" stroke-linejoin="round">'
        f"{SHAPE_MARKUP[shape]}</svg>"
    )


def place_color(place: Any) -> str:
    """Gold/silver/bronze for places 1-3, muted otherwise."""
    try:
        number = int(place)
    except (TypeError, ValueError):
        return MUTED
    return PLACE_COLORS.get(number, MUTED)


def sub_rank_segments(sub: Any) -> tuple[int, int]:
    """Return ``(filled, total)`` for the sub-rank figures, clamped and safe.

    ``None`` (no indicator) gives ``(0, 0)``; the caller then draws a single
    filled marker (Базовый/Легенда) instead of an empty set.
    """
    if not isinstance(sub, dict):
        return 0, 0
    try:
        total = max(0, int(sub.get("total") or 0))
        filled = int(sub.get("filled") or 0)
    except (TypeError, ValueError):
        return 0, 0
    return max(0, min(total, filled)), total


def format_delta(value: Any) -> str:
    """Signed ELO/reward delta with a real minus sign: +60, 0, −15."""
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = 0
    if number > 0:
        return f"+{number}"
    if number < 0:
        return "−" + str(abs(number))
    return "0"


def delta_color(value: Any) -> str:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = 0
    if number > 0:
        return POSITIVE
    if number < 0:
        return NEGATIVE
    return ZERO


def format_accuracy(accuracy: Any) -> str:
    """Accuracy (stored as 0..1) for a history row; em dash when absent."""
    if accuracy is None:
        return "—"
    try:
        return f"{float(accuracy) * 100:.2f}%"
    except (TypeError, ValueError):
        return "—"


def format_reward_accuracy(accuracy: Any) -> str:
    """Reward-table breakpoint (0..1) as a short percentage: 70%, 90%, 100%."""
    try:
        return f"{float(accuracy) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def format_stars(stars: Any) -> str:
    if stars is None:
        return "—"
    try:
        return f"★{float(stars):.2f}"
    except (TypeError, ValueError):
        return "—"


def window_text(star_window: Any) -> str:
    """'6.24–6.54★' from the server's star_window object, or ''."""
    if not isinstance(star_window, dict):
        return ""
    low = star_window.get("min")
    high = star_window.get("max")
    if low is None or high is None:
        return ""
    try:
        return f"{float(low):.2f}–{float(high):.2f}★"
    except (TypeError, ValueError):
        return ""


def star_range_text(star_range: Any) -> str:
    """Legacy tier outer bounds, used only as a fallback for the window text."""
    if not isinstance(star_range, dict):
        return ""
    low = star_range.get("min")
    high = star_range.get("max")
    if low is None:
        return ""
    try:
        if high is None:
            return f"{float(low):.2f}+★"
        return f"{float(low):.2f}–{float(high):.2f}★"
    except (TypeError, ValueError):
        return ""


def progress_detail(progress: Any) -> str:
    """Right-hand side of the progress line (no tier name, no ellipsis)."""
    if not isinstance(progress, dict):
        return ""
    next_tier = progress.get("next_tier")
    if not next_tier:
        return "максимальное звание"
    points = progress.get("points", 0)
    span = progress.get("span", 0)
    percent = progress.get("percent", 0)
    return f"{points} / {span} до «{next_tier}» · {percent}%"


def wld_values(payload: Any) -> dict:
    """Normalise the server's W/L/D counters for the rank card.

    Uses ``wins``/``losses``/``draws``/``win_rate`` from
    ``GET /api/ranked/stats``. When those keys are absent (older server or a
    plain ``/api/ranked`` response), falls back to ``passed``/``failed`` with
    zero draws, exactly like the Discord ``!rank`` embed.
    """
    data = payload if isinstance(payload, dict) else {}

    wins = data.get("wins")
    losses = data.get("losses")
    draws = data.get("draws")
    if wins is None or losses is None or draws is None:
        wins = data.get("passed", 0)
        losses = data.get("failed", 0)
        draws = 0

    def _int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    wins, losses, draws = _int(wins), _int(losses), _int(draws)
    games = wins + losses + draws

    raw_rate = data.get("win_rate")
    if raw_rate is None:
        rate = wins / games if games > 0 else 0.0
    else:
        try:
            rate = float(raw_rate)
        except (TypeError, ValueError):
            rate = wins / games if games > 0 else 0.0
    if games <= 0:
        rate = 0.0

    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "games": games,
        "win_rate": rate,
    }


def pretty_title(title: Any) -> str:
    """Use an em dash in 'artist - title [diff]' without touching the data."""
    text = str(title or "")
    return text.replace(" - ", " — ", 1)


def is_me_row(row: Any, username: Optional[str]) -> bool:
    """Match the leaderboard row to the configured local username."""
    if not isinstance(row, dict):
        return False
    wanted = str(username or "").strip().casefold()
    if not wanted:
        return False
    return str(row.get("username") or "").strip().casefold() == wanted


# --------------------------------------------------------------------------- #
# Window scale geometry
# --------------------------------------------------------------------------- #


def window_geometry(
    star_window: Any,
    span_min: Any,
    span_max: Any,
) -> Optional[dict]:
    """Percent geometry for the tier-range scale and the current window.

    Returns ``{"left": %, "width": %, "marker": %}`` relative to the tier's
    outer range ``[span_min, span_max)``. The window may cross a tier border
    (by design), so both ends are clamped to the scale; the marker is clamped
    too. Returns ``None`` when the scale makes no sense (open-ended
    Легенда, missing values, zero span).
    """
    if span_min is None or span_max is None:
        return None
    if not isinstance(star_window, dict):
        return None
    low = star_window.get("min")
    high = star_window.get("max")
    if low is None or high is None:
        return None
    try:
        span_low = float(span_min)
        span_high = float(span_max)
        win_low = float(low)
        win_high = float(high)
        target = star_window.get("target")
        marker_value = float(target) if target is not None else (win_low + win_high) / 2.0
    except (TypeError, ValueError):
        return None
    span = span_high - span_low
    if span <= 0:
        return None

    if win_high < win_low:
        win_low, win_high = win_high, win_low

    left = clamp((win_low - span_low) / span * 100.0)
    right = clamp((win_high - span_low) / span * 100.0)
    return {
        "left": left,
        "width": max(0.0, right - left),
        "marker": clamp((marker_value - span_low) / span * 100.0),
    }


# --------------------------------------------------------------------------- #
# History outcome icon / tooltip
# --------------------------------------------------------------------------- #


def outcome_icon(status: Any, delta: Any) -> dict:
    """Icon, colour and Russian tooltip for a history row's outcome."""
    key = str(status or "").strip().lower()
    try:
        number = int(delta or 0)
    except (TypeError, ValueError):
        number = 0

    if key == "passed":
        if number > 0:
            return {"icon": "check", "color": POSITIVE, "tooltip": "Пройдено"}
        if number < 0:
            return {
                "icon": "check",
                "color": NEGATIVE,
                "tooltip": "Пройдено, но ELO снизилось",
            }
        return {
            "icon": "remove",
            "color": MUTED,
            "tooltip": "Пройдено без изменения ELO",
        }
    if key == "failed":
        return {"icon": "close", "color": NEGATIVE, "tooltip": "Фейл"}
    if key == "surrendered":
        return {"icon": "close", "color": NEGATIVE, "tooltip": "Сдача"}
    if key == "expired":
        return {"icon": "close", "color": NEGATIVE, "tooltip": "Таймаут"}
    if key == "rerolled":
        return {"icon": "refresh", "color": MUTED, "tooltip": "Реролл"}
    if key == "active":
        return {"icon": "schedule", "color": ACCENT, "tooltip": "Активное задание"}
    return {
        "icon": "help_outline",
        "color": MUTED,
        "tooltip": STATUS_LABELS.get(key, str(status or "—")),
    }
