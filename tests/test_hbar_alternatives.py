import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.download_hbar_alternatives import (MINUTE, RangeZip, SourceError,
    add_rows, gaps, parse_binance, parse_kraken, parse_kucoin)

START=1774345140000


class AlternativeDataTests(unittest.TestCase):
    def binance_row(self,scale=1):
        return [START*scale,'2','3','1','2.5','10', (START+MINUTE)*scale-1,
                '25',7,'4','10','0']

    def test_microsecond_archive_matches_millisecond_api(self):
        self.assertEqual(parse_binance(self.binance_row()),
                         parse_binance(self.binance_row(1000),microseconds=True))
        with self.assertRaises(ValueError):parse_binance(self.binance_row(1000))

    def test_kucoin_column_order_and_turnover(self):
        row=parse_kucoin([START//1000,'2','2.5','3','1','10','25'])
        self.assertEqual((row['open'],row['high'],row['low'],row['close']),(2,3,1,2.5))
        self.assertEqual(row['quote_volume'],25)
        self.assertNotIn('trades',row)

    def test_kraken_keeps_trade_count_without_inventing_turnover(self):
        row=parse_kraken([START//1000,'2','3','1','2.5','10','7'])
        self.assertEqual(row['trades'],7)
        self.assertNotIn('quote_volume',row)

    def test_invalid_ohlcv_and_inconsistent_buy_volume_rejected(self):
        for index,value in ((3,'4'),(5,'nan'),(8,-1),(9,'11'),(10,'26')):
            raw=self.binance_row();raw[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):parse_binance(raw)

    def test_unknown_minutes_and_exclusive_end_are_preserved(self):
        row=parse_binance(self.binance_row());found={}
        add_rows(found,[dict(row,ts=START-MINUTE),row,dict(row,ts=START+2*MINUTE)],START,START+2*MINUTE)
        self.assertEqual(set(found),{START})
        self.assertEqual(gaps(set(found),START-MINUTE,START+2*MINUTE),[
            {'start_ts':START-MINUTE,'end_ts':START,'missing':1},
            {'start_ts':START+MINUTE,'end_ts':START+2*MINUTE,'missing':1}])

    def test_conflicting_duplicate_is_not_overwritten(self):
        row=parse_binance(self.binance_row());found={START:row}
        with self.assertRaises(ValueError):
            add_rows(found,[dict(row,volume=11)],START,START+MINUTE)
        self.assertEqual(found[START]['volume'],10)

    def test_range_reader_extracts_and_checks_real_zip_member(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('HBARUSD_1.csv','1774345140,2,3,1,2.5,10,7\n')
        payload=data.getvalue()
        class Cache:
            def get(self,url,name,byte_range):
                left,right=map(int,byte_range.split('-'))
                return payload[left:right+1],{'content_range':f'bytes {left}-{right}/{len(payload)}'}
        with zipfile.ZipFile(RangeZip(Cache(),'https://example.test/data.zip','quarter')) as archive:
            self.assertEqual(archive.read('HBARUSD_1.csv'),b'1774345140,2,3,1,2.5,10,7\n')

    def test_range_reader_refuses_ignored_or_truncated_range(self):
        class WrongCache:
            def get(self,*args):return b'not one byte',{'content_range':'bytes 0-0/100'}
        with self.assertRaises(SourceError):RangeZip(WrongCache(),'https://example.test/data.zip','quarter')


if __name__=='__main__':unittest.main()
