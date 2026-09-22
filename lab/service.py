"""Framework-independent request handlers; exercised directly by offline tests."""
import csv
import io
import json
import math
import os
import secrets
import tempfile
from pathlib import Path

from .continuous import ContinuousLearner, activity_rows, recent_trades, memory_leaderboard
from .db import init_db, list_runs, get_run
from .research import ResearchManager
from .coinbase_broker import CoinbaseAdapter
from .coinbase_live import CoinbaseTrader
from .autolearn import AutoLearner
from .stock_research import EDITION as STOCK_RESEARCH_EDITION


class Service:
    def __init__(self, base_dir, db_path, data_dir, token=None):
        self.base_dir, self.db_path, self.data_dir = Path(base_dir), Path(db_path), Path(data_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        init_db(self.db_path)
        self.agent = ContinuousLearner(self.db_path, self.data_dir)
        self.research = ResearchManager(self.db_path, self.data_dir)
        from .vwap_research import VwapResearchManager
        self.vwap = VwapResearchManager(self.db_path, self.data_dir)
        self.token = token or ""
        self.coinbase = CoinbaseTrader(self.db_path,self.agent,CoinbaseAdapter(
            key_file=os.getenv("COINBASE_KEY_FILE"),
            allow_live=os.getenv("COINBASE_ALLOW_LIVE")=="1"))
        self.autolearn = AutoLearner(self.db_path,self.data_dir,self.agent,self.research)
        from .event_store import EventCollector
        self.events = EventCollector(self.db_path)
        self.agent.events = self.events
        from .forward_study import ForwardStudies
        self.forward = ForwardStudies(self.db_path,self.autolearn,self.events)
        try:
            self.forward.resume()
        except RuntimeError:
            pass  # A different process holds this study's worker lease.
        if self.events.store.enabled():
            self.events.start()
        from .experiment_jobs import ExperimentJobs
        self.experiments = ExperimentJobs(self.db_path, self.data_dir, blocked=lambda: any(
            obj.worker and obj.worker.is_alive() for obj in (self.autolearn, self.research, self.vwap)))
        from .equity_jobs import EquityJobs
        self.equities = EquityJobs(self.data_dir, blocked=lambda: self.experiments.busy() or any(
            obj.worker and obj.worker.is_alive() for obj in (self.autolearn, self.research, self.vwap)))
        self.experiments.blocked = lambda: self.equities.busy() or any(
            obj.worker and obj.worker.is_alive() for obj in (self.autolearn, self.research, self.vwap))
        self.experiments.resume()
        self.equities.resume()

    def _limit(self, query, default=100):
        value = query.get("limit", str(default))
        if not str(value).isdigit() or not 1 <= int(value) <= 500:
            raise ValueError("limit must be a whole number between 1 and 500")
        return int(value)

    def handle(self, method, path, query=None, body=None, headers=None):
        query, headers = query or {}, {k.lower(): v for k, v in (headers or {}).items()}
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
            if hasattr(self, "strategy_lab"):
                from .website_lab import route
                routed = route(self, method, path, query, body)
                if routed is not None:
                    return routed
            if method == "GET" and path == "/":
                return 200, (self.base_dir / "templates/index.html").read_bytes(), {"Content-Type": "text/html; charset=utf-8"}
            if method == "GET" and path in ("/stocks", "/stocks/"):
                return 200, (self.base_dir / "templates/stocks.html").read_bytes(), {"Content-Type": "text/html; charset=utf-8"}
            if method == "GET" and path in ("/stock-practice", "/stock-practice/"):
                return 200, (self.base_dir / "templates/stock-practice.html").read_bytes(), {"Content-Type":"text/html; charset=utf-8"}
            if method == "GET" and path in ("/experiments", "/experiments/"):
                return 200, (self.base_dir / "templates/experiments.html").read_bytes(), {"Content-Type": "text/html; charset=utf-8"}
            if method == "GET" and path in ("/static/app.js", "/static/coinbase.js", "/static/style.css",
                                           "/static/stocks.js", "/static/stocks.css",
                                           "/static/experiments.js", "/static/experiments.css",
                                           "/static/stock-practice.js", "/static/stock-practice.css"):
                name = path.rsplit("/", 1)[-1]
                mime = "application/javascript; charset=utf-8" if name.endswith(".js") else "text/css; charset=utf-8"
                return 200, (self.base_dir / "static" / name).read_bytes(), {"Content-Type": mime}
            if method == "GET" and path == "/api/health":
                return 200, {"ok": True, "api_version": "11.0", "default_mode": "paper",
                             "live_capable":True, "starting_balance":500,
                             "stock_research_version":STOCK_RESEARCH_EDITION,
                             "app_version":"11.19", "stock_practice_version":"stock-practice-v1", "experiments_version":"controlled-experiments-v1"}, {}
            if path.startswith("/api/stocks/practice/"):
                prefix = "/api/stocks/practice/"
                action = path.removeprefix(prefix)
                if action == "status" and method == "GET":
                    return 200, self.equities.status(), {}
                if action == "start" and method == "POST":
                    return 202, self.equities.start(body), {}
                if action in ("cancel", "retry", "forward/start", "forward/stop") and method == "POST":
                    if set(body) != {"id"}:
                        raise ValueError("Choose one stock practice ID")
                    operation = {"cancel":self.equities.cancel,"retry":self.equities.retry,
                                 "forward/start":self.equities.start_forward,"forward/stop":self.equities.stop_forward}[action]
                    return 200, operation(body["id"]), {}
                if action in ("export", "candles", "forward/export") and method == "GET":
                    if action == "forward/export":
                        value = self.equities.forward_list(full=True)
                    else:
                        job = self.equities.get(query.get("id"),full=True)
                        value = job
                        if action == "candles":
                            from .experiment_jobs import read_gzip
                            stored = self.equities.snapshot_path(job["manifest"])
                            if not stored.exists():
                                raise ValueError("Stock candles have not been downloaded for this run yet")
                            value = read_gzip(stored)
                    return 200, json.dumps(value,indent=2,allow_nan=False).encode(), {
                        "Content-Type":"application/json","Content-Disposition":'attachment; filename="stock-practice.json"'}
                return 404, {"error":"Stock practice route not found"}, {}
            if path.startswith("/api/experiments/"):
                if path == "/api/experiments/status" and method == "GET":
                    return 200, self.experiments.status(), {}
                if path == "/api/experiments/start" and method == "POST":
                    return 202, self.experiments.start(body, dict(self.agent.settings)), {}
                if path in ("/api/experiments/cancel", "/api/experiments/retry") and method == "POST":
                    if set(body) != {"id"}:
                        raise ValueError("Choose one experiment ID")
                    action = self.experiments.cancel if path.endswith("/cancel") else self.experiments.retry
                    return 200, action(body["id"]), {}
                if path == "/api/experiments/export" and method == "GET":
                    return 200, json.dumps(self.experiments.get(query.get("id"), full=True), indent=2, allow_nan=False).encode(), {
                        "Content-Type":"application/json", "Content-Disposition":'attachment; filename="controlled-experiment.json"'}
                if path == "/api/experiments/planner" and method == "GET":
                    from .experiment_planner import planner_payload
                    return 200, planner_payload(self.db_path, self.experiments.status()["jobs"], len(self.token) >= 16), {}
                if path == "/api/experiments/planner" and method == "POST":
                    if body != {"mode":"openai"}:
                        raise ValueError("Use mode: openai for the optional AI planner")
                    if len(self.token) < 16:
                        raise RuntimeError("Configure protected app access before using paid AI planning")
                    from .experiment_planner import ai_plan, planner_context
                    context = planner_context(self.db_path, self.experiments.status()["jobs"])
                    return 200, ai_plan(self.db_path, context), {}
                if path == "/api/experiments/coverage" and method == "GET":
                    rows = json.loads((self.base_dir/"candle-coverage-2026-09-20.json").read_text())
                    return 200, {"as_of":"2026-09-20", "provider":"Binance", "quote_currency":"USDT",
                        "scope":"Dated archive inventory; not the Coinbase USD cache or a live coverage check",
                        "coins":[{k:r[k] for k in ("coin","pair","first_available_ts","end_ts_exclusive","timeframes")} for r in rows]}, {}
                if path == "/api/experiments/release-results" and method == "GET":
                    report = self.base_dir/"research"/"experiments-v11.18.json"
                    return (200, json.loads(report.read_text()), {}) if report.exists() else (200, {"reports":[]}, {})
                return 404, {"error":"Experiment route not found"}, {}
            if (method == "POST" and path in ("/api/learning/start", "/api/learning/practice", "/api/research/start",
                                               "/api/vwap/start", "/api/continuous/reset") and (self.experiments.busy() or self.equities.busy())):
                raise RuntimeError("Finish or cancel the active research task before starting another heavy task")
            if method == "GET" and path.startswith("/api/stocks/research"):
                from .stock_research import research_payload, report_bytes, REPORT_NAME
                if path == "/api/stocks/research/report":
                    return 200, report_bytes(self.base_dir), {"Content-Type": "text/markdown; charset=utf-8",
                        "Content-Disposition": f'attachment; filename="{REPORT_NAME}"'}
                if path in ("/api/stocks/research", "/api/stocks/research/export"):
                    data = research_payload(self.base_dir)
                    if path.endswith("/export"):
                        return 200, json.dumps(data, indent=2, allow_nan=False).encode(), {
                            "Content-Type": "application/json",
                            "Content-Disposition": 'attachment; filename="stock-research-watchlist.json"'}
                    return 200, data, {}
                if path.startswith("/api/stocks/research/"):
                    ticker = path.removeprefix("/api/stocks/research/").upper()
                    data = research_payload(self.base_dir)
                    stock = next((item for item in data["stocks"] if item["ticker"] == ticker), None)
                    if stock:
                        return 200, {"stock": stock, "research_as_of": data["research_as_of"],
                            "market_data_as_of": data["market_data_as_of"], "review": data["review"],
                            "live_quotes": False, "trading_enabled": False}, {}
                return 404, {"error": "Stock research not found"}, {}
            if (path == "/api/continuous/backup" and len(self.token)<16 and
                (self.coinbase.state.get("snapshot") or self.coinbase.trades(1))):
                raise RuntimeError("Set APP_ACCESS_TOKEN (at least 16 characters) before exporting private Coinbase account data")
            if path.startswith("/api/coinbase/"):
                if path=="/api/coinbase/status" and method=="GET":
                    if len(self.token)<16:
                        return 200, {"configured":self.coinbase.adapter.configured,"running":False,
                            "mode":"locked","live_orders_allowed":False,"snapshot":None,
                            "trades":[],"last_preview":None,"realized_pnl":"0","last_equity":None,
                            "equity_stale":True,"paused":False,"last_error":None,
                            "message":"Set APP_ACCESS_TOKEN (at least 16 characters) locally to unlock Coinbase controls"}, {}
                    return 200,self.coinbase.status(),{}
                if len(self.token)<16:
                    raise RuntimeError("Set APP_ACCESS_TOKEN (at least 16 characters) locally before using Coinbase")
                if method=="POST" and path in ("/api/coinbase/start","/api/coinbase/sync"):
                    mode = "sync" if path.endswith("/sync") else body.get("mode","preview")
                    if mode=="live" and body.get("confirm")!="ENABLE COINBASE LIVE":
                        raise ValueError("Enabling real Coinbase orders requires the exact confirmation phrase")
                    self.coinbase.start(mode)
                    return 202,{"ok":True,"coinbase":self.coinbase.status()},{}
                if method=="POST" and path=="/api/coinbase/stop":
                    self.coinbase.stop()
                    return 200,{"ok":True,"coinbase":self.coinbase.status()},{}
                if method=="POST" and path=="/api/coinbase/pause":
                    self.coinbase.pause(body.get("paused",True))
                    return 200,{"ok":True,"coinbase":self.coinbase.status()},{}
                if method=="POST" and path=="/api/coinbase/close":
                    self.coinbase.request_close()
                    return 202,{"ok":True,"message":"Close requested; cancellation and fills must reconcile first"},{}
                if method=="POST" and path=="/api/coinbase/apply-fees":
                    import time
                    snapshot = self.coinbase.status().get("snapshot")
                    if not snapshot or time.time()-snapshot["synced_at"]>300 or not snapshot["simple_fees"]:
                        raise ValueError("Sync a recent supported Coinbase fee tier first")
                    settings = self.agent.configure({"fee_rate":float(snapshot["taker_fee_rate"])})
                    return 200,{"ok":True,"settings":settings},{}
            if path == "/api/forward/status" and method == "GET":
                return 200,self.forward.status(),{}
            if path == "/api/vwap/status" and method == "GET":
                return 200, self.vwap.status(), {}
            if path == "/api/vwap/start" and method == "POST":
                if set(body)-{"symbols", "days", "fee_rate"}:
                    raise ValueError("VWAP research accepts symbols, days and fee_rate")
                settings = dict(self.agent.settings)
                if "fee_rate" in body:
                    fee = body["fee_rate"]
                    if isinstance(fee, bool) or not isinstance(fee, (int, float)) or not math.isfinite(fee) or not 0 <= fee <= .02:
                        raise ValueError("Fee fraction per side must be between 0 and 0.02")
                    settings["fee_rate"] = fee
                self.vwap.start(body.get("symbols", ["BTC-USD"]), body.get("days", 30), settings)
                return 202, self.vwap.status(), {}
            if path == "/api/vwap/cancel" and method == "POST":
                self.vwap.cancel()
                return 200, {"ok": True}, {}
            if path == "/api/vwap/export" and method == "GET":
                return 200, json.dumps(self.vwap.export(), indent=2, allow_nan=False).encode(), {
                    "Content-Type": "application/json", "Content-Disposition": 'attachment; filename="vwap-research.json"'}
            if path == "/api/forward/start" and method == "POST":
                if set(body)!={"symbol","interval","fingerprint"}:
                    raise ValueError("Choose one saved report for a fixed 30-day study")
                ident=self.forward.start(body["symbol"],body["interval"],body["fingerprint"])
                return 202,{"id":ident},{}
            if path == "/api/forward/stop" and method == "POST":
                self.forward.stop()
                return 200,{"ok":True},{}
            if path == "/api/forward/export" and method == "GET":
                return 200,json.dumps(self.forward.export(query.get("id")),allow_nan=False).encode(),{
                    "Content-Type":"application/json","Content-Disposition":'attachment; filename="forward-study.json"'}
            if path == "/api/events/status" and method == "GET":
                return 200,self.events.status(),{}
            if path == "/api/events/export" and method == "GET":
                return 200,json.dumps(self.events.snapshot(),indent=2,allow_nan=False).encode(),{
                    "Content-Type":"application/json",
                    "Content-Disposition":'attachment; filename="market-events.json"'}
            if path in ("/api/events/start","/api/events/stop") and method == "POST":
                if body:
                    raise ValueError("Event controls do not accept source URLs or settings")
                if path.endswith("/start"):self.events.start()
                else:self.events.stop()
                return 202,self.events.status(),{}
            if path == "/api/learning/status" and method == "GET":
                return 200, self.autolearn.status(compact=True), {}
            if path == "/api/learning/report" and method == "GET":
                return 200, self.autolearn.report_details(query.get("symbol"),
                    query.get("interval"), query.get("fingerprint")), {}
            if path == "/api/learning/start" and method == "POST":
                if set(body)-{"fee_rate"}:
                    raise ValueError("Automatic start accepts only the fee_rate setting")
                fees = {"fee_rate":body["fee_rate"]} if "fee_rate" in body else None
                self.autolearn.start(fees)
                self.events.start()
                return 202, {"ok":True,"learning":self.autolearn.status()}, {}
            if path == "/api/learning/practice" and method == "POST":
                if set(body)-{"fee_rate", "symbols", "intervals", "history_days"}:
                    raise ValueError("Historical practice accepts only fee_rate, symbols, intervals and history_days")
                fees = {"fee_rate":body["fee_rate"]} if "fee_rate" in body else None
                from .study_plan import HISTORY_DAYS
                self.autolearn.start_history(body.get("symbols"), fees, body.get("intervals"),
                    body.get("history_days", HISTORY_DAYS))
                self.events.start()
                return 202, {"ok":True,"learning":self.autolearn.status()}, {}
            if path == "/api/learning/stop" and method == "POST":
                self.autolearn.stop()
                return 200, {"ok":True,"learning":self.autolearn.status()}, {}
            if path == "/api/learning/export" and method == "GET":
                return 200, json.dumps(self.autolearn.export(),indent=2,allow_nan=False).encode(), {
                    "Content-Type":"application/json", "Content-Disposition":'attachment; filename="learning-results.json"'}
            if path == "/api/learning/data" and method == "GET":
                from .research_bundle import market_bundle
                content, filename = market_bundle(self.autolearn,query.get("symbol"),query.get("interval"))
                return 200,content,{"Content-Type":"application/zip",
                    "Content-Disposition":f'attachment; filename="{filename}"'}
            if path == "/api/continuous/status" and method == "GET":
                return 200, self.agent.status(), {}
            if path == "/api/continuous/settings":
                if method == "GET":
                    return 200, dict(self.agent.settings), {}
                if method == "POST":
                    return 200, {"ok": True, "settings": self.agent.configure(body)}, {}
            if path == "/api/continuous/start" and method == "POST":
                if body:
                    self.agent.configure(body)
                self.agent.start()
                self.events.start()
                return 200, {"ok": True, "status": self.agent.status()}, {}
            if path == "/api/continuous/stop" and method == "POST":
                self.autolearn.stop()
                self.agent.stop()
                return 200, {"ok": True, "status": self.agent.status()}, {}
            if path == "/api/continuous/pause" and method == "POST":
                self.agent.configure({"entries_paused": body.get("paused", True)})
                return 200, {"ok": True, "status": self.agent.status()}, {}
            if path == "/api/continuous/reset" and method == "POST":
                if body.get("confirm") != "RESET":
                    raise ValueError("Reset requires confirm: RESET")
                keep = body.get("keep_memory", True)
                if not isinstance(keep, bool):
                    raise ValueError("keep_memory must be true or false")
                if self.autolearn.worker and self.autolearn.worker.is_alive():
                    raise ValueError("Stop automatic learning before resetting the account")
                if self.research.worker and self.research.worker.is_alive():
                    raise ValueError("Cancel research and wait for it to finish before resetting")
                self.agent.reset(keep)
                return 200, {"ok": True, "status": self.agent.status()}, {}
            if path == "/api/continuous/close" and method == "POST":
                return 200, self.agent.close_manual(str(body.get("product_id", ""))), {}
            if path == "/api/continuous/trades" and method == "GET":
                return 200, recent_trades(self.db_path, self._limit(query)), {}
            if path == "/api/continuous/activity" and method == "GET":
                return 200, activity_rows(self.db_path, self._limit(query)), {}
            if path == "/api/continuous/opportunities" and method == "GET":
                return 200, self.agent.opportunity_board(30), {}
            if path == "/api/continuous/memory" and method == "GET":
                return 200, memory_leaderboard(self.db_path, 50), {}
            if path == "/api/continuous/analytics" and method == "GET":
                return 200, self.agent.analytics(), {}
            if path == "/api/research/status" and method == "GET":
                return 200, self.research.status(), {}
            if path == "/api/research/start" and method == "POST":
                if self.autolearn.worker and self.autolearn.worker.is_alive():
                    raise ValueError("Stop automatic learning before running a manual research experiment")
                self.research.start(body.get("symbols", ["BTC-USD"]), body.get("days", 180), self.agent.settings)
                return 202, {"ok": True, "research": self.research.status()}, {}
            if path == "/api/research/cancel" and method == "POST":
                self.research.cancel()
                return 200, {"ok": True}, {}
            if path == "/api/research/export" and method == "GET":
                data = json.dumps(self.research.status(), indent=2, allow_nan=False).encode()
                return 200, data, {"Content-Type": "application/json", "Content-Disposition": 'attachment; filename="research-results.json"'}
            if path == "/api/continuous/export" and method == "GET":
                from .paper_store import db_connect, review_from_decision
                con = db_connect(self.db_path)
                records = [dict(r) for r in con.execute("""SELECT id,opened_at,closed_at,product_id,family,direction,
                    entry,exit,qty,risk_usd,status,pnl,result_r,balance_after,exit_reason,decision_json FROM paper_trades ORDER BY id""")]
                con.close()
                fields = ["id", "opened_at", "closed_at", "product_id", "family", "direction", "entry", "exit", "qty",
                          "risk_usd", "status", "pnl", "result_r", "balance_after", "exit_reason", "trade_review_json"]
                output = io.StringIO(newline="")
                writer = csv.DictWriter(output, fieldnames=fields)
                writer.writeheader()
                for record in records:
                    record["trade_review_json"] = json.dumps(review_from_decision(record.pop("decision_json")),allow_nan=False)
                    for k, value in record.items():
                        if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
                            record[k] = "'" + value
                    writer.writerow(record)
                return 200, output.getvalue().encode(), {"Content-Type": "text/csv", "Content-Disposition": 'attachment; filename="paper-trades.csv"'}
            if path == "/api/continuous/backup" and method == "GET":
                handle, filename = tempfile.mkstemp(suffix=".sqlite3")
                os.close(handle)
                try:
                    self.agent.backup(filename)
                    data = Path(filename).read_bytes()
                finally:
                    Path(filename).unlink(missing_ok=True)
                return 200, data, {"Content-Type": "application/octet-stream", "Content-Disposition": 'attachment; filename="crypto-account-backup.sqlite3"'}
            if path == "/api/runs" and method == "GET":
                return 200, list_runs(self.db_path, 100), {}
            if path.startswith("/api/runs/") and method == "GET":
                value = get_run(self.db_path, int(path.rsplit("/", 1)[-1]))
                return (200, value, {}) if value else (404, {"error": "Run not found"}, {})
            return 404, {"error": "Route not found"}, {}
        except (ValueError, TypeError) as exc:
            return 400, {"error": str(exc)}, {}
        except RuntimeError as exc:
            return 409, {"error": str(exc)}, {}


def wsgi_application(service):
    from urllib.parse import parse_qs
    from http import HTTPStatus

    def application(environ, start_response):
        method, path = environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "/")
        body = None
        headers = {"content-type": environ.get("CONTENT_TYPE", ""),
                   "authorization": environ.get("HTTP_AUTHORIZATION", "")}
        extra = {}
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
            if length > 32768:
                status, payload = 413, {"error": "Request is too large"}
            else:
                if method == "POST":
                    raw = environ["wsgi.input"].read(length)
                    try:
                        body = json.loads(raw) if raw else {}
                    except (ValueError, UnicodeError):
                        status, payload = 400, {"error": "Malformed JSON"}
                    else:
                        status, payload, extra = service.handle(method, path,
                            {k: v[-1] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}, body, headers)
                else:
                    status, payload, extra = service.handle(method, path,
                        {k: v[-1] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}, body, headers)
        except Exception:
            import logging
            logging.exception("Request failed")
            status, payload = 500, {"error": "Internal error; see the local application log"}
        if not isinstance(payload, bytes):
            payload = json.dumps(payload, allow_nan=False).encode()
            extra.setdefault("Content-Type", "application/json")
        extra.update({"Content-Length": str(len(payload)), "Cache-Control": "no-store",
                      "X-Content-Type-Options": "nosniff"})
        start_response(f"{status} {HTTPStatus(status).phrase}", list(extra.items()))
        return [payload]
    return application
