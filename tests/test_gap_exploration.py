"""Gap and exploration regressions using fixtures, not market-performance evidence."""
import copy
import json
import unittest
from unittest.mock import patch

from lab.continuous import DEFAULTS
from lab.engine import build_feature_cache
from lab.execution import simulate
from lab.learning_data import prepare_learning_history
from lab.learning_research import build_learning_features, learn_history
from tests.test_adaptive import F
from tests.test_execution import PARAMS, candles, features

STEP = 900000


class GapFeatureTests(unittest.TestCase):
    def test_indicators_restart_without_filling_or_revising_earlier_prices(self):
        rows = candles(3200)
        del rows[1000]
        original = copy.deepcopy(rows)
        selected, _, coverage = prepare_learning_history(rows, "15m")
        result = build_learning_features(selected, "15m", coverage["segments"])
        self.assertEqual(rows, original)
        self.assertEqual(len(result), len(rows))
        self.assertTrue(all(f is None for f in result[1000:1240]))
        self.assertIsNotNone(result[1240])
        standalone = build_feature_cache(rows[1000:], "15m", simple_only=True)["features"]
        self.assertEqual(result[1240:], standalone[240:])
        rows[2500]["high"] = 500
        revised = build_learning_features(rows, "15m", coverage["segments"])
        self.assertEqual(result[:2500], revised[:2500])

    def test_history_fragmented_below_warmup_is_rejected(self):
        rows = [r for i, r in enumerate(candles(4000)) if i % 200 != 199]
        with self.assertRaisesRegex(ValueError, "indicator warmup"):
            prepare_learning_history(rows, "15m")

    def test_short_sections_are_preserved_without_signal_features(self):
        rows = candles(3300)
        del rows[100]
        selected, _, coverage = prepare_learning_history(rows, "15m")
        result = build_learning_features(selected, "15m", coverage["segments"])
        self.assertEqual(coverage["used_candles"], 3299)
        self.assertEqual(coverage["warmup_candles"], 340)
        self.assertTrue(all(f is None for f in result[:340]))
        self.assertIsNotNone(result[340])


class ExplorationExecutionTests(unittest.TestCase):
    def run_sim(self, rows, fs=None, training=False, params=None, **kwargs):
        with patch("lab.engine.evaluate_signal", return_value=(70, None)):
            return simulate(rows, fs or features(len(rows)), 240, len(rows),
                500, .0075, .004, .001, params or PARAMS,
                training_examples=training, bar_interval_ms=STEP, **kwargs)

    def test_exploration_charges_full_costs_while_account_entries_stay_blocked(self):
        for params, reason in ((dict(PARAMS, max_cost_r=.01), "trading_cost_too_high"),
                               (dict(PARAMS, min_net_rr=10), "net_reward_too_small")):
            with self.subTest(reason=reason):
                rows = candles(245)
                fs = [None]*len(rows)
                fs[240] = features(len(rows))[240]
                account, account_trades = self.run_sim(rows, fs, params=params)
                self.assertFalse(account_trades)
                self.assertEqual(account["signal_funnel"]["entry_rejections"], {reason:1})
                metrics, trades = self.run_sim(rows, fs, training=True, params=params)
                self.assertEqual(len(trades), 1)
                trade = trades[0]
                self.assertAlmostEqual(trade["entry"], 100*1.001)
                self.assertAlmostEqual(trade["exit"], 100*.999)
                expected_fees = (trade["entry"]+trade["exit"])*trade["qty"]*.004
                expected_pnl = (trade["exit"]-trade["entry"])*trade["qty"]-expected_fees
                self.assertAlmostEqual(trade["fees_paid"], expected_fees)
                self.assertAlmostEqual(trade["pnl"], expected_pnl)
                self.assertLess(trade["r_multiple"], 0)
                self.assertEqual(trade["training_cost_override"], reason)
                self.assertEqual(metrics["signal_funnel"]["training_cost_overrides"], {reason:1})

    def test_exploration_cannot_bypass_price_gap_or_signal_checks(self):
        rows = candles(245)
        rows[241].update(open=130, high=131, low=129, close=130)
        fs = [None]*len(rows)
        fs[240] = features(len(rows))[240]
        metrics, trades = self.run_sim(rows, fs, training=True)
        self.assertFalse(trades)
        self.assertEqual(metrics["signal_funnel"]["entry_rejections"], {"entry_gap_too_large":1})
        with patch("lab.engine.evaluate_signal", return_value=(None, "no_setup")):
            metrics, trades = simulate(candles(245), fs, 240, 245, 500, .0075, .004,
                .001, PARAMS, training_examples=True, bar_interval_ms=STEP)
        self.assertFalse(trades)
        self.assertEqual(metrics["signal_funnel"]["rejections"], {"no_setup":1})

    def test_no_entry_uses_a_candle_beyond_missing_prices(self):
        rows = candles(245)
        del rows[241]
        fs = [None]*len(rows)
        fs[240] = features(len(rows))[240]
        for training in (False, True):
            metrics, trades = self.run_sim(rows, fs, training=training)
            self.assertFalse(trades)
            self.assertTrue(metrics["complete"])
            self.assertEqual(metrics["signal_funnel"]["rejections"], {"missing_market_candles":1})

    def test_unknown_training_outcome_is_excluded_and_later_section_can_learn(self):
        rows = candles(500)
        del rows[243]
        fs = [None]*len(rows)
        fs[240] = features(len(rows))[240]
        fs[490] = features(len(rows))[490]
        rows[492].update(low=95)
        metrics, trades = self.run_sim(rows, fs, training=True)
        self.assertEqual(metrics["signal_funnel"]["gap_censored_examples"], 1)
        self.assertEqual(metrics["signal_funnel"]["entries_opened"], 2)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["entry_ts"], rows[491]["ts"])
        self.assertEqual(trades[0]["exit_ts"], rows[492]["ts"])
        self.assertEqual(trades[0]["reason"], "STOP")

    def test_account_stops_at_unknown_position_without_inventing_profit_or_label(self):
        rows = candles(500)
        del rows[243]
        metrics, trades = self.run_sim(rows)
        self.assertFalse(metrics["complete"])
        self.assertFalse(trades)
        self.assertEqual(metrics["stopped_at_ts"], rows[242]["ts"]+STEP)
        self.assertEqual(metrics["unresolved_positions"], 1)
        self.assertIsNone(metrics["net_pnl"])
        self.assertIsNone(metrics["ending_balance"])
        self.assertIsNone(metrics["max_drawdown_pct"])
        json.dumps(metrics, allow_nan=False)
        # Future outcomes cannot repair an unknown position or create an exit.
        rows[-1].update(high=500, close=500)
        later = self.run_sim(rows)
        self.assertEqual((metrics, trades), later)

    def test_training_account_mode_cannot_be_used_with_a_policy(self):
        with self.assertRaisesRegex(ValueError, "policy account"):
            self.run_sim(candles(245), training=True, policy=object())


class IncompleteQualificationTests(unittest.TestCase):
    def test_incomplete_final_or_validation_period_cannot_qualify(self):
        rows = candles(5000)
        for blocked_period in ("final", "validation"):
            with self.subTest(blocked_period=blocked_period):
                def fake_sim(data, fs, start, end, balance, risk, fee, slip, params, **kwargs):
                    training = kwargs.get("training_examples", False)
                    indices = [240+i*35 for i in range(100)] if training else [start+i for i in range(40)]
                    trades = [{"features":F, "r_multiple":1., "pnl":1., "entry_ts":data[i]["ts"],
                        "exit_ts":data[i]["ts"], "strategy_family":params["family"],
                        "reason":"TARGET2"} for i in indices]
                    complete = training or (start >= 4000) != (blocked_period == "final")
                    metrics = {"complete":complete, "net_pnl":40. if complete else None,
                        "return_pct":8. if complete else None, "trades":len(trades),
                        "max_drawdown_pct":0 if complete else None, "expectancy_r":1.}
                    return metrics, trades
                with patch("lab.learning_research.simulate", side_effect=fake_sim), patch(
                        "lab.learning_research.build_feature_cache", return_value={"features":[{}]*len(rows)}):
                    result = learn_history(rows, "BTC-USD", dict(DEFAULTS))
                self.assertFalse(result["validated"])
                self.assertTrue(any("gap" in r or "missing candles" in r for r in result["rejection_reasons"]))
                if blocked_period == "final":
                    self.assertIsNone(result["learning_pnl_difference"])
                    self.assertIsNone(result["upgrade_comparison"]["net_pnl_difference"])
                    self.assertIsNone(result["daily_goal"]["mean_net_per_day"])
                json.dumps(result, allow_nan=False)
