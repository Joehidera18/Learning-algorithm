"""Prospective registration, immutable input replay and independent account tests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab.continuous import ContinuousLearner
from lab.event_store import EventCollector
from lab.forward_study import ForwardStudies, append_observations, build_inputs, evaluate, validated_candles, DAY
from lab.paper_store import save_state, load_state
from lab.research import ResearchManager, cost_signature
from lab.autolearn import AutoLearner
from lab.service import Service
from tests.test_adaptive import F, trained_state
from tests.test_execution import candles

ROOT=Path(__file__).resolve().parents[1]
STEP=900000


def protocol(rows):
    return {"interval":"15m","symbol":"BTC-USD","start_ts":rows[240]["ts"]+STEP,
        "end_ts":rows[240]["ts"]+STEP+30*DAY,"model":trained_state(),
        "settings":{"fee_rate":.001,"slippage_rate":.0005,"risk_per_trade":.0075,
            "max_notional_fraction":.3,"daily_loss_limit":.03},"assumed_half_spread":.0005}


class ForwardReplayTests(unittest.TestCase):
    def test_only_normal_closures_teach_and_open_marks_are_separate(self):
        rows=candles(350); p=protocol(rows); original=copy.deepcopy(p)
        inputs={"rows":rows[:250],"features":[dict(F) for _ in rows[:250]]}
        early=evaluate(p,inputs)
        for a in early["accounts"].values():
            self.assertEqual(a["closed"]["closed_trades"],0)
            self.assertEqual(a["open_positions"],1)
            self.assertEqual(a["model_updates"],0)
            self.assertEqual(a["trades"][0]["reason"],"END")
            self.assertGreaterEqual(a["trades"][0]["entry_ts"],p["start_ts"])
        later=evaluate(p,{"rows":rows,"features":[dict(F) for _ in rows]})
        updating=later["accounts"]["updating"]
        self.assertGreater(updating["closed"]["closed_trades"],0)
        self.assertEqual(updating["model_updates"],updating["closed"]["closed_trades"])
        self.assertEqual(later["accounts"]["frozen"]["model_updates"],0)
        self.assertEqual(later["accounts"]["frozen"]["model_sha256"],early["accounts"]["frozen"]["model_sha256"])
        for a in later["accounts"].values():
            self.assertEqual(a["fill_audit_failures"],0)
            self.assertAlmostEqual(a["closed"]["net_pnl"]+a["open_mark_pnl"],a["metrics"]["net_pnl"])
        self.assertEqual(p,original)
        self.assertFalse(later["validated"])

    def test_prices_after_normal_closure_do_not_change_that_trade(self):
        rows=candles(350); p=protocol(rows)
        first=evaluate(p,{"rows":rows,"features":[dict(F) for _ in rows]})
        trade=first["accounts"]["updating"]["trades"][0]
        for r in rows:
            if r["ts"]>trade["exit_ts"]:
                r.update(open=80,high=100,low=70,close=90)
        second=evaluate(p,{"rows":rows,"features":[dict(F) for _ in rows]})
        self.assertEqual(trade,second["accounts"]["updating"]["trades"][0])

    def test_gap_with_open_position_has_no_known_account_result(self):
        rows=candles(250);p=protocol(rows);del rows[244]
        result=evaluate(p,{"rows":rows,"features":[dict(F) for _ in rows]})
        self.assertIsNone(result["equity_pnl_difference"])
        self.assertEqual(result["missing_execution_candles"],1)
        for a in result["accounts"].values():
            self.assertFalse(a["metrics"]["complete"])
            self.assertIsNone(a["open_mark_pnl"])
            self.assertEqual(a["model_updates"],0)

    def test_future_labels_are_rejected_and_trailing_missing_candles_are_counted(self):
        rows=candles(250);p=protocol(rows)
        inputs={"rows":rows,"features":[dict(F) for _ in rows],
            "collected_through_ts":rows[-1]["ts"]+4*STEP}
        result=evaluate(p,inputs)
        self.assertEqual(result["missing_execution_candles"],3)
        p["model"]["last_label_ts"]=p["start_ts"]+1
        with self.assertRaisesRegex(ValueError,"labels after"):
            evaluate(p,inputs)

    def test_candles_reject_revisions_late_insertions_and_unfinished_data(self):
        rows=validated_candles(candles(5),STEP,1700000000000)
        self.assertEqual(append_observations(rows[:3],rows[2:]),rows)
        revised=copy.deepcopy(rows);revised[1]["volume"]+=1
        with self.assertRaisesRegex(ValueError,"changed"):append_observations(rows,revised)
        with self.assertRaisesRegex(ValueError,"Late"):append_observations(rows[:1]+rows[2:],rows)
        for wrong in ([rows[0],rows[0]], [{**rows[0],"high":50}], [{**rows[0],"volume":float("nan")}], [{**rows[0],"ts":True}]):
            with self.subTest(rows=wrong),self.assertRaises(ValueError):validated_candles(wrong,STEP,1700000000000)
        with self.assertRaises(ValueError):validated_candles(rows,STEP,rows[-1]["ts"]+1)

    def test_signal_features_are_sealed_against_later_context_changes(self):
        rows=candles(350);p=protocol(rows)
        first=build_inputs(p,{},rows[:300],[],[],None)
        with patch('lab.forward_study.build_learning_features',return_value=[dict(F,rsi=99) for _ in rows]):
            second=build_inputs(p,first,rows[299:],[],[],None)
        self.assertEqual(second["features"][:300],first["features"])
        self.assertEqual(second["features"][300]["rsi"],99)
        self.assertEqual(second["rows"],validated_candles(rows,STEP,p["end_ts"]))


class ForwardPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'account.db'
        self.agent=ContinuousLearner(self.db,Path(self.tmp.name)/'data')
        self.agent.configure({"fee_rate":.001})
        self.learner=AutoLearner(self.db,self.agent.data_dir,self.agent,ResearchManager(self.db,self.agent.data_dir))
        self.events=EventCollector(self.db)
        self.study=ForwardStudies(self.db,self.learner,self.events)
        self.rows=candles(750)
        self.now=self.rows[499]["ts"]+STEP-1
        self.fingerprint='a'*64
        self.report={"symbol":"BTC-USD","interval":"15m","fingerprint":self.fingerprint,
            "cost_signature":cost_signature(self.agent.settings),"model":trained_state(),"validated":False}
        save_state(self.db,'learning_result_'+self.fingerprint,self.report)
        self.learner.state['results']=[self.report]

    def tearDown(self):
        self.study.shutdown();self.tmp.cleanup()

    def start(self):
        with patch.object(self.study,'resume'):
            return self.study.start('BTC-USD','15m',self.fingerprint,self.now)

    def test_register_freezes_seed_dates_costs_and_keeps_failed_attempts(self):
        ident=self.start();record=self.study.export(ident)
        p=record['protocol']
        self.assertGreater(p['start_ts'],self.now)
        self.assertEqual(p['end_ts']-p['start_ts'],30*DAY)
        self.agent.configure({'fee_rate':.002})
        self.report['model']['observations']+=123
        self.assertEqual(self.study.export(ident),record)
        self.assertEqual(record['protocol']['settings']['fee_rate'],.001)
        self.study.stop()
        self.assertEqual(self.study.export(ident)['status'],'stopped_early')
        self.assertEqual(self.study.status()['registered_studies'],1)
        self.assertEqual(load_state(self.db,'validated_profiles',{}),{})

    def test_rejects_duplicate_registration_and_cost_mismatch(self):
        self.start()
        with self.assertRaisesRegex(ValueError,'active'):self.start()
        self.study.stop();self.agent.configure({'fee_rate':.002})
        with self.assertRaisesRegex(ValueError,'Fees or risk'):self.start()
        self.assertEqual(self.study.status()['registered_studies'],1)

    def test_refresh_resume_and_export_reproduce_exact_results(self):
        ident=self.start()
        def fetch(symbol,interval,start,cutoff):
            return [r for r in self.rows if start<=r['ts']<cutoff] if interval=='15m' else []
        with patch.object(self.study,'_fetch',side_effect=fetch),patch('lab.forward_study.build_learning_features',side_effect=lambda rows,*a,**k:[dict(F) for _ in rows]):
            self.study.refresh(self.rows[530]['ts'])
            before=self.study.export(ident)
            self.study.refresh(self.rows[600]['ts'])
            after=self.study.export(ident)
        self.assertEqual(after['protocol'],before['protocol'])
        self.assertEqual(after['result'],evaluate(after['protocol'],after['inputs']))
        fresh=ForwardStudies(self.db,self.learner,self.events)
        self.assertEqual(fresh.export(ident),after)
        self.assertEqual(after['result']['accounts']['frozen']['model_updates'],0)
        self.assertIsNone(load_state(self.db,'continuous_portfolio'))
        self.assertEqual(self.agent.portfolio['completed_trades'],0)

    def test_source_change_stops_evaluation_without_discarding_the_record(self):
        ident=self.start()
        with patch('lab.forward_study.source_digest',return_value='different'):
            self.study.refresh(self.now+STEP)
        self.assertEqual(self.study.export(ident)['status'],'code_changed')
        self.assertEqual(self.study.export(ident)['result'],{})

    def test_collection_finishes_at_the_registered_end_even_after_an_outage(self):
        ident=self.start()
        p=self.study.export(ident)['protocol']
        rows=candles(3500)
        def fetch(symbol,interval,start,cutoff):
            self.assertLessEqual(cutoff,p['end_ts'])
            return [r for r in rows if start<=r['ts']<cutoff] if interval=='15m' else []
        with patch.object(self.study,'_fetch',side_effect=fetch),patch('lab.forward_study.build_learning_features',side_effect=lambda rows,*a,**k:[dict(F) for _ in rows]):
            self.study.refresh(p['end_ts']+2*DAY)
        record=self.study.export(ident)
        self.assertEqual(record['status'],'completed')
        self.assertEqual(record['result']['last_candle_close_ts'],p['end_ts'])
        self.assertEqual(record['result']['missing_execution_candles'],0)
        self.assertEqual(record['result']['expected_execution_candles'],2880)
        self.study.refresh(p['end_ts']+4*DAY)
        self.assertEqual(self.study.export(ident),record)

    def test_api_inherits_auth_and_does_not_accept_backdated_start(self):
        service=Service(ROOT,self.db,self.agent.data_dir,token='test-access-token-123456')
        self.assertEqual(service.handle('GET','/api/forward/status')[0],401)
        headers={'authorization':'Bearer test-access-token-123456','content-type':'application/json'}
        code,_,_=service.handle('POST','/api/forward/start',body={'symbol':'BTC-USD','interval':'15m',
            'fingerprint':self.fingerprint,'start_ts':0},headers=headers)
        self.assertEqual(code,400)
        self.assertEqual(service.forward.status()['registered_studies'],0)


if __name__=='__main__':unittest.main()
