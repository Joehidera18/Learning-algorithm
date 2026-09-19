"""Pinned, read-only deployment review on supplied candles or a capacity fixture.

Run each source/interval in a fresh process so peak RSS is comparable. Capacity
mode repeats supplied price shapes at artificial timestamps; it reports no
trading performance and must never be used as market or qualification evidence.
"""
import argparse
import csv
import hashlib
import io
import json
import resource
import sys
import time
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--interval', choices=('15m','1h','6h'), default='15m')
    parser.add_argument('--capacity-days', type=int)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve()))
    from lab.continuous import DEFAULTS
    from lab.data import INTERVAL_MS
    from lab.data_repair import aggregate_complete
    from lab.evaluation import dataset_digest
    from lab.learning_research import learn_history
    from lab.engine import build_feature_cache

    source_hash = hashlib.sha256()
    for path in sorted((args.repo/'lab').glob('*.py')):
        source_hash.update(path.name.encode()+b'\0'+path.read_bytes())
    def decode(blob):
        return [{k:int(v) if k in ('ts','trades') else float(v) for k,v in r.items()}
                for r in csv.DictReader(io.StringIO(blob.decode()))]
    with zipfile.ZipFile(args.bundle) as archive:
        rows = decode(archive.read('candles.csv'))
        daily = decode(archive.read('daily-candles.csv'))
        embedded = json.loads(archive.read('learning-result.json'))
    assert embedded['interval'] == '15m'
    assert dataset_digest(rows) == embedded['data_sha256']
    assert dataset_digest(daily) == embedded['daily_data']['data_sha256']
    source_end = rows[-1]['ts']+INTERVAL_MS['15m']
    record = {'source_code_sha256':source_hash.hexdigest(),
        'bundle_sha256':hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        'source_data_sha256':embedded['data_sha256'],
        'daily_data_sha256':embedded['daily_data']['data_sha256'],
        'source_end_ts':source_end, 'selection_uses_results':False,
        'qualification_uses_results':False}
    started = time.monotonic()
    if args.capacity_days is not None:
        if not 1 <= args.capacity_days <= 2920 or args.interval != '15m':
            parser.error('Capacity mode requires 15m and 1..2920 days')
        count = args.capacity_days*96
        fixture = [dict(rows[i % len(rows)], ts=1609459200000+i*900000) for i in range(count)]
        del rows, daily, embedded
        result = build_feature_cache(fixture, '15m', simple_only=True)
        feature_hash = hashlib.sha256()
        for f in result['features']:
            feature_hash.update(json.dumps(f, sort_keys=True, allow_nan=False).encode()+b'\n')
        record.update(mode='artificial_capacity_fixture_only', candles=count,
            feature_sha256=feature_hash.hexdigest(),
            feature_rows=sum(f is not None for f in result['features']),
            scope='Repeated supplied OHLC shapes at artificial timestamps. Feature-build capacity only; excludes learner, web workers and saved reports. No market-performance result.')
    else:
        step = INTERVAL_MS[args.interval]
        if args.interval != '15m':
            start = (rows[0]['ts']+step-1)//step*step
            rows = aggregate_complete(rows, INTERVAL_MS['15m'], step, start, source_end//step*step)
        settings = {**DEFAULTS, **embedded['cost_signature'], 'decision_interval':args.interval}
        result = learn_history(rows, embedded['symbol'], settings, daily_rows=daily,
            reviewed_through_ts=source_end,
            progress=lambda **p:print(p.get('message',''), flush=True))
        assert result['evaluation']['reuses_reviewed_history']
        assert not result['validated']
        assert result['data_sha256'] == dataset_digest(rows)
        assert result['model']['observations'] == result['historical_examples']+result['holdout_learning_updates']
        record.update(mode='recorded_candle_replay', symbol=embedded['symbol'], interval=args.interval,
            candles=len(rows), data_sha256=dataset_digest(rows), result=result,
            scope='Same supplied prices at pinned costs and settings. All data marked already reviewed. Complete buckets only; timeframes overlap. No new candles, tuning, profile installation or orders.')
    record.update(runtime_seconds=time.monotonic()-started,
        peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k != 'result'}), flush=True)


if __name__ == '__main__':
    main()
