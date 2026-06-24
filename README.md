# BreezeConnect

A monorepo of **ICICI Breeze** trading-data bots that share a single login. Each
bot is an independent product (its own strategy, config, and output); they all
authenticate through one shared `auth/` package, so you log in once and every bot
reuses the same daily session token.

Repo: `github.com/ruchit2106/BreezeConnect.git`

## Layout

```
D:\BreezeConnect\
├── auth/                     shared Breeze login — credentials + daily session token
│                             (one login, reused by every bot)
├── IV-Delta-BackFill/        bot: historical IV + delta backfill (live)
└── FutOpt-Price-BackFill/    bot: raw Future/CE/PE OHLC, no greeks (planned)
```

New bots are added as new sibling folders alongside the others, each importing
`auth`.

## How it fits together

- **All bots talk to ICICI Breeze.** ICICI allows **one API key per account**, so
  there is a single session token — and the bots are run **one at a time**, never
  concurrently.
- **`auth/` owns everything login-related** — the API credentials, the loopback
  login flow, and the cached session token. A bot contains *no* auth code or
  secrets; it just does `from auth.login_service import LoginService` and gets an
  authenticated client.
- **Login once per day.** Whichever bot you run first that day performs the login;
  the rest reuse the cached token until it expires (next day), then it re-mints.

## Setup

Requires Python 3.12.

1. **Credentials** — put your Breeze API key/secret in **`auth/.env`** (not in any
   bot folder):
   ```
   BREEZE_API_KEY=...
   BREEZE_API_SECRET=...
   ```
2. **Breeze redirect URL** — in the ICICI API portal, register your app's redirect
   URL as exactly:
   ```
   http://127.0.0.1:8080/
   ```
   After you log in, Breeze POSTs the session token here and `auth` captures it
   automatically (host/port configurable in `auth/login_service.py`).
3. **Per-bot dependencies** — install each bot's requirements, e.g.:
   ```bash
   pip install -r IV-Delta-BackFill/requirements.txt
   ```

## Running a bot

From inside the bot's folder:
```bash
cd IV-Delta-BackFill
python main.py
```
On first run of the day it opens the browser to log in (one-shot loopback capture,
no copy-paste) and caches the token in `auth/tokens.json`; subsequent runs — of any
bot — reuse it.

## The bots

- **[IV-Delta-BackFill](IV-Delta-BackFill/README.md)** — backfills historical option
  data for a basket of NSE stocks, computes **implied volatility** and **delta** via
  Black-Scholes (`vollib`), picks the **~+0.33 delta CALL** and **~−0.33 delta PUT**
  per stock/day at an open and a close snapshot, and writes strike / premium / IV /
  delta to an Excel workbook.
- **FutOpt-Price-BackFill** *(planned)* — fetches raw Future + option CE + PE OHLC,
  with **no IV or greek calculation** (raw price, in contrast to IV-Delta's derived
  outputs).

## Secrets & git

Credentials and tokens are git-ignored and never committed:
- `auth/.env`, `auth/tokens.json` — ignored via `auth/.gitignore`
- each bot ignores its own runtime artifacts (token caches, `*.xlsx`, etc.) via its
  own `.gitignore`
