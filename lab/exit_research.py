"""Summarize an independently trained exit experiment without publishing its model."""
from .exit_management import BREAK_EVEN_EXIT


def difference(left, right):
    if left.get("net_pnl") is None or right.get("net_pnl") is None:
        return None
    return left["net_pnl"]-right["net_pnl"]


def account_metrics(report, key):
    source = report[key]
    fields = ("complete", "trades", "net_pnl", "ending_balance", "return_pct", "win_rate",
              "profit_factor", "expectancy_r", "max_drawdown_pct", "gross_pnl", "fees_paid",
              "slippage_notional", "stopped_at_ts", "incomplete_reason", "signal_funnel", "regime_performance")
    return {k:source[k] for k in fields if k in source}


def comparison_report(baseline, experiment):
    """No model, approval flag, or hindsight selection crosses this boundary."""
    assert experiment["model"]["exit_policy"] == BREAK_EVEN_EXIT
    assert baseline["data_sha256"] == experiment["data_sha256"]
    assert baseline["daily_data"] == experiment["daily_data"]
    assert baseline.get("bitcoin_data") == experiment.get("bitcoin_data")
    assert baseline["cost_signature"] == experiment["cost_signature"]
    return {
        "rule":"After a candle closes at +1 net R, raise the stop to fee-covered break-even for the next candle; keep the target and time limit.",
        "exit_policy":BREAK_EVEN_EXIT,
        "selection_uses_comparison":False, "qualification_uses_comparison":False,
        "eligible_for_trading":False,
        "scope":"Independent experimental model with its own development labels, online feedback and account paths. "
                "Closed-candle activation, full fees and slippage, gap losses, risk limits and cooldowns apply. "
                "This comparison cannot replace the approved model or enable paper or Coinbase trades.",
        "historical_examples":experiment["historical_examples"],
        "candidate_count":experiment["candidate_count"],
        "pre_holdout_model_sha256":experiment["pre_holdout_model_sha256"],
        "training_label_end_ts":experiment["training_label_end_ts"],
        "holdout":account_metrics(experiment,"holdout"),
        "holdout_stressed":account_metrics(experiment,"holdout_stressed"),
        "net_pnl_difference":difference(experiment["holdout"],baseline["holdout"]),
        "stress_net_pnl_difference":difference(experiment["holdout_stressed"],baseline["holdout_stressed"]),
        "folds":experiment["folds"], "profitable_folds":experiment["profitable_folds"],
        "account_feedback_control":{
            "holdout":experiment["account_feedback_comparison"]["baseline"],
            "holdout_stressed":experiment["account_feedback_comparison"]["baseline_stressed"]},
        "holdout_learning_updates":experiment["holdout_learning_updates"],
        "holdout_expectancy_interval":experiment["holdout_expectancy_interval"],
        "evaluation":experiment["evaluation"],
        "research_checks_passed":experiment["validated"],
        "rejection_reasons":experiment["rejection_reasons"],
        "development_reviews":experiment["trade_reviews"]["development"],
        "selected_reviews":experiment["trade_reviews"]["selected"],
        "holdout_trades":experiment["holdout_trades"],
    }
