"""Pre-entry predictions of specific outcomes, scored only after normal closure.

These small logistic heads are measured research diagnostics, not entry filters
or calibrated probabilities. Unknown price paths do not become negative labels.
"""
import math

MIN_SAMPLES = 30
TARGETS = ("little_follow_through", "gave_back_gains", "fees_erased_gain",
           "near_break_even", "target_reached", "time_exit")
PATH_TARGETS = {"little_follow_through", "gave_back_gains"}


def labels(detail):
    review = detail.get("review")
    if not review:
        return {}
    findings = review["findings"]
    values = {"fees_erased_gain":int("fees_erased_gain" in findings),
        "near_break_even":int(review["outcome"] == "near_break_even"),
        "target_reached":int(str(detail.get("reason", "")).upper() in ("TARGET", "TARGET2")),
        "time_exit":int("time_exit" in findings)}
    if review.get("best_net_r") is not None:
        values.update({name:int(name in findings) for name in PATH_TARGETS})
    return values


def probability(head, vector):
    value = sum(w*x for w,x in zip(head["weights"], vector))
    return 1/(1+math.exp(-max(-30., min(30., value))))


def predict(heads, vector):
    return {name:{"estimate":probability(head, vector), "samples":head["samples"],
        "ready":head["samples"] >= MIN_SAMPLES,
        "prior_frequency":head["positives"]/head["samples"] if head["samples"] else .5}
        for name,head in heads.items()}


def validate_forecasts(forecasts):
    if not isinstance(forecasts, dict) or not set(forecasts).issubset(TARGETS):
        raise ValueError("Invalid failure forecasts")
    for item in forecasts.values():
        if (set(item) != {"estimate", "samples", "ready", "prior_frequency"}
                or type(item["samples"]) is not int or item["samples"] < 0
                or type(item["ready"]) is not bool or item["ready"] != (item["samples"] >= MIN_SAMPLES)
                or any(not isinstance(item[k], (int,float)) or not math.isfinite(item[k])
                       or not 0 <= item[k] <= 1 for k in ("estimate", "prior_frequency"))):
            raise ValueError("Invalid failure forecast values")


def update(heads, vector, detail):
    forecasts = detail.get("entry_forecast", {}).get("failure_predictions", {})
    for name,actual in labels(detail).items():
        head = heads.setdefault(name, {"weights":[0.]*len(vector), "samples":0, "positives":0,
            "scored":0, "brier_sum":0., "baseline_brier_sum":0.})
        earlier = forecasts.get(name)
        if earlier and earlier["ready"]:
            head["scored"] += 1
            head["brier_sum"] += (earlier["estimate"]-actual)**2
            head["baseline_brier_sum"] += (earlier["prior_frequency"]-actual)**2
        error = actual-probability(head, vector)
        rate = .15/math.sqrt(1+head["samples"]/500)
        norm = 1+sum(x*x for x in vector)
        head["weights"] = [max(-3., min(3., w*(1-rate*.0005)+rate*error*x/norm))
                           for w,x in zip(head["weights"], vector)]
        head["samples"] += 1
        head["positives"] += actual


def validate(heads, dimensions, maximum):
    if not isinstance(heads, dict) or not set(heads).issubset(TARGETS):
        raise ValueError("Invalid failure model targets")
    for head in heads.values():
        if (set(head) != {"weights", "samples", "positives", "scored", "brier_sum", "baseline_brier_sum"}
                or len(head["weights"]) != dimensions
                or any(type(head[k]) is not int for k in ("samples", "positives", "scored"))
                or not 0 <= head["positives"] <= head["samples"] <= maximum
                or not 0 <= head["scored"] <= head["samples"]
                or any(not math.isfinite(w) or abs(w)>3 for w in head["weights"])
                or any(not math.isfinite(head[k]) or not 0 <= head[k] <= head["scored"]+1e-9
                       for k in ("brier_sum", "baseline_brier_sum"))):
            raise ValueError("Invalid failure model state")


def summary(models):
    totals = {}
    for model in models.values():
        for name,head in model.get("eligible_model", {}).get("failure_models", {}).items():
            group = totals.setdefault(name, {k:0 for k in ("samples", "positives", "scored", "brier_sum", "baseline_brier_sum")})
            for key in group:
                group[key] += head[key]
    return {"targets":{name:{**g,
        "brier_score":g["brier_sum"]/g["scored"] if g["scored"] else None,
        "prior_frequency_brier":g["baseline_brier_sum"]/g["scored"] if g["scored"] else None}
        for name,g in totals.items()}, "selection_uses_predictions":False,
        "scope":"Predict specific failure patterns from entry features; train only on completed cost-eligible trades. "
            "Score the saved entry prediction against the later outcome and an entry-time historical-frequency baseline. "
            "Overlapping examples are not independent. These estimates are uncalibrated diagnostics, not trading filters."}
