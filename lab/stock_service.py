"""The stock-only web application. No crypto runner or broker is constructed."""
from __future__ import annotations

import json
import hashlib
import re
import secrets
import time
from pathlib import Path

from .equity_jobs import EquityJobs
from .stock_research import EDITION, REPORT_NAME, report_bytes, research_payload
from .website_lab import attach, route as strategy_route

APP_VERSION = "12.1"
PAGES = {"/": "stock-dashboard.html", "/stocks": "stocks.html",
         "/stock-practice": "stock-practice.html", "/strategy-lab": "strategy-lab.html",
         "/backtests": "strategy-lab.html"}
ASSETS = {"style.css", "stocks.css", "stocks.js", "stock-practice.css", "stock-practice.js",
          "strategy-lab.js", "backtests.css", "stock-dashboard.css", "stock-dashboard.js", "stock-session.js"}
RETIRED_APIS = ("/api/coinbase/", "/api/continuous/", "/api/learning/", "/api/research/",
                "/api/vwap/", "/api/forward/", "/api/experiments/", "/api/events/", "/api/runs")


class StockService:
    def __init__(self, base_dir, db_path, data_dir, token=None, resume=True):
        self.base_dir = Path(base_dir)
        # Retain the old path as metadata only. Never open or change its journal.
        self.db_path, self.data_dir = Path(db_path), Path(data_dir)
        self.token = token or ""
        self.assets = {}
        for name in ASSETS:
            content = (self.base_dir/"static"/name).read_bytes()
            self.assets[name] = (content, hashlib.sha256(content).hexdigest()[:20])
        self.pages = {}
        for name in set(PAGES.values()):
            page = (self.base_dir/"templates"/name).read_text()
            page = re.sub(r'/static/([a-zA-Z0-9_.-]+)(?:\?v=[a-zA-Z0-9.]+)?',
                lambda m: '/static/'+m[1]+'?v='+self.assets[m[1]][1] if m[1] in self.assets else m[0], page)
            self.pages[name] = page.encode()
        self.equities = EquityJobs(self.data_dir)
        attach(self, resume=False)
        if resume:
            self.equities.resume()
            self.strategy_lab.resume()

    def shutdown(self):
        self.equities.shutdown()
        self.strategy_lab.shutdown()

    @staticmethod
    def export(value, filename):
        return 200, json.dumps(value, indent=2, allow_nan=False).encode(), {
            "Content-Type": "application/json",
            "Content-Disposition": f'attachment; filename="{filename}"'}

    def overview(self):
        practice = self.equities.status(compact=True, limit=8)
        lab = self.strategy_lab.status(limit=8, include_results=False)
        research = research_payload(self.base_dir)
        benchmarks = [
            ("SPY", "S&P 500 ETF", "AMEX:SPY"), ("QQQ", "Nasdaq-100 ETF", "NASDAQ:QQQ"),
            ("IWM", "Russell 2000 ETF", "AMEX:IWM"), ("DIA", "Dow Jones ETF", "AMEX:DIA"),
            ("AAPL", "Apple", "NASDAQ:AAPL"), ("MSFT", "Microsoft", "NASDAQ:MSFT")]
        universe = [{"ticker": t, "name": n, "market_symbol": s, "research": False}
                    for t, n, s in benchmarks]
        universe += [{"ticker": s["ticker"], "name": s["name"], "market_symbol": s["market_symbol"],
                      "research": True} for s in research["stocks"]]
        return {"app_version": APP_VERSION, "asset_class": "equity", "trading_mode": "paper",
                "live_orders_allowed": False, "updated_ts": int(time.time()*1000),
                "market": practice["market"], "catalog": practice["catalog"], "universe": universe,
                "research_as_of": research["research_as_of"],
                "practice": {k: practice[k] for k in ("total_jobs", "pending_jobs", "active_id")},
                "jobs": [{k: j[k] for k in ("id", "status", "manifest", "progress", "updated_at")}
                         for j in practice["jobs"][:8]],
                "forward": practice["forward"],
                "strategy_lab": {"running": lab["running"], "jobs": lab["jobs"][:8],
                                 "error": lab.get("error")}}

    def handle(self, method, path, query=None, body=None, headers=None):
        query = query or {}
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        try:
            if path.startswith("/api/") and path != "/api/health" and self.token:
                supplied = headers.get("authorization", "").removeprefix("Bearer ")
                if not secrets.compare_digest(supplied, self.token):
                    return 401, {"error": "Enter the access token configured for this app"}, {}
            if method == "POST":
                if headers.get("content-type", "").split(";")[0].strip() != "application/json":
                    return 415, {"error": "Send application/json"}, {}
                if not isinstance(body, dict):
                    return 400, {"error": "Request body must be a JSON object"}, {}
            normalized = path.rstrip("/") or "/"
            if method == "GET" and normalized in PAGES:
                return 200, self.pages[PAGES[normalized]], {
                    "Content-Type": "text/html; charset=utf-8"}
            if method == "GET" and normalized in ("/experiments", "/crypto", "/coinbase"):
                return 302, b"", {"Location": "/strategy-lab" if normalized == "/experiments" else "/"}
            if method == "GET" and path.startswith("/static/") and path.removeprefix("/static/") in ASSETS:
                name = path.removeprefix("/static/")
                mime = "application/javascript" if name.endswith(".js") else "text/css"
                content, version = self.assets[name]
                etag = 'W/"'+version+'"'
                extra = {"Content-Type": mime+"; charset=utf-8", "ETag":etag,
                         "Cache-Control": "public, max-age=31536000, immutable" if query.get("v") == version
                         else "public, max-age=0, must-revalidate"}
                if etag in headers.get("if-none-match", "").split(", ") or headers.get("if-none-match") == "*":
                    return 304, b"", extra
                return 200, content, extra
            if method == "GET" and path == "/api/health":
                return 200, {"ok": True, "api_version": "12.0", "app_version": APP_VERSION,
                    "asset_class": "equity", "market_scope": "US stocks and ETFs",
                    "default_mode": "paper", "live_capable": False, "live_orders_allowed": False,
                    "crypto_enabled": False, "starting_balance": 500,
                    "stock_research_version": EDITION, "stock_practice_version": "stock-practice-v1"}, {}
            if method == "GET" and path == "/api/stocks/overview":
                return 200, self.overview(), {}
            if path.startswith("/api/stocks/practice/"):
                return self.practice_route(method, path.removeprefix("/api/stocks/practice/"), query, body)
            if path.startswith("/api/strategy-lab/"):
                return strategy_route(self, method, path, query, body)
            if method == "GET" and path.startswith("/api/stocks/research"):
                if path == "/api/stocks/research/report":
                    return 200, report_bytes(self.base_dir), {"Content-Type": "text/markdown; charset=utf-8",
                        "Content-Disposition": f'attachment; filename="{REPORT_NAME}"'}
                data = research_payload(self.base_dir)
                if path == "/api/stocks/research":
                    return 200, data, {}
                if path == "/api/stocks/research/export":
                    return self.export(data, "stock-research-watchlist.json")
                symbol = path.removeprefix("/api/stocks/research/").upper()
                stock = next((s for s in data["stocks"] if s["ticker"] == symbol), None)
                if stock:
                    return 200, {"stock": stock, "research_as_of": data["research_as_of"],
                        "market_data_as_of": data["market_data_as_of"], "review": data["review"],
                        "live_quotes": False, "trading_enabled": False}, {}
            if any(path.startswith(prefix) for prefix in RETIRED_APIS):
                return 410, {"error": "Crypto workflows are retired. This app now runs stock research and paper trading.",
                             "redirect": "/", "crypto_enabled": False}, {}
            return 404, {"error": "Route not found"}, {}
        except (ValueError, TypeError) as exc:
            return 400, {"error": str(exc)}, {}
        except RuntimeError as exc:
            return 409, {"error": str(exc)}, {}

    def practice_route(self, method, action, query, body):
        if action == "status" and method == "GET":
            return 200, self.equities.status(compact=True), {}
        if action == "result" and method == "GET":
            return 200, self.equities.get(query.get("id")), {}
        if action == "start" and method == "POST":
            return 202, self.equities.start(body), {}
        operations = {"cancel": self.equities.cancel, "retry": self.equities.retry,
                      "forward/start": self.equities.start_forward, "forward/stop": self.equities.stop_forward}
        if action in operations and method == "POST":
            if set(body) != {"id"}:
                raise ValueError("Choose one stock practice ID")
            return 200, operations[action](body["id"]), {}
        if action == "forward/export" and method == "GET":
            return self.export(self.equities.forward_list(full=True), "stock-forward-journal.json")
        if action in ("export", "candles") and method == "GET":
            job = self.equities.get(query.get("id"), full=True)
            value = job
            if action == "candles":
                from .experiment_jobs import read_gzip
                stored = self.equities.snapshot_path(job["manifest"])
                if not stored.exists():
                    raise ValueError("Stock candles have not been downloaded for this run yet")
                value = read_gzip(stored)
            return self.export(value, "stock-"+action+".json")
        return 404, {"error": "Stock practice route not found"}, {}
