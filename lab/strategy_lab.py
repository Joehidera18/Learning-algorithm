"""Backtest a named strategy on historical bars. Missing candles stay missing.

Decision bars drive fills. Higher timeframes are attached only after they have
closed. The engine never invents a bar, never uses a future close, and never
asks a language model during the run.
"""
from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path

from .data import INTERVAL_MS, load_history, validate_history
from .engine import build_feature_cache
from .execution import simulate
from .finances import closed_trade_totals
from .study_plan import ACTIVE_INTERVALS

DECISION_INTERVALS = ("1m", "5m", "15m", "30m", "1h", "4h")


def _end(row, interval):
    return int(row.get("end_ts", row["ts"] + INTERVAL_MS[interval]))


def _index_ends(rows, interval):
    return [_end(row, interval) for row in rows]


def attach_closed_context(decision_rows, decision_interval, frames):
    """Attach the last higher-timeframe bar whose close is at or before this close.

    frames: {interval: rows}. A missing closed bar is recorded as ready=False.
    No forward-fill. No interpolation.
    """
    catalogs = {}
    for interval, rows in frames.items():
        if interval not in INTERVAL_MS:
            raise ValueError("Unsupported context interval: " + interval)
        catalogs[interval] = (rows, _index_ends(rows, interval))
    attached = 0
    missing = {interval: 0 for interval in frames}
    for row in decision_rows:
        close = _end(row, decision_interval)
        bag = {}
        for interval, (rows, ends) in catalogs.items():
            i = bisect_right(ends, close) - 1
            if i < 0:
                bag[interval] = {"ready": False, "reason": "no_closed_context_bar"}
                missing[interval] += 1
                continue
            src = rows[i]
            bag[interval] = {
                "ready": True,
                "ts": src["ts"],
                "end_ts": ends[i],
                "open": src["open"],
                "high": src["high"],
                "low": src["low"],
                "close": src["close"],
                "volume": src.get("volume", 0),
            }
            attached += 1
        row["mtf"] = bag
    return {"decision_bars": len(decision_rows), "context_bars_attached": attached,
            "missing_closed_context": missing,
            "rule": "Context uses only bars with end_ts <= decision close. Gaps stay gaps."}


def attach_features(rows, interval, frames=None):
    cache = build_feature_cache(rows, interval, simple_only=True)
    features = cache["features"]
    alignment = {"decision_bars": len(rows), "context_bars_attached": 0,
                 "missing_closed_context": {}, "rule": "No higher-timeframe frames supplied."}
    if frames:
        alignment = attach_closed_context(rows, interval, frames)
        for feat, row in zip(features, rows):
            if feat is not None:
                feat["mtf"] = row.get("mtf", {})
    return features, alignment


def split_later(rows, fraction=0.7):
    if len(rows) < 400:
        raise ValueError("Need at least 400 decision bars to split development and later test")
    cut = int(len(rows) * fraction)
    return 240, cut, len(rows)


def _summarize(metrics, trades, window):
    resolved = [t for t in trades if t.get("reason") != "END"]
    totals = closed_trade_totals(t.get("pnl", 0) for t in resolved) if resolved else {
        "status": "available", "closed_trades": 0, "winning_trades": 0, "losing_trades": 0,
        "break_even_trades": 0, "money_won": 0., "money_lost": 0., "net_pnl": 0., "win_rate": None}
    rs = [t["pnl"] / t["risk_dollars"] for t in resolved if t.get("risk_dollars")]
    return {
        "window": window,
        "trades": len(resolved),
        "net_pnl": totals["net_pnl"],
        "win_rate": totals["win_rate"],
        "mean_r": (sum(rs) / len(rs)) if rs else None,
        "sum_r": sum(rs) if rs else 0.,
        "signal_funnel": metrics.get("signal_funnel", {}),
        "complete": metrics.get("complete", True),
    }


def run_backtest(strategy, rows, interval, costs, frames=None, starting_balance=500.,
                 stock_execution=False, close_at_session_end=False, cancelled=None):
    if interval not in DECISION_INTERVALS:
        raise ValueError("Decision interval must be one of " + ", ".join(DECISION_INTERVALS))
    if any(iv not in ACTIVE_INTERVALS for iv in (frames or {})):
        raise ValueError("Context interval not in the supported set")
    coverage = validate_history(rows, interval)
    features, alignment = attach_features(rows, interval, frames)
    strategy.prepare(rows, features, interval)
    params = dict(strategy.params)
    params.setdefault("family", strategy.name)
    params.setdefault("direction", strategy.direction)
    params["require_context"] = list(strategy.require_context)
    start, later, end = split_later(rows)
    fee, slip = costs["fee_rate"], costs["slippage_rate"] + costs.get("half_spread", 0.)
    bar_ms = INTERVAL_MS[interval]

    def evaluator(feat, trade_params):
        return strategy.signal(feat, trade_params)

    def levels(feat):
        custom = strategy.levels(feat, params)
        return custom if custom is not None else _default_levels(feat, params)

    common = dict(rows=rows, features=features, balance=starting_balance,
                  risk=costs.get("risk_per_trade", 0.0075), fee_rate=fee, base_slip=slip,
                  params=params, signal_evaluator=evaluator, level_provider=levels,
                  bar_interval_ms=bar_ms, stock_execution=stock_execution,
                  close_at_session_end=close_at_session_end, cancelled=cancelled)
    dev_metrics, dev_trades = simulate(start=start, end=later, **common)
    later_metrics, later_trades = simulate(start=later, end=end, **common)
    stressed = dict(costs)
    stressed["fee_rate"] = costs["fee_rate"] * 1.5
    stressed["slippage_rate"] = costs["slippage_rate"] * 1.5
    if "half_spread" in costs:
        stressed["half_spread"] = costs["half_spread"] * 1.5
    fee_s = stressed["fee_rate"]
    slip_s = stressed["slippage_rate"] + stressed.get("half_spread", 0.)
    stress_metrics, stress_trades = simulate(
        start=later, end=end, **dict(common, fee_rate=fee_s, base_slip=slip_s))
    later_summary = _summarize(later_metrics, later_trades, "later")
    stress_summary = _summarize(stress_metrics, stress_trades, "later_1.5x_costs")
    promoted = bool(
        later_summary["trades"] >= 20
        and (later_summary["mean_r"] or 0) > 0
        and later_summary["net_pnl"] > 0
        and (stress_summary["mean_r"] or 0) > 0
    )
    return {
        "kind": "strategy_lab",
        "strategy": strategy.name,
        "strategy_version": strategy.version,
        "interval": interval,
        "context_intervals": sorted(frames or {}),
        "coverage": coverage,
        "mtf_alignment": alignment,
        "costs": costs,
        "starting_balance": starting_balance,
        "development": _summarize(dev_metrics, dev_trades, "development"),
        "later": later_summary,
        "later_higher_cost": stress_summary,
        "eligible_for_bot": promoted,
        "promotion_rule": "Later window: >=20 trades, mean R > 0, net PnL > 0, and mean R > 0 at 1.5x costs. Not live authorization.",
        "limitations": [
            "Historical bars only. No live quotes.",
            "A missing decision bar skips the fill and does not invent a path.",
            "Higher-timeframe context is the last bar that already closed.",
            "Yahoo/Alpaca 1m history is short; do not treat a 29-day 1m test as multi-year evidence.",
        ],
    }


def _default_levels(feat, params):
    from .trade_quality import signal_atr
    close = float(feat.get("_close", 0))
    atr = max(signal_atr(feat, params), close * 0.002)
    distance = max(atr * params["stop_atr"], close * 0.0015)
    stop = close - distance
    target = close + distance * params["rr2"]
    return stop, target, target, 0.5


def write_report(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
