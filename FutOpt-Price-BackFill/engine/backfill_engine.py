"""Orchestrates the price backfill, fast.

For each configured position (stock + its CE/PE strikes) we fetch DAILY OHLC for
the monthly Future, the CE, and the PE across the whole date range in a handful
of calls — one per instrument per expiry-month segment — plus India VIX once for
the range, then write one row per (date, stock). No strike search, no greeks.

Daily bars mean the row's OPEN is the session open and CLOSE the session close.
Saves after every stock so a rate-limited run resumes cleanly.
"""

from __future__ import annotations

from datetime import date, timedelta

from config import Config
from entities.enums import Right
from helpers.candles import ohlc_by_date
from helpers.expiry import monthly_expiry_for
from services.breeze_client import RateLimitError


class BackfillEngine:
    def __init__(self, client, writer, cfg=Config) -> None:
        self.cfg = cfg
        self.client = client
        self.writer = writer

    # -- public ------------------------------------------------------------
    def run(self, start: date, end: date) -> None:
        stocks = list(self.cfg.POSITIONS.keys())
        print(f"Backfill {start} -> {end} | {len(stocks)} stocks | output: {self.writer.path}")
        try:
            vix = self._fetch_vix(start, end)
            for script in stocks:
                self._process_stock(script, start, end, vix)
            print(f"\nDone. Total API calls this run: {self.client.calls_made}")
        except RateLimitError as exc:
            self.writer.save()
            print(f"\n[PAUSED] {exc}")
            print("Progress saved. Re-run the same command to resume where it left off.")
        finally:
            self.writer.save()

    # -- per-stock ---------------------------------------------------------
    def _process_stock(self, script: str, start: date, end: date, vix: dict) -> None:
        pos = self.cfg.POSITIONS[script]
        lo, hi = self._session()
        try:
            isec = self.client.resolve_code(script)
            fut, ce, pe = {}, {}, {}
            for expiry, seg_start, seg_end in self._segments(start, end):
                fut.update(ohlc_by_date(self.client.future_range(isec, seg_start, seg_end, expiry), lo, hi))
                ce.update(ohlc_by_date(
                    self.client.option_range(isec, seg_start, seg_end, expiry, Right.CALL, pos["ce_strike"]), lo, hi))
                pe.update(ohlc_by_date(
                    self.client.option_range(isec, seg_start, seg_end, expiry, Right.PUT, pos["pe_strike"]), lo, hi))
        except RateLimitError:
            raise
        except Exception as exc:
            print(f"  {script:11s} ERROR fetching: {exc}")
            return

        rows = []
        for day in self._trading_days(start, end):
            ds = day.strftime("%Y-%m-%d")
            if self.writer.has(ds, script):
                continue
            if ds not in fut and ds not in ce and ds not in pe:
                continue  # no data that day (holiday / missing)
            rows.append(self._build_row(script, ds, pos, fut.get(ds), ce.get(ds), pe.get(ds), vix.get(ds)))

        if rows:
            self.writer.add_rows(rows)
            self.writer.save()
        print(f"  {script:11s} {len(rows)} new rows")

    def _fetch_vix(self, start: date, end: date) -> dict:
        if not self.cfg.FETCH_VIX:
            return {}
        lo, hi = self._session()
        try:
            return ohlc_by_date(self.client.equity_range(self.cfg.VIX_STOCK_CODE, start, end), lo, hi)
        except Exception:  # best-effort; never block the run on VIX
            return {}

    def _session(self) -> tuple:
        """Intraday session window (lo, hi) for reducing bars to a day; (None, None)
        for the 1day interval, where each bar already spans the full session."""
        if self.cfg.CANDLE_INTERVAL == "1day":
            return None, None
        return self.cfg.MARKET_OPEN_TIME, self.cfg.MARKET_CLOSE_TIME

    # -- row assembly ------------------------------------------------------
    def _build_row(self, script, ds, pos, fut, ce, pe, vix) -> dict:
        row = {
            "DATE": ds,
            "SCRIPT": script,
            "QTY": pos["qty"],
            "CE_STRIKE": pos["ce_strike"],
            "PE_STRIKE": pos["pe_strike"],
        }
        self._put_ohlc(row, "FUT", fut)
        self._put_ohlc(row, "CE", ce)
        self._put_ohlc(row, "PE", pe)
        self._put_ohlc(row, "VIX", vix)
        return row

    def _put_ohlc(self, row: dict, prefix: str, ohlc) -> None:
        if not ohlc:
            return
        r = self.cfg.ROUND_PRICE
        for name, val in zip(("OPEN", "HIGH", "LOW", "CLOSE"), ohlc):
            row[f"{prefix}_{name}"] = round(val, r) if val is not None else None

    # -- date / contract helpers -------------------------------------------
    def _trading_days(self, start: date, end: date):
        d = start
        while d <= end:
            if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in self.cfg.HOLIDAYS:
                yield d
            d += timedelta(days=1)

    def _segments(self, start: date, end: date):
        """Yield (expiry, seg_start, seg_end): contiguous runs of trading days that
        share the same monthly contract, so each instrument is fetched once per
        contract over its date range instead of once per day."""
        days = list(self._trading_days(start, end))
        if not days:
            return
        seg_start = prev = days[0]
        cur = monthly_expiry_for(days[0])
        for d in days[1:]:
            e = monthly_expiry_for(d)
            if e != cur:
                yield (cur, seg_start, prev)
                seg_start, cur = d, e
            prev = d
        yield (cur, seg_start, prev)
