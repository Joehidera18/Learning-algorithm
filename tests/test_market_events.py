"""Event causality, real feed formats, persistence and model integration."""
import copy
import io
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from lab.event_context import (DAY, HOUR, EventIndex, validate_snapshot, vector,
    digest, attach_event_context, outcome_summary)
from lab.event_feeds import SOURCES, parse, record
from lab.event_store import EventStore, EventCollector
from lab.adaptive import AdaptivePolicy, feature_vector, DIMENSIONS, action_key
from lab.learning_research import learn_history
from lab.continuous import DEFAULTS, ContinuousLearner
from lab.service import Service
from tests.test_adaptive import F
from tests.test_execution import candles

BASE=Path(__file__).resolve().parents[1]
T=int(datetime(2026,9,1,tzinfo=timezone.utc).timestamp()*1000)


def event(published=T, observed=T, identity="one", source="sec", **kw):
    return record(source,identity,"Test announcement", "https://example.org/"+identity,
                  published,observed,**kw)


def snapshot(events=(), polls=None, sources=None):
    return {"version":1,"sources":sources or list(SOURCES),"events":list(events),
        "polls":polls if polls is not None else [{"source":"sec","ts":T,"ok":True,"ttl_ms":HOUR}]}


class EventTimingTests(unittest.TestCase):
    def test_first_observation_not_old_publication_controls_availability(self):
        e=event(observed=T+10000)
        index=EventIndex(snapshot([e]))
        self.assertEqual(index.at(T+9999)["recent_counts"]["regulation"],0)
        self.assertEqual(index.at(T+10000)["recent_counts"]["regulation"],1)
        self.assertEqual(index.at(T-1)["recent"],[])  # Replay rewind also safe.

    def test_revisions_and_calendar_cancellations_do_not_rewrite_history(self):
        a=event(event_ts=T+DAY,status="scheduled",published=0)
        b=event(event_ts=T+2*DAY,status="scheduled",published=0,observed=T+HOUR)
        c=event(event_ts=T+2*DAY,status="cancelled",published=0,observed=T+2*HOUR)
        index=EventIndex(snapshot([a,b,c]))
        self.assertEqual(index.at(T)["upcoming"][0]["event_ts"],T+DAY)
        self.assertEqual(index.at(T+HOUR)["upcoming"][0]["event_ts"],T+2*DAY)
        self.assertEqual(index.at(T+2*HOUR)["upcoming"],[])
        self.assertEqual(index.at(T)["upcoming"][0]["status"],"scheduled")

    def test_scheduled_result_is_never_inferred_when_release_time_arrives(self):
        e=event(event_ts=T+HOUR,status="scheduled",published=0)
        index=EventIndex(snapshot([e]))
        self.assertEqual(index.at(T)["upcoming_24h"],1)
        self.assertEqual(index.at(T+HOUR+1)["upcoming_7d"],0)
        self.assertEqual(sum(index.at(T+HOUR+1)["recent_counts"].values()),0)

    def test_expiration_and_future_poll_success_do_not_fill_outages(self):
        polls=[{"source":"sec","ts":T,"ok":True,"ttl_ms":HOUR},
            {"source":"sec","ts":T+HOUR+1000,"ok":True,"ttl_ms":HOUR}]
        index=EventIndex(snapshot([event()],polls,sources=["sec"]))
        self.assertEqual(index.at(T+HOUR-1)["coverage"],1)
        self.assertEqual(index.at(T+HOUR)["coverage"],0)
        self.assertEqual(vector(index.at(T+HOUR)),[0.]*7)
        self.assertEqual(index.at(T+HOUR+1000)["coverage"],1)
        polls.append({"source":"sec","ts":T+100,"ok":False,"ttl_ms":HOUR})
        self.assertEqual(EventIndex(snapshot([],polls,["sec"])).at(T+100)["coverage"],0)

    def test_windows_change_without_new_feed_poll(self):
        s=snapshot([event(source="fed_monetary",event_ts=T+8*DAY,status="scheduled",published=0)])
        index=EventIndex(s)
        self.assertEqual(index.at(T)["upcoming_7d"],0)
        self.assertEqual(index.at(T+DAY)["upcoming_7d"],1)
        self.assertEqual(index.at(T+7*DAY)["upcoming_24h"],1)

    def test_future_archive_content_cannot_change_earlier_feature_vectors(self):
        original=snapshot([event()])
        revised=copy.deepcopy(original)
        revised["events"].append(event(identity="future",published=T+DAY,observed=T+DAY))
        revised["polls"].append({"source":"sec","ts":T+DAY,"ok":False,"ttl_ms":HOUR})
        rows=[{"ts":T+i*900000} for i in range(20)]
        a=attach_event_context(rows,[dict(F) for _ in rows],900000,original,"DOT-USD")
        b=attach_event_context(rows,[dict(F) for _ in rows],900000,revised,"DOT-USD")
        self.assertEqual(a,b)
        self.assertEqual([feature_vector(f) for f in a],[feature_vector(f) for f in b])

    def test_asset_filtering_and_repeated_headline_link_count_once(self):
        e=record("coindesk","btc","Bitcoin update","https://example.org/btc",T,T)
        self.assertEqual(EventIndex(snapshot([e]),"DOT-USD").at(T)["recent"],[])
        self.assertEqual(len(EventIndex(snapshot([e]),"BTC-USD").at(T)["recent"]),1)
        updated=copy.deepcopy(e);updated.update(id="second-feed-guid",revision="another")
        self.assertEqual(len(EventIndex(snapshot([e,updated]),"BTC-USD").at(T)["recent"]),1)

    def test_schema_rejects_forged_availability_and_unsafe_links(self):
        for key,value in (("available_ts",T-1),("observed_ts",True),("url","javascript:alert(1)"),
                          ("url","https://example.org/\nmalformed"),("category","buy_now")):
            e=event();e[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):validate_snapshot(snapshot([e]))
        with self.assertRaises(ValueError):validate_snapshot(snapshot([event(),event()]))


class FeedTests(unittest.TestCase):
    def test_rss_and_atom_preserve_reported_update_and_observation_times(self):
        rss=b'<rss><channel><item><title>SEC &amp; digital assets</title><link>https://example.org/a</link><pubDate>Tue, 01 Sep 2026 08:30:00 -0400</pubDate></item></channel></rss>'
        e=parse("sec",rss,T+DAY)[0]
        self.assertEqual(e["published_ts"],T+12*HOUR+HOUR//2)
        self.assertEqual(e["available_ts"],T+DAY)
        atom=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Incident</title><link href="https://example.org/a"/><published>2026-09-01T08:00:00Z</published><updated>2026-09-01T09:00:00Z</updated></entry></feed>'
        self.assertEqual(parse("coinbase_status",atom,T+DAY)[0]["published_ts"],T+9*HOUR)
        with self.assertRaises(ValueError):parse("sec",b'<html>blocked</html>',T)
        with self.assertRaises(ValueError):parse("sec",b'<!DOCTYPE rss [<!ENTITY bad "value">]><rss/>',T)

    def test_calendar_eastern_daylight_saving_and_folded_lines(self):
        raw=b'''BEGIN:VCALENDAR
BEGIN:VEVENT
UID:one
DTSTART;TZID=US-Eastern:20260710T083000
SUMMARY:Employment
 Situation
END:VEVENT
BEGIN:VEVENT
UID:two
DTSTART;TZID=US-Eastern:20260109T083000
SUMMARY:Employment Situation
END:VEVENT
END:VCALENDAR'''
        rows=parse("bls_calendar",raw,T)
        for e,hour in zip(rows,[12,13]):
            dt=datetime.fromtimestamp(e["event_ts"]/1000,timezone.utc)
            self.assertEqual((dt.hour,dt.minute),(hour,30))
            self.assertEqual(e["available_ts"],T)
            self.assertEqual(e["status"],"scheduled")
        with self.assertRaises(ValueError):parse("bls_calendar",raw.replace(b'END:VEVENT',b'RRULE:FREQ=MONTHLY\nEND:VEVENT'),T)

    def test_fomc_cross_month_calendar_keeps_date_only_precision(self):
        raw=b'<h4><a>2026 FOMC Meetings</a></h4><div class="fomc-meeting__month"><strong>Apr/May</strong></div><div class="fomc-meeting__date">30-1*</div>'
        e=parse("fomc_calendar",raw,T)[0]
        dt=datetime.fromtimestamp(e["event_ts"]/1000,timezone.utc)
        self.assertEqual((dt.month,dt.day),(4,30))
        self.assertEqual(e["precision"],"day")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/"events.db"
        self.store=EventStore(self.db)

    def tearDown(self):self.tmp.cleanup()

    def test_duplicate_polls_restart_and_changed_revisions(self):
        self.store.record_poll("sec",T,[event()])
        self.store.record_poll("sec",T+1000,[event(observed=T+1000)])
        self.assertEqual(len(EventStore(self.db).snapshot()["events"]),1)
        e=event(observed=T+2000);e["title"]="Correction";e["revision"]="changed"
        self.store.record_poll("sec",T+2000,[e])
        self.assertEqual(len(self.store.snapshot()["events"]),2)
        self.assertEqual(EventIndex(self.store.snapshot()).at(T)["recent"][0]["title"],"Test announcement")

    def test_failed_calendar_preserves_schedule_but_absence_withdraws_it(self):
        e=event(source="bls_calendar",event_ts=T+DAY,status="scheduled",published=0)
        self.store.record_poll("bls_calendar",T,[e])
        self.store.record_poll("bls_calendar",T+1000,error="offline")
        self.assertEqual(self.store.snapshot()["events"][-1]["status"],"scheduled")
        self.store.record_poll("bls_calendar",T+2000,[])
        self.assertEqual(self.store.snapshot()["events"][-1]["status"],"withdrawn")
        index=EventIndex(self.store.snapshot())
        self.assertEqual(len(index.at(T)["upcoming"]),1)
        self.assertEqual(index.at(T+2000)["upcoming"],[])

    def test_poll_with_wrong_observation_or_ambiguous_data_is_atomic(self):
        with self.assertRaises(ValueError):self.store.record_poll("sec",T+1,[event()])
        with self.assertRaises(ValueError):self.store.record_poll("sec",T,[event(),event()])
        self.assertEqual(self.store.snapshot()["events"],[])
        self.assertEqual(self.store.snapshot()["polls"],[])

    def test_collector_records_failed_sources_without_fake_events(self):
        def offline(source):raise OSError("offline")
        collector=EventCollector(self.db,fetcher=offline)
        self.assertTrue(collector.refresh())
        self.assertEqual(collector.status()["coverage"],0)
        self.assertEqual(collector.status()["versions"],0)
        self.assertTrue(all(s["error"]=="offline" for s in collector.status()["sources"]))


class IntegrationTests(unittest.TestCase):
    def test_complete_replay_learns_events_and_records_separate_price_control(self):
        from lab.strategies import profit_candidates
        start=T-40*DAY
        rows=candles(3000,start=start)
        events=[event(published=start+i*DAY,observed=start+i*DAY,identity=str(i)) for i in range(32)]
        polls=[{"source":"sec","ts":start+i*DAY,"ok":True,"ttl_ms":DAY} for i in range(32)]
        archive=snapshot(events,polls)
        def fixture_features(section,*args,**kwargs):
            return {"features":[dict(F) for _ in section]}
        with patch("lab.learning_research.build_feature_cache",side_effect=fixture_features), \
             patch("lab.adaptive.profit_candidates",return_value=[profit_candidates()[0]]):
            result=learn_history(rows,"DOT-USD",DEFAULTS,event_snapshot=archive,
                exit_comparison=False,selection_comparison=False)
        self.assertEqual(result["event_data"]["data_sha256"],digest(archive))
        self.assertEqual(result["event_snapshot"],archive)
        self.assertEqual(result["event_data"]["holdout_covered_candles"],600)
        self.assertGreater(result["model"]["observations"],0)
        self.assertTrue(any(any(m["weights"][-7:]) for m in result["model"]["models"].values()))
        self.assertFalse(result["event_comparison"]["selection_uses_comparison"])
        self.assertIn("event_inputs_disabled",result["experiment_registry"]["variants"])
        self.assertEqual(result["event_comparison"]["net_pnl_difference"],
            result["holdout"]["net_pnl"]-result["event_comparison"]["price_context_only"]["holdout"]["net_pnl"])

    def test_study_resume_pins_event_inputs_and_changes_fingerprint_for_new_study(self):
        from lab.paper_store import save_state
        with tempfile.TemporaryDirectory() as tmp:
            service=Service(BASE,Path(tmp)/"db",Path(tmp)/"data")
            learner=service.autolearn
            first=snapshot([event()]);later=snapshot([event(),event(identity="later",observed=T+HOUR)])
            job={}
            self.assertEqual(learner._pin_events(job,first),first)
            self.assertEqual(learner._pin_events(job,later),first)
            old=learner._fingerprint(candles(),"DOT-USD",DEFAULTS,event_snapshot=first)
            new=learner._fingerprint(candles(),"DOT-USD",DEFAULTS,event_snapshot=later)
            self.assertNotEqual(old,new)
            save_state(service.db_path,job["event_snapshot_key"],later)
            with self.assertRaises(ValueError):learner._pin_events(job,first)

    def test_event_features_train_only_after_outcome_and_model_mode_roundtrips(self):
        f={**F,"event_context":EventIndex(snapshot([event()])).at(T)}
        v=feature_vector(f);self.assertEqual(len(v),DIMENSIONS)
        policy=AdaptivePolicy(event_context_enabled=True)
        before=policy.export();p=policy.candidates[0]
        policy.forecast(p,v)
        self.assertEqual(policy.export(),before)
        policy.observe(p,v,-1.,T+HOUR)
        self.assertNotEqual(policy.state["models"][action_key(p)]["eligible_model"]["weights"][-7:],[0.]*7)
        self.assertEqual(AdaptivePolicy(policy.export()).export(),policy.export())
        with self.assertRaises(ValueError):AdaptivePolicy(policy.export(),event_context_enabled=False)

    def test_unknown_coverage_is_not_claimed_as_no_event_and_groups_overlap(self):
        c=EventIndex(snapshot([event()])).at(T)
        result=outcome_summary([{"pnl":-1.,"features":{"event_context":c}},
            {"pnl":2.,"features":{}},{"pnl":99.,"reason":"END","features":{}}])
        self.assertEqual(result["by_entry_context"]["regulation"]["net_pnl"],-1.)
        self.assertEqual(result["by_entry_context"]["coverage_unknown"]["net_pnl"],2.)

    def test_event_api_auth_export_and_no_network_on_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=Service(BASE,Path(tmp)/"db",Path(tmp)/"data",token="test-token")
            service.events.store.record_poll("sec",T,[event()]);service.events._reload()
            with patch.object(service.events,"fetcher",side_effect=AssertionError("network")):
                self.assertEqual(service.handle("GET","/api/events/status")[0],401)
                headers={"Authorization":"Bearer test-token","Content-Type":"application/json"}
                self.assertEqual(service.handle("GET","/api/events/status",headers=headers)[0],200)
                result=service.handle("GET","/api/events/export",headers=headers)
                self.assertEqual(len(json.loads(result[1])["events"]),1)
                self.assertEqual(service.handle("POST","/api/events/start",body={"url":"https://bad"},headers=headers)[0],400)

    def test_forward_feature_uses_same_signal_close_as_historical_join(self):
        rows=candles(300,start=T,step=900000)
        asof=rows[-1]["ts"]+900000
        with tempfile.TemporaryDirectory() as tmp:
            agent=ContinuousLearner(Path(tmp)/"db",Path(tmp)/"data")
            collector=EventCollector(agent.db_path)
            known=event(published=asof-1000,observed=asof-1000)
            future=event(published=asof,observed=asof+1,identity="future")
            collector.store.record_poll("sec",asof-1000,[known])
            collector.store.record_poll("sec",asof+1,[future]);collector._reload()
            agent.events=collector
            agent.market["DOT-USD"]={"bars":{"15m":rows},"ticker":{}}
            f=agent._latest_feature("DOT-USD","15m")
            expected=EventIndex(collector.snapshot(),"DOT-USD").at(asof)
            self.assertEqual(f["event_context"],expected)
            self.assertEqual(len(f["event_context"]["recent"]),1)


if __name__ == "__main__":unittest.main()
