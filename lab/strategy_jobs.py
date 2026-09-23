"""Website queue for named strategy backtests. Historical only. No live orders."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
import threading
import time
import uuid
from pathlib import Path

from .paper_store import db_connect
from .continuous import RuntimeLease
from .experiment_jobs import RESEARCH_SLOT


class StrategyLabJobs:
    def __init__(self, data_dir):
        self.folder = Path(data_dir) / "strategy-lab"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.db_path = self.folder / "jobs.sqlite3"
        self.lock = threading.Lock()
        self.worker = None
        self.stop_event = threading.Event()
        self.lease = RuntimeLease(str(self.db_path)+".worker")
        self.active_id = None
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("CREATE TABLE IF NOT EXISTS lab_jobs (id TEXT PRIMARY KEY, created INTEGER, status TEXT, request_json TEXT, result_json TEXT, message TEXT)")
        finally:
            con.close()

    def catalog(self):
        from .equity_data import EquityData
        from .equity_research import DEFAULT_COSTS
        from strategies import list_strategies, load_strategy
        from .strategy_lab import REPORT_VERSION
        data = EquityData()
        specs = {name:load_strategy(name) for name in list_strategies()}
        return {"report_version": REPORT_VERSION, "strategies": list_strategies(),
                "strategy_intervals": {name:list(spec.allowed_intervals) for name,spec in specs.items()},
                "strategy_details": {name:{"title":spec.title,"description":spec.description,
                    "modes":list(spec.supported_modes),"news_filter":spec.news_filter} for name,spec in specs.items()},
                "equity": data.catalog(), "default_costs": DEFAULT_COSTS,
                "scope": "Historical stock backtests. News is point-in-time. No live orders."}

    def status(self, limit=40, include_results=True):
        con = db_connect(self.db_path)
        try:
            fields = "id, created, status, request_json, message" + (",result_json" if include_results else "")
            rows = [dict(r) for r in con.execute("SELECT "+fields+" FROM lab_jobs ORDER BY created DESC,rowid DESC LIMIT ?", (limit,))]
            pending = con.execute("SELECT COUNT(*) FROM lab_jobs WHERE status IN ('queued','running')").fetchone()[0]
        finally:
            con.close()
        jobs = []
        for row in rows:
            req = json.loads(row["request_json"])
            jobs.append({"id": row["id"], "created": row["created"], "status": row["status"],
                         "message": row["message"], "request": req,
                         "result": self._result(row.get("result_json"))})
        return {"jobs": jobs, "catalog": self.catalog(), "running": self.active_id is not None,
                "pending_jobs":pending}

    @staticmethod
    def _result(raw):
        result = json.loads(raw) if raw else None
        if result:
            from .strategy_lab import REPORT_VERSION
            if result.get("report_version") != REPORT_VERSION:
                result["eligible_for_bot"] = False
                result["requires_rerun"] = True
        return result

    def get(self, job_id):
        if not isinstance(job_id, str) or not job_id or len(job_id) > 200:
            raise ValueError("Choose a saved stock backtest")
        con = db_connect(self.db_path)
        try:
            row = con.execute("SELECT * FROM lab_jobs WHERE id=?", (job_id,)).fetchone()
        finally:
            con.close()
        if not row:
            raise ValueError("Strategy lab job not found")
        result = self._result(row["result_json"])
        return {"id": row["id"], "created": row["created"], "status": row["status"],
                "message": row["message"], "request": json.loads(row["request_json"]), "result": result}

    def start(self, request):
        from strategies import load_strategy
        from .equity_data import EquityData, ticker
        from .study_plan import ACTIVE_INTERVALS
        allowed = {"strategy", "symbol", "decision", "context", "days", "provider", "news",
                   "settings", "starting_balance", "mode", "fractional_shares", "end_date"}
        if not isinstance(request, dict) or set(request) - allowed:
            raise ValueError("Unknown strategy lab setting")
        name = request.get("strategy") or "orb_15m"
        strategy = load_strategy(name)
        symbol = ticker(request.get("symbol") or "SPY")
        decision = request.get("decision") or "5m"
        if decision not in strategy.allowed_intervals:
            raise ValueError("%s requires one of: %s" % (name, ", ".join(strategy.allowed_intervals)))
        context = request.get("context", [])
        if isinstance(context, str):
            context = [part.strip() for part in context.split(",") if part.strip()]
        if not isinstance(context, list) or any(not isinstance(iv, str) or iv not in ACTIVE_INTERVALS for iv in context):
            raise ValueError("Choose supported context timeframes")
        context = list(dict.fromkeys(iv for iv in context if iv != decision))
        days = request.get("days", 59)
        provider = request.get("provider") or "yahoo"
        catalog = EquityData().catalog()["providers"]
        if not isinstance(provider, str) or provider not in catalog:
            raise ValueError("Choose a supported stock data provider")
        if not catalog[provider]["available"]:
            raise ValueError("Configure credentials for the selected provider")
        if type(days) is not int or not 1 <= days <= catalog[provider]["max_days"][decision]:
            raise ValueError("Days exceed the selected provider/timeframe limit")
        news = request.get("news", False)
        if not isinstance(news, bool):
            raise ValueError("News must be true or false")
        if news and not strategy.news_filter:
            raise ValueError("This strategy does not use a news filter")
        if news and not catalog["massive"]["available"]:
            raise ValueError("Configure MASSIVE_API_KEY before requesting the news filter")
        from .equity_research import validate_costs
        settings = validate_costs(request.get("settings", {}))
        balance = request.get("starting_balance", 500.)
        if (isinstance(balance, bool) or not isinstance(balance, (int, float)) or
                not math.isfinite(balance) or not 100 <= balance <= 1000000):
            raise ValueError("Starting paper balance must be between $100 and $1,000,000")
        mode = request.get("mode", "day")
        if mode not in strategy.supported_modes:
            raise ValueError("This strategy supports: "+", ".join(strategy.supported_modes))
        fractional = request.get("fractional_shares", True)
        if not isinstance(fractional, bool):
            raise ValueError("Choose fractional or whole shares")
        cutoff = (int(time.time()*1000)-20*60000)//60000*60000
        end_date = request.get("end_date")
        if end_date:
            if not isinstance(end_date, str) or len(end_date) != 10:
                raise ValueError("Use an ending date in YYYY-MM-DD form")
            requested_end = int(datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()*1000)
            if requested_end > int(time.time()*1000):
                raise ValueError("Choose an ending date in the past or today")
            cutoff = min(cutoff, requested_end)
        payload = {"strategy": name, "symbol": symbol, "decision": decision,
                   "context": context, "days": days, "provider": provider, "news": news,
                   "cutoff_ts":cutoff, "settings":settings, "starting_balance":balance,
                   "mode":mode, "fractional_shares":fractional, "end_date":end_date or None}
        ident = "%s-%s-%s-%s" % (name, symbol, decision, uuid.uuid4().hex[:12])
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("BEGIN IMMEDIATE")
                count = con.execute("SELECT COUNT(*) FROM lab_jobs WHERE status IN ('queued','running')").fetchone()[0]
                if count >= 4:
                    raise ValueError("Finish queued strategy lab jobs first")
                con.execute("INSERT INTO lab_jobs VALUES (?,?,?,?,NULL,?)",
                            (ident, int(time.time()), "queued", json.dumps(payload), "Queued stock strategy backtest"))
        finally:
            con.close()
        self.resume()
        return {"id": ident, "created": True}

    def resume(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return
            try:
                self.lease.acquire()
            except RuntimeError:
                return
            con = db_connect(self.db_path)
            try:
                with con:
                    con.execute("UPDATE lab_jobs SET status='error', message=? WHERE status='running'",
                        ("Interrupted by a server restart. Start a new backtest; partial results are not accepted.",))
            finally:
                con.close()
            self.stop_event.clear()
            self.worker = threading.Thread(target=self._loop, daemon=True, name="strategy-lab")
            self.worker.start()

    def shutdown(self):
        self.stop_event.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(timeout=2)

    def cancel(self, job_id):
        self.get(job_id)
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("UPDATE lab_jobs SET status='cancelled', message='Cancelled by user' WHERE id=? AND status IN ('queued','running')", (job_id,))
        finally:
            con.close()
        return self.get(job_id)

    def _loop(self):
        try:
            while not self.stop_event.is_set():
                con = db_connect(self.db_path)
                try:
                    row = con.execute("SELECT * FROM lab_jobs WHERE status='queued' ORDER BY created,rowid LIMIT 1").fetchone()
                finally:
                    con.close()
                if not row:
                    self.stop_event.wait(1)
                    continue
                # Stock learning and named-strategy jobs share a bounded server.
                if not RESEARCH_SLOT.acquire(timeout=.5):
                    continue
                try:
                    if self.stop_event.is_set():
                        return
                    self.active_id = row["id"]
                    if self.get(row["id"])["status"] == "queued":
                        self._run(dict(row))
                finally:
                    self.active_id = None
                    RESEARCH_SLOT.release()
        finally:
            self.lease.release()

    def _patch(self, job_id, **fields):
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("BEGIN IMMEDIATE")
                current = con.execute("SELECT status FROM lab_jobs WHERE id=?", (job_id,)).fetchone()
                if current and current["status"] == "cancelled":
                    return
                if "result" in fields:
                    con.execute("UPDATE lab_jobs SET status=?, message=?, result_json=? WHERE id=?",
                                (fields.get("status"), fields.get("message"), json.dumps(fields["result"]), job_id))
                else:
                    con.execute("UPDATE lab_jobs SET status=?, message=? WHERE id=?",
                                (fields.get("status"), fields.get("message"), job_id))
        finally:
            con.close()

    def _run(self, row):
        from .equity_data import EquityData
        from .equity_research import DEFAULT_COSTS
        from .strategy_lab import run_backtest, write_report
        from strategies import load_strategy
        job_id = row["id"]
        req = json.loads(row["request_json"])
        last_check, was_cancelled = 0., False
        def cancelled():
            nonlocal last_check, was_cancelled
            if self.stop_event.is_set():
                return True
            now = time.monotonic()
            if now-last_check >= .2:
                con = db_connect(self.db_path)
                try:
                    status = con.execute("SELECT status FROM lab_jobs WHERE id=?", (job_id,)).fetchone()
                    was_cancelled = not status or status[0] == "cancelled"
                finally:
                    con.close()
                last_check = now
            return was_cancelled
        def checkpoint():
            if cancelled():
                raise InterruptedError("Strategy backtest interrupted; start a new run to complete it")
        try:
            checkpoint()
            self._patch(job_id, status="running", message="Downloading stock candles")
            data = EquityData()
            cutoff = req.get("cutoff_ts") or (int(time.time()*1000)-20*60000)//60000*60000
            snap = data.history(req["symbol"], req["decision"], req["days"], cutoff=cutoff,
                                provider=req["provider"], cancelled=cancelled)
            frames = {}
            for interval in req.get("context") or []:
                if interval == req["decision"]:
                    continue
                cap = data.catalog()["providers"][req["provider"]]["max_days"][interval]
                self._patch(job_id, status="running", message="Downloading "+interval+" stock context candles")
                checkpoint()
                frames[interval] = data.history(req["symbol"], interval, min(req["days"], cap),
                    cutoff=cutoff, provider=req["provider"], cancelled=cancelled)["rows"]
            articles = None
            if req.get("news"):
                checkpoint()
                self._patch(job_id, status="running", message="Downloading point-in-time news")
                from news.massive_news import download
                start = snap["rows"][0]["ts"]
                end = snap["rows"][-1]["end_ts"]
                articles = download(req["symbol"], start, end, cancelled=cancelled)
            checkpoint()
            self._patch(job_id, status="running", message="Simulating strategy")
            strategy = load_strategy(req["strategy"])
            strategy.require_context = tuple(req.get("context") or ())
            report = run_backtest(strategy, snap["rows"], req["decision"], req.get("settings") or dict(DEFAULT_COSTS),
                starting_balance=req.get("starting_balance",500.), frames=frames or None,
                stock_execution=True, close_at_session_end=req.get("mode","day") == "day",
                fractional_shares=req.get("fractional_shares",True), articles=articles, cancelled=cancelled,
                progress=lambda message: self._patch(job_id,status="running",message=message))
            checkpoint()
            report["symbol"] = req["symbol"]
            report["provider"] = req["provider"]
            report["request"] = req
            report["market_data"] = snap.get("market_data", {})
            report["requested_coverage"] = snap.get("quality", {})
            report["holding_mode"] = req.get("mode", "day")
            dest = self.folder / (job_id + ".json")
            write_report(report, dest)
            self._patch(job_id, status="complete", message="Strategy lab finished",
                        result={"report_version": report["report_version"],
                                "eligible_for_bot": report["eligible_for_bot"],
                                "later": report["later"], "development": report["development"],
                                "later_higher_cost": report["later_higher_cost"],
                                "news_alignment": report.get("news_alignment"),
                                "coverage": report["coverage"], "requested_coverage":report["requested_coverage"],
                                "market_data":report["market_data"], "starting_balance":report["starting_balance"],
                                "costs":report["costs"], "holding_mode":report["holding_mode"],
                                "report_path": str(dest)})
        except Exception as exc:
            self._patch(job_id, status="error", message=str(exc)[:300])

    def report(self, job_id):
        job = self.get(job_id)
        if job["status"] != "complete":
            raise ValueError("Wait for this backtest to finish before opening its full report")
        path = self.folder/(job["id"]+".json")
        if not path.exists():
            raise ValueError("This saved run has no full report. Its summary remains available; run a new backtest for the journal.")
        report = json.loads(path.read_text())
        from .strategy_lab import REPORT_VERSION
        if report.get("report_version") != REPORT_VERSION:
            report.update(eligible_for_bot=False, requires_rerun=True)
        return report
