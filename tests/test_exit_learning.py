"""Adversarial artificial price paths validate the experiment, not profitability."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from lab.adaptive import AdaptivePolicy, action_key, approved_profile, profile_key
from lab.continuous import DEFAULTS
from lab.engine import ENGINE_VERSION
from lab.execution import simulate
from lab.exit_management import BREAK_EVEN_EXIT
from lab.paper_store import init_continuous_db, save_state
from lab.research import cost_signature
from lab.shadow_learning import HistoricalFeedback
from tests.test_adaptive import F
from tests.test_execution import candles

STEP = 900000


class ExitLearningTests(unittest.TestCase):
    def fixture(self, scenario="reversal"):
        rows = candles(360)
        rows[241].update(open=100.,low=99.5,high=105.2,close=105.)
        rows[242].update(open=104.9,low=100.5,high=105.2,close=102.)
        rows[243].update(open=100.,low=96.,high=100.2,close=98.)
        fs = [dict(F,_atr=2.) if i==240 else None for i in range(len(rows))]
        if scenario == "wick":
            rows[241]["close"] = 100.5
            rows[242].update(open=100.5,low=96.,high=101.,close=98.)
        elif scenario == "ambiguous":
            rows[241]["low"] = 96.
        elif scenario == "gap":
            rows[242].update(open=95.,low=94.,high=96.,close=95.)
        elif scenario == "reentry":
            fs[243] = dict(F,_atr=2.,_close=98.)
            rows[244].update(open=98.,low=97.5,high=99.,close=98.)
            rows[245].update(low=94.)
        return rows,fs

    def run_path(self, rows, fs, managed=True, direction="LONG", **kwargs):
        p = dict(AdaptivePolicy().candidates[2],direction=direction)
        if managed:
            p["exit_policy"] = BREAK_EVEN_EXIT
        with patch("lab.engine.evaluate_signal",return_value=(70,None)):
            return simulate(rows,fs,240,len(rows),500,.0075,.004,.001,p,
                            bar_interval_ms=STEP,**kwargs)

    def test_next_bar_exit_covers_both_fees_and_slippage_without_reward_bonus(self):
        rows,fs=self.fixture()
        baseline,before=self.run_path(rows,fs,managed=False)
        metrics,trades=self.run_path(rows,fs)
        self.assertEqual(len(trades),1)
        t=trades[0]
        self.assertEqual(t['break_even_active_ts'],rows[242]['ts'])
        self.assertEqual(t['exit_ts'],rows[242]['ts'])
        self.assertEqual(t['reason'],'BREAK_EVEN_STOP')
        self.assertEqual(t['pnl'],0.)
        self.assertEqual(t['outcome'],'BREAK_EVEN')
        self.assertEqual(t['r_multiple'],0.)
        self.assertEqual(t['review']['outcome'],'near_break_even')
        self.assertGreater(t['fees_paid'],0.)
        self.assertEqual(t['gross_pnl'],t['fees_paid'])
        self.assertGreater(t['stop'],t['initial_stop'])
        self.assertEqual(t['target2'],before[0]['target2'])
        self.assertAlmostEqual(metrics['ending_balance'],500.)
        self.assertAlmostEqual(baseline['net_pnl'],-3.75)
        self.assertAlmostEqual(t['risk_dollars'],before[0]['risk_dollars'])

    def test_wick_and_ambiguous_entry_cannot_activate_protection(self):
        for scenario in ('wick','ambiguous'):
            with self.subTest(scenario=scenario):
                _,trades=self.run_path(*self.fixture(scenario))
                self.assertIsNone(trades[0]['break_even_active_ts'])
                self.assertEqual(trades[0]['reason'],'STOP')
                self.assertAlmostEqual(trades[0]['r_multiple'],-1.)

    def test_gap_still_loses_more_than_planned_risk(self):
        _,trades=self.run_path(*self.fixture('gap'))
        self.assertIsNotNone(trades[0]['break_even_active_ts'])
        self.assertEqual(trades[0]['reason'],'STOP_GAP')
        self.assertLess(trades[0]['r_multiple'],-1.)

    def test_missing_price_interval_stays_incomplete_after_protection(self):
        rows,fs=self.fixture()
        del rows[242];del fs[242]
        metrics,trades=self.run_path(rows,fs)
        self.assertFalse(metrics['complete'])
        self.assertIsNone(metrics['net_pnl'])
        self.assertEqual(trades,[])

    def test_full_account_includes_a_new_losing_entry_after_earlier_exit(self):
        rows,fs=self.fixture('reentry')
        ordinary,old=self.run_path(rows,fs,managed=False)
        alternative,new=self.run_path(rows,fs)
        self.assertEqual(len(old),1)
        self.assertEqual(len(new),2)
        self.assertEqual(new[0]['pnl'],0.)
        self.assertEqual(new[1]['entry_ts'],rows[244]['ts'])
        self.assertLess(new[1]['pnl'],0.)
        self.assertAlmostEqual(alternative['net_pnl'],ordinary['net_pnl'])
        self.assertAlmostEqual(sum(t['pnl'] for t in new),alternative['net_pnl'])

    def test_shadow_reward_arrives_only_after_the_actual_alternative_exit_closes(self):
        rows,fs=self.fixture()
        policy=AdaptivePolicy(fee_rate=.004,slippage_rate=.001,exit_policy=BREAK_EVEN_EXIT)
        policy.candidates=[policy.candidates[2]]
        with patch("lab.engine.evaluate_signal",return_value=(70,None)):
            feedback=HistoricalFeedback(rows,fs,240,len(rows),DEFAULTS,policy,STEP)
            feedback.advance(rows[242]['ts']+STEP-1)
            self.assertEqual(policy.state['observations'],0)
            feedback.advance(rows[242]['ts']+STEP)
            self.assertEqual(policy.state['observations'],1)
            self.assertEqual(policy.state['last_label_ts'],rows[242]['ts']+STEP)
            learned=policy.state['models'][action_key(policy.candidates[0])]
            self.assertEqual(learned['sum_r'],0.)
            self.assertEqual(learned['outcomes']['causes'],{'near_break_even':1})
            feedback.advance(rows[-1]['ts']+STEP)
            self.assertEqual(policy.state['observations'],1)

    def test_short_break_even_algebra_is_symmetric(self):
        rows,fs=self.fixture()
        for r in rows:
            o,h,l,c=(r[k] for k in ('open','high','low','close'))
            r.update(open=200-o,high=200-l,low=200-h,close=200-c)
        _,trades=self.run_path(rows,fs,direction='SHORT')
        self.assertEqual(trades[0]['pnl'],0.)
        self.assertLess(trades[0]['stop'],trades[0]['initial_stop'])

    def test_exit_models_cannot_mix_rewards_or_be_approved_for_trading(self):
        fixed=AdaptivePolicy()
        managed=AdaptivePolicy(exit_policy=BREAK_EVEN_EXIT)
        self.assertNotEqual(action_key(fixed.candidates[0]),action_key(managed.candidates[0]))
        state=managed.export()
        restored=AdaptivePolicy(json.loads(json.dumps(state)),exit_policy=BREAK_EVEN_EXIT)
        self.assertEqual(restored.export(),state)
        with self.assertRaises(ValueError):AdaptivePolicy(state)
        with self.assertRaises(ValueError):AdaptivePolicy(fixed.export(),exit_policy=BREAK_EVEN_EXIT)
        with self.assertRaises(ValueError):AdaptivePolicy(exit_policy='unknown')
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'test.db';init_continuous_db(db)
            save_state(db,profile_key('BTC-USD'),{'engine_version':ENGINE_VERSION,
                'cost_signature':cost_signature(DEFAULTS),'data_end_ts':int(time.time()*1000),
                'model':state})
            self.assertIsNone(approved_profile(db,'BTC-USD',DEFAULTS))


if __name__=='__main__':unittest.main()
