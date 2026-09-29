"""Replay frozen source snapshots; never download data or place orders.

Usage: python research/day-strategy-candidates/run_study.py --output /tmp/day-study
An existing output directory is refused to preserve previous evidence.
"""
import argparse
import copy
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
from lab.strategy_lab import run_backtest
from strategies import load_strategy


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit("Choose a new output directory; existing evidence is preserved.")
    plan = json.loads((ROOT / "plan.json").read_text())
    frozen = json.loads((ROOT / "input_manifest.json").read_text())
    data = {}
    for symbol in plan["symbols"]:
        path = ROOT / "data" / (symbol + "-5m.json.gz")
        if digest(path) != frozen["snapshots"][path.name]["sha256"]:
            raise SystemExit("Input checksum mismatch: " + path.name)
        data[symbol] = json.loads(gzip.decompress(path.read_bytes()))
    manifest = {
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "packages": {p: importlib.metadata.version(p) for p in ("pandas", "pandas-market-calendars", "numpy")},
        "plan_sha256": digest(ROOT / "plan.json"),
        "runner_sha256": digest(Path(__file__)),
        "input_manifest_sha256": digest(ROOT / "input_manifest.json"),
        "code_sha256": {str(p.relative_to(REPO)): digest(p) for folder in ("lab", "strategies")
                        for p in sorted((REPO / folder).glob("*.py"))},
    }
    save(out / "manifest.json", manifest)
    results = []
    for candidate in plan["candidates"]:
        for symbol in plan["symbols"]:
            strategy = load_strategy(candidate["strategy"])
            source = data[symbol]
            report = run_backtest(strategy, copy.deepcopy(source["rows"]), "5m",
                dict(plan["costs"]), starting_balance=plan["starting_balance_per_independent_test"],
                stock_execution=True, close_at_session_end=True, fractional_shares=True)
            report.update(symbol=symbol, source_quality=source["quality"], market_data=source["market_data"])
            path = out / "reports" / (symbol + "-" + strategy.name + ".json")
            save(path, report)
            summary = {"symbol": symbol, "strategy": strategy.name, "report": str(path.relative_to(out)),
                **{k: report[k] for k in ("development", "later", "later_higher_cost", "sample", "eligible_for_bot", "research_only")}}
            results.append(summary)
            save(out / "results.json", results)
            print(json.dumps({"symbol": symbol, "strategy": strategy.name,
                "later_return": report["later"]["return_pct"], "later_trades": report["later"]["trades"],
                "stressed_return": report["later_higher_cost"]["return_pct"]}), flush=True)


if __name__ == "__main__":
    main()
