"""Forecast chronology and error feedback; fixtures are not profit evidence."""
import copy
import json
import unittest
from unittest.mock import patch

from lab.adaptive import AdaptivePolicy, action_key, feature_vector, approved_profile
from lab.continuous import DEFAULTS
from lab.execution import simulate
from lab.prediction_audit import PredictionAudit, entry_snapshot, summarize_predictions
from lab.shadow_learning import HistoricalFeedback
from tests.test_adaptive import F, trained_state
from tests.test_execution import candles

STEP = 900000


class EntryForecastTests(unittest.TestCase):
    def test_forward_forecast_uses_actual_decision_clock_after_signal_close(self):
        p=AdaptivePolicy(trained_state()); params=p.candidates[0];v=feature_vector(F)
        p.observe(params,v,1.,105)
        with self.assertRaises(ValueError): entry_snapshot(p.forecast(params,v),100)
        f=entry_snapshot(p.forecast(params,v),100,decision_ts=110)
        self.assertEqual(f['signal_close_ts'],100)
        self.assertEqual(f['forecast_ts'],110)
        before=p.export()
        with self.assertRaises(ValueError): p.observe(params,v,-1.,109,outcome={'entry_forecast':f})
        self.assertEqual(p.export(),before)
        p.observe(params,v,-1.,111,outcome={'entry_forecast':f})

    def test_forecast_uses_entry_model_even_if_weights_change_before_exit(self):
        rows = candles(248)
        rows[241].update(high=101, low=99, close=100)
        rows[243].update(low=95)
        fs = [dict(F) if i == 240 else None for i in range(len(rows))]
        policy = AdaptivePolicy(trained_state())
        expected = policy.choose(F)["learning"]["forecast"]
        def opened(trade):
            # Another resolved outcome can update the same model while open.
            policy.observe(trade["decision_params"], trade["learning"]["vector"], -1, rows[241]["ts"])
        _, trades = simulate(rows,fs,240,len(rows),500,.0075,0,0,
            {"family":"adaptive_policy","direction":"LONG"},policy=policy,
            on_entry=opened,bar_interval_ms=STEP)
        t = trades[0]
        self.assertEqual(t["entry_forecast"]["estimated_net_r"], expected["estimated_net_r"])
        self.assertEqual(t["entry_forecast"]["signal_close_ts"],rows[241]["ts"])
        audit = summarize_predictions(trades)
        self.assertEqual(audit["samples"],1)
        self.assertAlmostEqual(audit["optimism_bias_r"],expected["estimated_net_r"]-t["r_multiple"])

    def test_bulk_and_incremental_shadow_forecasts_and_updates_match(self):
        rows = candles(450)
        for r in rows: r.update(high=120.,low=90.)
        fs = [dict(F) for _ in rows]
        a, b = AdaptivePolicy(), AdaptivePolicy()
        one = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,a,STEP)
        many = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,b,STEP)
        one.advance(rows[-1]["ts"]+STEP)
        for r in rows[240:]: many.advance(r["ts"]+STEP)
        self.assertEqual(a.export(), b.export())
        self.assertEqual(one.summary(), many.summary())
        self.assertGreater(one.summary()["prediction_audit"]["samples"],0)
        restored = AdaptivePolicy(json.loads(json.dumps(a.export(),allow_nan=False)))
        self.assertEqual(restored.export(),a.export())

    def test_true_entry_error_can_raise_margin_without_a_second_reward(self):
        policy = AdaptivePolicy(trained_state()); p = policy.candidates[0]
        vector = feature_vector(F,p,0,0)
        forecast = entry_snapshot(dict(policy.forecast(p,vector),estimated_net_r=3),100)
        before = policy.state["observations"]
        for stamp in range(100,130):
            policy.observe(p,vector,-1.,stamp,outcome={"entry_forecast":forecast})
        model = policy.evidence(p,vector)
        self.assertEqual(policy.state["observations"],before+30)
        self.assertEqual(model["entry_error_samples"],30)
        self.assertEqual(model["entry_squared_error"],480)
        self.assertGreaterEqual(policy.error_penalty(model),4/(30**.5))

    def test_invalid_or_future_forecasts_cannot_partly_train(self):
        policy = AdaptivePolicy(trained_state()); p = policy.candidates[0]
        vector = feature_vector(F,p,0,0)
        f = entry_snapshot(policy.forecast(p,vector),100)
        before = policy.export()
        for wrong in (dict(f,model_last_label_ts=101),dict(f,signal_close_ts=102),
                      dict(f,estimated_net_r=float('nan')),dict(f,ready='true')):
            with self.assertRaises(ValueError):
                policy.observe(p,vector,-1.,101,outcome={"entry_forecast":wrong})
            self.assertEqual(policy.export(),before)

    def test_missing_warmup_end_and_exact_break_even_are_distinct(self):
        audit = PredictionAudit()
        p = AdaptivePolicy(); params=p.candidates[0];v=feature_vector(F)
        cold=entry_snapshot(p.forecast(params,v),100)
        audit.observe({"reason":"TIME","entry_forecast":cold})
        audit.observe({"reason":"TIME"})
        audit.observe({"reason":"END"})
        ready=entry_snapshot(AdaptivePolicy(trained_state()).forecast(params,v),100)
        audit.observe({"reason":"TIME","entry_forecast":ready,"strategy_family":"test"},0.)
        s=audit.summary()
        self.assertEqual((s['samples'],s['missing_forecasts'],s['untrained_forecasts'],s['excluded_end_marks']),(1,1,1,1))
        self.assertEqual(s['near_break_even'],1)
        self.assertEqual(s['positive_forecasts_that_lost'],0)
        self.assertEqual(s['zero_forecast_rmse_r'],0.)

    def test_conditional_research_state_cannot_load_as_the_trading_model(self):
        experiment = AdaptivePolicy(recent_return_veto=False)
        with self.assertRaises(ValueError): AdaptivePolicy(experiment.export())
        # All other qualification metadata can match and the alternate model is still rejected.
        from lab.engine import ENGINE_VERSION
        from lab.research import cost_signature
        import time
        profile = {'engine_version':ENGINE_VERSION,'cost_signature':cost_signature(DEFAULTS),
                   'data_end_ts':int(time.time()*1000),'model':experiment.export()}
        with patch('lab.adaptive.load_state',return_value=profile):
            self.assertIsNone(approved_profile('unused','DOT-USD',DEFAULTS))


if __name__ == '__main__': unittest.main()
