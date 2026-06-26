"""Monthly expiry calculation for NSE single-stock futures & options.

Same rule as IV-Delta-BackFill: the active monthly contract is the last
EXPIRY_WEEKDAY of the month, rolling forward once the trade day reaches expiry.
"""

from __future__ import annotations

from datetime import date, timedelta

from config import Config


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Last `weekday` (Mon=0..Sun=6) of the given month."""
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    d = nxt - timedelta(days=1)  # last day of month
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _adjust_for_holiday(d: date) -> date:
    """If expiry lands on a weekend/holiday, step back to the previous trading day."""
    while d.strftime("%Y-%m-%d") in Config.HOLIDAYS or d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def monthly_expiry_for(trade_day: date) -> date:
    """Active monthly expiry for a trade day: last EXPIRY_WEEKDAY of the month,
    rolling to next month once the trade day reaches expiry (ROLL_ON_EXPIRY_DAY)."""
    this_month = _adjust_for_holiday(
        _last_weekday_of_month(trade_day.year, trade_day.month, Config.EXPIRY_WEEKDAY)
    )
    rolled = trade_day >= this_month if Config.ROLL_ON_EXPIRY_DAY else trade_day > this_month
    if not rolled:
        return this_month

    y, m = (trade_day.year, trade_day.month + 1)
    if m == 13:
        y, m = y + 1, 1
    return _adjust_for_holiday(_last_weekday_of_month(y, m, Config.EXPIRY_WEEKDAY))
