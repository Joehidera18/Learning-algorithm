import gzip
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.build_coin_candle_library import FIELDS, aggregate_stream, export, insert, missing


def row(t):
    return dict(zip(FIELDS,[t,2.,3.,1.,2.5,10.,25.,7,4.,10.]))


class CandleLibraryTests(unittest.TestCase):
    def test_four_minute_ohlcv_and_actual_volume_fields(self):
        result=list(aggregate_stream([row(i*60000) for i in range(4)],4,0,240000))
        self.assertEqual(len(result),1)
        self.assertEqual((result[0]['volume'],result[0]['quote_volume'],result[0]['trades']),(40,100,28))
        self.assertEqual(result[0]['taker_buy_base_volume'],16)

    def test_missing_minute_cannot_be_hidden_in_a_larger_bar(self):
        rows=[row(i*60000) for i in (0,1,3,4,5,6,7)]
        self.assertEqual([r['ts'] for r in aggregate_stream(rows,4,0,480000)],[240000])

    def test_partial_first_and_last_buckets_are_excluded(self):
        rows=[row(i*60000) for i in range(1,10)]
        self.assertEqual([r['ts'] for r in aggregate_stream(rows,4,60000,600000)],[240000])

    def test_duplicate_and_conflicting_rows_fail(self):
        with self.assertRaises(ValueError):list(aggregate_stream([row(0),row(0)],4,0,240000))
        con=sqlite3.connect(':memory:')
        con.execute('CREATE TABLE candles ('+','.join(k+(' INTEGER PRIMARY KEY' if k=='ts' else ' REAL') for k in FIELDS)+')')
        insert(con,[row(0)])
        with self.assertRaises(ValueError):insert(con,[dict(row(0),close=2.6)])
        self.assertEqual(missing(con,0,180000),[{'start_ts':60000,'end_ts':180000,'minutes':2}])

    def test_export_reports_gaps_and_provider_empty_buckets(self):
        con=sqlite3.connect(':memory:')
        con.execute('CREATE TABLE candles ('+','.join(k+(' INTEGER PRIMARY KEY' if k=='ts' else ' REAL') for k in FIELDS)+')')
        rows=[row(i*60000) for i in range(8) if i!=2]
        rows[-1]=dict(rows[-1],volume=0,quote_volume=0,trades=0,taker_buy_base_volume=0,taker_buy_quote_volume=0)
        insert(con,rows)
        with tempfile.TemporaryDirectory() as tmp:
            reports=export(con,Path(tmp),'TESTUSDT',0,480000)
            one=next(r for r in reports if r['interval']=='1m')
            four=next(r for r in reports if r['interval']=='4m')
            self.assertEqual((one['rows'],one['missing_candles'],one['zero_volume_rows']),(7,1,1))
            self.assertEqual((four['rows'],four['missing_candles']),(1,1))


if __name__=='__main__':unittest.main()
