"""Check the prior XRP replay's finances after adding evaluation/reporting tools.

The prices are previously reviewed. This does not measure a new trading edge.
"""
import argparse
import csv
import io
import json
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lab.continuous import DEFAULTS
from lab.event_store import EventStore
from lab.evaluation import dataset_digest
from lab.forward_study import source_digest
from lab.learning_research import learn_history


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    expected=json.loads((ROOT/'research_baselines/observed-news-replay.json').read_text())
    previous=json.loads((ROOT/'research_baselines/eligible-context-comparison.json').read_text())
    study=next(s for s in previous['studies'] if s['symbol']=='XRP-USD')
    def read(archive,name):
        return [{k:int(v) if k in ('ts','trades') else float(v) for k,v in r.items()}
            for r in csv.DictReader(io.StringIO(archive.read(name).decode()))]
    with zipfile.ZipFile(args.bundle) as z:
        rows=read(z,'candles.csv');daily=read(z,'daily-candles.csv')
    assert dataset_digest(rows)==expected['data_sha256']
    began=time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        snapshot=EventStore(Path(directory)/'events.db').snapshot()
        result=learn_history(rows,'XRP-USD',{**DEFAULTS,**study['cost_signature']},daily_rows=daily,
            event_snapshot=snapshot,exit_comparison=False,selection_comparison=False,event_comparison=False)
    checks={}
    for label,metrics in expected['comparisons'].items():
        checked={k:result[label][k] for k in metrics}
        assert checked==metrics,(label,checked,metrics)
        checks[label]=checked
    assert not result['validated']
    assert result['model']['observations']==expected['observations']
    for t in result['holdout_trades']:
        assert abs(t['gross_pnl']-t['fees_paid']-t['pnl'])<1e-7
    record={'source_code_sha256':source_digest(),'symbol':'XRP-USD','candles':len(rows),
        'data_sha256':dataset_digest(rows),'prior_record':'observed-news-replay.json',
        'matching_prior_account_metrics':True,'comparisons':checks,'qualified':result['validated'],
        'observations':result['model']['observations'],'runtime_seconds':time.perf_counter()-began,
        'scope':'Previously reviewed historical prices. This verifies unchanged account calculations; no new profitability or forward-performance claim.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print(json.dumps(record,indent=2))


if __name__=='__main__':main()
