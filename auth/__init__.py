"""Shared Breeze authentication.

All auth state lives in this folder — credentials (.env) and the daily session
token (tokens.json) — so any bot that imports `auth` shares one login. The
folder's `.env` is loaded on import, before LoginService reads the credentials.
"""

from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

from .login_service import LoginService  # noqa: E402

__all__ = ["LoginService"]
