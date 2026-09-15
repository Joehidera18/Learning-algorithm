"""One fixed V11.4 replay of a supplied candle bundle and prior report.

No network, orders, parameter search or profit-based choice of a data source.
"""
import argparse
import csv
import hashlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lab.continuous import DEFAULTS
from lab.evaluation import dataset_digest
from lab.learning_research import learn_history


def candles(blob):
    return [{k:int(v) if k in ("ts","trades") else float(v) for k,v in r.items()}
            for r in csv.DictReader(io.StringIO(blob.decode()))]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle",type=Path,required=True)
    parser.add_argument("--previous-report",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--full-result",type=Path)
    args=parser.parse_args()
    with zipfile.ZipFile(args.bundle) as archive:
        rows=candles(archive.read("candles.csv"))
        daily=candles(archive.read("daily-candles.csv"))
        embedded=json.loads(archive.read("learning-result.json"))
    previous=json.loads(args.previous_report.read_text())
    previous=next(r for r in previous["results"] if r["symbol"]==embedded["symbol"] and r["interval"]==embedded["interval"])
    if embedded!=previous or dataset_digest(rows)!=previous["data_sha256"] or dataset_digest(daily)!=previous["daily_data"]["data_sha256"]:
        raise ValueError("The supplied bundle and report must identify the same exact candles and result")
    source_hash=hashlib.sha256()
    for path in sorted((ROOT/"lab").glob("*.py")):
        source_hash.update(path.name.encode()+b"\0"+path.read_bytes())
    clock=time.monotonic()
    result=learn_history(rows,embedded["symbol"],dict(DEFAULTS,**previous["cost_signature"]),
        daily_rows=daily,reviewed_through_ts=previous["replay"]["test_end_ts"],
        progress=lambda **s:print(s.get("message",""),flush=True))
    if args.full_result:
        args.full_result.parent.mkdir(parents=True,exist_ok=True)
        args.full_result.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    fields=("engine_version","policy_version","learning_report_version","historical_examples","candidate_count",
        "profitable_folds","data_sha256","daily_data","holdout","holdout_stressed","holdout_trades",
        "account_feedback_comparison","outcome_memory_comparison","failure_learning","evaluation",
        "validated","rejection_reasons")
    comparison={"method":"One fixed revision, unchanged candles, fees and account risk. Report 17 was already reviewed. No parameter search.",
        "source_bundle_sha256":hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        "source_report_sha256":hashlib.sha256(args.previous_report.read_bytes()).hexdigest(),
        "source_code_sha256":source_hash.hexdigest(),"runtime_seconds":round(time.monotonic()-clock,2),
        "previous":{k:previous[k] for k in fields},"revised":{k:result[k] for k in fields}}
    comparison["revised"]["training_diagnostics"]=result["training_diagnostics"]["totals"]
    comparison["revised"]["trade_review_counts"]={name:{k:v for k,v in summary.items() if k!="cases"}
        for name,summary in result["trade_reviews"].items() if name in ("development","selected")}
    comparison["revised"]["model_sha256"]=hashlib.sha256(json.dumps(result["model"],sort_keys=True).encode()).hexdigest()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(comparison,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"examples":result["historical_examples"],"previous_examples":previous["historical_examples"],
        "loss_pause_overrides":result["training_diagnostics"]["totals"]["loss_pause_overrides"],
        "development_outcomes":result["trade_reviews"]["development"]["outcomes"],
        "selected_outcomes":result["trade_reviews"]["selected"]["outcomes"],
        "trades":result["holdout"]["trades"],"net_pnl":result["holdout"]["net_pnl"],
        "stressed_net_pnl":result["holdout_stressed"]["net_pnl"],"validated":result["validated"]},indent=2),flush=True)


if __name__=="__main__":main()
