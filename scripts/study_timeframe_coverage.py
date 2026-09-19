"""Fixed hourly/6-hour replay of complete observed buckets from supplied bundles.

This is reused-history research, not new independent market data. No network,
parameter search, profile installation, or trading-account access is performed.
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,action='append',required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--summary',type=Path,required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    from lab.continuous import DEFAULTS
    from lab.data import INTERVAL_MS
    from lab.data_repair import aggregate_complete
    from lab.evaluation import dataset_digest
    from lab.learning_research import learn_history

    code = hashlib.sha256()
    for path in sorted((root/'lab').glob('*.py')):
        code.update(path.name.encode()+b'\0'+path.read_bytes())
    summary = {'source_code_sha256':code.hexdigest(), 'studies':[],
        'selection_uses_results':False, 'qualification_uses_results':False,
        'scope':'Fixed 1h and 6h replays of supplied 15m prices, aggregated only from complete observed buckets. Overlapping prices are not additional independent evidence. Each study has its own $500 simulated account. No new external candles were downloaded.'}
    args.out_dir.mkdir(parents=True,exist_ok=True)
    args.summary.parent.mkdir(parents=True,exist_ok=True)
    def candles(blob):
        return [{k:int(v) if k in ('ts','trades') else float(v) for k,v in r.items()}
                for r in csv.DictReader(io.StringIO(blob.decode()))]
    def metrics(m):
        return {k:m.get(k) for k in ('complete','trades','net_pnl','fees_paid','max_drawdown_pct','win_rate')}
    for bundle in args.bundle:
        with zipfile.ZipFile(bundle) as archive:
            source = candles(archive.read('candles.csv'))
            daily = candles(archive.read('daily-candles.csv'))
            embedded = json.loads(archive.read('learning-result.json'))
        assert embedded['interval']=='15m'
        assert dataset_digest(source)==embedded['data_sha256']
        assert dataset_digest(daily)==embedded['daily_data']['data_sha256']
        symbol = embedded['symbol']
        source_end = source[-1]['ts']+INTERVAL_MS['15m']
        for interval in ('1h','6h'):
            step = INTERVAL_MS[interval]
            start = (source[0]['ts']+step-1)//step*step
            end = source_end//step*step
            rows = aggregate_complete(source,INTERVAL_MS['15m'],step,start,end)
            print(f'Start {symbol} {interval}: {len(rows)} complete observed candles',flush=True)
            started = time.monotonic()
            result = learn_history(rows,symbol,{**DEFAULTS,**embedded['cost_signature'],
                'decision_interval':interval},daily_rows=daily,reviewed_through_ts=source_end)
            assert result['evaluation']['reuses_reviewed_history']
            assert not result['validated']
            assert result['data_sha256']==dataset_digest(rows)
            result['market_data']={'provider':'Supplied Coinbase candle archive',
                'kind':'complete_bucket_aggregation', 'source_interval':'15m',
                'source_bundle_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),
                'source_data_sha256':embedded['data_sha256'], 'synthetic_fallback':False,
                'new_independent_observations':False}
            path = args.out_dir/f'{symbol}_{interval}.json'
            path.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
            record = {'symbol':symbol,'interval':interval,'bundle_sha256':result['market_data']['source_bundle_sha256'],
                'source_data_sha256':embedded['data_sha256'],'data_sha256':result['data_sha256'],
                'daily_data_sha256':result['daily_data']['data_sha256'],
                'candles':len(rows),'missing_target_buckets':(end-start)//step-len(rows),
                'source_start_ts':source[0]['ts'],'source_end_ts':source_end,
                'historical_examples':result['historical_examples'],
                'later_practice_outcomes':result['holdout_learning_updates'],
                'model_observations':result['model']['observations'],
                'regime_examples':result['regime_examples'],
                'holdout':metrics(result['holdout']),'holdout_stressed':metrics(result['holdout_stressed']),
                'replay':result['replay'], 'cost_signature':result['cost_signature'],
                'validated':result['validated'],'rejection_reasons':result['rejection_reasons'],
                'runtime_seconds':round(time.monotonic()-started,3)}
            assert record['model_observations']==record['historical_examples']+record['later_practice_outcomes']
            summary['studies'].append(record)
            args.summary.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
            print(json.dumps(record),flush=True)


if __name__=='__main__':
    main()
