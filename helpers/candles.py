"""Helpers for working with Breeze 1-minute candle lists."""

from __future__ import annotations

from datetime import datetime

from config import Config


def _hms(dt_str: str) -> str:
    """'2025-12-15 09:30:00' -> '09:30:00'."""
    return dt_str.split(" ")[1] if " " in dt_str else dt_str


def select_close_at(candles: list[dict], target_hms: str) -> float | None:
    """Closing price of the candle at the target time, or the nearest candle
    at-or-before it within Config.TIME_TOLERANCE_MIN. None if nothing usable."""
    if not candles:
        return None
    target = datetime.strptime(target_hms, "%H:%M:%S").time()
    best = None
    best_gap = None
    for c in candles:
        t = c.get("datetime")
        close = c.get("close")
        if not t or close in (None, "", 0, "0"):
            continue
        try:
            ct = datetime.strptime(_hms(t), "%H:%M:%S").time()
        except ValueError:
            continue
        if ct == target:
            return float(close)
        if ct < target:
            gap = (
                datetime.combine(datetime.min, target)
                - datetime.combine(datetime.min, ct)
            ).total_seconds() / 60.0
            if gap <= Config.TIME_TOLERANCE_MIN and (best_gap is None or gap < best_gap):
                best, best_gap = float(close), gap
    return best
