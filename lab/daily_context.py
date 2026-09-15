"""Daily indicators from complete, consecutive recorded candles only.

The current UTC day supplies no daily indicator before its final bar closes.
A gap resets warmup. No missing candle or price is synthesized.
"""
from collections import deque

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
