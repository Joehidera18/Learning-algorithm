"""Point-in-time news features. A headline after the bar close cannot vote."""
from bisect import bisect_right

DAY = 86_400_000


def attach_news(rows, features, articles, interval_ms=60_000, window_ms=DAY):
    if len(rows) != len(features):
        raise ValueError("News features must match decision candles")
    times = [item["available_ts"] for item in articles]
    used = 0
    missing = 0
    for row, feat in zip(rows, features):
        if feat is None:
            continue
        close = int(row.get("end_ts", row["ts"] + interval_ms))
        end = bisect_right(times, close)
        start = bisect_right(times, close - window_ms)
        window = articles[start:end]
        if not window:
            feat["news"] = {"ready": False, "count": 0, "score": 0.0,
                            "positive": 0, "negative": 0, "reason": "no_published_news"}
            missing += 1
            continue
        scores = [item["score"] for item in window]
        feat["news"] = {
            "ready": True,
            "count": len(window),
            "score": sum(scores) / len(scores),
            "positive": sum(value > 0.15 for value in scores),
            "negative": sum(value < -0.15 for value in scores),
            "last_published_ts": window[-1]["available_ts"],
            "last_title": window[-1]["title"][:180],
        }
        used += 1
    return {"articles": len(articles), "bars_with_news": used, "bars_without_news": missing,
            "rule": "Only articles with available_ts <= decision close are visible."}
