"""Cost-aware trade reviews. Descriptions and fixed counterfactuals are not alpha.

Only the close-time review may enter outcome memory. After-exit observations
are report-only, bounded by the supplied period, and never enter entry features.
"""
from bisect import bisect_left
from collections import Counter
import math

BREAK_EVEN_R = .10
OUTCOMES = {"near_break_even", "loss", "full_risk_loss", "profit", "end_mark"}
FINDINGS = {"fees_erased_gain", "gave_back_gains", "little_follow_through",
    "loss_exceeded_plan", "entry_bar_stop", "time_exit", "high_fee_burden",
    "against_daily_trend", "profitable_exit"}
REVIEW_FIELDS = ("best_net_r", "worst_net_r", "giveback_r", "holding_hours")
POST_EXIT_HOURS = (1, 4, 24)


def outcome_band(net_r, reason=""):
    if reason == "END":
        return "end_mark"
    if abs(net_r) <= BREAK_EVEN_R+1e-12:
        return "near_break_even"
    if net_r <= -1+1e-9:
        return "full_risk_loss"
    return "loss" if net_r < 0 else "profit"


def net_at_price(trade, raw):
    """Hypothetical liquidation at a raw market price; charge both fees once."""
    sign = 1 if trade.get("direction", "LONG") == "LONG" else -1
    fill = raw*(1-sign*trade["slippage_rate"])
    return ((fill-trade["entry"])*sign-(trade["entry"]+fill)*trade["fee_rate"])*trade["qty_initial"]


def close_review(trade):
    risk = float(trade.get("risk_dollars", 0))
    if risk <= 0 or not math.isfinite(risk):
        return None
    net_r = trade["pnl"]/risk
    if not math.isfinite(net_r):
        raise ValueError("Trade review requires a finite net return")
    reason = str(trade.get("reason", "UNKNOWN")).upper()
    result = {"outcome":outcome_band(net_r, reason), "net_r":net_r,
        "gross_r":trade["gross_pnl"]/risk, "fee_r":trade["fees_paid"]/risk,
        "holding_hours":max(0., (trade["exit_ts"]-trade["entry_ts"])/3600000),
        "best_net_r":None, "worst_net_r":None, "giveback_r":None,
        "findings":[], "path_basis":"unavailable"}
    if all(k in trade for k in ("mfe_price", "mae_price", "fee_rate", "slippage_rate", "qty_initial")):
        result["best_net_r"] = max(net_r, net_at_price(trade, trade["mfe_price"])/risk)
        result["worst_net_r"] = min(net_r, net_at_price(trade, trade["mae_price"])/risk)
        result["giveback_r"] = max(0., result["best_net_r"]-net_r)
        result["path_basis"] = trade.get("path_basis", "observed_OHLC_before_exit_with_stop_first_ordering")
    findings = result["findings"]
    if result["gross_r"] > 0 and net_r <= 0:
        findings.append("fees_erased_gain")
    if result["fee_r"] >= .25:
        findings.append("high_fee_burden")
    if result["best_net_r"] is not None:
        if result["best_net_r"] >= .5 and net_r <= BREAK_EVEN_R:
            findings.append("gave_back_gains")
        if result["best_net_r"] <= BREAK_EVEN_R and net_r < -BREAK_EVEN_R:
            findings.append("little_follow_through")
    if net_r < -1-1e-6:
        findings.append("loss_exceeded_plan")
    if "STOP" in reason and trade["entry_ts"] == trade["exit_ts"]:
        findings.append("entry_bar_stop")
    if reason in ("TIME", "TIMEOUT"):
        findings.append("time_exit")
    daily = trade.get("features", {}).get("daily") or {}
    if daily.get("ready") and daily.get("trend_down" if trade.get("direction", "LONG") == "LONG" else "trend_up"):
        findings.append("against_daily_trend")
    if net_r > BREAK_EVEN_R:
        findings.append("profitable_exit")
    # This affects review selection only, never the training reward or evidence count.
    result["review_priority"] = (3 if result["outcome"] in ("near_break_even", "full_risk_loss")
        else 2 if net_r < 0 else 1)+sum(f in findings for f in ("fees_erased_gain", "gave_back_gains", "loss_exceeded_plan"))
    return result


def validate_review(review, net_r):
    if not isinstance(review, dict) or review.get("outcome") not in OUTCOMES:
        raise ValueError("Invalid trade review outcome")
    if review["outcome"] != outcome_band(net_r) or not math.isclose(float(review.get("net_r", math.nan)), net_r, abs_tol=1e-9):
        raise ValueError("Review outcome must describe the actual net reward")
    normalized = {"outcome":review["outcome"], "net_r":net_r, "findings":list(review.get("findings", []))}
    if len(set(normalized["findings"])) != len(normalized["findings"]) or not set(normalized["findings"]).issubset(FINDINGS):
        raise ValueError("Invalid trade review findings")
    for key in REVIEW_FIELDS:
        value = review.get(key)
        if value is not None:
            value = float(value)
            if not math.isfinite(value) or (key in ("giveback_r", "holding_hours") and value < 0):
                raise ValueError("Invalid trade review measurement")
        normalized[key] = value
    best, worst, giveback = (normalized[k] for k in ("best_net_r","worst_net_r","giveback_r"))
    if ((best is not None and best < net_r-1e-9) or (worst is not None and worst > net_r+1e-9)
            or (giveback is not None and (best is None or not math.isclose(giveback,best-net_r,abs_tol=1e-9)))):
        raise ValueError("Trade review excursions do not reconcile with its net reward")
    return normalized


def _post_exit(rows, stamps, trade, step, end):
    start = bisect_left(stamps, trade["exit_ts"])+1
    close_ts = trade["exit_ts"]+step
    sign = 1 if trade.get("direction", "LONG") == "LONG" else -1
    raw_exit = trade["exit"]/(1-sign*trade["slippage_rate"])
    observations = []
    for hours in POST_EXIT_HOURS:
        needed = hours*3600000
        available = close_ts+needed
        item = {"hours":hours, "available_ts":available, "status":"pending"}
        stop = bisect_left(stamps, available, start, end)
        part = rows[start:stop]
        if needed % step:
            item["status"] = "unsupported_interval"
        elif end and rows[end-1]["ts"]+step >= available:
            if len(part) != needed//step or any(r["ts"] != close_ts+i*step for i,r in enumerate(part)):
                item["status"] = "missing_candles"
            else:
                favorable = max(r["high"] for r in part) if sign == 1 else min(r["low"] for r in part)
                adverse = min(r["low"] for r in part) if sign == 1 else max(r["high"] for r in part)
                item.update(status="complete", candles=len(part),
                    favorable_move_pct=100*sign*(favorable/raw_exit-1),
                    adverse_move_pct=100*sign*(adverse/raw_exit-1),
                    end_move_pct=100*sign*(part[-1]["close"]/raw_exit-1))
        observations.append(item)
    return {"basis":"Observed prices after the exit bar, relative to the raw exit price. No position, alternative profit or cause is implied.",
            "observations":observations}


def _break_even_stop(rows, stamps, trade, step, end):
    """Fixed report-only rule: after a close above +1 net R, protect net break-even.

    Activate on the NEXT candle. Stops win ambiguous bars. Never remove the
    original stop, widen risk, or extend beyond the actual exit.
    """
    a, b = bisect_left(stamps, trade["entry_ts"]), bisect_left(stamps, trade["exit_ts"])
    label = "Move stop to fee-covered break-even on the candle after a close at +1 net R; keep original target and exit deadline."
    if b >= end or a > b or any(rows[i]["ts"] != trade["entry_ts"]+(i-a)*step for i in range(a,b+1)):
        return {"rule":label, "status":"missing_candles"}
    sign = 1 if trade.get("direction", "LONG") == "LONG" else -1
    fee, slip = trade["fee_rate"], trade["slippage_rate"]
    be_price = trade["entry"]*(sign+fee)/(sign-fee)/(1-sign*slip)
    stop, target, active = trade.get("initial_stop", trade["stop"]), trade["target2"], False
    activated_ts = None
    raw, exit_ts, reason = None, None, None
    for i in range(a,b+1):
        r = rows[i]
        if (r["open"] <= stop if sign == 1 else r["open"] >= stop):
            raw, reason = r["open"], "STOP_GAP"
        elif (r["low"] <= stop if sign == 1 else r["high"] >= stop):
            raw, reason = stop, "BREAK_EVEN_STOP" if active else "STOP"
        elif (r["high"] >= target if sign == 1 else r["low"] <= target):
            raw, reason = target, "TARGET"
        if raw is not None:
            exit_ts = r["ts"]
            break
        if i < b and not active and net_at_price(trade, r["close"])/trade["risk_dollars"] >= 1:
            stop = max(stop, be_price) if sign == 1 else min(stop, be_price)
            active, activated_ts = True, r["ts"]+step
    net_r = net_at_price(trade, raw)/trade["risk_dollars"] if raw is not None else trade["pnl"]/trade["risk_dollars"]
    return {"rule":label, "status":"complete", "activated_ts":activated_ts,
        "net_r":net_r, "difference_r":net_r-trade["pnl"]/trade["risk_dollars"],
        "exit_ts":exit_ts or trade["exit_ts"], "reason":reason or trade["reason"],
        "available_ts":trade["exit_ts"]+step,
        "scope":"One fixed counterfactual, not a chosen strategy or additional training reward. A gap can still cause a loss."}


def detailed_case(rows, stamps, trade, step, end):
    f = trade.get("features", {})
    case = {k:trade[k] for k in ("entry_ts", "exit_ts", "entry", "exit", "strategy_family", "reason", "pnl",
        "risk_dollars", "gross_pnl", "fees_paid", "decision_params")}
    case.update(review=trade["review"], entry_context={k:f.get(k) for k in
        ("regime", "rsi", "volume_z", "adx", "momentum20", "momentum50", "range_position", "daily")},
        known_at_exit_ts=trade["exit_ts"]+step,
        post_exit=_post_exit(rows,stamps,trade,step,end),
        break_even_stop=_break_even_stop(rows,stamps,trade,step,end))
    return case


def summarize_trades(rows, trades, step, end, cases_per_group=3):
    counts, findings, families, groups = Counter(), Counter(), {}, {}
    reviewed, omitted = 0, 0
    for trade in trades:
        if trade.get("reason") == "END":
            continue
        review = trade.get("review")
        if not review:
            omitted += 1
            continue
        reviewed += 1
        outcome, family = review["outcome"], trade["strategy_family"]
        counts[outcome] += 1
        findings.update(review["findings"])
        group = families.setdefault(family, {"examples":0, "outcomes":{}, "findings":{}})
        group["examples"] += 1
        group["outcomes"][outcome] = group["outcomes"].get(outcome,0)+1
        for key in review["findings"]:
            group["findings"][key] = group["findings"].get(key,0)+1
        pool = groups.setdefault((family,outcome), [])
        pool.append(trade)
        pool.sort(key=lambda t:(t["review"]["review_priority"],t["exit_ts"]), reverse=True)
        del pool[cases_per_group:]
    stamps = [r["ts"] for r in rows]
    selected = [t for pool in groups.values() for t in pool]
    selected.sort(key=lambda t:(t["review"]["review_priority"],t["exit_ts"]), reverse=True)
    return {"examples":reviewed, "unavailable_reviews":omitted, "outcomes":dict(counts), "findings":dict(findings),
        "by_family":families, "cases":[detailed_case(rows,stamps,t,step,end) for t in selected],
        "cases_per_family_outcome":cases_per_group,
        "case_selection":"Higher diagnostic priority, then more recent, within each strategy family and outcome. Counts cover all reviewed examples; detailed cases are a bounded sample."}


def merge_summaries(summaries, cases_per_group=3):
    output = {"examples":0, "unavailable_reviews":0, "outcomes":{}, "findings":{}, "by_family":{}, "cases":[]}
    pools = {}
    for summary in summaries:
        for key in ("examples", "unavailable_reviews"):
            output[key] += summary.get(key,0)
        for key in ("outcomes", "findings"):
            for name,count in summary.get(key,{}).items():
                output[key][name] = output[key].get(name,0)+count
        for family,group in summary.get("by_family",{}).items():
            merged = output["by_family"].setdefault(family,{"examples":0,"outcomes":{},"findings":{}})
            merged["examples"] += group["examples"]
            for key in ("outcomes", "findings"):
                for name,count in group[key].items():
                    merged[key][name] = merged[key].get(name,0)+count
        for case in summary.get("cases",[]):
            pools.setdefault((case["strategy_family"],case["review"]["outcome"]),[]).append(case)
    for pool in pools.values():
        pool.sort(key=lambda c:(c["review"]["review_priority"],c["exit_ts"]),reverse=True)
        output["cases"].extend(pool[:cases_per_group])
    output["cases"].sort(key=lambda c:(c["review"]["review_priority"],c["exit_ts"]),reverse=True)
    output.update(cases_per_family_outcome=cases_per_group,
        case_selection="Higher diagnostic priority, then more recent, per family and outcome. Counts include every reviewed example; cases are a bounded sample.")
    return output
