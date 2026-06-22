"""Rate-limited wrapper around an authenticated BreezeConnect: code resolution
and the historical-data helpers this bot needs.

Auth lives in LoginService; this client takes the already-authenticated breeze
object (mirroring how HFAlgoBot's OrderService takes an authenticated kite).
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import date

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

    # -- historical data ---------------------------------------------------
    def _day_window(self, d: date) -> tuple[str, str]:
        ds = d.strftime("%Y-%m-%d")
        cfg = self._cfg
        frm = f"{ds}T{cfg.HIST_WINDOW_START}{cfg.ISO_TIME_SUFFIX}"
        to = f"{ds}T{cfg.HIST_WINDOW_END}{cfg.ISO_TIME_SUFFIX}"
        return frm, to

    def _iso_expiry(self, expiry: date) -> str:
        return f"{expiry:%Y-%m-%d}T{self._cfg.EXPIRY_ISO_TIME}{self._cfg.ISO_TIME_SUFFIX}"

    def equity_minute(self, isec_code: str, d: date) -> list[dict]:
        """1-minute cash candles for the whole day."""
        frm, to = self._day_window(d)
        self._throttle()
        resp = self.breeze.get_historical_data_v2(
            interval=self._cfg.CANDLE_INTERVAL,
            from_date=frm,
            to_date=to,
            stock_code=isec_code,
            exchange_code=self._cfg.EXCHANGE_EQUITY,
            product_type=self._cfg.PRODUCT_EQUITY,
        )
        return resp.get("Success") or []

    def option_minute(
        self, isec_code: str, d: date, expiry: date, right: Right, strike: float
    ) -> list[dict]:
        """1-minute option candles for the whole day for one strike."""
        frm, to = self._day_window(d)
        self._throttle()
        resp = self.breeze.get_historical_data_v2(
            interval=self._cfg.CANDLE_INTERVAL,
            from_date=frm,
            to_date=to,
            stock_code=isec_code,
            exchange_code=self._cfg.EXCHANGE_OPTIONS,
            product_type=self._cfg.PRODUCT_OPTIONS,
            expiry_date=self._iso_expiry(expiry),
            right=right.breeze_value,
            strike_price=_fmt_strike(strike),
        )
        return resp.get("Success") or []


def _fmt_strike(strike: float) -> str:
    """Render strike without a trailing .0 for whole numbers (e.g. 1600 not 1600.0),
    but keep half-steps like 267.5."""
    return str(int(strike)) if float(strike).is_integer() else str(strike)
