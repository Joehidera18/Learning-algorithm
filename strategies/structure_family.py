"""Wrap the existing long-only structure families so the lab has a first test subject."""
from lab.strategies import simple_signal
from .base import StrategySpec, register


def _family(family_name):
    labels = {
        "trend_pullback_simple": ("Trend pullback", "Tests a pullback within an established upward trend using the existing price-structure and momentum checks."),
        "breakout_volume_simple": ("Breakout with volume", "Tests long breakouts with the existing price-structure, trend and volume checks."),
        "range_reclaim_simple": ("Range reclaim", "Tests recovery back into a range after a downside move, using the existing reclaim checks."),
        "signal_consensus_simple": ("Signal agreement", "Tests long entries when the existing structure, momentum and trend checks agree.")}
    class Family(StrategySpec):
        name = family_name
        title, description = labels[family_name]
        version = "structure-v1"
        params = dict(StrategySpec.params, family=family_name, direction="LONG", threshold=60)

        def signal(self, features, params):
            missing = [iv for iv in params.get("require_context", self.require_context)
                       if not (features.get("mtf") or {}).get(iv, {}).get("ready")]
            if missing:
                return None, "higher_timeframe_not_ready:" + ",".join(missing)
            return simple_signal(features, params)
    Family.__name__ = family_name
    return Family


for _name in ("trend_pullback_simple", "breakout_volume_simple",
              "range_reclaim_simple", "signal_consensus_simple"):
    register(_family(_name))
