"""Measure saved entry forecasts against later net outcomes, without training twice.

An optimizer's residual at closure is not the forecast made at entry: other
outcomes can update the model while a trade is open. These records preserve the
earlier forecast. R means realized net dollars divided by initial dollar risk.
"""
import copy
import math

from .forecast_calibration import COSTS, forecast_band


def entry_snapshot(forecast, signal_close_ts, decision_ts=None):
    if not forecast:
        return None
    result = dict(forecast, signal_close_ts=int(signal_close_ts))
    if decision_ts is not None:
        result["forecast_ts"] = int(decision_ts)
    asof = result.get("forecast_ts", signal_close_ts)
    for key in ("estimated_net_r", "error_penalty_r", "conservative_net_r"):
        if not isinstance(result[key], (int, float)) or not math.isfinite(result[key]):
            raise ValueError("Non-finite entry forecast")
    if (not -3 <= result["estimated_net_r"] <= 3 or result["error_penalty_r"] < 0
            or not isinstance(result["samples"], int) or result["samples"] < 0
            or not isinstance(result["ready"], bool)
            or result["ready"] != (result["samples"] >= 30)
            or not math.isfinite(result["model_last_label_ts"])
            or not math.isfinite(signal_close_ts) or signal_close_ts < 0
            or not math.isfinite(asof) or asof < signal_close_ts
            or result["model_last_label_ts"] < 0):
        raise ValueError("Invalid entry forecast state")
    if result["model_last_label_ts"] > asof:
        raise ValueError("Entry forecast includes a future outcome")
    calibration_fields = {"raw_estimated_net_r", "calibration_adjustment_r", "calibration_key",
        "calibration_samples", "calibration_effective_samples", "calibration_ready", "calibration_last_label_ts",
        "trial_estimated_net_r", "calibration_applied"}
    if calibration_fields.intersection(result):
        if not calibration_fields.issubset(result):
            raise ValueError("Incomplete entry calibration record")
        raw, adjustment = result["raw_estimated_net_r"], result["calibration_adjustment_r"]
        n, effective = result["calibration_samples"], result["calibration_effective_samples"]
        if (any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in
                (raw,adjustment,effective,result["calibration_last_label_ts"],result["trial_estimated_net_r"]))
                or not -3 <= raw <= 3 or type(n) is not int or n < 0
                or not -3 <= result["trial_estimated_net_r"] <= 3
                or not 0 <= effective <= min(n,100)+1e-9
                or type(result["calibration_ready"]) is not bool
                or result["calibration_ready"] != (n >= 30 and effective >= 30)
                or (not result["calibration_ready"] and adjustment != 0)
                or type(result["calibration_applied"]) is not bool
                or not math.isclose(raw+adjustment,result["trial_estimated_net_r"],abs_tol=1e-10)
                or not math.isclose(result["trial_estimated_net_r"] if result["calibration_applied"] else raw,
                                    result["estimated_net_r"],abs_tol=1e-10)
                or result["calibration_key"] not in {c+"/"+forecast_band(raw) for c in COSTS}
                or not 0 <= result["calibration_last_label_ts"] <= result["model_last_label_ts"]):
            raise ValueError("Invalid entry calibration record")
    return result


def empty_totals():
    return {"samples":0, "sum_predicted_r":0., "sum_actual_r":0.,
            "sum_error_r":0., "sum_absolute_error_r":0., "sum_squared_error_r":0.,
            "sum_zero_squared_error_r":0., "positive_forecasts":0,
            "positive_forecasts_that_lost":0, "near_break_even":0}


def add(totals, predicted, actual):
    from .trade_review import BREAK_EVEN_R
    error = predicted-actual
    totals["samples"] += 1
    totals["sum_predicted_r"] += predicted
    totals["sum_actual_r"] += actual
    totals["sum_error_r"] += error
    totals["sum_absolute_error_r"] += abs(error)
    totals["sum_squared_error_r"] += error*error
    totals["sum_zero_squared_error_r"] += actual*actual
    totals["positive_forecasts"] += int(predicted > 0)
    totals["positive_forecasts_that_lost"] += int(predicted > 0 and actual < 0)
    totals["near_break_even"] += int(abs(actual) <= BREAK_EVEN_R+1e-12)


def metrics(totals):
    n = totals["samples"]
    return {"samples":n,
        "mean_predicted_net_r":totals["sum_predicted_r"]/n if n else None,
        "mean_actual_net_r":totals["sum_actual_r"]/n if n else None,
        "optimism_bias_r":totals["sum_error_r"]/n if n else None,
        "mae_r":totals["sum_absolute_error_r"]/n if n else None,
        "rmse_r":math.sqrt(totals["sum_squared_error_r"]/n) if n else None,
        "zero_forecast_rmse_r":math.sqrt(totals["sum_zero_squared_error_r"]/n) if n else None,
        **{k:totals[k] for k in ("positive_forecasts", "positive_forecasts_that_lost", "near_break_even")}}


class PredictionAudit:
    def __init__(self):
        self.totals = empty_totals()
        self.families, self.bands = {}, {}
        self.missing = self.untrained = self.end_marks = 0
        self.raw_totals, self.paired_totals = empty_totals(), empty_totals()
        self.raw_bands = {}
        self.adjusted = self.applied = 0
        self.lanes = {}

    def observe(self, trade, actual=None):
        if trade.get("reason") == "END":
            self.end_marks += 1
            return
        forecast = trade.get("entry_forecast")
        if not forecast:
            self.missing += 1
            return
        if not forecast["ready"]:
            self.untrained += 1
            return
        predicted = forecast["estimated_net_r"]
        if actual is None:
            actual = trade["pnl"]/trade["risk_dollars"]
        if not math.isfinite(predicted) or not math.isfinite(actual):
            raise ValueError("Non-finite prediction audit outcome")
        family = trade["strategy_family"]
        band = forecast_band(predicted)
        lane = trade.get("practice_lane")
        if lane is not None and lane not in ("eligible", "cost_blocked"):
            raise ValueError("Invalid practice lane in prediction audit")
        for totals in (self.totals, self.families.setdefault(family, empty_totals()),
                       self.bands.setdefault(band, empty_totals())):
            add(totals, predicted, actual)
        if lane is not None:
            add(self.lanes.setdefault(lane, empty_totals()), predicted, actual)
        if "raw_estimated_net_r" in forecast:
            raw = forecast["raw_estimated_net_r"]
            trial = forecast["trial_estimated_net_r"]
            add(self.raw_totals,raw,actual)
            add(self.paired_totals,trial,actual)
            pair = self.raw_bands.setdefault(forecast_band(raw),
                {"raw":empty_totals(),"corrected":empty_totals()})
            add(pair["raw"],raw,actual)
            add(pair["corrected"],trial,actual)
            self.adjusted += int(abs(trial-raw)>1e-12)
            self.applied += int(forecast["calibration_applied"] and abs(trial-raw)>1e-12)

    def summary(self):
        return copy.deepcopy({**metrics(self.totals),
            "missing_forecasts":self.missing, "untrained_forecasts":self.untrained,
            "excluded_end_marks":self.end_marks,
            "by_family":{k:metrics(v) for k,v in self.families.items()},
            "by_forecast_band":{k:metrics(v) for k,v in self.bands.items()},
            "by_practice_lane":{k:metrics(v) for k,v in self.lanes.items()},
            "calibration":{"paired_samples":self.raw_totals["samples"],
                "adjusted_forecasts":self.adjusted,
                "applied_forecasts":self.applied,
                "raw":metrics(self.raw_totals), "corrected":metrics(self.paired_totals),
                "by_raw_forecast_band":{k:{n:metrics(t) for n,t in pair.items()}
                    for k,pair in self.raw_bands.items()},
                "scope":"Raw and experimental corrected forecasts evaluated on the same entries, grouped by the raw "
                    "entry estimate. applied_forecasts reports actual use in decisions; the default policy only studies "
                    "these corrections. This measures forecast error, not profit from another trading policy."},
            "selection_uses_summary":False,
            "scope":"Forecasts saved before entry, scored after normal exits with full net returns. "
                "Positive bias means overprediction. Zero-return RMSE is a forecast benchmark, not a trading strategy. "
                "Warm-up forecasts, missing records, end marks and unresolved gap positions are not scored. "
                "Historical candidate examples overlap; these are descriptive errors, not independent confidence intervals."})


def summarize_predictions(trades):
    audit = PredictionAudit()
    for trade in trades:
        audit.observe(trade)
    return audit.summary()
