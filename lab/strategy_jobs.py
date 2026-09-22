"""Website queue for named strategy backtests. Historical only. No live orders."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .paper_store import db_connect


class StrategyLabJobs:
    def __init__(self, data_dir):
        self.folder = Path(data_dir) / "strategy-lab"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.db_path = self.folder / "jobs.sqlite3"
        self.lock = threading.Lock()
        self.worker = None
        self.stop_event = threading.Event()
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("CREATE TABLE IF NOT EXISTS lab_jobs (id TEXT PRIMARY KEY, created INTEGER, status TEXT, request_json TEXT, result_json TEXT, message TEXT)")
        finally:
            con.close()

    def catalog(self):
        from .equity_data import EquityData
        from .equity_research import DEFAULT_COSTS
        from strategies import list_strategies
        data = EquityData()
        return {"strategies": list_strategies(), "equity": data.catalog(), "default_costs": DEFAULT_COSTS,
                "scope": "Historical stock backtests. News is point-in-time. No live orders."}

    def status(self):
        con = db_connect(self.db_path)
        try:
            rows = [dict(r) for r in con.execute("SELECT id, created, status, request_json, message FROM lab_jobs ORDER BY created DESC LIMIT 40")]
        finally:
            con.close()
        jobs = []
        for row in rows:
            req = json.loads(row["request_json"])
            jobs.append({"id": row["id"], "created": row["created"], "status": row["status"],
                         "message": row["message"], "request": req})
        return {"jobs": jobs, "catalog": self.catalog(), "running": bool(self.worker and self.worker.is_alive())}

    def get(self, job_id):
        con = db_connect(self.db_path)
        try:
            row = con.execute("SELECT * FROM lab_jobs WHERE id=?", (job_id,)).fetchone()
        finally:
            con.close()
        if not row:
            raise ValueError("Strategy lab job not found")
        result = json.loads(row["result_json"]) if row["result_json"] else None
        return {"id": row["id"], "created": row["created"], "status": row["status"],
                "message": row["message"], "request": json.loads(row["request_json"]), "result": result}

    def start(self, request):
        from strategies import load_strategy
        allowed = {"strategy", "symbol", "decision", "context", "days", "provider", "news"}
        if not isinstance(request, dict) or set(request) - allowed:
            raise ValueError("Unknown strategy lab setting")
        name = request.get("strategy") or "orb_15m"
        load_strategy(name)
        symbol = (request.get("symbol") or "SPY").upper()
        decision = request.get("decision") or "5m"
        context = request.get("context") or ["15m", "1h"]
        if isinstance(context, str):
            context = [part.strip() for part in context.split(",") if part.strip()]
        days = int(request.get("days") or 59)
        provider = request.get("provider") or "yahoo"
        news = bool(request.get("news"))
        payload = {"strategy": name, "symbol": symbol, "decision": decision,
                   "context": context, "days": days, "provider": provider, "news": news}
        ident = "%s-%s-%s-%s" % (name, symbol, decision, int(time.time()))
        con = db_connect(self.db_path)
        try:
            with con:
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
            self.stop_event.clear()
            self.worker = threading.Thread(target=self._loop, daemon=True, name="strategy-lab")
            self.worker.start()

    def shutdown(self):
        self.stop_event.set()

    def _loop(self):
        while not self.stop_event.is_set():
            con = db_connect(self.db_path)
            try:
                row = con.execute("SELECT * FROM lab_jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            finally:
                con.close()
            if not row:
                return
            self._run(dict(row))

    def _patch(self, job_id, **fields):
        con = db_connect(self.db_path)
        try:
            with con:
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
        try:
            self._patch(job_id, status="running", message="Downloading stock candles")
            data = EquityData()
            snap = data.history(req["symbol"], req["decision"], req["days"], provider=req["provider"])
            frames = {}
            for interval in req.get("context") or []:
                if interval == req["decision"]:
                    continue
                cap = data.catalog()["providers"][req["provider"]]["max_days"][interval]
                frames[interval] = data.history(req["symbol"], interval, min(req["days"], cap), provider=req["provider"])["rows"]
            articles = None
            if req.get("news"):
                self._patch(job_id, status="running", message="Downloading point-in-time news")
                from news.massive_news import download
                start = snap["rows"][0]["ts"]
                end = snap["rows"][-1]["end_ts"]
                articles = download(req["symbol"], start, end)
            self._patch(job_id, status="running", message="Simulating strategy")
            strategy = load_strategy(req["strategy"])
            report = run_backtest(strategy, snap["rows"], req["decision"], dict(DEFAULT_COSTS),
                                  frames=frames or None, stock_execution=True, close_at_session_end=True,
                                  articles=articles)
            report["symbol"] = req["symbol"]
            report["provider"] = req["provider"]
            dest = self.folder / (job_id + ".json")
            write_report(report, dest)
            self._patch(job_id, status="complete", message="Strategy lab finished",
                        result={"eligible_for_bot": report["eligible_for_bot"],
                                "later": report["later"], "development": report["development"],
                                "later_higher_cost": report["later_higher_cost"],
                                "news_alignment": report.get("news_alignment"),
                                "coverage": report["coverage"], "report_path": str(dest)})
        except Exception as exc:
            self._patch(job_id, status="error", message=str(exc)[:300])
