"""Fixed before/after replay on one supplied bundle; no search or winner selection.

Run once with --repo pointing to pinned V11.8, then with the revised source and
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


def entry_cost_lane(trade):
    # Exported public feature dictionaries omit private _close/_atr. Use the
    # saved signal-time economics instead, then the actual fill rejection.
    # The fixed .5 cost-R / 1.5 net-RR thresholds lie inside these feature caps.
    v, p = trade['training_vector'], trade['decision_params']
    return ('cost_blocked' if v[16]*2 > p['max_cost_r'] or v[17]*3 < p['min_net_rr']
            or trade.get('training_cost_override') else 'eligible')


def compare_forecasts(before, after):
    from math import sqrt, isclose
    paired = {}
    shared = set(before) & set(after)
    for key in sorted(shared):
        a,b = before[key],after[key]
        assert a['available_ts']==b['available_ts'] and isclose(a['actual_r'],b['actual_r'],abs_tol=1e-12)
        assert a['cost_lane']==b['cost_lane']
        if not (a['ready'] and b['ready']): continue
        values=paired.setdefault(b['cost_lane'],{'samples':0,'before_squared_error':0.,'after_squared_error':0.})
        values['samples'] += 1
        values['before_squared_error'] += (a['predicted_r']-a['actual_r'])**2
        values['after_squared_error'] += (b['predicted_r']-b['actual_r'])**2
    for v in paired.values():
        v['before_rmse_r']=sqrt(v['before_squared_error']/v['samples'])
        v['after_rmse_r']=sqrt(v['after_squared_error']/v['samples'])
    return {'common_entry_forecast_errors':paired,'shared_practice_entries':len(shared),
        'before_only_practice_entries':len(set(before)-shared),
        'after_only_practice_entries':len(set(after)-shared)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--reviewed-report',type=Path,required=True)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--out',type=Path,required=True)
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
    # Capture only the primary final-period practice forecasts. Matching entries
    # permit an error comparison even though separate tracks change the dataset.
    # This observer never changes a forecast, reward, policy or entry choice.
    from lab import learning_research, shadow_learning
    from lab.adaptive import action_key
    original_feedback = learning_research.HistoricalFeedback
    original_detail = shadow_learning.trade_feedback
    primary, captured = {}, False
    def detail(trade):
        value = original_detail(trade)
        value['_audit_cost_lane'] = entry_cost_lane(trade)
        return value
    shadow_learning.trade_feedback = detail
    class CaptureFeedback(original_feedback):
        def __init__(self, data, features, start, end, settings, policy, step, cancelled=None):
            nonlocal captured
            super().__init__(data,features,start,end,settings,policy,step,cancelled)
            if (not captured and start == int(len(data)*.8) and end == len(data)
                    and policy.exit_policy == 'fixed' and policy.recent_return_veto
                    and policy.regime_adaptation and policy.cost_filter and policy.failure_adaptation
                    and policy.fee_rate == embedded['cost_signature']['fee_rate']):
                captured = True
                observe = policy.observe
                def recorded(params,vector,reward,available_ts,outcome=None):
                    forecast=(outcome or {}).get('entry_forecast')
                    if forecast:
                        key=action_key(params)+'|'+str(forecast['signal_close_ts'])
                        if key in primary: raise ValueError('Duplicate primary practice forecast')
                        primary[key]={'predicted_r':forecast['estimated_net_r'],'actual_r':reward,
                            'ready':forecast['ready'],'available_ts':available_ts,
                            'cost_lane':outcome['_audit_cost_lane']}
                    return observe(params,vector,reward,available_ts,outcome=outcome)
                policy.observe = recorded
    learning_research.HistoricalFeedback = CaptureFeedback
    source = hashlib.sha256()
    for path in sorted((args.repo/'lab').glob('*.py')):
        source.update(path.name.encode()+b'\0'+path.read_bytes())
    started = time.monotonic()
    result = learn_history(rows,embedded['symbol'],{**DEFAULTS,**embedded['cost_signature']},
        daily_rows=daily,reviewed_through_ts=boundary,
        progress=lambda **s:print(s.get('message',''),flush=True))
    assert result['evaluation']['reviewed_through_ts'] == boundary
    record = {'bundle_sha256':hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        'primary_practice_forecasts':primary,
        'reviewed_report_sha256':hashlib.sha256(args.reviewed_report.read_bytes()).hexdigest(),
        'source_code_sha256':source.hexdigest(), 'runtime_seconds':time.monotonic()-started,
        'result':result}
    if args.baseline:
        previous = json.loads(args.baseline.read_text())
        assert previous['result']['engine_version']=='market-structure-v11.8-calibration'
        for key in ('bundle_sha256','reviewed_report_sha256'):
            assert previous[key] == record[key], key
        for key in ('data_sha256','daily_data','cost_signature','holdout_start_ts','candidate_count'):
            assert previous['result'][key] == result[key], key
        from lab.exit_research import difference
        record['comparison'] = {
            'baseline_source_code_sha256':previous['source_code_sha256'],
            'primary_net_difference':difference(result['holdout'],previous['result']['holdout']),
            'stress_net_difference':difference(result['holdout_stressed'],previous['result']['holdout_stressed']),
            **compare_forecasts(previous['primary_practice_forecasts'],primary),
            'selection_uses_comparison':False, 'qualification_uses_comparison':False}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'symbol':result['symbol'],'primary':result['holdout']['net_pnl'],
        'trades':result['holdout']['trades'],'stress':result['holdout_stressed']['net_pnl'],
        'conditional':result.get('selection_policy_comparison',{}).get('holdout',{}).get('net_pnl'),
        'qualified':result['validated'],'seconds':record['runtime_seconds']},indent=2),flush=True)


if __name__=='__main__': main()
