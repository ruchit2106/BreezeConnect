"""All tunable settings live here as a single `Config` class.

Edit this file, not the logic modules — every number, code, time, and label the
logic touches is a `Config` attribute. Credentials are read from the environment
(see .env). Right/flag/label semantics live on the `Right` enum, not here.
"""

from __future__ import annotations


class Config:
    # Authentication — credentials, login callback, and the session token — lives
    # entirely in the shared `auth` package (see auth/login_service.py). Nothing
    # auth-related belongs here.

    # -- Strategy / model ----------------------------------------------------
    TARGET_DELTA = 0.33            # calls hunt +0.33, puts hunt -0.33
    RISK_FREE_RATE = 0.095         # FALLBACK carry only. The real per-stock, per-
                                   # snapshot carry is derived from the market via ATM
                                   # put-call parity (StrikeSearcher._carry_rate); this
                                   # constant is used only when the ATM call/put pair is
                                   # missing, plus as the small discount on (C - P).

    # Snapshot times (IST clock, HH:MM:SS) sampled each trading day.
    OPEN_TIME = "09:30:00"
    CLOSE_TIME = "15:30:00"
    # Accept the nearest candle at-or-before a target time within this many minutes.
    TIME_TOLERANCE_MIN = 5

    # -- Expiry rule ---------------------------------------------------------
    EXPIRY_WEEKDAY = 1             # Mon=0..Sun=6; sheet shows last Tuesday = 1
    ROLL_ON_EXPIRY_DAY = True      # on/after expiry day, roll to next month's series
    HOLIDAYS: set[str] = set()     # YYYY-MM-DD; expiry rolls back off these
    DAYS_PER_YEAR = 365.0
    MIN_YEARS_TO_EXPIRY = 1e-5     # floor so near-expiry T never hits zero
    MARKET_CLOSE_TIME = "15:30:00"  # expiry measured to this IST clock time

    # -- Universe: NSE symbol -> strike step --------
    STOCKS: dict[str, float] = {
        "RELIANCE": 10,
        "SBIN": 10,
        "TCS": 20,
        "PNB": 1,
        "INFY": 5,
        "WIPRO": 2.5,
        "BAJAJ-AUTO": 100,
        "MARUTI": 100,
        "HDFCBANK": 5,
        "ICICIBANK": 10,
        "ADANIENT" : 20,
        "ADANIPORTS" : 20,
        "AXISBANK" : 10,
        "ASIANPAINT" : 20,
        "APOLLOHOSP" : 50,
        "BAJFINANCE" : 10,
        "BAJAJFINSV" : 20,
        "BEL" : 5,
        "BHARTIARTL" : 20,
        "CIPLA" : 10,
        "COALINDIA" : 5,
    }
    # NSE symbol -> ISEC code override, if auto-resolution is ever wrong/empty.
    STOCK_CODE_OVERRIDES: dict[str, str] = {}

    # -- Strike-scan tuning --------------------------------------------------
    SCAN_ITM_STEPS = 2             # start this many steps ITM of ATM
    SCAN_MAX_STEPS = 30            # give up after this many steps OTM
    STRIKE_ROUND_DECIMALS = 4      # tidy float noise when stepping strikes

    # -- Breeze API constants ------------------------------------------------
    EXCHANGE_EQUITY = "NSE"
    EXCHANGE_OPTIONS = "NFO"
    PRODUCT_EQUITY = "cash"
    PRODUCT_OPTIONS = "options"
    CANDLE_INTERVAL = "1minute"

    HIST_WINDOW_START = "09:15:00"
    HIST_WINDOW_END = MARKET_CLOSE_TIME
    ISO_TIME_SUFFIX = ".000Z"
    EXPIRY_ISO_TIME = "06:00:00"   # Breeze encodes expiry as <date>T06:00:00.000Z

    CODE_LOOKUP_KEYS = ("isec_stock_code", "ISEC_stock_code", "stock_code", "isec_token")

    # -- Rate limiting (Breeze: ~100/min, 5000/day) --------------------------
    MAX_CALLS_PER_MIN = 90
    MIN_SECONDS_BETWEEN_CALLS = 0.31
    DAILY_CALL_CAP = 4800
    RATE_WINDOW_SECONDS = 60
    RATE_SLEEP_BUFFER = 0.1

    # -- India VIX (best-effort) --------------------------------------------
    FETCH_VIX = True
    VIX_STOCK_CODE = "INDIA VIX"
    VIX_EXCHANGE = "NSE"

    # -- Output / formatting -------------------------------------------------
    OUTPUT_XLSX = "IV_DATA.xlsx"
    STOCKCODE_CACHE = ".stockcodes.json"
    SHEET_NAME = "IV DATA"

    IV_PCT_MULTIPLIER = 100        # store IV as a percent (14.77) not a decimal
    ROUND_IV = 2
    ROUND_PREMIUM = 2
    ROUND_DELTA = 2
    ROUND_SPOT = 2
    ROUND_VIX = 2
