"""Artificial fixtures verify software behavior, never market profitability."""
import copy
import json
import unittest
from unittest.mock import patch

from lab.adaptive import AdaptivePolicy, action_key, feature_vector, cost_context, DIMENSIONS
from lab.continuous import DEFAULTS
from lab.evaluation import REVIEWED_THROUGH, attribution
from lab.execution import simulate
from lab.learning_research import learn_history
from lab.shadow_learning import HistoricalFeedback
from tests.test_adaptive import F
from tests.test_execution import candles

STEP = 900000


class CostLearningTests(unittest.TestCase):
    def test_known_costs_and_holding_period_are_entry_features(self):
        p = AdaptivePolicy().candidates[0]
        zero = feature_vector(F, p, 0, 0)
        costs = feature_vector(F, p, .004, .001)
        self.assertEqual(len(costs), DIMENSIONS)
        self.assertEqual(costs[:16], zero[:16])
        self.assertGreater(costs[16], zero[16])
        self.assertLess(costs[17], zero[17])
        self.assertEqual(costs[18], 12/168)
        with self.assertRaises(ValueError):
            feature_vector(dict(F, _close=float("nan")), p, .004, .001)

    def test_costly_losses_do_not_erase_distinct_feasible_evidence(self):
        policy = AdaptivePolicy(fee_rate=.004, slippage_rate=.001)
        p = policy.candidates[0]
        cheap, expensive = dict(F, _atr=5), dict(F, _atr=.2)
        low = feature_vector(cheap,p,.004,.001)
        high = feature_vector(expensive,p,.004,.001)
        self.assertEqual(cost_context(low), "low")
        self.assertEqual(cost_context(high), "high")
        for t in range(80): policy.observe(p, low, 1., t)
        for t in range(80,580): policy.observe(p, high, -1., t)
        model = policy.state["models"][action_key(p)]
        self.assertLess(model["recent_r"], 0)
        self.assertGreater(policy.evidence(p, low)["recent_r"], 0)
        self.assertIsNotNone(policy.choose(cheap))
        self.assertIsNone(policy.choose(expensive))
        self.assertEqual(sum(m["samples"] for m in model["cost_contexts"].values()),580)
        self.assertEqual(policy.state["observations"],580)
        self.assertEqual(AdaptivePolicy(json.loads(json.dumps(policy.export()))).export(),policy.export())

    def test_prediction_error_is_measured_before_learning_and_penalizes_rank(self):
        p = AdaptivePolicy().candidates[0]
        policy = AdaptivePolicy()
        vector = feature_vector(F,p,0,0)
        policy.observe(p,vector,1.,1)
        model = policy.evidence(p,vector)
        self.assertEqual(model["squared_error"],1.)
        for t in range(2,81): policy.observe(p,vector,1.,t)
        choice = policy.choose(F)
        self.assertGreater(choice["error_penalty_r"],0)
        self.assertLess(choice["adjusted_score"],choice["estimated_net_r"])
        model = policy.evidence(p,vector)
        model["squared_error"] = 100000.
        self.assertIsNone(policy.choose(F))
        self.assertEqual(policy.last_diagnostics["rejections"]["prediction_error_too_large"],1)

    def test_training_keeps_signal_time_economics_when_next_open_changes(self):
        rows = candles(244)
        rows[241].update(open=100.2, high=101., low=99., close=100.5)
        p = AdaptivePolicy().candidates[0]
        fs = [dict(F) for _ in rows]
        _, trades = simulate(rows,fs,240,len(rows),500,.0075,.004,.001,p,
            training_examples=True,bar_interval_ms=STEP)
        self.assertEqual(trades[0]["training_vector"],feature_vector(F,p,.004,.001))
        self.assertNotEqual(trades[0]["entry"],F["_close"])


class ShadowLearningTests(unittest.TestCase):
    def setup_replay(self,n=500):
        rows = candles(n)
        # Both stop and target touch: the shared engine must assume the stop first.
        for row in rows: row.update(high=120.,low=90.)
        fs = [dict(F) if i>=240 else None for i in range(n)]
        policy = AdaptivePolicy(fee_rate=.004,slippage_rate=.001)
        return rows, fs, policy

    def test_no_future_feedback_then_full_cost_feedback_without_account_trades(self):
        rows,fs,policy = self.setup_replay()
        feedback = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
        feedback.advance(rows[241]["ts"])
        self.assertEqual(policy.state["observations"],0)
        feedback.advance(rows[241]["ts"]+STEP)
        self.assertGreater(policy.state["observations"],0)
        self.assertTrue(all(m["sum_r"]<0 for m in policy.state["models"].values()))
        before = policy.export()
        feedback.advance(rows[241]["ts"]+STEP)
        self.assertEqual(policy.export(),before)
        with self.assertRaises(ValueError): feedback.advance(rows[240]["ts"])
        rows,fs,policy = self.setup_replay()
        feedback = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
        metrics,trades = simulate(rows,fs,240,len(rows),500,.0075,.004,.001,
            {"family":"adaptive_policy","direction":"LONG"},policy=policy,
            feedback=feedback,bar_interval_ms=STEP)
        self.assertFalse(trades)
        self.assertEqual(metrics["net_pnl"],0.)
        self.assertGreater(feedback.count,0)
        self.assertEqual(policy.state["observations"],feedback.count)

    def test_shadow_outcomes_equal_individual_shared_execution(self):
        rows,fs,policy = self.setup_replay()
        feedback = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
        feedback.advance(rows[-1]["ts"]+STEP)
        expected = 0
        for p in policy.candidates:
            _,trades = simulate(rows,fs,240,len(rows),500,.0075,.004,.001,p,
                training_examples=True,bar_interval_ms=STEP)
            resolved = [t for t in trades if t["reason"]!="END"]
            expected += len(resolved)
            if resolved:
                model = policy.state["models"][action_key(p)]
                self.assertEqual(model["samples"],len(resolved))
                self.assertAlmostEqual(model["sum_r"],sum(t["r_multiple"] for t in resolved))
        self.assertEqual(feedback.count,expected)

    def test_future_prices_cannot_change_earlier_model(self):
        rows,fs,policy = self.setup_replay()
        changed = copy.deepcopy(rows)
        for row in changed[300:]: row.update(open=300,high=500,low=250,close=400)
        other = AdaptivePolicy(fee_rate=.004,slippage_rate=.001)
        a = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
        b = HistoricalFeedback(changed,fs,240,len(rows),DEFAULTS,other,STEP)
        for r in rows[240:300]:
            a.advance(r["ts"]+STEP); b.advance(r["ts"]+STEP)
            self.assertEqual(policy.export(),other.export())

    def test_skipped_candidates_can_recover_from_losing_evidence(self):
        rows = candles(550)
        for row in rows: row.update(high=120.,low=99.9)
        fs = [dict(F) for _ in rows]
        policy = AdaptivePolicy()
        p = policy.candidates[0]
        vector = feature_vector(F,p,0,0)
        for t in range(80): policy.observe(p,vector,-1.,t)
        self.assertIsNone(policy.choose(F))
        feedback = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
        feedback.advance(rows[-1]["ts"]+STEP)
        self.assertIsNotNone(policy.choose(F))

    def test_gap_censored_and_end_marked_positions_never_create_labels(self):
        rows = candles(500)
        del rows[243]
        fs = [dict(F) if i==240 else None for i in range(len(rows))]
        policy = AdaptivePolicy()
        feedback = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
        feedback.advance(rows[-1]["ts"]+STEP)
        self.assertEqual(feedback.count,0)
        self.assertGreater(feedback.gap_censored,0)
        rows = candles(243);fs = [dict(F) for _ in rows]
        policy = AdaptivePolicy()
        feedback = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
        feedback.advance(rows[-1]["ts"]+STEP)
        self.assertEqual(feedback.count,0)

    def test_account_closures_are_not_double_counted_as_shadow_examples(self):
        rows,fs,policy = self.setup_replay(550)
        for row in rows: row.update(low=99.9,high=120.)
        p = policy.candidates[0]
        for t in range(80): policy.observe(p,feature_vector(F,p,.004,.001),1.,t)
        feedback = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
        _,trades = simulate(rows,fs,240,len(rows),500,.0075,.004,.001,
            {"family":"adaptive_policy","direction":"LONG"},policy=policy,
            feedback=feedback,bar_interval_ms=STEP)
        self.assertGreater(len(trades),0)
        self.assertEqual(policy.state["observations"],80+feedback.count)


class EvaluationTests(unittest.TestCase):
    def fabricated_results(self, account_control_loss=False):
        def replay(rows,features,start,end,balance,risk,fee,slip,params,**kwargs):
            training = kwargs.get("training_examples",False)
            indices = [240+i*35 for i in range(100)] if training else list(range(start,start+40))
            reward = -1. if account_control_loss and not training and kwargs.get("feedback") is None and kwargs["policy"].learn else 1.
            trades = [{"entry_ts":rows[i]["ts"],"exit_ts":rows[i]["ts"],"reason":"TARGET2",
                "features":F,"training_vector":feature_vector(F),"strategy_family":params["family"],
                "r_multiple":reward,"pnl":reward} for i in indices]
            return {"net_pnl":40*reward,"return_pct":8*reward,"trades":len(trades),
                    "max_drawdown_pct":0,"complete":True},trades
        return replay

    def test_positive_reused_backtest_still_cannot_qualify(self):
        rows = candles(5000)
        with patch("lab.learning_research.simulate",side_effect=self.fabricated_results()), patch(
                "lab.learning_research.build_feature_cache",return_value={"features":[{}]*len(rows)}):
            result = learn_history(rows,"BTC-USD",dict(DEFAULTS))
        self.assertGreater(result["holdout"]["net_pnl"],0)
        self.assertGreater(result["holdout_stressed"]["net_pnl"],0)
        self.assertEqual(result["profitable_folds"],3)
        self.assertFalse(result["validated"])
        self.assertEqual(len(result["rejection_reasons"]),1)
        self.assertIn("already reviewed",result["rejection_reasons"][0])

    def test_shadow_profit_cannot_hide_a_losing_account_feedback_control(self):
        rows = candles(5000)
        with patch("lab.learning_research.simulate",side_effect=self.fabricated_results(True)), patch(
                "lab.learning_research.build_feature_cache",return_value={"features":[{}]*len(rows)}):
            result = learn_history(rows,"TEST-USD",dict(DEFAULTS))
        self.assertGreater(result["holdout"]["net_pnl"],0)
        self.assertLess(result["account_feedback_comparison"]["baseline"]["net_pnl"],0)
        self.assertFalse(result["validated"])
        self.assertTrue(any("selected account trades" in r for r in result["rejection_reasons"]))

    def test_reviewed_report_cannot_become_fresh_evidence_by_rerunning(self):
        result = learn_history(candles(3000),"BTC-USD",dict(DEFAULTS),reviewed_through_ts=1)
        self.assertTrue(result["evaluation"]["reuses_reviewed_history"])
        self.assertEqual(result["evaluation"]["reviewed_through_ts"],REVIEWED_THROUGH["BTC-USD"])
        self.assertIsNone(result["evaluation"]["confirmation"])
        self.assertFalse(result["validated"])
        self.assertTrue(any("already reviewed" in r for r in result["rejection_reasons"]))

    def test_fresh_shadow_profit_cannot_hide_a_losing_fresh_account_control(self):
        rows = candles(5000)
        ordinary = self.fabricated_results()
        losing_control = self.fabricated_results(True)
        def replay(*args, **kwargs):
            return (losing_control if args[2] >= 4700 else ordinary)(*args, **kwargs)
        with patch("lab.learning_research.simulate",side_effect=replay), patch(
                "lab.learning_research.build_feature_cache",return_value={"features":[{}]*len(rows)}):
            result = learn_history(rows,"TEST-USD",dict(DEFAULTS),reviewed_through_ts=rows[4700]["ts"])
        fresh = result["evaluation"]["confirmation"]
        self.assertGreater(result["account_feedback_comparison"]["baseline"]["net_pnl"],0)
        self.assertGreater(fresh["metrics"]["net_pnl"],0)
        self.assertLess(fresh["account_feedback_control"]["metrics"]["net_pnl"],0)
        self.assertFalse(result["validated"])
        self.assertEqual(len(result["rejection_reasons"]),1)
        self.assertIn("On new prices",result["rejection_reasons"][0])

    def test_confirmation_starts_after_review_and_uses_only_earlier_labels(self):
        rows = candles(3000)
        boundary = rows[2700]["ts"]
        result = learn_history(rows,"TEST-USD",dict(DEFAULTS),reviewed_through_ts=boundary)
        fresh = result["evaluation"]["confirmation"]
        self.assertEqual(fresh["start_ts"],boundary)
        self.assertLessEqual(fresh["training_label_end_ts"],boundary)
        self.assertFalse(result["validated"])
        json.dumps(result,allow_nan=False)

    def test_fee_attribution_reconciles_without_subtracting_slippage_twice(self):
        rows = candles(245); p = AdaptivePolicy().candidates[1]
        _,trades = simulate(rows,[dict(F) for _ in rows],240,len(rows),500,.0075,.004,.001,p)
        group = attribution(trades)["by_family"][p["family"]]
        self.assertGreater(group["slippage_notional"],0)
        self.assertAlmostEqual(group["gross_pnl"]-group["fees_paid"],group["net_pnl"])


if __name__=="__main__": unittest.main()
