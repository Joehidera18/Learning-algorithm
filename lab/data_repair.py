"""Recover missing candles from the same venue; never interpolate prices.

First retry the missing interval directly, then aggregate a complete set of
smaller Coinbase candles. Existing observations are never overwritten.
"""
import math
from .data import INTERVAL_MS

SMALLER = {"1h": "15m", "15m": "5m", "5m": "1m", "6h": "1h", "1d": "1h"}


def valid_candle(row, step):
    try:
        ts = row["ts"]
        values = [float(row[k]) for k in ("open", "high", "low", "close", "volume")]
        return (not isinstance(ts, bool) and int(ts) == ts and ts % step == 0
                and all(math.isfinite(v) for v in values)
                and min(values[:4]) > 0 and values[4] >= 0
                and row["low"] <= min(row["open"], row["close"])
                and row["high"] >= max(row["open"], row["close"])
                and math.isfinite(float(row.get("quote_volume", 0)))
                and row.get("quote_volume", 0) >= 0)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def missing_ranges(rows, step):
    """Internal gaps only; do not mistake time before listing for missing data."""
    return [(a["ts"] + step, b["ts"])
            for a, b in zip(rows, rows[1:]) if b["ts"] - a["ts"] > step]


def aggregate_complete(rows, source_step, target_step, start, end):
    if (source_step <= 0 or target_step <= 0 or target_step % source_step
            or start % target_step or end % target_step or end < start):
        raise ValueError("Aggregation requires aligned whole source and target intervals")
    groups, duplicates = {}, set()
    for row in rows:
        if not valid_candle(row, source_step) or not start <= row["ts"] < end:
            continue
        if row["ts"] in groups:
            duplicates.add(row["ts"])
        groups[row["ts"]] = row
    output = []
    for stamp in range(start, end, target_step):
        stamps = list(range(stamp, stamp + target_step, source_step))
        if any(t not in groups or t in duplicates for t in stamps):
            continue
        chunk = [groups[t] for t in stamps]
        output.append({"ts": stamp, "open": chunk[0]["open"], "close": chunk[-1]["close"],
            "high": max(r["high"] for r in chunk), "low": min(r["low"] for r in chunk),
            "volume": sum(r["volume"] for r in chunk),
            "quote_volume": sum(r.get("quote_volume", r["volume"]*r["close"]) for r in chunk),
            "trades": sum(r.get("trades", 0) for r in chunk)})
    return output


def repair_history(client, symbol, interval, rows, cancelled=None, progress=None,
                   max_requests=60):
    cancelled = cancelled or (lambda: False)
    progress = progress or (lambda **kwargs: None)
    step = INTERVAL_MS[interval]
    ordered = sorted(rows, key=lambda r: r["ts"])
    if any(not valid_candle(r, step) for r in ordered) or len({r["ts"] for r in ordered}) != len(ordered):
        raise ValueError("Cannot repair invalid or duplicate source candles")
    lookup = {r["ts"]: r for r in ordered}
    initial = missing_ranges(ordered, step)
    report = {"missing_before": sum((b-a)//step for a,b in initial), "requests": 0,
        "recovered_direct": 0, "recovered_from_smaller_candles": 0,
        "recovered": [], "errors": [], "source": "Coinbase Exchange", "synthetic": False}

    def fetch(iv, start, end):
        if cancelled():
            raise InterruptedError("Research cancelled")
        if report["requests"] >= max_requests:
            return []
        report["requests"] += 1
        try:
            return client.candles(symbol, iv, min(1500, (end-start)//INTERVAL_MS[iv]), end)
        except InterruptedError:
            raise
        except Exception as exc:
            if len(report["errors"]) < 10:
                report["errors"].append({"interval": iv, "start_ts": start,
                    "end_ts": end, "message": str(exc)[:240]})
            return []

    for start, end in initial:
        # One adjacent candle either side avoids ambiguous API boundary handling.
        for left in range(start, end, 1498*step):
            right = min(end, left + 1498*step)
            for row in fetch(interval, left-step, right+step):
                if valid_candle(row, step) and left <= row["ts"] < right and row["ts"] not in lookup:
                    lookup[row["ts"]] = row
                    report["recovered_direct"] += 1
                    report["recovered"].append({"ts": row["ts"], "method": "direct", "interval": interval})
        if report["requests"] >= max_requests:
            break
    smaller = SMALLER.get(interval)
    if smaller:
        small_step = INTERVAL_MS[smaller]
        remaining = missing_ranges([lookup[t] for t in sorted(lookup)], step)
        width = max(1, 1500 // (step//small_step))*step
        for start, end in remaining:
            for left in range(start, end, width):
                right = min(end, left+width)
                fetched = fetch(smaller, left, right)
                for row in aggregate_complete(fetched, small_step, step, left, right):
                    if row["ts"] not in lookup:
                        lookup[row["ts"]] = row
                        report["recovered_from_smaller_candles"] += 1
                        report["recovered"].append({"ts": row["ts"], "method": "complete_aggregation", "interval": smaller})
            if report["requests"] >= max_requests:
                break
    result = [lookup[t] for t in sorted(lookup)]
    gaps = missing_ranges(result, step)
    report.update(missing_after=sum((b-a)//step for a,b in gaps),
        remaining_gaps=[{"start_ts": a, "end_ts": b, "missing": (b-a)//step} for a,b in gaps],
        request_budget_exhausted=report["requests"] >= max_requests)
    progress(message=f"{symbol}: recovered {report['missing_before']-report['missing_after']} missing candles; {report['missing_after']} remain")
    return result, report
