"""Daily indicators from complete, consecutive recorded candles only.

The current UTC day supplies no daily indicator before its final bar closes.
A gap resets warmup. No missing candle or price is synthesized.
"""
from collections import deque
from bisect import bisect_right

DAY_MS = 86400000
DAILY_WARMUP = 21


def daily_context(rows, step):
    """One context per input close. Shared dictionaries must not be mutated."""
    if step <= 0 or DAY_MS % step:
        raise ValueError("Daily context requires an interval that divides a UTC day")
    days, contexts = deque(maxlen=DAILY_WARMUP), []
    current, previous, context = None, None, {}
    for row in rows:
        ts = row["ts"]
        if previous is not None and ts-previous != step:
            days.clear()
            current, context = None, {}
        previous = ts
        if ts % DAY_MS == 0:
            current = dict(row)
        elif current is not None:
            current["high"] = max(current["high"], row["high"])
            current["low"] = min(current["low"], row["low"])
            current["close"] = row["close"]
        if (ts+step) % DAY_MS == 0 and current is not None:
            days.append(current)
            current = None
            if len(days) == DAILY_WARMUP:
                window = list(days)
                close = window[-1]["close"]
                ma20 = sum(r["close"] for r in window[-20:])/20
                prior_ma20 = sum(r["close"] for r in window[:-1])/20
                tr = [max(b["high"]-b["low"], abs(b["high"]-a["close"]),
                          abs(b["low"]-a["close"])) for a,b in zip(window, window[1:])]
                atr = sum(tr[-14:])/14
                context = {"ready":True, "available_ts":ts+step,
                    "close":close, "ma20":ma20, "prior_ma20":prior_ma20,
                    "momentum7":close/window[-8]["close"]-1,
                    "atr":atr, "atr_pct":atr/close,
                    "ma_distance_atr":(close-ma20)/atr if atr else 0,
                    "trend_up":close>ma20 and ma20>prior_ma20,
                    "trend_down":close<ma20 and ma20<prior_ma20}
        contexts.append(context)
    return contexts


def independent_daily_context(rows, step, daily_rows):
    """As-of join to completed daily observations, independent of intraday gaps.

    A missing DAILY candle still resets daily warmup. Stale context is never
    carried across a missing day, and an in-progress day cannot supply features.
    """
    from .data_repair import valid_candle
    previous = None
    for row in daily_rows:
        if not valid_candle(row, DAY_MS) or (previous is not None and row["ts"] <= previous):
            raise ValueError("Daily candles must be valid, unique and chronological")
        previous = row["ts"]
    contexts = daily_context(daily_rows, DAY_MS)
    available = [r["ts"]+DAY_MS for r in daily_rows]
    joined = []
    for row in rows:
        clock = row["ts"]+step
        i = bisect_right(available, clock)-1
        # Latest completed UTC day must actually be represented.
        expected_close = clock//DAY_MS*DAY_MS
        joined.append(contexts[i] if i >= 0 and available[i] == expected_close else {})
    return joined
