"""Persistent stock research and forward paper practice, isolated from crypto."""
from __future__ import annotations

import copy
import json
import math
import shutil
import threading
import time
from bisect import bisect_left
from pathlib import Path

from .equity_data import EquityData, INTERVALS, DAY, ticker, market_status
from .equity_research import VERSION, DEFAULT_COSTS, validate_costs, run_stock_practice, features_for, stock_policy, stock_params, execute
from .experiment_jobs import ExperimentJobs, ACTIVE, Cancellation, RESEARCH_SLOT, encoded, write_gzip, read_gzip
from .experiments import digest, fixed_params, account_report
from .forward_study import source_digest
from .paper_store import db_connect


class EquityJobs(ExperimentJobs):
    def __init__(self, data_dir, client=None, blocked=None):
        root = Path(data_dir)/"equity-practice"
        root.mkdir(parents=True, exist_ok=True)
        super().__init__(root/"state.sqlite3", root, blocked=blocked)
        self.folder = root
        self.client = client or EquityData()
        self.last_forward_poll = 0
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("CREATE TABLE IF NOT EXISTS equity_forward (id TEXT PRIMARY KEY, status TEXT NOT NULL, state_json TEXT NOT NULL)")
        finally:
            con.close()

    def _row(self, row, full=False):
        result = super()._row(row, full)
        if not full and result["result"]:
            result["result"].pop("model", None)
        return result

    def status(self, compact=False, limit=100):
        if compact:
            con = db_connect(self.db_path)
            try:
                rows = con.execute("""SELECT id,created_at,updated_at,status,manifest_json,progress_json
                    FROM experiment_jobs ORDER BY created_at DESC,rowid DESC LIMIT ?""", (limit,)).fetchall()
                total = con.execute("SELECT COUNT(*) FROM experiment_jobs").fetchone()[0]
                active = con.execute("SELECT COUNT(*) FROM experiment_jobs WHERE status IN (?,?,?,?,?)", ACTIVE).fetchone()[0]
            finally:
                con.close()
            jobs = [{**{k:r[k] for k in ("id","created_at","updated_at","status")},
                     "manifest":json.loads(r["manifest_json"]), "progress":json.loads(r["progress_json"]),
                     "result":None, "result_available":r["status"] == "complete"} for r in rows]
            value = {"jobs":jobs, "total_jobs":total, "pending_jobs":active, "active_id":self.active_id,
                     "worker_alive":bool(self.worker and self.worker.is_alive()),
                     "blocked_by_other_research":bool(self.blocked()), "eligible_for_trading":False}
        else:
            value = super().status()
        value.update(version=VERSION, catalog={**self.client.catalog(), "default_costs":DEFAULT_COSTS},
                     market=market_status(), forward=self.forward_list(), asset_class="equity",
                     scope="Historical learning and delayed forward paper practice for US stocks and ETFs. No stock orders.")
        value["restart_policy"] = "Resume with the same code and original stock snapshot; interrupted historical calculations are rerun."
        return value

    def retry(self, job_id):
        super().retry(job_id)
        self._patch(job_id,message="Requeued with original stock candles, cutoff and costs")
        return self.get(job_id)

    def start(self, request, settings=None):
        allowed = {"symbol","interval","days","provider","feed","mode","fractional_shares","settings"}
        if not isinstance(request, dict) or set(request)-allowed:
            raise ValueError("Unknown stock practice setting")
        symbol = ticker(request.get("symbol", "SPY"))
        interval = request.get("interval", "1h")
        mode = request.get("mode", "swing")
        provider, feed = request.get("provider", "yahoo"), request.get("feed", "sip")
        catalog = self.client.catalog()
        if interval not in INTERVALS or mode not in ("day", "swing") or provider not in catalog["providers"] or feed not in ("sip","iex"):
            raise ValueError("Choose a supported stock timeframe, holding style and data feed")
        if interval == "1d" and mode == "day":
            raise ValueError("Daily candles support swing practice; choose intraday candles for day trading")
        if not catalog["providers"][provider]["available"]:
            raise ValueError("Configure the selected data provider on the server first")
        days, fractional = request.get("days",365), request.get("fractional_shares",True)
        limit = catalog["providers"][provider]["max_days"][interval]
        if isinstance(days,bool) or not isinstance(days,int) or not 1 <= days <= limit or type(fractional) is not bool:
            raise ValueError(f"Choose 1–{limit} whole days and a valid share-sizing option")
        cutoff = (int(time.time()*1000)-20*60000)//60000*60000
        manifest = {"version":VERSION, "symbol":symbol, "interval":interval, "days":days,
            "provider":provider, "feed":feed if provider == "alpaca" else provider, "mode":mode,
            "fractional_shares":fractional, "settings":validate_costs(request.get("settings",{})),
            "cutoff_ts":cutoff, "source_sha256":self.code_hash, "asset_class":"equity"}
        job_id = digest(manifest)
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("BEGIN IMMEDIATE")
                exists = con.execute("SELECT 1 FROM experiment_jobs WHERE id=?", (job_id,)).fetchone()
                if not exists:
                    count = con.execute("SELECT COUNT(*) FROM experiment_jobs WHERE status IN (?,?,?,?,?)", ACTIVE).fetchone()[0]
                    total = con.execute("SELECT COUNT(*) FROM experiment_jobs").fetchone()[0]
                    if count >= 12 or total >= 100 or shutil.disk_usage(self.folder).free < 150*1024*1024:
                        raise ValueError("Stock practice queue or storage limit reached; finish queued work and export the archive")
                    now = int(time.time())
                    con.execute("INSERT INTO experiment_jobs VALUES (?,?,?,?,?,?,NULL,NULL)",
                        (job_id,now,now,"queued",encoded(manifest),encoded({"message":"Queued for stock learning and comparison", "attempts":0})))
        finally:
            con.close()
        self.resume()
        return {"ids":[job_id], "created":int(not exists), "cutoff_ts":cutoff}

    def snapshot_path(self, manifest):
        identity = {k:manifest[k] for k in ("symbol","interval","days","cutoff_ts","provider","feed")}
        return self.folder/"snapshots"/(digest(identity)+".json.gz")

    def _run_job(self, job):
        job_id, m = job["id"], job["manifest"]
        if m["source_sha256"] != self.code_hash or source_digest() != self.code_hash:
            self._patch(job_id, status="code_changed", message="Code changed; start a new stock practice run")
            return
        cancellation = Cancellation(self, job_id)
        def progress(stage, message):
            if cancellation.is_set():
                raise InterruptedError("Stock practice paused")
            self._patch(job_id, status=stage, message=message)
        progress("downloading", "Downloading observed regular-session stock candles")
        path = self.snapshot_path(m)
        if path.exists():
            snapshot = read_gzip(path)
            if digest(snapshot["rows"]) != snapshot["data_sha256"]:
                raise ValueError("Stock snapshot integrity check failed")
        else:
            snapshot = self.client.history(m["symbol"],m["interval"],m["days"],m["cutoff_ts"],
                m["provider"], m["feed"] if m["provider"] == "alpaca" else "sip", cancellation.is_set)
            snapshot["data_sha256"] = digest(snapshot["rows"])
            write_gzip(path,snapshot)
        self._patch(job_id, candles=len(snapshot["rows"]), data_sha256=snapshot["data_sha256"])
        result = run_stock_practice(snapshot,m,progress,cancellation.is_set)
        self._patch(job_id,status="complete",result=result,message="Stock practice complete; compare net results and evidence counts")

    def forward_list(self, full=False):
        import json
        con = db_connect(self.db_path)
        try:
            # The UI needs account marks, not every saved trade. Remove the
            # journal in SQLite before transferring/parsing it in Python.
            fields = "state_json" if full else "json_remove(state_json, '$.account.trades') AS state_json"
            values = [dict(json.loads(r["state_json"]), id=r["id"], status=r["status"])
                      for r in con.execute("SELECT id,status,"+fields+" FROM equity_forward ORDER BY rowid DESC")]
        finally:
            con.close()
        if not full:
            for v in values:
                if v.get("account"):
                    v["account"].pop("trades",None)
        return values

    def _save_forward(self, identity, status, state, insert=False):
        con = db_connect(self.db_path)
        try:
            with con:
                if insert:
                    con.execute("INSERT INTO equity_forward VALUES (?,?,?)",(identity,status,encoded(state)))
                else:
                    # A user's stop takes precedence over a completing refresh.
                    con.execute("UPDATE equity_forward SET status=?,state_json=? WHERE id=? AND status='running'",
                                (status,encoded(state),identity))
        finally:
            con.close()

    def start_forward(self, job_id):
        with self.lock:
            states = self.forward_list()
            if any(s["status"] == "running" for s in states):
                raise ValueError("Stop the current stock forward account before starting another")
            if len(states) >= 30:
                raise ValueError("Export the forward archive before extending the 30-account limit")
            job = self.get(job_id,full=True)
            if job["status"] != "complete" or job["manifest"]["source_sha256"] != self.code_hash:
                raise ValueError("Choose completed stock practice from the current code version")
            if not job["result"]["seed"]["resolved_examples"]:
                raise ValueError("This stock run has no resolved learning examples; collect more history first")
            created = int(time.time()*1000)
            identity = digest({"job":job_id,"created":created})
            state = {"job_id":job_id,"created_ts":created,"symbol":job["manifest"]["symbol"],
                "interval":job["manifest"]["interval"], "mode":job["manifest"]["mode"],
                "source_sha256":self.code_hash,"updated_ts":None,"account":None,
                "message":"Waiting for a signal candle to close after registration, then its next observed fill candle",
                "scope":"Delayed forward paper simulation, never a broker account; only post-registration signals can trade."}
            snapshot = read_gzip(self.snapshot_path(job["manifest"]))
            if digest(snapshot["rows"]) != snapshot["data_sha256"]:
                raise ValueError("The source snapshot changed")
            write_gzip(self.folder/"forward"/(identity+".json.gz"),snapshot)
            self._save_forward(identity,"running",state,insert=True)
            self.resume()
            return {"id":identity,**state,"status":"running"}

    def stop_forward(self, identity):
        with self.lock:
            state = next((s for s in self.forward_list(full=True) if s["id"] == identity),None)
            if not state:
                raise ValueError("Stock forward account not found")
            state["message"] = "Stopped. Last observed account mark retained; no later fills are assumed."
            self._save_forward(identity,"stopped",state)
            return {**state,"status":"stopped"}

    def resume(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return
            if not self._next() and not any(s["status"] == "running" for s in self.forward_list()):
                return
            try:
                self.lease.acquire()
            except RuntimeError:
                return
            self.stop_event.clear()
            self.worker = threading.Thread(target=self._loop,daemon=True,name="stock-practice")
            self.worker.start()

    def _loop(self):
        try:
            while not self.stop_event.is_set():
                if self.blocked():
                    self.stop_event.wait(1)
                    continue
                job = self._next()
                if job:
                    self.active_id = job["id"]
                    try:
                        with RESEARCH_SLOT:
                            self._run_job(job)
                    except InterruptedError:
                        self._patch(job["id"],status="queued",message="Paused; original data snapshot retained")
                    except Exception as exc:
                        self._patch(job["id"],status="error",message=str(exc)[:300])
                    finally:
                        self.active_id = None
                elif time.time()-self.last_forward_poll >= 60:
                    self.last_forward_poll = time.time()
                    for state in self.forward_list(full=True):
                        if state["status"] != "running":
                            continue
                        self.active_id = state["id"]
                        try:
                            with RESEARCH_SLOT:
                                self._forward_tick(state)
                        except InterruptedError:
                            pass
                        except Exception as exc:
                            state["message"] = "Paused: "+str(exc)[:300]
                            self._save_forward(state["id"],"error",state)
                        finally:
                            self.active_id = None
                self.stop_event.wait(1)
        finally:
            self.lease.release()

    def _forward_tick(self, state):
        if state["source_sha256"] != self.code_hash:
            raise ValueError("Code changed; complete new stock practice and register a new forward account")
        job = self.get(state["job_id"],full=True)
        m, model = job["manifest"], job["result"]["model"]
        path = self.folder/"forward"/(state["id"]+".json.gz")
        snapshot = read_gzip(path)
        if digest(snapshot["rows"]) != snapshot["data_sha256"]:
            raise ValueError("Forward candle snapshot integrity check failed")
        old = snapshot["rows"]
        cutoff = (int(time.time()*1000)-20*60000)//60000*60000
        if cutoff <= old[-1]["end_ts"] or cutoff < old[-1]["next_ts"]:
            return
        days = max(2,math.ceil((cutoff-old[-1]["ts"])/DAY)+1)
        limit = self.client.catalog()["providers"][m["provider"]]["max_days"][m["interval"]]
        if days > limit:
            raise ValueError("The data outage exceeds provider retention; no missing prices can be reconstructed")
        update = self.client.history(m["symbol"],m["interval"],days,cutoff,m["provider"],
                                     m["feed"] if m["provider"] == "alpaca" else "sip",self.stop_event.is_set)
        indexed = {r["ts"]:r for r in old}
        for row in update["rows"]:
            prior = indexed.get(row["ts"])
            if prior and any(not math.isclose(prior[k],row[k],rel_tol=1e-7,abs_tol=1e-8)
                             for k in ("open","high","low","close","volume")):
                raise ValueError("Provider revised overlapping bars (possibly a split). Frozen forward history was preserved; register a new account")
        new = [r for r in update["rows"] if r["ts"] > old[-1]["ts"]]
        if not new:
            return
        rows = old+new
        if len(rows)>50000:
            raise ValueError("Forward account reached its 50,000-candle limit; export and register a new account")
        snapshot.update(rows=rows,data_sha256=digest(rows))
        write_gzip(path,snapshot)
        working = [dict(r,interval=m["interval"]) for r in rows]
        f = features_for(working,m["interval"],self.stop_event.is_set)
        start = bisect_left([r["end_ts"] for r in rows],state["created_ts"])
        policy = stock_policy(m["settings"],m["mode"],model,learn=True)
        from .shadow_learning import HistoricalFeedback
        from .data import INTERVAL_MS
        feedback = HistoricalFeedback(working,f,start,len(rows),m["settings"],policy,INTERVAL_MS[m["interval"]],
            self.stop_event.is_set, execution_options={"stock_execution":True,
            "close_at_session_end":m["mode"] == "day", "fractional_shares":m["fractional_shares"], "liquidate_end":False},
            lanes=("eligible",))
        metrics, trades = execute(working,f,start,len(rows),m["settings"],stock_params(fixed_params(m["settings"]),m["mode"]),
            m["mode"],m["fractional_shares"],policy=policy,cancelled=self.stop_event.is_set,liquidate_end=False,feedback=feedback)
        state.update(account=account_report(metrics,trades,policy.state["observations"]-model["observations"],digest(policy.export())),
                     practice_examples=feedback.count, practice_by_family=feedback.by_family,
                     feedback_scope="Independent cost-eligible setup examples resolved after registration; overlapping examples are not account trades or portfolio profit. Account feedback is not counted twice.",
                     updated_ts=int(time.time()*1000),data_sha256=snapshot["data_sha256"],
                     message="Following new closed session candles with the registered stock learner")
        if not metrics["complete"]:
            state["message"] = metrics["incomplete_reason"]
        self._save_forward(state["id"],"running" if metrics["complete"] else "error",state)
