"""Frozen, long-only research adaptations; never automatic trading approvals.

All session statistics are computed in one forward pass. A later missing bar
cannot invalidate an earlier decision, and today's volume never enters its own
relative-volume baseline. See research/day-strategy-candidates/README.md.
"""
from collections import deque
import math

from .base import StrategySpec, register

MINUTE = 60_000
STEP = 5 * MINUTE
LOOKBACK = 14
ORB_SOURCE = {
    "title": "Zarattini, Barbon & Aziz: opening ranges and stocks in play",
    "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284",
}
VWAP_SOURCE = {
    "title": "Andrew Aziz: public VWAP teaching slides",
    "url": "https://bearbulltraders.com/wp-content/uploads/pdfs/speedtrader.pdf",
}


def _session_contexts(rows):
    """Only completed, contiguous prior sessions contribute to volume averages."""
    history = deque(maxlen=LOOKBACK)
    current = previous = None
    for row in rows:
        new_session = current is None or row.get("session") != current["session"]
        if new_session:
            if current is not None:
                if current["valid"] and previous["end_ts"] == current["close_ts"]:
                    history.append(current)
                else:
                    history.clear()
            current = {
                "session": row.get("session"), "open_ts": row.get("session_open_ts"),
                "close_ts": row.get("session_close_ts"), "valid": (
                    row.get("asset_class") == "equity" and row.get("session") is not None
                    and row.get("ts") == row.get("session_open_ts")
                    and row.get("session_close_ts") is not None),
                "volume": 0., "pv": 0., "cumulative": {}, "opening5": None,
                "opening15": None, "high": None, "low": None, "recent": deque(maxlen=2),
            }
        if previous is not None and row["ts"] != previous.get("next_ts"):
            history.clear()
            if not new_session:
                current["valid"] = False
        if (row.get("end_ts") != row["ts"] + STEP
                or row.get("session_open_ts") != current["open_ts"]
                or row.get("session_close_ts") != current["close_ts"]):
            current["valid"] = False
        opening = current["open_ts"]
        elapsed = (row["end_ts"] - opening) // MINUTE if opening is not None else -1
        current["high"] = max(current["high"], row["high"]) if current["high"] is not None else row["high"]
        current["low"] = min(current["low"], row["low"]) if current["low"] is not None else row["low"]
        current["volume"] += row["volume"]
        current["pv"] += (row["high"] + row["low"] + row["close"]) / 3 * row["volume"]
        current["cumulative"][elapsed] = current["volume"]
        vwap = current["pv"] / current["volume"] if current["volume"] > 0 else None
        if elapsed == 5:
            current["opening5"] = dict(high=row["high"], low=row["low"],
                bullish=row["close"] > row["open"], volume=current["volume"])
        if elapsed == 15:
            current["opening15"] = dict(high=current["high"], low=current["low"],
                volume=current["volume"])

        def relative_volume(key):
            if not current["valid"] or len(history) != LOOKBACK:
                return None
            values = [(day[key] or {}).get("volume") if key != "cumulative"
                      else day[key].get(elapsed) for day in history]
            value = ((current[key] or {}).get("volume") if key != "cumulative"
                     else current["volume"])
            if value is None or any(v is None or v <= 0 for v in values):
                return None
            return value / (sum(values) / LOOKBACK)

        yield {"row": row, "elapsed": elapsed, "valid": current["valid"],
               "prior_sessions": len(history), "vwap": vwap,
               "opening5": current["opening5"], "opening15": current["opening15"],
               "rvol5": relative_volume("opening5"), "rvol15": relative_volume("opening15"),
               "cumulative_rvol": relative_volume("cumulative"), "recent": tuple(current["recent"])}
        current["recent"].append({"row": row, "vwap": vwap})
        previous = row


class _DayCandidate(StrategySpec):
    allowed_intervals = ("5m",)
    supported_modes = ("day",)
    research_only = True
    max_signals_per_session = 1
    evidence_note = ("Experimental rule translation. Single-stock, long-only tests do not reproduce "
                     "the published stock-selection studies. Longer history and forward paper results are required.")
    rvol_key = "rvol5"
    min_rvol = 1.5
    first_minute = 10
    last_minute = 90
    stop_buffer_atr = 0.
    params = dict(StrategySpec.params, min_net_rr=1., max_cost_r=.5,
                  cooldown_minutes=0, loss_streak_limit=3, loss_cooldown_hours=6,
                  time_stop_hours=24)

    def prepare(self, rows, features, interval):
        if interval != "5m":
            raise ValueError(self.name + " requires 5m decision candles")
        if len(rows) != len(features):
            raise ValueError("One feature slot is required per candle")
        session, state = None, {}
        for ctx, feat in zip(_session_contexts(rows), features):
            row = ctx["row"]
            if row.get("session") != session:
                session, state = row.get("session"), {"used": False}
            reason, stop = "no_setup", None
            if not ctx["valid"]:
                reason = "incomplete_session"
            elif ctx[self.rvol_key] is None:
                reason = "relative_volume_not_ready"
            elif ctx[self.rvol_key] < self.min_rvol:
                reason = "low_relative_volume"
            elif not self.first_minute <= ctx["elapsed"] <= self.last_minute:
                reason = "outside_entry_window"
            elif state.get("used"):
                reason = "session_signal_already_used"
            else:
                stop = self.setup(ctx, state)
                if stop is not None:
                    state["used"] = True
                    reason = None
            if feat is None:
                continue
            atr = feat.get("_atr")
            if stop is not None:
                if not isinstance(atr, (int, float)) or not math.isfinite(atr) or atr <= 0:
                    reason, stop = "atr_not_ready", None
                else:
                    stop -= self.stop_buffer_atr * atr
                    if not 0 < stop < row["close"]:
                        reason, stop = "invalid_stop", None
            feat["day_candidate"] = {"reason": reason, "stop": stop,
                "signal_close": row["close"], "relative_volume": ctx[self.rvol_key],
                "prior_sessions": ctx["prior_sessions"], "vwap": ctx["vwap"]}

    def signal(self, features, params):
        ctx = features.get("day_candidate") or {}
        if ctx.get("reason") is not None or ctx.get("stop") is None:
            return None, ctx.get("reason") or "session_context_not_ready"
        return 70., None

    def levels(self, features, params):
        ctx = features.get("day_candidate") or {}
        if ctx.get("stop") is None:
            return None
        stop, close = ctx["stop"], ctx["signal_close"]
        target = close + 2 * (close - stop)
        return stop, target, target, 0.


@register
class OpeningVolumeBreakout(_DayCandidate):
    name = "orb_5m_rvol"
    version = "orb-5m-rvol-close-v1"
    title = "5-minute opening-volume breakout · research"
    description = "Bullish first five minutes, opening volume at least 1.5× the prior 14 complete sessions, then a closing breakout by 11:00 New York time."
    sources = (ORB_SOURCE,)
    rules = (
        "Use 5-minute regular-session bars and 14 complete prior sessions for the opening-volume baseline.",
        "The 09:30–09:35 bar must close above its open. Its volume must be at least 1.5× its prior-session average.",
        "Take the first later close above that bar's high, from 09:40 through 11:00 New York time; entry is the next open.",
        "Stop at the opening bar's low. Full target is signal close plus twice its distance to the stop; flatten at session close.",
        "At most one signal per session. Next-open gaps and costs may reject it; there is no second attempt.",
    )
    params = dict(_DayCandidate.params, family=name)

    def setup(self, ctx, state):
        box = ctx["opening5"]
        if box and box["bullish"] and ctx["row"]["close"] > box["high"]:
            return box["low"]
        return None


@register
class OpeningRangeRetest(_DayCandidate):
    name = "orb_15m_retest"
    version = "orb-15m-retest-v1"
    title = "15-minute breakout and retest · research"
    description = "Above-average opening volume, a close above the opening range, and a bullish retest within six subsequent bars."
    rvol_key, min_rvol = "rvol15", 1.
    first_minute = 20
    stop_buffer_atr = .1
    sources = (ORB_SOURCE,)
    rules = (
        "Build the 09:30–09:45 high and low from complete 5-minute bars. Opening volume must be at least its prior 14-session average.",
        "Record the first subsequent close above the range high. Do not enter on that breakout bar.",
        "Within the next six bars, require low at or below the range high, close above it, and close above the candle's open.",
        "Signal must close by 11:00 New York time. Enter next open; stop below the retest low by 0.1× the signal's 5-minute ATR.",
        "Full target is signal close plus twice its stop distance. One signal per session; flatten at the close. The retest rules are our hypothesis, not the paper's implementation.",
    )
    params = dict(_DayCandidate.params, family=name)

    def setup(self, ctx, state):
        box, row = ctx["opening15"], ctx["row"]
        if not box:
            return None
        if "break_minute" not in state:
            if row["close"] > box["high"]:
                state["break_minute"] = ctx["elapsed"]
            return None
        age = ctx["elapsed"] - state["break_minute"]
        if (0 < age <= 30 and row["low"] <= box["high"] < row["close"]
                and row["close"] > row["open"]):
            return row["low"]
        return None


@register
class VWAPReclaim(_DayCandidate):
    name = "vwap_reclaim"
    version = "vwap-reclaim-v1"
    title = "VWAP reclaim · research"
    description = "After two closes below their session VWAPs, require a bullish close above VWAP and the preceding candle's high, with normal or better volume."
    rvol_key, min_rvol = "cumulative_rvol", 1.
    first_minute, last_minute = 30, 150
    stop_buffer_atr = .1
    sources = (VWAP_SOURCE,)
    rules = (
        "Compute session VWAP from cumulative typical-price × volume, resetting at 09:30 New York time. This bar approximation is not tick VWAP.",
        "From 10:00 through 12:00, require each of the two preceding candles to close below its own then-current VWAP.",
        "The signal must close above current VWAP, above the preceding high and above its own open.",
        "Cumulative volume must be at least its average at the same session minute over 14 complete prior sessions.",
        "Enter next open. Stop below the lowest low of the signal and preceding two bars by 0.1× 5-minute ATR; full target is twice the signal-close stop distance. One signal per session; flatten at close.",
    )
    params = dict(_DayCandidate.params, family=name)

    def setup(self, ctx, state):
        row, prior = ctx["row"], ctx["recent"]
        if (len(prior) == 2 and ctx["vwap"] is not None
                and all(p["vwap"] is not None and p["row"]["close"] < p["vwap"] for p in prior)
                and row["close"] > max(ctx["vwap"], prior[-1]["row"]["high"], row["open"])):
            return min(row["low"], *(p["row"]["low"] for p in prior))
        return None
