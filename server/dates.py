from __future__ import annotations

from datetime import datetime, timezone


def today_str() -> str:
    """Current UTC date as ``YYYY-MM-DD``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def date_str(dt: datetime) -> str:
    """A datetime as a UTC ``YYYY-MM-DD`` string (naive datetimes are UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
