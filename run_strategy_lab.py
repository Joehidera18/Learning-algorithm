#!/usr/bin/env python3
"""Run one named strategy on historical data. Does not place live orders."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab.data import INTERVAL_MS, load_history, validate_history
from lab.equity_data import EquityData, YAHOO_LIMITS
from lab.equity_research import DEFAULT_COSTS as STOCK_COSTS
from lab.strategy_lab import DECISION_INTERVALS, run_backtest, write_report
from strategies import list_strategies, load_strategy

CRYPTO_COSTS = {"fee_rate": 0.004, "slippage_rate": 0.0005, "half_spread": 0.0,
                "risk_per_trade": 0.0075}


def _parse_intervals(raw):
    items = [part.strip() for part in (raw or "").split(",") if part.strip()]
    for item in items:
        if item not in INTERVAL_MS:
            raise SystemExit("Unsupported interval %r" % item)
    return items


def main():
    parser = argparse.ArgumentParser(description="Strategy lab backtest (historical only)")
    parser.add_argument("--strategy", default="", help="Registered strategy name")
    parser.add_argument("--symbol", default="")
    parser.add_argument("--asset", choices=("equity", "crypto"), default="equity")
    parser.add_argument("--decision", default="15m", choices=DECISION_INTERVALS)
    parser.add_argument("--context", default="1h,4h",
                        help="Comma-separated higher timeframes, or empty")
    parser.add_argument("--days", type=int, default=59)
    parser.add_argument("--csv-dir", default="", help="For crypto: folder of SYMBOL_interval.csv files")
    parser.add_argument("--provider", default="yahoo", choices=("yahoo", "alpaca"))
    parser.add_argument("--out", default="")
    parser.add_argument("--list", action="store_true", help="Print registered strategies and exit")
    args = parser.parse_args()
    if args.list:
        print("\n".join(list_strategies()) or "(none)")
        return
    if not args.strategy or not args.symbol:
        raise SystemExit("Provide --strategy and --symbol, or pass --list")
    strategy = load_strategy(args.strategy)
    context = [iv for iv in _parse_intervals(args.context) if iv != args.decision]
    frames = {}
    stock = args.asset == "equity"
    if stock:
        data = EquityData()
        limit = YAHOO_LIMITS[args.decision] if args.provider == "yahoo" else 180
        if args.days > limit:
            raise SystemExit("%s %s history is capped at %s days" % (args.provider, args.decision, limit))
        snap = data.history(args.symbol, args.decision, args.days, provider=args.provider)
        rows = snap["rows"]
        for interval in context:
            cap = YAHOO_LIMITS[interval] if args.provider == "yahoo" else 180
            ctx = data.history(args.symbol, interval, min(args.days, cap), provider=args.provider)
            frames[interval] = ctx["rows"]
        costs = dict(STOCK_COSTS)
    else:
        folder = Path(args.csv_dir or "data")
        path = folder / ("%s_%s.csv" % (args.symbol, args.decision))
        if not path.exists():
            raise SystemExit("Missing %s. Download history first; the lab does not invent candles." % path)
        rows = load_history(path)
        for interval in context:
            cpath = folder / ("%s_%s.csv" % (args.symbol, interval))
            if not cpath.exists():
                raise SystemExit("Missing context file %s" % cpath)
            frames[interval] = load_history(cpath)
        costs = dict(CRYPTO_COSTS)
    quality = validate_history(rows, args.decision)
    if quality["bad_ohlc"] or quality["duplicates"]:
        raise SystemExit("Decision series failed validation: %s" % quality)
    report = run_backtest(
        strategy, rows, args.decision, costs, frames=frames or None,
        stock_execution=stock, close_at_session_end=stock)
    report["symbol"] = args.symbol
    report["asset_class"] = args.asset
    report["provider"] = args.provider if stock else "csv"
    dest = Path(args.out or ("strategy-lab-%s-%s-%s.json" % (args.strategy, args.symbol, args.decision)))
    write_report(report, dest)
    print(json.dumps({
        "wrote": str(dest),
        "strategy": report["strategy"],
        "later_trades": report["later"]["trades"],
        "later_net_pnl": report["later"]["net_pnl"],
        "later_mean_r": report["later"]["mean_r"],
        "eligible_for_bot": report["eligible_for_bot"],
        "coverage_pct": report["coverage"]["coverage_pct"],
        "missing_context": report["mtf_alignment"]["missing_closed_context"],
    }, indent=2))


if __name__ == "__main__":
    main()
