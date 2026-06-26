"""Rate-limited wrapper around an authenticated BreezeConnect: code resolution
and the historical-data helpers this bot needs (future, option, equity/VIX).

Auth lives in the shared `auth` package; this client takes the already-
authenticated breeze object. Copied from IV-Delta-BackFill and extended with
`future_minute`; the option/equity fetches are unchanged.
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import date, timedelta

from config import Config
from entities.enums import Right


class RateLimitError(RuntimeError):
    """Raised when we hit the configured daily call cap (stop & resume later)."""


class BreezeClient:
    def __init__(self, breeze, cfg=Config):
        self.breeze = breeze
        self._cfg = cfg
        self._call_times: deque[float] = deque()
        self._daily_calls = 0
        self._last_call = 0.0
        self._code_cache: dict[str, str] = self._load_code_cache()

    # -- rate limiting -----------------------------------------------------
    def _throttle(self) -> None:
        cfg = self._cfg
        if self._daily_calls >= cfg.DAILY_CALL_CAP:
            raise RateLimitError(
                f"Hit daily call cap ({cfg.DAILY_CALL_CAP}). Re-run later to resume."
            )
        gap = time.time() - self._last_call
        if gap < cfg.MIN_SECONDS_BETWEEN_CALLS:
            time.sleep(cfg.MIN_SECONDS_BETWEEN_CALLS - gap)

        now = time.time()
        while self._call_times and now - self._call_times[0] > cfg.RATE_WINDOW_SECONDS:
            self._call_times.popleft()
        if len(self._call_times) >= cfg.MAX_CALLS_PER_MIN:
            sleep_for = cfg.RATE_WINDOW_SECONDS - (now - self._call_times[0]) + cfg.RATE_SLEEP_BUFFER
            if sleep_for > 0:
                time.sleep(sleep_for)

        self._call_times.append(time.time())
        self._last_call = time.time()
        self._daily_calls += 1

    @property
    def calls_made(self) -> int:
        return self._daily_calls

    # -- stock-code resolution --------------------------------------------
    def _load_code_cache(self) -> dict[str, str]:
        if os.path.exists(self._cfg.STOCKCODE_CACHE):
            try:
                with open(self._cfg.STOCKCODE_CACHE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_code_cache(self) -> None:
        with open(self._cfg.STOCKCODE_CACHE, "w") as f:
            json.dump(self._code_cache, f, indent=2)

    def resolve_code(self, nse_symbol: str) -> str:
        """NSE symbol -> ICICI ISEC short code (required by Breeze calls)."""
        if nse_symbol in self._cfg.STOCK_CODE_OVERRIDES:
            return self._cfg.STOCK_CODE_OVERRIDES[nse_symbol]
        if nse_symbol in self._code_cache:
            return self._code_cache[nse_symbol]

        self._throttle()
        resp = self.breeze.get_names(
            exchange_code=self._cfg.EXCHANGE_EQUITY, stock_code=nse_symbol
        )
        code = None
        if isinstance(resp, dict):
            for key in self._cfg.CODE_LOOKUP_KEYS:
                if resp.get(key):
                    code = resp[key]
                    break
        if not code:
            raise RuntimeError(
                f"Could not resolve ISEC code for {nse_symbol!r}: {resp!r}. "
                f"Add it to STOCK_CODE_OVERRIDES in config.py."
            )
        self._code_cache[nse_symbol] = code
        self._save_code_cache()
        return code

    # -- historical data (chunked to respect the per-call record cap) ------
    def _range_window(self, start: date, end: date) -> tuple[str, str]:
        """ISO from/to spanning the FULL calendar days [start, end], both inclusive,
        so no bar is dropped at the edges. Session filtering happens downstream in
        ohlc_by_date, not here."""
        s = self._cfg.ISO_TIME_SUFFIX
        return f"{start:%Y-%m-%d}T00:00:00{s}", f"{end:%Y-%m-%d}T23:59:59{s}"

    def _iso_expiry(self, expiry: date) -> str:
        return f"{expiry:%Y-%m-%d}T{self._cfg.EXPIRY_ISO_TIME}{self._cfg.ISO_TIME_SUFFIX}"

    def _max_days_per_call(self) -> int:
        """Calendar-day span that keeps one response under MAX_RECORDS_PER_CALL for
        the chosen interval. Uses trading-day bar counts, so it is conservative."""
        per_day = self._cfg.CANDLES_PER_DAY.get(self._cfg.CANDLE_INTERVAL)
        if not per_day:
            raise ValueError(
                f"Unsupported CANDLE_INTERVAL {self._cfg.CANDLE_INTERVAL!r}; "
                f"use one of {list(self._cfg.CANDLES_PER_DAY)}"
            )
        return max(1, self._cfg.MAX_RECORDS_PER_CALL // per_day)

    def _chunks(self, start: date, end: date):
        span = timedelta(days=self._max_days_per_call())
        a = start
        while a <= end:
            b = min(a + span - timedelta(days=1), end)
            yield a, b
            a = b + timedelta(days=1)

    def _history(self, isec_code: str, start: date, end: date, *, exchange: str,
                 product: str, expiry: date | None = None, right=None,
                 strike: float | None = None) -> list[dict]:
        """Candles over [start, end] for one instrument, fetched in chunks small
        enough to stay under the per-call cap, then concatenated."""
        candles: list[dict] = []
        for a, b in self._chunks(start, end):
            frm, to = self._range_window(a, b)
            params = dict(
                interval=self._cfg.CANDLE_INTERVAL, from_date=frm, to_date=to,
                stock_code=isec_code, exchange_code=exchange, product_type=product,
            )
            if expiry is not None:
                params["expiry_date"] = self._iso_expiry(expiry)
            if right is not None:
                params["right"] = right.breeze_value
            if strike is not None:
                params["strike_price"] = _fmt_strike(strike)
            self._throttle()
            resp = self.breeze.get_historical_data_v2(**params)
            candles.extend(resp.get("Success") or [])
        return candles

    def equity_range(self, isec_code: str, start: date, end: date) -> list[dict]:
        """Cash candles over [start, end] (used for India VIX)."""
        return self._history(isec_code, start, end,
                             exchange=self._cfg.EXCHANGE_EQUITY, product=self._cfg.PRODUCT_EQUITY)

    def future_range(self, isec_code: str, start: date, end: date, expiry: date) -> list[dict]:
        """Futures candles over [start, end] for one monthly contract."""
        return self._history(isec_code, start, end, expiry=expiry,
                             exchange=self._cfg.EXCHANGE_FUTURES, product=self._cfg.PRODUCT_FUTURES)

    def option_range(self, isec_code: str, start: date, end: date, expiry: date,
                     right: Right, strike: float) -> list[dict]:
        """Option candles over [start, end] for one strike & monthly contract."""
        return self._history(isec_code, start, end, expiry=expiry, right=right, strike=strike,
                             exchange=self._cfg.EXCHANGE_OPTIONS, product=self._cfg.PRODUCT_OPTIONS)


def _fmt_strike(strike: float) -> str:
    """Render strike without a trailing .0 for whole numbers (e.g. 1600 not 1600.0),
    but keep half-steps like 267.5."""
    return str(int(strike)) if float(strike).is_integer() else str(strike)
