"""Fixed, reproducible first screen using the application's stock backtester."""
import argparse
import copy
import gc
import hashlib
import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--only", help="Run one SYMBOL:strategy job, preserving completed results")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    sys.path.insert(0, str(repo))
    from lab.equity_data import EquityData
    from lab.strategy_lab import run_backtest
    from strategies import load_strategy

    plan = json.loads((ROOT / "plan.json").read_text())
    cutoff = int(datetime.fromisoformat(plan["cutoff_utc"]).timestamp() * 1000)
    jobs = sorted({(s, c["interval"], c["days"]) for s in plan["symbols"] for c in plan["candidates"]})

    def fetch(job):
        symbol, interval, days = job
        path = ROOT / "data" / f"{symbol}-{interval}.json"
        if path.exists():
            result = json.loads(path.read_text())
        else:
            result = EquityData().history(symbol, interval, days, cutoff=cutoff, provider="yahoo")
            save(path, result)
        return job, result

    data, errors = {}, []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(fetch, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                _, result = future.result()
                data[job[:2]] = result
                print(json.dumps({"download": job, "rows": len(result["rows"]), "quality": result["quality"]}), flush=True)
            except Exception as exc:
                error = {"download": job, "error": f"{type(exc).__name__}: {exc}"}
                errors.append(error)
                print(json.dumps(error), flush=True)
    save(ROOT / "download-errors.json", errors)
    if args.download_only:
        return

    manifest = {
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": hashlib.sha256((ROOT / "plan.json").read_bytes()).hexdigest(),
        "code_sha256": {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for folder in ("lab", "strategies") for p in sorted((repo / folder).glob("*.py"))},
        "data_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "data").glob("*.json"))},
    }
    save(ROOT / "manifest.json", manifest)
    summaries = json.loads((ROOT / "results.json").read_text()) if (ROOT / "results.json").exists() else []
    for candidate in plan["candidates"]:
        for symbol in plan["symbols"]:
            if args.only and args.only != f"{symbol}:{candidate['strategy']}":
                continue
            if any(x["symbol"] == symbol and x["strategy"] == candidate["strategy"] and x["status"] == "tested" for x in summaries):
                continue
            key = (symbol, candidate["interval"])
            if key not in data:
                summaries.append({"symbol": symbol, **candidate, "status": "no_data"})
                continue
            source = data[key]
            strategy = load_strategy(candidate["strategy"])
            print(f"Testing {symbol} {strategy.name} {candidate['interval']}", flush=True)
            try:
                report = run_backtest(strategy, copy.deepcopy(source["rows"]), candidate["interval"],
                    dict(plan["costs"]), starting_balance=plan["starting_balance_per_independent_test"],
                    stock_execution=True, close_at_session_end=candidate["mode"] == "day",
                    fractional_shares=plan["fractional_shares"], progress=lambda msg: print(msg, flush=True))
                report.update(symbol=symbol, mode=candidate["mode"], strategy_parameters=strategy.params,
                              source_quality=source["quality"], market_data=source["market_data"])
                path = ROOT / "reports" / f"{symbol}-{strategy.name}-{candidate['interval']}.json"
                save(path, report)
                summary = {"symbol": symbol, **candidate, "status": "tested", "report": str(path.relative_to(ROOT)),
                           **{k: report[k] for k in ("development", "later", "later_higher_cost", "eligible_for_bot")}}
                summaries.append(summary)
                print(json.dumps(summary), flush=True)
            except Exception as exc:
                traceback.print_exc()
                summaries.append({"symbol": symbol, **candidate, "status": "error", "error": str(exc)})
            save(ROOT / "results.json", summaries)
            gc.collect()
    save(ROOT / "results.json", summaries)


if __name__ == "__main__":
    main()
