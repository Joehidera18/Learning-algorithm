"""Causal, recency-weighted memory of comparable completed trade outcomes.

Buckets and a 50-observation half-life are fixed research hypotheses, not tuned
on the supplied test period. Scores are clipped for robustness; accounting sums
retain actual returns. Effective counts are ranking aids, not independent bets.
"""
import math
from .trade_review import BREAK_EVEN_R, FINDINGS, REVIEW_FIELDS, validate_review

DECAY = .5**(1/50)
MIN_CONTEXT_SAMPLES = 30
SHRINKAGE = 50
CAUSES = {"net_profit", "fee_erased_gain", "stopped_out", "stalled_trade", "other_loss", "flat", "near_break_even"}


def setup_context(vector):
    cost = vector[16]*2
    cost = "low" if cost <= .25 else ("moderate" if cost <= .5 else "high")
    regime = "BULL" if vector[10] else ("BEAR" if vector[11] else "CHOP")
    daily = ("unavailable" if vector[15] <= 0 else
             "up" if vector[13] > 0 and vector[14] > 0 else
             "down" if vector[13] < 0 and vector[14] < 0 else "mixed")
    return "/".join((cost, regime, daily))


def empty_memory():
    return {"samples":0, "weight":0., "weight_squared":0., "weighted_r":0.,
            "weighted_r2":0., "sum_net_r":0., "sum_gross_r":0., "sum_fee_r":0.,
            "cost_observations":0, "causes":{}, "last_label_ts":0,
            "review_samples":0, "review_findings":{}, "review_measurements":{}}


def trade_feedback(trade):
    """Compact attribution. Gross already includes slippage; subtract fees once."""
    detail = {"reason":trade.get("reason", trade.get("exit_reason", "UNKNOWN"))}
    risk = float(trade.get("risk_dollars", trade.get("risk_usd", 0)))
    if risk > 0 and "gross_pnl" in trade and "fees_paid" in trade:
        detail.update(gross_r=float(trade["gross_pnl"])/risk, fee_r=float(trade["fees_paid"])/risk)
    if trade.get("review"):
        detail["review"] = trade["review"]
    return detail


def validate_detail(result_r, detail):
    if not isinstance(detail, dict):
        raise ValueError("Outcome attribution must be an object")
    if ("gross_r" in detail) != ("fee_r" in detail):
        raise ValueError("Outcome attribution requires both gross return and fees")
    normalized = {"reason":str(detail.get("reason", "UNKNOWN"))}
    if "gross_r" in detail:
        gross, fee = float(detail["gross_r"]), float(detail["fee_r"])
        if not math.isfinite(gross) or not math.isfinite(fee) or fee < 0:
            raise ValueError("Invalid outcome costs")
        if not math.isclose(gross-fee, result_r, rel_tol=1e-6, abs_tol=1e-7):
            raise ValueError("Gross return minus fees must equal the learned net return")
        normalized.update(gross_r=gross, fee_r=fee)
    if detail.get("review") is not None:
        normalized["review"] = validate_review(detail["review"], result_r)
    return normalized


def update_memory(memory, result_r, available_ts, detail):
    target = max(-3., min(3., result_r))
    memory["samples"] += 1
    memory["weight"] = DECAY*memory["weight"]+1
    memory["weight_squared"] = DECAY**2*memory["weight_squared"]+1
    memory["weighted_r"] = DECAY*memory["weighted_r"]+target
    memory["weighted_r2"] = DECAY*memory["weighted_r2"]+target*target
    memory["sum_net_r"] += result_r
    memory["last_label_ts"] = int(available_ts)
    if "gross_r" in detail:
        memory["sum_gross_r"] += float(detail["gross_r"])
        memory["sum_fee_r"] += float(detail["fee_r"])
        memory["cost_observations"] += 1
    reason = str(detail.get("reason", "UNKNOWN")).upper()
    cause = ("near_break_even" if abs(result_r) <= BREAK_EVEN_R+1e-12 else
             "net_profit" if result_r > 0 else
             "fee_erased_gain" if detail.get("gross_r", 0) > 0 else
             "flat" if result_r == 0 else
             "stopped_out" if "STOP" in reason else
             "stalled_trade" if reason in ("TIME", "TIMEOUT") else "other_loss")
    memory["causes"][cause] = memory["causes"].get(cause, 0)+1
    review = detail.get("review")
    if review:
        memory["review_samples"] += 1
        for finding in review["findings"]:
            memory["review_findings"][finding] = memory["review_findings"].get(finding,0)+1
        for field in REVIEW_FIELDS:
            if review[field] is not None:
                values = memory["review_measurements"].setdefault(field,{"count":0,"sum":0.})
                values["count"] += 1
                values["sum"] += review[field]


def estimate(memory):
    if not memory or memory["samples"] < MIN_CONTEXT_SAMPLES:
        return None
    weight = memory["weight"]
    effective = min(100., weight*weight/max(memory["weight_squared"], 1e-12))
    if effective < MIN_CONTEXT_SAMPLES:
        return None
    mean = memory["weighted_r"]/weight
    variance = max(0., memory["weighted_r2"]/weight-mean*mean)
    return {"recent_net_r":mean, "effective_samples":effective,
            "penalty_r":math.sqrt(variance/max(1., effective-1))}


def validate_memory(memory):
    for key in empty_memory():
        if key == "causes":
            if not set(memory[key]).issubset(CAUSES):
                raise ValueError("Invalid outcome cause")
            if any(not isinstance(n, int) or n < 0 for n in memory[key].values()):
                raise ValueError("Invalid outcome counts")
        elif key in ("review_findings", "review_measurements"):
            continue
        elif not math.isfinite(float(memory[key])):
            raise ValueError("Non-finite outcome memory")
    if (not isinstance(memory["samples"],int) or memory["samples"] < 0
            or memory["weight"] < 0 or memory["weight_squared"] < 0
            or (memory["samples"] > 0 and min(memory["weight"],memory["weight_squared"]) <= 0)
            or memory["weighted_r2"] < 0 or not 0 <= memory["cost_observations"] <= memory["samples"]
            or memory["sum_fee_r"] < 0 or memory["last_label_ts"] < 0
            or sum(memory["causes"].values()) != memory["samples"]):
        raise ValueError("Invalid outcome memory counts")
    n = memory["review_samples"]
    if not isinstance(n,int) or not 0 <= n <= memory["samples"]:
        raise ValueError("Invalid reviewed outcome count")
    if (not set(memory["review_findings"]).issubset(FINDINGS) or
            any(not isinstance(v,int) or not 0 <= v <= n for v in memory["review_findings"].values())):
        raise ValueError("Invalid learned review findings")
    if not set(memory["review_measurements"]).issubset(REVIEW_FIELDS):
        raise ValueError("Invalid learned review measurement")
    for values in memory["review_measurements"].values():
        if (not isinstance(values["count"],int) or not 0 <= values["count"] <= n
                or not math.isfinite(values["sum"])):
            raise ValueError("Invalid learned review statistics")


def summarize(models):
    families = {}
    import json
    for key, model in models.items():
        family = json.loads(key)[0]
        memory = model.get("outcomes", empty_memory())
        row = families.setdefault(family, {"examples":0, "sum_net_r":0., "sum_gross_r":0.,
            "sum_fee_r":0., "cost_observations":0, "causes":{}, "learned_contexts":0,
            "review_samples":0, "review_findings":{}})
        row["examples"] += memory["samples"]
        for field in ("sum_net_r", "sum_gross_r", "sum_fee_r", "cost_observations"):
            row[field] += memory[field]
        for cause, count in memory["causes"].items():
            row["causes"][cause] = row["causes"].get(cause, 0)+count
        row["learned_contexts"] += sum(estimate(c) is not None for c in model.get("setup_contexts", {}).values())
        row["review_samples"] += memory["review_samples"]
        for finding,count in memory["review_findings"].items():
            row["review_findings"][finding] = row["review_findings"].get(finding,0)+count
    return {"by_family":families, "half_life_observations":50,
        "break_even_band_r":BREAK_EVEN_R,
        "context_rule":"Strategy, cost burden, intraday regime and completed daily trend.",
        "scope":"Completed candidate examples, including overlapping simulations; not account profits. "
                "Recent net outcomes affect selection. Exit causes describe outcomes, not proven causal explanations. "
                "Gross returns include slippage. Cost sums cover cost_observations only. "
                "Near-break-even outcomes retain their actual net reward. Reviewing an outcome does not count it again."}
