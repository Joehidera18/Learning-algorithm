"""Replay real Coinbase history or a supplied OHLCV CSV without a live feed."""
import argparse
import json
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from lab.continuous import DEFAULTS
from lab.coinbase_feed import REST
from lab.data import load_history, INTERVAL_MS
from lab.paper_store import init_continuous_db
from lab.research import ResearchManager, research
from lab.learning_research import learn_history
from lab.study_plan import HISTORY_DAYS, INTERVAL_HISTORY_LIMITS, study_days, history_coverage


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", type=Path, help="Existing historical candles; source is supplied by you")
    source.add_argument("--coinbase", action="store_true", help="Download recorded prices from Coinbase's public API")
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--interval", choices=["5m", "15m", "1h", "6h"], default="15m")
    parser.add_argument("--fee", type=float, default=.004, help="Fee fraction per side; .004 means 0.4%%")
    parser.add_argument("--slippage", type=float, default=.0005)
    parser.add_argument("--learning", action="store_true", help="Train and evaluate the adaptive policy used by automatic learning")
    parser.add_argument("--daily-csv", type=Path, help="Optional recorded 1d OHLCV candles for --csv --learning; included as completed context only")
    parser.add_argument("--bitcoin-csv", type=Path, help="Optional recorded BTC-USD 1d OHLCV candles for --csv --learning; completed market context only")
    parser.add_argument("--events-json", type=Path, help="Recorded event-observation archive for --learning; never downloaded or backdated during replay")
    parser.add_argument("--days", type=int, help="History days: up to 365 for 5m, 1825 for 15m, 2920 for 1h/6h; default five years subject to these limits")
    parser.add_argument("--end", help="Optional exclusive historical end date, YYYY-MM-DD in UTC; requires --coinbase")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/automatic"), help="Saved Coinbase download directory")
    parser.add_argument("--out", type=Path, default=Path("research-result.json"))
    args = parser.parse_args(argv)
    if args.events_json and not args.learning:
        parser.error("--events-json requires --learning")
    if args.daily_csv and (not args.csv or not args.learning):
        parser.error("--daily-csv requires --csv and --learning")
    if args.bitcoin_csv and (not args.csv or not args.learning):
        parser.error("--bitcoin-csv requires --csv and --learning")
    import re
    if args.coinbase and not re.fullmatch(r"[A-Z0-9]{2,16}-USD", args.symbol):
        parser.error("Use a Coinbase USD market such as BTC-USD")
    args.days = study_days(args.interval, HISTORY_DAYS) if args.days is None else args.days
    if not 30 <= args.days <= INTERVAL_HISTORY_LIMITS[args.interval]:
        parser.error(f"Download history for {args.interval} must be 30–{INTERVAL_HISTORY_LIMITS[args.interval]} days; use 1h or 6h for up to eight years")
    end_ms = None
    if args.end:
        if not args.coinbase:
            parser.error("--end requires --coinbase; CSV dates are taken from the file")
        try:
            end_ms = int(datetime.combine(date.fromisoformat(args.end), datetime.min.time(), timezone.utc).timestamp()*1000)
        except ValueError:
            parser.error("Use YYYY-MM-DD for --end")
        if end_ms > time.time()*1000:
            parser.error("The historical end date cannot be in the future")
    settings = {**DEFAULTS, "decision_interval": args.interval, "fee_rate": args.fee, "slippage_rate": args.slippage}
    if args.coinbase and end_ms is None:
        step = INTERVAL_MS[args.interval]
        end_ms = int(time.time()*1000)//step*step
    if not 0 <= args.fee <= .02 or not 0 <= args.slippage <= .01:
        parser.error("Fee or slippage is outside the supported range")
    daily_rows, daily_source = None, None
    bitcoin_rows, bitcoin_source = None, None
    if args.coinbase:
        # The temporary research controller does not create a trading account or
        # connect a ticker. Download chunks persist in the explicit cache folder.
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory)/"download.sqlite3"
            init_continuous_db(db)
            downloader = ResearchManager(db, args.cache_dir)
            downloader._update = lambda **status: print(status.get("message", ""), flush=True)
            try:
                rows = downloader._history(args.symbol, args.interval, args.days, end_ms=end_ms)
                if args.learning and rows:
                    daily_rows, daily_source = downloader.daily_history(args.symbol, args.days,
                        rows[-1]["ts"]+INTERVAL_MS[args.interval])
                    bitcoin_rows, bitcoin_source = ((daily_rows, daily_source) if args.symbol == "BTC-USD" else
                        downloader.daily_history("BTC-USD", args.days, rows[-1]["ts"]+INTERVAL_MS[args.interval]))
            except Exception as exc:
                print(f"Real Coinbase history could not be downloaded: {exc}. No substitute prices were generated.")
                return 1
        provenance = {"provider":"Coinbase Exchange", "kind":"recorded_market_candles",
            "endpoint":REST+f"/products/{args.symbol}/candles", "synthetic_fallback":False,
            "retrieval":"Public candle API with saved local download chunks",
            "gap_repair":downloader.data_reports.get((args.symbol, args.interval)),
            "daily_context":daily_source, "bitcoin_context":bitcoin_source}
    else:
        rows = load_history(args.csv)
        if args.daily_csv:
            daily_rows = load_history(args.daily_csv)
        if args.bitcoin_csv:
            bitcoin_rows = load_history(args.bitcoin_csv)
        provenance = {"provider":"User-supplied CSV (source not independently verified)",
            "kind":"provided_ohlcv", "filename":args.csv.name, "synthetic_fallback":False}
    event_snapshot = None
    if args.events_json:
        from lab.event_context import validate_snapshot
        event_snapshot = validate_snapshot(json.loads(args.events_json.read_text()))
    if args.learning:
        result = learn_history(rows, args.symbol, settings,
            progress=lambda **status: print(status.get("message", ""), flush=True), daily_rows=daily_rows,
            bitcoin_rows=bitcoin_rows, event_snapshot=event_snapshot)
    else:
        result = research(rows, args.symbol, settings,
            progress=lambda stage, done, total, message: print(f"{done}/{total} {message}", flush=True))
    result["market_data"] = provenance
    if args.coinbase:
        step = INTERVAL_MS[args.interval]
        cutoff = int(time.time()*1000 if end_ms is None else end_ms)//step*step
        result["history_request"] = history_coverage(rows, args.interval, args.days, cutoff)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False))
    print("Historical gate:", "PASSED for further paper testing" if result["validated"] else "NOT PASSED")
    print(args.out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
