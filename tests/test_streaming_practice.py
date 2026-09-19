"""Bounded shadow retention must preserve every causal learning event."""
import copy
import unittest
from unittest.mock import patch

from lab.continuous import DEFAULTS
from lab.execution import simulate, simulation_steps
from lab.shadow_learning import HistoricalFeedback
from tests.test_adaptive import F
from tests.test_confirmation_continuity import one_candidate
from tests.test_execution import candles, features, PARAMS


class StreamingPracticeTests(unittest.TestCase):
    def test_streaming_preserves_outcomes_and_cooldowns_through_losses_and_gaps(self):
        rows = candles(1400)
        for i in range(241, 1400, 23):
            rows[i]['low'] = 90.
        for i in range(253, 1400, 23):
            rows[i]['high'] = 110.
        del rows[700:703]
        params = dict(PARAMS, loss_streak_limit=2, loss_cooldown_hours=6)
        for fee, slip in ((.004,.001), (.006,.0015)):
            runs = []
            for stream in (False,True):
                events, opened, diagnostics = [], [], []
                with patch('lab.engine.evaluate_signal', return_value=(70,None)):
                    result = simulate(rows, features(len(rows)), 240, len(rows),
                        500, .0075, fee, slip, params, bar_interval_ms=900000,
                        training_examples=True, stream_only=stream,
                        on_entry=lambda t:opened.append(t['entry_ts']),
                        on_resolved=lambda t,r,ts:events.append((copy.deepcopy(t),r,ts)),
                        on_training_event=lambda n,ts:diagnostics.append((n,ts)))
                if stream:
                    self.assertEqual(result, ({},[]))
                runs.append((events,opened,diagnostics))
            self.assertGreater(len(runs[0][0]), 25)
            self.assertEqual(*runs)

    def test_shadow_models_and_audits_match_full_retention(self):
        rows = candles(600)
        for i in range(241,600,13):
            rows[i]['low'] = 90.
        fs = [dict(F, _atr=5.) for _ in rows]
        snapshots = []
        for stream in (False, True):
            policy = one_candidate()
            def run(*args, **kwargs):
                return simulation_steps(*args, **dict(kwargs,stream_only=stream))
            with patch('lab.shadow_learning.simulation_steps', side_effect=run):
                feedback = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,900000)
                feedback.begin_reporting(rows[400]['ts'])
                feedback.advance(rows[-1]['ts']+900000)
            snapshots.append((policy.export(),feedback.summary()))
        self.assertEqual(*snapshots)

    def test_streaming_cannot_replace_an_account_ledger_or_drop_unconsumed_labels(self):
        for training, consumer in ((False,lambda *a:None),(True,None)):
            with self.subTest(training=training), self.assertRaises(ValueError):
                simulate(candles(),features(),240,260,500,.0075,.004,.001,PARAMS,
                    stream_only=True,training_examples=training,on_resolved=consumer)

    def test_streaming_preserves_daily_halts_when_a_caller_requests_them(self):
        rows = candles(800)
        for row in rows:
            row["low"] = 97.
        traces = []
        for stream in (False, True):
            events, entries = [], []
            with patch("lab.engine.evaluate_signal", return_value=(70, None)):
                metrics, _ = simulate(rows, features(len(rows)), 240, len(rows),
                    500, .02, .004, .001, PARAMS, bar_interval_ms=900000,
                    training_examples=True, stream_only=stream, daily_loss_limit=.003,
                    on_entry=lambda t:entries.append(t["entry_ts"]),
                    on_resolved=lambda t,r,ts:events.append((copy.deepcopy(t),r,ts)))
            if not stream:
                self.assertGreater(metrics["halted_utc_days"], 0)
                self.assertGreater(metrics["signal_funnel"]["rejections"]["daily_loss_limit"], 0)
            traces.append((events, entries))
        self.assertGreater(len(traces[0][0]), 1)
        self.assertEqual(*traces)
