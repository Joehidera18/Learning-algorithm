"""Declared, research-only VWAP reversion comparison on recorded 1m candles.

This is a transparent crypto adaptation, not the Reddit author's private code.
No outcome is fed into the learner and no profile can be installed here.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from collections import Counter, deque
from pathlib import Path

from .data import validate_history
from .execution import simulate
from .paper_store import load_state, save_state
from .research import ResearchManager, daily_goal_report

MINUTE = 60000
DAY = 86400000
VERSION = "vwap-proxy-research-v1"
PROTOCOL = {
    "version": VERSION, "direction": "LONG", "base_interval": "1m",
    "anchor": "UTC midnight", "warmup_minutes": 120,
    "bands": "volume-weighted HLC3 mean and population variance, separately on closed 1m/5m/30m bars",
    "profile": "48 HLC3-volume bins from the previous complete UTC day; three-bin smoothing",
    "profile_bins": 48, "node_tolerance_bins": 1.,
    "nodes": "local HVN >= 1.25 times mean or positive local LVN <= 0.75 times mean",
    "extension_sigma": 2., "extension_lookback_minutes": 30,
    "pivots": "strict low with two bars on each side; usable only after right-side bars close",
    "pivot_max_separation_minutes": 120,
    "delta": "session sum of signed 1m volume; sign from candle direction, flat bars inherit direction",
    "delta_normalization": "difference at two outside-band pivots / session CVD range known at confirmation",
    "minimum_delta_divergence": .10,
    "confirmation": "at a common 30m close, all three closed-bar band readings are inside +/-2 sigma",
    "stop_buffer_sigma": .10, "target1_fraction": .50,
    "targets": "signal-time 1m session VWAP and upper 1-sigma band, frozen through the trade",
    "trend_filter": "last 30m change in 1m VWAP / current sigma >= -0.25",
    "time_stop_hours": 4, "cooldown_minutes": 30,
    "weekday_exclusions": [], "cost_stress_multiplier": 1.5,
    "max_cost_r": .8, "min_net_rr": 1.,
    "windows": "first 70% of elapsed history and later 30%, split at UTC midnight; separately funded",
    "gaps": "no fabricated bars; session and prior-day profile must be complete; open account stops at a gap",
    "selection": "all four fixed variants reported; no winner selection, optimization or model promotion",
}
VARIANTS = (
    ("bands", "VWAP re-entry"),
    ("profile", "Re-entry + volume profile"),
    ("delta", "Profile + candle delta divergence"),
    ("trend", "Delta + trend filter"),
)


def source_hash():
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def validate_minute_rows(rows):
    if len(rows) < 3000:
        raise ValueError("VWAP research needs at least 3,000 recorded one-minute candles")
    previous = None
    now = int(time.time()*1000)
    for r in rows:
        values = [float(r[k]) for k in ("ts", "open", "high", "low", "close", "volume")]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Non-finite candle data")
        if min(values[1:5]) <= 0 or values[5] < 0:
            raise ValueError("Invalid candle prices or volume")
        ts = r["ts"]
        if ts != int(ts) or ts % MINUTE or ts+MINUTE > now:
            raise ValueError("Use completed UTC one-minute candles with millisecond timestamps")
        if previous is not None and (ts <= previous or (ts-previous) % MINUTE):
            raise ValueError("Candles must be chronological without duplicates")
        previous = ts
    # A sparse coarser series cannot masquerade as missing one-minute prices.
    if not any(b["ts"]-a["ts"] == MINUTE for a, b in zip(rows, rows[1:])):
        raise ValueError("Coarser candles cannot reconstruct this strategy's one-minute signals")
    quality = validate_history(rows, "1m")
    if not quality["valid"]:
        raise ValueError("Invalid OHLC ranges")
    return quality


class Moments:
    """Weighted Welford moments avoid subtracting nearly equal price squares."""
    def __init__(self):
        self.volume = self.mean = self.m2 = 0.

    def add(self, price, volume):
        if volume <= 0:
            return
        total = self.volume+volume
        change = price-self.mean
        self.mean += change*volume/total
        self.m2 += volume*change*(price-self.mean)
        self.volume = total

    @property
    def sigma(self):
        return math.sqrt(max(0., self.m2/self.volume)) if self.volume else 0.


def hlc3(row):
    return (row["high"]+row["low"]+row["close"])/3


def volume_nodes(rows):
    if len(rows) != 1440 or any(r["ts"] != rows[0]["ts"]+i*MINUTE for i, r in enumerate(rows)):
        return [], 0.
    low, high = min(r["low"] for r in rows), max(r["high"] for r in rows)
    width = (high-low)/PROTOCOL["profile_bins"]
    if width <= 0:
        return [], 0.
    bins = [0.]*PROTOCOL["profile_bins"]
    for r in rows:
        index = min(len(bins)-1, max(0, int((hlc3(r)-low)/width)))
        bins[index] += r["volume"]
    smooth = [sum(bins[max(0, i-1):i+2])/len(bins[max(0, i-1):i+2]) for i in range(len(bins))]
    mean = sum(smooth)/len(smooth)
    nodes = []
    for i in range(1, len(bins)-1):
        peak = smooth[i] > max(smooth[i-1], smooth[i+1]) and smooth[i] >= 1.25*mean
        valley = 0 < smooth[i] < min(smooth[i-1], smooth[i+1]) and smooth[i] <= .75*mean
        if peak or valley:
            nodes.append({"price": low+(i+.5)*width, "kind": "HVN" if peak else "LVN"})
    return nodes, width


def build_vwap_features(rows, cancelled=None):
    features = [None]*len(rows)
    counts = Counter()
    previous_day = None
    day_rows = []
    nodes, width = [], 0.
    for i, row in enumerate(rows):
        if cancelled and i % 1000 == 0 and cancelled():
            raise InterruptedError("VWAP research cancelled")
        day = row["ts"]//DAY
        if day != previous_day:
            nodes, width = volume_nodes(day_rows) if previous_day is not None and day == previous_day+1 else ([], 0.)
            previous_day, day_rows = day, []
            moments = {n: Moments() for n in (1, 5, 30)}
            buckets = {n: [] for n in (5, 30)}
            valid_session = row["ts"] % DAY == 0
            cvd = cvd_min = cvd_max = 0.
            last_sign = 1
            pivots, excursions, means, ranges = deque(maxlen=5), deque(), deque(maxlen=31), deque(maxlen=30)
            prior_pivot = divergence = None
        elif row["ts"]-day_rows[-1]["ts"] != MINUTE:
            valid_session = False
        previous_close = day_rows[-1]["close"] if day_rows else row["open"]
        direction = row["close"]-row["open"] or row["close"]-previous_close
        last_sign = (1 if direction > 0 else -1) if direction else last_sign
        cvd += last_sign*row["volume"]
        cvd_min, cvd_max = min(cvd_min, cvd), max(cvd_max, cvd)
        day_rows.append(row)
        moments[1].add(hlc3(row), row["volume"])
        for size in (5, 30):
            buckets[size].append(row)
            if (row["ts"]+MINUTE) % (size*MINUTE) == 0:
                group = buckets[size]
                if len(group) == size and group[-1]["ts"]-group[0]["ts"] == (size-1)*MINUTE:
                    price = (max(r["high"] for r in group)+min(r["low"] for r in group)+row["close"])/3
                    moments[size].add(price, sum(r["volume"] for r in group))
                buckets[size] = []
        m = moments[1]
        means.append(m.mean)
        ranges.append(max(row["high"]-row["low"], abs(row["high"]-previous_close), abs(row["low"]-previous_close)))
        warm = valid_session and len(day_rows) >= PROTOCOL["warmup_minutes"] and m.sigma > 0
        outside = warm and row["low"] < m.mean-2*m.sigma
        if outside:
            node = min(nodes, key=lambda n: abs(n["price"]-row["low"])) if nodes else None
            touch = node is not None and abs(node["price"]-row["low"]) <= width
            excursions.append({"ts": row["ts"], "low": row["low"], "node": node if touch else None})
        while excursions and row["ts"]-excursions[0]["ts"] >= 30*MINUTE:
            excursions.popleft()
        if divergence and (row["low"] < divergence["low"] or row["ts"]-divergence["ts"] >= 30*MINUTE):
            divergence = None
        pivots.append({"ts": row["ts"], "low": row["low"], "cvd": cvd, "outside": outside})
        if len(pivots) == 5:
            middle = pivots[2]
            if middle["outside"] and all(middle["low"] < p["low"] for j, p in enumerate(pivots) if j != 2):
                if (prior_pivot and middle["ts"]-prior_pivot["ts"] <= 120*MINUTE
                        and middle["low"] < prior_pivot["low"] and cvd_max > cvd_min):
                    strength = (middle["cvd"]-prior_pivot["cvd"])/(cvd_max-cvd_min)
                    if strength >= PROTOCOL["minimum_delta_divergence"]:
                        divergence = dict(middle, strength=strength, confirmed_ts=row["ts"]+MINUTE,
                                          prior_ts=prior_pivot["ts"])
                prior_pivot = dict(middle)
        if not warm or (row["ts"]+MINUTE) % (30*MINUTE) or (row["ts"]+MINUTE) % DAY == 0:
            continue
        inside = all(x.sigma > 0 and x.mean-2*x.sigma < row["close"] < x.mean+2*x.sigma for x in moments.values())
        reentry = bool(excursions) and inside and row["close"] < m.mean
        profile = any(e["node"] for e in excursions)
        slope = (m.mean-means[0])/m.sigma if len(means) == 31 else None
        feature = {"_close": row["close"], "_atr": sum(ranges)/len(ranges),
            "regime": "DOWN" if slope is not None and slope < -.25 else "CHOP",
            "reentry": reentry, "profile_touch": profile, "delta_divergence": bool(divergence),
            "trend_allowed": slope is not None and slope >= -.25,
            "vwap": m.mean, "sigma": m.sigma, "vwap_slope_sigma": slope,
            "delta_kind": "candle_direction_proxy", "divergence": divergence,
            "profile_day": day-1 if nodes else None,
            "profile_nodes_touched": [e["node"] for e in excursions if e["node"]],
            "stop": min(e["low"] for e in excursions)-.1*m.sigma if excursions else 0.,
            "target1": m.mean, "target2": m.mean+m.sigma,
            "known_at_ts": row["ts"]+MINUTE,
            "bands": {str(n): {"vwap": x.mean, "sigma": x.sigma} for n, x in moments.items()}}
        features[i] = feature
        counts["closed_30m_checks"] += 1
        for key, _ in VARIANTS:
            score, _ = evaluate_setup(feature, {"variant": key})
            counts[key] += score is not None
    return features, dict(counts)


def evaluate_setup(feature, params):
    if not feature["reentry"]:
        return None, "no_confirmed_vwap_reentry"
    variant = params["variant"]
    if variant != "bands" and not feature["profile_touch"]:
        return None, "no_previous_day_volume_node"
    if variant in ("delta", "trend") and not feature["delta_divergence"]:
        return None, "no_confirmed_delta_divergence"
    if variant == "trend" and not feature["trend_allowed"]:
        return None, "falling_vwap"
    return 1., None


def price_levels(feature):
    return feature["stop"], feature["target1"], feature["target2"], PROTOCOL["target1_fraction"]


def run_vwap_research(rows, symbol, settings, provenance=None, cancelled=None):
    quality = validate_minute_rows(rows)
    costs = {k: float(settings[k]) for k in ("fee_rate", "slippage_rate", "risk_per_trade", "max_notional_fraction", "daily_loss_limit")}
    bounds = {"fee_rate": (0, .02), "slippage_rate": (0, .01), "risk_per_trade": (.001, .02),
              "max_notional_fraction": (.05, 1), "daily_loss_limit": (.005, .10)}
    if any(not math.isfinite(v) or not bounds[k][0] <= v <= bounds[k][1] for k, v in costs.items()):
        raise ValueError("Invalid research costs or account limits")
    features, counts = build_vwap_features(rows, cancelled)
    split_ts = int((rows[0]["ts"]+.7*(rows[-1]["ts"]+MINUTE-rows[0]["ts"]))//DAY)*DAY
    split = next((i for i, r in enumerate(rows) if r["ts"] >= split_ts), len(rows))
    if split <= 240 or split >= len(rows)-30:
        raise ValueError("Not enough history for both chronological windows")
    results = []
    for variant, label in VARIANTS:
        params = {"family": "vwap_reversion_research", "variant": variant, "direction": "LONG",
            "stop_atr": 1., "rr2": 3., "max_gap_atr": .6,
            "max_cost_r": PROTOCOL["max_cost_r"], "min_net_rr": PROTOCOL["min_net_rr"],
            "time_stop_hours": PROTOCOL["time_stop_hours"], "cooldown_minutes": PROTOCOL["cooldown_minutes"],
            "max_notional_fraction": costs["max_notional_fraction"]}
        windows = {}
        # The later account's first possible entry is at the split, using the
        # immediately preceding closed signal. Neither account carries positions.
        for window, start, end in (("earlier", 240, split), ("later", split-1, len(rows))):
            accounts = {}
            for name, multiplier in (("standard", 1.), ("higher_cost", 1.5)):
                metrics, trades = simulate(rows, features, start, end, 500., costs["risk_per_trade"],
                    costs["fee_rate"]*multiplier, (costs["slippage_rate"]+.0005)*multiplier, params,
                    bar_interval_ms=MINUTE, daily_loss_limit=costs["daily_loss_limit"], cancelled=cancelled,
                    signal_evaluator=evaluate_setup, level_provider=price_levels)
                daily = daily_goal_report(trades, rows[start+1]["ts"], rows[end-1]["ts"]) if metrics["complete"] else None
                accounts[name] = {"metrics": metrics, "trades": trades, "daily": daily}
            windows[window] = {"start_ts": rows[start+1]["ts"], "end_ts": rows[end-1]["ts"]+MINUTE, **accounts}
        results.append({"variant": variant, "label": label, "windows": windows})
    identity = {"protocol": PROTOCOL, "source_hash": source_hash(), "symbol": symbol, "costs": costs,
        "data_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    return {**identity, "fingerprint": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
        "created_at": int(time.time()), "data_quality": quality, "signal_counts": counts,
        "market_data": provenance or {"provider": "Supplied OHLCV; authenticity not independently verified"},
        "assumed_half_spread": .0005, "results": results, "cash_benchmark_net": 0.,
        "validated": False, "eligible_for_trading": False, "learning_updates": 0,
        "scope": "Each window, market, variant and cost scenario has a separate $500 account. "
                 "Historical research only; no independent forward confirmation. No synthetic market fallback.",
        "limitations": ["Crypto adaptation, not an exact replication of private futures rules.",
            "Candle direction delta and HLC3 volume profile are approximations, not aggressor trades or resting orders.",
            "Fixed research thresholds were specified before this comparison; no optimizer or Wednesday exclusion.",
            "Stops take precedence over targets within ambiguous minute bars; partial exits pay fees.",
            "No automatic learning, qualification, profile replacement or real orders."]}


class VwapResearchManager(ResearchManager):
    def __init__(self, db_path, data_dir, client=None):
        super().__init__(db_path, Path(data_dir)/"vwap-research", client)
        self.state = load_state(db_path, "vwap_research", {"status": "idle", "message": "No VWAP comparison yet", "results": []})
        if self.state["status"] in ("running", "downloading", "testing"):
            self.state.update(status="interrupted", message="Interrupted; run again to reuse recorded candles")

    def _update(self, **patch):
        with self.lock:
            self.state.update(patch)
            save_state(self.db_path, "vwap_research", self.state)

    def status(self):
        with self.lock:
            result = json.loads(json.dumps(self.state, allow_nan=False))
        for report in result.get("results", []):
            for variant in report.get("results", []):
                for window in variant["windows"].values():
                    for name in ("standard", "higher_cost"):
                        window[name].pop("trades", None)
        return result

    def export(self):
        with self.lock:
            return json.loads(json.dumps(self.state, allow_nan=False))

    def start(self, symbols, days, settings):
        if not isinstance(symbols, list) or not 1 <= len(symbols) <= 3:
            raise ValueError("Choose one to three Coinbase USD markets")
        symbols = list(dict.fromkeys(str(s).upper().strip() for s in symbols))
        if any(not re.fullmatch(r"[A-Z0-9]{2,16}-USD", s) for s in symbols):
            raise ValueError("Use Coinbase USD markets such as BTC-USD")
        if isinstance(days, bool) or not isinstance(days, int) or not 7 <= days <= 180:
            raise ValueError("Choose 7–180 whole days of one-minute history")
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError("A VWAP comparison is already running")
            self.cancel_event.clear()
            cutoff = int(time.time()*1000)//MINUTE*MINUTE
            self._update(status="running", results=[], completed=0, total=len(symbols),
                message="Downloading recorded one-minute candles", protocol=PROTOCOL,
                requested_days=days, cutoff_ts=cutoff, settings=dict(settings))
            self.worker = threading.Thread(target=self._run_vwap, args=(symbols, days, dict(settings), cutoff),
                                           daemon=True, name="vwap-research")
            self.worker.start()

    def _run_vwap(self, symbols, days, settings, cutoff):
        results = []
        try:
            for symbol in symbols:
                try:
                    rows = self._history(symbol, "1m", days, end_ms=cutoff)
                    self._update(status="testing", message=f"Testing all four fixed variants for {symbol}")
                    result = run_vwap_research(rows, symbol, settings,
                        {"provider": "Coinbase Exchange", "interval": "1m", "requested_days": days,
                         "cutoff_ts": cutoff, "gap_repair": self.data_reports.get((symbol, "1m")),
                         "synthetic_fallback": False}, self.cancel_event.is_set)
                    save_state(self.db_path, "vwap_result_"+result["fingerprint"], result)
                except InterruptedError:
                    raise
                except Exception as exc:
                    result = {"symbol": symbol, "error": str(exc), "eligible_for_trading": False}
                results.append(result)
                self._update(results=results, completed=len(results))
            errors = sum("error" in r for r in results)
            self._update(status="error" if errors == len(results) else "partial" if errors else "complete",
                message=f"Finished {len(results)-errors}/{len(results)} markets; {errors} unavailable. Research only.")
        except InterruptedError:
            self._update(status="cancelled", message="Cancelled; completed reports and recorded candles retained")
