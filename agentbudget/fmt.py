"""One place for the number formats both readouts use."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

DASH = "—"


def fmt_pct(value: Optional[float]) -> str:
    """Headline quota share: whole percent, halves rounded away from zero."""
    if value is None or isinstance(value, bool):
        return DASH
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return DASH
    whole = math.floor(abs(value) + 0.5)
    return f"{'-' if value < 0 else ''}{whole:.0f}%"


def fmt_pct_fine(value: Optional[float]) -> str:
    """Today's share of a pool, where a whole percent would erase the figure."""
    if value is None or not math.isfinite(value):
        return DASH
    return f"{value:.2f}%"


def fmt_usd(cents: Optional[float]) -> str:
    if cents is None or not math.isfinite(cents):
        return DASH
    return f"${cents / 100:,.2f}"


def fmt_when(value: Optional[str]) -> str:
    """Local month/day + clock time for a billing instant."""
    if not value:
        return DASH
    try:
        raw = str(value).strip()
        if raw.isdigit():
            ms = int(raw)
            if ms > 10_000_000_000:
                ms /= 1000.0
            dt = datetime.fromtimestamp(ms).astimezone()
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone()
        return f"{dt.month}/{dt.day} {dt.hour:02d}:{dt.minute:02d}"
    except (ValueError, TypeError, OSError, OverflowError):
        return str(value)[:16]
