import gzip
import json
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path
from scripts.build_coin_candle_library import FIELDS, aggregate_stream, export, insert, missing, parse_rows


def row(t):
    return dict(zip(FIELDS,[t,2.,3.,1.,2.5,10.,25.,7,4.,10.]))


class CandleLibraryTests(unittest.TestCase):
    def test_output_verification_rejects_truncated_gzip_even_with_matching_hash(self):
        import hashlib
        from scripts.repair_candle_archive import verify_archive
        raw=gzip.compress((','.join(FIELDS)+'\n'+','.join(str(row(0)[k]) for k in FIELDS)+'\n').encode())[:-8]
        frame=dict(file='candles.csv.gz',sha256=hashlib.sha256(raw).hexdigest(),rows=1)
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'truncated.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('manifest.json',json.dumps(dict(timeframes=[frame])))
                z.writestr(frame['file'],raw)
            with self.assertRaises(EOFError):verify_archive(archive)

    def test_archive_repair_preserves_old_rows_and_updates_all_frames(self):
        from scripts.repair_candle_archive import main
        con=sqlite3.connect(':memory:')
        con.execute('CREATE TABLE candles ('+','.join(k+(' INTEGER PRIMARY KEY' if k=='ts' else ' INTEGER' if k=='trades' else ' REAL') for k in FIELDS)+')')
        insert(con,[row(i*60000) for i in range(240) if i!=2])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);frames=export(con,root,'TESTUSDT',0,14400000)
            manifest=dict(coin='TEST',pair='TESTUSDT',first_available_ts=0,end_ts_exclusive=14400000,
                          remaining_minute_gaps=[dict(start_ts=120000,end_ts=180000,minutes=1)],
                          timeframes=frames,sources=[])
            archive=root/'input.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('manifest.json',json.dumps(manifest));z.writestr('README.txt','fixture')
                for f in frames:z.write(root/f['file'],f['file'])
            # Offline recovery must never call a downloader on an absent checkpoint.
            with patch('sys.argv',['repair',str(archive),'--out',str(root/'offline'),'--offline']), patch(
                    'scripts.download_hbar_alternatives.subprocess.run') as network:
                main()
                network.assert_not_called()
            offline=json.loads((root/'offline'/'manifest.json').read_text())
            self.assertEqual(offline['missing_minutes_after_repair'],1)
            self.assertEqual(offline['supplemental_repair']['recovered_minutes'],0)
            with patch('sys.argv',['repair',str(archive),'--out',str(root/'fixed')]), patch(
                    'scripts.repair_candle_archive.api',return_value=([row(120000)],{'source':'fixture'})):
                main()
            result=json.loads((root/'fixed'/'manifest.json').read_text())
            self.assertEqual(result['supplemental_repair']['recovered_minutes'],1)
            self.assertTrue(all(f['missing_candles']==0 for f in result['timeframes']))
            with gzip.open(root/'fixed'/frames[0]['file'],'rt') as f:
                import csv
                restored=list(csv.DictReader(f))
            self.assertEqual([int(r['ts']) for r in restored],list(range(0,14400000,60000)))

    def test_supplemental_repair_completes_only_observed_buckets(self):
        from scripts.repair_candle_archive import affected_bars
        old=[row(i*60000) for i in (0,1,3,4,5,7)]
        additions=affected_bars(old,{120000:row(120000)},4,0,480000)
        self.assertEqual(list(additions),[0])
        self.assertEqual(additions[0]['volume'],40)
        with self.assertRaises(ValueError):
            affected_bars(old,{0:dict(row(0),close=2.1)},4,0,480000)

    def test_bad_source_row_does_not_discard_valid_neighbors(self):
        def raw(t):return [t,2,3,1,2.5,10,t+59999,25,7,4,10,0]
        bad=raw(60000);bad[6]+=1
        rows,rejected=parse_rows([raw(0),bad,raw(120000)])
        self.assertEqual([r['ts'] for r in rows],[0,120000])
        self.assertEqual(len(rejected),1)
        self.assertEqual(rejected[0]['row_index'],1)

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
        con.execute('CREATE TABLE candles ('+','.join(k+(' INTEGER PRIMARY KEY' if k=='ts' else ' INTEGER' if k=='trades' else ' REAL') for k in FIELDS)+')')
        insert(con,[row(0)])
        with self.assertRaises(ValueError):insert(con,[dict(row(0),close=2.6)])
        self.assertEqual(missing(con,0,180000),[{'start_ts':60000,'end_ts':180000,'minutes':2}])

    def test_export_reports_gaps_and_provider_empty_buckets(self):
        con=sqlite3.connect(':memory:')
        con.execute('CREATE TABLE candles ('+','.join(k+(' INTEGER PRIMARY KEY' if k=='ts' else ' INTEGER' if k=='trades' else ' REAL') for k in FIELDS)+')')
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
