"""Causal, recency-weighted response of resolved returns to entry forecasts.

Each candidate learns from its cost-eligible outcomes only. A monotone affine
fit shares evidence across forecast bands; it cannot reverse the ranking. This
is a forecast hypothesis, not a probability or a confidence interval.
"""
import math

from .outcome_memory import DECAY, MIN_CONTEXT_SAMPLES, SHRINKAGE


def empty_response():
    return {"samples": 0, "weight": 0., "weight_squared": 0.,
            "x": 0., "y": 0., "xx": 0., "yy": 0., "xy": 0.,
            "last_label_ts": 0}


def update(response, base, actual, available_ts):
    response["samples"] += 1
    response["weight"] = DECAY * response["weight"] + 1
    response["weight_squared"] = DECAY**2 * response["weight_squared"] + 1
    for key, value in (("x", base), ("y", actual), ("xx", base*base),
                       ("yy", actual*actual), ("xy", base*actual)):
        response[key] = DECAY * response[key] + value
    response["last_label_ts"] = int(available_ts)


def estimate(response, base):
    n = response["samples"] if response else 0
    effective = min(100., response["weight"]**2 / response["weight_squared"]) if n else 0.
    ready = n >= MIN_CONTEXT_SAMPLES and effective >= MIN_CONTEXT_SAMPLES
    selected = base
    if ready:
        weight = response["weight"]
        mean_x, mean_y = response["x"]/weight, response["y"]/weight
        variance = max(0., response["xx"]/weight - mean_x**2)
        covariance = response["xy"]/weight - mean_x*mean_y
        # Fixed ridge toward slope one; shrink sparse fits toward the identity.
        ridge = 1/effective
        slope = max(0., min(1., (covariance+ridge)/(variance+ridge)))
        fitted = mean_y + slope*(base-mean_x)
        fraction = effective/(effective+SHRINKAGE)
        selected = max(-3., min(3., base + fraction*(fitted-base)))
    return {"base_estimated_net_r":base, "response_adjustment_r":selected-base,
            "response_samples":n, "response_effective_samples":effective,
            "response_ready":ready,
            "response_last_label_ts":response["last_label_ts"] if n else 0}


def validate(response, maximum_samples, last_label_ts):
    if response is None:
        return
    if not isinstance(response, dict) or set(response) != set(empty_response()):
        raise ValueError("Invalid forecast response state")
    r = response
    if (type(r["samples"]) is not int or not 0 < r["samples"] <= maximum_samples
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in r.values())
            or not 0 < r["weight_squared"] <= r["weight"] <= r["samples"]
            or not 0 <= r["last_label_ts"] <= last_label_ts
            or r["xx"] < 0 or r["yy"] < 0
            or r["x"]**2 > r["weight"]*r["xx"] + 1e-6
            or r["y"]**2 > r["weight"]*r["yy"] + 1e-6
            or r["xy"]**2 > r["xx"]*r["yy"] + 1e-6):
        raise ValueError("Invalid forecast response moments")
    vx = max(0., r["xx"] - r["x"]**2/r["weight"])
    vy = max(0., r["yy"] - r["y"]**2/r["weight"])
    cov = r["xy"] - r["x"]*r["y"]/r["weight"]
    if cov**2 > vx*vy + 1e-6*max(1., vx*vy):
        raise ValueError("Invalid forecast response covariance")


def summarize(models):
    responses = [m["forecast_response"] for m in models.values() if m.get("forecast_response")]
    return {"scored_outcomes":sum(r["samples"] for r in responses),
            "candidates":len(responses),
            "ready_candidates":sum(estimate(r,0.)["response_ready"] for r in responses),
            "minimum_samples":MIN_CONTEXT_SAMPLES, "half_life_observations":50,
            "shrinkage":SHRINKAGE, "slope_bounds":[0,1],
            "rule":"Per candidate, learn a recency-weighted monotone response from the saved base entry forecast to resolved net R. Cost-eligible examples only; 30 actual and effective observations required; shrink toward the original forecast. No hindsight entries or cross-coin pooling."}
