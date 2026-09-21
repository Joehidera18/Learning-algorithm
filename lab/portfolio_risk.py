"""Observed hourly co-movement for the paper account's concentration budget."""
import math

HOUR = 3600000


def hourly_returns(rows, asof):
    recent = [r for r in rows if asof-169*HOUR <= r["ts"] and r["ts"]+HOUR <= asof]
    if not recent or asof-(recent[-1]["ts"]+HOUR) > HOUR+15000:
        return {}
    result = {}
    for a, b in zip(recent, recent[1:]):
        if b["ts"]-a["ts"] == HOUR and min(a["close"], b["close"]) > 0:
            v = math.log(b["close"]/a["close"])
            if math.isfinite(v):
                result[b["ts"]] = v
    return result


def correlation(left, right):
    stamps = sorted(set(left) & set(right))
    if len(stamps) < 72:
        return None, len(stamps)
    xs, ys = [left[t] for t in stamps], [right[t] for t in stamps]
    mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
    xx, yy = sum((x-mx)**2 for x in xs), sum((y-my)**2 for y in ys)
    if xx <= 1e-18 or yy <= 1e-18:
        return None, len(stamps)
    return max(-1., min(1., sum((x-mx)*(y-my) for x, y in zip(xs, ys))/math.sqrt(xx*yy))), len(stamps)


def related_risk(product, market, positions, asof, direction="LONG"):
    """Missing evidence counts toward the budget, never as diversification.

    This is an entry-time cap on nominal stop risk, not a forecast of maximum
    portfolio loss. Gaps can exceed stops and correlations can change.
    """
    left = hourly_returns(market.get(product, {}).get("bars", {}).get("1h", []), asof)
    risk, relationships = 0., []
    for symbol, position in positions.items():
        right = hourly_returns(market.get(symbol, {}).get("bars", {}).get("1h", []), asof)
        coefficient, observations = correlation(left, right)
        aligned = coefficient * (1 if direction == position.get("direction", "LONG") else -1) if coefficient is not None else None
        included = aligned is None or aligned >= .75 or symbol == product
        if included:
            risk += position["risk_usd"]
        relationships.append({"symbol": symbol, "correlation": coefficient, "direction_adjusted_correlation": aligned, "matched_hours": observations,
            "included_in_risk_budget": included, "unknown": coefficient is None})
    return {"related_open_risk_usd": risk, "relationships": relationships,
            "threshold": .75, "lookback_hours": 168, "minimum_matched_hours": 72,
            "missing_data_rule": "Count the position as related until adequate fresh history is available"}
