"""Generated evidence only: no providers, brokerage orders or paid AI calls."""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from xml.sax.saxutils import escape

from lab.crypto_watch import STEP, HOUR
from lab.event_feeds import date_ms
from lab.market_radar import MarketRadar, calendar_timing
from lab.paper_store import db_connect
from lab.radar_feeds import FEEDS, STOCKS, ASSETS, parse_news, matched_assets, stock_observation, StockSnapshots
from lab.stock_service import StockService

BASE = Path(__file__).resolve().parents[1]
T0 = date_ms("2026-09-28T18:00:00Z")


def iso(ts):
    return datetime.fromtimestamp(ts/1000, timezone.utc).isoformat()


def fixture_news(ts, title="Hedera announces a partnership", url="https://example.org/fixture", updated=None):
    return ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>'+escape(title)+
        '</title><id>fixture</id><link href="'+escape(url, {'"':'&quot;'})+'"/><published>'+iso(ts)+
        '</published><updated>'+iso(updated or ts)+'</updated></entry></feed>').encode()


def calendar_request(**changes):
    return dict(dict(id="", version=0, symbol="HBAR-USD", title="Generated catalyst fixture", date="2026-09-29",
        time_utc="17:00", status="target", source_url="https://example.org/fixture", note="Unconfirmed outcome"), **changes)


def stock_snapshot(ts=T0, price=106, close=100):
    return {"latestTrade":{"t":iso(ts),"p":price},"prevDailyBar":{"t":"2026-09-25T04:00:00Z","c":close}}


class ParsingTests(unittest.TestCase):
    def test_publication_update_and_late_observation_are_distinct(self):
        items, rejected = parse_news("hedera", fixture_news(T0-HOUR, updated=T0-1000), T0)
        self.assertEqual(rejected,0)
        self.assertEqual(items[0]["published_ts"],T0-HOUR)
        self.assertEqual(items[0]["updated_ts"],T0-1000)
        self.assertNotIn("observed_ts",items[0])

    def test_bad_item_does_not_hide_other_valid_entries(self):
        raw=fixture_news(T0-1000).replace(b'</feed>',b'<entry><title>No dates</title></entry></feed>')
        items,rejected=parse_news("hedera",raw,T0)
        self.assertEqual((len(items),rejected),(1,1))

    def test_future_dates_unsafe_links_and_html_are_not_news(self):
        for raw in (fixture_news(T0+1),fixture_news(T0,url="javascript:alert(1)"),b'<html>Access denied</html>',
                    b'<!DOCTYPE foo><rss/>',b'<feed><entry><title>x</title></entry></feed>'):
            with self.assertRaises(ValueError):parse_news("hedera",raw,T0)

    def test_aliases_do_not_turn_ordinary_words_into_asset_matches(self):
        self.assertEqual(matched_assets("Beam of light: keys link different findings"),[])
        self.assertEqual(matched_assets("$BEAM announces clinical data"),["BEAM"])
        self.assertEqual(matched_assets("NVDA reports earnings"),["NVDA"])
        self.assertEqual(matched_assets("Bitcoin Cash upgrade"),["BCH-USD"])
        self.assertEqual(matched_assets("Chainlink launches CCIP"),["LINK-USD"])

    def test_bad_news_is_categorized_without_bullish_score_and_spam_is_filtered(self):
        items,_=parse_news("stock_news",fixture_news(T0,title="Intellia trial halted after safety finding"),T0)
        self.assertEqual(items[0]["category"],"clinical / regulatory")
        self.assertEqual(items[0]["assets"],["NTLA"])
        self.assertNotIn("score",items[0])
        self.assertEqual(parse_news("hedera",fixture_news(T0,title="HBAR price prediction 100x"),T0)[0],[])


class QuoteTests(unittest.TestCase):
    def test_fresh_large_move_is_initial_price_evidence_without_volume_claim(self):
        item=stock_observation("NVDA",stock_snapshot(),T0,"iex")
        self.assertEqual(item["stage"],"large_move")
        self.assertAlmostEqual(item["change_pct"],6)
        self.assertTrue(item["initial_observation"])
        self.assertNotIn("relative_volume",item)

    def test_weekend_previous_close_is_valid_but_wrong_session_is_not(self):
        snap=stock_snapshot()
        snap["prevDailyBar"]["t"]="2026-09-24T04:00:00Z"
        item=stock_observation("NVDA",snap,T0,"iex")
        self.assertEqual(item["stage"],"unavailable")
        self.assertIn("preceding trading session",item["reason"])

    def test_stale_future_bad_price_and_off_session_data_block_signals(self):
        for snap in (stock_snapshot(T0-3*STEP),stock_snapshot(T0+1000),stock_snapshot(price=True),
                     stock_snapshot(price=float('nan')),stock_snapshot(close=0),{}):
            self.assertEqual(stock_observation("NVDA",snap,T0,"iex")["stage"],"unavailable")
        self.assertEqual(stock_observation("NVDA",stock_snapshot(),date_ms("2026-09-27T18:00:00Z"),"iex")["stage"],"market_closed")

    def test_comparison_requires_two_fresh_increasing_quotes_same_session_and_feed(self):
        previous=stock_observation("NVDA",stock_snapshot(T0-STEP,100),T0-STEP,"iex")
        current=stock_observation("NVDA",stock_snapshot(T0,103),T0,"iex",previous)
        self.assertEqual(current["stage"],"momentum_change")
        self.assertFalse(current["initial_observation"])
        self.assertAlmostEqual(current["interval_change_pct"],3)
        for old in (dict(previous,feed="sip"),dict(previous,session="2026-09-25"),dict(previous,observed_ts=T0-3*STEP),dict(previous,quote_ts=T0)):
            self.assertTrue(stock_observation("NVDA",stock_snapshot(T0,103),T0,"iex",old)["initial_observation"])

    def test_adapter_uses_fixed_read_only_host_and_does_not_expose_credentials(self):
        with patch.dict(os.environ,{"ALPACA_API_KEY":"secret-key","ALPACA_SECRET_KEY":"secret-value","RADAR_STOCK_FEED":"iex"}), \
                patch('lab.radar_feeds.read_url',return_value=b'{}') as read:
            client=StockSnapshots();client.snapshots()
        self.assertTrue(read.call_args.args[0].startswith("https://data.alpaca.markets/v2/stocks/snapshots?"))
        self.assertNotIn("secret",read.call_args.args[0])
        self.assertNotIn("secret",json.dumps(client.info()))


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.radar=MarketRadar(self.temp.name,"test-token",news_fetch=lambda _:fixture_news(T0-1000))
        self.radar._set(enabled=True)

    def tearDown(self):
        self.radar.shutdown();self.temp.cleanup()

    def collect(self,ts,source="hedera"):
        with patch('lab.market_radar.now_ms',return_value=ts):self.radar._collect(source)

    def status(self,ts=T0):
        with patch('lab.market_radar.now_ms',return_value=ts):return self.radar.status()

    def test_first_scan_is_not_an_early_news_alert_and_repoll_preserves_observation(self):
        self.collect(T0);self.collect(T0+STEP)
        value=self.status(T0+STEP)
        self.assertEqual(len(value["news"]),1)
        self.assertTrue(value["news"][0]["initial_snapshot"])
        self.assertEqual(value["news"][0]["observed_ts"],T0)
        self.assertFalse(value["alerts"])

    def test_fresh_bad_news_creates_alert_but_same_title_timestamp_update_does_not(self):
        self.collect(T0)
        self.radar.news_fetch=lambda _:fixture_news(T0+STEP-1000,"Hedera security incident",url="https://example.org/incident")
        self.collect(T0+STEP)
        self.assertEqual(len(self.status(T0+STEP)["alerts"]),1)
        self.radar.news_fetch=lambda _:fixture_news(T0+STEP-1000,"Hedera security incident",url="https://example.org/incident",updated=T0+2*STEP-1000)
        self.collect(T0+2*STEP)
        self.assertEqual(len(self.status(T0+2*STEP)["alerts"]),1)
        self.assertTrue(self.status(T0+2*STEP)["news"][0]["timestamp_only_update"])

    def test_reprints_are_not_independent_confirmations_and_late_news_is_not_fresh(self):
        self.collect(T0,"hedera");self.collect(T0,"crypto_news")
        self.radar.news_fetch=lambda _:fixture_news(T0+STEP-1000,"Hedera announces a new contract",url="https://example.org/primary")
        self.collect(T0+STEP,"hedera")
        self.radar.news_fetch=lambda _:fixture_news(T0+STEP-1000,"Hedera announces a new contract",url="https://example.org/reprint")
        self.collect(T0+STEP,"crypto_news")
        value=self.status(T0+STEP)
        self.assertEqual(len(value["alerts"]),1)
        self.assertTrue(any(n["possible_reprint"] for n in value["news"]))
        self.radar.news_fetch=lambda _:fixture_news(T0-4*HOUR,"Hedera launches old product",url="https://example.org/old")
        self.collect(T0+2*STEP)
        self.assertEqual(len(self.status(T0+2*STEP)["alerts"]),1)

    def test_incident_body_update_with_unchanged_title_is_preserved_and_alerted(self):
        def incident(ts, message):
            return fixture_news(T0-1000,"Hedera network incident",updated=ts).replace(
                b'</entry>', ('<content>'+escape(message)+'</content></entry>').encode())
        self.radar.news_fetch=lambda _:incident(T0-1000,"Investigating delayed transactions.")
        self.collect(T0,"hedera_status")
        self.radar.news_fetch=lambda _:incident(T0+STEP-1000,"Transactions have been halted while engineers investigate.")
        self.collect(T0+STEP,"hedera_status")
        value=self.status(T0+STEP)
        self.assertEqual(len(value["news"]),2)
        self.assertEqual(len(value["alerts"]),1)
        self.assertTrue(value["news"][0]["revised"])
        self.assertFalse(value["news"][0]["timestamp_only_update"])

    def test_failure_retains_evidence_exposes_coverage_and_recovery_is_labeled(self):
        self.collect(T0)
        self.radar.news_fetch=Mock(side_effect=TimeoutError("do not disclose raw error text"))
        self.collect(T0+STEP)
        value=self.status(T0+3*STEP)
        feed=next(s for s in value["sources"] if s["id"]=="hedera")
        self.assertTrue(feed["stale"])
        self.assertEqual(feed["success_ts"],T0)
        self.assertIn("timed out",feed["error"])
        self.assertNotIn("disclose",feed["error"])
        self.assertEqual(len(value["news"]),1)
        self.radar.news_fetch=lambda _:fixture_news(T0+3*STEP-1000,"Hedera new partnership")
        self.collect(T0+3*STEP)
        self.assertTrue(self.status(T0+3*STEP)["news"][0]["after_coverage_gap"])

    def test_stop_during_slow_fetch_drops_late_response_and_status_does_not_wait(self):
        entered,release=threading.Event(),threading.Event()
        def slow(_):entered.set();release.wait(3);return fixture_news(T0-1)
        self.radar.news_fetch=slow
        worker=threading.Thread(target=lambda:self.collect(T0));worker.start()
        self.assertTrue(entered.wait(1))
        start=time.monotonic();self.radar.status();self.assertLess(time.monotonic()-start,.5)
        self.radar.stop();release.set();worker.join(2)
        self.assertFalse(worker.is_alive());self.assertFalse(self.status()["news"])

    def test_sold_tag_and_notes_survive_restart_without_reducing_coverage(self):
        value=self.radar.save_tracking({"symbol":"NTLA","mode":"recently_sold","note":"Watch clinical safety and financing"})
        self.assertEqual(value["watch_count"],33)
        second=MarketRadar(self.temp.name,"test-token")
        try:
            item=next(w for w in second.status()["watchlist"] if w["symbol"]=="NTLA")
            self.assertEqual(item["mode"],"recently_sold")
            self.assertEqual(item["note"],"Watch clinical safety and financing")
            self.assertEqual(len(second.status()["watchlist"]),len(ASSETS))
        finally:second.shutdown()

    def test_calendar_revision_cancel_and_dedupe_preserve_original_evidence(self):
        value=self.radar.save_catalyst(calendar_request())
        event=next(c for c in value["calendar"] if c["title"]=="Generated catalyst fixture")
        self.assertIsNone(event["source_checked_on"])
        self.radar._calendar_alerts(T0);self.radar._calendar_alerts(T0+STEP)
        first=[a for a in self.status()["alerts"] if a["item"].get("id")==event["id"]]
        self.assertEqual(len(first),1)
        request=calendar_request(id=event["id"],version=event["version"],status="cancelled")
        value=self.radar.save_catalyst(request)
        with self.assertRaises(RuntimeError):self.radar.save_catalyst(request)
        self.assertEqual(len(value["changes"]),2)
        self.assertEqual(value["changes"][0]["before"]["status"],"target")
        old=next(a for a in value["alerts"] if a["item"].get("id")==event["id"])
        self.assertTrue(old["superseded"])
        self.assertEqual(old["item"]["status"],"target")

    def test_calendar_date_only_never_invents_approval_or_exact_time(self):
        value=self.radar.save_catalyst(calendar_request(time_utc=""))
        item=next(c for c in value["calendar"] if c["title"]=="Generated catalyst fixture")
        timing=calendar_timing(item,T0)
        self.assertEqual(timing["time_precision"],"day")
        self.assertTrue(timing["upcoming"])
        self.assertTrue(timing["needs_source_check"])
        self.assertTrue(calendar_timing(item,T0+5*24*HOUR)["past_due"])

    def test_calendar_rejects_unsafe_links_invalid_dates_and_unknown_assets(self):
        for change in ({"source_url":"http://example.org"},{"source_url":"https://user:pass@example.org"},
                       {"date":"2026-02-30"},{"time_utc":"26:10"},{"version":True},{"symbol":"FAKE"}):
            with self.assertRaises(ValueError):self.radar.save_catalyst(calendar_request(**change))

    def test_disabled_or_unconfigured_price_reader_does_not_call_provider(self):
        self.radar.snapshots=Mock()
        self.radar.snapshots.info.return_value={"configured":False,"error":None,"feed":"iex","coverage":"IEX"}
        self.radar._prices();self.radar.snapshots.snapshots.assert_not_called()

    def test_enabled_preference_resumes_after_shutdown_without_duplicate_calendar_seeds(self):
        self.radar._set(enabled=True)
        self.radar.shutdown()
        second=MarketRadar(self.temp.name,"test-token",news_fetch=lambda _:b'<rss><channel/></rss>')
        try:
            with patch.object(second,'start',return_value={}) as start:second.resume()
            start.assert_called_once()
            self.assertEqual(len(second.status()["calendar"]),2)
        finally:second.shutdown()


class IntegrationTests(unittest.TestCase):
    def test_authentication_export_agent_evidence_and_fast_compact_overview(self):
        with tempfile.TemporaryDirectory() as directory:
            service=StockService(BASE,Path(directory)/'unused',Path(directory)/'data','test-token',resume=False)
            try:
                for endpoint in ("status","export","start","stop","tracking","catalyst"):
                    method="GET" if endpoint in ("status","export") else "POST"
                    self.assertEqual(service.handle(method,"/api/market-radar/"+endpoint,body={})[0],401)
                headers={"Authorization":"Bearer test-token","Content-Type":"application/json"}
                response=service.handle("POST","/api/market-radar/tracking",body={"symbol":"NTLA","mode":"holding","note":"Review dilution"},headers=headers)
                self.assertEqual(response[0],200)
                brief=service.research_agent._tool("get_market_radar",{"symbol":"NTLA"},[])
                self.assertEqual(brief["watchlist"][0]["note"],"Review dilution")
                self.assertFalse(brief["execution_enabled"])
                status,raw,_=service.handle("GET","/api/market-radar/export",headers=headers)
                self.assertEqual(status,200);self.assertEqual(json.loads(raw)["watch_count"],33)
                self.assertLess(len(json.dumps(service.market_radar.status(compact=True))),2000)
                self.assertLess(len(json.dumps(service.overview())),20000)
                self.assertEqual(service.handle("GET","/market-radar")[0],200)
                self.assertFalse(service.handle("GET","/api/health")[1]["live_orders_allowed"])
            finally:service.shutdown()


if __name__ == '__main__':
    unittest.main()
