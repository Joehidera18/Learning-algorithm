"""Replay fixed comparisons on verified saved archives; never fetch or trade.

Uses each archive's final available window, specified by calendar days before
looking at results. Binance USDT and Coinbase USD remain separate observations.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import resource
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.continuous import DEFAULTS
from lab.data import INTERVAL_MS
from lab.evaluation import dataset_digest
from lab.experiments import RECIPES, MAX_CANDLES, run_experiment, summary, account_report, assess_pair
from lab.study_plan import ACTIVE_INTERVALS


def file_digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def recorded_rows(path, interval, days):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if "timeframes" in manifest:
            frame = next((r for r in manifest["timeframes"] if r["interval"] == interval), None)
            if frame is None:
                raise ValueError("Timeframe is absent from this recorded archive")
            h = hashlib.sha256()
            with archive.open(frame["file"]) as handle:
                for block in iter(lambda: handle.read(1024*1024), b""):
                    h.update(block)
            if h.hexdigest() != frame["sha256"]:
                raise ValueError("Archive member checksum mismatch")
            step = INTERVAL_MS[interval]
            cutoff = manifest["end_ts_exclusive"]//step*step
            with archive.open(frame["file"]) as compressed:
                with io.TextIOWrapper(gzip.GzipFile(fileobj=compressed)) as handle:
                    rows = [{k:int(v) if k in ("ts","trades") else float(v) for k,v in row.items()}
                            for row in csv.DictReader(handle) if cutoff-days*86400000 <= int(row["ts"]) < cutoff]
            source = {"provider": manifest["venue"], "quote_currency": manifest["quote_currency"],
                      "archive_member_sha256": frame["sha256"], "archive_member": frame["file"]}
            symbol = manifest["pair"]
        else:
            if manifest["interval"] != interval:
                raise ValueError("Use the recorded learning bundle's original timeframe")
            with io.TextIOWrapper(archive.open("candles.csv")) as handle:
                rows = [{k:int(v) if k in ("ts","trades") else float(v) for k,v in row.items()} for row in csv.DictReader(handle)]
            if dataset_digest(rows) != manifest["data_sha256"]:
                raise ValueError("Recorded learning data checksum mismatch")
            cutoff = rows[-1]["ts"]+INTERVAL_MS[interval]
            rows = [r for r in rows if r["ts"] >= cutoff-days*86400000]
            source = {"provider": manifest["market_data"]["provider"], "quote_currency": "USD",
                      "original_dataset_sha256": manifest["data_sha256"], "archive_member": "candles.csv"}
            symbol = manifest["symbol"]
    expected = days*86400000//INTERVAL_MS[interval]
    source.update(archive_sha256=file_digest(path), requested_days=days, cutoff_ts=cutoff,
                  requested_candles=expected, observed_candles=len(rows), coverage_pct=100*len(rows)/expected,
                  synthetic_fallback=False, scope="Previously collected archive; historical development replay")
    if len(rows) > MAX_CANDLES:
        raise ValueError("Choose a shorter fixed window; this exceeds the bounded experiment capacity")
    return symbol, rows, source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--interval", choices=ACTIVE_INTERVALS, required=True)
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--include-vwap", action="store_true", help="Also replay the existing four-variant VWAP protocol on recorded 1m data")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("Choose a positive number of calendar days")
    if args.include_vwap and args.interval != "1m":
        parser.error("VWAP requires the original one-minute observations")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    symbol, rows, source = recorded_rows(args.archive, args.interval, args.days)
    reports = []
    started = time.monotonic()
    for recipe in RECIPES:
        print(f"{symbol} {args.interval}: {recipe} on {len(rows):,} recorded candles", flush=True)
        report = run_experiment(rows, symbol, args.interval, recipe, DEFAULTS, source)
        reports.append(report)
        print(json.dumps({"recipe":recipe, "comparisons":report["comparisons"]}), flush=True)
    if args.include_vwap:
        from lab.vwap_research import run_vwap_research
        original = run_vwap_research(rows, symbol, DEFAULTS, source)
        variants = []
        for v in original["results"]:
            windows = {}
            for name, w in v["windows"].items():
                windows[name] = {"start_ts":w["start_ts"],"end_ts":w["end_ts"], **{
                    scenario:account_report(w[scenario]["metrics"],w[scenario]["trades"])
                    for scenario in ("standard","higher_cost")}}
            variants.append({"id":v["variant"],"windows":windows})
        control = variants[0]["windows"]["later"]
        comparisons = []
        for variant in variants[1:]:
            later=variant["windows"]["later"]
            comparisons.append({"challenger":variant["id"],"control":"bands", **assess_pair(
                control["standard"],later["standard"],control["higher_cost"],later["higher_cost"])})
        display = {k:v for k,v in original.items() if k != "results"}
        display.update(recipe="vwap_adaptation",interval="1m",title="Reddit VWAP crypto adaptation",
            source_sha256=original["source_hash"], variants=variants, comparisons=comparisons,
            start_ts=rows[0]["ts"],end_ts=rows[-1]["ts"]+60000,
            later_start_ts=control["start_ts"],coverage={"downloaded_candles":len(rows)},
            evaluation_kind="historical_development")
        reports.append(display)
        args.out.with_suffix(".vwap.json").write_text(json.dumps(original,indent=2,allow_nan=False)+"\n")
        print(json.dumps({"recipe":"vwap_adaptation","comparisons":comparisons}),flush=True)
    result = {"note":"Fixed recipes on previously collected market candles, at the configured 0.4% fee per side. "
              "No tuning, synthetic candles, trading qualification or independent future observations.",
              "reports":reports,"runtime_seconds":time.monotonic()-started,
              "peak_rss_mib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    args.out.with_suffix(".summary.json").write_text(json.dumps({**result,"reports":[summary(r) for r in reports]}, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("reports","note")}), flush=True)


if __name__ == "__main__":
    main()
