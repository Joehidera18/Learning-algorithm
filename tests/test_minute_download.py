"""Downloader fixtures check records and bounds, never market performance."""
import tempfile
import unittest
from unittest.mock import patch
from scripts.download_coinbase_minutes import (MINUTE, Downloader, compare_feeds,
                                                coverage, normalize, request_url, windows)

START = 1774345140000
BAR = [START//1000, 1., 3., 2., 2.5, 10.]


class MinuteDownloadTests(unittest.TestCase):
    def test_windows_cover_exact_requested_range_without_overlap(self):
        plan = windows(START, START+1000*MINUTE)
        self.assertEqual(plan[0][0], START)
        self.assertEqual(plan[-1][1], START+1000*MINUTE)
        self.assertTrue(all(b-a <= 299*MINUTE for a,b in plan))
        self.assertTrue(all(a[1] == b[0] for a,b in zip(plan,plan[1:])))
        with self.assertRaises(ValueError): windows(START+1, START+MINUTE)

    def test_api_boundary_rows_do_not_extend_coverage(self):
        before = [BAR[0]-60, *BAR[1:]]
        after = [BAR[0]+60, *BAR[1:]]
        rows = normalize('exchange', [after, BAR, before, BAR], START, START+MINUTE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['ts'], START)

    def test_malformed_prices_duplicates_and_timestamps_fail(self):
        for raw in ([BAR, [BAR[0], 1., 3., 2., 2.5, 11.]],
                    [[BAR[0], 4., 3., 2., 2.5, 10.]],
                    [[BAR[0]+1, *BAR[1:]]],
                    [[BAR[0], 1., 3., 2., 2.5, float('nan')]]):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                normalize('exchange', raw, START, START+MINUTE)

    def test_advanced_schema_uses_real_volume_and_no_fabrication(self):
        payload = {'candles': [{'start':str(BAR[0]), 'low':'1', 'high':'3',
                               'open':'2', 'close':'2.5', 'volume':'10'}]}
        self.assertEqual(normalize('advanced', payload, START, START+MINUTE),
                         normalize('exchange', [BAR], START, START+MINUTE))
        self.assertEqual(normalize('advanced', {'candles':[]}, START, START+MINUTE), [])

    def test_missing_endpoints_and_internal_minutes_are_retained(self):
        rows = normalize('exchange', [BAR], START, START+MINUTE)
        report = coverage(rows, START-MINUTE, START+2*MINUTE)
        self.assertEqual(report['observed_minutes'], 1)
        self.assertEqual(report['missing_minutes'], 2)
        self.assertEqual(len(report['missing_ranges']), 2)

    def test_feed_differences_are_reported_without_merging(self):
        first = normalize('exchange', [BAR], START, START+MINUTE)
        second = [dict(first[0], volume=11.), dict(first[0], ts=START+MINUTE)]
        result = compare_feeds(first, second)
        self.assertEqual(result['conflicting_minutes'], 1)
        self.assertEqual(result['advanced_only_minutes'], 1)
        self.assertFalse(result['merged'])
        self.assertEqual(first[0]['volume'], 10.)

    def test_unavailable_source_stops_before_full_download(self):
        with tempfile.TemporaryDirectory() as folder:
            downloader = Downloader(folder)
            with patch.object(downloader, 'fetch', side_effect=RuntimeError('timeout')) as fetch:
                rows, report = downloader.download('exchange', 'HBAR-USD', START, START+1000*MINUTE)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(rows, [])
            self.assertFalse(report['complete_request_scan'])
            self.assertEqual(report['missing_minutes'], 1000)


if __name__ == '__main__':
    unittest.main()
