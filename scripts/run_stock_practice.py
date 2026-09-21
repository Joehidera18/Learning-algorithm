#!/usr/bin/env python3
"""Download a stock snapshot or reproduce a saved one, then run bounded practice."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.equity_data import EquityData
from lab.equity_research import DEFAULT_COSTS, run_stock_practice
from lab.experiment_jobs import read_gzip, write_gzip
from lab.experiments import digest
from lab.forward_study import source_digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol",default="SPY")
    p.add_argument("--interval",default="1h")
    p.add_argument("--days",type=int,default=365)
    p.add_argument("--mode",choices=("day","swing"),default="swing")
    p.add_argument("--provider",choices=("yahoo","alpaca"),default="yahoo")
    p.add_argument("--feed",choices=("sip","iex"),default="sip")
    p.add_argument("--snapshot",type=Path,help="Existing gzip JSON input snapshot; skips downloading")
    p.add_argument("--output",type=Path,required=True,help="Result JSON path; snapshot is saved beside it")
    p.add_argument("--whole-shares",action="store_true")
    args=p.parse_args()
    snapshot=(read_gzip(args.snapshot) if args.snapshot else
              EquityData().history(args.symbol,args.interval,args.days,provider=args.provider,feed=args.feed))
    if snapshot.get("data_sha256",digest(snapshot["rows"])) != digest(snapshot["rows"]):
        raise ValueError("Snapshot integrity check failed")
    recorded=snapshot["market_data"]
    if recorded.get("symbol") != args.symbol or recorded.get("interval") != args.interval:
        raise ValueError("Snapshot symbol/timeframe does not match the requested stock practice")
    manifest={"symbol":args.symbol,"interval":args.interval,"mode":args.mode,"settings":DEFAULT_COSTS,
              "fractional_shares":not args.whole_shares,"source_sha256":source_digest()}
    result=run_stock_practice(snapshot,manifest)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({"manifest":manifest,"result":result},separators=(",",":"),allow_nan=False))
    snapshot["data_sha256"]=digest(snapshot["rows"])
    write_gzip(args.output.with_suffix(".snapshot.json.gz"),snapshot)
    print(json.dumps({"output":str(args.output),"examples":result["seed"]["resolved_examples"],
                      "comparisons":result["comparisons"]},indent=2))


if __name__=="__main__":
    main()
