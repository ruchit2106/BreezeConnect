"""Black-Scholes pricing, implied volatility and delta — via vollib only.

`vollib` is the canonical package; it's the exact library ICICI's Breeze team
recommends in SDK issue #130. We use it for the option price, the implied-vol
solve, and the delta, so there is a single engine and no second code path.
"""

from __future__ import annotations

import math
from statistics import NormalDist

from vollib.black_scholes import black_scholes as _bs_price
from vollib.black_scholes.greeks.analytical import delta as _bs_delta
from vollib.black_scholes.implied_volatility import implied_volatility as _bs_iv


def bs_price(flag: str, S: float, K: float, t: float, r: float, sigma: float) -> float:
    """Black-Scholes option price. flag: 'c' or 'p'."""
    return _bs_price(flag, S, K, t, r, sigma)


def bs_delta(flag: str, S: float, K: float, t: float, r: float, sigma: float) -> float:
    """Black-Scholes delta. flag: 'c' or 'p'."""
    return _bs_delta(flag, S, K, t, r, sigma)


def implied_vol(
    flag: str, S: float, K: float, t: float, r: float, option_price: float
) -> float | None:
    """Solve for IV (decimal, e.g. 0.1477) from the option's market price.

    Returns None when the price is unusable (None/zero, or below intrinsic /
    above max, which vollib raises on).
    """
    if option_price is None or option_price <= 0 or S <= 0 or K <= 0 or t <= 0:
        return None
    try:
        return _bs_iv(option_price, S, K, t, r, flag)
    except Exception:
        return None


def strike_for_delta(
    flag: str, S: float, t: float, r: float, sigma: float, target_delta: float
) -> float | None:
    """Invert BS delta analytically: the strike whose delta magnitude equals
    `target_delta` at the given vol. Used only to AIM the strike search (pick a
    good starting probe) — never to decide the final pick, which always comes
    from real fetched premiums.

    delta_call = N(d1), delta_put = N(d1) - 1, so d1 = inv_cdf(target) for calls
    and inv_cdf(1 - target) for puts; then solve d1's definition for K.
    Returns None if inputs are unusable.
    """
    if S <= 0 or t <= 0 or sigma is None or sigma <= 0 or not 0 < target_delta < 1:
        return None
    d1 = NormalDist().inv_cdf(target_delta if flag == "c" else 1.0 - target_delta)
    return S * math.exp((r + sigma * sigma / 2.0) * t - d1 * sigma * math.sqrt(t))


def iv_and_delta(
    flag: str, S: float, K: float, t: float, r: float, option_price: float
) -> tuple[float | None, float | None]:
    """Convenience: returns (iv_decimal, delta) or (None, None) if IV unsolvable."""
    iv = implied_vol(flag, S, K, t, r, option_price)
    if iv is None:
        return None, None
    return iv, bs_delta(flag, S, K, t, r, iv)
