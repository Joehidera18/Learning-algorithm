"""Declared V11.5/V11.6 comparison on identical supplied snapshots, without tuning.

The baseline is a record produced by compare_exit_learning.py at pinned V11.5.
This comparison cannot choose a policy, change its risk, or qualify it.
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--reviewed-report',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--summary',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.repo.resolve()))
    from lab.continuous import DEFAULTS
    from lab.evaluation import dataset_digest
    from lab.learning_research import learn_history

    def candles(blob):
        return [{k:int(v) if k in ('ts','trades') else float(v) for k,v in r.items()}
                for r in csv.DictReader(io.StringIO(blob.decode()))]
    with zipfile.ZipFile(args.bundle) as z:
        rows=candles(z.read('candles.csv'));daily=candles(z.read('daily-candles.csv'))
        embedded=json.loads(z.read('learning-result.json'))
    assert dataset_digest(rows)==embedded['data_sha256']
    assert dataset_digest(daily)==embedded['daily_data']['data_sha256']
    reviewed=json.loads(args.reviewed_report.read_text())
    boundary=next(r['replay']['test_end_ts'] for r in reviewed['results'] if r['symbol']==embedded['symbol'])
    previous=json.loads(args.baseline.read_text())
    bundle_hash=hashlib.sha256(args.bundle.read_bytes()).hexdigest()
    reviewed_hash=hashlib.sha256(args.reviewed_report.read_bytes()).hexdigest()
    assert previous['bundle_sha256']==bundle_hash
    assert previous['reviewed_report_sha256']==reviewed_hash
    base=previous['result']
    assert base['engine_version']=='market-structure-v11.5-exit-study'
    code=hashlib.sha256()
    for path in sorted((args.repo/'lab').glob('*.py')):
        code.update(path.name.encode()+b'\0'+path.read_bytes())
    started=time.monotonic()
    result=learn_history(rows,embedded['symbol'],{**DEFAULTS,**embedded['cost_signature']},
        daily_rows=daily,reviewed_through_ts=boundary,
        progress=lambda **s:print(s.get('message',''),flush=True))
    # Entry rules and execution of independent training labels are unchanged.
    # Learned selection and resulting account paths are intentionally allowed to differ.
    for key in ('data_sha256','daily_data','cost_signature','historical_examples',
                'training_diagnostics','holdout_start_ts'):
        assert base[key]==result[key],key
    assert base['evaluation']['reviewed_through_ts']==result['evaluation']['reviewed_through_ts']
    assert result['evaluation']['reuses_reviewed_history']
    record={'bundle_sha256':bundle_hash,'reviewed_report_sha256':reviewed_hash,
        'source_code_sha256':code.hexdigest(),'runtime_seconds':round(time.monotonic()-started,3),
        'result':result}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')

    def reduced(r):
        return {k:r[k] for k in ('engine_version','policy_version','historical_examples',
            'holdout','holdout_stressed','holdout_trades','profitable_folds','validated',
            'rejection_reasons','evaluation','account_feedback_comparison','exit_policy_comparison')}
    def difference(left,right):
        return None if left is None or right is None else left-right
    summary={k:v for k,v in record.items() if k!='result'}
    summary.update(symbol=result['symbol'],baseline_source_code_sha256=previous['source_code_sha256'],
        data_sha256=result['data_sha256'],daily_data_sha256=result['daily_data']['data_sha256'],
        baseline=reduced(base),revised=reduced(result),
        net_pnl_difference=difference(result['holdout']['net_pnl'],base['holdout']['net_pnl']),
        stress_net_pnl_difference=difference(result['holdout_stressed']['net_pnl'],base['holdout_stressed']['net_pnl']),
        selection_uses_comparison=False,qualification_uses_comparison=False)
    args.summary.parent.mkdir(parents=True,exist_ok=True)
    args.summary.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'symbol':result['symbol'],'baseline_net':base['holdout']['net_pnl'],
        'revised_net':result['holdout']['net_pnl'],'revised_trades':result['holdout']['trades'],
        'stress_net':result['holdout_stressed']['net_pnl'],'validated':result['validated'],
        'runtime_seconds':record['runtime_seconds']},indent=2),flush=True)


if __name__=='__main__': main()
