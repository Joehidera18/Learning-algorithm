"""Dated, read-only equity research. Never supplies a crypto trading signal."""
import copy
import json
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

EDITION = "2026-09-20.1"
REPORT_NAME = "stock-watchlist-2026-09-20.md"


@lru_cache(maxsize=4)
def _catalog(base_dir):
    with (Path(base_dir) / "research" / "stock_watchlist.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def research_payload(base_dir, today=None):
    """Preserve the research date; elapsed dates never imply successful outcomes."""
    today = today or datetime.now(timezone.utc).date()
    data = copy.deepcopy(_catalog(str(Path(base_dir).resolve())))
    reviewed = date.fromisoformat(data["research_as_of"])
    age = (today - reviewed).days
    status = "future_date" if age < 0 else "review_due" if age > data["review_interval_days"] else "dated"
    data["review"] = {"checked_on": today.isoformat(), "age_days": age, "status": status}
    data["live_quotes"] = False
    data["trading_enabled"] = False
    for stock in data["stocks"]:
        catalyst = stock["catalyst"]
        start = date.fromisoformat(catalyst["start_date"]) if catalyst["start_date"] else None
        end = date.fromisoformat(catalyst["end_date"]) if catalyst["end_date"] else None
        if end and end < today:
            state = "review_needed"
        elif start and end and start <= today <= end:
            state = "date_today" if start == end else "window_open"
        else:
            state = catalyst["kind"]
        catalyst["calendar_status"] = state
        catalyst["outcome"] = "not_verified"
    return data


def report_bytes(base_dir):
    return (Path(base_dir) / "research" / REPORT_NAME).read_bytes()
