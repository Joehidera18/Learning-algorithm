"""Named research strategies. Live trading only uses a frozen file that already passed the lab."""
from .base import StrategySpec, list_strategies, load_strategy
from . import structure_family  # noqa: F401 — registers built-in families

__all__ = ["StrategySpec", "list_strategies", "load_strategy"]
