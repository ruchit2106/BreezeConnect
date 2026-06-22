"""Find the strike whose delta is closest to the target, for a given snapshot.

For historical backfill we cannot pull a whole option chain, so we probe strikes
one-by-one (each probe = one full-day 1-min series, cached and reused for both the
open and close snapshots). Call delta decreases as strike rises; put |delta|
decreases as strike falls.

To spend as few API calls as possible we probe ATM first, use its implied vol to
*predict* the target-delta strike analytically (strike_for_delta), jump there, and
then walk strike-by-strike until the target is bracketed by two adjacent valid
strikes — one at-or-above the target |delta|, one below. The prediction only
chooses where to probe next; every delta that enters the final pick is computed
from that strike's real fetched premium, so a bad prediction costs extra probes,
never a different answer.
"""

from __future__ import annotations

import math
from datetime import datetime

from config import Config
from entities.enums import Right
from entities.option_pick import OptionPick
from helpers.black_scholes import iv_and_delta, strike_for_delta
from helpers.candles import select_close_at
from helpers.expiry import years_to_expiry


class StrikeSearcher:
    """Caches option series per (right, strike) for a single stock-day."""

    def __init__(self, client, isec_code: str, day, expiry) -> None:
        self.client = client
        self.isec = isec_code
        self.day = day
        self.expiry = expiry
        self._cache: dict[tuple[Right, float], list[dict]] = {}

    def _series(self, right: Right, strike: float) -> list[dict]:
        key = (right, strike)
        if key not in self._cache:
            self._cache[key] = self.client.option_minute(
                self.isec, self.day, self.expiry, right, strike
            )
        return self._cache[key]

    def _carry_rate(self, snapshot_dt: datetime, spot: float, step: float, t: float) -> float | None:
        """Effective carry r implied by the ATM call/put at this snapshot, via
        put-call parity: F = K + (C - P)*e^{r0*t}, then r = ln(F/spot)/t. This is the
        per-stock, per-snapshot forward the market itself prices off (carry and
        dividends baked in) — not a guessed constant. Returns None if either ATM leg
        is missing (caller falls back to Config.RISK_FREE_RATE). The ATM call/put are
        the search's own seed probes, so this adds no API calls."""
        if t <= 0:
            return None
        atm = round(spot / step) * step
        hms = snapshot_dt.strftime("%H:%M:%S")
        c = select_close_at(self._series(Right.CALL, atm), hms)
        p = select_close_at(self._series(Right.PUT, atm), hms)
        if c is None or p is None:
            return None
        fwd = atm + (c - p) * math.exp(Config.RISK_FREE_RATE * t)
        if fwd <= 0:
            return None
        return math.log(fwd / spot) / t

    def find(self, right: Right, snapshot_dt: datetime, spot: float, step: float) -> OptionPick | None:
        """Return the OptionPick closest to the (signed) target delta for one
        snapshot, or None if nothing solvable."""
        signed_target = right.sign * Config.TARGET_DELTA
        t_years = years_to_expiry(snapshot_dt, self.expiry)
        target_hms = snapshot_dt.strftime("%H:%M:%S")
        atm = round(spot / step) * step
        lo, hi = -Config.SCAN_ITM_STEPS, Config.SCAN_MAX_STEPS

        # Carry/forward implied by the market at this snapshot (per stock, per
        # snapshot); fall back to the constant only if the ATM pair is unavailable.
        r = self._carry_rate(snapshot_dt, spot, step, t_years)
        if r is None:
            r = Config.RISK_FREE_RATE

        # Index convention: strike(i) = atm + sign*i*step, so +i is always the
        # OTM direction for either right and |delta| decreases as i grows.
        probed: set[int] = set()
        candidates: dict[int, OptionPick] = {}

        def _probe(i: int) -> OptionPick | None:
            if i in probed:
                return candidates.get(i)
            probed.add(i)
            strike = round(atm + right.sign * i * step, Config.STRIKE_ROUND_DECIMALS)
            if strike <= 0:
                return None
            ltp = select_close_at(self._series(right, strike), target_hms)
            if ltp is None:
                return None
            iv, delta = iv_and_delta(
                right.flag, spot, strike, t_years, r, ltp
            )
            if iv is None or delta is None:
                return None
            candidates[i] = OptionPick(
                strike=strike, premium=round(ltp, Config.ROUND_PREMIUM), iv=iv, delta=delta
            )
            return candidates[i]

        def _next_index() -> int | None:
            """Next strike to probe, or None once the target is bracketed by
            adjacent valid strikes (or both scan bounds are exhausted)."""
            i_above = max(
                (i for i, c in candidates.items() if abs(c.delta) >= Config.TARGET_DELTA),
                default=None,
            )
            i_below = min(
                (i for i, c in candidates.items() if abs(c.delta) < Config.TARGET_DELTA),
                default=None,
            )
            if i_above is not None and i_below is not None:
                if i_below < i_above:  # non-monotone (noisy premiums): stop here
                    return None
                gap = [j for j in range(i_above + 1, i_below) if j not in probed]
                return gap[-1] if gap else None
            if i_below is None:  # everything so far is above target: walk OTM
                nxt = max(probed) + 1
                if nxt <= hi:
                    return nxt
            if i_above is None:  # everything so far is below target: walk ITM
                nxt = min(probed) - 1
                if nxt >= lo:
                    return nxt
            return None

        # Seed at ATM; its IV aims the first jump (clamped to the scan bounds).
        seed = _probe(0)
        if seed is not None:
            k_pred = strike_for_delta(
                right.flag, spot, t_years, r, seed.iv, Config.TARGET_DELTA
            )
            if k_pred is not None:
                _probe(max(lo, min(hi, round(right.sign * (k_pred - atm) / step))))

        while (nxt := _next_index()) is not None:
            _probe(nxt)

        if not candidates:
            return None
        # Iterate in strike order so an exact-distance tie resolves to the more
        # ITM strike, matching the old low-to-high scan.
        ordered = [candidates[i] for i in sorted(candidates)]
        return min(ordered, key=lambda c: abs(c.delta - signed_target))
