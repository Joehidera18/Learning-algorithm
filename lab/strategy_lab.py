"""Backtest a named strategy on historical bars. Missing candles stay missing.

Decision bars drive fills. Higher timeframes are attached only after they have
closed. The engine never invents a bar, never uses a future close, and never
asks a language model during the run.
"""
from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path

from .data import INTERVAL_MS, validate_history
from .engine import build_feature_cache
from .execution import simulate
from .finances import closed_trade_totals
from .study_plan import ACTIVE_INTERVALS
from .market_clock import consecutive

DECISION_INTERVALS = ("1m", "5m", "15m", "30m", "1h", "4h")
REPORT_VERSION = 3


def _end(row, interval):
    return int(row.get("end_ts", row["ts"] + INTERVAL_MS[interval]))


def _index_ends(rows, interval):
    return [_end(row, interval) for row in rows]


def attach_closed_context(decision_rows, decision_interval, frames):
    previous_session_close = {}
    equity = bool(decision_rows and decision_rows[0].get("asset_class") == "equity")
    if equity:
        from .equity_data import schedule_between, DAY
        schedule = schedule_between(decision_rows[0]["ts"] - 14*DAY,
                                    _end(decision_rows[-1], decision_interval))
        previous_session_close = {b[0]: a[2] for a, b in zip(schedule, schedule[1:])}
    catalogs = {}
    for interval, rows in frames.items():
        if interval not in INTERVAL_MS:
            raise ValueError("Unsupported context interval: " + interval)
        ends = _index_ends(rows, interval)
        if (any(a["ts"] >= b["ts"] for a, b in zip(rows, rows[1:])) or
                any(a >= b for a, b in zip(ends, ends[1:]))):
            raise ValueError("Context candles must be ordered and unique")
        catalogs[interval] = (rows, ends)
    attached = 0
    missing = {interval: 0 for interval in frames}
    for row in decision_rows:
        close = _end(row, decision_interval)
        bag = {}
        for interval, (rows, ends) in catalogs.items():
            step = INTERVAL_MS[interval]
            expected_end = close // step * step
            if equity:
                opening, closing = row["session_open_ts"], row["session_close_ts"]
                elapsed = (close - opening) // step
                expected_end = (closing if close == closing else opening + elapsed*step
                                if elapsed else previous_session_close.get(row["session"]))
            i = bisect_right(ends, close) - 1
            if i < 0:
                bag[interval] = {"ready": False, "reason": "no_closed_context_bar"}
                missing[interval] += 1
                continue
            if ends[i] != expected_end:
                bag[interval] = {"ready": False, "reason": "missing_expected_context_bar",
                                 "expected_end_ts": expected_end, "last_observed_end_ts": ends[i]}
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
            "rule": "Use the most recent expected closed bar; a missing bar is unavailable. Stock closures follow the exchange calendar."}


def attach_features(rows, interval, frames=None, cancelled=None):
    if rows and rows[0].get("asset_class") == "equity":
        from .equity_research import features_for
        features = features_for(rows, interval, cancelled=cancelled)
    else:
        starts = [0] + [i for i in range(1, len(rows))
                        if not consecutive(rows[i-1], rows[i], INTERVAL_MS[interval])]
        features = [None]*len(rows)
        for start, end in zip(starts, starts[1:]+[len(rows)]):
            if cancelled and cancelled():
                raise InterruptedError("Backtest cancelled")
            if end-start > 240:
                features[start:end] = build_feature_cache(rows[start:end], interval, simple_only=True)["features"]
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
    complete = metrics.get("complete") is True
    return {
        "window": window,
        "trades": len(resolved),
        # Account P/L includes marked END exits; those exits do not count as
        # independently resolved trades for the evidence threshold.
        "net_pnl": metrics.get("net_pnl") if complete else None,
        **{key: metrics.get(key) if complete else None for key in (
            "ending_balance", "return_pct", "max_drawdown_pct", "profit_factor", "fees_paid")},
        "closed_net_pnl": totals["net_pnl"],
        "window_end_exits": sum(t.get("reason") == "END" for t in trades),
        "win_rate": totals["win_rate"] if complete else None,
        "mean_r": (sum(rs) / len(rs)) if complete and rs else None,
        "sum_r": (sum(rs) if rs else 0.) if complete else None,
        "signal_funnel": metrics.get("signal_funnel", {}),
        "complete": complete,
        "incomplete_reason": metrics.get("incomplete_reason"),
        "stopped_at_ts": metrics.get("stopped_at_ts"),
        "unresolved_positions": metrics.get("unresolved_positions", 0),
    }


def run_backtest(strategy, rows, interval, costs, frames=None, starting_balance=500.,
                 stock_execution=False, close_at_session_end=False, cancelled=None,
                 articles=None, fractional_shares=True, progress=None):
    progress = progress or (lambda message: None)
    def checkpoint(message):
        if cancelled and cancelled():
            raise InterruptedError("Backtest cancelled")
        progress(message)
    if interval not in DECISION_INTERVALS:
        raise ValueError("Decision interval must be one of " + ", ".join(DECISION_INTERVALS))
    if any(iv not in ACTIVE_INTERVALS for iv in (frames or {})):
        raise ValueError("Context interval not in the supported set")
    coverage = validate_history(rows, interval)
    if not coverage["valid"] or any(a["ts"] >= b["ts"] for a, b in zip(rows, rows[1:])):
        raise ValueError("Decision candles must be valid, ordered and unique")
    if stock_execution:
        from .equity_data import slots
        expected = slots(interval, rows[0]["ts"], rows[-1]["end_ts"])
        coverage = {"valid": True, "rows": len(rows), "expected_candles": len(expected),
                    "missing_candles": len(expected)-len(rows),
                    "coverage_pct": 100*len(rows)/len(expected) if expected else 0,
                    "calendar": "NYSE regular sessions"}
    checkpoint("Building indicators from completed stock candles")
    features, alignment = attach_features(rows, interval, frames, cancelled=cancelled)
    news_alignment = None
    if articles is not None:
        from news.attach import attach_news
        news_alignment = attach_news(rows, features, articles, INTERVAL_MS[interval])
    strategy.prepare(rows, features, interval)
    params = dict(strategy.params)
    params.setdefault("family", strategy.name)
    params.setdefault("direction", strategy.direction)
    params["require_context"] = list(strategy.require_context)
    if stock_execution:
        params["time_stop_hours"] = 24 if close_at_session_end else 120
    if "max_notional_fraction" in costs:
        params["max_notional_fraction"] = costs["max_notional_fraction"]
    start, later, end = split_later(rows)
    fee, slip = costs["fee_rate"], costs["slippage_rate"] + costs.get("half_spread", 0.)
    bar_ms = INTERVAL_MS[interval]

    def evaluator(feat, trade_params):
        missing = [iv for iv in strategy.require_context
                   if not feat.get("mtf", {}).get(iv, {}).get("ready")]
        if missing:
            return None, "higher_timeframe_not_ready:" + ",".join(missing)
        return strategy.signal(feat, trade_params)

    def levels(feat):
        custom = strategy.levels(feat, params)
        return custom if custom is not None else _default_levels(feat, params)

    common = dict(rows=rows, features=features, balance=starting_balance,
                  risk=costs.get("risk_per_trade", 0.0075), fee_rate=fee, base_slip=slip,
                  params=params, signal_evaluator=evaluator, level_provider=levels,
                  bar_interval_ms=bar_ms, stock_execution=stock_execution,
                  close_at_session_end=close_at_session_end, cancelled=cancelled,
                  daily_loss_limit=costs.get("daily_loss_limit"), fractional_shares=fractional_shares)
    checkpoint("Testing the earlier development window")
    dev_metrics, dev_trades = simulate(start=start, end=later, **common)
    checkpoint("Testing the later historical window")
    later_metrics, later_trades = simulate(start=later, end=end, **common)
    stressed = dict(costs)
    stressed["fee_rate"] = costs["fee_rate"] * 1.5
    stressed["slippage_rate"] = costs["slippage_rate"] * 1.5
    if "half_spread" in costs:
        stressed["half_spread"] = costs["half_spread"] * 1.5
    fee_s = stressed["fee_rate"]
    slip_s = stressed["slippage_rate"] + stressed.get("half_spread", 0.)
    checkpoint("Retesting the later window at 1.5× trading costs")
    stress_metrics, stress_trades = simulate(
        start=later, end=end, **dict(common, fee_rate=fee_s, base_slip=slip_s))
    dev_summary = _summarize(dev_metrics, dev_trades, "development")
    later_summary = _summarize(later_metrics, later_trades, "later")
    stress_summary = _summarize(stress_metrics, stress_trades, "later_1.5x_costs")
    for summary, first, last in ((dev_summary, start, later), (later_summary, later, end),
                                  (stress_summary, later, end)):
        summary.update(start_ts=rows[first]["ts"], end_ts=_end(rows[last-1], interval),
                       observed_candles=last-first)
    promoted = bool(
        later_summary["complete"] and stress_summary["complete"]
        and later_summary["trades"] >= 20 and stress_summary["trades"] >= 20
        and (later_summary["mean_r"] or 0) > 0
        and later_summary["net_pnl"] > 0
        and (stress_summary["mean_r"] or 0) > 0
        and (stress_summary["net_pnl"] or 0) > 0
    )
    from .experiments import compact_trade
    return {
        "kind": "strategy_lab",
        "report_version": REPORT_VERSION,
        "strategy": strategy.name,
        "strategy_version": strategy.version,
        "interval": interval,
        "context_intervals": sorted(frames or {}),
        "coverage": coverage,
        "mtf_alignment": alignment,
        "news_alignment": news_alignment,
        "costs": costs,
        "starting_balance": starting_balance,
        "fractional_shares": fractional_shares,
        "development": dev_summary,
        "later": later_summary,
        "later_higher_cost": stress_summary,
        "trade_journal": {key: [compact_trade(t) for t in trades] for key, trades in (
            ("development", dev_trades), ("later", later_trades), ("later_higher_cost", stress_trades))},
        "eligible_for_bot": promoted,
        "promotion_rule": "Both later tests must complete with >=20 resolved trades, positive mean R and positive total account P/L, including at 1.5x costs. Not live authorization.",
        "limitations": [
            "Historical bars only. No live quotes.",
            "Each window starts with a fresh paper balance; the first 240 candles warm up indicators. Repeatedly selecting on later results can overfit.",
            "Day mode exits at the session close. Swing mode allows overnight positions with a 120-hour time stop. Long-only and unleveraged.",
            "END exits mark positions at the test boundary, count toward account P/L, and are excluded from the resolved-trade evidence count.",
            "Profit factor uses all simulated exits, including boundary marks; a missing value can mean no losses, not a guaranteed edge.",
            "Missing decision bars reset indicator warmup; a gap during an open position makes account P/L unknown and blocks eligibility.",
            "Higher-timeframe context must match the latest expected close; missing bars are unavailable.",
            "News is visible only after its published timestamp.",
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
