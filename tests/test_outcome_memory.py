"""Artificial fixtures establish learning behavior, not market profitability."""
import copy
import json
import unittest

from lab.adaptive import AdaptivePolicy, action_key, feature_vector
from lab.outcome_memory import setup_context, summarize
from tests.test_adaptive import F


class OutcomeMemoryTests(unittest.TestCase):
    def conditions(self, up=True):
        sign = 1 if up else -1
        return dict(F, daily={"atr":10., "atr_pct":.1, "momentum7":.05*sign,
            "ma_distance_atr":sign, "ready":True})

    def test_failures_in_one_daily_context_do_not_blacklist_another(self):
        policy = AdaptivePolicy()
        p = policy.candidates[0]
        up, down = self.conditions(), self.conditions(False)
        u, d = feature_vector(up,p,0,0), feature_vector(down,p,0,0)
        for i in range(120):
            policy.observe(p,u,1.,i,outcome={"reason":"TARGET2","gross_r":1.2,"fee_r":.2})
        for i in range(120,420):
            policy.observe(p,d,-1.,i,outcome={"reason":"STOP","gross_r":-.8,"fee_r":.2})
        self.assertIsNotNone(policy.choose(up))
        self.assertIsNone(policy.choose(down))
        self.assertEqual(policy.last_diagnostics["rejections"]["recent_context_losses"],1)
        model = policy.state["models"][action_key(p)]
        self.assertEqual(model["outcomes"]["causes"],{"net_profit":120,"stopped_out":300})
        self.assertEqual(sum(m["samples"] for m in model["setup_contexts"].values()),420)
        self.assertEqual(policy.state["observations"],420)
        self.assertGreater(policy.predict(p,u),policy.predict(p,d))

    def test_fee_erased_gains_reduce_net_score_and_later_success_can_recover(self):
        policy = AdaptivePolicy()
        p = policy.candidates[0]; f = self.conditions(); v = feature_vector(f,p,0,0)
        for i in range(100):
            policy.observe(p,v,-.2,i,outcome={"reason":"TIME","gross_r":.1,"fee_r":.3})
        self.assertIsNone(policy.choose(f))
        memory = policy.state["models"][action_key(p)]["setup_contexts"][setup_context(v)]
        self.assertEqual(memory["causes"],{"fee_erased_gain":100})
        before = policy.export()
        for _ in range(20): policy.choose(f)
        self.assertEqual(before,policy.export())
        for i in range(100,260): policy.observe(p,v,1.,i)
        self.assertIsNotNone(policy.choose(f))
        self.assertGreater(policy.context_evidence(p,v)["recent_net_r"],.5)
        restored = AdaptivePolicy(json.loads(json.dumps(policy.export(),allow_nan=False)))
        self.assertEqual(restored.choose(f),policy.choose(f))

    def test_bad_attribution_or_future_order_cannot_partly_update_the_model(self):
        policy = AdaptivePolicy(); p = policy.candidates[0]; v = feature_vector(F,p,0,0)
        policy.observe(p,v,-1.,100,outcome={"reason":"STOP","gross_r":-.8,"fee_r":.2})
        before = policy.export()
        for outcome in ({"gross_r":0.,"fee_r":.1},{"fee_r":1.},
                        {"gross_r":float("nan"),"fee_r":1.},{"gross_r":-2.,"fee_r":-1.}):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                policy.observe(p,v,-1.,101,outcome=outcome)
            self.assertEqual(before,policy.export())
        with self.assertRaises(ValueError): policy.observe(p,v,1.,99)
        self.assertEqual(before,policy.export())
        corrupted=copy.deepcopy(before)
        corrupted["models"][action_key(p)]["outcomes"]["weighted_r"] = float("inf")
        with self.assertRaises(ValueError): AdaptivePolicy(corrupted)
        # Numeric JSON strings are normalized before any memory is changed.
        policy.observe(p,v,-.2,101,outcome={"reason":"TIME","gross_r":".1","fee_r":".3"})
        self.assertEqual(policy.state["models"][action_key(p)]["outcomes"]["causes"]["fee_erased_gain"],1)

    def test_summary_counts_outcomes_once_and_small_samples_cannot_trade(self):
        policy = AdaptivePolicy(); p = policy.candidates[0]; v = feature_vector(F,p,0,0)
        for i in range(29): policy.observe(p,v,1.,i)
        self.assertIsNone(policy.choose(F))
        summary=summarize(policy.state["models"])["by_family"][p["family"]]
        self.assertEqual(summary["examples"],29)
        self.assertEqual(summary["causes"]["net_profit"],29)
        self.assertEqual(summary["learned_contexts"],0)
        self.assertEqual(summary["cost_observations"],0)


if __name__ == "__main__": unittest.main()
