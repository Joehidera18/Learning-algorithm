"""Persistent forecast bias is not reduced by replaying more biased examples."""
import copy
import json
import unittest

from lab.adaptive import AdaptivePolicy, action_key, empty_model, feature_vector, update_model
from tests.test_adaptive import F, trained_state


class ForecastReliabilityTests(unittest.TestCase):
    def test_persistent_optimism_does_not_shrink_with_sample_count(self):
        policy=AdaptivePolicy()
        vector=feature_vector(F,policy.candidates[0],0,0)
        model=empty_model()
        for i in range(300):
            update_model(model,vector,-1.,{'ready':True,'estimated_net_r':.5})
            if i+1 in (30,100,300):
                self.assertGreaterEqual(policy.error_penalty(model),1.5)
        self.assertEqual(model['entry_error_sum'],450.)
        self.assertEqual(model['sum_r'],-300.)

    def test_signed_bias_does_not_treat_underprediction_as_optimism(self):
        model=empty_model()
        model.update(samples=100,entry_error_samples=100,
                     entry_error_sum=-100.,entry_squared_error=100.,squared_error=0.)
        self.assertAlmostEqual(AdaptivePolicy().error_penalty(model),.1)

    def test_zero_scored_forecasts_and_untrained_forecasts_add_no_bias(self):
        model=empty_model();policy=AdaptivePolicy()
        vector=feature_vector(F,policy.candidates[0],0,0)
        update_model(model,vector,-1.)
        update_model(model,vector,-1.,{'ready':False,'estimated_net_r':.5})
        self.assertEqual(model['entry_error_samples'],0)
        self.assertEqual(model['entry_error_sum'],0.)

    def test_saved_moments_round_trip_and_reject_inconsistent_bias(self):
        policy=AdaptivePolicy(trained_state());params=policy.candidates[0]
        vector=feature_vector(F,params,0,0)
        from lab.prediction_audit import entry_snapshot
        forecast=entry_snapshot(policy.forecast(params,vector),100)
        policy.observe(params,vector,-8,101,{'entry_forecast':forecast})
        saved=json.loads(json.dumps(policy.export(),allow_nan=False))
        self.assertEqual(AdaptivePolicy(saved).export(),saved)
        for value in (float('nan'),float('inf'),1000.):
            broken=copy.deepcopy(saved)
            broken['models'][action_key(params)]['entry_error_sum']=value
            with self.assertRaises(ValueError): AdaptivePolicy(broken)


if __name__=='__main__': unittest.main()
