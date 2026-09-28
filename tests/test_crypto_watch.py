"""Causal fixtures, not historical market evidence or a profitability backtest."""
import copy
import json
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from lab.crypto_watch import CryptoWatch, CandleSource, STEP, HOUR, SYMBOLS, evaluate, normalize, now_ms
from lab.paper_store import db_connect
from lab.stock_service import StockService


def fixture_rows(observed, stage="quiet"):
    end = observed // STEP * STEP
    rows = [dict(ts=end - (289 - i) * STEP, open=100., high=100.3, low=99.7, close=100., volume=10000.)
            for i in range(289)]
    if stage != "quiet":
        close = {"building": 100.2, "breakout": 100.5, "extended": 120.}[stage]
        rows[-1].update(close=close, high=max(100.3, close + .1), volume=32000.)
    return rows


def fixture_news(observed):
    from email.utils import formatdate
    published = formatdate((observed - 2 * HOUR) / 1000, usegmt=True)
    return ('<rss><channel><item><guid>fixture-hbar</guid><title>Hedera test headline</title>'
            '<link>https://example.org/hbar-fixture</link><pubDate>' + published +
            '</pubDate></item></channel></rss>').encode()


class FixtureSource:
    def candles(self, symbol, observed):
        if symbol == "LTC-USD":
            raise TimeoutError("Generated unavailable-data fixture")
        stage = {"HBAR-USD": "breakout", "ETH-USD": "extended", "SOL-USD": "building"}.get(symbol, "quiet")
        return fixture_rows(observed, stage)


class SignalTests(unittest.TestCase):
    def setUp(self):
        self.at = now_ms() // STEP * STEP + 15000
        self.btc = fixture_rows(self.at)

    def signal(self, rows, at=None, btc=None):
        return evaluate("HBAR-USD", rows, self.btc if btc is None else btc, self.at if at is None else at)

    def test_breakout_excludes_event_high_and_volume_from_baselines(self):
        signal = self.signal(fixture_rows(self.at, "breakout"))
        self.assertEqual(signal["stage"], "breakout")
        self.assertAlmostEqual(signal["metrics"]["relative_volume"], 3.2)
        self.assertEqual(signal["metrics"]["prior_high"], 100.3)
        self.assertEqual(signal["candle_end_ts"], self.at // STEP * STEP)
        self.assertNotIn("probability", signal)

    def test_future_and_still_open_candles_cannot_create_a_signal(self):
        rows = fixture_rows(self.at)
        future = dict(rows[-1], ts=self.at // STEP * STEP, close=150., high=151., volume=1e8)
        self.assertEqual(self.signal(rows + [future])["stage"], "quiet")
        future["ts"] += STEP
        self.assertEqual(self.signal(rows + [future]), self.signal(rows))

    def test_building_interest_requires_actual_relative_strength(self):
        rows = fixture_rows(self.at, "building")
        self.assertEqual(self.signal(rows)["stage"], "building")
        fast_btc = fixture_rows(self.at, "breakout")
        self.assertEqual(self.signal(rows, btc=fast_btc)["stage"], "quiet")

    def test_already_extended_move_is_not_called_an_early_breakout(self):
        rows = fixture_rows(self.at, "extended")
        rows[-1]["volume"] = 10000.
        self.assertEqual(self.signal(rows)["stage"], "extended")

    def test_gaps_stale_and_insufficient_history_block_signals(self):
        rows = fixture_rows(self.at, "breakout")
        older = dict(rows[0], ts=rows[0]["ts"] - STEP)
        for changed, at in ((rows[1:], self.at), ([older] + rows[:80] + rows[81:], self.at),
                            (rows, self.at + 3 * STEP)):
            with self.subTest(at=at, count=len(changed)):
                self.assertEqual(self.signal(changed, at)["stage"], "unavailable")

    def test_invalid_and_conflicting_data_is_not_silently_repaired(self):
        for field, value in (("high", 90.), ("volume", float("nan")), ("close", float("inf")), ("volume", -1.)):
            rows = fixture_rows(self.at, "breakout")
            rows[-1][field] = value
            self.assertEqual(self.signal(rows)["stage"], "unavailable")
        rows = fixture_rows(self.at)
        self.assertEqual(self.signal(rows + [dict(rows[-1], volume=1234)])['stage'], 'unavailable')
        self.assertEqual(len(normalize(rows + [rows[-1]], self.at)), len(rows))

    def test_thin_liquidity_does_not_generate_alerts(self):
        rows = fixture_rows(self.at, "breakout")
        for row in rows:
            row["volume"] /= 100000
        signal = self.signal(rows)
        self.assertEqual(signal["stage"], "unavailable")
        self.assertIn("liquidity", signal["reasons"][0])

    def test_missing_or_misaligned_benchmark_is_not_assumed_flat(self):
        rows = fixture_rows(self.at, "breakout")
        for benchmark in ([], self.btc[:-1], self.btc[:-2] + self.btc[-1:]):
            self.assertEqual(self.signal(rows, btc=benchmark)["stage"], "unavailable")
        self.assertEqual(evaluate("BTC-USD", rows, [], self.at)["stage"], "breakout")

    def test_provider_whitelist_schema_and_response_limit(self):
        source = CandleSource()
        with self.assertRaises(ValueError):
            source.candles("https://example.org", self.at)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        for payload in (b'{}', b'[[1,2]]', b'x' * 1000001):
            response.read.return_value = payload
            with patch('urllib.request.build_opener') as opener:
                opener.return_value.open.return_value = response
                with self.assertRaises(ValueError):
                    source.candles("HBAR-USD", self.at)
                self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 8)


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.watch = CryptoWatch(self.temp.name, "fixture-token", FixtureSource(), lambda _: fixture_news(now_ms()))
        self.watch._set(enabled=True)

    def tearDown(self):
        self.watch.shutdown()
        if self.watch.worker:
            self.watch.worker.join(timeout=3)
        self.temp.cleanup()

    def test_snapshot_and_journal_use_observation_time_not_candle_time(self):
        self.watch._scan()
        status = self.watch.status()
        hbar = next(s for s in status['signals'] if s['symbol'] == 'HBAR-USD')
        self.assertEqual(hbar['stage'], 'breakout')
        self.assertTrue(hbar['initial_observation'])
        self.assertGreaterEqual(hbar['observed_ts'], hbar['candle_end_ts'])
        first = copy.deepcopy(status['alerts'])
        self.watch._scan()
        self.assertEqual(first, self.watch.status()['alerts'])
        self.assertTrue(all(a['initial_observation'] for a in first))

    def test_cooldown_and_gap_snapshots_do_not_manufacture_early_detections(self):
        at = now_ms()
        signal = evaluate('HBAR-USD', fixture_rows(at, 'breakout'), fixture_rows(at), at)
        self.watch._publish(signal)
        self.watch._publish(dict(signal, observed_ts=at+STEP, candle_end_ts=signal['candle_end_ts']+STEP))
        self.assertEqual(len(self.watch.status()['alerts']), 1)
        later = dict(signal, observed_ts=at+HOUR, candle_end_ts=signal['candle_end_ts']+HOUR)
        self.watch._publish(later)
        self.assertEqual(len(self.watch.status()['alerts']), 2)
        self.assertTrue(self.watch.status()['alerts'][0]['initial_observation'])

    def test_news_retains_first_observed_revision_and_publication_separately(self):
        at = now_ms()
        raw = fixture_news(at)
        self.watch.news_fetch = lambda _: raw
        with patch('lab.crypto_watch.now_ms', return_value=at):
            self.watch._news()
        original = self.watch.status()['news']['items'][0]
        self.assertGreater(original['observed_ts'], original['published_ts'])
        self.assertEqual(original['available_ts'], at)
        with patch('lab.crypto_watch.now_ms', return_value=at+HOUR):
            self.watch._news()
        self.assertEqual(self.watch.status()['news']['items'], [original])
        self.watch.news_fetch = lambda _: raw.replace(b'test headline', b'revised headline')
        with patch('lab.crypto_watch.now_ms', return_value=at+HOUR):
            self.watch._news()
        items = self.watch.status()['news']['items']
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['observed_ts'], at+HOUR)
        self.assertEqual(items[1]['observed_ts'], at)

    def test_feed_failures_and_stale_observations_are_explicit(self):
        self.watch.news_fetch = Mock(side_effect=TimeoutError('fixture news timeout'))
        self.watch._scan()
        status = self.watch.status()
        self.assertIn('timeout', status['news']['error'])
        self.assertEqual(next(s for s in status['signals'] if s['symbol']=='LTC-USD')['stage'], 'unavailable')
        with patch('lab.crypto_watch.now_ms', return_value=now_ms()+3*STEP):
            self.assertTrue(all(s['stale'] for s in self.watch.status()['signals']))

    def test_stop_during_slow_request_prevents_late_signals_and_new_fetches(self):
        began, release = threading.Event(), threading.Event()
        def slow(symbol, observed):
            began.set()
            release.wait(3)
            return fixture_rows(observed, 'breakout')
        self.watch.client.candles = Mock(side_effect=slow)
        try:
            self.watch.start()
            self.assertTrue(began.wait(2))
            self.watch.start()  # Idempotent; no second worker/request.
            self.watch.stop()
            with self.assertRaises(RuntimeError):
                self.watch.start()
        finally:
            release.set()
            self.watch.worker.join(3)
        self.assertEqual(self.watch.client.candles.call_count, 1)
        self.assertFalse(self.watch.status()['alerts'])
        self.assertFalse(self.watch.status()['enabled'])

    def test_shutdown_preserves_enablement_and_resume_uses_existing_state(self):
        finished = threading.Event()
        self.watch._scan = lambda: finished.set()
        self.watch.start()
        self.assertTrue(finished.wait(2))
        self.watch.shutdown()
        self.assertTrue(self.watch.status()['enabled'])
        second = CryptoWatch(self.temp.name, 'fixture-token', FixtureSource(), lambda _: fixture_news(now_ms()))
        second._scan = Mock()
        try:
            second.resume()
            self.assertTrue(second.status()['running'])
        finally:
            second.stop()
            second.shutdown()
        third = CryptoWatch(self.temp.name, 'fixture-token')
        third.resume()
        self.assertIsNone(third.worker)

    def test_process_lease_prevents_duplicate_watchers(self):
        self.watch.lease.acquire()
        other = CryptoWatch(self.temp.name, 'fixture-token')
        try:
            with self.assertRaises(RuntimeError):
                other.start()
            self.assertTrue(other.status()['enabled'])
        finally:
            self.watch.lease.release()

    def test_resume_waits_for_previous_process_to_release_lease(self):
        self.watch.lease.acquire()
        second = CryptoWatch(self.temp.name, 'fixture-token')
        scanned = threading.Event()
        second._scan = scanned.set
        try:
            second.resume()
            self.assertIsNone(second.worker)
            self.watch.lease.release()
            self.assertTrue(scanned.wait(7))
        finally:
            self.watch.lease.release()
            second.stop()
            second.shutdown()

    def test_status_never_calls_network_or_creates_live_trades(self):
        self.watch.client.candles = Mock(side_effect=AssertionError('Network on request thread'))
        self.watch.news_fetch = Mock(side_effect=AssertionError('Network on request thread'))
        self.assertEqual(len(self.watch.status()['signals']), 12)
        self.assertFalse(self.watch.status()['execution_enabled'])
        self.watch.client.candles.assert_not_called()
        self.watch.news_fetch.assert_not_called()


class WatchRoutesTests(unittest.TestCase):
    def test_routes_require_authentication_and_workspace_exposes_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            service = StockService(Path(__file__).resolve().parents[1], Path(directory)/'old.db', directory, 'fixture', resume=False)
            headers = {'authorization': 'Bearer fixture', 'content-type': 'application/json'}
            try:
                for path in ('status', 'export', 'start', 'stop'):
                    method = 'GET' if path in ('status','export') else 'POST'
                    self.assertEqual(service.handle(method, '/api/crypto-watch/'+path, body={}, headers={})[0], 401)
                self.assertEqual(service.handle('POST', '/api/crypto-watch/start', body={'symbol':'URL'}, headers=headers)[0], 400)
                self.assertEqual(service.handle('GET', '/api/crypto-watch/status', headers=headers)[0], 200)
                self.assertIn('attachment', service.handle('GET', '/api/crypto-watch/export', headers=headers)[2]['Content-Disposition'])
                self.assertFalse(service.overview()['crypto_watch']['execution_enabled'])
                service.token = service.breakout_watch.token = ''
                self.assertEqual(service.handle('POST', '/api/crypto-watch/start', body={}, headers=headers)[0], 503)
            finally:
                service.shutdown()


if __name__ == '__main__':
    unittest.main()
