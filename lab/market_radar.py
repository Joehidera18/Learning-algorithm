"""Durable news, catalyst and watch journal; all collection happens off request threads."""
from __future__ import annotations

import json
import re
import uuid
from contextlib import closing
from datetime import date, datetime, timezone

from .crypto_watch import CryptoWatch, DAY, HOUR, STEP, encode, now_ms
from .equity_data import market_status
from .event_context import canonical_url, digest
from .paper_store import db_connect
from .radar_feeds import (ASSETS, STOCKS, CRYPTO, NAMES, FEEDS, StockSnapshots,
                          fetch_news, parse_news, source_error, stock_observation)

VERSION = "market-radar-v1"
SEEDS = (
    {"id": "seed-hbar-20260929", "symbol": "HBAR-USD", "title": "Hedera mainnet v0.77.2 upgrade",
     "date": "2026-09-29", "time_utc": "17:00", "status": "scheduled",
     "source_url": "https://status.hedera.com/incidents/hhd6nw87yrv5",
     "note": "Approximately 40 minutes; the official notice expects service disruption. A technical upgrade does not establish additional token demand."},
    {"id": "seed-ntla-20270310", "symbol": "NTLA", "title": "Lonvo-z FDA target decision date",
     "date": "2027-03-10", "time_utc": "", "status": "target",
     "source_url": "https://www.sec.gov/Archives/edgar/data/1652130/000119312526385194/ntla-ex99_1.htm",
     "note": "Company-reported PDUFA target following priority review. A target date is not approval; delays, safety findings and financing remain risks."},
)


def text_field(value, limit, required=True):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError("Text is missing or exceeds " + str(limit) + " characters")
    return value.strip()


def valid_symbol(value):
    if value not in ASSETS:
        raise ValueError("Choose a stock or cryptoasset in this watchlist")
    return value


def calendar_timing(item, observed):
    start = int(datetime.fromisoformat(item["date"] + "T" + (item["time_utc"] or "00:00") + "+00:00").timestamp() * 1000)
    end = start if item["time_utc"] else start + DAY
    active = item["status"] in ("scheduled", "target")
    return {"event_ts": start, "time_precision": "minute" if item["time_utc"] else "day",
        "upcoming": bool(active and end >= observed and start <= observed + 72 * HOUR),
        "past_due": bool(active and end < observed),
        "needs_source_check": not item.get("source_checked_on") or
            observed - int(datetime.fromisoformat(item["source_checked_on"] + "T00:00:00+00:00").timestamp()*1000) > 30 * DAY}


class MarketRadar(CryptoWatch):
    """Reuse the tested lease/restart/stop lifecycle, with an independent database."""
    def __init__(self, data_dir, token="", crypto_watch=None, news_fetch=None, snapshots=None):
        super().__init__(data_dir, token, database_name="market-radar.sqlite3")
        self.news_fetch = news_fetch or fetch_news
        self.snapshots = snapshots or StockSnapshots()
        self.crypto_watch = crypto_watch
        with closing(db_connect(self.path)) as con, con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS radar_sources (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS radar_news (id TEXT, revision TEXT, observed_ts INTEGER,
                    updated_ts INTEGER, headline_key TEXT, payload TEXT, PRIMARY KEY(id,revision));
                CREATE INDEX IF NOT EXISTS radar_news_time ON radar_news(updated_ts);
                CREATE INDEX IF NOT EXISTS radar_news_title ON radar_news(headline_key);
                CREATE TABLE IF NOT EXISTS radar_alerts (id TEXT PRIMARY KEY, observed_ts INTEGER, payload TEXT);
                CREATE INDEX IF NOT EXISTS radar_alert_time ON radar_alerts(observed_ts);
                CREATE TABLE IF NOT EXISTS radar_calendar (id TEXT PRIMARY KEY, version INTEGER, payload TEXT);
                CREATE TABLE IF NOT EXISTS radar_tracking (symbol TEXT PRIMARY KEY, payload TEXT);
                CREATE TABLE IF NOT EXISTS radar_prices (symbol TEXT PRIMARY KEY, payload TEXT);
                CREATE TABLE IF NOT EXISTS radar_changes (id INTEGER PRIMARY KEY, observed_ts INTEGER, payload TEXT);
            """)
            for seed in SEEDS:
                item = dict(seed, version=1, recorded_ts=now_ms(), source_checked_on="2026-09-29", origin="Researched starter entry")
                con.execute("INSERT OR IGNORE INTO radar_calendar VALUES(?,?,?)", (item["id"], 1, encode(item)))
            # User explicitly said HBAR was sold. No holdings or balances are inferred.
            con.execute("INSERT OR IGNORE INTO radar_tracking VALUES(?,?)", ("HBAR-USD", encode({
                "symbol": "HBAR-USD", "mode": "recently_sold", "note": "", "updated_ts": now_ms()})))

    def _scan(self):
        with self.lock:
            if not self._active():
                return
            self._set(last_scan_started_ts=now_ms(), heartbeat_ts=now_ms())
        for source in FEEDS:
            if not self._active():
                return
            self._collect(source)
        if not self._active():
            return
        self._prices()
        with self.lock:
            if self._active():
                observed = now_ms()
                self._calendar_alerts(observed)
                with closing(db_connect(self.path)) as con, con:
                    con.execute("DELETE FROM radar_news WHERE observed_ts<?", (observed - 90 * DAY,))
                    con.execute("DELETE FROM radar_news WHERE rowid NOT IN (SELECT rowid FROM radar_news ORDER BY observed_ts DESC LIMIT 5000)")
                    con.execute("DELETE FROM radar_alerts WHERE observed_ts<?", (observed - 90 * DAY,))
                    con.execute("DELETE FROM radar_alerts WHERE rowid NOT IN (SELECT rowid FROM radar_alerts ORDER BY observed_ts DESC LIMIT 2000)")
                self._set(last_scan_finished_ts=observed, heartbeat_ts=observed)

    @staticmethod
    def _alert(con, identity, kind, item, observed):
        value = {"kind": kind, "observed_ts": observed, "item": item}
        con.execute("INSERT OR IGNORE INTO radar_alerts VALUES(?,?,?)", (identity, observed, encode(value)))

    def _collect(self, source):
        attempt = now_ms()
        with closing(db_connect(self.path)) as con:
            row = con.execute("SELECT payload FROM radar_sources WHERE id=?", (source,)).fetchone()
        previous = json.loads(row[0]) if row else {}
        try:
            raw = self.news_fetch(source)
            observed = now_ms()
            items, rejected = parse_news(source, raw, observed)
            initial = not previous.get("success_ts")
            gap = not initial and attempt - previous["success_ts"] > 2 * STEP
            with self.lock:
                if not self._active():
                    return
                with closing(db_connect(self.path)) as con, con:
                    for item in items:
                        if con.execute("SELECT 1 FROM radar_news WHERE id=? AND revision=?", (item["id"], item["revision"])).fetchone():
                            continue
                        reprint = bool(con.execute("SELECT 1 FROM radar_news WHERE headline_key=? AND id!=? AND updated_ts>?",
                            (item["headline_key"], item["id"], item["updated_ts"] - 7 * DAY)).fetchone())
                        prior_revision = con.execute("SELECT payload FROM radar_news WHERE id=? ORDER BY observed_ts DESC,rowid DESC LIMIT 1", (item["id"],)).fetchone()
                        revised = bool(prior_revision)
                        timestamp_only = bool(prior_revision and json.loads(prior_revision[0]).get("content_key") == item["content_key"])
                        saved = dict(item, observed_ts=observed, available_ts=max(item["updated_ts"], observed),
                            initial_snapshot=initial, after_coverage_gap=gap, possible_reprint=reprint,
                            revised=revised, timestamp_only_update=timestamp_only, late_discovery=observed - item["updated_ts"] > 2 * HOUR)
                        con.execute("INSERT INTO radar_news VALUES(?,?,?,?,?,?)", (item["id"], item["revision"],
                            observed, item["updated_ts"], item["headline_key"], encode(saved)))
                        if (not initial and not reprint and not timestamp_only and not saved["late_discovery"] and item["category"] != "general"
                                and item["updated_ts"] >= previous.get("success_ts", 0) - 30_000):
                            self._alert(con, "news:" + item["id"] + item["revision"], "news", saved, observed)
                    health = {"attempt_ts": attempt, "success_ts": observed, "error": None,
                        "matched_items": len(items), "rejected_items": rejected}
                    con.execute("INSERT OR REPLACE INTO radar_sources VALUES(?,?)", (source, encode(health)))
                self._set(heartbeat_ts=observed)
        except Exception as exc:
            with self.lock:
                if self._active():
                    health = dict(previous, attempt_ts=attempt, error=source_error(exc))
                    with closing(db_connect(self.path)) as con, con:
                        con.execute("INSERT OR REPLACE INTO radar_sources VALUES(?,?)", (source, encode(health)))
                    self._set(heartbeat_ts=now_ms())

    def _prices(self):
        info, observed = self.snapshots.info(), now_ms()
        if not info["configured"] or info["error"]:
            return
        try:
            payload = self.snapshots.snapshots() if market_status(observed)["open"] else {}
            observed = now_ms()
            with self.lock:
                if not self._active():
                    return
                with closing(db_connect(self.path)) as con, con:
                    old = {r[0]: json.loads(r[1]) for r in con.execute("SELECT symbol,payload FROM radar_prices")}
                    for symbol in STOCKS:
                        item = stock_observation(symbol, payload.get(symbol), observed, info["feed"], old.get(symbol))
                        con.execute("INSERT OR REPLACE INTO radar_prices VALUES(?,?)", (symbol, encode(item)))
                        if item["stage"] in ("large_move", "momentum_change"):
                            direction = "up" if (item["change_pct"] if item["stage"] == "large_move" else item["interval_change_pct"]) > 0 else "down"
                            key = ":".join(("price", symbol, item["stage"], direction, item["session"]))
                            self._alert(con, key, "price", item, observed)
                self._set(stock_error=None, stock_attempt_ts=observed, stock_success_ts=observed, heartbeat_ts=observed)
        except Exception as exc:
            with self.lock:
                if self._active():
                    self._set(stock_error=source_error(exc), stock_attempt_ts=observed, heartbeat_ts=now_ms())

    def _calendar_alerts(self, observed):
        with closing(db_connect(self.path)) as con, con:
            for row in con.execute("SELECT payload FROM radar_calendar").fetchall():
                item = json.loads(row[0])
                if calendar_timing(item, observed)["upcoming"]:
                    self._alert(con, "calendar:" + item["id"] + ":" + str(item["version"]), "calendar", item, observed)

    def save_tracking(self, body):
        if set(body) != {"symbol", "mode", "note"} or body["mode"] not in ("watch", "holding", "recently_sold"):
            raise ValueError("Choose watch, holding or recently_sold and a note")
        value = {"symbol": valid_symbol(body["symbol"]), "mode": body["mode"],
            "note": text_field(body["note"], 1000, False), "updated_ts": now_ms()}
        with self.lock, closing(db_connect(self.path)) as con, con:
            con.execute("INSERT OR REPLACE INTO radar_tracking VALUES(?,?)", (value["symbol"], encode(value)))
        return self.status()

    def save_catalyst(self, body):
        if set(body) != {"id", "version", "symbol", "title", "date", "time_utc", "status", "source_url", "note"}:
            raise ValueError("Provide the catalyst fields and saved version")
        if type(body["version"]) is not int or body["version"] < 0:
            raise ValueError("Invalid catalyst version")
        ident = body["id"]
        if not isinstance(ident, str) or (ident and not re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", ident)):
            raise ValueError("Invalid catalyst ID")
        date_string = text_field(body["date"], 10)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_string) or not 2020 <= date.fromisoformat(date_string).year <= 2100:
            raise ValueError("Use a valid calendar date between 2020 and 2100")
        clock = body["time_utc"]
        if not isinstance(clock, str) or (clock and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock)):
            raise ValueError("Use HH:MM UTC or leave the time blank")
        if body["status"] not in ("scheduled", "target", "cancelled", "completed"):
            raise ValueError("Invalid catalyst status")
        value = {"id": ident or uuid.uuid4().hex, "symbol": valid_symbol(body["symbol"]),
            "title": text_field(body["title"], 200), "date": date_string, "time_utc": clock,
            "status": body["status"], "source_url": canonical_url(body["source_url"]),
            "note": text_field(body["note"], 1000, False), "recorded_ts": now_ms(),
            "source_checked_on": None, "origin": "User-supplied source; verify before acting"}
        with self.lock, closing(db_connect(self.path)) as con, con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT version,payload FROM radar_calendar WHERE id=?", (ident,)).fetchone() if ident else None
            if (ident and not row) or (row and row[0] != body["version"]) or (not ident and body["version"] != 0):
                raise RuntimeError("Catalyst changed or no longer exists. Reload it before saving.")
            if not ident and con.execute("SELECT count(*) FROM radar_calendar").fetchone()[0] >= 200:
                raise ValueError("The calendar holds at most 200 entries")
            value["version"] = (row[0] if row else 0) + 1
            con.execute("INSERT OR REPLACE INTO radar_calendar VALUES(?,?,?)", (value["id"], value["version"], encode(value)))
            con.execute("INSERT INTO radar_changes(observed_ts,payload) VALUES(?,?)", (value["recorded_ts"], encode({
                "before": json.loads(row[1]) if row else None, "after": value})))
        return self.status()

    def status(self, compact=False, symbol=""):
        if symbol:
            valid_symbol(symbol)
        observed = now_ms()
        with closing(db_connect(self.path)) as con:
            meta = {r[0]: json.loads(r[1]) for r in con.execute("SELECT key,value FROM watch_meta")}
            health = {r[0]: json.loads(r[1]) for r in con.execute("SELECT id,payload FROM radar_sources")}
            calendar = [json.loads(r[0]) for r in con.execute("SELECT payload FROM radar_calendar")]
            tracking = {r[0]: json.loads(r[1]) for r in con.execute("SELECT symbol,payload FROM radar_tracking")}
            prices = {r[0]: json.loads(r[1]) for r in con.execute("SELECT symbol,payload FROM radar_prices")}
            news = [json.loads(r[0]) for r in con.execute("SELECT payload FROM radar_news ORDER BY updated_ts DESC,observed_ts DESC LIMIT 200")]
            alerts = [json.loads(r[0]) for r in con.execute("SELECT payload FROM radar_alerts ORDER BY observed_ts DESC,rowid DESC LIMIT 200")]
            changes = [] if compact else [json.loads(r[0]) for r in con.execute("SELECT payload FROM radar_changes ORDER BY id DESC LIMIT 50")]
        sources = [dict(id=k, name=f["name"], url=f["url"], origin=f["origin"], symbols=f["symbols"],
            **health.get(k, {}), stale=observed - health.get(k, {}).get("success_ts", 0) > 2 * STEP) for k, f in FEEDS.items()]
        all_calendar = {c["id"]: c for c in calendar}
        calendar = [dict(c, **calendar_timing(c, observed)) for c in calendar if not symbol or c["symbol"] == symbol]
        calendar.sort(key=lambda c: (c["status"] in ("cancelled", "completed") or c["past_due"], c["event_ts"]))
        for alert in alerts:
            if alert["kind"] == "calendar":
                current = all_calendar.get(alert["item"]["id"])
                alert["superseded"] = not current or current["version"] != alert["item"]["version"] or not calendar_timing(current, observed)["upcoming"]
        matches = lambda item: not symbol or item.get("symbol") == symbol or symbol in item.get("assets", []) or "*" in item.get("assets", [])
        news = [n for n in news if matches(n)][:3 if compact else 50]
        alerts = [a for a in alerts if matches(a["item"])][:3 if compact else 50]
        running = bool(meta.get("running") and meta.get("enabled") and observed - meta.get("heartbeat_ts", 0) < 3 * STEP)
        result = {"version": VERSION, "enabled": meta.get("enabled", False), "running": running,
            "requires_token": not bool(self.token), "worker_error": meta.get("worker_error"),
            "last_scan_started_ts": meta.get("last_scan_started_ts"), "last_scan_finished_ts": meta.get("last_scan_finished_ts"),
            "cadence_seconds": 300, "watch_count": len(ASSETS),
            "source_issues": sum(bool(s["stale"] or s.get("error") or s.get("rejected_items")) for s in sources),
            "news": news, "alerts": alerts, "calendar": calendar[:3] if compact else calendar,
            "stock_connection": dict(self.snapshots.info(), error=meta.get("stock_error") or self.snapshots.info()["error"],
                last_success_ts=meta.get("stock_success_ts")),
            "execution_enabled": False, "notifications": "In-app journal only; no phone or email delivery from this server",
            "limitations": "Partial headline coverage, not all news. Topic matching is not a materiality or return model. "
                "Starter calendars are dated; user entries require source checks. No automatic paid AI research. "
                "Stock observations use regular hours and unadjusted prior closes; check splits and dividends. "
                "No volume confirmation or measured forecasting accuracy. Recently sold assets remain covered."}
        if compact:
            small = {k: result[k] for k in ("version", "enabled", "running", "requires_token", "worker_error",
                "last_scan_finished_ts", "watch_count", "source_issues", "execution_enabled")}
            small["upcoming"] = [{k: c[k] for k in ("symbol", "title", "date", "time_utc", "status", "needs_source_check")}
                for c in calendar if c["upcoming"]][:3]
            small["recent_alerts"] = [{"kind": a["kind"], "observed_ts": a["observed_ts"],
                "title": a["item"].get("title", a["item"].get("symbol", "") + " price observation")} for a in alerts[:3]]
            return small
        result.update(sources=sources, changes=changes,
            watchlist=[dict(symbol=s, name=NAMES[s], asset_class="stock" if s in STOCKS else "crypto",
                mode=tracking.get(s, {}).get("mode", "watch"), note=tracking.get(s, {}).get("note", ""),
                updated_ts=tracking.get(s, {}).get("updated_ts")) for s in ASSETS if not symbol or s == symbol],
            stock_prices=[dict(prices.get(s, {"symbol": s, "stage": "unavailable", "reason": "Not scanned yet", "price": None}),
                stale=not prices.get(s, {}).get("quote_ts") or observed - prices[s]["quote_ts"] > 2 * STEP,
                connection_error=bool(meta.get("stock_error"))) for s in STOCKS if not symbol or s == symbol],
            crypto_watch=self.crypto_watch.status(compact=True) if self.crypto_watch else None)
        return result

    def route(self, method, action, body, query=None):
        if method == "GET" and action in ("status", "export"):
            value = self.status(symbol=(query or {}).get("symbol", ""))
            if action == "export":
                return 200, json.dumps(value, indent=2, allow_nan=False).encode(), {
                    "Content-Type": "application/json", "Content-Disposition": 'attachment; filename="market-radar-journal.json"'}
            return 200, value, {}
        if method == "POST" and action in ("start", "stop", "tracking", "catalyst"):
            if not self.token:
                return 503, {"error": "Configure APP_ACCESS_TOKEN before changing Market Radar"}, {}
            if action in ("start", "stop"):
                if body:
                    raise ValueError("No start/stop options accepted")
                value = self.start() if action == "start" else self.stop()
            else:
                value = self.save_tracking(body) if action == "tracking" else self.save_catalyst(body)
            return 200, value, {}
        return 404, {"error": "Market Radar route not found"}, {}
