"""Deterministic stock-market regressions. Generated candles are test fixtures only."""
import copy
import json
import math
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from lab.data import INTERVAL_MS
from lab.equity_data import EquityData, normalize, sessions, slots, market_status, ticker
from lab.equity_jobs import EquityJobs
from lab.equity_research import (DEFAULT_COSTS, features_for, prepare, session_context,
                                stock_policy, run_stock_practice, validate_costs)
from lab.experiment_jobs import read_gzip, write_gzip
from lab.experiments import digest
from lab.execution import simulate
from lab.service import Service
from tests.test_execution import PARAMS, features

BASE = Path(__file__).resolve().parents[1]


def stamp(value):
    return int(datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()*1000)


def stock_rows(interval="1h", start="2025-01-02T00:00:00Z", end="2025-08-01T23:00:00Z", moving=False):
    output = []
    for i, r in enumerate(slots(interval,stamp(start),stamp(end)).values()):
        price = 100+(i*.025+math.sin(i/11)) if moving else 100.
        output.append({**r,"open":price,"high":price+.4,"low":price-.4,"close":price+.1 if moving else price,
                       "volume":100.+i%23,"quote_volume":price*(100+i%23),"trades":10,"asset_class":"equity"})
    return output


def snapshot(rows):
    return {"rows":rows,"data_sha256":digest(rows),"quality":{"observed_candles":len(rows),"coverage_pct":100.,"missing_candles":0},
            "market_data":{"provider":"test_fixture","adjustment":"test only","currency":"USD"}}


class StockCalendarTests(unittest.TestCase):
    def test_weekends_holidays_exceptional_closure_and_early_close(self):
        self.assertEqual(sessions("2025-01-09","2025-01-09"),())
        self.assertEqual(sessions("2026-11-26","2026-11-26"),())
        self.assertEqual(sessions("2026-09-19","2026-09-20"),())
        day = sessions("2026-11-27","2026-11-27")[0]
        self.assertEqual(day[2]-day[1],210*60000)

    def test_daylight_saving_changes_utc_open(self):
        a,b=sessions("2026-03-06","2026-03-09")
        self.assertEqual(datetime.fromtimestamp(a[1]/1000,timezone.utc).hour,14)
        self.assertEqual(datetime.fromtimestamp(b[1]/1000,timezone.utc).hour,13)
        self.assertFalse(market_status(stamp("2026-11-26T16:00:00Z"))["open"])
        self.assertTrue(market_status(stamp("2026-11-27T16:00:00Z"))["open"])
        self.assertFalse(market_status(stamp("2026-11-27T19:00:00Z"))["open"])

    def test_four_minute_tail_and_four_hour_bars_are_session_anchored(self):
        a,b=stamp("2026-09-18T00:00:00Z"),stamp("2026-09-19T00:00:00Z")
        raw=stock_rows("1m","2026-09-18T00:00:00Z","2026-09-19T00:00:00Z")
        rows,q=normalize(raw,"1m","4m",a,b)
        self.assertEqual(len(rows),98)
        self.assertEqual(rows[-1]["end_ts"]-rows[-1]["ts"],120000)
        self.assertEqual(q["missing_candles"],0)
        rows,_=normalize(raw,"1m","4h",a,b)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["ts"],stamp("2026-09-18T13:30:00Z"))
        self.assertEqual(rows[1]["end_ts"]-rows[1]["ts"],150*60000)
        self.assertEqual(rows[-1]["next_ts"],stamp("2026-09-21T13:30:00Z"))

    def test_missing_source_minute_invalidates_only_its_aggregate(self):
        raw=stock_rows("1m","2026-09-18T00:00:00Z","2026-09-19T00:00:00Z")
        del raw[2]
        rows,q=normalize(raw,"1m","4m",stamp("2026-09-18T00:00:00Z"),stamp("2026-09-19T00:00:00Z"))
        self.assertEqual(len(rows),97)
        self.assertEqual(q["missing_candles"],1)
        self.assertEqual(rows[0]["ts"],raw[0]["ts"]+240000)

    def test_unclosed_and_invalid_bars_are_not_filled(self):
        raw=stock_rows("1m","2026-09-18T00:00:00Z","2026-09-19T00:00:00Z")
        raw[0]["close"]=float("nan")
        rows,q=normalize(raw,"1m","1m",raw[0]["ts"],raw[0]["ts"]+150000)
        self.assertEqual(len(rows),1)
        self.assertEqual(q["invalid_source_candles"],1)
        self.assertLessEqual(rows[-1]["end_ts"],raw[0]["ts"]+150000)

    def test_features_span_scheduled_closures_but_reset_after_missing_bars(self):
        rows=stock_rows(moving=True)
        self.assertEqual(len(prepare(rows,"1h")),1)
        f=features_for(rows,"1h")
        self.assertIsNotNone(f[300])
        changed=rows[:300]+rows[301:]
        g=features_for(changed,"1h")
        self.assertIsNone(g[300])
        self.assertIsNotNone(g[540])

    def test_daily_context_and_indicators_do_not_see_future_prices(self):
        rows=stock_rows(moving=True)
        fs=features_for(rows,"1h")
        self.assertEqual(fs[:400],features_for(rows[:400],"1h"))
        for row,f in zip(rows,fs):
            if f and f["daily"]:
                self.assertLessEqual(f["daily"]["available_ts"],row["end_ts"])
        context=session_context(stock_rows("1d",moving=True))
        self.assertFalse(context[19]);self.assertTrue(context[20]["ready"])


class StockProviderTests(unittest.TestCase):
    def test_massive_builds_session_hours_from_thirty_minute_bars(self):
        for start, end, expected in (("2026-09-18T00:00:00Z", "2026-09-19T00:00:00Z", {"1h":7, "4h":2}),
                                     ("2026-11-27T00:00:00Z", "2026-11-28T00:00:00Z", {"1h":4, "4h":1})):
            raw = stock_rows("30m", start, end, moving=True)
            response = Mock(status_code=200)
            response.json.return_value = {"status":"OK", "results":[
                {"t":r["ts"], "o":r["open"], "h":r["high"], "l":r["low"], "c":r["close"], "v":r["volume"]}
                for r in raw]}
            http = Mock(); http.get.return_value = response
            client = EquityData(http); client.massive_key = "test-only"
            with patch("lab.equity_data.time.time", return_value=(stamp(end)+86400000)/1000):
                for interval in ("1h", "4h"):
                    result = client.history("SPY", interval, 1, cutoff=stamp(end), provider="massive")
                    self.assertEqual(len(result["rows"]), expected[interval])
                    self.assertEqual(result["quality"]["missing_candles"], 0)
                    self.assertEqual(result["rows"][0]["ts"], raw[0]["session_open_ts"])
                    self.assertEqual(result["rows"][-1]["end_ts"], raw[-1]["session_close_ts"])
                    self.assertIn("/range/30/minute/", http.get.call_args.args[0])
                    self.assertEqual(http.get.call_args.kwargs["params"]["adjusted"], "true")

    def test_massive_missing_half_hour_invalidates_its_hour(self):
        start, end = "2026-09-18T00:00:00Z", "2026-09-19T00:00:00Z"
        raw = stock_rows("30m", start, end)
        del raw[1]
        client = EquityData(Mock()); client.massive_key = "test-only"
        with patch.object(client, "_massive", return_value=(raw, {})):
            result = client.history("SPY", "1h", 1, cutoff=stamp(end), provider="massive")
        self.assertEqual(result["quality"]["missing_candles"], 1)
        self.assertEqual(result["rows"][0]["ts"], raw[0]["ts"]+3600000)

    def test_massive_snapped_chunk_overlap_is_deduplicated_or_rejected_if_revised(self):
        one = {"t":123, "o":100, "h":101, "l":99, "c":100, "v":100}
        for revised in (False, True):
            first = Mock(status_code=200); second = Mock(status_code=200)
            first.json.return_value = {"status":"OK", "results":[one]}
            second.json.return_value = {"status":"OK", "results":[dict(one, c=101 if revised else 100)]}
            http = Mock(); http.get.side_effect = [first, second]
            client = EquityData(http)
            with patch("lab.equity_data.time.sleep"):
                if revised:
                    with self.assertRaisesRegex(ValueError, "conflicting"):
                        client._massive("SPY", "30m", 0, 31*86400000, None)
                else:
                    rows, _ = client._massive("SPY", "30m", 0, 31*86400000, None)
                    self.assertEqual(len(rows), 1)

    def test_yahoo_invalid_instrument_and_rate_limit_are_visible(self):
        http=Mock()
        http.get.return_value.status_code=429
        client=EquityData(http)
        with self.assertRaisesRegex(RuntimeError,"429"):
            client._yahoo("SPY","1h",0,10000)
        http.get.return_value.status_code=200
        http.get.return_value.json.return_value={"chart":{"result":[{"meta":{"currency":"EUR"}}]}}
        with self.assertRaisesRegex(ValueError,"US-listed"):
            client._yahoo("ABC","1h",0,10000)

    def test_alpaca_paginates_and_requests_split_adjusted_explicit_feed(self):
        one=Mock(status_code=200);two=Mock(status_code=200)
        one.json.return_value={"bars":{"SPY":[{"t":"2026-09-18T13:30:00Z","o":100,"h":101,"l":99,"c":100,"v":20}]},"next_page_token":"page2"}
        two.json.return_value={"bars":{"SPY":[]},"next_page_token":None}
        http=Mock();http.get.side_effect=[one,two]
        client=EquityData(http)
        rows,_=client._alpaca("SPY","1m",0,20000,"iex",None)
        self.assertEqual(len(rows),1)
        self.assertEqual(http.get.call_count,2)
        params=http.get.call_args.kwargs["params"]
        self.assertEqual(params["adjustment"],"split");self.assertEqual(params["feed"],"iex")
        self.assertEqual(params["page_token"],"page2")

    def test_no_silent_feed_fallback_or_duplicate_pagination(self):
        http=Mock();http.get.return_value.status_code=403
        with self.assertRaisesRegex(RuntimeError,"403"):
            EquityData(http)._alpaca("SPY","1m",0,20000,"sip",None)
        http.get.return_value.status_code=200
        http.get.return_value.json.return_value={"bars":{},"next_page_token":"same"}
        with self.assertRaisesRegex(RuntimeError,"repeated"):
            EquityData(http)._alpaca("SPY","1m",0,20000,"sip",None)

    def test_yahoo_split_factors_preserve_historical_share_basis(self):
        http=Mock();http.get.return_value.status_code=200
        http.get.return_value.json.return_value={"chart":{"result":[{
            "meta":{"currency":"USD","exchangeTimezoneName":"America/New_York","instrumentType":"EQUITY"},
            "timestamp":[100,200],"indicators":{"quote":[{"open":[25,25],"high":[26,26],"low":[24,24],"close":[25,25],"volume":[400,400]}]},
            "events":{"splits":{"200":{"date":200,"numerator":4,"denominator":1}}}}]}}
        rows,_=EquityData(http)._yahoo("AAPL","1d",0,300000)
        self.assertEqual([r["split_factor"] for r in rows],[4.,1.])

    def test_minute_history_chunks_and_applies_splits_across_boundaries(self):
        client=EquityData(Mock())
        day=86400000
        def batch(symbol,interval,start,end):
            metadata={"corporate_actions":{"splits":{str(7*day):{"date":7*day//1000,"numerator":2,"denominator":1}}} if start>=6*day else {}}
            return [{"ts":start,"split_factor":1.},{"ts":99*day,"split_factor":1.}],metadata
        client._yahoo=Mock(side_effect=batch)
        rows,meta=client._yahoo_chunks("SPY",0,13*day,None)
        self.assertEqual(len(rows),3)
        self.assertEqual([r["split_factor"] for r in rows],[2.,2.,1.])
        self.assertTrue(all(call.args[3]-call.args[2] <= 6*day for call in client._yahoo.call_args_list))
        self.assertEqual(meta["minute_request_days"],6)

    def test_retention_tickers_and_costs_reject_invalid_inputs(self):
        for symbol in ("BTC-USD","../../x","<script>","eurusd=x"):
            with self.assertRaises(ValueError):ticker(symbol)
        for value in (float("nan"),True,-.01):
            with self.assertRaises(ValueError):validate_costs({"fee_rate":value})
        with self.assertRaises(ValueError):EquityData().history("SPY","1m",31)


class StockExecutionTests(unittest.TestCase):
    def run_account(self, rows, start=240, **kwargs):
        p=dict(PARAMS,time_stop_hours=1000)
        with patch("lab.engine.evaluate_signal",return_value=(70,None)):
            return simulate(rows,features(len(rows),atr=rows[0]["close"]*.02),start,len(rows),500,.01,0,0,p,
                            bar_interval_ms=3600000,stock_execution=True,**kwargs)

    def friday_boundary(self):
        rows=stock_rows()
        i=next(i for i,r in enumerate(rows) if i>245 and r["session"]=="2025-02-28" and r["end_ts"]==r["session_close_ts"])
        return rows,i

    def test_weekend_gap_executes_stop_at_monday_open(self):
        rows,i=self.friday_boundary();rows=rows[:i+2]
        rows[-1].update(open=90.,high=92.,low=89.,close=91.)
        metrics,trades=self.run_account(rows,start=i-2)
        self.assertTrue(metrics["complete"])
        self.assertEqual(trades[0]["reason"],"STOP_GAP")
        self.assertEqual(trades[0]["exit"],90.)
        self.assertLess(trades[0]["r_multiple"],-1)

    def test_known_target_gap_precedes_later_intrabar_low(self):
        rows,i=self.friday_boundary();rows=rows[:i+2]
        rows[-1].update(open=110.,high=111.,low=90.,close=100.)
        _,trades=self.run_account(rows,start=i-2)
        self.assertEqual(trades[0]["reason"],"TARGET2")
        self.assertEqual(trades[0]["exit"],104.)

    def test_day_mode_closes_on_short_final_candle_and_expires_prior_signal(self):
        rows,i=self.friday_boundary();rows=rows[:i+3]
        _,trades=self.run_account(rows,start=i-2,close_at_session_end=True)
        self.assertEqual(trades[0]["reason"],"SESSION_CLOSE")
        self.assertEqual(trades[0]["available_ts"],rows[i]["session_close_ts"])
        self.assertNotEqual(trades[-1]["entry_ts"],rows[i+1]["ts"])

    def test_missing_scheduled_bar_stops_open_account(self):
        rows=stock_rows()[:250];del rows[245]
        metrics,_=self.run_account(rows)
        self.assertFalse(metrics["complete"]);self.assertIsNone(metrics["net_pnl"])

    def test_open_forward_mark_does_not_manufacture_a_closed_trade(self):
        rows=stock_rows()[:244]
        metrics,trades=self.run_account(rows,liquidate_end=False)
        self.assertEqual(trades,[])
        self.assertIsNotNone(metrics["open_position"])
        self.assertEqual(metrics["as_of_ts"],rows[-1]["end_ts"])

    def test_whole_shares_use_pre_split_price_and_actual_entry_quantity(self):
        rows=stock_rows()[:243]
        for r in rows:
            for k in ("open","high","low","close"):r[k]/=4
            r["split_factor"]=4.
        _,trades=self.run_account(rows,fractional_shares=False)
        self.assertEqual(trades[0]["actual_entry_shares"],1.)
        self.assertEqual(trades[0]["qty_initial"],4.)
        self.assertEqual(trades[0]["entry_split_factor"],4.)

    def test_whole_shares_and_fractional_cash_cap(self):
        rows=stock_rows()[:243]
        for fractional in (True,False):
            _,trades=self.run_account(rows,fractional_shares=fractional)
            q=trades[0]["qty_initial"]
            self.assertEqual(q,1.5 if fractional else 1)
            self.assertLessEqual(q*trades[0]["entry"],150)


class StockResearchAndJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.jobs=EquityJobs(Path(self.temp.name))
        self.jobs.resume=lambda:None

    def tearDown(self):
        self.jobs.shutdown();self.temp.cleanup()

    def test_seed_cannot_learn_from_later_price_changes(self):
        rows=stock_rows(moving=True)
        m={"symbol":"SPY","interval":"1h","mode":"swing","fractional_shares":True,"settings":DEFAULT_COSTS}
        a=run_stock_practice(snapshot(rows),m)
        changed=copy.deepcopy(rows)
        for r in changed[int(len(rows)*.7)+1:]:
            for k in ("open","high","low","close"):r[k]*=1.4
        b=run_stock_practice(snapshot(changed),m)
        self.assertEqual(a["seed"],b["seed"])
        self.assertFalse(a["eligible_for_trading"])
        self.assertEqual(len(a["variants"]),6)
        self.assertLess(a["seed"]["last_label_ts"],a["later_start_ts"])
        frozen=next(v for v in a["variants"] if v["id"]=="frozen")
        self.assertEqual(frozen["windows"]["later"]["standard"]["model_updates"],0)

    def test_queue_reuses_request_and_survives_restart_separately_from_crypto(self):
        request={"symbol":"SPY","interval":"1h","days":365}
        a=self.jobs.start(request);b=self.jobs.start(request)
        self.assertEqual(a["ids"],b["ids"]);self.assertEqual(b["created"],0)
        other=EquityJobs(Path(self.temp.name));other.resume=lambda:None
        self.assertEqual(other.get(a["ids"][0])["status"],"queued")
        other.cancel(a["ids"][0])
        self.jobs._patch(a["ids"][0],status="complete",message="late completion")
        self.assertEqual(other.get(a["ids"][0])["status"],"cancelled")
        self.assertIn("equity-practice",str(other.db_path))
        other.shutdown()

    def test_snapshot_roundtrip_and_exported_model(self):
        self.jobs.client.history=Mock(return_value=snapshot(stock_rows(moving=True)))
        j=self.jobs.start({"symbol":"SPY","interval":"1h","days":365})["ids"][0]
        self.jobs._run_job(self.jobs.get(j))
        self.assertEqual(self.jobs.get(j)["status"],"complete")
        self.assertNotIn("model",self.jobs.get(j)["result"])
        self.assertIn("model",self.jobs.get(j,full=True)["result"])
        self.jobs._run_job(self.jobs.get(j))
        self.assertEqual(self.jobs.client.history.call_count,1)

    def test_api_auth_validation_and_no_order_route(self):
        root=Path(self.temp.name)
        s=Service(BASE,root/"crypto.sqlite3",root/"data",token="test-stock-token")
        s.equities.resume=lambda:None
        try:
            self.assertEqual(s.handle("GET","/api/stocks/practice/status")[0],401)
            headers={"authorization":"Bearer test-stock-token","content-type":"application/json"}
            status,payload,_=s.handle("GET","/api/stocks/practice/status",headers=headers)
            self.assertEqual(status,200);self.assertEqual(len(payload["catalog"]["intervals"]),8)
            self.assertEqual(s.handle("POST","/api/stocks/practice/start",body={"symbol":"SPY","interval":"1d","mode":"day"},headers=headers)[0],400)
            self.assertEqual(s.handle("POST","/api/stocks/practice/order",body={},headers=headers)[0],404)
            self.assertEqual(s.handle("GET","/stock-practice")[0],200)
        finally:
            s.equities.shutdown();s.experiments.shutdown();s.forward.shutdown()

    def test_forward_registration_restart_no_backfill_and_revision_rejection(self):
        rows=stock_rows(moving=True)
        old=rows[:500]
        self.jobs.client.history=Mock(return_value=snapshot(old))
        jobid=self.jobs.start({"symbol":"SPY","interval":"1h","days":365})["ids"][0]
        m=self.jobs.get(jobid)["manifest"]
        # A seeded fixture isolates the forward clock and feedback machinery.
        result={"model":stock_policy(DEFAULT_COSTS,"swing").export(),"seed":{"resolved_examples":1},"variants":[]}
        self.jobs._patch(jobid,status="complete",result=result)
        write_gzip(self.jobs.snapshot_path(m),snapshot(old))
        registered=old[-1]["end_ts"]+1
        with patch("lab.equity_jobs.time.time",return_value=registered/1000):
            state=self.jobs.start_forward(jobid)
        self.assertEqual(state["created_ts"],registered)
        with self.assertRaises(ValueError):self.jobs.start_forward(jobid)
        future=rows[:550]
        self.jobs.client.history=Mock(return_value=snapshot(future))
        with patch("lab.equity_jobs.time.time",return_value=(future[-1]["end_ts"]+21*60000)/1000),patch("lab.engine.evaluate_signal",return_value=(70,None)):
            self.jobs._forward_tick(state)
        current=self.jobs.forward_list(full=True)[0]
        self.assertGreater(current["practice_examples"],0)
        self.assertTrue(all(t["signal_ts"]>=registered for t in current["account"]["trades"]))
        self.assertEqual(current["account"]["window_end_exits"],0)
        reloaded=EquityJobs(Path(self.temp.name));reloaded.resume=lambda:None
        self.assertEqual(reloaded.forward_list(full=True)[0],current)
        reloaded.shutdown()
        revised=copy.deepcopy(future);revised[499]["volume"]+=100
        self.jobs.client.history.return_value=snapshot(revised)
        with patch("lab.equity_jobs.time.time",return_value=(rows[551]["end_ts"]+21*60000)/1000):
            with self.assertRaisesRegex(ValueError,"revised"):
                self.jobs._forward_tick(current)
        self.jobs.stop_forward(state["id"])
        self.jobs._save_forward(state["id"],"running",current)
        self.assertEqual(self.jobs.forward_list()[0]["status"],"stopped")


if __name__ == "__main__":
    unittest.main()
