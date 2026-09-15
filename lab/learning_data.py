"""Select history without inventing candles or trading through missing prices."""
from .data import INTERVAL_MS
from .research import validate_rows


def prepare_learning_history(rows, interval):
    original = validate_rows(rows, interval, allow_gaps=True)
    step = INTERVAL_MS[interval]
    start = 0
    for index in range(1, len(rows)):
        if rows[index]["ts"]-rows[index-1]["ts"] != step:
            start = index
    selected = rows[start:]
    if len(selected) < 3000:
        raise ValueError(f"Only {len(selected):,} consecutive completed candles remain after the latest gap; "
                         "learning needs at least 3,000. Missing prices are not filled in.")
    quality = validate_rows(selected, interval)
    coverage = {"downloaded_candles":len(rows), "used_candles":len(selected),
        "excluded_candles":start, "missing_intervals":original["gaps"],
        "downloaded_hours":len(rows)*step/3600000, "used_hours":len(selected)*step/3600000,
        "selection":"Most recent continuous history; all earlier candles before the last gap are excluded."}
    return selected, quality, coverage
