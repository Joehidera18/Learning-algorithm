"""Stock migration boundaries, authenticated workflows and durable queues."""
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lab.http import wsgi_application
from lab.stock_service import StockService, ASSETS
from lab.strategy_jobs import StrategyLabJobs
from lab.experiment_jobs import RESEARCH_SLOT

BASE = Path(__file__).resolve().parents[1]


class StockOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.legacy = self.root/'research.sqlite3'
        self.legacy.write_bytes(b'existing crypto account journal: must remain untouched')
        self.service = StockService(BASE, self.legacy, self.root/'data', 'stock-test-token', resume=False)
        self.service.equities.resume = Mock()
        self.service.strategy_lab.resume = Mock()
        self.app = wsgi_application(self.service)

    def tearDown(self):
        self.service.shutdown()
        self.temp.cleanup()

    def request(self, path, method='GET', body=None, authorized=True, raw=None, content_type='application/json'):
        payload = raw if raw is not None else json.dumps(body if body is not None else {}).encode()
        url, _, query = path.partition('?')
        env = {'PATH_INFO':url, 'QUERY_STRING':query, 'REQUEST_METHOD':method, 'CONTENT_TYPE':content_type,
               'CONTENT_LENGTH':str(len(payload)), 'wsgi.input':io.BytesIO(payload)}
        if authorized:
            env['HTTP_AUTHORIZATION'] = 'Bearer stock-test-token'
        response = []
        value = b''.join(self.app(env, lambda status, headers: response.append((int(status.split()[0]), dict(headers)))))
        return response[0][0], value, response[0][1]

    def test_stock_startup_never_constructs_crypto_workers_or_opens_old_journal(self):
        before = self.legacy.read_bytes()
        with patch('lab.service.ContinuousLearner', side_effect=AssertionError('crypto learner created')), \
             patch('lab.service.CoinbaseTrader', side_effect=AssertionError('broker created')), \
             patch('lab.autolearn.AutoLearner', side_effect=AssertionError('crypto autolearn created')), \
             patch('lab.event_store.EventCollector', side_effect=AssertionError('crypto events created')), \
             patch.dict('os.environ', {'COINBASE_ALLOW_LIVE':'1'}):
            active = StockService(BASE, self.legacy, self.root/'data', resume=True)
            active.shutdown()
        self.assertEqual(before, self.legacy.read_bytes())
        for name in ('agent', 'coinbase', 'autolearn', 'forward', 'research', 'vwap', 'events', 'experiments'):
            self.assertFalse(hasattr(self.service, name), name)

    def test_health_identifies_stock_only_paper_execution(self):
        status, body, _ = self.request('/api/health', authorized=False)
        value = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(value['app_version'], '12.1')
        self.assertEqual(value['asset_class'], 'equity')
        for name in ('live_capable', 'live_orders_allowed', 'crypto_enabled'):
            self.assertFalse(value[name])

    def test_public_pages_and_only_stock_assets_are_served(self):
        for path in ('/', '/stocks', '/stock-practice', '/strategy-lab', '/backtests'):
            status, body, _ = self.request(path, authorized=False)
            self.assertEqual(status, 200, path)
            self.assertIn(b'Stock Lab', body)
            self.assertNotIn(b'Crypto trading', body)
            self.assertNotIn(b'/static/coinbase.js', body)
            self.assertIn(b'/static/stock-session.js', body)
        for asset in ASSETS:
            self.assertEqual(self.request('/static/'+asset, authorized=False)[0], 200, asset)
        for asset in ('coinbase.js', 'app.js', 'experiments.js', '../app.py'):
            self.assertEqual(self.request('/static/'+asset)[0], 404, asset)

    def test_saved_old_page_links_redirect_into_stock_workspace(self):
        self.assertEqual(self.request('/experiments')[2]['Location'], '/strategy-lab')
        self.assertEqual(self.request('/crypto/')[2]['Location'], '/')

    def test_authentication_covers_stock_and_retired_routes(self):
        for path in ('/api/stocks/overview', '/api/stocks/research', '/api/stocks/practice/status',
                     '/api/stocks/practice/forward/export', '/api/strategy-lab/status', '/api/coinbase/status'):
            self.assertEqual(self.request(path, authorized=False)[0], 401, path)
        for path in ('/api/stocks/practice/start', '/api/strategy-lab/start', '/api/strategy-lab/cancel',
                     '/api/coinbase/start', '/api/learning/start'):
            self.assertEqual(self.request(path, 'POST', {}, authorized=False)[0], 401, path)

    def test_even_authorized_old_crypto_actions_are_retired_without_side_effects(self):
        before = self.legacy.read_bytes()
        for path in ('coinbase/start', 'continuous/start', 'learning/start', 'research/start', 'vwap/start',
                     'forward/start', 'experiments/start', 'events/start'):
            self.assertEqual(self.request('/api/'+path, 'POST', {'mode':'live'})[0], 410, path)
        self.assertFalse(self.service.equities.status()['jobs'])
        self.assertEqual(before, self.legacy.read_bytes())

    def test_overview_uses_stock_state_and_does_not_invent_account_returns(self):
        self.service.equities.start({'symbol':'AAPL', 'interval':'1h', 'days':30})
        status, body, _ = self.request('/api/stocks/overview')
        value = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(value['practice']['total_jobs'], 1)
        self.assertEqual(value['jobs'][0]['manifest']['symbol'], 'AAPL')
        self.assertEqual(len(value['universe']), 26)
        self.assertEqual(len({s['ticker'] for s in value['universe']}), 26)
        self.assertEqual(value['forward'], [])
        self.assertNotIn('net_pnl', value)
        self.assertFalse(value['live_orders_allowed'])

    def test_stock_run_and_lab_requests_validate_json_symbols_and_costs(self):
        for path in ('/api/stocks/practice/start', '/api/strategy-lab/start'):
            self.assertEqual(self.request(path, 'POST', {'symbol':'BTC-USD'})[0], 400)
            self.assertEqual(self.request(path, 'POST', {}, content_type='text/plain')[0], 415)
            self.assertEqual(self.request(path, 'POST', [])[0], 400)
            self.assertEqual(self.request(path, 'POST', raw=b'{')[0], 400)
            self.assertEqual(self.request(path, 'POST', raw=b'x'*32769)[0], 413)
        self.assertEqual(self.request('/api/stocks/practice/start', 'POST', {'settings':{'risk_per_trade':99}})[0], 400)

    def test_existing_stock_jobs_and_forward_accounts_survive_service_restart(self):
        created = self.service.equities.start({'symbol':'MSFT', 'interval':'1h', 'days':30})
        self.service.equities._save_forward('saved-account', 'stopped', {'symbol':'MSFT', 'account':None}, insert=True)
        second = StockService(BASE, self.legacy, self.root/'data', 'stock-test-token', resume=False)
        try:
            self.assertEqual(second.equities.get(created['ids'][0])['manifest']['symbol'], 'MSFT')
            self.assertEqual(second.equities.forward_list()[0]['id'], 'saved-account')
        finally:
            second.shutdown()

    def test_research_profile_and_download_still_work(self):
        for path in ('/api/stocks/research', '/api/stocks/research/VRTX', '/api/stocks/research/export', '/api/stocks/research/report'):
            self.assertEqual(self.request(path)[0], 200, path)
        self.assertIn('attachment', self.request('/api/stocks/research/export')[2]['Content-Disposition'])

    def test_cancel_is_authenticated_and_does_not_delete_a_strategy_report(self):
        status, body, _ = self.request('/api/strategy-lab/start', 'POST', {'symbol':'SPY'})
        self.assertEqual(status, 202)
        identity = json.loads(body)['id']
        self.assertEqual(self.request('/api/strategy-lab/cancel', 'POST', {'id':identity}, authorized=False)[0], 401)
        status, body, _ = self.request('/api/strategy-lab/cancel', 'POST', {'id':identity})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['status'], 'cancelled')
        self.service.strategy_lab._patch(identity, status='complete', message='late completion', result={'eligible_for_bot':True})
        self.assertEqual(self.service.strategy_lab.get(identity)['status'], 'cancelled')
        self.assertIsNone(self.service.strategy_lab.get(identity)['result'])


class StockQueueTests(unittest.TestCase):
    def test_strategy_waits_for_shared_compute_slot_and_uses_frozen_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = StrategyLabJobs(directory)
            finished = threading.Event()
            def run(row):
                jobs._patch(row['id'], status='complete', message='fixture')
                finished.set()
            jobs._run = Mock(side_effect=run)
            RESEARCH_SLOT.acquire()
            try:
                created = jobs.start({})
                request = jobs.get(created['id'])['request']
                self.assertLessEqual(request['cutoff_ts'], int(time.time()*1000)-19*60000)
                self.assertFalse(finished.wait(.15))
                jobs._run.assert_not_called()
            finally:
                RESEARCH_SLOT.release()
            try:
                self.assertTrue(finished.wait(3))
                self.assertEqual(jobs.get(created['id'])['status'], 'complete')
            finally:
                jobs.shutdown()

    def test_restart_marks_an_interrupted_job_incomplete_and_preserves_its_request(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = StrategyLabJobs(directory)
            with patch.object(jobs, 'resume'):
                created = jobs.start({})
            jobs._patch(created['id'], status='running', message='old process')
            original = jobs.get(created['id'])['request']
            jobs.resume()
            try:
                self.assertEqual(jobs.get(created['id'])['status'], 'error')
                self.assertEqual(jobs.get(created['id'])['request'], original)
                self.assertIn('restart', jobs.get(created['id'])['message'])
            finally:
                jobs.shutdown()

    def test_cancelled_job_never_downloads_candles(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = StrategyLabJobs(directory)
            with patch.object(jobs, 'resume'):
                created = jobs.start({})
            row = jobs.get(created['id'])
            jobs.cancel(created['id'])
            with patch('lab.equity_data.EquityData.history') as history:
                jobs._run({'id':row['id'], 'request_json':json.dumps(row['request'])})
                history.assert_not_called()
            self.assertEqual(jobs.get(created['id'])['status'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
