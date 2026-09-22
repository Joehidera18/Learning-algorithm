"""15-minute opening range breakout for US cash-session stocks.

Rules (long only, first signal of the day):
- Build high/low from bars whose close is inside the first 15 minutes after session open.
- After that box is complete, a close above the box high is the signal.
- Require this morning's opening-range volume to beat the average of the prior 20 sessions.
- Stop is the box low. Targets are 1x and 2x the box width.
- If news features are present and the 24h score is clearly negative, skip the long.
- Missing session metadata or an incomplete box is a skip, never a guessed range.
"""
from .base import StrategySpec, register

RANGE_MS = 15 * 60 * 1000
RVOL_LOOKBACK = 20
MIN_RVOL = 1.0
NEWS_BLOCK = -0.35


def _end(row):
    return int(row.get("end_ts", row["ts"]))


@register
class OpeningRange15m(StrategySpec):
    name = "orb_15m"
    version = "orb-15m-v1-news-filter"
    direction = "LONG"
    params = dict(StrategySpec.params,
                  family="orb_15m",
                  stop_atr=1.0,
                  rr2=2.0,
                  max_cost_r=0.8,
                  min_net_rr=0.8,
                  time_stop_hours=8,
                  cooldown_minutes=390,
                  loss_cooldown_hours=24)

    def prepare(self, rows, features, interval):
        sessions = {}
        order = []
        for i, row in enumerate(rows):
            open_ts = row.get("session_open_ts")
            session = row.get("session")
            if not open_ts or session is None:
                continue
            bag = sessions.get(session)
            if bag is None:
                bag = {"open_ts": int(open_ts), "high": None, "low": None,
                       "volume": 0.0, "complete": False, "signaled": False}
                sessions[session] = bag
                order.append(session)
            end = _end(row)
            if end <= bag["open_ts"] + RANGE_MS:
                high, low = row["high"], row["low"]
                bag["high"] = high if bag["high"] is None else max(bag["high"], high)
                bag["low"] = low if bag["low"] is None else min(bag["low"], low)
                bag["volume"] += float(row.get("volume") or 0)
                if end == bag["open_ts"] + RANGE_MS:
                    bag["complete"] = bag["high"] is not None and bag["low"] is not None
            elif not bag["complete"] and end > bag["open_ts"] + RANGE_MS:
                bag["complete"] = bag["high"] is not None and bag["low"] is not None
        prior = []
        rvol_by_session = {}
        for session in order:
            bag = sessions[session]
            avg = (sum(prior) / len(prior)) if prior else None
            rvol_by_session[session] = (bag["volume"] / avg) if avg and avg > 0 else None
            if bag["complete"]:
                prior.append(bag["volume"])
                if len(prior) > RVOL_LOOKBACK:
                    prior.pop(0)
        for i, (row, feat) in enumerate(zip(rows, features)):
            if feat is None:
                continue
            session = row.get("session")
            bag = sessions.get(session)
            if not bag or not bag["complete"] or _end(row) <= bag["open_ts"] + RANGE_MS:
                feat["orb"] = {"ready": False}
                continue
            rvol = rvol_by_session.get(session)
            first = (not bag["signaled"]) and feat.get("_close", 0) > bag["high"]
            if first:
                bag["signaled"] = True
            feat["orb"] = {
                "ready": True,
                "high": bag["high"],
                "low": bag["low"],
                "width": bag["high"] - bag["low"],
                "rvol": rvol,
                "first_break": first,
            }

    def signal(self, features, params):
        orb = features.get("orb") or {}
        if not orb.get("ready"):
            return None, "opening_range_not_ready"
        if orb.get("rvol") is None:
            return None, "relative_volume_not_ready"
        if orb["rvol"] < params.get("min_rvol", MIN_RVOL):
            return None, "low_relative_volume"
        if orb["width"] <= 0:
            return None, "zero_opening_range"
        if not orb.get("first_break"):
            return None, "no_first_orb_breakout"
        news = features.get("news")
        if news and news.get("ready") and news.get("score", 0) <= params.get("news_block", NEWS_BLOCK):
            return None, "negative_news_filter"
        return 70.0, None

    def levels(self, features, params):
        orb = features.get("orb") or {}
        if not orb.get("ready") or orb.get("width", 0) <= 0:
            return None
        close = float(features.get("_close", 0))
        stop = orb["low"]
        width = orb["width"]
        if stop <= 0 or close <= stop:
            return None
        t1 = close + width
        t2 = close + 2 * width
        return stop, t1, t2, 0.5
