"""Download public Coinbase minute observations; never synthesize or merge feeds.

Each provider has its own CSV, exact HTTP response checkpoints and coverage
record. This command has no account credentials, database writes or order API.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MINUTE = 60000
FIELDS = ('ts', 'open', 'high', 'low', 'close', 'volume')
PROVIDERS = ('exchange', 'advanced')


def windows(start, end, minutes=299):
    if start < 0 or end <= start or start % MINUTE or end % MINUTE:
        raise ValueError('Use an increasing interval aligned to UTC minutes')
    if not 1 <= minutes <= 299:
        raise ValueError('Each request must fit within the candle API limit')
    return [(left, min(left+minutes*MINUTE, end))
            for left in range(start, end, minutes*MINUTE)]


def request_url(provider, symbol, start, end):
    if provider == 'exchange':
        iso = lambda ms: datetime.fromtimestamp(ms/1000, timezone.utc).isoformat()
        params = dict(granularity=60, start=iso(start), end=iso(end))
        base = 'https://api.exchange.coinbase.com/products/' + symbol + '/candles'
    elif provider == 'advanced':
        params = dict(start=str(start//1000), end=str(end//1000),
                      granularity='ONE_MINUTE', limit=350)
        base = 'https://api.coinbase.com/api/v3/brokerage/market/products/' + symbol + '/candles'
    else:
        raise ValueError('Unknown candle provider')
    return base+'?'+urlencode(params)


def normalize(provider, payload, start, end):
    raw = payload if provider == 'exchange' else payload.get('candles') if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        raise ValueError('Candle response has no candle list')
    found = {}
    for item in raw:
        try:
            if provider == 'exchange':
                seconds, low, high, opening, close, volume = item
            else:
                seconds = item['start']
                low, high, opening, close, volume = (item[k] for k in ('low', 'high', 'open', 'close', 'volume'))
            if isinstance(seconds, bool):
                raise ValueError('Boolean candle timestamp')
            seconds = float(seconds)
            if not math.isfinite(seconds) or seconds != int(seconds) or seconds % 60:
                raise ValueError('Candle timestamp is not an aligned UTC minute')
            stamp = int(seconds)*1000
            if not start <= stamp < end:
                continue  # Both APIs may include the end boundary or earlier buckets.
            opening, high, low, close, volume = map(float, (opening, high, low, close, volume))
            if (not all(math.isfinite(v) for v in (opening, high, low, close, volume))
                    or min(opening, high, low, close) <= 0 or volume < 0
                    or low > min(opening, close) or high < max(opening, close)):
                raise ValueError('Invalid OHLCV observation')
            row = dict(zip(FIELDS, (stamp, opening, high, low, close, volume)))
            if stamp in found and found[stamp] != row:
                raise ValueError('Conflicting observations for one minute')
            found[stamp] = row
        except (TypeError, KeyError, OverflowError) as exc:
            raise ValueError('Malformed candle observation') from exc
    return [found[t] for t in sorted(found)]


def coverage(rows, start, end):
    stamps = {r['ts'] for r in rows}
    missing, left = [], None
    for stamp in range(start, end, MINUTE):
        if stamp not in stamps and left is None:
            left = stamp
        elif stamp in stamps and left is not None:
            missing.append(dict(start_ts=left, end_ts=stamp, missing=(stamp-left)//MINUTE))
            left = None
    if left is not None:
        missing.append(dict(start_ts=left, end_ts=end, missing=(end-left)//MINUTE))
    expected = (end-start)//MINUTE
    return dict(expected_minutes=expected, observed_minutes=len(stamps),
                missing_minutes=expected-len(stamps), coverage_pct=100*len(stamps)/expected,
                zero_volume_observations=sum(r['volume'] == 0 for r in rows),
                missing_ranges=missing)


class Downloader:
    def __init__(self, output, timeout=12, request_spacing=.4):
        self.output, self.timeout, self.spacing = Path(output), timeout, request_spacing
        self.lock, self.next_request = threading.Lock(), 0.

    def _pace(self):
        with self.lock:
            delay = max(0., self.next_request-time.monotonic())
            self.next_request = max(self.next_request, time.monotonic())+self.spacing
        if delay:
            time.sleep(delay)

    def fetch(self, provider, symbol, start, end):
        url = request_url(provider, symbol, start, end)
        folder = self.output/'responses'/provider
        folder.mkdir(parents=True, exist_ok=True)
        path = folder/f'{symbol}_{start}_{end}.json.gz'
        if path.exists():
            with gzip.open(path, 'rt') as handle:
                saved = json.load(handle)
            if saved['url'] != url:
                raise ValueError('Checkpoint does not match this exact request')
            return normalize(provider, saved['response'], start, end)
        last = None
        for attempt in range(3):
            self._pace()
            try:
                req = Request(url, headers={'User-Agent': 'CryptO-Data-Recovery/1.0', 'Accept': 'application/json'})
                with urlopen(req, timeout=self.timeout) as response:
                    payload = json.load(response)
                rows = normalize(provider, payload, start, end)
                saved = dict(url=url, provider=provider, symbol=symbol, start_ts=start, end_ts=end,
                             retrieved_at=datetime.now(timezone.utc).isoformat(), response=payload)
                temporary = path.with_suffix('.tmp')
                with gzip.open(temporary, 'wt') as handle:
                    json.dump(saved, handle, allow_nan=False)
                temporary.replace(path)
                return rows
            except HTTPError as exc:
                last = f'HTTP {exc.code}'
                if exc.code != 429 and exc.code < 500:
                    break
            except (URLError, TimeoutError, OSError, ValueError) as exc:
                last = type(exc).__name__+': '+str(exc)[:200]
            if attempt < 2:
                time.sleep(1+attempt)
        raise RuntimeError(last or 'No response')

    def download(self, provider, symbol, start, end):
        plan = windows(start, end)
        found, failures = {}, []
        # Stop promptly if this environment cannot retrieve even one known
        # historical window; do not spend hundreds of requests on that failure.
        first_start, first_end = plan[0]
        try:
            for row in self.fetch(provider, symbol, first_start, first_end):
                found[row['ts']] = row
        except RuntimeError as exc:
            return [], dict(provider=provider, requests_planned=len(plan), requests_completed=0,
                            source_unavailable=str(exc), complete_request_scan=False,
                            **coverage([], start, end))
        completed = 1
        with ThreadPoolExecutor(max_workers=2) as executor:
            pending = {executor.submit(self.fetch, provider, symbol, a, b): (a, b) for a, b in plan[1:]}
            for future in as_completed(pending):
                a, b = pending[future]
                try:
                    for row in future.result():
                        found[row['ts']] = row
                    completed += 1
                except RuntimeError as exc:
                    failures.append(dict(start_ts=a, end_ts=b, error=str(exc)))
                if (completed+len(failures)) % 50 == 0:
                    print(f'{provider}: {completed+len(failures)}/{len(plan)} windows; '
                          f'{len(found):,} observed candles; {len(failures)} failed windows', flush=True)
        rows = [found[t] for t in sorted(found)]
        return rows, dict(provider=provider, requests_planned=len(plan), requests_completed=completed,
                          failed_windows=failures, complete_request_scan=not failures,
                          **coverage(rows, start, end))


def compare_feeds(first, second):
    a, b = ({r['ts']: r for r in rows} for rows in (first, second))
    shared = set(a) & set(b)
    conflicts = [t for t in sorted(shared) if any(
        not math.isclose(a[t][k], b[t][k], rel_tol=1e-8, abs_tol=1e-12) for k in FIELDS[1:])]
    return dict(overlap_minutes=len(shared), matching_minutes=len(shared)-len(conflicts),
                conflicting_minutes=len(conflicts), conflicting_timestamps=conflicts,
                exchange_only_minutes=len(set(a)-set(b)), advanced_only_minutes=len(set(b)-set(a)),
                merged=False, interpretation='Additional timestamps are candidates for investigation, not automatic replacements.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--start-ms', type=int, required=True)
    parser.add_argument('--end-ms', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Z0-9]{2,15}-USD', args.symbol):
        parser.error('Use a Coinbase USD product ID')
    if args.end_ms > int(time.time()*1000)//MINUTE*MINUTE or args.end_ms-args.start_ms > 366*86400000:
        parser.error('Use completed historical minutes within a maximum 366-day request')
    windows(args.start_ms, args.end_ms)
    args.out.mkdir(parents=True, exist_ok=True)
    downloader = Downloader(args.out)
    reports, datasets = [], {}
    for provider in PROVIDERS:
        rows, report = downloader.download(provider, args.symbol, args.start_ms, args.end_ms)
        path = args.out/f'{args.symbol}_1m_{provider}.csv'
        with path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        report.update(csv=path.name, csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        reports.append(report);datasets[provider] = rows
        print(json.dumps({k: v for k, v in report.items() if k not in ('missing_ranges', 'failed_windows')}, indent=2), flush=True)
        (args.out/'download-status.json').write_text(json.dumps(reports, indent=2)+'\n')
    summary = dict(symbol=args.symbol, interval='1m', start_ts=args.start_ms, end_ts=args.end_ms,
                   providers=reports, comparison=compare_feeds(datasets['exchange'], datasets['advanced']),
                   synthetic_candles=0, production_history_modified=False,
                   unknown_minutes_are_not_verified_inactive=True)
    (args.out/'recovery-report.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    return 0 if any(datasets.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
