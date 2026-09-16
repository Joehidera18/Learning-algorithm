"""Fixed same-candle model comparison. No downloads, orders or parameter search.

Run once with --repo pointing to the V11.4 source to create a baseline result.
Run with V11.5 and --baseline pointing to that JSON to assert the approved
model's predictions and account outcomes remain unchanged while studying exits.
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
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--summary',type=Path)
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
    boundary=next(s['replay']['test_end_ts'] for s in reviewed['results'] if s['symbol']==embedded['symbol'])
    code=hashlib.sha256()
    for path in sorted((args.repo/'lab').glob('*.py')):
        code.update(path.name.encode()+b'\0'+path.read_bytes())
    started=time.monotonic()
    result=learn_history(rows,embedded['symbol'],{**DEFAULTS,**embedded['cost_signature']},
        daily_rows=daily,reviewed_through_ts=boundary,
        progress=lambda **s:print(s.get('message',''),flush=True))
    record={'bundle_sha256':hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        'reviewed_report_sha256':hashlib.sha256(args.reviewed_report.read_bytes()).hexdigest(),
        'source_code_sha256':code.hexdigest(),'runtime_seconds':round(time.monotonic()-started,3),
        'result':result}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    comparison={}
    if args.baseline:
        previous=json.loads(args.baseline.read_text())
        assert previous['bundle_sha256']==record['bundle_sha256']
        assert previous['reviewed_report_sha256']==record['reviewed_report_sha256']
        base=previous['result']
        fields=('historical_examples','data_sha256','daily_data','cost_signature','training_diagnostics',
            'folds','holdout','holdout_stressed','holdout_trades','account_feedback_comparison',
            'outcome_memory_comparison','trade_reviews','evaluation','validated','rejection_reasons')
        mismatches=[k for k in fields if base[k]!=result[k]]
        old_model={k:v for k,v in base['model'].items() if k not in ('version','exit_policy')}
        new_model={k:v for k,v in result['model'].items() if k not in ('version','exit_policy')}
        comparison={'baseline_engine':base['engine_version'],'primary_field_mismatches':mismatches,
                    'primary_model_weights_and_observations_unchanged':old_model==new_model}
        assert not mismatches, mismatches
        assert old_model==new_model
    experiment=result.get('exit_policy_comparison')
    summary={**{k:v for k,v in record.items() if k!='result'}, **comparison,
        'symbol':result['symbol'],'engine_version':result['engine_version'],
        'data_sha256':result['data_sha256'],'daily_data_sha256':result['daily_data']['data_sha256'],
        'primary':{k:result[k] for k in ('historical_examples','holdout','holdout_stressed',
                                       'validated','evaluation','holdout_trades')},
        'exit_experiment':experiment}
    if args.summary:
        args.summary.parent.mkdir(parents=True,exist_ok=True)
        args.summary.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'symbol':result['symbol'],'primary_trades':result['holdout']['trades'],
        'primary_net':result['holdout']['net_pnl'],
        'alternative_trades':experiment['holdout']['trades'] if experiment else None,
        'alternative_net':experiment['holdout']['net_pnl'] if experiment else None,
        'alternative_stressed_net':experiment['holdout_stressed']['net_pnl'] if experiment else None,
        'alternative_examples':experiment['historical_examples'] if experiment else None,
        **comparison},indent=2),flush=True)


if __name__=='__main__':main()
