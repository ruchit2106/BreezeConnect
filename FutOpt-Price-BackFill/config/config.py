"""All tunable settings live here as a single `Config` class.

Edit this file, not the logic modules. Credentials and the session token live in
the shared `auth` package, not here. CALL/PUT semantics live on the `Right` enum.
"""

from __future__ import annotations


class Config:
    # -- Positions: NSE symbol -> {qty, ce_strike, pe_strike} ----------------
    # You enter these (the "green" inputs): the lot qty and the CE/PE strikes to
    # track. The contract month auto-rolls (closest non-expired monthly; see the
    # expiry rule below), so a strike is tracked against whatever month is current.
    POSITIONS: dict[str, dict[str, float]] = {
        "WIPRO": {"qty": 800, "ce_strike": 195, "pe_strike": 170},
    }
    # NSE symbol -> ISEC code override, if auto-resolution is ever wrong/empty.
    STOCK_CODE_OVERRIDES: dict[str, str] = {}

    # -- Expiry rule (same as IV-Delta: last Tuesday, roll on/after expiry) ---
    EXPIRY_WEEKDAY = 1             # Mon=0..Sun=6; last Tuesday = 1
    ROLL_ON_EXPIRY_DAY = True      # on/after expiry day, roll to next month's series
    HOLIDAYS: set[str] = set()     # YYYY-MM-DD; expiry rolls back off these

    # -- Breeze API constants ------------------------------------------------
    EXCHANGE_EQUITY = "NSE"        # India VIX is fetched as an equity (cash)
    EXCHANGE_OPTIONS = "NFO"
    EXCHANGE_FUTURES = "NFO"
    PRODUCT_EQUITY = "cash"
    PRODUCT_OPTIONS = "options"
    PRODUCT_FUTURES = "futures"
    # -- Candle interval -----------------------------------------------------
    # Breeze v2 offers: 1second, 1minute, 5minute, 30minute, 1day. 30minute is the
    # sweet spot — the finest data that still fits a monthly contract segment in ONE
    # call (same call-count as 1day), and unlike 1day it's available same-day.
    # Finer intervals (5minute/1minute) are auto-chunked to stay under the per-call
    # record cap, costing proportionally more calls.
    CANDLE_INTERVAL = "30minute"
    MAX_RECORDS_PER_CALL = 1000     # Breeze v2 caps a single response at ~1000 candles
    CANDLES_PER_DAY = {             # bars per trading session, used to size fetch chunks
        "1day": 1,
        "30minute": 13,
        "5minute": 75,
        "1minute": 375,
    }

    # Market session (IST). For intraday intervals the day's OPEN is the first bar
    # at/after MARKET_OPEN_TIME and the CLOSE is the last bar at/before
    # MARKET_CLOSE_TIME; High/Low span that window. For "1day" the bar already
    # encodes the full session, so these are ignored.
    MARKET_OPEN_TIME = "09:15:00"
    MARKET_CLOSE_TIME = "15:30:00"
    ISO_TIME_SUFFIX = ".000Z"
    EXPIRY_ISO_TIME = "06:00:00"    # Breeze encodes expiry as <date>T06:00:00.000Z
    CODE_LOOKUP_KEYS = ("isec_stock_code", "ISEC_stock_code", "stock_code", "isec_token")

    # -- Rate limiting (Breeze: ~100/min, 5000/day) --------------------------
    MAX_CALLS_PER_MIN = 90
    MIN_SECONDS_BETWEEN_CALLS = 0.31
    DAILY_CALL_CAP = 4800
    RATE_WINDOW_SECONDS = 60
    RATE_SLEEP_BUFFER = 0.1

    # -- India VIX (best-effort) --------------------------------------------
    # ICICI's symbol for India VIX is "INDVIX" (NOT "INDIA VIX"). It's an index,
    # so it's passed straight to the historical call (like "NIFTY"), not resolved
    # via get_names — which is why _fetch_vix uses VIX_STOCK_CODE directly.
    FETCH_VIX = True
    VIX_STOCK_CODE = "INDVIX"

    # -- Output / formatting -------------------------------------------------
    OUTPUT_XLSX = "FUTOPT_DATA.xlsx"
    STOCKCODE_CACHE = ".stockcodes.json"
    SHEET_NAME = "Daily P&L data"
    ROUND_PRICE = 2
