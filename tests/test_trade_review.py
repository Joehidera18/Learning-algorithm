"""Artificial paths check timing/accounting; they provide no profit evidence."""
import copy
import json
import unittest
from unittest.mock import patch

from lab.adaptive import AdaptivePolicy, feature_vector, action_key
from lab.execution import simulate
from lab.outcome_memory import trade_feedback
from lab.trade_review import close_review, outcome_band, summarize_trades, merge_summaries
from tests.test_adaptive import F
from tests.test_execution import candles

STEP = 900000


class TradeReviewTests(unittest.TestCase):
    def trade_path(self, mode="reversal"):
        rows = candles(360)
        rows[241].update(open=100.,low=99.5,high=104.5,close=104.)
        rows[242].update(open=103.9,low=100.5,high=104.5,close=102.)
        rows[243].update(open=100.,low=97.,high=100.2,close=98.)
        if mode == "same_bar":
            rows[241].update(low=97.)
        elif mode == "wick_only":
            rows[241].update(close=100.5)
            rows[242].update(open=100.5,low=97.,high=101.,close=98.)
        elif mode == "gap":
            rows[242].update(open=95.,low=94.,high=96.,close=95.)
        policy = AdaptivePolicy()
        params = dict(policy.candidates[0],stop_atr=1.,rr2=3.,cooldown_minutes=0)
        fs = [dict(F,_atr=2.) if i==240 else None for i in range(len(rows))]
        with patch("lab.engine.evaluate_signal",return_value=(70,None)):
            _, trades = simulate(rows,fs,240,len(rows),500,.0075,.004,.001,params,
                training_examples=True,bar_interval_ms=STEP)
        self.assertEqual(len(trades),1)
        return rows,trades[0]

    def summary(self, rows, trades, end=None):
        return summarize_trades(rows,trades,STEP,len(rows) if end is None else end)

    def test_break_even_is_after_costs_and_never_a_positive_reward_bonus(self):
        self.assertEqual(outcome_band(.1),"near_break_even")
        self.assertEqual(outcome_band(-.1),"near_break_even")
        self.assertEqual(outcome_band(-1.),"full_risk_loss")
        self.assertEqual(outcome_band(-.11),"loss")
        for reward in (-.05,0.,.05):
            policy=AdaptivePolicy(); p=policy.candidates[0]
            t={"risk_dollars":10.,"pnl":reward*10,"gross_pnl":(reward+.2)*10,"fees_paid":2.,
                "entry_ts":0,"exit_ts":STEP,"reason":"TIME"}
            t["review"]=close_review(t)
            policy.observe(p,feature_vector(F,p,0,0),reward,STEP,outcome=trade_feedback(t))
            model=policy.state["models"][action_key(p)]
            self.assertEqual(model["sum_r"],reward)
            self.assertEqual(model["samples"],1)
            self.assertEqual(model["outcomes"]["causes"],{"near_break_even":1})
            self.assertEqual(model["outcomes"]["review_samples"],1)
            self.assertEqual(model["wins"],int(reward>0))
            self.assertEqual(AdaptivePolicy(json.loads(json.dumps(policy.export()))).export(),policy.export())

    def test_giveback_uses_net_marks_and_fee_covered_stop_can_change_a_reversal(self):
        rows,t=self.trade_path()
        self.assertEqual(t["reason"],"STOP")
        self.assertIn("gave_back_gains",t["review"]["findings"])
        self.assertGreater(t["review"]["best_net_r"],1.)
        case=self.summary(rows,[t])["cases"][0]
        alternative=case["break_even_stop"]
        self.assertEqual(alternative["activated_ts"],rows[242]["ts"])
        self.assertEqual(alternative["exit_ts"],rows[242]["ts"])
        self.assertAlmostEqual(alternative["net_r"],0.)
        self.assertAlmostEqual(alternative["difference_r"],1.)
        self.assertEqual(alternative["available_ts"],t["exit_ts"]+STEP)
        self.assertAlmostEqual(t["r_multiple"],-1.)

    def test_high_wick_cannot_activate_a_rule_that_requires_a_prior_close(self):
        rows,t=self.trade_path("wick_only")
        alternative=self.summary(rows,[t])["cases"][0]["break_even_stop"]
        self.assertIsNone(alternative["activated_ts"])
        self.assertAlmostEqual(alternative["difference_r"],0.)

    def test_ambiguous_entry_bar_does_not_credit_a_gain_after_the_stop(self):
        rows,t=self.trade_path("same_bar")
        self.assertIn("entry_bar_stop",t["review"]["findings"])
        self.assertLess(t["review"]["best_net_r"],0.)
        alternative=self.summary(rows,[t])["cases"][0]["break_even_stop"]
        self.assertIsNone(alternative["activated_ts"])
        self.assertAlmostEqual(alternative["net_r"],-1.)

    def test_gap_can_lose_money_even_after_break_even_stop_activates(self):
        rows,t=self.trade_path("gap")
        alternative=self.summary(rows,[t])["cases"][0]["break_even_stop"]
        self.assertIsNotNone(alternative["activated_ts"])
        self.assertLess(alternative["net_r"],-1.)
        self.assertEqual(alternative["reason"],"STOP_GAP")
        self.assertIn("loss_exceeded_plan",t["review"]["findings"])

    def test_post_exit_observations_wait_for_complete_horizons(self):
        rows,t=self.trade_path()
        exit_index=next(i for i,r in enumerate(rows) if r["ts"]==t["exit_ts"])
        first=self.summary(rows,[t],exit_index+1)["cases"][0]
        self.assertTrue(all(x["status"]=="pending" for x in first["post_exit"]["observations"]))
        one_hour=self.summary(rows,[t],exit_index+5)["cases"][0]
        statuses=[o["status"] for o in one_hour["post_exit"]["observations"]]
        self.assertEqual(statuses,["complete","pending","pending"])
        full=self.summary(rows,[t])["cases"][0]
        self.assertEqual([o["status"] for o in full["post_exit"]["observations"]],["complete"]*3)
        self.assertEqual(full["post_exit"]["observations"][0]["available_ts"],t["exit_ts"]+STEP+3600000)

    def test_future_prices_cannot_change_a_period_bounded_review_or_close_feedback(self):
        rows,t=self.trade_path()
        before=trade_feedback(t)
        end=248
        a=self.summary(rows,[t],end)
        changed=copy.deepcopy(rows)
        for row in changed[end:]:row.update(open=1000.,high=2000.,low=900.,close=1500.)
        b=self.summary(changed,[t],end)
        self.assertEqual(a,b)
        self.assertEqual(trade_feedback(t),before)
        self.assertNotIn("post_exit",before["review"])
        self.assertNotIn("break_even_stop",before["review"])

    def test_missing_post_exit_candle_stays_unknown(self):
        rows,t=self.trade_path()
        del rows[245]
        observations=self.summary(rows,[t])["cases"][0]["post_exit"]["observations"]
        self.assertTrue(all(o["status"]=="missing_candles" for o in observations))
        self.assertTrue(all("end_move_pct" not in o for o in observations))

    def test_priority_case_sample_does_not_duplicate_or_discard_summary_evidence(self):
        rows,t=self.trade_path()
        trades=[copy.deepcopy(t) for _ in range(10)]
        summary=self.summary(rows,trades)
        self.assertEqual(summary["examples"],10)
        self.assertEqual(summary["outcomes"],{"full_risk_loss":10})
        self.assertEqual(len(summary["cases"]),3)
        merged=merge_summaries([summary,summary])
        self.assertEqual(merged["examples"],20)
        self.assertEqual(len(merged["cases"]),3)
        ended=dict(t,reason="END")
        self.assertEqual(self.summary(rows,[ended])["examples"],0)

    def test_invalid_review_does_not_partly_update_model(self):
        rows,t=self.trade_path()
        policy=AdaptivePolicy();p=policy.candidates[0];v=feature_vector(F,p,0,0)
        detail=trade_feedback(t)
        detail["review"]=dict(detail["review"],best_net_r=float("nan"))
        before=policy.export()
        with self.assertRaises(ValueError):policy.observe(p,v,-1,100,outcome=detail)
        self.assertEqual(policy.export(),before)
        detail["review"]=dict(t["review"],outcome="profit")
        with self.assertRaises(ValueError):policy.observe(p,v,-1,100,outcome=detail)
        self.assertEqual(policy.export(),before)

    def test_unknown_live_price_path_is_not_filled_with_invented_excursions(self):
        review=close_review({"risk_dollars":4.,"pnl":-2.,"gross_pnl":-1.,"fees_paid":1.,
            "entry_ts":0,"exit_ts":STEP,"reason":"UNKNOWN"})
        self.assertEqual(review["path_basis"],"unavailable")
        self.assertIsNone(review["best_net_r"])
        self.assertIsNone(review["giveback_r"])


class LossTolerantPracticeTests(unittest.TestCase):
    def test_loss_streaks_pause_accounts_but_not_independent_training(self):
        rows=candles(450)
        for row in rows:row.update(low=90.)
        fs=[dict(F,_atr=5.) for _ in rows]
        params=AdaptivePolicy().candidates[0]
        with patch("lab.engine.evaluate_signal",return_value=(70,None)):
            practice,examples=simulate(rows,fs,240,len(rows),500,.0075,.004,.001,params,
                training_examples=True,bar_interval_ms=STEP)
            account,trades=simulate(rows,fs,240,len(rows),500,.0075,.004,.001,params,bar_interval_ms=STEP)
        self.assertGreater(len(examples),len(trades))
        self.assertGreater(practice["signal_funnel"]["loss_pause_overrides"],0)
        self.assertNotIn("loss_pause_overrides",account["signal_funnel"])
        self.assertTrue(all(t["pnl"]<0 for t in examples))
        self.assertTrue(all(t["risk_dollars"] <= 500*.0075+1e-9 for t in examples))
        self.assertGreaterEqual(trades[3]["entry_ts"]-trades[2]["exit_ts"],params["loss_cooldown_hours"]*3600000)


if __name__=="__main__":unittest.main()
