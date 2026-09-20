"""Learn from earlier resolved examples; test an updating policy on later prices."""
from __future__ import annotations
import math
import hashlib
import json
import time
from bisect import bisect_left

from .adaptive import AdaptivePolicy, POLICY_VERSION, FEATURE_NAMES
from .engine import ENGINE_VERSION, build_feature_cache
from .execution import simulate
from .research import cost_signature, bootstrap_interval, daily_goal_report
from .data import INTERVAL_MS
from .learning_data import prepare_learning_history, FEATURE_WARMUP
from .shadow_learning import HistoricalFeedback
from .evaluation import reviewed_boundary, attribution, dataset_digest
from .outcome_memory import trade_feedback, summarize as summarize_outcomes
from .trade_review import summarize_trades, merge_summaries, BREAK_EVEN_R, POST_EXIT_HOURS
from .exit_management import FIXED_EXIT, BREAK_EVEN_EXIT
from .prediction_audit import summarize_predictions
from .chronological_learning import ChronologicalTrainer
from .forecast_calibration import summarize as summarize_calibration
from .practice import PRACTICE_LANES, merge_counts, outcome_totals
from .market_context import attach_market_context, data_summary as bitcoin_summary
from .learning_diagnostics import evidence_summary, regime_report, experiment_manifest
from .failure_predictions import summary as failure_prediction_summary

from .event_context import (attach_event_context, data_summary as event_summary,
    validate_snapshot, outcome_summary as event_outcomes)

LEARNING_REPORT_VERSION = 20


def build_learning_features(rows, interval, segments, cancelled=None, daily_rows=None, bitcoin_rows=None,
                            event_snapshot=None, symbol="*"):
    """Keep chronology and restart all indicators at every missing-data boundary."""
    features = [None]*len(rows)
    for segment in segments:
        if cancelled and cancelled():
            raise InterruptedError("Learning cancelled")
        start, end = segment["start_index"], segment["end_index"]
        if end-start > FEATURE_WARMUP:
            cache = build_feature_cache(rows[start:end], interval, simple_only=True,
                                        daily_rows=daily_rows)["features"]
            features[start+FEATURE_WARMUP:end] = cache[FEATURE_WARMUP:]
    if bitcoin_rows is not None:
        features = attach_market_context(rows, features, INTERVAL_MS[interval], bitcoin_rows, in_place=True)
    if event_snapshot is not None:
        features = attach_event_context(rows, features, INTERVAL_MS[interval], event_snapshot, symbol)
    return features


def learn_history(rows, symbol, settings, progress=None, cancelled=None, checkpoint=None,
                  reviewed_through_ts=None, daily_rows=None, exit_comparison=True,
                  selection_comparison=True, forecast_correction=False, bitcoin_rows=None,
                  event_snapshot=None, event_comparison=True):
    """Keep the approved model separate from one independently trained experiment."""
    result = _learn_history(rows, symbol, settings, progress, cancelled, checkpoint,
        reviewed_through_ts, daily_rows, exit_policy=FIXED_EXIT, forecast_correction=forecast_correction, bitcoin_rows=bitcoin_rows, event_snapshot=event_snapshot)
    if exit_comparison:
        def experimental_progress(**state):
            if progress:
                state["message"] = "Break-even exit study: " + state.get("message", "")
                progress(**state)
        experiment_checkpoint = None
        if checkpoint:
            offset = result["candidate_count"]
            experiment_checkpoint = {
                "load":lambda index:checkpoint["load"](offset+index),
                "save":lambda index,value:checkpoint["save"](offset+index,value)}
        experiment = _learn_history(rows, symbol, settings, experimental_progress, cancelled,
            experiment_checkpoint, reviewed_through_ts, daily_rows, exit_policy=BREAK_EVEN_EXIT,
            forecast_correction=forecast_correction, bitcoin_rows=bitcoin_rows, event_snapshot=event_snapshot)
        from .exit_research import comparison_report
        result["exit_policy_comparison"] = comparison_report(result, experiment)
    if selection_comparison:
        def conditional_progress(**state):
            if progress:
                state["message"] = "Conditional selection study: " + state.get("message", "")
                progress(**state)
        # Both selection rules use identical fixed-exit development labels.
        # Existing checkpoints can be reused without another candidate namespace.
        experiment = _learn_history(rows, symbol, settings, conditional_progress, cancelled,
            checkpoint, reviewed_through_ts, daily_rows, recent_return_veto=False,
            forecast_correction=forecast_correction, bitcoin_rows=bitcoin_rows, event_snapshot=event_snapshot)
        from .selection_research import comparison_report
        result["selection_policy_comparison"] = comparison_report(result, experiment)
    if event_comparison and result["event_data"].get("covered_candles",0):
        control = _learn_history(rows, symbol, settings, progress, cancelled, None,
            reviewed_through_ts, daily_rows, forecast_correction=forecast_correction, bitcoin_rows=bitcoin_rows)
        result["event_comparison"] = {
            "price_context_only":{key:control[key] for key in ("holdout","holdout_stressed","validated")},
            "net_pnl_difference":result["holdout"]["net_pnl"]-control["holdout"]["net_pnl"],
            "stress_net_pnl_difference":result["holdout_stressed"]["net_pnl"]-control["holdout_stressed"]["net_pnl"],
            "selection_uses_comparison":False,
            "scope":"Independently train without event inputs on the same candles, costs and boundaries. "
                    "This comparison is research, not a promotion rule or proof of causation."}
    result["event_snapshot"] = event_snapshot
    result["experiment_registry"] = experiment_manifest(result, exit_comparison, selection_comparison)
    return result


def _learn_history(rows, symbol, settings, progress=None, cancelled=None, checkpoint=None,
                   reviewed_through_ts=None, daily_rows=None, exit_policy=FIXED_EXIT,
                   recent_return_veto=True, forecast_correction=False, bitcoin_rows=None, event_snapshot=None):
    progress = progress or (lambda **kwargs:None)
    cancelled = cancelled or (lambda:False)
    interval = settings["decision_interval"]
    if cancelled():
        raise InterruptedError("Learning cancelled")
    rows, quality, coverage = prepare_learning_history(rows, interval)
    step = INTERVAL_MS[interval]
    purge = math.ceil(24*3600000/step)
    holdout_start = int(len(rows)*.80)
    development = holdout_start-purge
    # Context inputs are snapshotted and hashed, including when supplied by CSV.
    # Future daily rows are not retained in the research artifact.
    if daily_rows is not None:
        from .daily_context import independent_daily_context, DAY_MS
        independent_daily_context([], step, daily_rows)
        daily_rows = [r for r in daily_rows if r["ts"]+DAY_MS <= rows[-1]["ts"]+step]
    if bitcoin_rows is not None:
        from .daily_context import independent_daily_context, DAY_MS
        independent_daily_context([], step, bitcoin_rows)
        bitcoin_rows = [r for r in bitcoin_rows if r["ts"]+DAY_MS <= rows[-1]["ts"]+step]
    if event_snapshot is not None:
        validate_snapshot(event_snapshot)
    features = build_learning_features(rows, interval, coverage["segments"], cancelled, daily_rows, bitcoin_rows, event_snapshot, symbol)
    event_required = event_snapshot is not None  # Fixed mode, never chosen using future events.
    fee, slip = settings["fee_rate"], settings["slippage_rate"]+.0005
    candidates = AdaptivePolicy(max_notional_fraction=settings["max_notional_fraction"],
                                exit_policy=exit_policy, recent_return_veto=recent_return_veto,
                                forecast_correction=forecast_correction).candidates
    examples = []
    training_candidates = []
    training_reviews = []
    training_totals = {"candles_checked":0, "features_available":0,
        "qualified_setups":0, "entry_attempts":0, "entries_opened":0, "rejections":{},
        "entry_rejections":{}, "exploratory_entries":0, "training_cost_overrides":{},
        "gap_censored_examples":0, "loss_pause_overrides":0}
    # These independently funded hypothetical examples are training labels, not
    # a multi-strategy portfolio. The actual policy tests use one $500 account.
    for index, params in enumerate(candidates):
        if cancelled():
            raise InterruptedError("Learning cancelled")
        progress(phase="learning", message=f"{symbol}: studying setup {index+1}/{len(candidates)}")
        saved = checkpoint["load"](index) if checkpoint else None
        if saved is None:
            labels, reviews, funnel, lanes = [], [], {}, {}
            for lane in PRACTICE_LANES:
                metrics, trades = simulate(rows, features, 240, development, 500,
                    settings["risk_per_trade"], fee, slip, params,
                    cancelled=cancelled, training_examples=True, bar_interval_ms=step,
                    practice_cost_mode=lane)
                labels.extend((trade["exit_ts"]+step, index, trade["training_vector"],
                    trade["r_multiple"], trade_feedback(trade), trade["entry_ts"])
                    for trade in trades if trade["reason"] != "END")
                lanes[lane] = {**outcome_totals(trades), "signal_funnel":metrics.get("signal_funnel", {})}
                merge_counts(funnel, metrics.get("signal_funnel", {}))
                reviews.append(summarize_trades(rows,trades,step,development))
            saved = {"labels":labels, "diagnostics":{"params":dict(params),
                "resolved_examples":len(labels), "signal_funnel":funnel, "by_practice_lane":lanes},
                "trade_reviews":merge_summaries(reviews)}
            if checkpoint:
                checkpoint["save"](index, saved)
            del trades
        training_candidates.append(saved["diagnostics"])
        training_reviews.append(saved.get("trade_reviews",{}))
        funnel = saved["diagnostics"]["signal_funnel"]
        examples.extend(saved["labels"])
        for key in training_totals:
            if isinstance(training_totals[key], dict):
                for reason, count in funnel.get(key, {}).items():
                    counts = training_totals[key]
                    counts[reason] = counts.get(reason, 0)+count
            else:
                training_totals[key] += funnel.get(key, 0)
    examples.sort(key=lambda x:(x[0],x[1]))
    seed = AdaptivePolicy(max_notional_fraction=settings["max_notional_fraction"], exit_policy=exit_policy,
                          recent_return_veto=recent_return_veto, fee_rate=fee, slippage_rate=slip,
                          forecast_correction=forecast_correction, market_context_required=bool(bitcoin_rows),
                          event_context_enabled=event_required)
    trainer = ChronologicalTrainer(seed,candidates,examples,cancelled)

    def train_until(cut_ts):
        return trainer.advance(cut_ts)

    def test(initial, start, end, stress=1, learn=True, baseline=False, legacy=False, shadow=True,
             failure_adaptation=True, practice_start=None, retain_model=False, retain_start=False):
        policy = AdaptivePolicy(initial, settings["max_notional_fraction"], learn=learn,
            fee_rate=fee*stress, slippage_rate=slip*stress,
            regime_adaptation=not baseline, cost_filter=not baseline,
            legacy_candidates_only=legacy, failure_adaptation=failure_adaptation and not baseline,
            exit_policy=exit_policy, recent_return_veto=recent_return_veto,
            forecast_correction=forecast_correction)
        feedback = (HistoricalFeedback(rows, features,
                    start if practice_start is None else practice_start, end, settings, policy, step, cancelled)
                    if learn and shadow else None)
        if practice_start is not None:
            if feedback is None or not 240 <= practice_start <= start:
                raise ValueError("Confirmation requires an earlier continuous practice stream")
            # Warm up the SAME stream that will continue after the boundary.
            # Truncating a prefix would END-mark and discard pending outcomes.
            feedback.begin_reporting(rows[start]["ts"])
        starting_observations = policy.state["observations"]
        starting_state = policy.export() if retain_start else None
        metrics, trades = simulate(rows, features, start, end, 500,
            settings["risk_per_trade"], fee*stress, slip*stress,
            {"family":"adaptive_policy", "direction":"LONG"},
            policy=policy, cancelled=cancelled, daily_loss_limit=settings["daily_loss_limit"],
            bar_interval_ms=step, feedback=feedback)
        metrics["feedback"] = feedback.summary() if feedback else {
            "mode":"selected_account_trades" if learn else "frozen",
            "resolved_examples":policy.state["observations"]-starting_observations}
        metrics["prediction_audit"] = summarize_predictions(trades)
        metrics["regime_performance"] = regime_report(features, trades, start, end)
        metrics["event_performance"] = event_outcomes(trades)
        return metrics, trades, policy.export() if retain_model else None, starting_state

    starts = [int(development*f) for f in (.45,.63,.81)]
    ends = starts[1:]+[development]
    folds = []
    for index,(start,end) in enumerate(zip(starts,ends),1):
        initial = train_until(rows[start-purge]["ts"])
        progress(phase="testing", message=f"{symbol}: checking later period {index}/3")
        metrics, _, _, _ = test(initial,start,end)
        folds.append({"fold":index, "training_labels":initial["observations"],
            "training_label_end_ts":initial["last_label_ts"], "test_start_ts":rows[start]["ts"],
            "test_end_ts":rows[end-1]["ts"]+step,
            "development_prediction_audit":trainer.predictions.summary(), "metrics":metrics})

    initial = train_until(rows[development]["ts"])
    progress(phase="testing", message=f"{symbol}: checking the later period and higher costs")
    holdout, trades, trained, _ = test(initial,holdout_start,len(rows),retain_model=True)
    stressed, _, _, _ = test(initial,holdout_start,len(rows),stress=1.5)
    frozen, _, _, _ = test(initial,holdout_start,len(rows),learn=False)
    baseline, _, _, _ = test(initial,holdout_start,len(rows),baseline=True)
    baseline_stressed, _, _, _ = test(initial,holdout_start,len(rows),stress=1.5,baseline=True)
    # A diagnostic, never a second chance to choose a winning holdout policy.
    legacy, _, _, _ = test(initial,holdout_start,len(rows),legacy=True)
    legacy_stressed, _, _, _ = test(initial,holdout_start,len(rows),stress=1.5,legacy=True)
    account_only, _, _, _ = test(initial,holdout_start,len(rows),shadow=False)
    account_only_stressed, _, _, _ = test(initial,holdout_start,len(rows),stress=1.5,shadow=False)
    # Declared ablation: same observations and candidates, memory adjustment off.
    # Its performance is reported; it cannot select or qualify another policy.
    no_memory, _, _, _ = test(initial,holdout_start,len(rows),failure_adaptation=False)
    no_memory_stressed, _, _, _ = test(initial,holdout_start,len(rows),stress=1.5,failure_adaptation=False)
    # This release was designed after the supplied report was reviewed. Reusing
    # its test window is useful research, but cannot provide fresh qualification.
    boundary = reviewed_boundary(symbol, reviewed_through_ts)
    fresh_start = max(holdout_start, bisect_left([r["ts"] for r in rows], boundary))
    reused = rows[holdout_start]["ts"] < boundary
    confirmation = None
    if reused and fresh_start < len(rows)-1:
        progress(phase="testing", message=f"{symbol}: checking prices after the reviewed report")
        fresh, fresh_trades, _, confirmation_initial = test(initial,fresh_start,len(rows),
            practice_start=holdout_start,retain_start=True)
        fresh_stress, _, _, stressed_initial = test(initial,fresh_start,len(rows),stress=1.5,
            practice_start=holdout_start,retain_start=True)
        fresh_account, _, _, _ = test(confirmation_initial,fresh_start,len(rows),shadow=False)
        fresh_account_stress, _, _, _ = test(stressed_initial,fresh_start,len(rows),stress=1.5,shadow=False)
        confirmation = {"start_ts":rows[fresh_start]["ts"], "end_ts":rows[-1]["ts"]+step,
            "metrics":fresh, "stressed":fresh_stress,
            "account_feedback_control":{"metrics":fresh_account, "stressed":fresh_account_stress},
            "training_label_end_ts":confirmation_initial["last_label_ts"],
            "stressed_training_label_end_ts":stressed_initial["last_label_ts"],
            "practice_continuity":{"start_ts":rows[holdout_start]["ts"],
                "rule":"Continue open practice positions, cooldowns and saved entry forecasts across the review boundary. "
                    "Only outcomes available after the boundary appear in confirmation feedback. "
                    "Ordinary and stressed tests each preserve their own costed practice history. "
                    "Account tests start with a separate $500 balance at the confirmation boundary."},
            "expectancy_interval":bootstrap_interval([t["r_multiple"] for t in fresh_trades])}
    first, last = rows[holdout_start+1]["open"], rows[-1]["close"]
    buy_hold = 500/(first*(1+slip)*(1+fee))*last*(1-slip)*(1-fee)-500
    regime_examples = {regime:sum(m.get("regimes", {}).get(regime, {}).get("samples",0)
        for m in trained["models"].values()) for regime in ("BULL","BEAR","CHOP")}
    positive = sum(f["metrics"].get("complete", True) and f["metrics"]["net_pnl"]>0 for f in folds)
    uncertainty = bootstrap_interval([t["r_multiple"] for t in trades])
    reasons = []
    if forecast_correction:
        reasons.append("Experimental forecast correction cannot qualify or control trading.")
    if not examples:
        reasons.append("No completed training examples survived the signal and execution checks; see training diagnostics.")
    if any(not f["metrics"].get("complete", True) for f in folds):
        reasons.append("A later test period stopped at a data gap while holding a position; its return is unknown.")
    if positive < 2:
        reasons.append("Fewer than two later test periods made money after costs.")
    if len(trades) < 30:
        reasons.append("Fewer than 30 trades in the final test period.")
    final_complete = holdout.get("complete", True) and stressed.get("complete", True)
    if not final_complete:
        reasons.append("The final test could not follow an open position through missing candles. "
                       "A complete account result is required before qualification.")
    elif holdout["net_pnl"] <= 0 or stressed["net_pnl"] <= 0:
        reasons.append("The final test did not stay profitable at both ordinary and higher costs.")
    if uncertainty["lower_r"] is None or uncertainty["lower_r"] <= 0:
        reasons.append("The uncertainty in final trade results is too large to qualify.")
    if holdout.get("max_drawdown_pct") is not None and holdout["max_drawdown_pct"] > 15:
        reasons.append("The final test lost more than 15% from a prior equity peak.")
    if (not account_only.get("complete", True) or not account_only_stressed.get("complete", True)
            or account_only.get("net_pnl", 0) <= 0 or account_only_stressed.get("net_pnl", 0) <= 0):
        reasons.append("Learning only from selected account trades did not stay profitable at ordinary and higher costs.")
    if reused:
        if confirmation is None:
            reasons.append("This history was already reviewed when this learner was designed. No later prices are available for fresh confirmation.")
        else:
            fresh, fresh_stress = confirmation["metrics"], confirmation["stressed"]
            if (not fresh.get("complete", True) or not fresh_stress.get("complete", True)
                    or fresh.get("net_pnl", 0) <= 0 or fresh_stress.get("net_pnl", 0) <= 0
                    or fresh.get("trades", 0) < 30
                    or (confirmation["expectancy_interval"]["lower_r"] or 0) <= 0
                    or (fresh.get("max_drawdown_pct") or 0) > 15):
                reasons.append("New prices after the reviewed report have not passed the trade-count, cost, uncertainty and drawdown checks.")
            fresh_control = confirmation["account_feedback_control"]
            if any(not m.get("complete", True) or m.get("net_pnl", 0) <= 0
                   for m in fresh_control.values()):
                reasons.append("On new prices, learning only from selected account trades did not stay profitable at ordinary and higher costs.")
    def pnl_difference(left, right):
        if left.get("net_pnl") is None or right.get("net_pnl") is None:
            return None
        return left["net_pnl"]-right["net_pnl"]
    daily = daily_goal_report(trades,rows[holdout_start]["ts"],rows[-1]["ts"])
    daily["complete"] = holdout.get("complete", True)
    if not daily["complete"]:
        daily.update(mean_net_per_day=None, median_net_per_day=None,
            basis="Incomplete account test: listed closed trades cover only the observed prefix before an unresolved data gap.")
    return {"engine_version":ENGINE_VERSION, "policy_version":POLICY_VERSION,
        "learning_report_version":LEARNING_REPORT_VERSION,
        "learning_inputs":{"dimensions":len(FEATURE_NAMES), "names":list(FEATURE_NAMES),
            "rule":"Fixed-scale entry-time features; preceding support/resistance, closed-candle "
                "wicks, RSI change, VWAP distance, volatility, completed daily context, Bitcoin trend, relative strength, "
                "and news/calendar context observed by that close. "
                "Exit reviews and future candles are not entry inputs."},
        "entry_error_rule":"Save the forecast at entry in chronological development training as well as later tests. "
            "After at least 30 resolved forecasts in a model component, "
            "its entry-time RMSE can raise the ranking error margin; it cannot reduce the existing margin. "
            "Each realized reward still trains once. Diagnostic summaries cannot select a policy.",
        "symbol":symbol, "interval":interval, "created_at":int(time.time()),
        "data_selection":coverage,
        "replay":{"clock":"Historical candles processed without wall-clock waits",
            "decision_interval":interval, "training_start_ts":rows[240]["ts"],
            "training_end_ts":rows[development-1]["ts"]+step,
            "test_start_ts":rows[holdout_start]["ts"], "test_end_ts":rows[-1]["ts"]+step,
            "daily_context_rule":"Only completed UTC days, joined at each signal close. 21 consecutive daily candles required; intraday indicators restart after intraday gaps.",
            "decision_rule":"Use only information available at the signal close; enter no earlier than the next candle.",
            "time_exit_rule":"Evaluate time limits at the execution candle close. Fixed learning deadlines align with supported intervals; other deadlines use the first available close at or after the limit. Intrabar stop/target ordering remains stop-first.",
            "feedback_rule":"Learn a trade result only after its exit candle closes."},
        "evaluation":{"reviewed_through_ts":boundary, "reuses_reviewed_history":reused,
            "basis":"reused_research" if reused else "chronological_test",
            "confirmation":confirmation,
            "note":"Decision-time causality does not erase research reuse. Known reviewed history cannot independently qualify a revised learner."},
        "model_provenance":{"source":"primary_continuous_practice_replay",
            "last_label_ts":trained["last_label_ts"],
            "rule":"The saved model comes from the primary chronological replay. "
                "Changing a report review boundary cannot replace it with a restarted confirmation model. "
                "Confirmation and higher-cost simulations remain separate evaluation accounts."},
        "data_quality":quality, "data_sha256":dataset_digest(rows), "data_hours":len(rows)*step/3600000,
        "daily_data":{"source":"independent_daily_candles" if daily_rows is not None else "complete_intraday_aggregation",
            "rows":len(daily_rows) if daily_rows is not None else None,
            "data_sha256":dataset_digest(daily_rows) if daily_rows is not None else None,
            "start_ts":daily_rows[0]["ts"] if daily_rows else None,
            "end_ts":daily_rows[-1]["ts"] if daily_rows else None,
            "holdout_ready_candles":sum(bool(f and f.get("daily",{}).get("ready")) for f in features[holdout_start:]),
            "holdout_candles":len(rows)-holdout_start},
        "bitcoin_data":bitcoin_summary(bitcoin_rows, features, holdout_start),
        "event_data":{**event_summary(event_snapshot, features, holdout_start),
                      "enabled":event_required},
        "learning_evidence":evidence_summary(trained["models"]),
        "failure_predictions":failure_prediction_summary(trained["models"]),
        "historical_examples":len(examples), "candidate_count":len(candidates),
        "regime_examples":regime_examples,
        "training_diagnostics":{"totals":training_totals, "candidates":training_candidates,
            "mode":"Separate eligible and cost-blocked practice tracks for each strategy. "
                   "An open cost-blocked example cannot occupy eligible practice; entry eligibility uses signal and fill costs. "
                   "All fees and slippage are charged; unresolved trades spanning gaps are excluded from learning. "
                   "Repeated losses do not pause independent label collection beyond routine entry spacing. "
                   "Policy tests and trading retain their cost and qualification checks.",
            "count_basis":"Counts cover two complementary tracks per candidate; candle checks repeat across tracks. "
                          "Different strategies and holding periods overlap. These are not independent bets or account trades."},
        "training_label_end_ts":initial["last_label_ts"],
        "development_prediction_audit":trainer.predictions.summary(),
        "forecast_calibration":{**summarize_calibration({k:m.get("eligible_model", {}) for k,m in trained["models"].items()}),
            "enabled_for_selection":True,
            "policy":"two_sided_experiment" if forecast_correction else "eligible_downside_only",
            "scope":"The normal model only reduces positive forecasts after enough comparable cost-eligible outcomes. "
                "Two-sided corrections remain a separate research experiment. Saved entry errors also affect the ranking margin."},
        "pre_holdout_model_sha256":hashlib.sha256(json.dumps(initial,sort_keys=True).encode()).hexdigest(),
        "holdout_start_ts":rows[holdout_start]["ts"],
        "folds":folds, "profitable_folds":positive, "holdout":holdout,
        "holdout_stressed":stressed, "frozen_holdout":frozen,
        "learning_pnl_difference":pnl_difference(holdout, frozen),
        "upgrade_comparison":{"baseline":baseline, "baseline_stressed":baseline_stressed,
            "net_pnl_difference":pnl_difference(holdout, baseline),
            "stress_net_pnl_difference":pnl_difference(stressed, baseline_stressed),
            "selection_uses_comparison":False,
            "label":"Pooled learning without regime adaptation or signal-time cost screening; same seed, costs and daily halt."},
        "strategy_expansion_comparison":{"baseline":legacy, "baseline_stressed":legacy_stressed,
            "net_pnl_difference":pnl_difference(holdout, legacy),
            "stress_net_pnl_difference":pnl_difference(stressed, legacy_stressed),
            "selection_uses_comparison":False,
            "label":"Original 16 candidates only, using the same entry features, model seed, costs and risk. "
                    "Negative differences mean the added strategies made this test worse; this is not a replication of an older app version."},
        "benchmarks":{"cash_net_pnl":0., "buy_hold_net_pnl":buy_hold,
            "buy_hold_return_pct":buy_hold/5, "scope":"$500 buy and hold after costs over the same executable final-test period; different exposure from the trading policy."},
        "holdout_learning_updates":holdout.get("feedback", {}).get("resolved_examples", 0),
        "holdout_shadow_feedback":holdout.get("feedback"),
        "account_feedback_comparison":{"baseline":account_only, "baseline_stressed":account_only_stressed,
            "net_pnl_difference":pnl_difference(holdout, account_only),
            "stress_net_pnl_difference":pnl_difference(stressed, account_only_stressed),
            "selection_uses_comparison":False,
            "label":"The same cost-aware learner updated only by selected account trades. "
                    "Continuous paper and Coinbase journals use selected-trade feedback between scheduled historical reviews. "
                    "This control must also be profitable before qualification."},
        "performance_attribution":attribution(trades),
        "failure_learning":summarize_outcomes(trained["models"]),
        "trade_reviews":{"break_even_band_r":BREAK_EVEN_R, "post_exit_hours":list(POST_EXIT_HOURS),
            "development":merge_summaries(training_reviews),
            "selected":summarize_trades(rows,trades,step,len(rows),cases_per_group=8),
            "scope":"Costs and observed trade paths describe outcomes, not proven causes. "
                "Losses and near-break-even examples receive detailed review priority; actual net rewards are unchanged. "
                "After-exit windows and the fixed break-even-stop counterfactual are report-only and never train entry decisions. "
                "Detailed cases are sampled; counts cover all reviewed completed trades."},
        "outcome_memory_comparison":{"baseline":no_memory, "baseline_stressed":no_memory_stressed,
            "net_pnl_difference":pnl_difference(holdout, no_memory),
            "stress_net_pnl_difference":pnl_difference(stressed, no_memory_stressed),
            "selection_uses_comparison":False,
            "label":"Same version, data, candidates, seed and costs with the new outcome-memory selection adjustment disabled."},
        "holdout_expectancy_interval":uncertainty, "validated":not reasons,
        "prediction_audit":{"selected":holdout["prediction_audit"],
            "shadow":(holdout.get("feedback") or {}).get("prediction_audit"),
            "scope":"Entry forecasts evaluated after closure. Account trades and overlapping candidate practice are reported separately."},
        "rejection_reasons":reasons, "cost_signature":cost_signature(settings),
        "costs":{"fee_per_side":fee, "slippage_per_fill":settings["slippage_rate"],
                 "assumed_half_spread":.0005, "stress_multiplier":1.5},
        "daily_goal":daily,
        "model":trained,
        "scope":"One-market $500 policy tests. Historical shadow feedback keeps studying unselected candidates; account profits count only selected trades. Training examples overlap and are not independent evidence. Forward journal updates learn only completed account trades between historical reviews. Model estimates are not calibrated probabilities.",
        "warning":"Repeated runs can reuse test periods. The frozen comparison cannot change qualification. Portfolio execution, latency, live fills, and future profit remain unvalidated.",
        "holdout_trades":[{k:t[k] for k in ("entry_ts","exit_ts","strategy_family","pnl","r_multiple","reason",
            "risk_dollars","gross_pnl","fees_paid","entry_forecast","regime") if k in t} for t in trades]}
