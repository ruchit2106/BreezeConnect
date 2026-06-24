# IV / Delta Backfill Bot (ICICI Breeze)

Fetches historical option data for a fixed basket of NSE stocks, computes
**implied volatility** and **delta** via Black-Scholes (the exact method ICICI's
Breeze team recommends), finds the **~0.33 delta CALL** and **~-0.33 delta PUT**
for each stock/day at **9:30 AM** and **3:15 PM**, and writes
strike / premium / IV to an Excel workbook.

## Why we compute IV/delta ourselves
The Breeze API returns **no Greeks and no IV** anywhere (confirmed in their own
SDK issue #130). So we fetch the option's market price and back out IV with
**vollib** (`black_scholes.implied_volatility`), then compute delta from that
IV — the library ICICI's own team recommends, just wired for *historical* data
instead of live quotes. vollib is the single math engine (no fallback).

## Project layout
```
main.py                 entry — interactive Q&A (no CLI args)
utils/prompts.py        the Q&A prompts (login? / dates / output file)
config/config.py        Config class — every tunable, code, time, precision
entities/
  option_pick.py        OptionPick dataclass (strike/premium/iv/delta)
  enums/right.py        Right enum (CALL/PUT: breeze value, flag, label, sign)
helpers/
  black_scholes.py      vollib pricing / IV / delta
  expiry.py             last-Tuesday monthly expiry + time-to-expiry
  candles.py            pick the candle at a target time
services/
  breeze_client.py      rate-limited historical fetch + code resolution
  excel_writer.py       xlsx output, resume-aware
engine/
  strike_searcher.py    scan strikes to bracket the target delta
  backfill_engine.py    BackfillEngine: wires services, owns the loop
```
Login is **not** in this folder. It lives in the shared `auth/` package (a sibling
at the repo root): `auth/login_service.py` (Breeze login -> session token),
`auth/.env` (credentials), `auth/tokens.json` (the cached daily token). Every bot
imports `auth`, so one login is shared across all of them.

## Setup
```bash
pip install -r requirements.txt      # vollib is pure-Python; works on 3.12
```
Put your credentials in **`auth/.env`** (the shared auth package at the repo root),
not in this folder:
```
BREEZE_API_KEY=...
BREEZE_API_SECRET=...
```

**One-time: set your Breeze app's Redirect URL** (in the ICICI API portal) to
exactly match the local listener:
```
http://127.0.0.1:8080/
```
(host/port configurable via `CALLBACK_HOST`/`CALLBACK_PORT` in `auth/login_service.py`.)
After you log in, Breeze POSTs the session token here and the bot captures it
automatically. If ICICI rejects a plain-`http` loopback and demands `https`,
tell me — we'll switch the listener to a self-signed TLS socket.

## Run it
```bash
python main.py
```
Everything is interactive — no CLI flags. It asks, in order:

1. **First login? (y/n)** — `y` opens the browser and starts a one-shot local
   listener that **auto-captures** the session token Breeze POSTs back (no
   copy-paste; token cached in `tokens.json`). `n` reuses the saved token; if
   it's missing/stale it tells you to log in. (Like Kite, the token expires daily.)
2. **From / To date** (`YYYY-MM-DD`).
3. **Output: new file or append** + the file path. *Append* resumes an existing
   file (skips already-written DATE+SCRIPT); *new* writes a fresh workbook.

Then it backfills every stock in `STOCKS` (edit that list in `config/config.py`),
**two rows per stock** (CALL then PUT), saving after each stock. Breeze caps
~5000 calls/day; if the cap is hit it pauses cleanly — just run again later and
choose *append* to the same file to resume.

## Output columns
`DATE, DAY, SCRIPT, RIGHT, EXPIRY, SPOT_OPEN, OPEN_STRIKE, OPEN_PREMIUM, OPEN_IV,
OPEN_DELTA, SPOT_CLOSE, CLOSE_STRIKE, CLOSE_PREMIUM, CLOSE_IV, CLOSE_DELTA,
VIX_OPEN, VIX_CLOSE`

- The timed columns carry the snapshot time in the header, e.g. `OPEN_IV (at 9:30 AM)`,
  `CLOSE_IV (at 3:15 PM)` — derived from `OPEN_TIME`/`CLOSE_TIME`.
- `SPOT_OPEN`/`SPOT_CLOSE` = the underlying **stock price** at each snapshot (the `S`
  fed into Black-Scholes), not an option value.
- IV is in %, e.g. 14.77; delta is a decimal.

## Things to VERIFY on first run (see `config/config.py`)
- **Stock codes** — Breeze uses ICICI's own short codes, auto-resolved via
  `get_names()` and cached to `.stockcodes.json`. Sanity-check that file; add
  `STOCK_CODE_OVERRIDES` for any wrong one.
- **Expiry weekday** — set to **Tuesday** (last Tue of month) per your sheet.
- **India VIX** — best-effort; if Breeze won't serve `INDIA VIX`, the column is
  left blank (adjust `VIX_STOCK_CODE`/`VIX_EXCHANGE`).
- **Risk-free rate** — fixed `0.065`; dividends ignored (matches ICICI's snippet).
- **Timezone** — historical timestamps are matched on IST clock time.

## Known limitations
- IV/delta are **model outputs**, so they won't match a broker terminal to the
  decimal (different model/inputs).
- Backfilling many months can take **multiple days** under the 5000-calls/day cap
  (resume handles this automatically).
- Daily login refresh is required (`python run.py --login`) — Breeze, like Kite,
  has no headless login.
