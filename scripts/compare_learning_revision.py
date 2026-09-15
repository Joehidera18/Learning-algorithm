"""Reproduce the declared DOT 15m/1h research checks without network or orders.

Use the supplied candle bundle and report-16 export. A report-only summary is
not enough: the canonical 15m data hash must match. Full outputs are optional.
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lab.continuous import DEFAULTS
from lab.data_repair import aggregate_complete
from lab.evaluation import dataset_digest
from lab.learning_research import learn_history


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle",type=Path,required=True)
    parser.add_argument("--previous-report",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--full-results",type=Path)
    args=parser.parse_args()
    with zipfile.ZipFile(args.bundle) as archive:
        raw=list(csv.DictReader(io.StringIO(archive.read("candles.csv").decode())))
    rows=[{k:(int(v) if k in ("ts","trades") else float(v)) for k,v in r.items()} for r in raw]
    previous=json.loads(args.previous_report.read_text())
    previous=next(r for r in previous["results"] if r["symbol"]=="DOT-USD" and r["interval"]=="15m")
    if dataset_digest(rows)!=previous["data_sha256"]:
        raise ValueError("Input candles do not reproduce the previous DOT report's data hash")
    step=900000; hour=3600000
    start=(rows[0]["ts"]+hour-1)//hour*hour
    end=(rows[-1]["ts"]+step)//hour*hour
    hourly=aggregate_complete(rows,step,hour,start,end)
    source_hash=hashlib.sha256()
    for path in sorted((ROOT/"lab").glob("*.py")):
        source_hash.update(path.name.encode()+b"\0"+path.read_bytes())
    output={"source_bundle_sha256":hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        "source_report_sha256":hashlib.sha256(args.previous_report.read_bytes()).hexdigest(),
        "source_code_sha256":source_hash.hexdigest(),
        "hypotheses":"One fixed outcome-memory policy on 15m and complete 1h aggregates, same 22 candidates. No parameter search or selection from these results.",
        "data_acquisition":"No external candles obtained for this comparison. 1h candles contain all four actual 15m observations. Partial hours omitted; no interpolation or daily-price imputation.",
        "previous_15m":{k:previous.get(k) for k in ("engine_version","policy_version","historical_examples",
            "profitable_folds","data_sha256","validated")}, "results":[]}
    for field in ("holdout","holdout_stressed"):
        output["previous_15m"][field]={k:previous[field].get(k) for k in ("net_pnl","trades","complete")}
    for interval,data in (("15m",rows),("1h",hourly)):
        clock=time.monotonic()
        result=learn_history(data,"DOT-USD",dict(DEFAULTS,decision_interval=interval),
            reviewed_through_ts=rows[-1]["ts"]+step,
            progress=lambda **s:print(f"{interval}: {s.get('message','')}",flush=True))
        if args.full_results:
            args.full_results.mkdir(parents=True,exist_ok=True)
            (args.full_results/f"dot-v11.3-{interval}-full.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
        fields=("engine_version","policy_version","learning_report_version","interval","data_sha256",
            "data_quality","daily_data","historical_examples","candidate_count","profitable_folds",
            "holdout","holdout_stressed","holdout_trades","account_feedback_comparison",
            "outcome_memory_comparison","failure_learning","performance_attribution","costs",
            "cost_signature","holdout_expectancy_interval","evaluation","validated","rejection_reasons")
        summary={k:result[k] for k in fields}
        summary["folds"]=[{k:f[k] for k in ("fold","test_start_ts","test_end_ts","metrics")} for f in result["folds"]]
        summary["runtime_seconds"]=round(time.monotonic()-clock,2)
        summary["model_sha256"]=hashlib.sha256(json.dumps(result["model"],sort_keys=True,allow_nan=False).encode()).hexdigest()
        summary["development_failure_learning"]={"examples":result["historical_examples"]}
        output["results"].append(summary)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
        print(f"{interval}: {result['historical_examples']} examples; {result['holdout']['trades']} trades; net ${result['holdout']['net_pnl']}; qualified={result['validated']}",flush=True)
    return 0


if __name__=="__main__": raise SystemExit(main())
