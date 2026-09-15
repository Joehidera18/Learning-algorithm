"""Small shared execution rules; thresholds are test hypotheses, not proven alpha."""

import math


def signal_cost_check(features, params, fee, slip):
    """Screen a candidate at the KNOWN signal close, never a future fill price.

    The execution engine still rechecks costs and gaps at the actual fill.
    This only keeps a cost-infeasible favorite from hiding another candidate.
    """
    raw = float(features.get("_close", 0))
    atr = float(features.get("_atr", 0))
    if not all(math.isfinite(x) for x in (raw, atr, fee, slip)) or raw <= 0 or atr < 0:
        return None, "invalid_entry_features"
    sign = 1 if params.get("direction", "LONG") == "LONG" else -1
    entry = raw * (1 + sign * slip)
    distance = max(max(atr, raw*.002)*params["stop_atr"], raw*.0015)
    stop = entry-sign*distance
    target = entry+sign*distance*params["rr2"]
    if min(entry, stop, target) <= 0:
        return None, "invalid_stop_distance"
    stop_fill = stop*(1-sign*slip)
    cost_r = ((entry+stop_fill)*fee+abs(stop-stop_fill)+abs(entry-raw))/distance
    quality = dict(net_payoff(entry, stop, target, fee, slip, params.get("direction", "LONG")),
        cost_r=cost_r)
    if cost_r > params.get("max_cost_r", .8):
        return quality, "trading_cost_too_high"
    if quality["net_rr"] < params.get("min_net_rr", 0):
        return quality, "net_reward_too_small"
    return quality, None


def net_payoff(entry, stop, target, fee, slip, direction="LONG"):
    """Return modeled stop risk and target reward after fees and adverse exit slippage.

    Supports floats for simulation and Decimal for exchange order construction.
    Entry must already include its modeled slippage.
    """
    sign = 1 if direction == "LONG" else -1
    stop_fill = stop * (1-sign*slip)
    target_fill = target * (1-sign*slip)
    risk = sign*(entry-stop_fill)+(entry+stop_fill)*fee
    reward = sign*(target_fill-entry)-(entry+target_fill)*fee
    if risk <= 0:
        raise ValueError("Net stop risk must be positive")
    return {"unit_risk":risk, "unit_reward":reward, "net_rr":reward/risk,
            "break_even_win_rate":risk/(risk+reward) if reward>0 else None}


def cooldown_minutes(pnls, params):
    """Longer per-market cooldown after consecutive resolved net losses."""
    base = params.get("cooldown_minutes",15)
    threshold = params.get("loss_streak_limit",0)
    streak = 0
    for pnl in reversed(pnls):
        if pnl >= 0:
            break
        streak += 1
    if threshold > 0 and streak >= threshold:
        return max(base,params.get("loss_cooldown_hours",6)*60)
    return base
