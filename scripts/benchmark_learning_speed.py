"""Time pinned learner sources on the same real candles and verify exact results.

Run each source in a separate, otherwise idle process. Creation timestamps are
the only report field omitted from the result digest. Profiler timings are not
used as throughput measurements. No model is installed and no order is placed.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import platform
import resource
import sys
import time
import zipfile


def digest_report(report):
    stable = {key:value for key,value in report.items() if key != "created_at"}
    digest = hashlib.sha256()
    for chunk in json.JSONEncoder(sort_keys=True, allow_nan=False, separators=(",", ":")).iterencode(stable):
        digest.update(chunk.encode())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--primary-only", action="store_true", help="Omit the two independent policy experiments in both sources")
    parser.add_argument("--last-candles", type=int, help="Optional fixed tail for short profiling; normal measurement uses the full bundle")
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve()))
    from lab.continuous import DEFAULTS
    from lab.data import INTERVAL_MS
    from lab.evaluation import dataset_digest
    from lab.learning_research import learn_history

    source = hashlib.sha256()
    for path in sorted((args.repo/"lab").glob("*.py")):
        source.update(path.name.encode()+b"\0"+path.read_bytes())

    def decode(archive, name):
        return [{key:int(value) if key in ("ts", "trades") else float(value)
                 for key,value in row.items()}
                for row in csv.DictReader(io.StringIO(archive.read(name).decode()))]

    with zipfile.ZipFile(args.bundle) as archive:
        rows = decode(archive, "candles.csv")
        daily = decode(archive, "daily-candles.csv")
        bitcoin = decode(archive, "bitcoin-daily-candles.csv") if "bitcoin-daily-candles.csv" in archive.namelist() else None
        embedded = json.loads(archive.read("learning-result.json"))
    assert dataset_digest(rows) == embedded["data_sha256"]
    assert dataset_digest(daily) == embedded["daily_data"]["data_sha256"]
    if args.last_candles is not None:
        if not 3000 <= args.last_candles <= len(rows):
            parser.error("--last-candles must select 3000 or more existing candles")
        rows = rows[-args.last_candles:]
    settings = {**DEFAULTS, **embedded["cost_signature"]}
    boundary = rows[-1]["ts"]+INTERVAL_MS[embedded["interval"]]
    started = time.perf_counter()
    cpu_started = time.process_time()
    result = learn_history(rows, embedded["symbol"], settings,
        daily_rows=daily, bitcoin_rows=bitcoin, reviewed_through_ts=boundary,
        exit_comparison=not args.primary_only, selection_comparison=not args.primary_only)
    elapsed = time.perf_counter()-started
    cpu_elapsed = time.process_time()-cpu_started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    assert not result["validated"], "Already-reviewed prices cannot qualify this revision"
    record = {
        "source_code_sha256":source.hexdigest(), "python":platform.python_version(),
        "bundle_sha256":hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        "data_sha256":result["data_sha256"], "candles":len(rows), "symbol":result["symbol"],
        "interval":result["interval"], "cost_signature":result["cost_signature"],
        "primary_only":args.primary_only, "last_candles":args.last_candles,
        "report_sha256_without_created_at":digest_report(result),
        "model_sha256":hashlib.sha256(json.dumps(result["model"],sort_keys=True).encode()).hexdigest(),
        "runtime_seconds":elapsed, "cpu_seconds":cpu_elapsed, "peak_replay_rss_mib":rss,
        "observations":result["model"]["observations"], "historical_examples":result["historical_examples"],
        "net_pnl":result["holdout"]["net_pnl"], "account_trades":result["holdout"]["trades"],
        "higher_cost_net_pnl":result["holdout_stressed"]["net_pnl"], "qualified":result["validated"],
        "scope":"Local CPU replay only; excludes candle downloading, output serialization and hosted load. "
            "Exact report digest includes all forecasts, model weights, fees, account paths, diagnostic comparisons and qualification decisions. "
            "Creation time is the only excluded field. Recorded data is reviewed research, not fresh performance evidence."}
    if args.compare:
        previous = json.loads(args.compare.read_text())
        for key in ("bundle_sha256", "data_sha256", "cost_signature", "candles", "primary_only", "last_candles",
                    "report_sha256_without_created_at", "model_sha256"):
            if record[key] != previous[key]:
                raise AssertionError("Before/after comparison differs: "+key)
        record["comparison"] = {"identical_report_except_created_at":True,
            "baseline_source_code_sha256":previous["source_code_sha256"],
            "baseline_seconds":previous["runtime_seconds"],
            "time_reduction_pct":100*(1-elapsed/previous["runtime_seconds"]),
            "speed_multiple":previous["runtime_seconds"]/elapsed}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, allow_nan=False)+"\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
