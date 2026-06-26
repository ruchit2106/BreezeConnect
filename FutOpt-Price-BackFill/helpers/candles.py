"""Helpers for reducing Breeze candle lists (daily or intraday) to daily OHLC."""

from __future__ import annotations


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _date_of(dt) -> str:
    """Breeze candle datetime -> 'YYYY-MM-DD' (handles 'T' and space forms)."""
    return str(dt).replace("T", " ").split(" ")[0]


def _time_of(dt) -> str:
    """Breeze candle datetime -> 'HH:MM:SS' (a daily bar has no time -> 00:00:00)."""
    parts = str(dt).replace("T", " ").split(" ")
    return parts[1] if len(parts) > 1 else "00:00:00"


def ohlc_by_date(candles: list[dict], lo: str | None = None, hi: str | None = None) -> dict[str, tuple]:
    """Reduce candles to {date: (open, high, low, close)}.

    Intraday intervals: pass the session window lo/hi as 'HH:MM:SS' — only bars
    whose time is in [lo, hi] count; the day's open is the first such bar's open,
    the close is the last such bar's close, and high/low span that window.
    Daily ('1day') interval: pass lo=hi=None — one bar per day, time ignored.
    """
    grouped: dict[str, list[dict]] = {}
    for c in sorted(candles, key=lambda x: str(x.get("datetime", ""))):
        dt = c.get("datetime")
        if not dt:
            continue
        if lo is not None and not (lo <= _time_of(dt) <= hi):
            continue
        grouped.setdefault(_date_of(dt), []).append(c)

    out: dict[str, tuple] = {}
    for ds, bars in grouped.items():
        highs = [h for h in (_num(b.get("high")) for b in bars) if h is not None]
        lows = [low for low in (_num(b.get("low")) for b in bars) if low is not None]
        out[ds] = (
            _num(bars[0].get("open")),
            max(highs) if highs else None,
            min(lows) if lows else None,
            _num(bars[-1].get("close")),
        )
    return out
