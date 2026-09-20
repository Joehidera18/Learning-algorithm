"""Check that newly collected events cannot alter already reviewed price history.

Use an unchanged archive whose first observation follows the candle range. This
is a causality regression, not evidence of event-driven profitability.
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--events',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True,help='Earlier compare_eligible_learning.py result on these prices')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    from lab.continuous import DEFAULTS
    from lab.evaluation import dataset_digest
    from lab.event_context import validate_snapshot, digest
    from lab.learning_research import learn_history
    old=json.loads(args.baseline.read_text())['result']
    def decode(archive,name):
        return [{k:int(v) if k in ('ts','trades') else float(v) for k,v in row.items()}
            for row in csv.DictReader(io.StringIO(archive.read(name).decode()))]
    with zipfile.ZipFile(args.bundle) as archive:
        rows=decode(archive,'candles.csv');daily=decode(archive,'daily-candles.csv')
        bitcoin=decode(archive,'bitcoin-daily-candles.csv') if 'bitcoin-daily-candles.csv' in archive.namelist() else None
    events=validate_snapshot(json.loads(args.events.read_text()))
    end=old['replay']['test_end_ts']
    assert events['polls'] and min(p['ts'] for p in events['polls'])>end
    assert events['events'] and min(e['observed_ts'] for e in events['events'])>end
    assert dataset_digest(rows)==old['data_sha256']
    assert dataset_digest(daily)==old['daily_data']['data_sha256']
    began=time.perf_counter()
    result=learn_history(rows,old['symbol'],{**DEFAULTS,**old['cost_signature']},daily_rows=daily,
        bitcoin_rows=bitcoin,event_snapshot=events,reviewed_through_ts=old['evaluation']['reviewed_through_ts'],
        exit_comparison=False,selection_comparison=False)
    elapsed=time.perf_counter()-began
    assert result['event_data']['covered_candles']==0
    assert not result['validated']
    assert 'event_comparison' not in result  # No meaningful event experiment without coverage.
    assert result['model']['observations']==old['model']['observations']
    metrics=('trades','net_pnl','gross_pnl','fees_paid','win_rate','max_drawdown_pct')
    comparisons={}
    for key in ('holdout','holdout_stressed','frozen_holdout'):
        checked=[m for m in metrics if m in old[key]]
        for m in checked:assert result[key][m]==old[key][m],(key,m)
        comparisons[key]={m:result[key][m] for m in checked}
    def without_scope(value):
        if isinstance(value,dict):return {k:without_scope(v) for k,v in value.items() if k != 'scope'}
        if isinstance(value,list):return [without_scope(v) for v in value]
        return value
    # The saved earlier run predates an explanatory scope-text correction.
    # Compare all forecast data; only descriptive scope strings are excluded.
    assert without_scope(result['prediction_audit'])==without_scope(old['prediction_audit'])
    assert result['forecast_calibration']==old['forecast_calibration']
    for key,model in result['model']['models'].items():
        assert model['weights'][-7:]==[0.]*7
        assert model['weights'][:-7]==old['model']['models'][key]['weights']
        for group in ('eligible_model',):
            if group in model:
                assert model[group]['weights'][-7:]==[0.]*7
                assert model[group]['weights'][:-7]==old['model']['models'][key][group]['weights']
    source=hashlib.sha256()
    for path in sorted((root/'lab').glob('*.py')):
        source.update(path.name.encode()+b'\0'+path.read_bytes())
    record={'source_code_sha256':source.hexdigest(),
        'baseline_sha256':hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        'bundle_sha256':hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        'events_sha256':digest(events),'data_sha256':result['data_sha256'],
        'symbol':result['symbol'],'candles':len(rows),'event_versions':len(events['events']),
        'first_event_observation_ts':min(e['observed_ts'] for e in events['events']),
        'candle_test_end_ts':end,'event_data':result['event_data'],'comparisons':comparisons,
        'matching_entry_forecast_audits_except_scope_text':True,'matching_calibration':True,
        'matching_original_model_weights':True,'new_event_weights_zero':True,
        'observations':result['model']['observations'],'qualified':result['validated'],
        'runtime_seconds':elapsed,
        'scope':'Previously reviewed market prices. Current news has zero historical coverage. '
                'Matching results test causality; they do not establish profit or predictive benefit from events.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print(json.dumps(record,indent=2),flush=True)


if __name__=='__main__':main()
