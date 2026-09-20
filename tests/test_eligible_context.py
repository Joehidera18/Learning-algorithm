"""Causal evidence, forecast and market-context tests use artificial prices."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab.adaptive import AdaptivePolicy, action_key, feature_vector
from lab.continuous import ContinuousLearner, DEFAULTS
from lab.daily_context import DAY_MS, independent_daily_context
from lab.learning_data import prepare_learning_history
from lab.learning_research import build_learning_features
from lab.learning_diagnostics import evidence_summary, regime_report, experiment_manifest
from lab.market_context import attach_market_context
from lab.outcome_memory import validate_detail
from lab.prediction_audit import entry_snapshot
from tests.test_adaptive import F
from tests.test_execution import candles


def days(n=40):
    rows = candles(n, step=DAY_MS, start=0)
    for i,r in enumerate(rows):
        price = 100+i*.5
        r.update(open=price, high=price+1, low=price-1, close=price+.1)
    return rows


class EligibleEvidenceTests(unittest.TestCase):
    def test_blocked_samples_cannot_make_an_affordable_forecast_ready(self):
        policy = AdaptivePolicy()
        p = policy.candidates[0]; v = feature_vector(F,p,0,0)
        # Signal economics pass, but the later fill can fail its cost check.
        for i in range(200):
            policy.observe(p,v,1.,i,outcome={"practice_lane":"cost_blocked"})
        self.assertEqual(policy.forecast(p,v)["samples"],0)
        self.assertIsNone(policy.choose(F))
        for i in range(29): policy.observe(p,v,1.,200+i,outcome={"practice_lane":"eligible"})
        self.assertFalse(policy.forecast(p,v)["ready"])
        self.assertIsNone(policy.choose(F))
        policy.observe(p,v,1.,229,outcome={"practice_lane":"eligible"})
        self.assertTrue(policy.forecast(p,v)["ready"])
        self.assertIsNotNone(policy.choose(F))
        self.assertEqual(policy.state["observations"],230)
        self.assertEqual(evidence_summary(policy.state["models"])["eligible_examples"],30)

    def test_many_blocked_losses_cannot_change_eligible_weights_or_calibration(self):
        policy=AdaptivePolicy(); p=policy.candidates[0]; v=feature_vector(F,p,0,0)
        for i in range(80): policy.observe(p,v,.5,i)
        before=copy.deepcopy(policy.state["models"][action_key(p)]["eligible_model"])
        for i in range(80,280):
            f=entry_snapshot(policy.forecast(p,v),i)
            policy.observe(p,v,-2.,i,outcome={"practice_lane":"cost_blocked","entry_forecast":f})
        self.assertEqual(policy.state["models"][action_key(p)]["eligible_model"],before)
        self.assertEqual(AdaptivePolicy(json.loads(json.dumps(policy.export()))).export(),policy.export())

    def test_invalid_lane_and_invalid_failure_forecast_do_not_partly_train(self):
        policy=AdaptivePolicy(); p=policy.candidates[0];v=feature_vector(F,p,0,0)
        before=policy.export()
        with self.assertRaises(ValueError): policy.observe(p,v,-1,1,outcome={"practice_lane":"made_up"})
        self.assertEqual(policy.export(),before)
        f=entry_snapshot(policy.forecast(p,v),0)
        f["failure_predictions"]={"target_reached":{"estimate":1.5,"samples":30,"ready":True,"prior_frequency":.5}}
        with self.assertRaises(ValueError): policy.observe(p,v,-1,1,outcome={"entry_forecast":f})
        self.assertEqual(policy.export(),before)
        self.assertEqual(validate_detail(-1,{"practice_lane":"cost_blocked"})["practice_lane"],"cost_blocked")

    def test_primary_correction_cannot_raise_an_entry_estimate(self):
        for reward in (-1.,1.):
            policy=AdaptivePolicy();p=policy.candidates[0];v=feature_vector(F,p,0,0)
            for i in range(80):policy.observe(p,v,.5,i)
            from lab.forecast_response import estimate as response_estimate
            with patch.object(policy,"response_estimate",return_value=response_estimate(None,.4)):
                for i in range(40):
                    f=entry_snapshot(policy.forecast(p,v),100+i*2)
                    policy.observe(p,v,reward,101+i*2,outcome={"entry_forecast":f})
                result=entry_snapshot(policy.forecast(p,v),200)
            self.assertLessEqual(result["estimated_net_r"],.4)
            self.assertEqual(result["calibration_samples"],40)
            self.assertEqual(result["calibration_policy"],"eligible_downside_shrinkage")
            if reward < 0:self.assertLess(result["estimated_net_r"],.4)
            else:self.assertGreater(result["trial_estimated_net_r"],result["estimated_net_r"])


class FailurePredictionTests(unittest.TestCase):
    def review(self, path=True):
        return {"outcome":"loss", "net_r":-.5, "findings":["little_follow_through"] if path else [],
            "best_net_r":0. if path else None,"worst_net_r":-.5 if path else None,
            "giveback_r":.5 if path else None,"holding_hours":1.}

    def test_entry_predictions_are_scored_after_closure_against_saved_baseline(self):
        policy=AdaptivePolicy();p=policy.candidates[0];v=feature_vector(F,p,0,0)
        for i in range(40):
            forecast=entry_snapshot(policy.forecast(p,v),i*2)
            before=copy.deepcopy(forecast)
            policy.observe(p,v,-.5,i*2+1,outcome={"review":self.review(),"reason":"STOP","entry_forecast":forecast})
            self.assertEqual(forecast,before)
        head=policy.state["models"][action_key(p)]["eligible_model"]["failure_models"]["little_follow_through"]
        self.assertEqual(head["samples"],40)
        self.assertEqual(head["positives"],40)
        self.assertEqual(head["scored"],10)
        self.assertGreater(head["brier_sum"],0)
        self.assertEqual(head["baseline_brier_sum"],0)
        self.assertEqual(policy.state["observations"],40)
        self.assertEqual(AdaptivePolicy(json.loads(json.dumps(policy.export()))).export(),policy.export())

    def test_unknown_paths_do_not_become_no_follow_through_labels(self):
        policy=AdaptivePolicy();p=policy.candidates[0];v=feature_vector(F,p,0,0)
        policy.observe(p,v,-.5,1,outcome={"review":self.review(False),"reason":"TIME"})
        heads=policy.state["models"][action_key(p)]["eligible_model"]["failure_models"]
        self.assertNotIn("little_follow_through",heads)
        self.assertNotIn("gave_back_gains",heads)
        self.assertEqual(heads["near_break_even"]["samples"],1)

    def test_future_failure_labels_cannot_change_pending_forecasts(self):
        from lab.chronological_learning import ChronologicalTrainer
        one,two=AdaptivePolicy(),AdaptivePolicy();v=feature_vector(F,one.candidates[0],0,0)
        a=ChronologicalTrainer(one,one.candidates,[(20,0,v,-.5,{"review":self.review()},10)])
        b=ChronologicalTrainer(two,two.candidates,[(20,0,v,-.5,{"review":self.review(False)},10)])
        a.advance(19);b.advance(19)
        self.assertEqual(one.export(),two.export());self.assertEqual(a.pending,b.pending)
        a.advance(20);b.advance(20)
        self.assertNotEqual(one.export(),two.export())


class BitcoinContextTests(unittest.TestCase):
    def test_empty_signal_features_stay_unavailable_when_context_is_attached(self):
        rows=candles(2,start=25*DAY_MS)
        self.assertEqual(attach_market_context(rows,[None,{}],900000,days()),[None,{}])

    def test_a_changed_bitcoin_candle_invalidates_the_cached_model_identity(self):
        from lab.autolearn import AutoLearner
        rows=candles(300);daily=days()
        a=AutoLearner._fingerprint(None,rows,'ALT-USD',DEFAULTS,bitcoin_rows=daily)
        changed=copy.deepcopy(daily);changed[-1]['close']+=.01
        b=AutoLearner._fingerprint(None,rows,'ALT-USD',DEFAULTS,bitcoin_rows=changed)
        self.assertNotEqual(a,b)

    def test_future_and_unfinished_daily_candles_do_not_change_context(self):
        daily=days(); rows=candles(2,step=900000,start=25*DAY_MS)
        fs=[dict(F,daily=q) for q in independent_daily_context(rows,900000,daily)]
        original=copy.deepcopy(fs)
        a=attach_market_context(rows,fs,900000,daily)
        changed=copy.deepcopy(daily)
        for r in changed[25:]:r.update(open=500,high=600,low=400,close=550)
        b=attach_market_context(rows,fs,900000,changed)
        self.assertEqual(a,b);self.assertEqual(fs,original)
        self.assertTrue(a[0]["market_context"]["ready"])
        self.assertEqual(a[0]["market_context"]["available_ts"],25*DAY_MS)
        self.assertEqual(a[0]["market_context"]["relative_momentum7"],0)

    def test_missing_daily_candle_resets_readiness_and_cannot_be_forward_filled(self):
        daily=days();rows=candles(1,start=25*DAY_MS)
        fs=[dict(F,daily=independent_daily_context(rows,900000,daily)[0])]
        gap=daily[:24]+daily[25:]
        self.assertFalse(attach_market_context(rows,fs,900000,gap)[0]["market_context"]["ready"])
        self.assertFalse(attach_market_context(rows,fs,900000,None)[0]["market_context"]["ready"])

    def test_continuous_and_replay_features_use_the_same_bitcoin_join(self):
        daily=days();rows=candles(300,start=25*DAY_MS)
        segments=[{"start_index":0,"end_index":len(rows)}]
        expected=build_learning_features(rows,"15m",segments,daily_rows=daily,bitcoin_rows=daily)[-1]
        with tempfile.TemporaryDirectory() as td:
            agent=ContinuousLearner(Path(td)/'test.db',Path(td)/'data')
            agent.market['ALT-USD']=agent._empty_market()
            agent.market['ALT-USD']['bars'].update({'15m':rows,'1d':daily})
            agent._bitcoin_daily=daily
            actual=agent._latest_feature('ALT-USD','15m')
            self.assertEqual(actual['market_context'],expected['market_context'])
            self.assertEqual(feature_vector(actual),feature_vector(expected))
            agent._bitcoin_daily=[]
            self.assertFalse(agent._latest_feature('ALT-USD','15m')['market_context']['ready'])

    def test_trained_context_requirement_blocks_missing_benchmark_and_survives_restart(self):
        policy=AdaptivePolicy(market_context_required=True);p=policy.candidates[0]
        f=dict(F,market_context={'ready':True,'momentum7':.02,'trend':1,'atr_pct':.02,'relative_momentum7':.01})
        v=feature_vector(f,p,0,0)
        for i in range(80):policy.observe(p,v,1.,i)
        self.assertIsNotNone(policy.choose(f));self.assertIsNone(policy.choose(F))
        self.assertEqual(policy.last_diagnostics['rejections'],{'bitcoin_context_unavailable':22})
        restored=AdaptivePolicy(policy.export());self.assertIsNone(restored.choose(F))

    def test_shared_daily_context_does_not_copy_each_large_feature_dictionary(self):
        daily=days();rows=candles(50,start=25*DAY_MS)
        joined=independent_daily_context(rows,900000,daily)
        fs=[dict(F,daily=q) for q in joined]
        original=fs[0]
        attached=attach_market_context(rows,fs,900000,daily,in_place=True)
        self.assertIs(attached[0],original)
        self.assertIs(attached[0]['market_context'],attached[1]['market_context'])


class RegimeDiagnosticsTests(unittest.TestCase):
    def test_prices_and_entry_regimes_are_not_confused_with_candidate_counts(self):
        report=regime_report([{'regime':'BULL'},{'regime':'BEAR'},None],
            [{'regime':'BULL','pnl':-1},{'regime':'BEAR','pnl':2}],0,3)['by_entry_regime']
        self.assertEqual(report['BULL']['candles'],1)
        self.assertEqual(report['BEAR']['wins'],1)
        self.assertEqual(report['UNKNOWN']['trades'],0)
        self.assertEqual(sum(g['net_pnl'] for g in report.values()),1)

    def test_trial_identity_tracks_context_costs_and_review_boundary(self):
        r={'policy_version':'v','engine_version':'v','symbol':'ALT-USD','interval':'15m',
           'data_sha256':'a','daily_data':{'data_sha256':'b'},'bitcoin_data':{'data_sha256':'c'},
           'cost_signature':{'fee_rate':.004},'evaluation':{'reviewed_through_ts':123},
           'model':{'forecast_correction':False}}
        initial=experiment_manifest(r,True,True)
        self.assertFalse(initial['selection_uses_comparisons'])
        for key,value in [('bitcoin_data',{'data_sha256':'changed'}),('evaluation',{'reviewed_through_ts':124}),('cost_signature',{'fee_rate':.005})]:
            revised=experiment_manifest(dict(r,**{key:value}),True,True)
            self.assertNotEqual(initial['trial_id'],revised['trial_id'])


if __name__=='__main__':unittest.main()
