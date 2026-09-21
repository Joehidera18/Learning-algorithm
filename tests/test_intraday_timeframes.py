"""Check source pagination and missing-minute behavior without network access."""
import unittest
from datetime import datetime
from unittest.mock import patch
from lab.coinbase_feed import CoinbaseClient
from lab.continuous import resample
from lab.study_plan import ACTIVE_INTERVALS, DEFAULT_PRACTICE_INTERVALS, normalize_plan

class IntradayTests(unittest.TestCase):
    def test_all_requested_frames_are_default_and_accepted(self):
        expected=('1m','4m','5m','15m','30m','1h','4h')
        self.assertEqual(tuple(DEFAULT_PRACTICE_INTERVALS),expected)
        self.assertEqual(tuple(ACTIVE_INTERVALS),expected)
        self.assertEqual(normalize_plan(list(expected),1825,'15m')[0],list(expected))

    def test_derived_coinbase_frames_paginate_and_exclude_incomplete_bars(self):
        client=CoinbaseClient()
        for interval,source,target in [('4m',60,240),('30m',900,1800),('4h',3600,14400)]:
            with self.subTest(interval=interval):
                end=1800000000000//(target*1000)*target*1000
                missing=end//1000-source*2
                calls=[]
                def get(path,params):
                    self.assertEqual(params['granularity'],source)
                    start=int(datetime.fromisoformat(params['start']).timestamp())
                    stop=int(datetime.fromisoformat(params['end']).timestamp())
                    self.assertLessEqual((stop-start)//source,300)
                    calls.append((start,stop))
                    return [[t,99,102,100,101,1] for t in range(start,stop+source,source) if t!=missing]
                with patch.object(client,'_get',side_effect=get):
                    rows=client.candles('BTC-USD',interval,500,end+1000)
                self.assertEqual(len(rows),499)
                self.assertGreater(len(calls),1)
                self.assertEqual(rows[0]['ts'],end-500*target*1000)
                self.assertEqual(rows[-1]['ts'],end-2*target*1000)
                self.assertTrue(all(r['volume']==target//source for r in rows))

    def test_resample_rejects_duplicate_or_missing_minutes_and_open_bucket(self):
        rows=[dict(ts=i*60000,open=100,high=102,low=99,close=101,volume=1) for i in range(12)]
        self.assertEqual(len(resample(rows,240000,asof_ms=660000,source_step=60000)),2)
        broken=rows[:3]+rows[4:]+[rows[5]]
        self.assertEqual(resample(broken,240000,asof_ms=660000,source_step=60000),[])
