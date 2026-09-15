"""Twenty-two fixed research candidates in seven strategy families.

Motivation and empirical limits are documented in RESEARCH_NOTES.md.
"""
def profit_candidates():
    output = []
    for family in ("trend_pullback_simple", "breakout_volume_simple", "range_reclaim_simple",
                   "signal_consensus_simple"):
        for stop, reward, volume in ((1.5, 2.0, 0), (2.0, 2.5, 0), (1.5, 2.5, .5), (2.0, 3.0, .5)):
            output.append({"family": family, "direction": "LONG", "threshold": 60,
                "stop_atr": stop, "rr1": 1.0, "rr2": reward, "volume_z_min": volume,
                "max_gap_atr": .5, "max_cost_r": .5, "time_stop_hours": 12, "cooldown_minutes": 15,
                "min_net_rr": 1.5, "loss_streak_limit": 3, "loss_cooldown_hours": 6,
                "min_edge_probability": .5})
    # Predeclared adaptations, not fitted to the user's holdout. Daily ATR
    # accommodates multi-day moves; position sizing keeps dollar risk capped.
    for family, hours in (("daily_trend_momentum_simple", 168),
                          ("volatility_expansion_simple", 72),
                          ("support_rsi_reclaim_simple", 72)):
        for stop, reward in ((.75, 2.5), (1., 3.)):
            output.append({"family":family, "direction":"LONG", "threshold":60,
                "atr_timeframe":"daily", "stop_atr":stop, "rr1":1., "rr2":reward,
                "volume_z_min":0., "max_gap_atr":.5, "max_cost_r":.5,
                "time_stop_hours":hours, "cooldown_minutes":240,
                "min_net_rr":1.5, "loss_streak_limit":3, "loss_cooldown_hours":24,
                "min_edge_probability":.5})
    return output


def simple_signal(f, p):
    """Return a bounded evidence score, never a probability of profit."""
    family = p["family"]
    if f.get("atr_regime", 1) > 2.5 or f.get("range_expansion", 1) > 4:
        return None, "extreme_volatility"
    if p.get("atr_timeframe") == "daily":
        daily = f.get("daily", {})
        if not daily.get("ready") or daily.get("atr", 0) <= 0:
            return None, "daily_history_not_ready"
        if daily.get("trend_down"):
            return None, "daily_downtrend"
        if f.get("volume_z", 0) < p["volume_z_min"]:
            return None, "weak_volume"
        if family == "daily_trend_momentum_simple":
            if not daily.get("trend_up") or daily.get("momentum7", 0) <= 0:
                return None, "no_daily_momentum"
            if not f.get("breakout") or not 45 <= f.get("rsi", 50) <= 75:
                return None, "no_momentum_entry"
            return 70., None
        if family == "volatility_expansion_simple":
            if not f.get("prior_compression"):
                return None, "no_prior_compression"
            if not f.get("breakout") or not 1.5 <= f.get("range_expansion", 1) <= 4:
                return None, "no_expansion_breakout"
            if f.get("rsi", 50) > 78:
                return None, "overextended"
            return 70., None
        if family == "support_rsi_reclaim_simple":
            if not f.get("support_reclaim") or f.get("lower_wick", 0) < .25:
                return None, "no_support_reclaim"
            if not f.get("rsi_previous", 50) <= 40 < f.get("rsi", 50) <= 60:
                return None, "no_rsi_recovery"
            return 70., None
        return None, "unknown_strategy"
    if family == "trend_pullback_simple":
        if f["regime"] != "BULL" or not f.get("_pullback_long"):
            return None, "no_bullish_pullback"
        if not 40 <= f["rsi"] <= 65 or f.get("signed_volume_pressure", 0) < -.1:
            return None, "weak_pullback_confirmation"
        return 65 + min(10, max(0, f.get("adx", 0) - 15) / 2), None
    if family == "breakout_volume_simple":
        if f["regime"] == "BEAR" or not f.get("breakout55"):
            return None, "no_channel_breakout"
        if f["volume_z"] < p["volume_z_min"] or f["rsi"] > 78:
            return None, "weak_breakout_volume_or_overextended"
        return 65 + min(10, max(0, f["volume_z"]) * 3), None
    if family == "range_reclaim_simple":
        if f["regime"] != "CHOP" or f.get("adx", 0) >= 25:
            return None, "not_a_range"
        if not f.get("sweep_low") or f.get("lower_wick", 0) < .35 or f["rsi"] > 50:
            return None, "no_range_reclaim"
        return 65 + min(10, f["lower_wick"] * 10), None
    if family == "signal_consensus_simple":
        # A completed close above the PRECEDING 20-bar high is the entry event.
        # Correlated confirmations are a rule filter, not independent probabilities.
        if f.get("regime") not in ("BULL", "CHOP") or not f.get("breakout"):
            return None, "no_consensus_breakout"
        if f["volume_z"] < p["volume_z_min"] or f["rsi"] > 78:
            return None, "weak_consensus_volume_or_overextended"
        confirmations = sum((bool(f.get("_trend_long")),
                             55 <= f["rsi"] <= 70,
                             f.get("obv_slope", 0) > 0))
        if confirmations < 2:
            return None, "insufficient_consensus_confirmation"
        return 65 + 5 * (confirmations - 2), None
    return None, "unknown_simple_strategy"
