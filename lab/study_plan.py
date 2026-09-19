"""Bounded, explicit historical study plans; each timeframe has its own model."""
HISTORY_DAYS = 1825
MAX_HISTORY_DAYS = 2920
MAX_PRACTICE_MARKETS = 60
PRACTICE_INTERVALS = ('5m', '15m', '1h', '6h')
DEFAULT_PRACTICE_INTERVALS = ('15m', '1h', '6h')
# Keep fine-grained studies within a practical single-process candle budget.
# The requested and effective lookback are both shown, never silently conflated.
INTERVAL_HISTORY_LIMITS = {'5m':365, '15m':1825, '1h':2920, '6h':2920}
DEFAULT_PRACTICE_SYMBOLS = (
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'HBAR-USD', 'XRP-USD', 'XLM-USD',
    'ADA-USD', 'DOGE-USD', 'AVAX-USD', 'LINK-USD', 'LTC-USD', 'BCH-USD', 'DOT-USD',
    'UNI-USD', 'AAVE-USD', 'ATOM-USD', 'NEAR-USD', 'FIL-USD', 'ETC-USD', 'ALGO-USD',
    'XTZ-USD', 'ICP-USD', 'INJ-USD', 'OP-USD', 'ARB-USD', 'RENDER-USD', 'APT-USD',
    'SUI-USD', 'SHIB-USD', 'PEPE-USD')


def normalize_plan(intervals, days, primary_interval):
    # Older API clients that omit intervals keep their single selected timeframe.
    intervals = [primary_interval] if intervals is None else intervals
    if (not isinstance(intervals, list) or not 1 <= len(intervals) <= len(PRACTICE_INTERVALS)
            or any(iv not in PRACTICE_INTERVALS for iv in intervals)):
        raise ValueError('Choose one or more of 5m, 15m, 1h and 6h for historical practice')
    if type(days) is not int or not 365 <= days <= MAX_HISTORY_DAYS:
        raise ValueError('Practice history must be 365–2920 whole days')
    return list(dict.fromkeys(intervals)), days


def study_days(interval, requested):
    return min(requested, INTERVAL_HISTORY_LIMITS[interval])


def study_key(report):
    return report['symbol'], report.get('interval', '15m')


def history_coverage(rows, interval, requested_days, end_ms):
    from .data import INTERVAL_MS
    step = INTERVAL_MS[interval]
    days = study_days(interval, requested_days)
    expected = days*86400000//step
    return {'requested_days':requested_days, 'effective_days':days,
        'capped':days < requested_days, 'effective_start_ts':end_ms-days*86400000,
        'requested_end_ts':end_ms, 'expected_candles':expected,
        'observed_candles':len(rows), 'coverage_pct':100*len(rows)/expected,
        'first_candle_ts':rows[0]['ts'] if rows else None,
        'last_candle_close_ts':rows[-1]['ts']+step if rows else None,
        'available_span_days':(rows[-1]['ts']+step-rows[0]['ts'])/86400000 if rows else 0,
        'scope':'Coverage of the effective requested window. Unavailable history, including time before listing, is not invented.'}


def unique_market_hours(reports):
    """Union observed time coverage per market, so overlapping frames count once."""
    markets = {}
    for report in reports:
        ranges, fallback = markets.setdefault(report['symbol'], ([], []))
        segments = report.get('data_selection', {}).get('segments', [])
        if segments:
            ranges.extend((s['start_ts'], s['end_ts']) for s in segments)
        else:
            fallback.append(report.get('data_hours', 0))
    total = 0.
    for ranges, fallback in markets.values():
        covered, end = 0, None
        for first, last in sorted(ranges):
            if end is None or first > end:
                covered += last-first
            else:
                covered += max(0, last-end)
            end = max(end or last, last)
        total += max(covered/3600000, max(fallback, default=0))
    return total
