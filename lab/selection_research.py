"""One declared selection experiment; no model or trading eligibility is exported."""
from .exit_research import account_metrics, difference


def comparison_report(baseline, experiment):
    assert baseline["model"]["selection_rule"] == "recent_return_veto"
    assert experiment["model"]["selection_rule"] == "conditional_net_return"
    for key in ("data_sha256", "daily_data", "cost_signature", "training_diagnostics"):
        assert baseline[key] == experiment[key], key
    return {"rule":"Remove the blanket recent-return veto. Keep the same context-adjusted net estimate, error margin, sample minimum, costs and account risk checks.",
        "selection_uses_comparison":False, "qualification_uses_comparison":False,
        "eligible_for_trading":False,
        "scope":"Separate research account with its own choices and feedback. No automatic promotion, per-market winner selection or trading model is returned.",
        "historical_examples":experiment["historical_examples"],
        "holdout":account_metrics(experiment,"holdout"),
        "holdout_stressed":account_metrics(experiment,"holdout_stressed"),
        "net_pnl_difference":difference(experiment["holdout"],baseline["holdout"]),
        "stress_net_pnl_difference":difference(experiment["holdout_stressed"],baseline["holdout_stressed"]),
        "folds":experiment["folds"], "profitable_folds":experiment["profitable_folds"],
        "account_feedback_control":experiment["account_feedback_comparison"],
        "evaluation":experiment["evaluation"],
        "research_checks_passed":experiment["validated"],
        "rejection_reasons":experiment["rejection_reasons"],
        "prediction_audit":experiment["prediction_audit"],
        "holdout_trades":experiment["holdout_trades"]}
