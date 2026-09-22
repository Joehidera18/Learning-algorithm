"""Wrap the existing long-only structure families so the lab has a first test subject."""
from lab.strategies import simple_signal
from .base import StrategySpec, register


def _family(family_name):
    class Family(StrategySpec):
        name = family_name
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
