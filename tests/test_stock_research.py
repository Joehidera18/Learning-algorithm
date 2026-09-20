"""Research freshness, authenticated exports, and isolation from trading state."""
import copy
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from lab.service import Service, wsgi_application
from lab.stock_research import EDITION, research_payload

BASE = Path(__file__).resolve().parents[1]


class ResearchEditionTests(unittest.TestCase):
    def test_catalog_is_complete_and_sources_are_external_https(self):
        data = research_payload(BASE, date(2026, 9, 20))
        tickers = [stock['ticker'] for stock in data['stocks']]
        self.assertEqual(len(tickers), 20)
        self.assertEqual(len(set(tickers)), 20)
        self.assertEqual(sorted(s['priority'] for s in data['stocks']), list(range(1, 21)))
        self.assertEqual(data['focus_tickers'], ['VRTX', 'AVGO', 'ALNY', 'VRT', 'BEAM'])
        self.assertEqual(set(data['focus_tickers']), {s['ticker'] for s in data['stocks'] if s['focus']})
        self.assertEqual(data['edition'], EDITION)
        self.assertFalse(data['live_quotes'])
        self.assertFalse(data['trading_enabled'])
        for stock in data['stocks']:
            with self.subTest(ticker=stock['ticker']):
                self.assertEqual(stock['asset_class'], 'stock')
                self.assertGreaterEqual(len(stock['blocks']), 3)
                self.assertTrue(all(block['paragraphs'] for block in stock['blocks']))
                self.assertTrue(stock['sources'])
                self.assertIn(stock['sector'], data['sectors'])
                self.assertIn(stock['exposure'], data['exposures'])
                for url in [stock['quote_url'], *[s['url'] for s in stock['sources']]]:
                    parsed = urlparse(url)
                    self.assertEqual(parsed.scheme, 'https')
                    self.assertTrue(parsed.netloc)
                    self.assertIsNone(parsed.username)
        for theme in data['themes']:
            self.assertLessEqual(set(theme['tickers']), set(tickers))
        for row in data['valuation_checks']:
            self.assertIn(row['ticker'], tickers)
            self.assertEqual(row['price_as_of'], data['market_data_as_of'])

    def test_elapsed_dates_require_review_and_never_imply_success(self):
        data = research_payload(BASE, date(2027, 1, 1))
        self.assertEqual(data['review']['status'], 'review_due')
        stocks = {s['ticker']: s for s in data['stocks']}
        for ticker in ('VRTX', 'BEAM', 'VKTX'):
            self.assertEqual(stocks[ticker]['catalyst']['calendar_status'], 'review_needed')
        self.assertEqual(stocks['ETN']['catalyst']['calendar_status'], 'window_open')
        self.assertTrue(all(s['catalyst']['outcome'] == 'not_verified' for s in data['stocks']))
        self.assertEqual(data['research_as_of'], '2026-09-20')
        today = research_payload(BASE, date(2026, 11, 30))
        self.assertEqual(today['stocks'][0]['catalyst']['calendar_status'], 'date_today')
        self.assertEqual(research_payload(BASE, date(2026, 9, 19))['review']['status'], 'future_date')

    def test_responses_do_not_mutate_the_packaged_edition(self):
        first = research_payload(BASE, date(2027, 1, 1))
        first['stocks'][0]['sources'].clear()
        first['focus_tickers'].clear()
        original = research_payload(BASE, date(2026, 9, 20))
        self.assertTrue(original['stocks'][0]['sources'])
        self.assertEqual(len(original['focus_tickers']), 5)
        self.assertEqual(original['review']['status'], 'dated')
        self.assertEqual(original['stocks'][0]['catalyst']['calendar_status'], 'scheduled')


class StockResearchRoutesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = Service(BASE, Path(self.tmp.name) / 'test.sqlite3', Path(self.tmp.name) / 'data', token='research-test-token')
        self.app = wsgi_application(self.service)

    def tearDown(self):
        self.service.forward.shutdown()
        self.service.events.stop(persist=False)
        self.service.agent.stop()
        self.tmp.cleanup()

    def request(self, path, method='GET', auth='Bearer research-test-token'):
        raw = b'{}' if method == 'POST' else b''
        result = {}
        environ = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'QUERY_STRING': '',
                   'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(raw)),
                   'HTTP_AUTHORIZATION': auth, 'wsgi.input': io.BytesIO(raw)}
        def start(status, headers):
            result.update(status=int(status.split()[0]), headers=dict(headers))
        result['body'] = b''.join(self.app(environ, start))
        return result

    def test_html_assets_and_health_work_without_token(self):
        for path in ('/', '/stocks', '/stocks/', '/static/stocks.js', '/static/stocks.css', '/api/health'):
            self.assertEqual(self.request(path, auth='')['status'], 200, path)
        html = self.request('/stocks')['body']
        self.assertIn(b'/static/stocks.js', html)
        self.assertNotIn(b'/static/app.js', html)
        health = json.loads(self.request('/api/health')['body'])
        self.assertEqual(health['stock_research_version'], EDITION)
        self.assertEqual(health['default_mode'], 'paper')

    def test_authentication_covers_catalog_details_and_both_exports(self):
        for path in ('/api/stocks/research', '/api/stocks/research/VRTX', '/api/stocks/research/export', '/api/stocks/research/report'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, auth='')['status'], 401)
                self.assertEqual(self.request(path, auth='Bearer wrong')['status'], 401)
                self.assertEqual(self.request(path)['status'], 200)
        detail = json.loads(self.request('/api/stocks/research/beam')['body'])
        self.assertEqual(detail['stock']['ticker'], 'BEAM')
        self.assertEqual(detail['stock']['exposure'], 'speculative')
        export = self.request('/api/stocks/research/export')
        self.assertEqual(len(json.loads(export['body'])['stocks']), 20)
        self.assertIn('attachment', export['headers']['Content-Disposition'])
        report = self.request('/api/stocks/research/report')
        self.assertGreater(len(report['body']), 40000)
        self.assertIn(b'VRTX', report['body'])
        self.assertIn('attachment', report['headers']['Content-Disposition'])

    def test_research_requests_leave_account_settings_and_trades_unchanged(self):
        before_settings = copy.deepcopy(self.service.agent.settings)
        before_portfolio = copy.deepcopy(self.service.agent.portfolio)
        before_positions = copy.deepcopy(self.service.agent.open_positions)
        before_running = self.service.agent.runtime['running']
        for path in ('/stocks', '/api/stocks/research', '/api/stocks/research/export', '/api/stocks/research/report'):
            self.assertEqual(self.request(path)['status'], 200)
        self.assertEqual(self.service.agent.settings, before_settings)
        self.assertEqual(self.service.agent.portfolio, before_portfolio)
        self.assertEqual(self.service.agent.open_positions, before_positions)
        self.assertEqual(self.service.agent.runtime['running'], before_running)
        self.assertEqual(self.request('/api/stocks/order', method='POST')['status'], 404)
        self.assertEqual(self.request('/api/stocks/research', method='POST')['status'], 404)

    def test_unknown_tickers_and_file_paths_are_not_served(self):
        for path in ('/api/stocks/research/UNKNOWN', '/api/stocks/research/../../app.py', '/static/../app.py', '/research/stock_watchlist.json'):
            self.assertEqual(self.request(path)['status'], 404, path)
