"""Fixed, auditable comparisons. This module cannot install profiles or trade.

All account variants share one data snapshot, costs and chronological boundaries.
The later window is development research: it is never described as unseen data.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from collections import deque

from .adaptive import AdaptivePolicy
from .chronological_learning import ChronologicalTrainer
from .data import INTERVAL_MS
from .evaluation import dataset_digest, reviewed_boundary
from .execution import simulate
from .exit_management import FIXED_EXIT, BREAK_EVEN_EXIT, TRAILING_EXIT
from .forward_study import source_digest
from .learning_data import prepare_learning_history
from .learning_research import build_learning_features
from .outcome_memory import trade_feedback
from .research import bootstrap_interval
from .strategies import profit_candidates, simple_signal
from .study_plan import ACTIVE_INTERVALS, DEFAULT_PRACTICE_SYMBOLS

VERSION = "controlled-experiments-v1"
DAY = 86400000
MAX_CANDLES = 50000
RECIPES = {
    "breakout_retest": {
        "title": "Breakout vs confirmed retest",
        "hypothesis": "Waiting for a broken level to hold may reduce failed breakout entries.",
        "change": "Enter after a later completed retest candle instead of the original breakout close.",
        "variants": ["breakout", "retest"], "baseline": "breakout",
    },
    "exit_rules": {
        "title": "How should a trade exit?",
        "hypothesis": "Protecting a move or limiting its duration may reduce profit giveback.",
        "change": "Keep breakout entries and sizing; compare fixed, fee-covered break-even, trailing, and six-hour exits.",
        "variants": ["fixed", "break_even", "trailing", "six_hour"], "baseline": "fixed",
    },
    "learning_control": {
        "title": "Does continued learning help?",
        "hypothesis": "Learning from newly resolved account trades may improve on a frozen copy of the same model.",
        "change": "Start from the same development seed; update one account only after its trades close.",
        "variants": ["frozen", "updating"], "baseline": "frozen",
    },
}
PROTOCOL = {
    "version": VERSION, "starting_balance": 500., "split_fraction": .7,
    "purge_hours": 24, "higher_cost_multiplier": 1.5, "assumed_half_spread": .0005,
    "retest": {"lookback_bars": 55, "expiry_bars": 12, "touch_atr": .25, "invalidation_atr": .5},
    "trailing": "After a closed candle earns at least 1 net R, trail one initial stop distance from its close; effective next candle.",
    "evidence_floor_closed_trades": 30, "automatic_promotion": False,
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def history_limits(interval):
    step = INTERVAL_MS[interval]
    return {"min_days": max(7, math.ceil(3100*step/DAY)),
            "max_days": min(2920, MAX_CANDLES*step//DAY)}


def catalog():
    return {"version": VERSION, "recipes": [{"id": k, **v} for k, v in RECIPES.items()],
            "intervals": list(ACTIVE_INTERVALS), "symbols": list(DEFAULT_PRACTICE_SYMBOLS),
            "history_limits": {iv: history_limits(iv) for iv in ACTIVE_INTERVALS},
            "protocol": copy.deepcopy(PROTOCOL), "max_candles_per_job": MAX_CANDLES,
            "scope": "Crypto candle simulations. Stock price widgets cannot supply stock backtest history."}


def fixed_params(settings):
    # The existing second breakout candidate, specified before results are read.
    p = next(p for p in profit_candidates() if p["family"] == "breakout_volume_simple"
             and p["stop_atr"] == 2. and p["rr2"] == 2.5)
    return dict(p, max_notional_fraction=settings["max_notional_fraction"])


def retest_features(rows, features, step, params):
    """One retest per qualified breakout, using a fixed prior 55-bar level.

    No same-bar breakout/retest. Reset state on missing candles or feature warmup.
    A later candle must touch the level, close above it and close at/above its open;
    the ordinary volume, regime and overextension filters still apply at that close.
    """
    result, highs, pending = [], deque(maxlen=55), None
    for i, (row, f) in enumerate(zip(rows, features)):
        if i and row["ts"]-rows[i-1]["ts"] != step:
            highs.clear()
            pending = None
        output = dict(f) if f else None
        if output:
            output["breakout55"] = False
        else:
            pending = None
        if pending and f:
            level, atr, armed = pending
            if i-armed > 12 or row["low"] < level-.5*atr:
                pending = None
            elif (row["low"] <= level+.25*atr and row["high"] >= level
                  and row["close"] > level and row["close"] >= row["open"]):
                output["breakout55"] = True
                output["_experiment_retest_level"] = level
                pending = None
        # A pending original level is not moved up by subsequent breakout bars.
        if (pending is None and not (output and output["breakout55"]) and f and len(highs) == 55
                and simple_signal(f, params)[0] is not None):
            pending = (max(highs), max(float(f["_atr"]), row["close"]*.002), i)
        result.append(output)
        highs.append(row["high"])
    return result


def compact_trade(t):
    keys = ("entry_ts", "exit_ts", "exit_time_ts", "signal_ts", "entry", "exit", "initial_stop", "stop",
            "target2", "qty_initial", "risk_dollars", "pnl", "r_multiple", "reason", "regime",
            "gross_pnl", "fees_paid", "slippage_notional", "decision_params", "strategy_family",
            "break_even_active_ts", "trailing_active_ts", "planned_cost_r", "planned_net_rr")
    return {k: t[k] for k in keys if k in t}


def account_report(metrics, trades, updates=0, model_hash=None):
    closed = [t for t in trades if t["reason"] != "END"]
    return {"metrics": metrics, "closed_trades": len(closed),
            "closed_net_pnl": sum(t["pnl"] for t in closed),
            "window_end_exits": len(trades)-len(closed),
            "window_end_pnl": sum(t["pnl"] for t in trades if t["reason"] == "END"),
            "uncertainty": bootstrap_interval([t["r_multiple"] for t in closed]),
            "model_updates": updates, "model_sha256": model_hash,
            "trades": [compact_trade(t) for t in trades]}


def assess_pair(control, challenger, stress_control, stress_challenger):
    accounts = (control, challenger, stress_control, stress_challenger)
    if any(not a["metrics"]["complete"] for a in accounts):
        return {"status": "incomplete", "net_difference": None, "stress_net_difference": None,
                "reason": "Missing market candles interrupted an open position."}
    net = challenger["metrics"]["net_pnl"]-control["metrics"]["net_pnl"]
    stressed = stress_challenger["metrics"]["net_pnl"]-stress_control["metrics"]["net_pnl"]
    # Lower net losses are a relative improvement, not evidence of profitability.
    result = {"net_difference": net, "stress_net_difference": stressed}
    if min(a["closed_trades"] for a in accounts) < PROTOCOL["evidence_floor_closed_trades"]:
        result.update(status="insufficient_evidence", reason="At least one account has fewer than 30 normally closed trades.")
    elif net <= 0 or stressed <= 0:
        result.update(status="no_improvement", reason="The challenger did not beat the control under both cost assumptions.")
    elif challenger["metrics"]["net_pnl"] <= 0 or stress_challenger["metrics"]["net_pnl"] <= 0:
        result.update(status="lower_loss_only", reason="Losses improved, but the challenger still lost money in at least one cost scenario.")
    else:
        result.update(status="historical_lead", reason="A historical lead worth investigating; no prospective confirmation or trading approval.")
    return result


def run_experiment(rows, symbol, interval, recipe, settings, provenance=None,
                   cancelled=None, progress=None, checkpoint=None):
    if recipe not in RECIPES or interval not in ACTIVE_INTERVALS:
        raise ValueError("Unknown experiment or unsupported candle interval")
    if len(rows) > MAX_CANDLES:
        raise ValueError(f"Bound this experiment to {MAX_CANDLES:,} candles or fewer")
    costs = {}
    for key, (lo, hi) in {"fee_rate": (0, .02), "slippage_rate": (0, .01),
                          "risk_per_trade": (.001, .02), "max_notional_fraction": (.05, 1),
                          "daily_loss_limit": (.005, .10)}.items():
        v = settings[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError("Invalid experiment cost or risk setting: "+key)
        costs[key] = float(v)
    rows, quality, coverage = prepare_learning_history(rows, interval)
    step = INTERVAL_MS[interval]
    progress = progress or (lambda **_: None)
    cancelled = cancelled or (lambda: False)
    if cancelled():
        raise InterruptedError("Experiment paused")
    identity = {"protocol": PROTOCOL, "recipe": recipe, "source_sha256": source_digest(),
                "symbol": symbol, "interval": interval, "costs": costs, "data_sha256": dataset_digest(rows),
                "market_data": provenance or {"provider": "Supplied OHLCV", "authenticity_verified": False}}
    fingerprint = digest(identity)

    def remembered(key, calculate):
        if cancelled():
            raise InterruptedError("Experiment paused")
        key = fingerprint+"_"+key
        old = checkpoint["load"](key) if checkpoint else None
        if old is not None:
            return old
        value = calculate()
        if checkpoint:
            checkpoint["save"](key, value)
        return value

    split = int(len(rows)*.7)
    purge = math.ceil(DAY/step)
    development = split-purge
    if development <= 500 or len(rows)-split < 500:
        raise ValueError("More candles are required for development, a 24-hour purge, and later evaluation")
    progress(stage="features", message="Building indicators from completed candles; resetting after every gap")
    features = build_learning_features(rows, interval, coverage["segments"], cancelled)
    params = fixed_params(costs)
    later_start = rows[split]["ts"]
    windows = (("earlier", 240, development), ("later", split-1, len(rows)))
    seed = None
    if recipe == "learning_control":
        def train_seed():
            policy = AdaptivePolicy(max_notional_fraction=costs["max_notional_fraction"],
                                    fee_rate=costs["fee_rate"], slippage_rate=costs["slippage_rate"]+.0005)
            examples = []
            for number, p in enumerate(policy.candidates):
                progress(stage="training", message=f"Learning development seed {number+1}/{len(policy.candidates)}")

                def collect():
                    _, trades = simulate(rows, features, 240, development, 500., costs["risk_per_trade"],
                        costs["fee_rate"], costs["slippage_rate"]+.0005, p, training_examples=True,
                        practice_cost_mode="eligible", bar_interval_ms=step, cancelled=cancelled)
                    return [(t["exit_ts"]+step, number, t["training_vector"], t["r_multiple"],
                             trade_feedback(t), t["entry_ts"]) for t in trades if t["reason"] != "END"]

                examples.extend(remembered("labels_"+str(number), collect))
            examples.sort(key=lambda x: (x[0], x[1], x[5]))
            trainer = ChronologicalTrainer(policy, policy.candidates, examples, cancelled)
            model = trainer.advance(rows[development-1]["ts"]+step)
            return {"model": model, "resolved_examples": len(examples), "last_label_ts": model.get("last_label_ts", 0)}
        seed = remembered("seed", train_seed)
        if seed["last_label_ts"] > later_start:
            raise ValueError("Seed labels extend into evaluation")
        windows = (("later", split-1, len(rows)),)
    retests = retest_features(rows, features, step, params) if recipe == "breakout_retest" else None
    variants = []
    for variant in RECIPES[recipe]["variants"]:
        p = dict(params)
        if variant == "break_even":
            p["exit_policy"] = BREAK_EVEN_EXIT
        elif variant == "trailing":
            p["exit_policy"] = TRAILING_EXIT
        elif variant == "six_hour":
            p["time_stop_hours"] = 6
        f = retests if variant == "retest" else features
        reports = {}
        for window, start, end in windows:
            accounts = {}
            for scenario, multiplier in (("standard", 1.), ("higher_cost", 1.5)):
                progress(stage="testing", message=f"{variant.replace('_', ' ')} · {window} · {scenario.replace('_', ' ')}")

                def calculate():
                    fee, slip = costs["fee_rate"]*multiplier, (costs["slippage_rate"]+.0005)*multiplier
                    policy = (AdaptivePolicy(seed["model"], costs["max_notional_fraction"], learn=variant == "updating",
                                             fee_rate=fee, slippage_rate=slip) if seed else None)
                    metrics, trades = simulate(rows, f, start, end, 500., costs["risk_per_trade"], fee, slip, p,
                        policy=policy, bar_interval_ms=step, daily_loss_limit=costs["daily_loss_limit"], cancelled=cancelled)
                    return account_report(metrics, trades,
                        policy.state["observations"]-seed["model"]["observations"] if policy else 0,
                        digest(policy.export()) if policy else None)

                accounts[scenario] = remembered(f"account_{variant}_{window}_{scenario}", calculate)
            reports[window] = {"start_ts": rows[start+1]["ts"], "end_ts": rows[end-1]["ts"]+step, **accounts}
        variants.append({"id": variant, "windows": reports})
    baseline = next(v for v in variants if v["id"] == RECIPES[recipe]["baseline"])["windows"]["later"]
    comparisons = []
    for v in variants:
        if v["id"] != RECIPES[recipe]["baseline"]:
            after = v["windows"]["later"]
            comparisons.append({"challenger": v["id"], "control": RECIPES[recipe]["baseline"],
                **assess_pair(baseline["standard"], after["standard"], baseline["higher_cost"], after["higher_cost"])})
    return {**identity, "fingerprint": fingerprint, "created_at": int(time.time()),
            "title": RECIPES[recipe]["title"], "hypothesis": RECIPES[recipe]["hypothesis"],
            "data_quality": quality, "coverage": {k: v for k, v in coverage.items() if k != "segments"},
            "start_ts": rows[0]["ts"], "end_ts": rows[-1]["ts"]+step,
            "later_start_ts": later_start, "development_end_ts": rows[development-1]["ts"]+step,
            "known_reviewed_through_ts": reviewed_boundary(symbol), "evaluation_kind": "historical_development",
            "variants": variants, "comparisons": comparisons,
            "seed": ({"sha256": digest(seed["model"]), "resolved_examples": seed["resolved_examples"],
                      "last_label_ts": seed["last_label_ts"], "practice_lane": "eligible",
                      "updating_feedback": "Only this account's normally closed trades; no shadow feedback"} if seed else None),
            "cash_benchmark_net": 0., "eligible_for_trading": False, "validated": False,
            "limitations": ["Separate $500 accounts, not a combined portfolio or live fills.",
                "Historical development data may already have been reviewed; no claim of unseen validation.",
                "OHLC fills use next-open execution and stop-first ambiguity; actual spreads and liquidity vary.",
                "End-of-window liquidation is shown separately and excluded from evidence counts.",
                "Bootstrap ranges describe dependent historical trades, not confidence that a stock or coin will rise.",
                "No parameters are optimized from the later window; repeated trials still create selection bias.",
                "No automatic profile installation, live orders, or increase in trading risk."]}


def summary(report):
    result = copy.deepcopy(report)
    for variant in result.get("variants", []):
        for window in variant["windows"].values():
            for scenario in ("standard", "higher_cost"):
                window[scenario].pop("trades", None)
    return result
