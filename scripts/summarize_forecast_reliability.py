"""Archive every declared comparison and summarize it without choosing a winner.

Inputs are full outputs of compare_eligible_learning.py. The compressed records
retain models, diagnostics, forecasts and account paths for review. No result
from this script installs a model or constitutes independent validation.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


STUDIES = (
    ('xrp', 'XRP-USD_15m_learning-data 2.zip'),
    ('avax', 'AVAX-USD_15m_learning-data.zip'),
    ('dot', 'DOT-USD_15m_learning-data 4.zip'),
    ('xrp6h', 'XRP-USD_6h_learning-data.zip'))
METRICS = ('complete', 'trades', 'net_pnl', 'ending_balance', 'win_rate',
           'profit_factor', 'expectancy_r', 'max_drawdown_pct', 'gross_pnl', 'fees_paid')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    archive_dir=args.out.parent/'forecast-reliability-records'
    archive_dir.mkdir(exist_ok=True)
    summary={
        'design':'FORECAST_RELIABILITY_RESEARCH.md; one declared revision, no parameter search',
        'baseline_git_commit':'24e21c77cacd4dba28885a55e0a216eb857c3e67',
        'baseline_git_tree':'a27acc3ceae94b5ac60c808c2f296817d892c429',
        'scope':'Separate $500 simulations on previously reviewed prices. No portfolio total, '
            'model promotion or proof of profitability. Counts may overlap.',
        'selection_uses_comparison':False,'qualification_uses_comparison':False,
        'studies':[]}
    for label,bundle in STUDIES:
        variants={}
        for name in ('baseline','revised'):
            raw=(args.records/f'{label}-{name}.json').read_bytes()
            record=json.loads(raw)
            report=record['result']
            if report['validated']:
                raise ValueError('Reviewed research must not qualify a model')
            filename=f'{label}-{name}.json.gz'
            (archive_dir/filename).write_bytes(gzip.compress(raw,mtime=0))
            variants[name]={
                'full_record':str(archive_dir.name+'/'+filename),
                'uncompressed_record_sha256':digest(raw),
                'source_code_sha256':record['source_code_sha256'],
                'engine_version':report['engine_version'],
                'policy_version':report['policy_version'],
                'learning_report_version':report['learning_report_version'],
                'validated':report['validated'],
                'rejection_reasons':report['rejection_reasons'],
                'accounts':{key:{k:report[key].get(k) for k in METRICS}
                    for key in ('holdout','holdout_stressed','frozen_holdout')},
                'selected_trades':report['holdout_trades'],
                'prediction_audit':report['prediction_audit'],
                'development_prediction_audit':report['development_prediction_audit'],
                'learning_evidence':report['learning_evidence']}
            if name=='baseline':
                first,old=record,report
            else:
                for key in ('bundle_sha256','reviewed_report_sha256','bitcoin_data_sha256'):
                    if record[key]!=first[key]:raise ValueError(f'Unmatched {key}')
                for key in ('data_sha256','daily_data','cost_signature','historical_examples',
                            'training_diagnostics','holdout_start_ts','training_label_end_ts'):
                    if report[key]!=old[key]:raise ValueError(f'Unmatched {key}')
                if report['evaluation']['reviewed_through_ts']!=old['evaluation']['reviewed_through_ts']:
                    raise ValueError('Unmatched reviewed boundary')
        def economics(trades):
            return [{k:v for k,v in t.items() if k!='entry_forecast'} for t in trades]
        summary['studies'].append({
            'symbol':report['symbol'],'interval':report['interval'],'bundle':bundle,
            'bundle_sha256':record['bundle_sha256'],
            'reviewed_report_sha256':record['reviewed_report_sha256'],
            'data_sha256':report['data_sha256'],
            'daily_data_sha256':report['daily_data']['data_sha256'],
            'bitcoin_data_sha256':record['bitcoin_data_sha256'],
            'cost_signature':report['cost_signature'],
            'reviewed_through_ts':report['evaluation']['reviewed_through_ts'],
            'replay':report['replay'],'historical_examples':report['historical_examples'],
            'selected_trade_economics_identical':economics(old['holdout_trades'])==economics(report['holdout_trades']),
            'ordinary_net_difference':report['holdout']['net_pnl']-old['holdout']['net_pnl'],
            'higher_cost_net_difference':report['holdout_stressed']['net_pnl']-old['holdout_stressed']['net_pnl'],
            'variants':variants})
    args.out.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'studies':len(summary['studies']),
        'ordinary_differences':[s['ordinary_net_difference'] for s in summary['studies']],
        'all_selected_trade_economics_identical':all(s['selected_trade_economics_identical'] for s in summary['studies'])}))


if __name__=='__main__':main()
