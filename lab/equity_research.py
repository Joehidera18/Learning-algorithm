"""Stock practice uses the existing strategy, execution and online learning core.

Stock models and account results are scoped to one ticker, feed, timeframe and
holding style. No crypto learner, profile, account or order runner is changed.
"""
from __future__ import annotations

import copy
import math
from bisect import bisect_left
from collections import deque

from .adaptive import AdaptivePolicy
from .chronological_learning import ChronologicalTrainer
from .data import INTERVAL_MS
from .engine import build_feature_cache
from .equity_data import DAY, INTERVALS, slots, valid_prices
from .execution import simulate
from .experiments import account_report, assess_pair, digest, fixed_params, retest_features
from .exit_management import FIXED_EXIT, BREAK_EVEN_EXIT, TRAILING_EXIT
from .market_clock import close_ts, consecutive
from .outcome_memory import trade_feedback

VERSION = "stock-practice-v1"
DEFAULT_COSTS = {"fee_rate":.0001, "slippage_rate":.0005, "half_spread":.0002,
                 "risk_per_trade":.005, "max_notional_fraction":.95, "daily_loss_limit":.02}


def validate_costs(value):
    if not isinstance(value, dict) or set(value)-set(DEFAULT_COSTS):
        raise ValueError("Unknown stock cost setting")
    result = dict(DEFAULT_COSTS, **value)
    for key, limits in {"fee_rate":(0,.02), "slippage_rate":(0,.01), "half_spread":(0,.01),
            "risk_per_trade":(.001,.02), "max_notional_fraction":(.05,1), "daily_loss_limit":(.005,.1)}.items():
        x = result[key]
        if isinstance(x, bool) or not isinstance(x, (int,float)) or not math.isfinite(x) or not limits[0] <= x <= limits[1]:
            raise ValueError("Invalid stock cost assumption: "+key)
    return result


def prepare(rows, interval):
    if interval not in INTERVALS or not 2 <= len(rows) <= 50000:
        raise ValueError("Stock practice needs 2–50,000 observed candles")
    expected = slots(interval, rows[0]["ts"], rows[-1]["end_ts"])
    starts = [0]
    for i, row in enumerate(rows):
        metadata = expected.get(row["ts"])
        if (not valid_prices(row) or row.get("asset_class") != "equity" or not metadata
                or any(row.get(k) != v for k,v in metadata.items())
                or (i and row["ts"] <= rows[i-1]["ts"])):
            raise ValueError("Stock candles must be valid, ordered and match the exchange calendar")
        if i and not consecutive(rows[i-1], row, INTERVAL_MS[interval]):
            starts.append(i)
    return list(zip(starts, starts[1:]+[len(rows)]))


def session_context(rows):
    days, contexts = deque(maxlen=21), []
    current, context = None, {}
    for i, row in enumerate(rows):
        if i and row["ts"] != rows[i-1]["next_ts"]:
            current, context = None, {}
            days.clear()
        if row["ts"] == row["session_open_ts"]:
            current = dict(row)
        elif current is not None:
            current.update(high=max(current["high"],row["high"]), low=min(current["low"],row["low"]), close=row["close"])
        if row["end_ts"] == row["session_close_ts"] and current is not None:
            days.append(current)
            current = None
            if len(days) == 21:
                w = list(days)
                price = w[-1]["close"]
                ma = sum(r["close"] for r in w[-20:])/20
                prior = sum(r["close"] for r in w[:-1])/20
                tr = [max(b["high"]-b["low"], abs(b["high"]-a["close"]), abs(b["low"]-a["close"])) for a,b in zip(w,w[1:])]
                atr = sum(tr[-14:])/14
                context = {"ready":True, "available_ts":row["end_ts"], "close":price, "ma20":ma,
                    "prior_ma20":prior, "momentum7":price/w[-8]["close"]-1, "atr":atr, "atr_pct":atr/price,
                    "ma_distance_atr":(price-ma)/atr if atr else 0,
                    "trend_up":price>ma and ma>prior, "trend_down":price<ma and ma<prior}
        contexts.append(context)
    return contexts


def features_for(rows, interval, cancelled=None):
    segments = prepare(rows, interval)
    features = [None]*len(rows)
    for start, end in segments:
        if cancelled and cancelled():
            raise InterruptedError("Stock practice cancelled")
        if end-start > 240:
            features[start:end] = build_feature_cache(rows[start:end], interval, simple_only=True)["features"]
    daily = session_context(rows)
    day, pv, volume, complete = None, 0., 0., False
    for i, (r, f) in enumerate(zip(rows, features)):
        if r["session"] != day:
            day, pv, volume = r["session"], 0., 0.
            complete = r["ts"] == r["session_open_ts"]
        elif i and r["ts"] != rows[i-1]["next_ts"]:
            complete = False
        pv += (r["high"]+r["low"]+r["close"])/3*r["volume"]
        volume += r["volume"]
        if f:
            f["daily"] = daily[i]
            f["session_vwap_ready"] = complete and volume > 0
            f["vwap_distance_atr"] = ((r["close"]-pv/volume)/f["_atr"] if complete and volume > 0 else 0.)
    return features


def stock_params(p, mode):
    return dict(p, direction="LONG", time_stop_hours=120 if mode == "swing" else 24)


def stock_policy(costs, mode, state=None, learn=True):
    p = AdaptivePolicy(state, costs["max_notional_fraction"], learn=learn,
                       fee_rate=costs["fee_rate"], slippage_rate=costs["slippage_rate"]+costs["half_spread"])
    p.candidates = [stock_params(c, mode) for c in p.candidates]
    return p


def execute(rows, features, start, end, costs, params, mode, fractional, policy=None,
            training=False, cancelled=None, liquidate_end=True, feedback=None):
    return simulate(rows, features, start, end, 500., costs["risk_per_trade"], costs["fee_rate"],
        costs["slippage_rate"]+costs["half_spread"], params, policy=policy,
        bar_interval_ms=INTERVAL_MS[rows[0].get("interval", "1m")], # caller stamps the declared timeframe
        daily_loss_limit=None if training else costs["daily_loss_limit"], training_examples=training,
        practice_cost_mode="eligible" if training else "all", cancelled=cancelled,
        stock_execution=True, close_at_session_end=mode == "day", fractional_shares=fractional,
        liquidate_end=liquidate_end, feedback=feedback)


def run_stock_practice(snapshot, manifest, progress=None, cancelled=None):
    progress = progress or (lambda **_:None)
    interval, mode = manifest["interval"], manifest["mode"]
    costs = validate_costs(manifest["settings"])
    fractional = manifest["fractional_shares"]
    rows = [dict(r, interval=interval) for r in snapshot["rows"]]
    if interval == "1d" and mode == "day":
        raise ValueError("Use an intraday timeframe for day trading; daily candles are for swing practice")
    progress(stage="features", message="Building stock indicators across scheduled exchange sessions")
    features = features_for(rows, interval, cancelled)
    later = int(len(rows)*.7)
    # Purge one wall-clock day, then round backwards to an observed close.
    development = bisect_left([r["end_ts"] for r in rows], rows[later]["ts"]-DAY)
    if development <= 260 or len(rows)-later < 80 or not any(features[:development]):
        raise ValueError("Too little continuous stock history for training and a later comparison. Choose more days, 1h/daily, or a deeper data provider.")
    seed = stock_policy(costs, mode)
    candidates, examples, diagnostics = seed.candidates, [], []
    for index, params in enumerate(candidates):
        progress(stage="training", message=f"Learning stock setups {index+1}/{len(candidates)} from earlier closed trades")
        metrics, trades = execute(rows, features, 240, development, costs, params, mode, fractional,
                                  training=True, cancelled=cancelled)
        resolved = [t for t in trades if t["reason"] != "END"]
        examples.extend((t["available_ts"], index, t["training_vector"], t["r_multiple"], trade_feedback(t), t["entry_ts"]) for t in resolved)
        diagnostics.append({"family":params["family"], "params":params, "resolved_examples":len(resolved),
                            "signal_funnel":metrics["signal_funnel"]})
    trainer = ChronologicalTrainer(seed, candidates, examples, cancelled)
    trainer.advance(rows[development-1]["end_ts"])
    initial = seed.export()
    fixed = stock_params(fixed_params(costs), mode)
    # The same price-based rules as the crypto experiment; scheduled closures
    # preserve retest levels by using the shared calendar-aware continuity check.
    retest = retest_features(rows, features, INTERVAL_MS[interval], fixed)
    variants = []
    for name in ("breakout", "retest", "break_even", "trailing", "frozen", "updating"):
        accounts = {}
        for scenario, multiplier in (("standard",1.), ("higher_cost",1.5)):
            progress(stage="testing", message=f"Stock practice: {name.replace('_',' ')} / {scenario.replace('_',' ')}")
            c = dict(costs, **{k:costs[k]*multiplier for k in ("fee_rate","slippage_rate","half_spread")})
            policy = stock_policy(c, mode, initial, name == "updating") if name in ("frozen","updating") else None
            p = dict(fixed, exit_policy={"break_even":BREAK_EVEN_EXIT, "trailing":TRAILING_EXIT}.get(name,FIXED_EXIT))
            metrics, trades = execute(rows, retest if name == "retest" else features, later, len(rows), c, p,
                                      mode, fractional, policy=policy, cancelled=cancelled)
            accounts[scenario] = account_report(metrics, trades,
                policy.state["observations"]-initial["observations"] if policy else 0,
                digest(policy.export()) if policy else None)
        variants.append({"id":name, "windows":{"later":{"start_ts":rows[later+1]["ts"], "end_ts":rows[-1]["end_ts"], **accounts}}})
    by_id = {v["id"]:v["windows"]["later"] for v in variants}
    comparisons = []
    for name, control in (("retest","breakout"),("break_even","breakout"),("trailing","breakout"),("updating","frozen")):
        a, b = by_id[control], by_id[name]
        comparisons.append({"control":control, "challenger":name,
            **assess_pair(a["standard"],b["standard"],a["higher_cost"],b["higher_cost"])})
    entry = rows[later+1]["open"]*(1+costs["slippage_rate"]+costs["half_spread"])
    qty = 500/(entry*(1+costs["fee_rate"]))
    factor = rows[later+1].get("split_factor",1.)
    qty = (math.floor(qty/factor*1e6)/1e6 if fractional else math.floor(qty/factor))*factor
    exit_price = rows[-1]["close"]*(1-costs["slippage_rate"]-costs["half_spread"])
    benchmark = qty*(exit_price-entry)-qty*(entry+exit_price)*costs["fee_rate"]
    report = {"version":VERSION, "asset_class":"equity", "symbol":manifest["symbol"], "interval":interval,
        "mode":mode, "costs":costs, "starting_balance":500., "fractional_shares":fractional,
        "data_sha256":digest(rows), "market_data":snapshot["market_data"], "coverage":snapshot["quality"],
        "development_end_ts":rows[development-1]["end_ts"], "later_start_ts":rows[later+1]["ts"],
        "end_ts":rows[-1]["end_ts"], "variants":variants, "comparisons":comparisons,
        "seed":{"resolved_examples":len(examples), "sha256":digest(initial), "last_label_ts":initial["last_label_ts"]},
        "training":diagnostics, "model":initial, "evaluation_kind":"historical_development",
        "validated":False, "eligible_for_trading":False, "cash_benchmark_net":0.,
        "buy_hold_price_return":{"net_pnl":benchmark, "return_pct":benchmark/5, "dividends_included":False,
            "scope":"Full $500 cash allocation, unlike the strategy risk sizing; price-only benchmark."},
        "limitations":["US-listed USD stocks and ETFs, long-only, unleveraged regular-session paper practice.",
            "Each variant is a separate $500 account, not a combined portfolio. Costs are assumptions, not a broker fee schedule.",
            "Historical development research, not unseen validation. Today's watchlist has survivorship and selection bias.",
            "Split-adjusted prices; cash dividends and dividend reinvestment are excluded. This is not total return.",
            "Gaps through stops fill at the observed opening price. Intrabar ambiguity assumes stop first.",
            "A missing scheduled candle stops an open account; market closures do not. Halts are not synthesized.",
            "Day mode exits at the final session candle; its close is a simulation assumption, not a guaranteed auction fill.",
            "Swing deadlines use elapsed time and execute at the next observed candle close after the deadline.",
            "No stock broker execution, short borrowing, leverage, settlement or margin-rule simulation."]}
    return report
