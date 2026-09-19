"""Reporting cutoffs must not reset learning, forecasts or practice occupancy."""
import copy
import unittest
from unittest.mock import patch

from lab.adaptive import AdaptivePolicy
from lab.continuous import DEFAULTS
from lab.execution import simulate
from lab.learning_research import learn_history
from lab.shadow_learning import HistoricalFeedback
from tests.test_adaptive import F, trained_state
from tests.test_execution import candles

STEP = 900000


def one_candidate():
    policy = AdaptivePolicy(trained_state(), fee_rate=.004, slippage_rate=.001)
    policy.candidates = [policy.candidates[0]]
    return policy


class PracticeContinuityTests(unittest.TestCase):
    def carried_fixture(self):
        rows = candles(270)
        rows[250]['low'] = 90.
        features = [dict(F, _atr=5.) if i == 240 else None for i in range(len(rows))]
        return rows, features

    def test_open_example_and_original_forecast_survive_boundary(self):
        rows, features = self.carried_fixture()
        policy = one_candidate()
        observed = []
        original = policy.observe
        def capture(params, vector, reward, available_ts, outcome=None):
            observed.append((available_ts, copy.deepcopy(outcome['entry_forecast'])))
            return original(params, vector, reward, available_ts, outcome)
        policy.observe = capture
        feedback = HistoricalFeedback(rows, features, 240, len(rows), DEFAULTS, policy, STEP)
        boundary = rows[245]['ts']
        feedback.begin_reporting(boundary)
        self.assertEqual(feedback.summary()['resolved_examples'], 0)
        feedback.advance(rows[250]['ts'])
        self.assertFalse(observed)
        feedback.advance(rows[250]['ts']+STEP)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][0], rows[250]['ts']+STEP)
        self.assertEqual(observed[0][1]['signal_close_ts'], rows[241]['ts'])
        self.assertLess(observed[0][1]['model_last_label_ts'], boundary)
        group = feedback.summary()['by_entry_period']['carried_in']
        self.assertEqual(group['resolved_examples'], 1)
        self.assertEqual(group['net_losses'], 1)
        self.assertEqual(group['by_practice_lane']['eligible']['resolved_examples'], 1)
        reference = one_candidate()
        uninterrupted = HistoricalFeedback(rows, features, 240, len(rows), DEFAULTS, reference, STEP)
        uninterrupted.advance(rows[-1]['ts']+STEP)
        feedback.advance(rows[-1]['ts']+STEP)
        self.assertEqual(policy.export(), reference.export())
        self.assertEqual(feedback.summary()['prediction_audit'], uninterrupted.summary()['prediction_audit'])
        before = policy.export()
        feedback.advance(rows[-1]['ts']+STEP)
        self.assertEqual(policy.export(), before)
        self.assertEqual(feedback.count, 1)

    def test_future_outcome_cannot_change_boundary_model_or_forecast(self):
        snapshots = []
        for low in (90., 10.):
            rows, features = self.carried_fixture()
            rows[250]['low'] = low
            policy = one_candidate()
            feedback = HistoricalFeedback(rows, features, 240, len(rows), DEFAULTS, policy, STEP)
            feedback.begin_reporting(rows[245]['ts'])
            snapshots.append((policy.export(), feedback.summary()))
        self.assertEqual(*snapshots)

    def test_cooldown_and_exact_boundary_closure_are_preserved(self):
        rows = candles(250)
        rows[241]['low'] = rows[243]['low'] = 90.
        features = [dict(F, _atr=5.) if i in (240, 242) else None for i in range(len(rows))]
        policy = one_candidate()
        policy.candidates[0]['cooldown_minutes'] = 60
        feedback = HistoricalFeedback(rows, features, 240, len(rows), DEFAULTS, policy, STEP)
        feedback.begin_reporting(rows[242]['ts'])  # first outcome resolves exactly here
        self.assertEqual(policy.state['observations'], 81)
        feedback.advance(rows[-1]['ts']+STEP)
        self.assertEqual(feedback.count, 0)
        self.assertEqual(len(feedback.seen_entries), 1)
        reset_policy = one_candidate()
        reset_policy.candidates[0]['cooldown_minutes'] = 60
        reset = HistoricalFeedback(rows, features, 242, len(rows), DEFAULTS, reset_policy, STEP)
        reset.advance(rows[-1]['ts']+STEP)
        self.assertEqual(reset.count, 1)  # reproduces the spurious post-reset entry

    def test_gap_censor_counts_only_events_in_the_window(self):
        rows = candles(270)
        # Two unresolved positions encounter separate gaps, one per report period.
        signal_times = {rows[240]['ts'], rows[252]['ts']}
        del rows[256]
        del rows[245]
        features = [dict(F, _atr=5.) if r['ts'] in signal_times else None for r in rows]
        policy = one_candidate()
        feedback = HistoricalFeedback(rows, features, 240, len(rows), DEFAULTS, policy, STEP)
        boundary = next(r['ts'] for r in rows if r['ts'] >= rows[0]['ts']+250*STEP)
        feedback.advance(boundary)
        self.assertEqual(feedback.summary()['gap_censored_examples'], 1)
        feedback.begin_reporting(boundary)
        feedback.advance(rows[-1]['ts']+STEP)
        self.assertEqual(feedback.summary()['gap_censored_examples'], 1)
        self.assertEqual(feedback.count, 0)
        self.assertEqual(policy.state['observations'], 80)

    def test_loss_pause_counts_only_events_in_the_window(self):
        rows = candles(250)
        rows[241]['low'] = rows[245]['low'] = 90.
        features = [dict(F, _atr=5.) if i in (240, 244) else None for i in range(len(rows))]
        policy = one_candidate()
        policy.candidates[0].update(cooldown_minutes=15, loss_streak_limit=1, loss_cooldown_hours=6)
        feedback = HistoricalFeedback(rows, features, 240, len(rows), DEFAULTS, policy, STEP)
        feedback.advance(rows[243]['ts'])
        self.assertEqual(feedback.summary()['loss_pause_overrides'], 1)
        feedback.begin_reporting(rows[243]['ts'])
        feedback.advance(rows[-1]['ts']+STEP)
        self.assertEqual(feedback.summary()['loss_pause_overrides'], 1)
        self.assertEqual(feedback.summary()['by_entry_period']['new_entry']['resolved_examples'], 1)


class ConfirmationReportTests(unittest.TestCase):
    def fixture(self):
        rows = candles(3000)
        entries = (300, 1200, 1800, 2500, 2600, 2900)
        for i in entries:
            rows[i+40]['low'] = 90.
        features = [dict(F, _atr=5.) if i in entries else None for i in range(len(rows))]
        return rows, features

    def replay(self, rows, features, boundary):
        with patch('lab.learning_research.build_learning_features', return_value=features):
            return learn_history(rows, 'TEST-USD', dict(DEFAULTS), reviewed_through_ts=boundary,
                exit_comparison=False, selection_comparison=False)

    def test_saved_model_is_independent_of_report_review_boundary(self):
        rows, features = self.fixture()
        with_confirmation = self.replay(rows, features, rows[2520]['ts'])
        without = self.replay(rows, features, rows[-1]['ts']+STEP)
        self.assertEqual(with_confirmation['model'], without['model'])
        self.assertEqual(with_confirmation['holdout_trades'], without['holdout_trades'])
        self.assertEqual(with_confirmation['model']['observations'],
            with_confirmation['historical_examples']+with_confirmation['holdout_learning_updates'])
        fresh = with_confirmation['evaluation']['confirmation']
        self.assertGreater(fresh['metrics']['feedback']['by_entry_period']['carried_in']['resolved_examples'], 0)
        self.assertEqual(fresh['metrics']['trades'], 0)
        self.assertFalse(with_confirmation['validated'])
        self.assertIsNone(without['evaluation']['confirmation'])

    def test_each_cost_scenario_and_its_control_share_the_same_prefix(self):
        rows, features = self.fixture()
        seeds = {}
        def inspect(*args, **kwargs):
            if not kwargs.get('training_examples') and args[2] == 2650:
                kind = (args[6], kwargs.get('feedback') is not None)
                seeds[kind] = kwargs['policy'].export()
            return simulate(*args, **kwargs)
        with patch('lab.learning_research.simulate', side_effect=inspect):
            result = self.replay(rows, features, rows[2650]['ts'])
        for fee in (.004, .006):
            self.assertEqual(seeds[(fee, True)], seeds[(fee, False)])
            self.assertLessEqual(seeds[(fee, True)]['last_label_ts'], rows[2650]['ts'])
        self.assertNotEqual(seeds[(.004, True)], seeds[(.006, True)])
        self.assertLessEqual(result['evaluation']['confirmation']['stressed_training_label_end_ts'], rows[2650]['ts'])


if __name__ == '__main__':
    unittest.main()
