"""Pinned primary-policy comparison on supplied prices; never search parameters.

Run with each source tree and the same bundle/reviewed report. Bitcoin context
is optional but its exact hash is recorded. Older sources cannot use the new
Bitcoin features. Missing benchmark prices must not be invented.
"""
import argparse
import csv
import hashlib
import inspect
import io
import json
from pathlib import Path
import resource
import sys
import time
import zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--reviewed-report',type=Path,required=True)
    parser.add_argument('--bitcoin-csv',type=Path)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--with-exit-study',action='store_true')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.repo.resolve()))
    from lab.continuous import DEFAULTS
    from lab.evaluation import dataset_digest
    from lab.learning_research import learn_history
    def read(raw):
        return [{k:int(v) if k in ('ts','trades') else float(v) for k,v in row.items()}
                for row in csv.DictReader(io.StringIO(raw))]
    with zipfile.ZipFile(args.bundle) as archive:
        rows=read(archive.read('candles.csv').decode())
        daily=read(archive.read('daily-candles.csv').decode())
        embedded=json.loads(archive.read('learning-result.json'))
        bitcoin=(read(archive.read('bitcoin-daily-candles.csv').decode())
                 if 'bitcoin-daily-candles.csv' in archive.namelist() else None)
    if args.bitcoin_csv:
        bitcoin=read(args.bitcoin_csv.read_text())
    assert dataset_digest(rows)==embedded['data_sha256']
    assert dataset_digest(daily)==embedded['daily_data']['data_sha256']
    reviewed=json.loads(args.reviewed_report.read_text())
    symbol=embedded['symbol']
    boundary=max([r.get('replay',{}).get('test_end_ts',0) for r in reviewed['results']
                  if r['symbol']==symbol]+[embedded['replay']['test_end_ts']])
    source=hashlib.sha256()
    for path in sorted((args.repo/'lab').glob('*.py')):
        source.update(path.name.encode()+b'\0'+path.read_bytes())
    kwargs=dict(daily_rows=daily,reviewed_through_ts=boundary,
                exit_comparison=args.with_exit_study,selection_comparison=False)
    if 'bitcoin_rows' in inspect.signature(learn_history).parameters:
        kwargs['bitcoin_rows']=bitcoin
    elif bitcoin is not None:
        raise ValueError('Use the same no-Bitcoin inputs for a primary learning-only baseline comparison')
    began=time.monotonic()
    report=learn_history(rows,symbol,{**DEFAULTS,**embedded['cost_signature']},
        progress=lambda **s:print(s.get('message',''),flush=True),**kwargs)
    assert not report['validated'], 'Reviewed prices cannot independently qualify this revision'
    record={'bundle_sha256':hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        'reviewed_report_sha256':hashlib.sha256(args.reviewed_report.read_bytes()).hexdigest(),
        'source_code_sha256':source.hexdigest(),
        'bitcoin_data_sha256':dataset_digest(bitcoin) if bitcoin is not None else None,
        'runtime_seconds':time.monotonic()-began,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        'result':report,'scope':'Paired historical research on reviewed prices. No tuning or model promotion. Missing Bitcoin context stays unavailable.'}
    if args.baseline:
        previous=json.loads(args.baseline.read_text())
        for key in ('bundle_sha256','reviewed_report_sha256','bitcoin_data_sha256'):
            assert record[key]==previous[key],key
        old=previous['result']
        for key in ('data_sha256','daily_data','cost_signature','historical_examples','training_diagnostics','holdout_start_ts','training_label_end_ts'):
            assert report[key]==old[key],key
        record['comparison']={'baseline_source_code_sha256':previous['source_code_sha256'],
            'ordinary_net_difference':report['holdout']['net_pnl']-old['holdout']['net_pnl'],
            'higher_cost_net_difference':report['holdout_stressed']['net_pnl']-old['holdout_stressed']['net_pnl'],
            'old_selected_forecasts':old['prediction_audit']['selected'],
            'new_selected_forecasts':report['prediction_audit']['selected'],
            'selection_uses_comparison':False,'qualification_uses_comparison':False}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'symbol':symbol,'interval':report['interval'],'net':report['holdout']['net_pnl'],
        'trades':report['holdout']['trades'],'higher_cost_net':report['holdout_stressed']['net_pnl'],
        'qualified':report['validated'],'seconds':record['runtime_seconds']},indent=2),flush=True)


if __name__=='__main__':main()
