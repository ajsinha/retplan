"""Daily price collection from Yahoo, with a bounded history.

:class:`PriceCollector` keeps every held symbol priced: a symbol seen for the
first time gets a year of daily closes, one already stored gets only the days
since its last close (plus a small overlap, because adjusted closes are restated
after dividends). After each run, closes older than the retention window are
deleted.

:class:`PriceScheduler` runs the collector once a day at a configured local time
on a daemon thread, and once at start-up when the last successful run is more
than 20 hours old - so a laptop that was asleep at collection time still catches up.
``tools/fetch_prices.py`` runs the same collector from cron instead.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta

from . import yahoo
from .db import PRICE_RETENTION_DAYS, utcnow
from .repository import PortfolioRepo, normalise_symbol

logger = logging.getLogger(__name__)

LONG_RUN_REFRESH_DAYS = 30
PAUSE_BETWEEN_SYMBOLS = 0.4          # be polite to an unofficial endpoint


def _range_for(last: str | None, retention_days: int = PRICE_RETENTION_DAYS) -> str:
    """The smallest Yahoo range that covers the gap since ``last`` (or, for a new
    symbol, the whole retention window)."""
    if not last:
        for days, rng in ((366, "1y"), (731, "2y"), (1827, "5y"), (3653, "10y")):
            if retention_days <= days:
                return rng
        return "max"
    gap = (date.today() - date.fromisoformat(last)).days
    if gap <= 4:
        return "5d"
    if gap <= 25:
        return "1mo"
    if gap <= 80:
        return "3mo"
    if gap <= 170:
        return "6mo"
    return "1y"


class PriceCollector:
    def __init__(self, repo: PortfolioRepo, retention_days: int = PRICE_RETENTION_DAYS,
                 fetch=yahoo.fetch_history, long_run=yahoo.long_run_stats,
                 pause: float = PAUSE_BETWEEN_SYMBOLS):
        self.repo = repo
        self.retention_days = retention_days
        self._fetch = fetch
        self._long_run = long_run
        self._pause = pause
        self._lock = threading.Lock()
        self.running = False

    def collect(self, symbols=None, reason: str = "manual") -> dict:
        """Fetch ``symbols`` (default: every held symbol). Safe to call concurrently:
        a second caller waits for the first rather than fetching twice."""
        with self._lock:
            self.running = True
            try:
                return self._collect(symbols, reason)
            finally:
                self.running = False

    def _collect(self, symbols, reason: str) -> dict:
        syms = sorted({normalise_symbol(s) for s in (symbols or
                                                     self.repo.tracked_symbols())})
        syms = [s for s in syms if s and s != "CASH"
                and (self.repo.security(s) or {}).get("source") != "manual"]
        run_id = self.repo.start_run(reason, len(syms))
        ok, failed, added, errors = 0, 0, 0, []
        t0 = time.time()
        queue, seen = list(syms), set(syms)
        i = -1
        while i + 1 < len(queue):
            i += 1
            sym = queue[i]
            if i and self._pause:
                time.sleep(self._pause)
            try:
                h = self._fetch(sym, range_=_range_for(self.repo.last_price_date(sym),
                                                        self.retention_days))
                self.repo.record_quote(h)
                added += self.repo.store_bars(sym, h.bars, self.retention_days)
                ok += 1
                if not sym.endswith("=X"):
                    self._maybe_long_run(sym)
                # a newly learned currency may need an FX pair priced this run
                for fx in self.repo.fx_pairs_needed():
                    if fx not in seen:
                        seen.add(fx)
                        queue.append(fx)
            except yahoo.YahooError as exc:
                failed += 1
                errors.append(f"{sym}: {exc}")
                self.repo.record_error(sym, str(exc))
                logger.warning("price fetch for %s failed: %s", sym, exc)
            except Exception as exc:  # noqa: BLE001 - one symbol never stops the run
                failed += 1
                errors.append(f"{sym}: {exc}")
                self.repo.record_error(sym, str(exc))
                logger.exception("price fetch for %s failed", sym)
        pruned = self.repo.prune(self.retention_days)
        msg = "; ".join(errors) if errors else f"{ok} symbol(s) updated"
        self.repo.finish_run(run_id, ok, failed, added, pruned, msg)
        if ok:
            try:
                from .networth import NetWorthRepo, record_all_portfolio_values
                record_all_portfolio_values(self.repo, NetWorthRepo(self.repo.db))
            except Exception:  # noqa: BLE001 - history is a by-product, never fatal
                logger.exception("recording portfolio values failed")
        syms = queue
        logger.info("price run (%s): %d ok, %d failed, %d rows, %d pruned in %.1fs",
                    reason, ok, failed, added, pruned, time.time() - t0)
        return dict(run_id=run_id, symbols=len(syms), ok=ok, failed=failed,
                    rows_added=added, rows_pruned=pruned, errors=errors)

    def _maybe_long_run(self, sym: str) -> None:
        sec = self.repo.security(sym) or {}
        stamp = sec.get("lt_updated")
        if stamp:
            age = datetime.now().astimezone() - datetime.fromisoformat(stamp)
            if age < timedelta(days=LONG_RUN_REFRESH_DAYS):
                return
        stats = self._long_run(sym)
        if stats:
            self.repo.record_long_run(sym, stats)


class PriceScheduler:
    """Runs the collector daily at ``run_at`` (local HH:MM) on a daemon thread."""

    def __init__(self, collector: PriceCollector, run_at: str = "18:30",
                 enabled: bool = True, catch_up: bool = True):
        self.collector = collector
        self.run_at = run_at
        self.enabled = enabled
        self.catch_up = catch_up
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.next_run: datetime | None = None
        self.last_result: dict | None = None

    def start(self) -> None:
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="price-scheduler",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _next_after(self, now: datetime) -> datetime:
        hh, mm = (int(x) for x in self.run_at.split(":"))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return target if target > now else target + timedelta(days=1)

    def _stale(self) -> bool:
        last = self.collector.repo.last_successful_run()
        if not last:
            return True
        started = datetime.fromisoformat(last["started_at"])
        return datetime.now().astimezone() - started > timedelta(hours=20)

    def _run(self, reason: str) -> None:
        try:
            if self.collector.repo.tracked_symbols():
                self.last_result = self.collector.collect(reason=reason)
        except Exception:  # noqa: BLE001 - the thread must survive a bad day
            logger.exception("scheduled price collection failed")

    def _loop(self) -> None:
        if self.catch_up and self._stale():
            # let the web server finish starting before the first network call
            if self._stop.wait(5):
                return
            self._run("startup")
        while not self._stop.is_set():
            self.next_run = self._next_after(datetime.now())
            # wake at least every minute so a changed clock or stop() is noticed
            while not self._stop.is_set() and datetime.now() < self.next_run:
                self._stop.wait(min(60.0, max(1.0, (self.next_run - datetime.now())
                                              .total_seconds())))
            if not self._stop.is_set():
                self._run("schedule")

    def status(self) -> dict:
        return dict(enabled=self.enabled, run_at=self.run_at,
                    alive=bool(self._thread and self._thread.is_alive()),
                    running=self.collector.running,
                    next_run=self.next_run.isoformat(timespec="minutes")
                    if self.next_run else None, now=utcnow())


def collect_in_background(collector: PriceCollector, symbols, reason="new-symbol"):
    """Price newly added symbols now, without making the request wait."""
    t = threading.Thread(target=lambda: _safe(collector, symbols, reason),
                         name=f"price-{reason}", daemon=True)
    t.start()
    return t


def _safe(collector, symbols, reason):
    try:
        collector.collect(symbols, reason=reason)
    except Exception:  # noqa: BLE001
        logger.exception("background price collection failed")
