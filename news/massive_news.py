"""Pull Massive ticker news. Publication time is required; no backdating."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from .score import article_score


def _ms(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 10_000_000_000:
        return int(value)
    text = str(value).replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except ValueError:
        return None


def download(symbol, start_ts, end_ts, session=None, api_key=None, cancelled=None):
    import requests
    key = api_key if api_key is not None else os.getenv("MASSIVE_API_KEY", "")
    if not key:
        raise ValueError("Set MASSIVE_API_KEY to download stock news")
    http = session or requests.Session()
    start = datetime.fromtimestamp(start_ts/1000, timezone.utc).date().isoformat()
    end = datetime.fromtimestamp(end_ts/1000, timezone.utc).date().isoformat()
    params = {"ticker": symbol, "published_utc.gte": start, "published_utc.lte": end,
              "order": "asc", "sort": "published_utc", "limit": 50}
    headers = {"Authorization": "Bearer "+key, "User-Agent": "Learning-algorithm-news/1"}
    rows, url = [], "https://api.massive.com/v2/reference/news"
    for _ in range(40):
        if cancelled and cancelled():
            raise InterruptedError("News download cancelled")
        response = http.get(url, params=params, headers=headers, timeout=30)
        if response.status_code != 200:
            raise RuntimeError("Massive news unavailable (HTTP %s)" % response.status_code)
        payload = response.json()
        for item in payload.get("results") or []:
            published = _ms(item.get("published_utc"))
            if published is None:
                continue
            score, method = article_score(item, symbol)
            rows.append({
                "id": item.get("id"),
                "published_ts": published,
                "available_ts": published,
                "title": item.get("title") or "",
                "url": item.get("article_url") or item.get("url") or "",
                "publisher": (item.get("publisher") or {}).get("name"),
                "score": score,
                "method": method,
                "ticker": symbol,
            })
        next_url = payload.get("next_url")
        if not next_url:
            break
        url, params = next_url, None
    rows.sort(key=lambda row: row["published_ts"])
    return rows
