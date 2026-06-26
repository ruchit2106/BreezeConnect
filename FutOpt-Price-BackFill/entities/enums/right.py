"""CALL / PUT option side. Carries the Breeze request value and a display label.

Trimmed from IV-Delta's Right: this bot never computes greeks, so the vollib
`flag` and delta `sign` are dropped.
"""

from __future__ import annotations

from enum import Enum


class Right(Enum):
    CALL = "call"
    PUT = "put"

    @property
    def breeze_value(self) -> str:
        """String Breeze's API expects for `right` ("call" / "put")."""
        return self.value

    @property
    def label(self) -> str:
        """Label for logs/output ("CALL" / "PUT")."""
        return self.name
