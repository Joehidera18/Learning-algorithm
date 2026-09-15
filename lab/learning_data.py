"""Select history without inventing candles or trading through missing prices."""
from .data import INTERVAL_MS
from .research import validate_rows

FEATURE_WARMUP = 240


def prepare_learning_history(rows, interval):
    quality = validate_rows(rows, interval, allow_gaps=True)
    step = INTERVAL_MS[interval]
    starts = [0]+[i for i in range(1, len(rows)) if rows[i]["ts"]-rows[i-1]["ts"] != step]
    segments = [{"start_index":start, "end_index":end,
                 "start_ts":rows[start]["ts"], "end_ts":rows[end-1]["ts"]+step,
                 "candles":end-start, "warmup_candles":min(FEATURE_WARMUP, end-start)}
                for start, end in zip(starts, starts[1:]+[len(rows)])]
    warmup = sum(s["warmup_candles"] for s in segments)
    if warmup == len(rows):
        raise ValueError("No observed section has more than 240 consecutive candles for indicator warmup. "
                         "Missing prices are not filled in.")
    coverage = {"downloaded_candles":len(rows), "used_candles":len(rows),
        "excluded_candles":0, "missing_intervals":quality["gaps"],
        "downloaded_hours":len(rows)*step/3600000, "used_hours":len(rows)*step/3600000,
        "segment_count":len(segments), "segments":segments,
        "warmup_candles":warmup, "signal_ready_candles":len(rows)-warmup,
        "selection":"Keep all recorded candles in separate continuous sections; restart indicators after each gap. "
                    "No fabricated candles or entries across missing prices."}
    return rows, quality, coverage
