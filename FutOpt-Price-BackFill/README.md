# FutOpt Price Backfill (ICICI Breeze)

Backfills **raw daily OHLC** for a basket of NSE positions — the monthly
**Future**, a **CE option** at a chosen strike, and a **PE option** at a chosen
strike — plus **India VIX**. One row per (date, stock). **No IV, no greeks** —
just prices (the counterpart to the sibling `IV-Delta-BackFill`, which computes
derived values).

Shares the repo's `auth/` package for login, exactly like `IV-Delta-BackFill`.

## Project layout
```
main.py                 entry — interactive Q&A (no CLI args)
utils/prompts.py        the Q&A prompts (login? / dates / output file)
config/config.py        Config — POSITIONS, expiry rule, API constants, rounding
entities/enums/right.py Right enum (CALL/PUT: breeze value, label)
helpers/
  expiry.py             last-Tuesday monthly expiry (closest non-expired)
  candles.py            day_ohlc(): reduce 1-min candles to (O,H,L,C)
services/
  breeze_client.py      rate-limited historical fetch (future/option/equity) + code resolution
  excel_writer.py       two-row grouped-header xlsx, resume-aware
engine/
  backfill_engine.py    BackfillEngine: wires services, owns the loop
```
Login is **not** here — it lives in the shared `auth/` package at the repo root
(`from auth.login_service import LoginService`), so one login is shared across all
bots. Put credentials in `auth/.env`.

## What it fetches
For each configured position and each trading day:
- **Future** O/H/L/C (monthly contract, auto-rolled)
- **CE** O/H/L/C at `ce_strike`, **PE** O/H/L/C at `pe_strike`
- **India VIX** O/H/L/C (once per day)

The contract month is the closest non-expired monthly (last Tuesday, roll on/after
expiry) — same rule as `IV-Delta-BackFill`.

## Configure
Edit `config/config.py` → `POSITIONS`:
```python
POSITIONS = {
    "WIPRO": {"qty": 800, "ce_strike": 195, "pe_strike": 170},
}
```
`qty` and the strikes are *your* inputs (the green columns). Add one line per stock.

## Run
```bash
pip install -r requirements.txt
python main.py
```
Interactive: **first login? (y/n)** → **From/To dates** → **new file or append**.
Append resumes (skips already-written DATE+SCRIPT). Saves after every stock; if the
Breeze daily call cap is hit it pauses — re-run and choose *append* to resume.

## Output
A workbook matching the template's two-row grouped header
(Future / Option (CE) / Option (PE) / NET DAILY P&L / VIX). The bot fills the OHLC
and your inputs; the price/P&L/IV columns are left blank for you to fill in later.
