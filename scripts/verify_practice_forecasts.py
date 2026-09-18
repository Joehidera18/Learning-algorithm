"""Independently verify stored practice entries/outcomes and their cost grouping.

Candidate practice does not depend on model choices, so execution can verify
entry identity, exit time, reward and cost eligibility without refitting or
changing any saved prediction. Supply the pinned --repo used by --record.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile

from compare_practice_tracks import entry_cost_lane


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','bundle','record','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.repo.resolve()))
    from lab.adaptive import AdaptivePolicy, action_key
    from lab.data import INTERVAL_MS
    from lab.evaluation import dataset_digest
    from lab.execution import simulate
    from lab.learning_data import prepare_learning_history
    from lab.learning_research import build_learning_features
    record=json.loads(args.record.read_text()); report=record['result']
    source=hashlib.sha256()
    for p in sorted((args.repo/'lab').glob('*.py')):
        source.update(p.name.encode()+b'\0'+p.read_bytes())
    assert source.hexdigest()==record['source_code_sha256']
    assert hashlib.sha256(args.bundle.read_bytes()).hexdigest()==record['bundle_sha256']
    with zipfile.ZipFile(args.bundle) as z:
        def read(name):
            return [{k:int(v) if k in ('ts','trades') else float(v) for k,v in r.items()}
                    for r in csv.DictReader(io.StringIO(z.read(name).decode()))]
        rows,daily=read('candles.csv'),read('daily-candles.csv')
    assert dataset_digest(rows)==report['data_sha256']
    assert dataset_digest(daily)==report['daily_data']['data_sha256']
    rows,_,coverage=prepare_learning_history(rows,report['interval'])
    features=build_learning_features(rows,report['interval'],coverage['segments'],daily_rows=daily)
    step=INTERVAL_MS[report['interval']]; settings=report['cost_signature']
    lanes=('eligible','cost_blocked') if report['learning_report_version']>=14 else ('all',)
    expected, actual = record['primary_practice_forecasts'], {}
    params=AdaptivePolicy(max_notional_fraction=settings['max_notional_fraction']).candidates
    for p in params:
        for lane in lanes:
            _,trades=simulate(rows,features,int(len(rows)*.8),len(rows),500,
                settings['risk_per_trade'],settings['fee_rate'],settings['slippage_rate']+.0005,p,
                training_examples=True,bar_interval_ms=step,
                **({'practice_cost_mode':lane} if lane!='all' else {}))
            for t in trades:
                if t['reason']=='END': continue
                key=action_key(p)+'|'+str(t['signal_ts']+step)
                assert key not in actual
                actual[key]=t
        print(p['family'],flush=True)
    assert set(expected)==set(actual), 'Practice entries differ from pinned execution'
    changes=0
    for key,t in actual.items():
        saved=expected[key]
        assert saved['available_ts']==t['exit_ts']+step
        assert math.isclose(saved['actual_r'],t['r_multiple'],abs_tol=1e-12)
        lane=entry_cost_lane(t)
        changes+=int(saved['cost_lane']!=lane)
        saved['cost_lane']=lane
    record['entry_outcome_verification']={'matched_entries':len(actual),'corrected_cost_groups':changes,
        'source_code_sha256':source.hexdigest(),
        'scope':'Entry identities, exit availability, actual rewards and cost groups verified by a separate '
                'candidate execution replay. Saved forecasts and all account/model results are unchanged.'}
    # Pair comparisons must be recomputed against the separately verified baseline.
    for k in ('common_entry_forecast_errors','shared_practice_entries','before_only_practice_entries','after_only_practice_entries'):
        record.get('comparison',{}).pop(k,None)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print(record['entry_outcome_verification'],flush=True)


if __name__=='__main__': main()
