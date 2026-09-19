"""Artificial paths check learning correctness, not market profitability."""
import copy
import json
import math
import unittest

from lab.adaptive import AdaptivePolicy, FEATURE_NAMES, feature_vector, action_key
from lab.engine import build_feature_cache
from lab.outcome_memory import DECAY, setup_context
from tests.test_adaptive import F
from tests.test_execution import candles


class CandleContextTests(unittest.TestCase):
    def test_new_inputs_distinguish_rejection_and_extension_without_outcome_leakage(self):
        base = feature_vector(F)
        changed = dict(F, upper_wick=.7, lower_wick=.1, rsi_previous=40,
            distance_to_resistance_atr=-2, distance_to_support_atr=4,
            vwap_distance_atr=2, atr_regime=2, prior_compression=True)
        richer = feature_vector(changed)
        self.assertEqual(base[:19], richer[:19])
        self.assertTrue(all(a != b for a,b in zip(base[19:27],richer[19:27])))
        self.assertEqual(base[27:], richer[27:])
        self.assertEqual(len(richer),len(FEATURE_NAMES))
        self.assertTrue(all(math.isfinite(v) and abs(v)<=1 for v in richer))
        # Completed-trade attribution must never sneak into the entry features.
        self.assertEqual(richer,feature_vector(dict(changed,pnl=10000,
            r_multiple=1000,reason="TARGET2",mfe_net_r=200,review={"future":True})))
        for name in ("upper_wick","distance_to_resistance_atr","vwap_distance_atr"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                feature_vector(dict(F,**{name:float("nan")}))

    def test_same_old_features_can_learn_different_wick_outcomes(self):
        policy=AdaptivePolicy(); p=policy.candidates[0]
        clean=feature_vector(dict(F,upper_wick=0),p,0,0)
        rejected=feature_vector(dict(F,upper_wick=.8),p,0,0)
        self.assertEqual(clean[:19],rejected[:19])
        for i in range(300):
            policy.observe(p,clean,1.5,2*i)
            policy.observe(p,rejected,-.5,2*i+1)
        self.assertGreater(policy.predict(p,clean),policy.predict(p,rejected)+.1)
        self.assertEqual(policy.state["observations"],600)
        restored=AdaptivePolicy(json.loads(json.dumps(policy.export(),allow_nan=False)))
        self.assertEqual(restored.predict(p,clean),policy.predict(p,clean))

    def test_compact_entry_inputs_equal_full_inputs_and_ignore_later_candles(self):
        rows=candles(330)
        for i,r in enumerate(rows):
            close=100+.01*i+math.sin(i/4)
            r.update(open=close-.05,close=close,high=close+.3,low=close-.2,volume=5+i%11)
        compact=build_feature_cache(rows,"15m",simple_only=True)["features"]
        full=build_feature_cache(rows,"15m")["features"]
        prefix=build_feature_cache(rows[:300],"15m",simple_only=True)["features"]
        for i in range(240,300):
            self.assertEqual(feature_vector(compact[i]),feature_vector(full[i]))
            self.assertEqual(feature_vector(prefix[i]),feature_vector(compact[i]))
            preceding=rows[i-20:i]
            atr=compact[i]["_atr"]
            self.assertAlmostEqual(compact[i]["distance_to_resistance_atr"],
                (max(r["high"] for r in preceding)-rows[i]["close"])/atr)

    def test_full_tail_loss_changes_economic_memory_and_uncertainty_with_stable_weights(self):
        policy=AdaptivePolicy(); p=policy.candidates[0]; v=feature_vector(F,p,0,0)
        for i in range(80): policy.observe(p,v,1.,i)
        old=policy.export()["models"][action_key(p)]
        policy.observe(p,v,-1000.,80,outcome={"reason":"STOP_GAP"})
        model=policy.state["models"][action_key(p)]
        memory=model["setup_contexts"][setup_context(v)]
        old_memory=old["setup_contexts"][setup_context(v)]
        self.assertAlmostEqual(memory["weighted_r"],DECAY*old_memory["weighted_r"]-1000.)
        self.assertAlmostEqual(memory["weighted_r2"],DECAY*old_memory["weighted_r2"]+1000000.)
        self.assertLess(policy.context_evidence(p,v)["recent_net_r"],0)
        self.assertLess(model["recent_r"],0)
        self.assertEqual(model["sum_r"],-920.)
        self.assertGreater(model["squared_error"]-old["squared_error"],999000.)
        self.assertGreater(policy.error_penalty(model),policy.error_penalty(old))
        self.assertTrue(all(math.isfinite(w) and abs(w)<=3 for w in model["weights"]))
        self.assertIsNone(policy.choose(F))
        self.assertEqual(AdaptivePolicy(json.loads(json.dumps(policy.export()))).export(),policy.export())

    def test_old_vectors_and_unusable_numbers_cannot_partly_train_new_model(self):
        policy=AdaptivePolicy(); p=policy.candidates[0]; v=feature_vector(F,p,0,0)
        policy.observe(p,v,1.,1)
        before=policy.export()
        for vector,reward in ((v[:19],1.),(v,1e308),(v,float("nan"))):
            with self.assertRaises(ValueError): policy.observe(p,vector,reward,2)
            self.assertEqual(policy.export(),before)
        old=copy.deepcopy(before);old["version"]="online-net-r-v8-exit-study"
        with self.assertRaises(ValueError): AdaptivePolicy(old)


if __name__=="__main__": unittest.main()
