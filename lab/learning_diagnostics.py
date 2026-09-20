"""Evidence coverage and immutable experiment identities, not strategy selectors."""
import hashlib
import json


def evidence_summary(models):
    families = {}
    for key,model in models.items():
        group = families.setdefault(json.loads(key)[0], {"examples":0, "eligible_examples":0,
            "cost_blocked_examples":0, "eligible_ready_candidates":0, "candidates":0})
        eligible = model.get("eligible_model", {}).get("samples", 0)
        group["examples"] += model["samples"]
        group["eligible_examples"] += eligible
        group["cost_blocked_examples"] += model["samples"]-eligible
        group["eligible_ready_candidates"] += eligible >= 30
        group["candidates"] += 1
    return {"by_family":families,
        "eligible_examples":sum(g["eligible_examples"] for g in families.values()),
        "cost_blocked_examples":sum(g["cost_blocked_examples"] for g in families.values()),
        "minimum_eligible_examples":30,
        "rule":"An affordable entry uses only completed cost-eligible evidence for its return estimate, recent outcomes and error margin. "
            "Sparse cost subgroups can borrow from eligible examples of the same candidate, never from cost-blocked practice. "
            "Examples overlap and do not count as independent bets."}


def regime_report(features, trades, start, end):
    groups = {name:{"candles":0, "trades":0, "net_pnl":0., "wins":0, "losses":0}
              for name in ("BULL", "BEAR", "CHOP", "UNKNOWN")}
    for f in features[start:end]:
        name = (f or {}).get("regime", "UNKNOWN")
        groups.get(name, groups["UNKNOWN"])["candles"] += 1
    for trade in trades:
        name = trade.get("regime") or trade.get("features", {}).get("regime", "UNKNOWN")
        group = groups.get(name, groups["UNKNOWN"])
        group["trades"] += 1
        group["net_pnl"] += trade["pnl"]
        group["wins"] += trade["pnl"] > 0
        group["losses"] += trade["pnl"] < 0
    return {"by_entry_regime":groups,
        "scope":"Candles describe the full test window; trades and net P&L use the regime known at entry. "
            "End marks are account valuations. No-trade regimes have no demonstrated trading edge."}


def experiment_manifest(report, exit_comparison, selection_comparison):
    variants = ["primary", "higher_cost", "frozen", "pooled_control", "pooled_control_higher_cost",
        "original_strategies", "original_strategies_higher_cost", "account_feedback",
        "account_feedback_higher_cost", "memory_disabled", "memory_disabled_higher_cost",
        "two_sided_forecast_diagnostic"]
    if exit_comparison:
        variants.append("fee_covered_break_even_exit")
    if selection_comparison:
        variants.append("conditional_entry_selection")
    if report.get("event_comparison"):
        variants.extend(["event_inputs_disabled", "event_inputs_disabled_higher_cost"])
    identity = {"hypothesis":"event-context-v1", "policy_version":report["policy_version"],
        "engine_version":report["engine_version"], "symbol":report["symbol"], "interval":report["interval"],
        "data_sha256":report["data_sha256"], "daily_sha256":report["daily_data"]["data_sha256"],
        "bitcoin_sha256":report["bitcoin_data"]["data_sha256"], "cost_signature":report["cost_signature"],
        "events_sha256":report.get("event_data",{}).get("data_sha256"),
        "reviewed_through_ts":report["evaluation"]["reviewed_through_ts"], "variants":variants,
        "forecast_correction":report["model"]["forecast_correction"]}
    return {**identity, "trial_id":hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
        "selection_uses_comparisons":False,
        "scope":"Record every declared variant in this run, including losing results. This is a reproducibility ledger, "
            "not a multiple-testing-adjusted significance claim. Repeated candles and overlapping strategies are not independent trials."}
