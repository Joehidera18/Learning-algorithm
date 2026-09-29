"""Read-only, closed-candle observations. These rules are not return probabilities."""
from __future__ import annotations

import json
import math
import statistics
import threading
import time
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .continuous import RuntimeLease
from .event_feeds import NoRedirect, fetch as fetch_feed, parse as parse_feed
from .paper_store import db_connect

STEP = 300_000
HOUR = 3_600_000
DAY = 24 * HOUR
VERSION = "crypto-watch-v1"
SYMBOLS = ("BTC-USD", "HBAR-USD", "ETH-USD", "SOL-USD", "XRP-USD", "XLM-USD",
           "LINK-USD", "ADA-USD", "DOGE-USD", "AVAX-USD", "LTC-USD", "BCH-USD")
SOURCE = "Coinbase Exchange · 5-minute candles"
NEWS_SOURCE = "coindesk"


def now_ms():
    return int(time.time() * 1000)


def encode(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def normalize(rows, observed):
    """Validate only information closed by observed; never fill missing buckets."""
    cutoff = observed // STEP * STEP
    clean = {}
    for row in rows:
        ts = row["ts"]
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts) or ts % STEP:
            raise ValueError("Invalid candle timestamp")
        if ts >= cutoff:
            continue
        values = {k: float(row[k]) for k in ("open", "high", "low", "close", "volume")}
        if not all(math.isfinite(v) for v in values.values()):
            raise ValueError("Non-finite candle data")
        o, h, l, c, v = (values[k] for k in ("open", "high", "low", "close", "volume"))
        if l <= 0 or v < 0 or not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError("Invalid candle prices or volume")
        item = dict(values, ts=int(ts))
        if ts in clean and item != clean[ts]:
            raise ValueError("Conflicting duplicate candles")
        clean[ts] = item
    return [clean[t] for t in sorted(clean)]


class CandleSource:
    """One bounded request per pair per five minutes; no ticker-volume proxy."""
    def __init__(self):
        self.last_fetch = 0.

    def candles(self, symbol, observed):
        if symbol not in SYMBOLS:
            raise ValueError("Unsupported watch symbol")
        # Pace the twelve-pair batch; a fast response must not create a burst.
        pause = .35 - (time.monotonic() - self.last_fetch)
        if pause > 0:
            time.sleep(pause)
        self.last_fetch = time.monotonic()
        end = observed // STEP * STEP
        iso = lambda ts: datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat()
        query = urllib.parse.urlencode({"granularity": 300,
            "start": iso(end - 300 * STEP), "end": iso(end)})
        req = urllib.request.Request("https://api.exchange.coinbase.com/products/" + symbol +
            "/candles?" + query, headers={"User-Agent": "Stock-Lab-Crypto-Watch/1.0", "Accept": "application/json"})
        with urllib.request.build_opener(NoRedirect).open(req, timeout=8) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("Candle response exceeds size limit")
        payload = json.loads(raw)
        if not isinstance(payload, list) or len(payload) > 600:
            raise ValueError("Unexpected candle response")
        if any(not isinstance(r, list) or len(r) != 6 for r in payload):
            raise ValueError("Unexpected candle schema")
        return normalize([dict(ts=r[0] * 1000, low=r[1], high=r[2], open=r[3], close=r[4], volume=r[5])
                          for r in payload], observed)


def evaluate(symbol, rows, benchmark, observed):
    """All baselines exclude the event bar. Missing inputs produce no alert."""
    result = {"symbol": symbol, "stage": "unavailable", "source": SOURCE, "rule_version": VERSION,
              "observed_ts": observed, "candle_end_ts": None, "metrics": {}, "reasons": []}
    try:
        rows = normalize(rows, observed)[-289:]
        if len(rows) < 289:
            raise ValueError("Need 289 closed five-minute candles for a full 24-hour baseline")
        if any(b["ts"] - a["ts"] != STEP for a, b in zip(rows, rows[1:])):
            raise ValueError("Missing candles in the 24-hour baseline; no gaps are filled")
        last = rows[-1]
        if observed - (last["ts"] + STEP) > 2 * STEP:
            raise ValueError("Latest closed candle is stale")
        prior = rows[-21:-1]
        median_volume = statistics.median(r["volume"] for r in prior)
        if median_volume <= 0:
            raise ValueError("Volume baseline is zero")
        resistance = max(r["high"] for r in prior)
        ranges = [max(r["high"] - r["low"], abs(r["high"] - p["close"]), abs(r["low"] - p["close"]))
                  for p, r in zip(rows[-22:-2], prior)]
        atr = statistics.mean(ranges)
        change15 = 100 * (last["close"] / rows[-4]["close"] - 1)
        change24 = 100 * (last["close"] / rows[0]["close"] - 1)
        ratio = last["volume"] / median_volume
        liquidity = statistics.median(r["volume"] * r["close"] for r in prior) * 288
        m = result["metrics"] = {"price": last["close"], "change_15m_pct": change15,
            "change_24h_pct": change24, "relative_volume": ratio, "prior_high": resistance,
            "prior_atr": atr, "approx_daily_turnover_usd": liquidity, "relative_btc_15m_pp": None}
        result["candle_end_ts"] = last["ts"] + STEP
        if liquidity < 250_000:
            raise ValueError("Thin venue liquidity: estimated daily turnover below $250,000")
        if symbol != "BTC-USD":
            btc = {r["ts"]: r for r in normalize(benchmark, observed)}
            times = [last["ts"] - n * STEP for n in range(4)]
            if any(t not in btc for t in times):
                raise ValueError("Matching BTC candles unavailable; relative strength is unverified")
            btc15 = 100 * (btc[times[0]]["close"] / btc[times[-1]]["close"] - 1)
            m["relative_btc_15m_pp"] = change15 - btc15
        strong = symbol == "BTC-USD" or m["relative_btc_15m_pp"] > 0
        extension = (last["close"] - resistance) / atr if atr > 0 else 0
        if change15 >= 5 or change24 >= 15 or extension >= 4:
            result.update(stage="extended", reasons=["Price has already moved sharply; this is a late-move warning, not an early entry signal"])
        elif last["close"] > resistance and ratio >= 3 and change15 > 0 and strong:
            result.update(stage="breakout", reasons=["Closed above the preceding 20-candle high",
                "Volume at least 3× its preceding 20-candle median", "Positive momentum and relative strength"])
        elif .99 * resistance <= last["close"] <= resistance and ratio >= 2 and change15 > 0 and strong:
            result.update(stage="building", reasons=["Within 1% of the preceding 20-candle high",
                "Volume at least 2× its preceding 20-candle median", "Momentum is improving; a breakout is not confirmed"])
        else:
            result.update(stage="quiet", reasons=["No qualifying combination in the latest closed candle"])
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        result.update(stage="unavailable", reasons=[str(exc)])
    return result


class CryptoWatch:
    def __init__(self, data_dir, token="", client=None, news_fetch=None, *, database_name="crypto-watch.sqlite3"):
        self.path = Path(data_dir) / database_name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.token = token
        self.client = client or CandleSource()
        self.news_fetch = news_fetch or fetch_feed
        self.lock = threading.RLock()
        self.worker = None
        self.resume_worker = None
        self.stop_event = threading.Event()
        self.lease = RuntimeLease(self.path)
        with closing(db_connect(self.path)) as con, con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS watch_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS watch_latest (symbol TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS watch_alerts (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL,
                    stage TEXT NOT NULL, candle_end_ts INTEGER NOT NULL, observed_ts INTEGER NOT NULL,
                    payload TEXT NOT NULL, UNIQUE(symbol,stage,candle_end_ts));
                CREATE INDEX IF NOT EXISTS watch_alert_time ON watch_alerts(observed_ts);
                CREATE TABLE IF NOT EXISTS watch_news (id TEXT NOT NULL, revision TEXT NOT NULL,
                    observed_ts INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id,revision));
            """)

    def _meta(self, key, default=None):
        with closing(db_connect(self.path)) as con:
            row = con.execute("SELECT value FROM watch_meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _set(self, **values):
        with closing(db_connect(self.path)) as con, con:
            con.executemany("INSERT OR REPLACE INTO watch_meta VALUES(?,?)", [(k, encode(v)) for k, v in values.items()])

    def resume(self):
        if self.token and self._meta("enabled", False):
            try:
                self.start()
            except RuntimeError:
                # During a rolling restart the old worker can still own the lock.
                # Keep waiting without clearing its settings or duplicating scans.
                if not self.resume_worker or not self.resume_worker.is_alive():
                    self.resume_worker = threading.Thread(target=self._await_lease, name="crypto-watch-resume", daemon=True)
                    self.resume_worker.start()

    def _await_lease(self):
        while not self.stop_event.wait(5) and self._meta("enabled", False):
            try:
                self.start()
                return
            except RuntimeError:
                continue

    def start(self):
        if not self.token:
            raise ValueError("Configure APP_ACCESS_TOKEN before starting the watch")
        with self.lock:
            if self.worker and self.worker.is_alive():
                if self.stop_event.is_set():
                    raise RuntimeError("Watch is still stopping; try again shortly")
                return self.status()
            self.lease.acquire()
            self.stop_event.clear()
            self._set(enabled=True, heartbeat_ts=now_ms(), worker_error=None, running=True)
            self.worker = threading.Thread(target=self._loop, name="crypto-breakout-watch", daemon=True)
            self.worker.start()
        return self.status()

    def stop(self):
        with self.lock:
            self.stop_event.set()
            self._set(enabled=False, running=False)
        return self.status()

    def shutdown(self):
        # Keep the persisted preference so an enabled watch resumes after a deploy.
        with self.lock:
            self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=2)
        if self.resume_worker:
            self.resume_worker.join(timeout=2)

    def _active(self):
        return not self.stop_event.is_set() and self._meta("enabled", False)

    def _loop(self):
        try:
            while self._active():
                scan_started = now_ms()
                self._scan()
                due = ((scan_started // STEP) + 1) * STEP + 15_000
                while self._active() and now_ms() < due:
                    self._set(heartbeat_ts=now_ms())
                    self.stop_event.wait(min(15, max(.1, (due - now_ms()) / 1000)))
        except Exception as exc:
            self._set(worker_error=type(exc).__name__ + ": " + str(exc)[:180])
        finally:
            self._set(running=False)
            self.lease.release()

    def _scan(self):
        observed = now_ms()
        with self.lock:
            if not self._active():
                return
            self._set(last_scan_started_ts=observed, heartbeat_ts=observed)
        btc = []
        for symbol in SYMBOLS:
            if not self._active():
                return
            try:
                rows = self.client.candles(symbol, observed)
                if symbol == "BTC-USD":
                    btc = rows
                result = evaluate(symbol, rows, btc, now_ms())
            except Exception as exc:
                result = {"symbol": symbol, "stage": "unavailable", "source": SOURCE,
                    "rule_version": VERSION, "observed_ts": now_ms(), "candle_end_ts": None, "metrics": {},
                    "reasons": ["Market data failed: " + type(exc).__name__ + ": " + str(exc)[:140]]}
            self._publish(result)
        if self._active() and now_ms() - self._meta("news_attempt_ts", 0) >= HOUR:
            self._news()
        with self.lock:
            if self._active():
                self._set(last_scan_finished_ts=now_ms(), heartbeat_ts=now_ms())

    def _publish(self, result):
        with self.lock:
            if not self._active():
                return
            with closing(db_connect(self.path)) as con, con:
                previous = con.execute("SELECT payload FROM watch_latest WHERE symbol=?", (result["symbol"],)).fetchone()
                previous = json.loads(previous[0]) if previous else None
                # A restart/gap is a current snapshot, not evidence that an onset was caught.
                initial = not previous or previous["stage"] == "unavailable" or (
                    result["observed_ts"] - previous["observed_ts"] > 2 * STEP)
                result = dict(result, initial_observation=initial)
                con.execute("INSERT OR REPLACE INTO watch_latest VALUES(?,?)", (result["symbol"], encode(result)))
                if result["stage"] in ("building", "breakout", "extended"):
                    recent = con.execute("SELECT MAX(observed_ts) FROM watch_alerts WHERE symbol=? AND stage=?",
                                         (result["symbol"], result["stage"])).fetchone()[0]
                    if recent is None or result["observed_ts"] - recent >= HOUR:
                        con.execute("INSERT OR IGNORE INTO watch_alerts(symbol,stage,candle_end_ts,observed_ts,payload) VALUES(?,?,?,?,?)",
                            (result["symbol"], result["stage"], result["candle_end_ts"], result["observed_ts"], encode(result)))
                con.execute("DELETE FROM watch_alerts WHERE observed_ts<?", (now_ms() - 90 * DAY,))
            self._set(heartbeat_ts=now_ms())

    def _news(self):
        attempt = now_ms()
        try:
            raw = self.news_fetch(NEWS_SOURCE)
            observed = now_ms()  # Availability is retrieval time, never a historical publication time.
            items = parse_feed(NEWS_SOURCE, raw, observed)
            if not items:
                raise ValueError("No dated headlines returned")
            with self.lock:
                if not self._active():
                    return
                with closing(db_connect(self.path)) as con, con:
                    for item in items[:200]:
                        if observed - 7 * DAY <= item["published_ts"] <= observed:
                            con.execute("INSERT OR IGNORE INTO watch_news VALUES(?,?,?,?)",
                                (item["id"], item["revision"], observed, encode(item)))
                    con.execute("DELETE FROM watch_news WHERE observed_ts<?", (observed - 30 * DAY,))
                self._set(news_attempt_ts=attempt, news_success_ts=observed, news_error=None)
        except Exception as exc:
            with self.lock:
                if self._active():
                    self._set(news_attempt_ts=attempt, news_error=type(exc).__name__ + ": " + str(exc)[:160])

    def status(self, compact=False):
        observed = now_ms()
        with closing(db_connect(self.path)) as con:
            meta = {r[0]: json.loads(r[1]) for r in con.execute("SELECT key,value FROM watch_meta")}
            latest = {r[0]: json.loads(r[1]) for r in con.execute("SELECT symbol,payload FROM watch_latest")}
            alerts = [json.loads(r[0]) for r in con.execute("SELECT payload FROM watch_alerts ORDER BY observed_ts DESC,id DESC LIMIT ?", (4 if compact else 100,))]
            news = [json.loads(r[0]) for r in con.execute("SELECT payload FROM watch_news ORDER BY observed_ts DESC,rowid DESC LIMIT ?", (4 if compact else 30,))]
        signals = []
        for symbol in SYMBOLS:
            saved = latest.get(symbol, {"symbol": symbol, "stage": "unavailable", "observed_ts": None,
                "candle_end_ts": None, "metrics": {}, "reasons": ["Not scanned yet"], "source": SOURCE})
            stale = not saved["observed_ts"] or observed - saved["observed_ts"] > 2 * STEP or (
                saved.get("candle_end_ts") is not None and observed - saved["candle_end_ts"] > 2 * STEP)
            signals.append(dict(saved, stale=bool(stale)))
        return {"version": VERSION, "enabled": meta.get("enabled", False), "requires_token": not bool(self.token),
            "running": bool(meta.get("running") and meta.get("enabled") and observed - meta.get("heartbeat_ts", 0) < 3 * STEP),
            "heartbeat_ts": meta.get("heartbeat_ts"), "worker_error": meta.get("worker_error"),
            "last_scan_started_ts": meta.get("last_scan_started_ts"), "last_scan_finished_ts": meta.get("last_scan_finished_ts"),
            "cadence_seconds": 300, "source": SOURCE, "execution_enabled": False, "signals": signals, "alerts": alerts,
            "news": {"source": "CoinDesk RSS headlines (limited coverage, hourly)", "items": news,
                "last_success_ts": meta.get("news_success_ts"), "last_attempt_ts": meta.get("news_attempt_ts"),
                "error": meta.get("news_error")},
            "limitations": "Experimental rules, not calibrated probabilities or buy recommendations. "
                "One venue and one news feed. Dashboard alerts only; no push/email. No crypto backtest or automatic paid AI research. "
                "A first snapshot cannot establish that a move was caught early."}

    def route(self, method, action, body):
        if method == "GET" and action in ("status", "export"):
            value = self.status()
            if action == "export":
                return 200, json.dumps(value, indent=2, allow_nan=False).encode(), {
                    "Content-Type": "application/json", "Content-Disposition": 'attachment; filename="crypto-watch-observations.json"'}
            return 200, value, {}
        if method == "POST" and action in ("start", "stop"):
            if not self.token:
                return 503, {"error": "Configure APP_ACCESS_TOKEN before controlling the watch"}, {}
            if body:
                raise ValueError("No options accepted; watch rules are fixed")
            return 200, self.start() if action == "start" else self.stop(), {}
        return 404, {"error": "Watch route not found"}, {}
