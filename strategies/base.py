"""One file, one strategy. The lab calls signal(); it never asks a chat model at runtime."""
from __future__ import annotations

STRATEGIES = {}
ALLOWED_INTERVALS = ("1m", "5m", "15m", "30m", "1h", "4h")


class StrategySpec:
    """Explicit rules only. Missing higher-timeframe context must reject, not guess."""
    name = ""
    version = "v1"
    direction = "LONG"
    require_context = ()
    params = {
        "stop_atr": 1.5,
        "rr1": 1.0,
        "rr2": 2.0,
        "volume_z_min": 0.0,
        "max_gap_atr": 0.5,
        "max_cost_r": 0.5,
        "time_stop_hours": 24,
        "cooldown_minutes": 15,
        "min_net_rr": 1.5,
        "loss_streak_limit": 3,
        "loss_cooldown_hours": 6,
        "entry_mode": "MARKET_NEXT_OPEN",
        "max_notional_fraction": 0.30,
    }

    def prepare(self, rows, features, interval):
        return

    def signal(self, features, params):
        raise NotImplementedError

    def levels(self, features, params):
        return None


def register(cls):
    if not cls.name:
        raise ValueError("Strategy is missing a name")
    STRATEGIES[cls.name] = cls
    return cls


def list_strategies():
    return sorted(STRATEGIES)


def load_strategy(name):
    if name not in STRATEGIES:
        raise ValueError("Unknown strategy %r. Available: %s" % (name, ", ".join(list_strategies()) or "none"))
    return STRATEGIES[name]()
