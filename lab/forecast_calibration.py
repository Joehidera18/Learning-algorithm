"""Small causal corrections to net-return forecasts, never win probabilities.

Use only saved raw entry estimates and subsequently resolved net returns. Fixed
bands, minimum evidence and shrinkage are hypotheses, not fitted on test P&L.
Serial and overlapping examples do not justify confidence-interval claims.
"""
import math

from .outcome_memory import DECAY, MIN_CONTEXT_SAMPLES, SHRINKAGE

BANDS = ("nonpositive", "0_to_0.5R", "above_0.5R")
COSTS = ("low", "moderate", "high")


def forecast_band(raw):
    return BANDS[0] if raw <= 0 else BANDS[1] if raw <= .5 else BANDS[2]


def bucket_key(cost, raw):
    return cost + "/" + forecast_band(raw)


def empty_bucket():
    return {"samples":0, "weight":0., "weight_squared":0.,
            "weighted_residual":0., "weighted_residual_squared":0.,
            "last_label_ts":0}


def update_bucket(bucket, raw, actual, available_ts):
    # A correction is learned against the ORIGINAL prediction. Learning the
    # residual of an already corrected estimate would repeatedly undo the fix.
    residual = actual-raw
    bucket["samples"] += 1
    bucket["weight"] = DECAY*bucket["weight"]+1
    bucket["weight_squared"] = DECAY**2*bucket["weight_squared"]+1
    bucket["weighted_residual"] = DECAY*bucket["weighted_residual"]+residual
    bucket["weighted_residual_squared"] = DECAY*bucket["weighted_residual_squared"]+residual**2
    bucket["last_label_ts"] = int(available_ts)


def correction(bucket):
    if not bucket:
        return {"samples":0, "effective_samples":0., "ready":False,
                "adjustment_r":0., "shrunk_adjustment_r":0., "last_label_ts":0}
    n, weight = bucket["samples"], bucket["weight"]
    effective = min(100., weight**2/max(bucket["weight_squared"],1e-12))
    ready = n >= MIN_CONTEXT_SAMPLES and effective >= MIN_CONTEXT_SAMPLES
    shrunk = bucket["weighted_residual"]/weight * effective/(effective+SHRINKAGE)
    return {"samples":n, "effective_samples":effective, "ready":ready,
            "adjustment_r":shrunk if ready else 0., "shrunk_adjustment_r":shrunk,
            "last_label_ts":bucket["last_label_ts"]}


def validate_buckets(buckets, maximum_samples, last_label_ts):
    if not isinstance(buckets, dict):
        raise ValueError("Invalid forecast calibration buckets")
    total = 0
    for key, b in buckets.items():
        if key not in {c+"/"+band for c in COSTS for band in BANDS}:
            raise ValueError("Unknown forecast calibration bucket")
        if not isinstance(b, dict) or set(b) != set(empty_bucket()):
            raise ValueError("Invalid forecast calibration state")
        if (type(b["samples"]) is not int or not 0 < b["samples"] <= maximum_samples
                or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in b.values())
                or not 0 < b["weight"] <= b["samples"]
                or not 0 < b["weight_squared"] <= b["weight"]
                or b["weighted_residual_squared"] < 0
                or not 0 <= b["last_label_ts"] <= last_label_ts
                or b["weighted_residual"]**2 > b["weight"]*b["weighted_residual_squared"]+1e-6):
            raise ValueError("Invalid forecast calibration moments")
        total += b["samples"]
    if total > maximum_samples:
        raise ValueError("Calibration outcomes cannot be counted twice")


def summarize(models):
    buckets = [b for model in models.values() for b in model.get("forecast_bands",{}).values()]
    return {"scored_outcomes":sum(b["samples"] for b in buckets),
            "buckets":len(buckets), "ready_buckets":sum(correction(b)["ready"] for b in buckets),
            "minimum_samples":MIN_CONTEXT_SAMPLES, "half_life_observations":50,
            "shrinkage":SHRINKAGE,
            "rule":"Match strategy parameters, cost burden and raw forecast band. "
                "The normal policy can lower a positive eligible forecast from the first resolved matching "
                "example, shrinking by effective samples / (effective samples + 50). Sparse corrections "
                "are marked provisional; readiness still requires 30 observations and 30 effective samples. "
                "Only the separate research policy can raise estimates, after that readiness minimum. "
                "Raw forecasts are stored before entry; unresolved trades never train the correction. "
                "Final estimates remain bounded and existing cost, error and risk checks still apply."}
