"""Bitcoin context joined at the decision close, never from an unfinished day."""
from .daily_context import DAY_MS, independent_daily_context

BENCHMARK = "BTC-USD"


def attach_market_context(rows, features, step, benchmark_rows, in_place=False):
    if len(rows) != len(features):
        raise ValueError("Market context must match the decision candles")
    joined = independent_daily_context(rows, step, benchmark_rows or [])
    output, cached = [], {}
    for feature, benchmark in zip(features, joined):
        if not feature:
            output.append(feature)
            continue
        daily = feature.get("daily", {})
        key = (id(daily), id(benchmark))
        if key not in cached:
            context = {"ready":False, "symbol":BENCHMARK}
            if benchmark.get("ready") and daily.get("ready"):
                context.update(ready=True, available_ts=benchmark["available_ts"],
                    momentum7=benchmark["momentum7"], atr_pct=benchmark["atr_pct"],
                    trend=1 if benchmark["trend_up"] else -1 if benchmark["trend_down"] else 0,
                    relative_momentum7=daily["momentum7"]-benchmark["momentum7"])
            cached[key] = context
        target = feature if in_place else dict(feature)
        target["market_context"] = cached[key]
        output.append(target)
    return output


def data_summary(rows, features, start=0):
    from .evaluation import dataset_digest
    return {"symbol":BENCHMARK, "source":"independent_daily_candles" if rows is not None else "unavailable",
        "rows":len(rows or []), "data_sha256":dataset_digest(rows) if rows is not None else None,
        "start_ts":rows[0]["ts"] if rows else None, "end_ts":rows[-1]["ts"] if rows else None,
        "holdout_ready_candles":sum(bool(f and f.get("market_context", {}).get("ready")) for f in features[start:]),
        "holdout_candles":len(features)-start,
        "rule":"Use only completed, consecutive Bitcoin UTC daily candles available at signal close. "
            "Relative strength is the coin's seven-day return minus Bitcoin's. Missing or stale days are unavailable, never forward-filled."}
