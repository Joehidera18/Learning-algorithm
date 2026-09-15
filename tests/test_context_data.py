"""Data repairs require real observations; synthetic fixtures test the rules."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from lab.continuous import ContinuousLearner, DEFAULTS
from lab.daily_context import DAY_MS, daily_context, independent_daily_context
from lab.data_repair import repair_history, aggregate_complete
from lab.learning_research import build_learning_features
from lab.research import ResearchManager
from lab.autolearn import AutoLearner
from lab.paper_store import init_continuous_db
from tests.test_execution import candles
from tests.test_swing_strategies import hourly, HOUR


class RepairTests(unittest.TestCase):
    def test_direct_retry_and_complete_smaller_candles_recover_exact_ohlcv(self):
        step=900000; rows=candles(8); missing=rows[3]["ts"]
        observed=rows[:3]+rows[4:]
        client=Mock()
        client.candles.return_value=rows[2:5]
        recovered, report=repair_history(client,"DOT-USD","15m",observed)
        self.assertEqual(recovered,rows)
        self.assertEqual(report["recovered_direct"],1)
        self.assertEqual(report["missing_after"],0)
        source=[dict(rows[3],ts=missing+i*300000,open=100+i,close=101+i,
                     high=103+i,low=99+i,volume=10+i,quote_volume=1000+i) for i in range(3)]
        client.candles.side_effect=lambda symbol,iv,*args: source if iv=="5m" else []
        recovered,report=repair_history(client,"DOT-USD","15m",observed)
        middle=next(r for r in recovered if r["ts"]==missing)
        self.assertEqual((middle["open"],middle["close"],middle["low"],middle["high"]),(100,103,99,105))
        self.assertEqual(middle["volume"],33)
        self.assertEqual(report["recovered_from_smaller_candles"],1)
        self.assertFalse(report["synthetic"])
        self.assertEqual([r for r in recovered if r["ts"]!=missing],observed)

    def test_partial_or_duplicate_lower_bars_never_fill_a_gap(self):
        rows=candles(8); stamp=rows[3]["ts"]; observed=rows[:3]+rows[4:]
        small=[dict(rows[3],ts=stamp+i*300000) for i in range(3)]
        for source in (small[:2],small+[small[1]], [dict(r,high=float("nan")) for r in small]):
            client=Mock(); client.candles.side_effect=lambda symbol,iv,*args: source if iv=="5m" else []
            recovered, report=repair_history(client,"DOT-USD","15m",observed)
            self.assertEqual(recovered,observed)
            self.assertEqual(report["missing_after"],1)
        with self.assertRaises(ValueError):
            repair_history(Mock(),"DOT-USD","15m",observed+[observed[0]])

    def test_cancellation_and_request_limits_are_honored_without_prices(self):
        rows=candles(8); observed=rows[:3]+rows[4:]
        client=Mock(); client.candles.side_effect=TimeoutError("offline")
        recovered,report=repair_history(client,"DOT-USD","15m",observed,max_requests=1)
        self.assertEqual(recovered,observed)
        self.assertEqual(client.candles.call_count,1)
        self.assertTrue(report["request_budget_exhausted"])
        self.assertEqual(report["errors"][0]["message"],"offline")
        with self.assertRaises(InterruptedError):
            repair_history(client,"DOT-USD","15m",observed,cancelled=lambda:True)

    def test_recovered_data_and_its_provenance_survive_a_second_cached_download(self):
        rows=candles(96); stamp=rows[40]["ts"]
        observed=rows[:40]+rows[41:]
        small=[dict(rows[40],ts=stamp+i*300000) for i in range(3)]
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"test.db"; init_continuous_db(db)
            manager=ResearchManager(db,Path(folder)/"data")
            manager.client=Mock()
            manager.client.candles.side_effect=lambda symbol,iv,*args: small if iv=="5m" else observed
            result=manager._history("DOT-USD","15m",1,end_ms=rows[-1]["ts"]+900000)
            report=manager.data_reports[("DOT-USD","15m")]
            self.assertEqual(len(result),96)
            self.assertEqual(report["recovered_from_smaller_candles"],1)
            self.assertEqual(report["recovery_history"][0]["ts"],stamp)
            calls=manager.client.candles.call_count
            repeated=manager._history("DOT-USD","15m",1,end_ms=rows[-1]["ts"]+900000)
            self.assertEqual(repeated,result)
            self.assertEqual(manager.client.candles.call_count,calls)
            self.assertEqual(manager.data_reports[("DOT-USD","15m")]["recovery_history"],report["recovery_history"])


class IndependentDailyTests(unittest.TestCase):
    def setUp(self):
        self.rows=hourly(55)
        self.base=self.rows[0]["ts"]
        self.daily=aggregate_complete(self.rows,HOUR,DAY_MS,self.base,self.base+55*DAY_MS)

    def test_completed_daily_join_preserves_context_after_intraday_gap(self):
        missing=27*24+3
        rows=self.rows[:missing]+self.rows[missing+1:]
        fallback=daily_context(rows,HOUR)
        joined=independent_daily_context(rows,HOUR,self.daily)
        self.assertFalse(fallback[missing])
        self.assertTrue(joined[missing]["ready"])
        self.assertLessEqual(joined[missing]["available_ts"],rows[missing]["ts"]+HOUR)
        # Still restart the separate intraday indicators after the missing hour.
        segments=[{"start_index":0,"end_index":missing},{"start_index":missing,"end_index":len(rows)}]
        fs=build_learning_features(rows,"1h",segments,daily_rows=self.daily)
        self.assertTrue(all(f is None for f in fs[missing:missing+240]))
        self.assertTrue(fs[missing+240]["daily"]["ready"])

    def test_future_daily_prices_and_stale_missing_days_cannot_leak(self):
        cut=30*24+7
        joined=independent_daily_context(self.rows[:cut],HOUR,self.daily)
        changed=copy.deepcopy(self.daily)
        for r in changed[30:]:
            for key in ("open","high","low","close"): r[key]*=100
        self.assertEqual(joined,independent_daily_context(self.rows[:cut],HOUR,changed))
        missing=self.daily[:30]+self.daily[31:]
        stale=independent_daily_context(self.rows,HOUR,missing)
        self.assertFalse(stale[31*24-1])
        self.assertFalse(stale[51*24-2])
        self.assertTrue(stale[52*24-1]["ready"])
        with self.assertRaises(ValueError):
            independent_daily_context([],HOUR,self.daily+[self.daily[-1]])

    def test_replay_and_monitoring_share_daily_inputs_and_gap_warmup(self):
        with tempfile.TemporaryDirectory() as folder:
            agent=ContinuousLearner(Path(folder)/"test.db",Path(folder)/"data")
            market=agent._empty_market(); agent.market["DOT-USD"]=market
            market["bars"]["1h"]=self.rows[:45*24][-300:]
            market["bars"]["1d"]=self.daily  # even a longer cache must join as-of
            feature=agent._latest_feature("DOT-USD","1h")
            self.assertEqual(feature["daily"],independent_daily_context([self.rows[45*24-1]],HOUR,self.daily)[0])
            market["bars"]["1h"].pop(-3)
            self.assertIsNone(agent._latest_feature("DOT-USD","1h"))
            agent.stop()

    def test_daily_data_participates_in_fingerprint_and_offline_fallback_is_explicit(self):
        learner=object.__new__(AutoLearner)
        first=learner._fingerprint(self.rows,"DOT-USD",DEFAULTS,daily_rows=self.daily)
        changed=copy.deepcopy(self.daily); changed[-1]["close"]-=.01
        second=learner._fingerprint(self.rows,"DOT-USD",DEFAULTS,daily_rows=changed)
        self.assertNotEqual(first,second)
        manager=object.__new__(ResearchManager)
        manager._history=Mock(side_effect=TimeoutError("offline"))
        rows,source=manager.daily_history("DOT-USD",1095,self.base+55*DAY_MS)
        self.assertIsNone(rows)
        self.assertEqual(source["status"],"daily_download_unavailable")


if __name__ == "__main__": unittest.main()
