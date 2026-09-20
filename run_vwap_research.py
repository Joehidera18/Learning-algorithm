"""Run the declared VWAP research comparison; never start trading or learning."""
import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from lab.continuous import DEFAULTS
from lab.data import load_history
from lab.paper_store import init_continuous_db
from lab.vwap_research import VwapResearchManager, run_vwap_research


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--csv', type=Path, help='Recorded, completed 1m OHLCV; timestamps in UTC milliseconds')
    source.add_argument('--coinbase', action='store_true')
    parser.add_argument('--symbol', default='BTC-USD')
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--end', help='Exclusive UTC cutoff, YYYY-MM-DD; Coinbase only')
    parser.add_argument('--fee', type=float, default=.004, help='Actual fee fraction per side; default is an assumption')
    parser.add_argument('--slippage', type=float, default=.0005)
    parser.add_argument('--cache-dir', type=Path, default=Path('data'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    import re
    if not re.fullmatch(r'[A-Z0-9]{2,16}-USD', args.symbol) or not 7 <= args.days <= 180:
        parser.error('Use a Coinbase USD symbol and 7–180 days')
    if args.end and not args.coinbase:
        parser.error('--end requires --coinbase')
    settings = {**DEFAULTS, 'fee_rate': args.fee, 'slippage_rate': args.slippage}
    try:
        if args.coinbase:
            end = int(datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()*1000) if args.end else None
            import time
            if end is not None and end > time.time()*1000:
                raise ValueError('The cutoff cannot be in the future')
            with tempfile.TemporaryDirectory() as directory:
                db = Path(directory)/'vwap.sqlite3'
                init_continuous_db(db)
                manager = VwapResearchManager(db, args.cache_dir)
                manager._update = lambda **value: print(value.get('message', ''), flush=True)
                rows = manager._history(args.symbol, '1m', args.days, end_ms=end)
            provenance = {'provider': 'Coinbase Exchange', 'requested_days': args.days,
                          'exclusive_cutoff_ts': end, 'synthetic_fallback': False}
        else:
            rows = load_history(args.csv)
            provenance = {'provider': 'Supplied CSV; authenticity not independently verified', 'filename': args.csv.name}
        result = run_vwap_research(rows, args.symbol, settings, provenance)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, allow_nan=False))
        for variant in result['results']:
            metrics = variant['windows']['later']['standard']['metrics']
            print(variant['label'], 'later net:', metrics['net_pnl'], 'trades:', metrics['trades'], 'complete:', metrics['complete'])
        print('Research only. Report:', args.out.resolve())
        return 0
    except (ValueError, OSError) as exc:
        print('No completed market comparison:', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
