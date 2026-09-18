"""Regressions for causal cost selection, context learning and resumable research."""
import json
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from lab.adaptive import AdaptivePolicy, action_key, feature_vector, current_policy
from lab.autolearn import AutoLearner, UNQUALIFIED_REVIEW_SECONDS, REVIEW_SECONDS
from lab.continuous import DEFAULTS
from lab.execution import simulate
from lab.learning_data import prepare_learning_history
from lab.learning_research import learn_history
from lab.paper_store import load_state
from lab.research import cost_signature
from lab.service import Service
from lab.trade_quality import signal_cost_check
from tests.test_adaptive import F, install
from tests.test_execution import candles, features, PARAMS


class RegimeAndCostTests(unittest.TestCase):
    def test_costly_favorite_does_not_block_feasible_alternative(self):
        policy = AdaptivePolicy(fee_rate=.004, slippage_rate=.001)
        f = {**F, "_atr":1.2}
        first, second = policy.candidates[:2]
        for i in range(80):
            policy.observe(first, feature_vector(f), 1.5, i)
            policy.observe(second, feature_vector(f), 1., i)
        baseline = AdaptivePolicy(policy.export(), fee_rate=.004, slippage_rate=.001,
                                  cost_filter=False)
        self.assertEqual(baseline.choose(f)["params"], first)
        self.assertEqual(signal_cost_check(f, first, .004, .001)[1], "trading_cost_too_high")
        self.assertIsNone(signal_cost_check(f, second, .004, .001)[1])
        self.assertEqual(policy.choose(f)["params"], second)
        # The next open is never used to rank candidates. It can still reject a fill.
        rows = candles(243)
        rows[241].update(open=110, high=111, low=109, close=110)
        fs = [None]*243
        fs[240] = f
        metrics, trades = simulate(rows, fs, 240, 243, 500, .01, .004, .001,
                                    PARAMS, policy=policy)
        self.assertFalse(trades)
        self.assertEqual(metrics["signal_funnel"]["rejections"]["entry_gap_too_large"], 1)

    def test_signal_cost_check_agrees_with_execution_at_same_price(self):
        p = AdaptivePolicy().candidates[1]
        f = {**F, "_atr":1.2}
        quality, reason = signal_cost_check(f, p, .004, .001)
        self.assertIsNone(reason)
        fs = [None]*243
        fs[240] = f
        _, trades = simulate(candles(243), fs, 240, 243, 500, .01, .004, .001, p)
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0]["planned_cost_r"], quality["cost_r"])
        self.assertAlmostEqual(trades[0]["planned_net_rr"], quality["net_rr"])

    def test_regime_results_stay_distinct_without_double_counting(self):
        policy = AdaptivePolicy()
        p = policy.candidates[4]
        chop = {**F, "regime":"CHOP"}
        for i in range(100):
            policy.observe(p, feature_vector(F), 1., i)
        for i in range(160):
            policy.observe(p, feature_vector(chop), -1., 100+i)
        model = policy.state["models"][action_key(p)]
        self.assertEqual(policy.state["observations"], 260)
        self.assertEqual(sum(m["samples"] for m in model["regimes"].values()), 260)
        self.assertEqual(model["samples"], 260)
        self.assertLess(model["recent_r"], 0)
        self.assertGreater(model["regimes"]["BULL"]["recent_r"], 0)
        self.assertGreater(policy.predict(p, feature_vector(F)), policy.predict(p, feature_vector(chop)))
        self.assertIsNotNone(policy.choose(F))
        self.assertIsNone(policy.choose(chop))
        self.assertIsNone(AdaptivePolicy(policy.export(), regime_adaptation=False, failure_adaptation=False).choose(F))
        self.assertEqual(AdaptivePolicy(json.loads(json.dumps(policy.export()))).export(), policy.export())

    def test_sparse_regime_uses_pooled_estimate(self):
        policy = AdaptivePolicy()
        p = policy.candidates[4]
        for i in range(60):
            policy.observe(p, feature_vector(F), 1., i)
        vector = feature_vector({**F, "regime":"CHOP"})
        for i in range(5):
            policy.observe(p, vector, -1., 60+i)
        baseline = AdaptivePolicy(policy.export(), regime_adaptation=False)
        self.assertEqual(policy.predict(p, vector), baseline.predict(p, vector))

    def test_invalid_or_old_regime_models_are_rejected(self):
        policy = AdaptivePolicy()
        p = policy.candidates[0]
        policy.observe(p, feature_vector(F), 1., 1)
        state = policy.export()
        state["models"][action_key(p)]["regimes"]["BULL"]["weights"][0] = float("nan")
        with self.assertRaises(ValueError):
            AdaptivePolicy(state)
        state = policy.export()
        state["version"] = "online-net-r-v1"
        with self.assertRaises(ValueError):
            AdaptivePolicy(state)


class ReplayRiskTests(unittest.TestCase):
    def test_daily_loss_halt_resets_at_next_utc_day(self):
        rows = candles(340, step=300000)
        for row in rows:
            row["low"] = 98.
        params = {**PARAMS, "cooldown_minutes":0, "max_notional_fraction":1.}
        with patch("lab.engine.evaluate_signal", return_value=(70, None)):
            metrics, trades = simulate(rows, features(len(rows), atr=1.), 240, len(rows),
                500, .01, 0., 0., params, daily_loss_limit=.03)
        counts = Counter(t["entry_ts"]//86400000 for t in trades)
        self.assertEqual(sorted(counts.values()), [4, 4])
        self.assertEqual(metrics["halted_utc_days"], 2)
        self.assertGreater(metrics["signal_funnel"]["rejections"]["daily_loss_limit"], 0)
        self.assertAlmostEqual(metrics["gross_pnl"]-metrics["fees_paid"], metrics["net_pnl"])

    def test_intrabar_loss_latches_even_if_price_recovers(self):
        rows = candles(244)
        rows[241]["low"] = 97.5
        params = {**PARAMS, "stop_atr":5., "max_notional_fraction":1.}
        with patch("lab.engine.evaluate_signal", return_value=(70, None)):
            metrics, trades = simulate(rows, features(len(rows), atr=1.), 240, len(rows),
                500, .05, 0., 0., params, daily_loss_limit=.02)
        self.assertEqual(metrics["halted_utc_days"], 1)
        self.assertAlmostEqual(metrics["net_pnl"], 0.)
        self.assertEqual(trades[0]["reason"], "END")


class HistoricalCoverageTests(unittest.TestCase):
    def test_older_gap_retains_recorded_history_on_both_sides(self):
        rows = candles(6000)
        del rows[1000]
        selected, quality, coverage = prepare_learning_history(rows, "15m")
        self.assertEqual(selected, rows)
        self.assertEqual(coverage["used_candles"], 5999)
        self.assertEqual(coverage["missing_intervals"], 1)
        self.assertEqual(coverage["excluded_candles"], 0)
        self.assertEqual(coverage["used_hours"], 5999/4)
        self.assertEqual(quality["gaps"], 1)
        self.assertEqual(coverage["segment_count"], 2)
        self.assertEqual([s["candles"] for s in coverage["segments"]], [1000, 4999])
        self.assertEqual(coverage["warmup_candles"], 480)
        self.assertEqual(coverage["signal_ready_candles"], 5519)

    def test_recent_gap_keeps_earlier_history_but_invalid_old_prices_reject(self):
        rows = candles(6000)
        del rows[5000]
        selected, _, coverage = prepare_learning_history(rows, "15m")
        self.assertEqual(selected, rows)
        self.assertEqual([s["candles"] for s in coverage["segments"]], [5000, 999])
        rows = candles(6000)
        del rows[1000]
        rows[0]["close"] = float("nan")
        with self.assertRaises(ValueError):
            prepare_learning_history(rows, "15m")

    def test_completed_candidates_resume_to_identical_research_result(self):
        saved, simulations = {}, []
        stopped = False
        def save(index, value):
            nonlocal stopped
            saved[index] = json.loads(json.dumps(value))
            if index in (2,24):
                stopped = True
        def traced(*args, **kwargs):
            if kwargs.get("training_examples"):
                simulations.append(args[8]["family"])
            return simulate(*args, **kwargs)
        checkpoint = {"load":saved.get, "save":save}
        rows = candles(3000)
        # Fixed entry signals create resolved labels; this tests saved weights and
        # label ordering, rather than only resuming an empty no-signal dataset.
        with patch("lab.learning_research.build_feature_cache", return_value={"features":[dict(F) for _ in rows]}):
            with patch("lab.learning_research.simulate", side_effect=traced):
                with self.assertRaises(InterruptedError):
                    learn_history(rows, "BTC-USD", DEFAULTS, cancelled=lambda:stopped,
                                  checkpoint=checkpoint)
                self.assertEqual(len(simulations), 6)  # Two tracks per completed candidate.
                stopped = False
                with self.assertRaises(InterruptedError):
                    learn_history(rows, "BTC-USD", DEFAULTS, cancelled=lambda:stopped,
                                  checkpoint=checkpoint)
                self.assertEqual(len(simulations),50)
                self.assertNotIn('exit_policy',saved[0]['diagnostics']['params'])
                self.assertEqual(saved[22]['diagnostics']['params']['exit_policy'],'fee_covered_break_even')
                stopped = False
                resumed = learn_history(rows, "BTC-USD", DEFAULTS, checkpoint=checkpoint)
                self.assertEqual(len(simulations), 88)
                self.assertEqual(set(saved),set(range(44)))
            fresh = learn_history(rows, "BTC-USD", DEFAULTS)
        self.assertGreater(resumed["historical_examples"], 100)
        self.assertGreater(resumed["model"]["observations"], 0)
        for key in ("model", "pre_holdout_model_sha256", "training_diagnostics", "holdout", "upgrade_comparison", "trade_reviews", "exit_policy_comparison"):
            self.assertEqual(resumed[key], fresh[key], key)
        self.assertFalse(resumed["upgrade_comparison"]["selection_uses_comparison"])


class ReviewPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.service = Service(self.base, db_path=self.base/"test.sqlite3", data_dir=self.base/"data")
        self.learner = self.service.autolearn
        self.settings = dict(self.service.agent.settings)

    def tearDown(self):
        self.service.agent.stop()
        self.temp.cleanup()

    def rejected(self, symbol):
        return {"symbol":symbol, "validated":False, "historical_examples":0,
                "data_hours":750, "cost_signature":cost_signature(self.settings),
                "rejection_reasons":["Artificial fixture"]}

    def test_restart_reuses_pinned_download_cutoff_and_checkpoint(self):
        stamp = time.time()
        ends = []
        def history(*args, **kwargs):
            ends.append(kwargs["end_ms"])
            return candles(3000)
        def interrupted(*args, checkpoint, **kwargs):
            checkpoint["save"](0, {"marker":"completed"})
            raise InterruptedError("Fixture interruption")
        with patch("lab.autolearn.time.time", return_value=stamp), \
             patch.object(self.learner.downloader, "_history", side_effect=history), \
             patch("lab.autolearn.learn_history", side_effect=interrupted):
            with self.assertRaises(InterruptedError):
                self.learner.study(["BTC-USD"], self.settings)
        job = load_state(self.learner.db_path, "learning_job_BTC-USD")
        self.assertIsNotNone(job)
        restored = AutoLearner(self.learner.db_path, self.base/"data",
                               self.learner.agent, self.learner.research_manager)
        def resumed(*args, checkpoint, **kwargs):
            self.assertEqual(checkpoint["load"](0), {"marker":"completed"})
            return self.rejected("BTC-USD")
        with patch("lab.autolearn.time.time", return_value=stamp+3600), \
             patch.object(restored.downloader, "_history", side_effect=history), \
             patch("lab.autolearn.learn_history", side_effect=resumed):
            restored.study(["BTC-USD"], self.settings)
        self.assertEqual(ends[0], ends[1])
        self.assertIsNone(load_state(restored.db_path, "learning_job_BTC-USD"))
        self.assertIsNone(load_state(restored.db_path, "learning_candidate_"+job["fingerprint"]+"_0"))

    def test_unqualified_market_reviews_daily_without_retraining_qualified_market(self):
        stamp = time.time()
        profile = install(self.learner.db_path, self.settings)
        def learned(rows, symbol, *args, **kwargs):
            if symbol == "BTC-USD":
                return {**self.rejected(symbol), "validated":True, "interval":"15m",
                        "created_at":int(stamp), "model":profile["model"],
                        "data_quality":{"end_ts":int(stamp*1000)//900000*900000-900000}}
            return self.rejected(symbol)
        with patch.object(self.learner.downloader, "_history", return_value=candles(3000)) as history, \
             patch("lab.autolearn.learn_history", side_effect=learned) as train:
            with patch("lab.autolearn.time.time", return_value=stamp):
                self.learner.study(["BTC-USD", "ETH-USD"], self.settings)
            results = self.learner.state["results"]
            self.assertEqual(results[0]["next_review_at"], stamp+REVIEW_SECONDS)
            self.assertEqual(results[1]["next_review_at"], stamp+UNQUALIFIED_REVIEW_SECONDS)
            with patch("lab.autolearn.time.time", return_value=stamp+UNQUALIFIED_REVIEW_SECONDS):
                self.learner.study(["BTC-USD", "ETH-USD"], self.settings)
            self.assertEqual([c.args[:2] for c in history.call_args_list], [
                ("BTC-USD","15m"),("BTC-USD","1d"),("ETH-USD","15m"),("ETH-USD","1d"),
                ("ETH-USD","15m"),("ETH-USD","1d")])
            self.assertEqual(history.call_args.args[0], "ETH-USD")
            self.assertEqual(train.call_count, 2)  # identical prices reuse the completed result

    def test_changed_daily_risk_limit_invalidates_job_and_qualified_policy(self):
        install(self.learner.db_path, self.settings)
        old = self.learner._job("BTC-USD", self.settings)
        changed = {**self.settings, "daily_loss_limit":.02}
        new = self.learner._job("BTC-USD", changed)
        self.assertNotEqual(old["scope"], new["scope"])
        self.assertIsNone(current_policy(self.learner.db_path, "BTC-USD", changed))
