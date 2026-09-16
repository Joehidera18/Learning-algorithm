"""Fixed before/after replay on one supplied bundle; no search or winner selection.

Run once with --repo pointing to pinned V11.7, then with the revised source and
--baseline pointing to that record. Both runs must use the same reviewed report.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--reviewed-report',type=Path,required=True)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--experimental-correction',action='store_true',
                        help='Study the disabled correction on V11.8; cannot qualify for trading')
    args = parser.parse_args()
    sys.path.insert(0,str(args.repo.resolve()))
    from lab.continuous import DEFAULTS
    from lab.evaluation import dataset_digest
    from lab.learning_research import learn_history
    with zipfile.ZipFile(args.bundle) as z:
        def read(name):
            return [{k:int(v) if k in ('ts','trades') else float(v) for k,v in row.items()}
                    for row in csv.DictReader(io.StringIO(z.read(name).decode()))]
        rows, daily = read('candles.csv'), read('daily-candles.csv')
        embedded = json.loads(z.read('learning-result.json'))
    assert dataset_digest(rows) == embedded['data_sha256']
    assert dataset_digest(daily) == embedded['daily_data']['data_sha256']
    reviewed = json.loads(args.reviewed_report.read_text())
    boundary = next(d['replay']['test_end_ts'] for d in reviewed['results'] if d['symbol']==embedded['symbol'])
    source = hashlib.sha256()
    for path in sorted((args.repo/'lab').glob('*.py')):
        source.update(path.name.encode()+b'\0'+path.read_bytes())
    started = time.monotonic()
    result = learn_history(rows,embedded['symbol'],{**DEFAULTS,**embedded['cost_signature']},
        daily_rows=daily,reviewed_through_ts=boundary,
        **({'forecast_correction':True} if args.experimental_correction else {}),
        progress=lambda **s:print(s.get('message',''),flush=True))
    assert result['evaluation']['reviewed_through_ts'] == boundary
    record = {'bundle_sha256':hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        'experimental_correction':args.experimental_correction,
        'reviewed_report_sha256':hashlib.sha256(args.reviewed_report.read_bytes()).hexdigest(),
        'source_code_sha256':source.hexdigest(), 'runtime_seconds':time.monotonic()-started,
        'result':result}
    if args.baseline:
        previous = json.loads(args.baseline.read_text())
        assert previous['result']['engine_version']=='market-structure-v11.7-entry-audit'
        for key in ('bundle_sha256','reviewed_report_sha256'):
            assert previous[key] == record[key], key
        for key in ('data_sha256','daily_data','cost_signature','historical_examples',
                    'training_diagnostics','holdout_start_ts','training_label_end_ts'):
            assert previous['result'][key] == result[key], key
        from lab.exit_research import difference
        record['comparison'] = {
            'baseline_source_code_sha256':previous['source_code_sha256'],
            'primary_net_difference':difference(result['holdout'],previous['result']['holdout']),
            'stress_net_difference':difference(result['holdout_stressed'],previous['result']['holdout_stressed']),
            'selection_uses_comparison':False, 'qualification_uses_comparison':False}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'symbol':result['symbol'],'primary':result['holdout']['net_pnl'],
        'trades':result['holdout']['trades'],'stress':result['holdout_stressed']['net_pnl'],
        'conditional':result.get('selection_policy_comparison',{}).get('holdout',{}).get('net_pnl'),
        'qualified':result['validated'],'seconds':record['runtime_seconds']},indent=2),flush=True)


if __name__=='__main__': main()
