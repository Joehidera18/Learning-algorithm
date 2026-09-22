"""Named research strategies. Live trading only uses a frozen file that already passed the lab."""
from .base import StrategySpec, list_strategies, load_strategy
from . import structure_family  # noqa: F401 — registers built-in families
from . import orb_15m  # noqa: F401

__all__ = ["StrategySpec", "list_strategies", "load_strategy"]
