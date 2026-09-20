"""Timestamp-aligned relative returns, not proof of institutional order flow."""
import math


def relative_strength_divergence(primary_rows, peer_rows, lookback=20, tolerance=.002):
    """One result per primary candle; a missing paired window is unavailable.

    This is return-spread divergence, not a confirmed-swing SMT strategy. Future
    peer rows cannot substitute for missing observations at the same timestamp.
    """
    if type(lookback) is not int or lookback < 1 or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError('Invalid divergence window or tolerance')
    for rows in (primary_rows, peer_rows):
        prior = -1
        for row in rows:
            ts = row.get('ts')
            close = row.get('close')
            if (type(ts) is not int or ts <= prior or not isinstance(close, (int, float)) or
                    not math.isfinite(close) or close <= 0):
                raise ValueError('Divergence needs ordered unique timestamps and positive finite closes')
            prior = ts
    peer = {r['ts']:r['close'] for r in peer_rows}
    missing = [0]
    for row in primary_rows:
        missing.append(missing[-1]+int(row['ts'] not in peer))
    out = []
    for i,row in enumerate(primary_rows):
        result = {'smt_available':False, 'smt_bullish':False, 'smt_bearish':False, 'smt_spread':0.}
        if i >= lookback and missing[i+1] == missing[i-lookback]:
            start = primary_rows[i-lookback]
            spread = (row['close']/start['close']-1) - (peer[row['ts']]/peer[start['ts']]-1)
            result.update(smt_available=True, smt_bullish=spread>tolerance,
                          smt_bearish=spread<-tolerance, smt_spread=spread)
        out.append(result)
    return out
