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
from .coinbase_feed import REST, STABLE_BASES
from .data import INTERVAL_MS
from .learning_research import LEARNING_REPORT_VERSION, learn_history
from .paper_store import db_connect, load_state, save_state
from .research import ResearchManager, cost_signature
from .evaluation import reviewed_boundary
from .finances import historical_trade_totals
from .study_reports import compact_report
from .study_plan import (HISTORY_DAYS, MAX_PRACTICE_MARKETS, DEFAULT_PRACTICE_SYMBOLS,
    DEFAULT_PRACTICE_INTERVALS, INTERVAL_HISTORY_LIMITS, normalize_plan, study_days,
    study_key, unique_market_hours, history_coverage)

TRAINING_MARKETS = 10
REVIEW_SECONDS = 28*86400
UNQUALIFIED_REVIEW_SECONDS = 86400


class AutoLearner:
    def __init__(self, db_path, data_dir, agent, research_manager):
        self.db_path, self.agent, self.research_manager = db_path, agent, research_manager
        self.lock = threading.RLock()
        self.worker, self.stop_event = None, threading.Event()
        self._finance_cache = {}
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

    def status(self, compact=False):
        with self.lock:
            result = copy.deepcopy({k:v for k,v in self.state.items() if k != "results"})
            originals = list(self.state.get("results", []))
            result["results"] = ([compact_report(r) for r in originals] if compact
                else copy.deepcopy(originals))
        settings = dict(self.agent.settings)
        reports = result.get("results", [])
        active, updates = [], 0
        for report, original in zip(reports, originals):
            report["trade_finances"] = self._report_finances(original)
            profile = (approved_profile(self.db_path, report["symbol"], settings)
                if report.get("interval", "15m") == settings["decision_interval"]
                and report["symbol"] not in active else None)
            if profile:
                active.append(report["symbol"])
                saved = load_state(self.db_path, "adaptive_paper_"+report["symbol"], {})
                if saved.get("fingerprint")==profile["fingerprint"]:
                    updates += saved.get("forward_trades", 0)
        with self.lock:
            active_fingerprints = {r.get("fingerprint") for r in reports}
            self._finance_cache = {k:v for k,v in self._finance_cache.items() if k in active_fingerprints}
        result.update(active_markets=active, forward_learning_trades=updates,
            market_data_hours=unique_market_hours(reports),
            historical_examples=sum(r.get("historical_examples",0) for r in reports),
            history_days=result.get("practice_history_days", HISTORY_DAYS),
            default_practice_intervals=list(DEFAULT_PRACTICE_INTERVALS),
            interval_history_limits=dict(INTERVAL_HISTORY_LIMITS),
            decision_interval=settings["decision_interval"], max_training_markets=TRAINING_MARKETS,
            max_practice_markets=MAX_PRACTICE_MARKETS,
            default_practice_symbols=list(DEFAULT_PRACTICE_SYMBOLS),
            paper_running=self.agent.runtime["running"],
            current_policy_version=POLICY_VERSION,
            current_report_version=LEARNING_REPORT_VERSION)
        return result

    def report_details(self, symbol, interval, fingerprint=None):
        with self.lock:
            report = next((r for r in self.state.get("results", [])
                if study_key(r) == (symbol, interval)), None)
            if report is None:
                raise ValueError("No saved study matches this coin and timeframe")
            report = dict(report)
        if (fingerprint or None) != (report.get("fingerprint") or None):
            raise ValueError("This study changed; refresh its summary before opening the review")
        full = (load_state(self.db_path, "learning_result_"+report["fingerprint"], report)
            if report.get("fingerprint") else report)
        result = copy.deepcopy({k:v for k,v in full.items() if k not in ("model","holdout_trades","event_snapshot")})
        result["trade_finances"] = self._report_finances(full)
        result["report_summary"] = False
        return result

    def _report_finances(self, report):
        # Status reports omit the full trade list. Read the saved report once per
        # immutable fingerprint so already completed practice needs no rerun.
        fingerprint = report.get("fingerprint")
        if not fingerprint or "holdout_trades" in report:
            return historical_trade_totals(report)
        with self.lock:
            cached = self._finance_cache.get(fingerprint)
        if cached is not None:
            return copy.deepcopy(cached)
        full = load_state(self.db_path, "learning_result_"+fingerprint, report)
        summary = historical_trade_totals(full)
        if summary["status"] == "available":
            with self.lock:
                self._finance_cache[fingerprint] = copy.deepcopy(summary)
        return summary

    def start(self, fee_settings=None):
        with self.lock:
            if self.worker and self.worker.is_alive():
                if self.stop_event.is_set():
                    raise RuntimeError("The previous learning task is still stopping")
                if self.state.get("mode") == "historical_replay":
                    raise ValueError("Historical practice is still running")
                return
            if self.research_manager.worker and self.research_manager.worker.is_alive():
                raise ValueError("Finish or cancel the existing research run before starting automatic learning")
            self.agent.configure({**(fee_settings or {}), "learning_enabled":True, "validated_only":True})
            self.stop_event.clear()
            self._update(enabled=True, mode="continuous", phase="starting", message="Starting market monitoring and learning.")
            self.worker = threading.Thread(target=self._run, daemon=True, name="automatic-learning")
            self.worker.start()

    def start_history(self, symbols=None, fee_settings=None, intervals=None, history_days=HISTORY_DAYS):
        """Replay recorded prices without starting a ticker or a paper/live runner."""
        symbols = list(DEFAULT_PRACTICE_SYMBOLS) if symbols is None else symbols
        if not isinstance(symbols, list) or not 1 <= len(symbols) <= MAX_PRACTICE_MARKETS:
            raise ValueError("Choose one to sixty Coinbase USD markets")
        if any(not isinstance(s, str) for s in symbols):
            raise ValueError("Use Coinbase market names such as BTC-USD")
        symbols = [s.strip().upper() for s in symbols]
        symbols = [s if s.endswith("-USD") else s+"-USD" for s in symbols]
        if any(not re.fullmatch(r"[A-Z0-9]{2,16}-USD", s) for s in symbols):
            raise ValueError("Use Coinbase USD market names such as HBAR or HBAR-USD")
        symbols = list(dict.fromkeys(symbols))
        intervals, history_days = normalize_plan(intervals, history_days, self.agent.settings["decision_interval"])
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError("A learning task is already running")
            if self.research_manager.worker and self.research_manager.worker.is_alive():
                raise ValueError("Finish or cancel the existing research run first")
            if fee_settings:
                self.agent.configure(fee_settings)
            self.stop_event.clear()
            settings = dict(self.agent.settings)
            self._update(enabled=True, mode="historical_replay", phase="starting", practice_symbols=symbols,
                practice_intervals=intervals, practice_history_days=history_days,
                completed_studies=0, total_studies=len(symbols)*len(intervals),
                completed_markets=0, total_markets=len(symbols),
                message="Preparing accelerated practice on recorded Coinbase prices.")
            self.worker = threading.Thread(target=self._run_history, args=(symbols, settings, intervals, history_days),
                daemon=True, name="historical-practice")
            self.worker.start()

    def _run_history(self, symbols, settings, intervals=None, history_days=HISTORY_DAYS):
        phase = "completed"
        try:
            results = self.study(symbols, settings, retry_failed=True, intervals=intervals, history_days=history_days)
            if all(r.get("error") for r in results):
                phase = "error"
                self._update(message="Could not load real market history. "+results[0]["error"])
            else:
                failed = sum(bool(r.get("error")) for r in results)
                self._update(message=f"Historical practice finished: {len(results)-failed} studies completed, {failed} unavailable. Each coin and timeframe has separate results.")
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

    def _fingerprint(self, rows, symbol, settings, reviewed_through_ts=None, daily_rows=None, history_days=None,
                     bitcoin_rows=None, event_snapshot=None):
        from .evaluation import dataset_digest
        from .event_context import digest as event_digest
        digest = hashlib.sha256(json.dumps({"symbol":symbol,"engine":ENGINE_VERSION,
            "policy":POLICY_VERSION, "report_version":LEARNING_REPORT_VERSION,
            "reviewed_through_ts":reviewed_boundary(symbol, reviewed_through_ts),
            "daily_data_sha256":dataset_digest(daily_rows) if daily_rows is not None else None,
            "bitcoin_data_sha256":dataset_digest(bitcoin_rows) if bitcoin_rows is not None else None,
            "events_sha256":event_digest(event_snapshot) if event_snapshot is not None else None,
            "requested_history_days":history_days,
            "costs":cost_signature(settings)}, sort_keys=True).encode())
        for row in rows:
            digest.update(json.dumps(row,sort_keys=True,separators=(",",":")).encode())
            digest.update(b"\n")
        return digest.hexdigest()

    def _pin_events(self, job, snapshot):
        from .event_context import digest as event_digest, validate_snapshot
        if "event_snapshot_key" not in job:
            key = "learning_events_"+event_digest(snapshot) if snapshot is not None else None
            if key:
                save_state(self.db_path,key,snapshot)
            job["event_snapshot_key"] = key
        key = job["event_snapshot_key"]
        pinned = load_state(self.db_path,key) if key else None
        if key and (pinned is None or key != "learning_events_"+event_digest(validate_snapshot(pinned))):
            raise ValueError("The study's pinned event archive is missing or changed")
        return pinned

    def _install(self, result, fingerprint):
        # Secondary-timeframe research must never replace or remove the profile
        # used by the currently configured forward account.
        settings = dict(self.agent.settings)
        if (result.get("interval") == "6h" or result.get("research_only") or
                result.get("interval", "15m") != settings["decision_interval"] or
                result.get("cost_signature") != cost_signature(settings)):
            return
        symbol = result["symbol"]
        con = db_connect(self.db_path)
        try:
            with con:
                if result["validated"]:
                    profile = {"fingerprint":fingerprint, "engine_version":ENGINE_VERSION,
                        "cost_signature":result["cost_signature"], "model":result["model"],
                        "data_end_ts":result["data_quality"]["end_ts"]+INTERVAL_MS[result["interval"]],
                        "created_at":result["created_at"]}
                    write_in_transaction(con, profile_key(symbol), profile)
                else:
                    con.execute("DELETE FROM continuous_state WHERE key=?", (profile_key(symbol),))
        finally:
            con.close()

    def _scope(self, settings, history_days=HISTORY_DAYS):
        return hashlib.sha256(json.dumps({"engine":ENGINE_VERSION, "policy":POLICY_VERSION,
            "report":LEARNING_REPORT_VERSION, "history_days":history_days,
            "costs":cost_signature(settings)}, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _job_key(symbol, interval):
        return "learning_job_"+symbol+("" if interval == "15m" else "_"+interval)

    def _finish_job(self, symbol, job):
        con = db_connect(self.db_path)
        try:
            with con:
                con.execute("DELETE FROM continuous_state WHERE key=?",
                    (self._job_key(symbol, job.get("interval", "15m")),))
                if job.get("fingerprint"):
                    con.execute("DELETE FROM continuous_state WHERE key LIKE ?",
                        ("learning_candidate_"+job["fingerprint"]+"_%",))
        finally:
            con.close()

    def _job(self, symbol, settings, history_days=HISTORY_DAYS):
        interval = settings["decision_interval"]
        key = self._job_key(symbol, interval)
        job = load_state(self.db_path, key, {})
        stamp = int(time.time()*1000)
        scope = self._scope(settings, history_days)
        if job.get("scope") != scope or not 0 <= stamp-job.get("end_ms",0) < 86400000:
            self._finish_job(symbol, {**job, "interval":interval})
            step = INTERVAL_MS[settings["decision_interval"]]
            job = {"scope":scope, "end_ms":stamp//step*step, "interval":interval}
            save_state(self.db_path, key, job)
        return job

    def study(self, symbols, settings, retry_failed=False, intervals=None, history_days=None):
        """Replay each coin/timeframe independently and retain other saved studies."""
        if history_days is None:
            history_days = self.state.get("practice_history_days", HISTORY_DAYS)
        intervals, history_days = normalize_plan(intervals, history_days, settings["decision_interval"])
        if self.stop_event.is_set():
            raise InterruptedError("Learning cancelled")
        base_settings = dict(settings)
        results = []
        previous = {study_key(r):r for r in self.state.get("results", [])}
        updated = dict(previous)
        queue = [(symbol, interval) for symbol in symbols for interval in intervals]
        queue_set = set(queue)
        completed = set()
        bitcoin_cache = {}
        collector = getattr(self.agent,"events",None)
        event_snapshot = collector.snapshot() if collector else None
        if event_snapshot and not any(p["ok"] for p in event_snapshot["polls"]):
            event_snapshot = None
        def publish():
            self._update(results=[updated[k] for k in queue if k in updated]+
                [r for k,r in updated.items() if k not in queue_set],
                completed_studies=len(completed), total_studies=len(queue),
                completed_markets=sum(all((s,iv) in completed for iv in intervals) for s in symbols),
                total_markets=len(symbols))
        # Use current product metadata, not a hardcoded claim that every suggested
        # ticker still exists. If metadata is unavailable, the candle API must
        # still supply real data and the missing check is recorded explicitly.
        catalog, catalog_error = None, None
        try:
            products = self.agent.client.products()
            if not isinstance(products, list):
                raise ValueError("Invalid Coinbase product list")
            catalog = {p['id']:p for p in products}
        except Exception as exc:
            catalog_error = str(exc)[:240]
        for symbol, interval in queue:
            if self.stop_event.is_set():
                raise InterruptedError("Learning cancelled")
            settings = {**base_settings, "decision_interval":interval}
            scope = self._scope(settings, history_days)
            old = previous.get((symbol, interval), {})
            if (old.get("review_scope") == scope and time.time() < old.get("next_review_at", 0)
                    and not retry_failed
                    and (interval != base_settings["decision_interval"] or not old.get("validated")
                         or approved_profile(self.db_path, symbol, settings))):
                results.append(old)
                completed.add((symbol, interval))
                publish()
                continue
            job = self._job(symbol, settings, history_days)
            trial_key = None
            try:
                job_events = self._pin_events(job,event_snapshot)
                save_state(self.db_path,self._job_key(symbol,interval),job)
                product = catalog.get(symbol) if catalog is not None else None
                if catalog is not None and (not product or product.get("quote_currency") != "USD"
                        or product.get("base_currency") in STABLE_BASES
                        or product.get("status") != "online" or product.get("trading_disabled")
                        or product.get("cancel_only") or product.get("auction_mode")):
                    raise ValueError(f"{symbol} is not currently an available Coinbase USD study market. Check its listing or use an archived CSV for historical research.")
                boundary_key = "learning_review_boundary_"+scope+"_"+symbol
                boundary = load_state(self.db_path, boundary_key)
                if boundary is None:
                    # Seeing the same prices at another timeframe does not make
                    # them independent, previously unseen confirmation data.
                    seen = max([r.get("replay", {}).get("test_end_ts", 0)
                        for r in updated.values() if r["symbol"] == symbol]+[
                        load_state(self.db_path, "learning_reviewed_"+symbol, 0)])
                    boundary = reviewed_boundary(symbol, seen)
                    save_state(self.db_path, boundary_key, boundary)
                days = study_days(interval, history_days)
                self._update(phase="downloading", message=f"{symbol} · {interval}: collecting up to {days:,} days of history ({len(completed)+1}/{len(queue)} studies).")
                rows = self.downloader._history(symbol, interval, days,
                    end_ms=job["end_ms"])
                coverage = history_coverage(rows, interval, history_days, job["end_ms"])
                daily_rows, daily_source = self.downloader.daily_history(symbol, days, job["end_ms"])
                benchmark_key = (days, job["end_ms"]//86400000)
                if symbol == "BTC-USD":
                    bitcoin_cache[benchmark_key] = (daily_rows, daily_source)
                elif benchmark_key not in bitcoin_cache:
                    bitcoin_cache[benchmark_key] = self.downloader.daily_history("BTC-USD", days, job["end_ms"])
                bitcoin_rows, bitcoin_source = bitcoin_cache[benchmark_key]
                fingerprint = self._fingerprint(rows, symbol, settings, boundary, daily_rows, history_days, bitcoin_rows, job_events)
                if job.get("fingerprint") and job["fingerprint"] != fingerprint:
                    self._finish_job(symbol, job)
                job["fingerprint"] = fingerprint
                save_state(self.db_path, self._job_key(symbol, interval), job)
                result = load_state(self.db_path, "learning_result_"+fingerprint)
                trial_key = "learning_trial_"+fingerprint
                if result is None:
                    trial = load_state(self.db_path, trial_key, {})
                    save_state(self.db_path, trial_key, {"status":"running", "symbol":symbol, "interval":interval,
                        "fingerprint":fingerprint, "started_at":int(time.time()),
                        "attempts":trial.get("attempts",0)+1, "cost_signature":cost_signature(settings),
                        "reviewed_through_ts":boundary})
                    prefix = "learning_candidate_"+fingerprint+"_"
                    checkpoint = {
                        "load":lambda index:load_state(self.db_path, prefix+str(index)),
                        "save":lambda index, value:save_state(self.db_path, prefix+str(index), value)}
                    result = learn_history(rows, symbol, settings, self._update, self.stop_event.is_set,
                        checkpoint=checkpoint, reviewed_through_ts=boundary, daily_rows=daily_rows,
                        bitcoin_rows=bitcoin_rows, event_snapshot=job_events)
                trial = load_state(self.db_path, trial_key, {})
                save_state(self.db_path, trial_key, {**trial, "status":"completed",
                    "completed_at":int(time.time()), "manifest":result.get("experiment_registry"),
                    "ordinary_net_pnl":result.get("holdout", {}).get("net_pnl"),
                    "higher_cost_net_pnl":result.get("holdout_stressed", {}).get("net_pnl"),
                    "validated":result.get("validated",False), "rejection_reasons":result.get("rejection_reasons",[])})
                # Retrieval metadata is refreshed even if identical observations
                # reuse the learned result; no stale date range is claimed.
                result.setdefault("interval", interval)
                result["research_only"] = interval == "6h"
                result["fingerprint"] = fingerprint
                result["history_request"] = coverage
                result["market_data"] = {"provider":"Coinbase Exchange",
                    "kind":"recorded_market_candles", "endpoint":REST+f"/products/{symbol}/candles",
                    "retrieval":"Public candle API with saved local download chunks",
                    "gap_repair":self.downloader.data_reports.get((symbol, interval)),
                    "daily_context":daily_source,
                    "bitcoin_context":bitcoin_source,
                    "product_check":{"status":"checked" if catalog is not None else "unavailable",
                        "message":catalog_error, "product_status":(product or {}).get("status")},
                    "synthetic_fallback":False}
                save_state(self.db_path, "learning_result_"+fingerprint, result)
                if self.stop_event.is_set():
                    raise InterruptedError("Learning cancelled")
                self._install(result, fingerprint)
                report = {k:v for k,v in result.items() if k not in ("model","holdout_trades","event_snapshot")}
                report.update(review_scope=scope, next_review_at=time.time()+(
                    REVIEW_SECONDS if result["validated"] else UNQUALIFIED_REVIEW_SECONDS))
                results.append(report)
                reviewed_key = "learning_reviewed_"+symbol
                save_state(self.db_path, reviewed_key, max(load_state(self.db_path, reviewed_key, 0),
                    report.get("replay", {}).get("test_end_ts", 0)))
                self._finish_job(symbol, job)
                del rows
            except InterruptedError:
                if trial_key:
                    save_state(self.db_path, trial_key, {**load_state(self.db_path, trial_key, {}),
                        "status":"interrupted", "stopped_at":int(time.time())})
                raise
            except Exception as exc:
                if trial_key:
                    save_state(self.db_path, trial_key, {**load_state(self.db_path, trial_key, {}),
                        "status":"failed", "error":str(exc)[:500], "stopped_at":int(time.time())})
                results.append({"symbol":symbol, "interval":interval, "validated":False, "error":str(exc),
                    "history_request":{"requested_days":history_days, "effective_days":study_days(interval, history_days)},
                    "review_scope":scope, "next_review_at":time.time()+3600,
                    "rejection_reasons":["Historical learning could not finish for this market."]})
                self._finish_job(symbol, job)
            updated[(symbol, interval)] = results[-1]
            completed.add((symbol, interval))
            publish()
        self._update(tested_costs=cost_signature(base_settings),
            tested_engine=ENGINE_VERSION, tested_policy=POLICY_VERSION,
            tested_report_version=LEARNING_REPORT_VERSION, tested_symbols=list(symbols),
            next_review_at=min((r["next_review_at"] for r in results), default=time.time()+3600))
        return results

    def _needs_review(self, symbols, settings):
        with self.lock:
            stale = (self.state.get("tested_costs") != cost_signature(settings) or
                self.state.get("tested_engine") != ENGINE_VERSION or
                self.state.get("tested_policy") != POLICY_VERSION or
                self.state.get("tested_report_version") != LEARNING_REPORT_VERSION or
                set(self.state.get("tested_symbols", [])) != set(symbols) or
                time.time() >= self.state.get("next_review_at", 0))
            days = self.state.get("practice_history_days", HISTORY_DAYS)
            reports = {study_key(r):dict(r) for r in self.state.get("results", [])}
        if stale:
            return True
        scope = self._scope(settings, days)
        for symbol in symbols:
            report = reports.get((symbol, settings["decision_interval"]), {})
            # A different timeframe's completed study cannot satisfy the
            # monitored model's review, even if the global queue is up to date.
            if (report.get("review_scope") != scope or
                    time.time() >= report.get("next_review_at", 0) or
                    (report.get("validated") and not approved_profile(self.db_path, symbol, settings))):
                return True
        return False

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
                active = self.status(compact=True)["active_markets"]
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
