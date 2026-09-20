"""Registered prospective candle studies. No order or profile installation path.

Each study pins its code, seed, costs, hypothesis and end date before new prices
exist. Both accounts replay the same immutable observations. These are candle
simulations, not forward quote fills or a substitute for trading qualification.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import threading
import time
import uuid
from bisect import bisect_left
from pathlib import Path

from .adaptive import AdaptivePolicy, POLICY_VERSION
from .coinbase_feed import CoinbaseClient
from .continuous import RuntimeLease
from .data import INTERVAL_MS
from .engine import ENGINE_VERSION
from .evaluation import canonical_candle, dataset_digest
from .event_context import digest
from .execution import simulate
from .finances import closed_trade_totals, execution_audit
from .learning_diagnostics import regime_report
from .learning_research import build_learning_features
from .paper_store import db_connect, load_state
from .prediction_audit import summarize_predictions

DAY = 86400000
WARMUP = 500


def source_digest():
    h = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        h.update(path.name.encode()+b"\0"+path.read_bytes())
    return h.hexdigest()


def encoded(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)


def validated_candles(rows, step, cutoff):
    result = []
    previous = None
    for original in rows:
        if isinstance(original.get("ts"),bool) or original["ts"] != int(original["ts"]):
            raise ValueError("Invalid candle timestamp")
        r = canonical_candle(original)
        if (r["ts"] % step or r["ts"]+step > cutoff or r["ts"] < 0
                or (previous is not None and r["ts"] <= previous)):
            raise ValueError("Candle timestamps are unfinished, duplicated or unordered")
        if (not all(math.isfinite(float(v)) for v in r.values()) or r["low"] <= 0
                or r["volume"] < 0 or r["quote_volume"] < 0
                or r["low"] > min(r["open"],r["close"])
                or r["high"] < max(r["open"],r["close"])):
            raise ValueError("Invalid candle prices or volumes")
        result.append(r)
        previous = r["ts"]
    return result


def append_observations(previous, incoming):
    """Never revise an input that has already participated in evaluation."""
    known = {r["ts"]:r for r in previous}
    last = previous[-1]["ts"] if previous else -1
    for r in incoming:
        if r["ts"] in known:
            if known[r["ts"]] != r:
                raise ValueError("Previously recorded candle changed; study inputs stay frozen")
        elif r["ts"] <= last:
            raise ValueError("Late candle would rewrite previously evaluated history")
        else:
            known[r["ts"]] = r
    return [known[k] for k in sorted(known)]


def build_inputs(protocol, previous, rows, daily, bitcoin, events):
    step = INTERVAL_MS[protocol["interval"]]
    cutoff = protocol["end_ts"]
    rows = append_observations(previous.get("rows",[]),validated_candles(rows,step,cutoff))
    daily = append_observations(previous.get("daily",[]),validated_candles(daily,DAY,cutoff))
    bitcoin = append_observations(previous.get("bitcoin",[]),validated_candles(bitcoin,DAY,cutoff))
    starts = [0]+[i for i in range(1,len(rows)) if rows[i]["ts"]-rows[i-1]["ts"] != step]
    segments = [{"start_index":s,"end_index":e} for s,e in zip(starts,starts[1:]+[len(rows)])]
    features = build_learning_features(rows,protocol["interval"],segments,
        daily_rows=daily, bitcoin_rows=bitcoin if protocol["model"].get("market_context_required") else None,
        event_snapshot=events if protocol["model"].get("event_context_enabled") else None,
        symbol=protocol["symbol"])
    # Late-arriving daily/news inputs cannot rewrite a saved signal or decision.
    frozen = previous.get("features",[])
    features[:len(frozen)] = frozen
    return {"rows":rows,"daily":daily,"bitcoin":bitcoin,"features":features,"events":events}


def evaluate(protocol, inputs):
    if protocol["model"].get("last_label_ts",0)>protocol["start_ts"]:
        raise ValueError("The seed includes labels after the evaluation start")
    rows, features = inputs["rows"], inputs["features"]
    step = INTERVAL_MS[protocol["interval"]]
    start = bisect_left([r["ts"]+step for r in rows],protocol["start_ts"])
    settings = protocol["settings"]
    fee, slip = settings["fee_rate"], settings["slippage_rate"]+protocol["assumed_half_spread"]
    accounts = {}
    for label, learn in (("updating",True),("frozen",False)):
        policy = AdaptivePolicy(protocol["model"],settings["max_notional_fraction"],learn=learn,
            fee_rate=fee,slippage_rate=slip)
        metrics,trades = simulate(rows,features,start,len(rows),500.,settings["risk_per_trade"],fee,slip,
            {"family":"adaptive_policy","direction":"LONG"},policy=policy,
            daily_loss_limit=settings["daily_loss_limit"],bar_interval_ms=step)
        closed = [t for t in trades if t["reason"] != "END"]
        marks = [t for t in trades if t["reason"] == "END"]
        for t in trades:
            t["execution_audit"] = execution_audit({**t,"qty":t["qty_initial"],
                "risk_usd":t["risk_dollars"],"result_r":t["r_multiple"]},{"fee_rate":fee})
        accounts[label] = {"metrics":metrics,"closed":closed_trade_totals(t["pnl"] for t in closed),
            "open_mark_pnl":sum(t["pnl"] for t in marks) if metrics["complete"] else None,
            "open_positions":len(marks) if metrics["complete"] else 1,
            "model_updates":policy.state["observations"]-protocol["model"]["observations"],
            "model_sha256":digest(policy.export()), "trades":trades,
            "forecast_audit":summarize_predictions(closed),
            "regime_performance":regime_report(features,closed,start,len(rows)),
            "fill_audit_failures":sum(t["execution_audit"]["status"] != "reconciled" for t in trades)}
    nets = [accounts[k]["metrics"]["net_pnl"] for k in ("updating","frozen")]
    through = inputs.get("collected_through_ts",rows[-1]["ts"]+step if rows else protocol["start_ts"])
    expected = max(0,(min(protocol["end_ts"],through)-protocol["start_ts"])//step)
    observed = sum(protocol["start_ts"] <= r["ts"] < protocol["end_ts"] for r in rows)
    return {"accounts":accounts, "equity_pnl_difference":nets[0]-nets[1] if None not in nets else None,
        "observed_execution_candles":observed,"expected_execution_candles":expected,
        "missing_execution_candles":max(0,expected-observed),
        "requested_through_ts":through,
        "last_candle_close_ts":rows[-1]["ts"]+step if rows else None,
        "inputs_sha256":digest(inputs), "candles_sha256":dataset_digest(rows),
        "cash_benchmark_net_pnl":0., "validated":False, "research_only":True,
        "scope":"Two separate $500 candle simulations on prices following registration. "
                "Only the updating account learns its own normally closed trades. "
                "END records value open positions after estimated exit costs; they are not completed trades or learning labels. "
                "This is not live fill evidence, a combined portfolio, or automatic permission to trade."}


class ForwardStudies:
    def __init__(self, db_path, learner, events, client=None):
        self.db_path, self.learner, self.events = db_path, learner, events
        self.client = client or CoinbaseClient()
        self.lock = threading.RLock()
        self.worker = None
        self.stop_event = threading.Event()
        self.lease = RuntimeLease(str(db_path)+".forward")
        con = db_connect(db_path)
        try:
            with con:
                con.executescript("""
                  CREATE TABLE IF NOT EXISTS forward_studies(
                    id TEXT PRIMARY KEY,created_at INTEGER NOT NULL,status TEXT NOT NULL,
                    protocol_json TEXT NOT NULL,inputs_json TEXT NOT NULL,result_json TEXT NOT NULL,
                    updated_at INTEGER,last_error TEXT);
                  CREATE UNIQUE INDEX IF NOT EXISTS one_active_forward_study ON forward_studies(status) WHERE status='active';
                """)
        finally:
            con.close()

    def _row(self, ident=None, active=False):
        con = db_connect(self.db_path)
        try:
            query = "SELECT * FROM forward_studies"
            args = ()
            if ident:
                query += " WHERE id=?"; args = (ident,)
            elif active:
                query += " WHERE status='active'"
            row = con.execute(query+" ORDER BY created_at DESC,id DESC LIMIT 1",args).fetchone()
            return dict(row) if row else None
        finally:
            con.close()

    def start(self, symbol, interval, fingerprint, now=None):
        if not isinstance(symbol,str) or not re.fullmatch(r"[A-Z0-9]{2,16}-USD",symbol) or interval not in ("15m","1h"):
            raise ValueError("Choose a completed 15m or 1h Coinbase USD study")
        if not isinstance(fingerprint,str) or not re.fullmatch(r"[a-f0-9]{64}",fingerprint):
            raise ValueError("Choose a saved learning report")
        with self.learner.lock:
            found = any(r.get("fingerprint")==fingerprint and r.get("symbol")==symbol and r.get("interval")==interval
                        for r in self.learner.state.get("results",[]))
        if not found:
            raise ValueError("The selected learning report changed; refresh the page")
        report = load_state(self.db_path,"learning_result_"+fingerprint,{})
        model = report.get("model")
        if (not model or report.get("symbol")!=symbol or report.get("interval")!=interval
                or model.get("version")!=POLICY_VERSION or report.get("error")):
            raise ValueError("Complete historical practice with the current learner first")
        settings = copy.deepcopy(self.learner.agent.settings)
        from .research import cost_signature
        settings["decision_interval"] = interval
        if cost_signature(settings) != report.get("cost_signature"):
            raise ValueError("Fees or risk settings differ from the saved study; run practice again")
        now = int(time.time()*1000) if now is None else now
        if model.get("last_label_ts",0) > now:
            raise ValueError("The seed contains outcomes later than registration")
        AdaptivePolicy(model,settings["max_notional_fraction"])
        step = INTERVAL_MS[interval]
        start = (now//step+1)*step
        protocol = {"version":1,"symbol":symbol,"interval":interval,"created_at":now,
            "start_ts":start,"end_ts":start+30*DAY,"duration_days":30,
            "source_sha256":source_digest(),"engine_version":ENGINE_VERSION,"policy_version":POLICY_VERSION,
            "seed_fingerprint":fingerprint,"model":model,"model_sha256":digest(model),
            "settings":{k:settings[k] for k in ("fee_rate","slippage_rate","risk_per_trade","max_notional_fraction","daily_loss_limit")},
            "assumed_half_spread":.0005,"warmup_candles":WARMUP,
            "hypothesis":"Learning from completed selected trades improves subsequent net results versus the identical frozen seed.",
            "comparisons":["updating","frozen","cash"],"promotion":"Never automatically promote this study",
            "execution":"Next candle open; stop first when ordering is unknown. Equal costs, risk and initial $500 per account.",
            "data":"Coinbase completed candles; immutable recorded inputs and signal features. News uses its local observation time."}
        protocol["protocol_sha256"] = digest(protocol)
        ident = uuid.uuid4().hex
        with self.lock:
            if self.worker and self.worker.is_alive() and self.stop_event.is_set():
                raise RuntimeError("Wait for the previous collection task to stop")
            con = db_connect(self.db_path)
            try:
                with con:
                    if con.execute("SELECT 1 FROM forward_studies WHERE status='active'").fetchone():
                        raise ValueError("A forward study is already active; its rules and end date stay fixed")
                    con.execute("INSERT INTO forward_studies VALUES(?,?,'active',?,'{}','{}',?,NULL)",
                        (ident,now,encoded(protocol),now))
            finally:
                con.close()
        self.resume()
        return ident

    def resume(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return
            if not self._row(active=True):
                return
            self.lease.acquire()
            self.stop_event.clear()
            self.worker = threading.Thread(target=self._run,daemon=True,name="forward-candle-study")
            self.worker.start()

    def shutdown(self):
        """Stop the local worker without modifying the registered experiment."""
        self.stop_event.set()

    def stop(self):
        with self.lock:
            self.stop_event.set()
            con = db_connect(self.db_path)
            try:
                with con:
                    con.execute("UPDATE forward_studies SET status='stopped_early',updated_at=? WHERE status='active'",(int(time.time()*1000),))
            finally:
                con.close()

    def _run(self):
        try:
            while not self.stop_event.is_set() and self._row(active=True):
                try:
                    self.refresh()
                except Exception as exc:
                    con = db_connect(self.db_path)
                    try:
                        with con:
                            con.execute("UPDATE forward_studies SET last_error=? WHERE status='active'",(str(exc)[:240],))
                    finally:
                        con.close()
                if self._row(active=True):
                    self.stop_event.wait(60)
        finally:
            self.lease.release()

    def _fetch(self, symbol, interval, start, cutoff):
        step = INTERVAL_MS[interval]
        rows = {}
        cursor = start
        while cursor < cutoff:
            if self.stop_event.is_set():
                raise InterruptedError("Forward collection stopped")
            end = min(cutoff,cursor+1500*step)
            for r in self.client.candles(symbol,interval,max(1,(end-cursor)//step),end):
                if cursor <= r["ts"] < end:
                    rows[r["ts"]] = r
            cursor = end
        return [rows[k] for k in sorted(rows)]

    def refresh(self, now=None):
        row = self._row(active=True)
        if not row:
            return
        protocol = json.loads(row["protocol_json"])
        stamp = protocol.pop("protocol_sha256")
        if digest(protocol)!=stamp or digest(protocol["model"])!=protocol["model_sha256"]:
            raise ValueError("Registered protocol changed; original record is required")
        protocol["protocol_sha256"] = stamp
        if source_digest()!=protocol["source_sha256"]:
            con = db_connect(self.db_path)
            try:
                with con:
                    con.execute("UPDATE forward_studies SET status='code_changed',last_error=? WHERE id=? AND status='active'",
                        ("Code changed; start a new registered study with this version",row["id"]))
            finally:
                con.close()
            return
        now = int(time.time()*1000) if now is None else now
        step = INTERVAL_MS[protocol["interval"]]
        cutoff = min(now//step*step,protocol["end_ts"])
        previous = json.loads(row["inputs_json"])
        prior_result = json.loads(row["result_json"])
        if prior_result and digest(previous)!=prior_result.get("inputs_sha256"):
            raise ValueError("Saved observations no longer match their recorded hash")
        old = previous.get("rows",[])
        if old and old[-1]["ts"]+step >= cutoff:
            return
        start = old[-1]["ts"] if old else protocol["start_ts"]-WARMUP*step
        rows = self._fetch(protocol["symbol"],protocol["interval"],start,cutoff)
        if not rows:
            raise ValueError("No completed Coinbase candles returned; no prices assumed")
        day_cutoff = cutoff//DAY*DAY
        daily_start = previous["daily"][-1]["ts"] if previous.get("daily") else protocol["start_ts"]//DAY*DAY-90*DAY
        daily = self._fetch(protocol["symbol"],"1d",daily_start,day_cutoff)
        bitcoin = []
        if protocol["model"].get("market_context_required"):
            btc_start = previous["bitcoin"][-1]["ts"] if previous.get("bitcoin") else protocol["start_ts"]//DAY*DAY-90*DAY
            bitcoin = daily if protocol["symbol"]=="BTC-USD" else self._fetch("BTC-USD","1d",btc_start,day_cutoff)
        events = self.events.snapshot() if protocol["model"].get("event_context_enabled") else None
        inputs = build_inputs(protocol,previous,rows,daily,bitcoin,events)
        inputs["collected_through_ts"] = cutoff
        result = evaluate(protocol,inputs)
        # Detect any noncausal change to earlier, normally completed trades.
        for key, account in prior_result.get("accounts",{}).items():
            before = [t for t in account["trades"] if t["reason"]!="END"]
            after = [t for t in result["accounts"][key]["trades"] if t["reason"]!="END"]
            if after[:len(before)] != before:
                raise ValueError("Earlier closed trades changed during replay; result was not accepted")
        status = "completed" if inputs["rows"][-1]["ts"]+step >= protocol["end_ts"] else "active"
        if any(not a["metrics"]["complete"] or a["fill_audit_failures"] for a in result["accounts"].values()):
            status = "incomplete"
        with self.lock:
            con = db_connect(self.db_path)
            try:
                with con:
                    con.execute("UPDATE forward_studies SET inputs_json=?,result_json=?,updated_at=?,last_error=NULL,status=? WHERE id=? AND status='active'",
                        (encoded(inputs),encoded(result),now,status,row["id"]))
            finally:
                con.close()

    def status(self):
        con = db_connect(self.db_path)
        try:
            total = con.execute("SELECT COUNT(*) FROM forward_studies").fetchone()[0]
            rows = con.execute("SELECT id,created_at,status,protocol_json,result_json,updated_at,last_error FROM forward_studies ORDER BY created_at DESC,id DESC LIMIT 20").fetchall()
        finally:
            con.close()
        result = []
        for row in rows:
            item = dict(row)
            protocol = json.loads(item.pop("protocol_json"))
            report = json.loads(item.pop("result_json"))
            item["protocol"] = {k:v for k,v in protocol.items() if k!="model"}
            item["result"] = {**report,"accounts":{k:{n:v for n,v in a.items() if n!="trades"}
                                                   for k,a in report.get("accounts",{}).items()}}
            result.append(item)
        return {"studies":result,"registered_studies":total,"running":bool(self.worker and self.worker.is_alive()),
            "scope":"Registered candle studies are separate simulations. All attempts remain recorded, including early stops and failures."}

    def export(self, ident):
        if not isinstance(ident,str) or not re.fullmatch(r"[a-f0-9]{32}",ident):
            raise ValueError("Choose a registered study")
        row = self._row(ident)
        if not row:
            raise ValueError("Study not found")
        return {"id":row["id"],"status":row["status"],"last_error":row["last_error"],
            "protocol":json.loads(row["protocol_json"]),"inputs":json.loads(row["inputs_json"]),
            "result":json.loads(row["result_json"])}
