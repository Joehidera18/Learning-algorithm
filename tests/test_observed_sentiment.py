"""Provider values are dated observations, never backfilled trading knowledge."""
import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from lab.event_context import DAY, EventIndex, INPUT_NAMES, vector, validate_snapshot, without_sentiment
from lab.event_feeds import parse, source_info
from lab.event_store import EventCollector, EventStore
from tests.test_market_events import T, event, snapshot


def payload(value=25, previous=30, published=T):
    return json.dumps({'data':[{'value':str(value),'timestamp':str(published//1000)},
        {'value':str(previous),'timestamp':str((published-DAY)//1000)}], 'metadata':{'error':None}}).encode()


def archive(raw=None, observed=T+1000):
    records=parse('alternative_fng',raw or payload(),observed)
    s=snapshot(records,[{'source':'alternative_fng','ts':observed,'ok':True,'ttl_ms':DAY}])
    s['source_info']=source_info()
    return s


class SentimentTests(unittest.TestCase):
    def test_old_dates_never_enter_before_actual_receipt_and_missing_is_not_neutral(self):
        index=EventIndex(archive(), 'DOT-USD')
        self.assertFalse(index.at(T)['sentiment']['available'])
        known=index.at(T+1000)
        self.assertEqual(known['sentiment']['value'],25)
        self.assertEqual(known['sentiment']['change_1d'],-5)
        inputs=dict(zip(INPUT_NAMES,vector(known)))
        self.assertEqual(inputs['sentiment_value'],-.5)
        self.assertEqual(inputs['sentiment_available'],1.)
        neutral=dict(zip(INPUT_NAMES,vector(EventIndex(archive(payload(50))).at(T+1000))))
        self.assertEqual(neutral['sentiment_value'],0.)
        self.assertEqual(neutral['sentiment_available'],1.)
        missing=dict(zip(INPUT_NAMES,vector(index.at(T))))
        self.assertEqual(missing['sentiment_value'],0.)
        self.assertEqual(missing['sentiment_available'],0.)

    def test_revisions_are_causal_and_older_backfill_cannot_replace_newest_date(self):
        s=archive();earlier=EventIndex(s).at(T+1000)
        revisions=parse('alternative_fng',payload(70),T+2000)
        s['events']+=revisions
        index=EventIndex(s)
        self.assertEqual(index.at(T+1000),earlier)
        self.assertEqual(index.at(T+2000)['sentiment']['value'],70)
        self.assertEqual(index.at(T+2000)['sentiment']['published_ts'],T)
        self.assertEqual(index.at(T+2000)['sentiment']['observed_ts'],T+2000)

    def test_poll_failure_and_stale_index_each_remove_sentiment(self):
        s=archive();s['polls'].append({'source':'alternative_fng','ts':T+2000,'ok':False,'ttl_ms':DAY})
        self.assertFalse(EventIndex(s).at(T+2000)['sentiment']['available'])
        s=archive();s['polls'].append({'source':'alternative_fng','ts':T+2*DAY,'ok':True,'ttl_ms':DAY})
        self.assertFalse(EventIndex(s).at(T+2*DAY)['sentiment']['available'])
        self.assertFalse(EventIndex(archive()).at(T+1000+DAY)['sentiment']['available'])

    def test_invalid_values_future_dates_and_forged_archives_are_rejected(self):
        for raw in (payload(101),payload(-1),payload(published=T+DAY),b'{"data":[]}'):
            with self.assertRaises(ValueError):parse('alternative_fng',raw,T+1000)
        for bad in (True,1000,float('nan')):
            s=archive();s['events'][0]['sentiment_value']=bad
            with self.assertRaises(ValueError):validate_snapshot(s)

    def test_repeated_poll_retains_first_observation_and_control_retains_news(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=EventStore(Path(tmp)/'events.db')
            for ts in (T+1000,T+2000):store.record_poll('alternative_fng',ts,parse('alternative_fng',payload(),ts))
            s=store.snapshot();self.assertEqual(len(s['events']),2)
            self.assertEqual({e['observed_ts'] for e in s['events']},{T+1000})
        s['events'].append(event());s['polls'].append({'source':'sec','ts':T,'ok':True,'ttl_ms':DAY})
        c=without_sentiment(s)
        self.assertNotIn('alternative_fng',c['sources'])
        self.assertEqual([e['source'] for e in c['events']],['sec'])
        self.assertFalse(EventIndex(c).at(T+2000)['sentiment']['available'])

    def test_fast_success_is_published_before_slow_feed_finishes(self):
        release=threading.Event()
        def fetch(source):
            if source=='alternative_fng':return payload()
            release.wait(3);raise OSError('offline')
        with tempfile.TemporaryDirectory() as tmp:
            collector=EventCollector(Path(tmp)/'events.db',fetcher=fetch)
            with patch('lab.event_store.now_ms',return_value=T+1000):
                try:
                    result=collector.prepare_for_study(timeout=1.)
                    self.assertTrue(any(p['ok'] for p in result['polls']))
                    self.assertFalse(release.is_set())
                    self.assertTrue(collector.worker.is_alive())
                    self.assertEqual(EventIndex(result).at(T+1000)['sentiment']['value'],25)
                finally:
                    collector.stop();release.set();collector.worker.join(3)


if __name__=='__main__':unittest.main()
