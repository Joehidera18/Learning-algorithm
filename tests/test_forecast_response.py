"""Response fits must learn actual entry errors without future/blocked labels."""
import copy
import json
import unittest
from unittest.mock import patch

from lab.adaptive import AdaptivePolicy, action_key, feature_vector
from lab.forecast_response import empty_response, update, estimate, validate
from lab.prediction_audit import entry_snapshot
from tests.test_adaptive import F, trained_state


class ForecastResponseTests(unittest.TestCase):
    def test_persistent_optimism_is_reduced_only_after_required_evidence(self):
        r=empty_response()
        for i in range(29): update(r,.4,-1.,i)
        self.assertEqual(estimate(r,.4)['response_adjustment_r'],0.)
        for i in range(29,100): update(r,.4,-1.,i)
        result=estimate(r,.4)
        self.assertTrue(result['response_ready'])
        self.assertLess(.4+result['response_adjustment_r'],0.)
        self.assertEqual(result['response_samples'],100)
        validate(r,100,99)

    def test_fit_preserves_order_and_keeps_full_tail_losses(self):
        r=empty_response()
        for i in range(100): update(r,(-1,1)[i%2],(1,-1)[i%2],i)
        estimates=[x+estimate(r,x)['response_adjustment_r'] for x in (-1.,0.,1.)]
        self.assertEqual(estimates,sorted(estimates))
        for i in range(100,250): update(r,.4,-8.,i)
        self.assertEqual(.4+estimate(r,.4)['response_adjustment_r'],-3.)
        self.assertLess(r['y']/r['weight'],-7.)

    def test_saved_entry_base_not_later_weights_trains_once_and_round_trips(self):
        p=AdaptivePolicy(trained_state());params=p.candidates[0];v=feature_vector(F,params)
        with patch.object(p,'base_predict',return_value=.4):
            forecast=entry_snapshot(p.forecast(params,v),100)
        saved=copy.deepcopy(forecast)
        with patch.object(p,'base_predict',return_value=2.):
            p.observe(params,v,-1.,110,{'entry_forecast':forecast})
        group=p.state['models'][action_key(params)]
        self.assertNotIn('forecast_response',group)
        response=group['eligible_model']['forecast_response']
        self.assertEqual(response['samples'],1)
        self.assertEqual(response['x'],.4)
        self.assertEqual(response['y'],-1.)
        self.assertEqual(forecast,saved)
        state=json.loads(json.dumps(p.export(),allow_nan=False))
        self.assertEqual(AdaptivePolicy(state).export(),state)

    def test_cost_blocked_labels_and_other_candidates_cannot_supply_response(self):
        p=AdaptivePolicy(trained_state());params=p.candidates[0];v=feature_vector(F,params)
        costly=list(v);costly[16]=1.
        for i in range(40):
            f=entry_snapshot(p.forecast(params,costly),100+i*2)
            p.observe(params,costly,-1.,101+i*2,{'entry_forecast':f,'practice_lane':'cost_blocked'})
        self.assertEqual(p.forecast(params,v)['response_samples'],0)
        self.assertEqual(p.forecast(p.candidates[1],v)['response_samples'],0)

    def test_corrupt_or_future_response_is_rejected_before_any_update(self):
        p=AdaptivePolicy(trained_state());params=p.candidates[0];v=feature_vector(F,params)
        f=entry_snapshot(p.forecast(params,v),100);before=p.export()
        for bad in (dict(f,response_adjustment_r=1.), dict(f,response_samples=-1),
                    dict(f,response_last_label_ts=200),dict(f,base_estimated_net_r=float('nan'))):
            with self.assertRaises(ValueError):p.observe(params,v,-1.,101,{'entry_forecast':bad})
            self.assertEqual(p.export(),before)
        r=empty_response()
        for i in range(40):update(r,.4,-1.,i)
        for field,value in (('samples',1000),('weight_squared',0),('xy',1e9),('last_label_ts',41)):
            broken=dict(r);broken[field]=value
            with self.assertRaises(ValueError):validate(broken,40,40)


if __name__=='__main__':unittest.main()
