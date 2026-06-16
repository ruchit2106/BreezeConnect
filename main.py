"""main.py — entry point.  Run: python main.py

Fully interactive (no CLI args): login, then asks the date range and the output
file (new or append), then runs the backfill.
"""

from __future__ import annotations

import logging
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from config import Config
from services.login_service import LoginService
from services.breeze_client import BreezeClient
from services.excel_writer import ExcelWriter
from engine.backfill_engine import BackfillEngine
from utils.prompts import pick_first_login, pick_date, pick_output

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Fully disable breeze_connect's loggers (e.g. "Get Historical data V2 response"
# on every call). Drop their handlers, stop propagation to our console, and
# disable them so nothing is emitted to the screen or to apiLogs/websocketLogs.
for _name in ("APILogger", "WebsocketLogger"):
    _lg = logging.getLogger(_name)
    _lg.handlers.clear()
    _lg.propagate = False
    _lg.disabled = True


def main() -> int:
    cfg = Config
    login = LoginService(cfg)

    # 1. Login — fresh login, or reload the saved token (error -> tell & exit).
    if pick_first_login():
        breeze = login.first_login()
    else:
        try:
            breeze = login.load_token()
        except RuntimeError as e:
            log.error(str(e))
            sys.exit(1)

    # 2. Date range.
    start = pick_date("From date")
    end = pick_date("To date")

    # 3. Output file — new or append.
    path, append = pick_output()

    # 4. Run.
    client = BreezeClient(breeze, cfg)
    writer = ExcelWriter(path, append=append)
    BackfillEngine(client, writer, cfg).run(start, end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
