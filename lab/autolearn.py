"""One control for historical learning and continuous paper monitoring.

This controller never enables Coinbase live mode or submits exchange orders.
It runs only while the application process and this controller are running.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
import threading
import time

from .adaptive import POLICY_VERSION, approved_profile, profile_key, write_in_transaction
from .engine import ENGINE_VERSION
from .coinbase_feed import REST
from .data import INTERVAL_MS
from .learning_research import LEARNING_REPORT_VERSION, learn_history
from .paper_store import db_connect, load_state, save_state
from .research import ResearchManager, cost_signature

HISTORY_DAYS = 1095
TRAINING_MARKETS = 5
REVIEW_SECONDS = 28*86400
UNQUALIFIED_REVIEW_SECONDS = 86400


class AutoLearner:
    def __init__(self, db_path, data_dir, agent, research_manager):
        self.db_path, self.agent, self.research_manager = db_path, agent, research_manager
        self.lock = threading.RLock()
        self.worker, self.stop_event = None, threading.Event()
        self.state = load_state(db_path, "automatic_learning", {
            "results":[], "next_review_at":0, "tested_costs":None, "history_days":HISTORY_DAYS})
        self.state.update(enabled=False, phase="stopped", message="Ready to learn from history.")
        self.downloader = ResearchManager(db_path, data_dir/"automatic", client=agent.client)
        self.downloader.cancel_event = self.stop_event
        self.downloader._update = self._download_progress

    def _update(self, **patch):
        with self.lock:
            self.state.update(patch)
            save_state(self.db_path, "automatic_learning", self.state)

    def _download_progress(self, **patch):
        self._update(phase="downloading", message=patch.get("message", "Collecting market history"))

    def status(self):
        with self.lock:
            result = copy.deepcopy(self.state)
        settings = dict(self.agent.settings)
        reports = result.get("results", [])
        active, updates = [], 0
        for report in reports:
            profile = approved_profile(self.db_path, report["symbol"], settings)
            if profile:
                active.append(report["symbol"])
                saved = load_state(self.db_path, "adaptive_paper_"+report["symbol"], {})
                if saved.get("fingerprint")==profile["fingerprint"]:
                    updates += saved.get("forward_trades", 0)
        result.update(active_markets=active, forward_learning_trades=updates,
            market_data_hours=sum(r.get("data_hours",0) for r in reports),
            historical_examples=sum(r.get("historical_examples",0) for r in reports),
            history_days=HISTORY_DAYS, max_training_markets=TRAINING_MARKETS,
            paper_running=self.agent.runtime["running"])
        return result

    def start(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                if self.stop_event.is_set():
                    raise RuntimeError("The previous learning task is still stopping")
                if self.state.get("mode") == "historical_replay":
                    raise ValueError("Historical practice is still running")
                return
            if self.research_manager.worker and self.research_manager.worker.is_alive():
                raise ValueError("Finish or cancel the existing research run before starting automatic learning")
            self.agent.configure({"learning_enabled":True, "validated_only":True})
            self.stop_event.clear()
            self._update(enabled=True, mode="continuous", phase="starting", message="Starting market monitoring and learning.")
            self.worker = threading.Thread(target=self._run, daemon=True, name="automatic-learning")
            self.worker.start()

    def start_history(self, symbols=None, fee_settings=None):
        """Replay recorded prices without starting a ticker or a paper/live runner."""
        symbols = ["BTC-USD", "ETH-USD", "SOL-USD"] if symbols is None else symbols
        if not isinstance(symbols, list) or not 1 <= len(symbols) <= TRAINING_MARKETS:
            raise ValueError("Choose one to five Coinbase USD markets")
        if any(not isinstance(s, str) or not re.fullmatch(r"[A-Z0-9]{2,16}-USD", s) for s in symbols):
            raise ValueError("Use Coinbase market names such as BTC-USD")
        symbols = list(dict.fromkeys(symbols))
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError("A learning task is already running")
            if self.research_manager.worker and self.research_manager.worker.is_alive():
                raise ValueError("Finish or cancel the existing research run first")
            if fee_settings:
                self.agent.configure(fee_settings)
            self.stop_event.clear()
            settings = dict(self.agent.settings)
            self._update(enabled=True, mode="historical_replay", phase="starting",
                message="Preparing accelerated practice on recorded Coinbase prices.")
            self.worker = threading.Thread(target=self._run_history, args=(symbols, settings),
                daemon=True, name="historical-practice")
            self.worker.start()

    def _run_history(self, symbols, settings):
        phase = "completed"
        try:
            results = self.study(symbols, settings)
            if all(r.get("error") for r in results):
                phase = "error"
                self._update(message="Could not load real market history. "+results[0]["error"])
            else:
                self._update(message="Historical practice finished. Decisions were tested on recorded prices without waiting for live candles. See each market's results.")
        except InterruptedError:
            phase = "stopped"
        except Exception as exc:
            phase = "error"
            self._update(message=str(exc))
        finally:
            self._update(enabled=False, phase=phase)

    def stop(self):
        self.stop_event.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(timeout=3)
        stopping = bool(self.worker and self.worker.is_alive())
        self._update(enabled=False, phase="stopping" if stopping else "stopped",
            message="Stopping learning; completed work is saved." if stopping else "Automatic learning stopped. Models are saved.")

    def _fingerprint(self, rows, symbol, settings):
        digest = hashlib.sha256(json.dumps({"symbol":symbol,"engine":ENGINE_VERSION,
            "policy":POLICY_VERSION, "report_version":LEARNING_REPORT_VERSION,
            "costs":cost_signature(settings)}, sort_keys=True).encode())
        for row in rows:
            digest.update(json.dumps(row,sort_keys=True,separators=(",",":")).encode())
            digest.update(b"\n")
        return digest.hexdigest()

    def _install(self, result, fingerprint):
        symbol = result["symbol"]
        con = db_connect(self.db_path)
        try:
            with con:
                if result["validated"]:
                    profile = {"fingerprint":fingerprint, "engine_version":ENGINE_VERSION,
                        "cost_signature":result["cost_signature"], "model":result["model"],
                        "data_end_ts":result["data_quality"]["end_ts"]+{
                            "5m":300000,"15m":900000,"1h":3600000}[result["interval"]],
                        "created_at":result["created_at"]}
                    write_in_transaction(con, profile_key(symbol), profile)
                else:
                    con.execute("DELETE FROM continuous_state WHERE key=?", (profile_key(symbol),))
        finally:
            con.close()

    def _scope(self, settings):
        return hashlib.sha256(json.dumps({"engine":ENGINE_VERSION, "policy":POLICY_VERSION,
            "report":LEARNING_REPORT_VERSION, "costs":cost_signature(settings)}, sort_keys=True).encode()).hexdigest()

    def _finish_job(self, symbol, job):
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("DELETE FROM continuous_state WHERE key=?", ("learning_job_"+symbol,))
                if job.get("fingerprint"):
                    con.execute("DELETE FROM continuous_state WHERE key LIKE ?",
                        ("learning_candidate_"+job["fingerprint"]+"_%",))
        finally:
            con.close()

    def _job(self, symbol, settings):
        key = "learning_job_"+symbol
        job = load_state(self.db_path, key, {})
        stamp = int(time.time()*1000)
        scope = self._scope(settings)
        if job.get("scope") != scope or not 0 <= stamp-job.get("end_ms",0) < 86400000:
            self._finish_job(symbol, job)
            step = INTERVAL_MS[settings["decision_interval"]]
            job = {"scope":scope, "end_ms":stamp//step*step}
            save_state(self.db_path, key, job)
        return job

    def study(self, symbols, settings):
        """Sequential, cancellable study; failures retain the other market results."""
        results = []
        previous = {r["symbol"]:r for r in self.state.get("results", [])}
        scope = self._scope(settings)
        for symbol in symbols:
            if self.stop_event.is_set():
                raise InterruptedError("Learning cancelled")
            old = previous.get(symbol, {})
            if (old.get("review_scope") == scope and time.time() < old.get("next_review_at", 0)
                    and (not old.get("validated") or approved_profile(self.db_path, symbol, settings))):
                results.append(old)
                self._update(results=results, completed_markets=len(results), total_markets=len(symbols))
                continue
            job = self._job(symbol, settings)
            try:
                self._update(phase="downloading", message=f"{symbol}: collecting up to three years of history.")
                rows = self.downloader._history(symbol, settings["decision_interval"], HISTORY_DAYS,
                    end_ms=job["end_ms"])
                fingerprint = self._fingerprint(rows, symbol, settings)
                if job.get("fingerprint") and job["fingerprint"] != fingerprint:
                    self._finish_job(symbol, job)
                job["fingerprint"] = fingerprint
                save_state(self.db_path, "learning_job_"+symbol, job)
                result = load_state(self.db_path, "learning_result_"+fingerprint)
                if result is None:
                    prefix = "learning_candidate_"+fingerprint+"_"
                    checkpoint = {
                        "load":lambda index:load_state(self.db_path, prefix+str(index)),
                        "save":lambda index, value:save_state(self.db_path, prefix+str(index), value)}
                    result = learn_history(rows, symbol, settings, self._update, self.stop_event.is_set,
                        checkpoint=checkpoint)
                    result["fingerprint"] = fingerprint
                    result["market_data"] = {"provider":"Coinbase Exchange",
                        "kind":"recorded_market_candles", "endpoint":REST+f"/products/{symbol}/candles",
                        "retrieval":"Public candle API with saved local download chunks",
                        "synthetic_fallback":False}
                    save_state(self.db_path, "learning_result_"+fingerprint, result)
                if self.stop_event.is_set():
                    raise InterruptedError("Learning cancelled")
                self._install(result, fingerprint)
                report = {k:v for k,v in result.items() if k not in ("model","holdout_trades")}
                report.update(review_scope=scope, next_review_at=time.time()+(
                    REVIEW_SECONDS if result["validated"] else UNQUALIFIED_REVIEW_SECONDS))
                results.append(report)
                self._finish_job(symbol, job)
                del rows
            except InterruptedError:
                raise
            except Exception as exc:
                results.append({"symbol":symbol, "validated":False, "error":str(exc),
                    "review_scope":scope, "next_review_at":time.time()+3600,
                    "rejection_reasons":["Historical learning could not finish for this market."]})
                self._finish_job(symbol, job)
            self._update(results=results, completed_markets=len(results), total_markets=len(symbols))
        self._update(results=results, tested_costs=cost_signature(settings),
            tested_engine=ENGINE_VERSION, tested_policy=POLICY_VERSION,
            tested_report_version=LEARNING_REPORT_VERSION, tested_symbols=list(symbols),
            next_review_at=min((r["next_review_at"] for r in results), default=time.time()+3600))
        return results

    def _needs_review(self, symbols, settings):
        with self.lock:
            return (self.state.get("tested_costs") != cost_signature(settings) or
                self.state.get("tested_engine") != ENGINE_VERSION or
                self.state.get("tested_policy") != POLICY_VERSION or
                self.state.get("tested_report_version") != LEARNING_REPORT_VERSION or
                set(self.state.get("tested_symbols", [])) != set(symbols) or
                time.time() >= self.state.get("next_review_at", 0))

    def _run(self):
        try:
            # Monitor recovered positions while training; missing models block entries.
            self.agent.start()
            while not self.stop_event.is_set():
                if not self.agent.runtime["running"]:
                    raise RuntimeError(self.agent.runtime.get("last_error") or "Market monitoring stopped; restart after checking the dashboard.")
                if not self.agent.runtime["bootstrapped"]:
                    self._update(phase="starting", message="Loading the Coinbase market scanner.")
                    if self.stop_event.wait(2):
                        break
                    continue
                settings = dict(self.agent.settings)
                if not settings.get("learning_enabled"):
                    break
                # A restart can select different markets before the 28-day review.
                symbols = list(self.agent.product_ids)[:TRAINING_MARKETS]
                if not symbols:
                    raise RuntimeError("No Coinbase USD markets are available")
                if self._needs_review(symbols, settings):
                    self.study(symbols, settings)
                active = self.status()["active_markets"]
                self._update(phase="watching" if active else "waiting",
                    message="Learning from completed paper trades and watching for qualified setups." if active else
                    "No market has passed yet. Historical learning will retry with new data within a day; see each market's results.")
                if self.stop_event.wait(15):
                    break
        except InterruptedError:
            pass
        except Exception as exc:
            self._update(phase="error", message=str(exc))
        finally:
            phase = "error" if self.state.get("phase")=="error" else "stopped"
            self._update(enabled=False, phase=phase)

    def export(self):
        result = self.status()
        result["results"] = [load_state(self.db_path, "learning_result_"+r["fingerprint"],r)
            if r.get("fingerprint") else r for r in result.get("results",[])]
        return result
