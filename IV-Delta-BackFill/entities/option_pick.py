"""The option a snapshot resolved to: the strike whose delta is nearest target."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OptionPick:
    strike: float
    premium: float
    iv: float       # implied volatility as a decimal (e.g. 0.1477)
    delta: float    # signed Black-Scholes delta
