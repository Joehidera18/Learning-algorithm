"""Small online net-return models; scores are estimates, not win probabilities.

Fixed feature scales, bounded SGD updates, and JSON state keep training causal
and portable. No new dependencies or generated executable strategy code.
"""
from __future__ import annotations
import copy
import json
import math
import time

from .strategies import profit_candidates, simple_signal
from .paper_store import db_connect, load_state
from .trade_quality import signal_cost_check
from .outcome_memory import (setup_context, empty_memory, update_memory, validate_detail,
    validate_memory, estimate as context_estimate, SHRINKAGE)
from .exit_management import FIXED_EXIT, EXIT_POLICIES

POLICY_VERSION = "online-net-r-v8-exit-study"
MIN_SAMPLES = 30
MIN_ESTIMATED_R = .10
MIN_REGIME_SAMPLES = 15
REGIME_SHRINKAGE = 50
DIMENSIONS = 19


def bounded(value, lower=-1., upper=1.):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Learning inputs must be finite")
    return max(lower, min(upper, value))


def feature_vector(f, params=None, fee_rate=0., slippage_rate=0.):
    """Only entry-time features, normalized using fixed, predeclared scales."""
    daily = f.get("daily", {})
    quality = None
    if params is not None:
        quality, _ = signal_cost_check(f, params, fee_rate, slippage_rate)
        if quality is None:
            raise ValueError("Cannot learn from invalid entry economics")
    economics = [bounded(quality["cost_r"]/2, 0, 1),
                 bounded(quality["net_rr"]/3, -1, 1),
                 bounded(params.get("time_stop_hours", 12)/168, 0, 1)] if quality else [0., 0., 0.]
    return [1., bounded((f.get("rsi", 50)-50)/50),
        bounded(f.get("volume_z", 0)/3), bounded((f.get("adx", 25)-25)/25),
        bounded((f.get("atr_pct", .01)-.01)/.02),
        bounded(f.get("momentum20", 0)/.05), bounded(f.get("momentum50", 0)/.10),
        bounded(f.get("obv_slope", 0)*10), bounded(f.get("signed_volume_pressure", 0)*3),
        bounded(f.get("range_position", .5)*2-1),
        float(f.get("regime")=="BULL"), float(f.get("regime")=="BEAR"),
        bounded(f.get("range_expansion", 1)/3, 0, 1),
        bounded(daily.get("momentum7", 0)/.2),
        bounded(daily.get("ma_distance_atr", 0)/3),
        bounded(daily.get("atr_pct", 0)/.1, 0, 1)] + economics


def action_key(p):
    key = [p["family"], p["stop_atr"], p["rr2"], p["volume_z_min"]]
    if p.get("exit_policy", FIXED_EXIT) != FIXED_EXIT:
        key.append(p["exit_policy"])
    return json.dumps(key, separators=(",", ":"))


def vector_regime(vector):
    return "BULL" if vector[10] else ("BEAR" if vector[11] else "CHOP")


def empty_model():
    return {"weights":[0.]*DIMENSIONS, "samples":0, "wins":0, "sum_r":0.,
            "recent_r":0., "squared_error":0.}


def cost_context(vector):
    """Fixed buckets; do not let expensive exploration swamp feasible setups."""
    cost_r = vector[16]*2
    return "low" if cost_r <= .25 else ("moderate" if cost_r <= .5 else "high")


def update_model(model, vector, result_r):
    predicted = sum(w*x for w,x in zip(model["weights"],vector))
    target = bounded(result_r, -3, 3)
    rate = max(.025, .15/math.sqrt(1+model["samples"]/500))
    error = bounded(target-predicted, -3, 3)
    # Error measured BEFORE the outcome updates the weights. This is a ranking
    # penalty, not a calibrated confidence interval for dependent market samples.
    model["squared_error"] = model.get("squared_error", 0.) + error*error
    norm = 1 + sum(x*x for x in vector)
    model["weights"] = [bounded(w*(1-rate*.0005)+rate*error*x/norm, -3, 3)
                        for w,x in zip(model["weights"],vector)]
    model["recent_r"] += .03*(target-model["recent_r"])
    model["samples"] += 1
    model["wins"] += int(result_r > 0)
    model["sum_r"] += result_r


class AdaptivePolicy:
    def __init__(self, state=None, max_notional_fraction=.30, learn=True,
                 fee_rate=0., slippage_rate=0., regime_adaptation=True, cost_filter=True,
                 legacy_candidates_only=False, failure_adaptation=True, exit_policy=FIXED_EXIT):
        if exit_policy not in EXIT_POLICIES:
            raise ValueError("Unknown exit policy")
        if state is not None and state.get("exit_policy", FIXED_EXIT) != exit_policy:
            raise ValueError("Learning models with different exit policies cannot be mixed")
        self.exit_policy = exit_policy
        self.learn = learn
        self.legacy_candidates_only = legacy_candidates_only
        self.failure_adaptation = failure_adaptation
        self.fee_rate, self.slippage_rate = float(fee_rate), float(slippage_rate)
        if not (0 <= self.fee_rate <= .05 and 0 <= self.slippage_rate <= .05):
            raise ValueError("Invalid learning cost assumptions")
        self.regime_adaptation, self.cost_filter = regime_adaptation, cost_filter
        self.candidates = [dict(p, max_notional_fraction=max_notional_fraction) for p in profit_candidates()]
        if exit_policy != FIXED_EXIT:
            self.candidates = [dict(p, exit_policy=exit_policy) for p in self.candidates]
        if state is not None and state.get("version") != POLICY_VERSION:
            raise ValueError("This learning model needs to be retrained")
        self.state = copy.deepcopy(state) if state else {
            "version": POLICY_VERSION, "models": {}, "observations": 0, "last_label_ts": 0,
            "exit_policy":exit_policy}
        allowed = {action_key(p) for p in self.candidates}
        self._allowed_actions = frozenset(allowed)
        if not set(self.state["models"]).issubset(allowed):
            raise ValueError("Unknown strategy in learning model")
        for model in self.state["models"].values():
            if "outcomes" in model:
                validate_memory(model["outcomes"])
            for key, memory in model.get("setup_contexts", {}).items():
                parts = key.split("/")
                if (len(parts) != 3 or parts[0] not in ("low", "moderate", "high")
                        or parts[1] not in ("BULL", "BEAR", "CHOP")
                        or parts[2] not in ("up", "down", "mixed", "unavailable")):
                    raise ValueError("Invalid setup context")
                validate_memory(memory)
            costs = model.get("cost_contexts", {})
            if not set(costs).issubset({"low", "moderate", "high"}):
                raise ValueError("Invalid learning cost context")
            components = []
            for group in [model, *costs.values()]:
                regimes = group.get("regimes", {})
                if not set(regimes).issubset({"BULL", "BEAR", "CHOP"}):
                    raise ValueError("Invalid learning regime")
                components.extend([group, *regimes.values()])
            for component in components:
                if len(component["weights"]) != DIMENSIONS or component["samples"] < 0:
                    raise ValueError("Invalid learning model state")
                if component.get("squared_error", 0) < 0:
                    raise ValueError("Invalid learning error state")
                for value in component["weights"] + [component["recent_r"], component["sum_r"], component.get("squared_error", 0)]:
                    bounded(value, -1e12, 1e12)

    def export(self):
        return copy.deepcopy(self.state)

    def predict(self, params, vector):
        model = self.evidence(params, vector)
        if not model:
            return 0.
        pooled = sum(w*x for w,x in zip(model["weights"],vector))
        local = model.get("regimes", {}).get(vector_regime(vector)) if self.regime_adaptation else None
        if local and local["samples"] >= MIN_REGIME_SAMPLES:
            # Shrink sparse context estimates toward all-condition evidence.
            weight = local["samples"]/(local["samples"]+REGIME_SHRINKAGE)
            contextual = sum(w*x for w,x in zip(local["weights"],vector))
            pooled = (1-weight)*pooled+weight*contextual
        context = self.context_evidence(params, vector)
        if context:
            weight = context["effective_samples"]/(context["effective_samples"]+SHRINKAGE)
            pooled = (1-weight)*pooled+weight*context["recent_net_r"]
        return bounded(pooled, -3, 3)

    def context_evidence(self, params, vector):
        if not self.failure_adaptation:
            return None
        model = self.state["models"].get(action_key(params), {})
        return context_estimate(model.get("setup_contexts", {}).get(setup_context(vector)))

    def evidence(self, params, vector):
        model = self.state["models"].get(action_key(params))
        if model and self.cost_filter:
            context = model.get("cost_contexts", {}).get(cost_context(vector))
            if context and context["samples"] >= MIN_SAMPLES:
                return context
        return model

    def error_penalty(self, model):
        n = model["samples"]
        # Cap the effective sample count; overlapping history is not unlimited
        # independent evidence. Fixed before the new replay is examined.
        return math.sqrt(model.get("squared_error", 0)/max(1, n))/math.sqrt(max(1, min(n, 100)))

    def observe(self, params, vector, result_r, available_ts, outcome=None):
        if not self.learn:
            return
        if len(vector) != DIMENSIONS or any(not math.isfinite(float(v)) for v in vector):
            raise ValueError("Invalid entry feature vector")
        result_r = float(result_r)
        if not math.isfinite(result_r) or not math.isfinite(float(available_ts)):
            raise ValueError("Invalid resolved outcome")
        if available_ts < self.state["last_label_ts"]:
            raise ValueError("Outcomes must be learned in the order they become available")
        key = action_key(params)
        if key not in self._allowed_actions:
            raise ValueError("Unknown learning candidate")
        detail = outcome if outcome is not None else {}
        detail = validate_detail(result_r, detail)
        model = self.state["models"].setdefault(key, empty_model())
        update_memory(model.setdefault("outcomes", empty_memory()), result_r, available_ts, detail)
        memory = model.setdefault("setup_contexts", {}).setdefault(setup_context(vector), empty_memory())
        update_memory(memory, result_r, available_ts, detail)
        local = model.setdefault("regimes", {}).setdefault(vector_regime(vector), empty_model())
        update_model(model, vector, result_r)
        update_model(local, vector, result_r)
        context = model.setdefault("cost_contexts", {}).setdefault(cost_context(vector), empty_model())
        contextual_regime = context.setdefault("regimes", {}).setdefault(vector_regime(vector), empty_model())
        update_model(context, vector, result_r)
        update_model(contextual_regime, vector, result_r)
        # Multiple estimates of ONE outcome: do not double-count evidence.
        self.state["observations"] += 1
        self.state["last_label_ts"] = int(available_ts)

    def opportunities(self, f):
        result = []
        candidates = [p for p in self.candidates
                      if not self.legacy_candidates_only or p.get("atr_timeframe") != "daily"]
        # Counts are per candidate, not independent candles or trade outcomes.
        self.last_diagnostics = {"candidates_checked": len(candidates),
            "eligible_candidates": 0, "rejections": {}}
        def reject(reason):
            counts = self.last_diagnostics["rejections"]
            counts[reason] = counts.get(reason, 0) + 1
        for p in candidates:
            score, reason = simple_signal(f, p)
            if score is None:
                reject(reason or "no_setup")
                continue
            if self.cost_filter:
                _, reason = signal_cost_check(f, p, self.fee_rate, self.slippage_rate)
                if reason:
                    reject(reason)
                    continue
            vector = feature_vector(f, p, self.fee_rate, self.slippage_rate)
            model = self.evidence(p, vector)
            if not model or model["samples"] < MIN_SAMPLES:
                reject("insufficient_learning_samples")
                continue
            local = model.get("regimes", {}).get(vector_regime(vector)) if self.regime_adaptation else None
            recent = local if local and local["samples"] >= MIN_REGIME_SAMPLES else model
            context = self.context_evidence(p, vector)
            if context and context["recent_net_r"] <= 0:
                reject("recent_context_losses")
                continue
            if not context and recent["recent_r"] <= 0:
                reject("nonpositive_recent_return")
                continue
            estimate = self.predict(p, vector)
            if estimate < MIN_ESTIMATED_R:
                reject("low_estimated_return")
                continue
            penalty = self.error_penalty(model)
            if context:
                penalty = max(penalty, context["penalty_r"])
            conservative = estimate-penalty
            if conservative < MIN_ESTIMATED_R:
                reject("prediction_error_too_large")
                continue
            result.append({"params":p, "score":score, "raw_score":score,
                "adjusted_score":conservative, "estimated_net_r":estimate,
                "error_penalty_r":penalty, "conservative_net_r":conservative,
                "learned":{"samples":model["samples"], "expectancy_r":estimate,
                    "cost_context":cost_context(vector), "regime":vector_regime(vector),
                    "regime_samples":local["samples"] if local else 0},
                "outcome_context":{"key":setup_context(vector), **(context or {})},
                "learning":{"version":POLICY_VERSION, "vector":list(vector)}})
        self.last_diagnostics["eligible_candidates"] = len(result)
        return sorted(result, key=lambda x:x["conservative_net_r"], reverse=True)

    def choose(self, f):
        choices = self.opportunities(f)
        return choices[0] if choices else None


def profile_key(symbol):
    return "adaptive_profile_" + symbol


def read_in_transaction(con, key, default=None):
    row = con.execute("SELECT value_json FROM continuous_state WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def write_in_transaction(con, key, value):
    con.execute("""INSERT INTO continuous_state(key,value_json,updated_at) VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
        (key,json.dumps(value,allow_nan=False,separators=(",",":")),int(time.time())))


def approved_profile(db_path, symbol, settings):
    from .engine import ENGINE_VERSION
    from .research import cost_signature
    profile = load_state(db_path, profile_key(symbol))
    if not profile or profile.get("engine_version") != ENGINE_VERSION:
        return None
    if profile.get("cost_signature") != cost_signature(settings):
        return None
    if not 0 <= time.time()*1000-profile.get("data_end_ts", 0) <= 30*86400000:
        return None
    if profile.get("model", {}).get("version") != POLICY_VERSION:
        return None
    if profile.get("model", {}).get("exit_policy", FIXED_EXIT) != FIXED_EXIT:
        return None
    return profile


def current_policy(db_path, symbol, settings, channel="paper"):
    if channel not in ("paper", "coinbase"):
        raise ValueError("Unknown learning channel")
    profile = approved_profile(db_path, symbol, settings)
    if not profile:
        return None
    saved = load_state(db_path, "adaptive_"+channel+"_"+symbol, {})
    state = saved.get("model") if saved.get("fingerprint")==profile["fingerprint"] else profile["model"]
    try:
        return AdaptivePolicy(state, settings["max_notional_fraction"],
            fee_rate=settings["fee_rate"], slippage_rate=settings["slippage_rate"]+.0005)
    except (KeyError, TypeError, ValueError):
        return None


def record_outcome(con, symbol, channel, params, learning, result_r, closed_ms, outcome=None):
    """Caller atomically marks a journal trade CLOSED in this SAME transaction.

    Paper and real Coinbase outcomes never train each other's forward models.
    The journal transition is the deduplication gate, including after a crash.
    """
    if not learning or learning.get("version") != POLICY_VERSION:
        return False
    profile = read_in_transaction(con, profile_key(symbol))
    if (not profile or closed_ms < profile["data_end_ts"] or
            learning.get("cost_signature") != profile["cost_signature"]):
        return False
    key = "adaptive_"+channel+"_"+symbol
    saved = read_in_transaction(con, key, {})
    if saved.get("fingerprint") != profile["fingerprint"]:
        saved = {"fingerprint":profile["fingerprint"], "model":profile["model"],
                 "forward_trades":0, "forward_net_r":0.}
    policy = AdaptivePolicy(saved["model"], profile["cost_signature"]["max_notional_fraction"])
    # A late reconciliation is new information at reconciliation time.
    available = max(int(closed_ms), policy.state["last_label_ts"])
    policy.observe(params, learning["vector"], result_r, available, outcome=outcome)
    saved.update(model=policy.export(), forward_trades=saved["forward_trades"]+1,
                 forward_net_r=saved["forward_net_r"]+float(result_r))
    write_in_transaction(con, key, saved)
    return True
