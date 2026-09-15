"""Learn from earlier resolved examples; test an updating policy on later prices."""
from __future__ import annotations
import math
import hashlib
import json
import time

from .adaptive import AdaptivePolicy, POLICY_VERSION, feature_vector
from .engine import ENGINE_VERSION, build_feature_cache
from .execution import simulate
from .research import cost_signature, bootstrap_interval, daily_goal_report
from .data import INTERVAL_MS
from .learning_data import prepare_learning_history

LEARNING_REPORT_VERSION = 3


def learn_history(rows, symbol, settings, progress=None, cancelled=None, checkpoint=None):
    progress = progress or (lambda **kwargs:None)
    cancelled = cancelled or (lambda:False)
    interval = settings["decision_interval"]
    if cancelled():
        raise InterruptedError("Learning cancelled")
    rows, quality, coverage = prepare_learning_history(rows, interval)
    step = INTERVAL_MS[interval]
    purge = math.ceil(24*3600000/step)
    holdout_start = int(len(rows)*.80)
    development = holdout_start-purge
    features = build_feature_cache(rows, interval, simple_only=True)["features"]
    fee, slip = settings["fee_rate"], settings["slippage_rate"]+.0005
    candidates = AdaptivePolicy(max_notional_fraction=settings["max_notional_fraction"]).candidates
    examples = []
    training_candidates = []
    training_totals = {"candles_checked":0, "features_available":0,
        "qualified_setups":0, "entry_attempts":0, "entries_opened":0, "rejections":{}}
    # These independently funded hypothetical examples are training labels, not
    # a multi-strategy portfolio. The actual policy tests use one $500 account.
    for index, params in enumerate(candidates):
        if cancelled():
            raise InterruptedError("Learning cancelled")
        progress(phase="learning", message=f"{symbol}: studying setup {index+1}/{len(candidates)}")
        saved = checkpoint["load"](index) if checkpoint else None
        if saved is None:
            metrics, trades = simulate(rows, features, 240, development, 500,
                settings["risk_per_trade"], fee, slip, params,
                cancelled=cancelled, training_examples=True)
            labels = [(trade["exit_ts"]+step, index, feature_vector(trade["features"]), trade["r_multiple"])
                      for trade in trades if trade["reason"] != "END"]
            saved = {"labels":labels, "diagnostics":{"params":dict(params),
                "resolved_examples":len(labels), "signal_funnel":metrics.get("signal_funnel", {})}}
            if checkpoint:
                checkpoint["save"](index, saved)
            del trades
        training_candidates.append(saved["diagnostics"])
        funnel = saved["diagnostics"]["signal_funnel"]
        examples.extend(saved["labels"])
        for key in training_totals:
            if key != "rejections":
                training_totals[key] += funnel.get(key, 0)
        for reason, count in funnel.get("rejections", {}).items():
            counts = training_totals["rejections"]
            counts[reason] = counts.get(reason, 0) + count
    examples.sort(key=lambda x:(x[0],x[1]))
    seed = AdaptivePolicy(max_notional_fraction=settings["max_notional_fraction"])
    cursor = 0

    def train_until(cut_ts):
        nonlocal cursor
        while cursor < len(examples) and examples[cursor][0] <= cut_ts:
            if cursor % 500 == 0 and cancelled():
                raise InterruptedError("Learning cancelled")
            stamp, index, vector, reward = examples[cursor]
            seed.observe(candidates[index], vector, reward, stamp)
            cursor += 1
        return seed.export()

    def test(initial, start, end, stress=1, learn=True, baseline=False):
        policy = AdaptivePolicy(initial, settings["max_notional_fraction"], learn=learn,
            fee_rate=fee*stress, slippage_rate=slip*stress,
            regime_adaptation=not baseline, cost_filter=not baseline)
        metrics, trades = simulate(rows, features, start, end, 500,
            settings["risk_per_trade"], fee*stress, slip*stress,
            {"family":"adaptive_policy", "direction":"LONG"},
            policy=policy, cancelled=cancelled, daily_loss_limit=settings["daily_loss_limit"])
        return metrics, trades, policy.export()

    starts = [int(development*f) for f in (.45,.63,.81)]
    ends = starts[1:]+[development]
    folds = []
    for index,(start,end) in enumerate(zip(starts,ends),1):
        initial = train_until(rows[start-purge]["ts"])
        progress(phase="testing", message=f"{symbol}: checking later period {index}/3")
        metrics, _, _ = test(initial,start,end)
        folds.append({"fold":index, "training_labels":initial["observations"],
            "training_label_end_ts":initial["last_label_ts"], "test_start_ts":rows[start]["ts"],
            "test_end_ts":rows[end-1]["ts"]+step, "metrics":metrics})

    initial = train_until(rows[development]["ts"])
    progress(phase="testing", message=f"{symbol}: checking the final unseen period and higher costs")
    holdout, trades, trained = test(initial,holdout_start,len(rows))
    stressed, _, _ = test(initial,holdout_start,len(rows),stress=1.5)
    frozen, _, _ = test(initial,holdout_start,len(rows),learn=False)
    baseline, _, _ = test(initial,holdout_start,len(rows),baseline=True)
    baseline_stressed, _, _ = test(initial,holdout_start,len(rows),stress=1.5,baseline=True)
    first, last = rows[holdout_start+1]["open"], rows[-1]["close"]
    buy_hold = 500/(first*(1+slip)*(1+fee))*last*(1-slip)*(1-fee)-500
    regime_examples = {regime:sum(m.get("regimes", {}).get(regime, {}).get("samples",0)
        for m in trained["models"].values()) for regime in ("BULL","BEAR","CHOP")}
    positive = sum(f["metrics"]["net_pnl"]>0 for f in folds)
    uncertainty = bootstrap_interval([t["r_multiple"] for t in trades])
    reasons = []
    if not examples:
        reasons.append("No completed training examples survived the signal and execution checks; see training diagnostics.")
    if positive < 2:
        reasons.append("Fewer than two later test periods made money after costs.")
    if len(trades) < 30:
        reasons.append("Fewer than 30 trades in the final test period.")
    if holdout["net_pnl"] <= 0 or stressed["net_pnl"] <= 0:
        reasons.append("The final test did not stay profitable at both ordinary and higher costs.")
    if uncertainty["lower_r"] is None or uncertainty["lower_r"] <= 0:
        reasons.append("The uncertainty in final trade results is too large to qualify.")
    if holdout["max_drawdown_pct"] > 15:
        reasons.append("The final test lost more than 15% from a prior equity peak.")
    return {"engine_version":ENGINE_VERSION, "policy_version":POLICY_VERSION,
        "learning_report_version":LEARNING_REPORT_VERSION,
        "symbol":symbol, "interval":interval, "created_at":int(time.time()),
        "data_selection":coverage,
        "data_quality":quality, "data_hours":len(rows)*step/3600000,
        "historical_examples":len(examples), "candidate_count":len(candidates),
        "regime_examples":regime_examples,
        "training_diagnostics":{"totals":training_totals, "candidates":training_candidates,
            "count_basis":"Candidate evaluations can overlap on the same candles. Counts are not independent opportunities or account trades."},
        "training_label_end_ts":initial["last_label_ts"],
        "pre_holdout_model_sha256":hashlib.sha256(json.dumps(initial,sort_keys=True).encode()).hexdigest(),
        "holdout_start_ts":rows[holdout_start]["ts"],
        "folds":folds, "profitable_folds":positive, "holdout":holdout,
        "holdout_stressed":stressed, "frozen_holdout":frozen,
        "learning_pnl_difference":holdout["net_pnl"]-frozen["net_pnl"],
        "upgrade_comparison":{"baseline":baseline, "baseline_stressed":baseline_stressed,
            "net_pnl_difference":holdout["net_pnl"]-baseline["net_pnl"],
            "stress_net_pnl_difference":stressed["net_pnl"]-baseline_stressed["net_pnl"],
            "selection_uses_comparison":False,
            "label":"Pooled learning without regime adaptation or signal-time cost screening; same seed, costs and daily halt."},
        "benchmarks":{"cash_net_pnl":0., "buy_hold_net_pnl":buy_hold,
            "buy_hold_return_pct":buy_hold/5, "scope":"$500 buy and hold after costs over the same executable final-test period; different exposure from the trading policy."},
        "holdout_learning_updates":trained["observations"]-initial["observations"],
        "holdout_expectancy_interval":uncertainty, "validated":not reasons,
        "rejection_reasons":reasons, "cost_signature":cost_signature(settings),
        "costs":{"fee_per_side":fee, "slippage_per_fill":settings["slippage_rate"],
                 "assumed_half_spread":.0005, "stress_multiplier":1.5},
        "daily_goal":daily_goal_report(trades,rows[holdout_start]["ts"],rows[-1]["ts"]),
        "model":trained,
        "scope":"One-market $500 policy tests. Training examples overlap across variants and are not independent market hours or account profits. Forward updates learn only completed trades. Model estimates are not calibrated probabilities.",
        "warning":"Repeated runs can reuse test periods. The frozen comparison cannot change qualification. Portfolio execution, latency, live fills, and future profit remain unvalidated.",
        "holdout_trades":[{k:t[k] for k in ("entry_ts","exit_ts","strategy_family","pnl","r_multiple","reason")} for t in trades]}
