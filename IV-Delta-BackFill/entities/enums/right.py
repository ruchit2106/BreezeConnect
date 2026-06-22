"""CALL / PUT option side, with everything that varies by side attached to it.

Replaces the loose RIGHT_*/FLAG_*/LABEL_* maps: one type carries its Breeze
request value, its vollib flag, its spreadsheet label, and its delta sign.
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
    def flag(self) -> str:
        """vollib option-type flag ("c" / "p")."""
        return "c" if self is Right.CALL else "p"

    @property
    def label(self) -> str:
        """Label written to the spreadsheet ("CALL" / "PUT")."""
        return self.name

    @property
    def sign(self) -> int:
        """+1 for calls, -1 for puts: signs the target delta and the OTM scan
        direction (calls scan up in strike, puts scan down)."""
        return 1 if self is Right.CALL else -1
