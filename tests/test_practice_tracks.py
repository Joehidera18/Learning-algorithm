"""Practice coverage and delayed learning, not evidence of investment returns."""
import json
import unittest

from lab.adaptive import AdaptivePolicy, action_key
from lab.chronological_learning import ChronologicalTrainer
from lab.continuous import DEFAULTS
from lab.execution import simulate
from lab.shadow_learning import HistoricalFeedback
from lab.trade_quality import signal_cost_check
from tests.test_adaptive import F
from tests.test_execution import candles

STEP = 900000


class PracticeTrackTests(unittest.TestCase):
    def fixture(self):
        rows = candles(250)
        for row in rows:
            row.update(open=100., high=100.2, low=99.9, close=100.)
        rows[243].update(low=90.)
        fs = [None]*len(rows)
        fs[240] = dict(F, _atr=.2)
        fs[242] = dict(F, _atr=5.)
        return rows, fs, AdaptivePolicy().candidates[0]

    def run_track(self, lane, rows=None, fs=None):
        base_rows, base_fs, params = self.fixture()
        return simulate(rows or base_rows, fs or base_fs, 240, len(base_rows),
            500, .0075, .004, .001, params, training_examples=True,
            bar_interval_ms=STEP, practice_cost_mode=lane)

    def test_blocked_position_cannot_occupy_later_eligible_practice(self):
        rows, fs, params = self.fixture()
        self.assertIsNotNone(signal_cost_check(fs[240],params,.004,.001)[1])
        self.assertIsNone(signal_cost_check(fs[242],params,.004,.001)[1])
        _, original = self.run_track('all')
        _, eligible = self.run_track('eligible')
        _, blocked = self.run_track('cost_blocked')
        self.assertEqual([t['entry_ts'] for t in original], [rows[241]['ts']])
        self.assertEqual([t['entry_ts'] for t in eligible], [rows[243]['ts']])
        self.assertEqual([t['entry_ts'] for t in blocked], [rows[241]['ts']])
        for t in eligible+blocked:
            self.assertEqual(t['reason'],'STOP')
            self.assertAlmostEqual(t['r_multiple'],-1.)
            self.assertAlmostEqual(t['gross_pnl']-t['fees_paid'],t['pnl'])
        self.assertEqual(original[0]['pnl'],blocked[0]['pnl'])

    def test_exact_entry_cannot_belong_to_both_tracks(self):
        _, eligible = self.run_track('eligible')
        _, blocked = self.run_track('cost_blocked')
        self.assertFalse({t['entry_ts'] for t in eligible} & {t['entry_ts'] for t in blocked})
        self.assertTrue(all(t['practice_lane']=='eligible' and not t['training_cost_override'] for t in eligible))
        self.assertTrue(all(t['practice_lane']=='cost_blocked' and t['training_cost_override'] for t in blocked))

    def test_practice_mode_cannot_bypass_account_cost_checks(self):
        rows, fs, params = self.fixture()
        with self.assertRaises(ValueError):
            simulate(rows,fs,240,len(rows),500,.0075,.004,.001,params,practice_cost_mode='eligible')
        with self.assertRaises(ValueError): self.run_track('unknown')
        _, account = simulate(rows,fs,240,len(rows),500,.0075,.004,.001,params,bar_interval_ms=STEP)
        self.assertEqual([t['entry_ts'] for t in account],[rows[243]['ts']])

    def test_signal_and_fill_must_both_pass_cost_rules(self):
        for atr, next_open in ((3.,99.),(3.04,101.)):
            with self.subTest(atr=atr,next_open=next_open):
                rows,fs,_=self.fixture()
                fs[240]=dict(F,_atr=atr)
                fs[242]=None
                rows[241].update(open=next_open,high=max(next_open,100.2),low=min(next_open,99.9))
                # One case fails at the signal and passes at the fill; the other
                # passes at the signal and fails at the fill. Neither is eligible.
                _,eligible=self.run_track('eligible',rows,fs)
                _,blocked=self.run_track('cost_blocked',rows,fs)
                self.assertFalse(eligible)
                self.assertEqual(len(blocked),1)
                self.assertEqual(blocked[0]['training_cost_override'],'net_reward_too_small')

    def test_both_tracks_wait_for_closure_and_count_each_reward_once(self):
        rows, fs, _ = self.fixture()
        policy = AdaptivePolicy(fee_rate=.004,slippage_rate=.001)
        feedback = HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
        feedback.advance(rows[243]['ts'])
        self.assertEqual(policy.state['observations'],0)
        feedback.advance(rows[243]['ts']+STEP)
        summary=feedback.summary()
        self.assertGreater(summary['by_practice_lane']['eligible']['resolved_examples'],0)
        self.assertGreater(summary['by_practice_lane']['cost_blocked']['resolved_examples'],0)
        count=sum(v['resolved_examples'] for v in summary['by_practice_lane'].values())
        self.assertEqual(count,policy.state['observations'])
        before=policy.export()
        feedback.advance(rows[243]['ts']+STEP)
        self.assertEqual(policy.export(),before)
        self.assertEqual(AdaptivePolicy(json.loads(json.dumps(before))).export(),before)

    def test_future_candles_cannot_change_earlier_updates(self):
        rows, fs, _ = self.fixture()
        before=[]
        for future_low in (90.,10.):
            rows[243]['low']=future_low
            policy=AdaptivePolicy(fee_rate=.004,slippage_rate=.001)
            feedback=HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
            feedback.advance(rows[243]['ts'])
            before.append((policy.export(),feedback.summary()))
        self.assertEqual(*before)

    def test_duplicate_training_entries_are_rejected(self):
        p=AdaptivePolicy()
        label=(2,0,[0.]*27,-1.,{},1)
        with self.assertRaises(ValueError): ChronologicalTrainer(p,p.candidates,[label,label])

    def test_simultaneous_closures_are_independent_of_collection_order(self):
        from lab.adaptive import feature_vector
        from tests.test_adaptive import trained_state
        labels=[(200,0,feature_vector(F),-1.,{},100),(200,0,feature_vector(F),1.,{},110)]
        models=[]
        for data in (labels,list(reversed(labels))):
            p=AdaptivePolicy(trained_state())
            trainer=ChronologicalTrainer(p,p.candidates,data)
            trainer.advance(200)
            models.append((p.export(),trainer.predictions.summary()))
        self.assertEqual(*models)


if __name__=='__main__': unittest.main()
