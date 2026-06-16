"""Breeze login — mirrors HFAlgoBot's Kite LoginService, with a one-shot
loopback listener that auto-captures the session token.

Like a Kite access token, a Breeze session token expires daily, so the flow is
the same: log in once to mint a token, cache it in tokens.json, and reuse it
until it goes stale — then run a first login again to refresh.

Unlike Kite (which puts the token in the redirect query string), Breeze POSTs it
as a form field (`API_Session`) to the redirect URL. So `first_login` briefly
runs a local HTTP server at the registered callback URL, opens the browser, and
grabs the POSTed token automatically — no DevTools, no copy-paste. If that times
out (or the port is busy), it falls back to manual paste.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import logging
import os
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

from config import Config

log = logging.getLogger(__name__)

_TOKEN_FILE = Path(__file__).parent.parent / "tokens.json"
# Form/query keys Breeze has used for the session token, in order of preference.
_SESSION_KEYS = ("API_Session", "apisession", "session_token", "sessionToken")


def _import_breeze_connect():
    """Import breeze_connect, shielding its broken bare `import config`.

    breeze_connect/breeze_connect.py does `import config` expecting its own
    sibling config.py, but our top-level `config` package shadows it. We load
    breeze's config.py under the name 'config' just long enough for breeze to
    import (it binds the reference into its own globals), then restore ours.
    """
    if "breeze_connect" not in sys.modules:
        spec = importlib.util.find_spec("breeze_connect")
        bc_config_path = os.path.join(os.path.dirname(spec.origin), "config.py")
        saved = sys.modules.pop("config", None)
        cfg_spec = importlib.util.spec_from_file_location("config", bc_config_path)
        bc_config = importlib.util.module_from_spec(cfg_spec)
        sys.modules["config"] = bc_config
        try:
            cfg_spec.loader.exec_module(bc_config)
            import breeze_connect  # noqa: F401 — its `import config` now binds bc_config
        finally:
            sys.modules.pop("config", None)
            if saved is not None:
                sys.modules["config"] = saved
    from breeze_connect import BreezeConnect

    return BreezeConnect


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Captures the session token from Breeze's redirect (POST form, or GET)."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length).decode("utf-8", "ignore")
        self._capture(urllib.parse.parse_qs(body))

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        self._capture(urllib.parse.parse_qs(query))

    def _capture(self, data: dict) -> None:
        token = next((data[k][0] for k in _SESSION_KEYS if data.get(k)), None)
        if token:
            self.server.captured_token = token
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        msg = "Token Captured. You can close now." if token else "Waiting for token..."
        self.wfile.write(f"<html><body><h3>{msg}</h3></body></html>".encode())

    def log_message(self, *args):
        pass  # keep the terminal clean


class LoginService:
    def __init__(self, cfg=Config):
        self._cfg = cfg
        self._breeze = _import_breeze_connect()(api_key=cfg.API_KEY)

    def login_url(self) -> str:
        return self._cfg.BREEZE_LOGIN_URL + urllib.parse.quote_plus(self._cfg.API_KEY or "")

    def callback_url(self) -> str:
        return f"http://{self._cfg.CALLBACK_HOST}:{self._cfg.CALLBACK_PORT}/"

    def first_login(self):
        log.info("Breeze app redirect URL must be set to: %s", self.callback_url())
        log.info("Opening browser for login...")
        log.info(self.login_url())
        webbrowser.open(self.login_url())

        token = self._await_callback()
        if not token:
            log.warning("Callback not captured (timed out / port busy). Paste it manually.")
            token = input("API_Session: ").strip()
        return self.first_login_with_token(token)

    def _await_callback(self) -> str | None:
        cfg = self._cfg
        try:
            server = http.server.HTTPServer(
                (cfg.CALLBACK_HOST, cfg.CALLBACK_PORT), _CallbackHandler
            )
        except OSError as exc:
            log.warning("Could not start callback listener on %s (%s).", self.callback_url(), exc)
            return None
        server.captured_token = None
        server.timeout = 1
        log.info("Waiting for login callback on %s ...", self.callback_url())
        deadline = time.time() + cfg.CALLBACK_TIMEOUT_SEC
        try:
            while server.captured_token is None and time.time() < deadline:
                server.handle_request()
        finally:
            server.server_close()
        return server.captured_token

    def first_login_with_token(self, session_token: str):
        self._breeze.generate_session(
            api_secret=self._cfg.API_SECRET, session_token=session_token
        )
        self._save(session_token)
        log.info("Login successful. Token saved.")
        return self._breeze

    def load_token(self):
        token = self._load()
        if not token:
            raise RuntimeError("No saved token found in tokens.json. Run with first login.")
        self._breeze.generate_session(
            api_secret=self._cfg.API_SECRET, session_token=token
        )
        log.info("Session token loaded from tokens.json.")
        return self._breeze

    def _save(self, token: str) -> None:
        _TOKEN_FILE.write_text(json.dumps({"session_token": token}, indent=2))

    def _load(self) -> str | None:
        if _TOKEN_FILE.exists():
            try:
                return json.loads(_TOKEN_FILE.read_text()).get("session_token")
            except Exception:
                pass
        return None
