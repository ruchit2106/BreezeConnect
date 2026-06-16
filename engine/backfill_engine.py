"""Orchestrates the backfill: for each trading day and stock, find the
~0.33 delta CALL and ~-0.33 delta PUT at open and close, and write
strike / premium / IV to the workbook.

Mirrors HFAlgoBot's AlgoEngine: wires the services together and owns the loop.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from config import Config
from entities.enums import Right
from helpers.candles import select_close_at
from helpers.expiry import monthly_expiry_for
from services.breeze_client import RateLimitError
from engine.strike_searcher import StrikeSearcher


class BackfillEngine:
    def __init__(self, client, writer, cfg=Config) -> None:
        self.cfg = cfg
        self.client = client
        self.writer = writer

    # -- public ------------------------------------------------------------
    def run(self, start: date, end: date) -> None:
        cfg = self.cfg
        stocks = list(cfg.STOCKS.keys())
        print(f"Backfill {start} -> {end} | {len(stocks)} stocks | output: {self.writer.path}")
        print("Black-Scholes engine: vollib")

        try:
            for day in self._trading_days(start, end):
                self._process_day(day, stocks)
            print(f"\nDone. Total API calls this run: {self.client.calls_made}")
        except RateLimitError as exc:
            self.writer.save()
            print(f"\n[PAUSED] {exc}")
            print("Progress saved. Re-run the same command to resume where it left off.")
        finally:
            self.writer.save()

    # -- per-day / per-stock ----------------------------------------------
    def _process_day(self, day: date, stocks: list[str]) -> None:
        date_str = day.strftime("%Y-%m-%d")
        print(f"\n=== {date_str} ({day:%a}) ===")
        vix_done = False
        for script in stocks:
            if self.writer.has(date_str, script):
                print(f"  {script:11s} already done, skipping")
                continue
            rows = self._process_stock(day, script)
            if rows is None:
                continue
            if not vix_done:
                self._attach_vix(rows, day)
                vix_done = True
            self.writer.add_rows(rows)
            self.writer.save()
            self._log_stock(script, rows)

    def _process_stock(self, day: date, script: str) -> list[dict] | None:
        cfg = self.cfg
        step = cfg.STOCKS[script]
        try:
            isec = self.client.resolve_code(script)
            equity = self.client.equity_minute(isec, day)
        except RateLimitError:
            raise
        except Exception as exc:
            print(f"  {script:11s} ERROR fetching equity: {exc}")
            return None

        spot_o = select_close_at(equity, cfg.OPEN_TIME)
        spot_c = select_close_at(equity, cfg.CLOSE_TIME)
        if spot_o is None and spot_c is None:
            print(f"  {script:11s} no spot data (holiday/missing), skipping")
            return None

        expiry = monthly_expiry_for(day)
        searcher = StrikeSearcher(self.client, isec, day, expiry)
        open_dt = self._snapshot_dt(day, cfg.OPEN_TIME)
        close_dt = self._snapshot_dt(day, cfg.CLOSE_TIME)

        rows = []
        for right in (Right.CALL, Right.PUT):
            open_res = searcher.find(right, open_dt, spot_o, step) if spot_o else None
            close_res = searcher.find(right, close_dt, spot_c, step) if spot_c else None
            rows.append(self._build_row(script, right, expiry, day, open_res, close_res, spot_o, spot_c))
        return rows

    # -- row assembly ------------------------------------------------------
    def _build_row(self, script, right: Right, expiry, day, open_res, close_res, spot_o, spot_c) -> dict:
        cfg = self.cfg
        row = {
            "DATE": day.strftime("%Y-%m-%d"),
            "DAY": day.strftime("%a"),
            "SCRIPT": script,
            "RIGHT": right.label,
            "EXPIRY": expiry.strftime("%Y-%m-%d"),
            "SPOT_OPEN": round(spot_o, cfg.ROUND_SPOT) if spot_o else None,
            "SPOT_CLOSE": round(spot_c, cfg.ROUND_SPOT) if spot_c else None,
        }
        if open_res:
            row.update({
                "OPEN_STRIKE": open_res.strike,
                "OPEN_PREMIUM": open_res.premium,
                "OPEN_IV": self._iv_pct(open_res.iv),
                "OPEN_DELTA": round(open_res.delta, cfg.ROUND_DELTA),
            })
        if close_res:
            row.update({
                "CLOSE_STRIKE": close_res.strike,
                "CLOSE_PREMIUM": close_res.premium,
                "CLOSE_IV": self._iv_pct(close_res.iv),
                "CLOSE_DELTA": round(close_res.delta, cfg.ROUND_DELTA),
            })
        return row

    def _attach_vix(self, rows: list[dict], day: date) -> None:
        cfg = self.cfg
        if not cfg.FETCH_VIX:
            return
        try:
            candles = self.client.equity_minute(cfg.VIX_STOCK_CODE, day)
            vo = select_close_at(candles, cfg.OPEN_TIME)
            vc = select_close_at(candles, cfg.CLOSE_TIME)
        except Exception as exc:  # best-effort; never block the run on VIX
            print(f"    (VIX fetch failed for {day}: {exc})")
            return
        rows[0]["VIX_OPEN"] = round(vo, cfg.ROUND_VIX) if vo else None
        rows[0]["VIX_CLOSE"] = round(vc, cfg.ROUND_VIX) if vc else None

    # -- small utilities ---------------------------------------------------
    def _iv_pct(self, iv: float | None):
        return round(iv * self.cfg.IV_PCT_MULTIPLIER, self.cfg.ROUND_IV) if iv is not None else None

    def _trading_days(self, start: date, end: date):
        d = start
        while d <= end:
            if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in self.cfg.HOLIDAYS:
                yield d
            d += timedelta(days=1)

    @staticmethod
    def _snapshot_dt(day: date, hms: str) -> datetime:
        return datetime.combine(day, datetime.strptime(hms, "%H:%M:%S").time())

    @staticmethod
    def _log_stock(script: str, rows: list[dict]) -> None:
        parts = [
            f"{r['RIGHT']}: O[{r.get('OPEN_STRIKE')}@{r.get('OPEN_IV')}] "
            f"C[{r.get('CLOSE_STRIKE')}@{r.get('CLOSE_IV')}]"
            for r in rows
        ]
        print(f"  {script:11s} " + " | ".join(parts))
