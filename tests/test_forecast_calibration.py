"""Causal learning and saved-state checks; synthetic fixtures are not returns."""
import copy
import json
import unittest
from unittest.mock import patch

from lab.adaptive import AdaptivePolicy, action_key, feature_vector
from lab.chronological_learning import ChronologicalTrainer
from lab.forecast_calibration import correction, empty_bucket, update_bucket
from lab.forecast_response import estimate as response_estimate
from lab.prediction_audit import entry_snapshot, summarize_predictions
from tests.test_adaptive import F, trained_state


class ForecastCalibrationTests(unittest.TestCase):
    def collect(self, reward, n=40, applied=True):
        state=dict(trained_state(),forecast_correction=applied)
        policy=AdaptivePolicy(state,forecast_correction=applied);params=policy.candidates[0]
        vector=feature_vector(F,params,0,0)
        with patch.object(policy,'response_estimate',return_value=response_estimate(None,.4)):
            for i in range(n):
                forecast=entry_snapshot(policy.forecast(params,vector),100+i*2)
                policy.observe(params,vector,reward,101+i*2,outcome={'entry_forecast':forecast})
            result=policy.forecast(params,vector)
        return policy,params,vector,result

    def test_losses_and_break_even_correct_optimism_without_becoming_bonus_rewards(self):
        for actual in (-1.,-.03,0.):
            policy,params,vector,forecast=self.collect(actual)
            self.assertTrue(forecast['calibration_ready'])
            self.assertLess(forecast['estimated_net_r'],.4)
            self.assertEqual(forecast['raw_estimated_net_r'],.4)
            self.assertEqual(forecast['calibration_samples'],40)
            model=policy.state['models'][action_key(params)]
            self.assertAlmostEqual(model['sum_r'],80+40*actual)
            self.assertEqual(policy.state['observations'],120)
            b=model['forecast_bands']['low/0_to_0.5R']
            self.assertAlmostEqual(b['weighted_residual']/b['weight'],actual-.4)

    def test_underprediction_can_raise_estimate_after_enough_observations(self):
        _,_,_,forecast=self.collect(.9)
        self.assertGreater(forecast['estimated_net_r'],.4)
        self.assertLess(forecast['estimated_net_r'],.9)
        self.assertTrue(forecast['calibration_ready'])

    def test_sparse_context_does_not_override_the_base_forecast(self):
        _,_,_,forecast=self.collect(-1,n=29)
        self.assertFalse(forecast['calibration_ready'])
        self.assertEqual(forecast['estimated_net_r'],.4)

    def test_first_resolved_loss_can_lower_normal_forecast_but_is_not_ready_evidence(self):
        policy,params,v,forecast=self.collect(-1,n=1,applied=False)
        self.assertAlmostEqual(forecast['estimated_net_r'],.4-1.4/51)
        self.assertEqual(forecast['trial_estimated_net_r'],.4)
        self.assertEqual(forecast['calibration_adjustment_r'],0)
        self.assertFalse(forecast['calibration_ready'])
        self.assertTrue(forecast['calibration_provisional'])
        f=entry_snapshot(forecast,200)
        audit=summarize_predictions([{'entry_forecast':f,'reason':'STOP',
            'strategy_family':params['family'],'pnl':-1,'risk_dollars':1}])['calibration']
        self.assertEqual(audit['applied_forecasts'],1)
        self.assertEqual(audit['provisional_forecasts'],1)
        self.assertEqual(audit['adjusted_forecasts'],0)
        self.assertEqual(audit['selected']['samples'],audit['raw']['samples'])
        self.assertLess(audit['selected']['rmse_r'],audit['raw']['rmse_r'])
        self.assertEqual(policy.state['observations'],81)

    def test_normal_correction_has_no_thirty_sample_activation_cliff_and_never_raises(self):
        before=self.collect(-1,n=29,applied=False)[3]
        after=self.collect(-1,n=30,applied=False)[3]
        self.assertLess(before['estimated_net_r'],.4)
        self.assertLess(abs(after['estimated_net_r']-before['estimated_net_r']),.03)
        for n in (1,29,40):
            forecast=self.collect(.9,n=n,applied=False)[3]
            self.assertEqual(forecast['estimated_net_r'],.4)
            self.assertFalse(forecast['calibration_provisional'])

    def test_invalid_provisional_record_cannot_update_model(self):
        policy,params,v,forecast=self.collect(-1,n=1,applied=False)
        good=entry_snapshot(forecast,200)
        before=policy.export()
        missing=dict(good);missing.pop('shrunk_calibration_adjustment_r')
        for broken in (missing,dict(good,calibration_provisional=False),
                       dict(good,shrunk_calibration_adjustment_r=float('nan')),
                       dict(good,shrunk_calibration_adjustment_r=1)):
            with self.assertRaises(ValueError):
                policy.observe(params,v,-1,201,outcome={'entry_forecast':broken})
            self.assertEqual(policy.export(),before)

    def test_cost_bands_actions_and_forecast_bands_do_not_share_corrections(self):
        policy,params,v,_=self.collect(-1)
        costly=list(v);costly[16]=1.
        with patch.object(policy,'response_estimate',return_value=response_estimate(None,.4)):
            self.assertLess(policy.predict(params,v),.4)
            self.assertEqual(policy.predict(params,costly),.4)
            self.assertEqual(policy.predict(policy.candidates[1],v),.4)
        with patch.object(policy,'response_estimate',return_value=response_estimate(None,.8)):
            self.assertEqual(policy.predict(params,v),.8)

    def test_tail_losses_keep_their_actual_size(self):
        b=empty_bucket()
        for i in range(40): update_bucket(b,.4,-8.,i)
        self.assertAlmostEqual(b['weighted_residual']/b['weight'],-8.4)
        self.assertLess(correction(b)['adjustment_r'],-3.)
        policy,params,v,f=self.collect(-8.)
        self.assertEqual(f['estimated_net_r'],-3.)
        self.assertAlmostEqual(f['calibration_adjustment_r'],-3.4)
        entry_snapshot(f,200)

    def test_saved_state_round_trips_and_rejects_invalid_calibration(self):
        policy,params,v,_=self.collect(-1)
        state=json.loads(json.dumps(policy.export(),allow_nan=False))
        self.assertEqual(AdaptivePolicy(state,forecast_correction=True).forecast(params,v),policy.forecast(params,v))
        key=action_key(params)
        for field,value in [('samples',99999),('weighted_residual',float('nan')),
                            ('weight_squared',0),('last_label_ts',99999)]:
            broken=copy.deepcopy(state)
            broken['models'][key]['forecast_bands']['low/0_to_0.5R'][field]=value
            with self.assertRaises(ValueError): AdaptivePolicy(broken,forecast_correction=True)

    def test_default_can_only_lower_optimism_and_experimental_state_cannot_load(self):
        policy,params,v,forecast=self.collect(-1,applied=False)
        self.assertTrue(forecast['calibration_ready'])
        self.assertTrue(forecast['calibration_applied'])
        self.assertLess(forecast['estimated_net_r'],.4)
        self.assertLess(forecast['trial_estimated_net_r'],.4)
        f=entry_snapshot(forecast,200)
        a=summarize_predictions([{'entry_forecast':f,'reason':'STOP','strategy_family':params['family'],
                                 'pnl':-1.,'risk_dollars':1.}])
        self.assertEqual(a['calibration']['applied_forecasts'],1)
        self.assertEqual(a['calibration']['adjusted_forecasts'],1)
        alternate=dict(policy.export(),forecast_correction=True)
        with self.assertRaises(ValueError): AdaptivePolicy(alternate)
        from lab.adaptive import approved_profile
        from lab.engine import ENGINE_VERSION
        from lab.research import cost_signature
        from lab.continuous import DEFAULTS
        import time
        profile={'engine_version':ENGINE_VERSION,'cost_signature':cost_signature(DEFAULTS),
                 'data_end_ts':int(time.time()*1000),'model':alternate}
        with patch('lab.adaptive.load_state',return_value=profile):
            self.assertIsNone(approved_profile('unused','DOT-USD',DEFAULTS))

    def test_invalid_entry_correction_is_rejected_before_any_model_update(self):
        policy,params,v,_=self.collect(-1)
        good=entry_snapshot(policy.forecast(params,v),200)
        before=policy.export()
        for wrong in (dict(good,calibration_adjustment_r=9),
                      dict(good,calibration_key='high/nonpositive'),
                      dict(good,calibration_last_label_ts=99999),
                      dict(good,raw_estimated_net_r=float('nan'))):
            with self.assertRaises(ValueError): policy.observe(params,v,-1,201,outcome={'entry_forecast':wrong})
            self.assertEqual(policy.export(),before)

    def test_audit_compares_raw_and_corrected_on_the_same_entries(self):
        policy,params,v,f=self.collect(-1)
        f=entry_snapshot(f,200)
        t={'entry_forecast':f,'pnl':-1,'risk_dollars':1,'strategy_family':params['family'],'reason':'STOP'}
        a=summarize_predictions([t,dict(t,reason='END')])
        paired=a['calibration']
        self.assertEqual(paired['paired_samples'],1)
        self.assertEqual(paired['adjusted_forecasts'],1)
        self.assertLess(paired['corrected']['rmse_r'],paired['raw']['rmse_r'])
        self.assertEqual(paired['by_raw_forecast_band']['0_to_0.5R']['raw']['samples'],1)
        self.assertEqual(a['excluded_end_marks'],1)

    def test_experimental_report_has_a_permanent_disqualifying_reason(self):
        from lab.learning_research import learn_history
        from lab.continuous import DEFAULTS
        from tests.test_execution import candles
        rows=candles(3000)
        with patch('lab.learning_research.build_learning_features',return_value=[None]*len(rows)):
            report=learn_history(rows,'BTC-USD',DEFAULTS,exit_comparison=False,
                                 selection_comparison=False,forecast_correction=True)
        self.assertFalse(report['validated'])
        self.assertTrue(report['model']['forecast_correction'])
        self.assertIn('Experimental forecast correction cannot qualify or control trading.',report['rejection_reasons'])


class ChronologicalDevelopmentTests(unittest.TestCase):
    def trainer(self, future_reward=-1.):
        p=AdaptivePolicy(trained_state());v=feature_vector(F,p.candidates[0],0,0)
        examples=[(140,0,v,future_reward,{'reason':'STOP'},100),
                  (110,0,v,1.,{'reason':'TARGET2'},101),
                  (160,0,v,.1,{'reason':'TIME'},110)]
        return p,ChronologicalTrainer(p,p.candidates,examples)

    def test_future_labels_cannot_change_earlier_forecasts_or_models(self):
        a,one=self.trainer(-1);b,two=self.trainer(2.)
        one.advance(110);two.advance(110)
        self.assertEqual(a.export(),b.export())
        self.assertEqual(one.pending,two.pending)
        self.assertEqual(one.pending[0]['model_last_label_ts'],79)
        self.assertEqual(one.pending[2]['model_last_label_ts'],110)
        saved=copy.deepcopy(one.pending[0])
        one.advance(140)
        self.assertEqual(one.predictions.totals['samples'],2)
        self.assertEqual(saved['signal_close_ts'],100)
        self.assertEqual(a.state['observations'],82)

    def test_bulk_incremental_and_reconstructed_training_are_identical(self):
        a,one=self.trainer();b,two=self.trainer();c,three=self.trainer()
        one.advance(160)
        for time in (100,101,105,110,140,160): two.advance(time)
        three.advance(160)
        self.assertEqual(a.export(),b.export())
        self.assertEqual(a.export(),c.export())
        self.assertEqual(one.predictions.summary(),two.predictions.summary())
        self.assertEqual(a.state['observations'],83)
        self.assertEqual(one.predictions.summary()['samples'],3)
        self.assertFalse(one.pending)
        with self.assertRaises(ValueError): one.advance(159)

    def test_development_rejects_entry_after_outcome(self):
        p=AdaptivePolicy()
        for entry in (100,101,float('nan')):
            with self.assertRaises(ValueError):
                ChronologicalTrainer(p,p.candidates,[(100,0,feature_vector(F),1.,{},entry)])


if __name__=='__main__': unittest.main()
