"""A bounded, persistent queue for historical experiments. No trading methods."""
from __future__ import annotations

import gzip
import json
import re
import shutil
import threading
import time
from pathlib import Path

from .continuous import RuntimeLease
from .data import INTERVAL_MS
from .evaluation import dataset_digest
from .experiments import RECIPES, VERSION, catalog, digest, history_limits, run_experiment, summary
from .forward_study import source_digest
from .paper_store import db_connect
from .research import ResearchManager
from .study_plan import ACTIVE_INTERVALS, DEFAULT_PRACTICE_SYMBOLS

ACTIVE = ("queued", "downloading", "features", "training", "testing")
COST_KEYS = ("fee_rate", "slippage_rate", "risk_per_trade", "max_notional_fraction", "daily_loss_limit")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_gzip(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with gzip.open(temp, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, separators=(",", ":"), allow_nan=False)
    temp.replace(path)


def read_gzip(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


class ExperimentHistory(ResearchManager):
    def __init__(self, db, folder, client, progress, cancellation):
        super().__init__(db, folder, client)
        self.progress, self.cancel_event = progress, cancellation

    def _update(self, **patch):
        self.progress(stage="downloading", message=patch.get("message", "Collecting observed candles"))


class Cancellation:
    def __init__(self, manager, job_id):
        self.manager, self.job_id = manager, job_id

    def is_set(self):
        return self.manager.stop_event.is_set() or self.manager.get(self.job_id)["status"] == "cancelled"


class ExperimentJobs:
    def __init__(self, db_path, data_dir, client=None, blocked=None):
        self.db_path = Path(db_path)
        self.folder = Path(data_dir)/"experiments"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.client, self.blocked = client, blocked or (lambda: False)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.worker = None
        self.lease = RuntimeLease(str(db_path)+".experiments")
        self.active_id = None
        self.code_hash = source_digest()
        con = db_connect(self.db_path)
        try:
            with con:
                con.executescript("""
                CREATE TABLE IF NOT EXISTS experiment_jobs (
                  id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                  status TEXT NOT NULL, manifest_json TEXT NOT NULL, progress_json TEXT NOT NULL,
                  result_json TEXT, summary_json TEXT);
                CREATE INDEX IF NOT EXISTS experiment_job_status ON experiment_jobs(status, created_at);
                """)
        finally:
            con.close()

    def _row(self, row, full=False):
        if row is None:
            raise ValueError("Experiment not found")
        value = {k: row[k] for k in ("id", "created_at", "updated_at", "status")}
        value.update(manifest=json.loads(row["manifest_json"]), progress=json.loads(row["progress_json"]))
        value["result"] = json.loads(row["result_json"] if full else row["summary_json"]) if (
            row["result_json"] if full else row["summary_json"]) else None
        return value

    def get(self, job_id, full=False):
        if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{64}", job_id):
            raise ValueError("Invalid experiment ID")
        con = db_connect(self.db_path)
        try:
            fields = "*" if full else "id,created_at,updated_at,status,manifest_json,progress_json,summary_json"
            return self._row(con.execute(f"SELECT {fields} FROM experiment_jobs WHERE id=?", (job_id,)).fetchone(), full)
        finally:
            con.close()

    def status(self):
        con = db_connect(self.db_path)
        try:
            rows = con.execute("""SELECT id,created_at,updated_at,status,manifest_json,progress_json,summary_json
                FROM experiment_jobs ORDER BY created_at DESC,rowid DESC LIMIT 100""").fetchall()
            total = con.execute("SELECT COUNT(*) FROM experiment_jobs").fetchone()[0]
            active = con.execute("SELECT COUNT(*) FROM experiment_jobs WHERE status IN (?,?,?,?,?)", ACTIVE).fetchone()[0]
        finally:
            con.close()
        return {"version": VERSION, "jobs": [self._row(r) for r in rows], "total_jobs": total,
                "pending_jobs": active, "active_id": self.active_id,
                "worker_alive": bool(self.worker and self.worker.is_alive()),
                "blocked_by_other_research": bool(self.blocked()),
                "eligible_for_trading": False, "catalog": catalog(),
                "restart_policy": "Resume unfinished jobs with the same code and frozen cutoff; completed account checkpoints are reused.",
                "storage": "Saved to the app database and research directory; persistence across deploys requires a mounted disk."}

    def busy(self):
        return self.active_id is not None

    def _patch(self, job_id, status=None, result=None, **progress):
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("BEGIN IMMEDIATE")
                row = con.execute("SELECT status,progress_json FROM experiment_jobs WHERE id=?", (job_id,)).fetchone()
                if row["status"] == "cancelled" and status != "cancelled":
                    return
                current = json.loads(row["progress_json"])
                current.update(progress)
                # A cancellation that wins the transaction stays cancelled even
                # if the worker finishes an account at the same instant.
                next_status = row["status"] if row["status"] == "cancelled" else status or row["status"]
                con.execute("UPDATE experiment_jobs SET updated_at=?,status=?,progress_json=? WHERE id=?",
                    (int(time.time()), next_status, encoded(current), job_id))
                if result is not None:
                    con.execute("UPDATE experiment_jobs SET result_json=?,summary_json=? WHERE id=?",
                                (encoded(result), encoded(summary(result)), job_id))
        finally:
            con.close()

    def start(self, request, settings):
        if not isinstance(request, dict) or set(request)-{"symbol", "interval", "days", "recipes"}:
            raise ValueError("Use symbol, interval, days and recipes only")
        symbol, interval = request.get("symbol"), request.get("interval")
        if symbol not in DEFAULT_PRACTICE_SYMBOLS or interval not in ACTIVE_INTERVALS:
            raise ValueError("Choose a supported crypto market and candle interval")
        days, recipes = request.get("days"), request.get("recipes")
        limits = history_limits(interval)
        if isinstance(days, bool) or not isinstance(days, int) or not limits["min_days"] <= days <= limits["max_days"]:
            raise ValueError(f"For {interval}, choose {limits['min_days']}–{limits['max_days']} whole days")
        if (not isinstance(recipes, list) or not 1 <= len(recipes) <= 3
                or any(not isinstance(r, str) or r not in RECIPES for r in recipes)
                or len(set(recipes)) != len(recipes)):
            raise ValueError("Choose one to three distinct approved experiments")
        costs = {k: settings[k] for k in COST_KEYS}
        cutoff = int(time.time()*1000)//INTERVAL_MS[interval]*INTERVAL_MS[interval]
        manifests = [{"version": VERSION, "recipe": recipe, "symbol": symbol, "interval": interval,
            "days": days, "cutoff_ts": cutoff, "settings": costs, "source_sha256": self.code_hash,
            "provider": "Coinbase Exchange", "quote_currency": "USD"} for recipe in recipes]
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("BEGIN IMMEDIATE")
                count = con.execute("SELECT COUNT(*) FROM experiment_jobs WHERE status IN (?,?,?,?,?)", ACTIVE).fetchone()[0]
                new = [m for m in manifests if not con.execute("SELECT 1 FROM experiment_jobs WHERE id=?", (digest(m),)).fetchone()]
                if count+len(new) > 12:
                    raise ValueError("The queue is full. Finish or cancel pending experiments first (maximum 12).")
                total = con.execute("SELECT COUNT(*) FROM experiment_jobs").fetchone()[0]
                if total+len(new) > 100:
                    raise ValueError("The saved experiment limit is 100. Export and review the research archive before extending it.")
                if new and shutil.disk_usage(self.folder).free < 150*1024*1024:
                    raise ValueError("Less than 150 MB of research storage remains; free storage before adding experiments")
                now = int(time.time())
                for m in new:
                    con.execute("INSERT INTO experiment_jobs VALUES (?,?,?,?,?,?,NULL,NULL)",
                        (digest(m), now, now, "queued", encoded(m), encoded({"message": "Queued for a bounded comparison", "attempts": 0})))
        finally:
            con.close()
        self.resume()
        return {"ids": [digest(m) for m in manifests], "created": len(new), "cutoff_ts": cutoff,
                "message": "Queued. Identical requests reuse their existing result; they do not count as new evidence."}

    def cancel(self, job_id):
        job = self.get(job_id)
        if job["status"] in ACTIVE:
            self._patch(job_id, status="cancelled", message="Cancelled; completed checkpoints and recorded candles retained")
        return self.get(job_id)

    def retry(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job["status"] not in ("error", "cancelled"):
                raise ValueError("Only failed or cancelled experiments can be resumed")
            if self.active_id == job_id:
                raise RuntimeError("The worker is still stopping; wait before resuming")
            if job["manifest"]["source_sha256"] != self.code_hash:
                raise ValueError("Code changed. Create a new experiment; old checkpoints cannot be reused.")
            con = db_connect(self.db_path)
            try:
                with con:
                    con.execute("BEGIN IMMEDIATE")
                    count = con.execute("SELECT COUNT(*) FROM experiment_jobs WHERE status IN (?,?,?,?,?)", ACTIVE).fetchone()[0]
                    if count >= 12:
                        raise ValueError("The queue is full")
                    con.execute("UPDATE experiment_jobs SET status='queued',updated_at=? WHERE id=?", (int(time.time()), job_id))
            finally:
                con.close()
            self._patch(job_id, message="Requeued with the original cutoff, costs and saved checkpoints")
            self.resume()
        return self.get(job_id)

    def resume(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return
            con = db_connect(self.db_path)
            try:
                pending = con.execute("SELECT id FROM experiment_jobs WHERE status IN (?,?,?,?,?) LIMIT 1", ACTIVE).fetchone()
            finally:
                con.close()
            if not pending:
                return
            try:
                self.lease.acquire()
            except RuntimeError:
                return  # Another process owns this queue. Never reset its work.
            self.stop_event.clear()
            self.worker = threading.Thread(target=self._loop, daemon=True, name="controlled-experiments")
            self.worker.start()

    def shutdown(self):
        self.stop_event.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(timeout=2)

    def _next(self):
        con = db_connect(self.db_path)
        try:
            row = con.execute("SELECT id FROM experiment_jobs WHERE status IN (?,?,?,?,?) ORDER BY created_at,rowid LIMIT 1", ACTIVE).fetchone()
        finally:
            con.close()
        return self.get(row[0]) if row else None

    def _loop(self):
        try:
            while not self.stop_event.is_set():
                if self.blocked():
                    self.stop_event.wait(1)
                    continue
                job = self._next()
                if not job:
                    self.stop_event.wait(1)
                    continue
                self.active_id = job["id"]
                try:
                    self._run_job(job)
                except InterruptedError:
                    self._patch(job["id"], status="queued", message="Paused; resume from saved checkpoints with the same inputs")
                except Exception as exc:
                    import logging
                    logging.exception("Historical experiment failed: %s", job["id"])
                    # Market/research failures are visible, not replaced with fake data.
                    failures = job["progress"].get("failures", [])[-9:]
                    failures.append({"at": int(time.time()), "type": type(exc).__name__, "message": str(exc)[:240]})
                    self._patch(job["id"], status="error", failures=failures,
                                message="Data or research failed: "+str(exc)[:240])
                finally:
                    self.active_id = None
        finally:
            self.lease.release()

    def _run_job(self, job):
        job_id, m = job["id"], job["manifest"]
        if job["status"] == "cancelled":
            return
        if m["source_sha256"] != self.code_hash or source_digest() != self.code_hash:
            self._patch(job_id, status="code_changed", message="The code changed; start a new comparison with a new identity")
            return
        cancellation = Cancellation(self, job_id)
        attempts = job["progress"].get("attempts", 0)+1

        def progress(stage, message):
            if cancellation.is_set():
                raise InterruptedError("Experiment paused")
            self._patch(job_id, status=stage, message=message)

        self._patch(job_id, attempts=attempts)
        input_id = digest({k: m[k] for k in ("symbol", "interval", "days", "cutoff_ts", "provider")})
        snapshot_path = self.folder/"snapshots"/(input_id+".json.gz")
        if snapshot_path.exists():
            snapshot = read_gzip(snapshot_path)
            rows = snapshot["rows"]
            if dataset_digest(rows) != snapshot["data_sha256"]:
                raise ValueError("Recorded candle snapshot failed its integrity check")
        else:
            progress("downloading", "Collecting recorded Coinbase USD candles")
            loader = ExperimentHistory(self.db_path, self.folder, self.client, progress, cancellation)
            rows = loader._history(m["symbol"], m["interval"], m["days"], end_ms=m["cutoff_ts"])
            if not rows:
                raise ValueError("No recorded market candles were returned")
            snapshot = {"rows": rows, "data_sha256": dataset_digest(rows),
                        "repair": loader.data_reports.get((m["symbol"], m["interval"])),
                        "recorded_at": int(time.time())}
            write_gzip(snapshot_path, snapshot)
        if job["progress"].get("data_sha256", snapshot["data_sha256"]) != snapshot["data_sha256"]:
            raise ValueError("The previously tested data snapshot changed")
        self._patch(job_id, data_sha256=snapshot["data_sha256"], candles=len(rows))
        directory = self.folder/"checkpoints"/job_id

        def load(key):
            path = directory/(key+".json.gz")
            return read_gzip(path) if path.exists() else None

        def save(key, value):
            write_gzip(directory/(key+".json.gz"), value)

        start = m["cutoff_ts"]-m["days"]*86400000
        expected = m["days"]*86400000//INTERVAL_MS[m["interval"]]
        if any(r["ts"] < start or r["ts"]+INTERVAL_MS[m["interval"]] > m["cutoff_ts"] for r in rows):
            raise ValueError("Candle snapshot exceeds its registered research window")
        provenance = {"provider": m["provider"], "quote_currency": "USD", "cutoff_ts": m["cutoff_ts"],
                      "requested_days": m["days"], "recorded_at": snapshot["recorded_at"],
                      "requested_candles": expected, "observed_candles": len(rows),
                      "coverage_pct": 100*len(rows)/expected, "synthetic_fallback": False,
                      "repair": snapshot.get("repair")}
        result = run_experiment(rows, m["symbol"], m["interval"], m["recipe"], m["settings"], provenance,
            cancellation.is_set, progress, {"load": load, "save": save})
        self._patch(job_id, status="complete", result=result, message="Comparison complete; historical research only")
