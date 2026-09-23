"""Stock UI performance boundaries and complete historical report delivery."""
import gzip
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lab.http import wsgi_application
from lab.paper_store import db_connect
from lab.stock_service import StockService
from lab.strategy_lab import REPORT_VERSION, run_backtest
from tests.test_equity_practice import stock_rows, snapshot
from tests.test_strategy_lab import FixtureStrategy

BASE = Path(__file__).resolve().parents[1]


class StockPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = StockService(BASE, Path(self.temp.name)/'legacy.db', Path(self.temp.name)/'data',
                                    token='fixture-token', resume=False)
        self.service.equities.resume = Mock()
        self.service.strategy_lab.resume = Mock()
        self.app = wsgi_application(self.service)

    def tearDown(self):
        self.service.shutdown()
        self.temp.cleanup()

    def request(self, url, authorized=True, **extra):
        path, _, query = url.partition('?')
        env = {'PATH_INFO':path, 'QUERY_STRING':query, 'REQUEST_METHOD':'GET',
               'CONTENT_LENGTH':'0', 'wsgi.input':io.BytesIO()}
        if authorized:
            env['HTTP_AUTHORIZATION'] = 'Bearer fixture-token'
        env.update(extra)
        response = []
        body = b''.join(self.app(env, lambda status, headers:response.append((int(status.split()[0]), dict(headers)))))
        return response[0][0], body, response[0][1]

    def test_dashboard_and_list_never_parse_saved_learning_results(self):
        jobs = self.service.equities
        identity = jobs.start({'symbol':'SPY','interval':'1h','days':365})['ids'][0]
        con = db_connect(jobs.db_path)
        try:
            with con:
                # A corrupt report must not prevent opening the dashboard/list.
                con.execute("UPDATE experiment_jobs SET status='complete',summary_json='broken report' WHERE id=?", (identity,))
            for path in ('/api/stocks/overview','/api/stocks/practice/status'):
                status, body, _ = self.request(path)
                self.assertEqual(status, 200)
                value = json.loads(body)
                self.assertEqual(value['jobs'][0]['id'], identity)
                self.assertNotIn('broken report', body.decode())
                self.assertLess(len(body), 20000)
        finally:
            con.close()
        with self.assertRaises(ValueError):
            jobs.get(identity)  # The report is only decoded when explicitly opened.

    def test_lazy_result_preserves_summary_and_full_model_export(self):
        jobs = self.service.equities
        identity = jobs.start({'symbol':'SPY','interval':'1h','days':365})['ids'][0]
        con = db_connect(jobs.db_path)
        report = {'model':{'fixture':True},'net_pnl':1.5,'variants':[]}
        try:
            with con:
                con.execute("UPDATE experiment_jobs SET status='complete',summary_json=?,result_json=? WHERE id=?",
                            (json.dumps(report),json.dumps(report),identity))
        finally:
            con.close()
        data = json.loads(self.request('/api/stocks/practice/status')[1])
        self.assertIsNone(data['jobs'][0]['result'])
        self.assertTrue(data['jobs'][0]['result_available'])
        path = '/api/stocks/practice/result?id='+identity
        self.assertEqual(self.request(path, authorized=False)[0],401)
        result = json.loads(self.request(path)[1])['result']
        self.assertEqual(result['net_pnl'],1.5)
        self.assertNotIn('model',result)
        full = json.loads(self.request('/api/stocks/practice/export?id='+identity)[1])
        self.assertEqual(full['result']['model'],{'fixture':True})

    def test_forward_ui_omits_trades_without_mutating_journal(self):
        jobs = self.service.equities
        saved = {'symbol':'SPY','account':{'metrics':{'net_pnl':3},'trades':[{'pnl':3}]*200}}
        jobs._save_forward('fixture','stopped',saved,insert=True)
        self.assertNotIn('trades',jobs.forward_list()[0]['account'])
        self.assertEqual(jobs.forward_list(full=True)[0]['account']['trades'],saved['account']['trades'])

    def test_lab_status_does_not_fetch_each_completed_report(self):
        jobs = self.service.strategy_lab
        identity = jobs.start({})['id']
        jobs._patch(identity,status='complete',message='fixture',result={'report_version':REPORT_VERSION,'later':{'trades':0}})
        with patch.object(jobs,'get',side_effect=AssertionError('N+1 report read')):
            status, body, _ = self.request('/api/strategy-lab/status')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['jobs'][0]['result']['later']['trades'],0)
        self.assertIsNone(jobs.status(include_results=False)['jobs'][0]['result'])

    def test_versioned_assets_cache_and_revalidate_while_private_data_does_not(self):
        _, page, page_headers = self.request('/backtests',authorized=False)
        self.assertEqual(page_headers['Cache-Control'],'no-store')
        url = re.search(rb'/static/strategy-lab.js\?v=[0-9a-f]+',page)[0].decode()
        status, content, headers = self.request(url,authorized=False)
        self.assertEqual(status,200)
        self.assertIn('immutable',headers['Cache-Control'])
        self.assertEqual(content,(BASE/'static/strategy-lab.js').read_bytes())
        status, content, second = self.request(url,authorized=False,HTTP_IF_NONE_MATCH=headers['ETag'])
        self.assertEqual(status,304)
        self.assertEqual(content,b'')
        self.assertEqual(second['ETag'],headers['ETag'])
        self.assertIn('must-revalidate',self.request('/static/strategy-lab.js?v=old')[2]['Cache-Control'])
        self.assertEqual(self.request('/api/stocks/overview')[2]['Cache-Control'],'no-store')
        self.assertEqual(self.request('/api/stocks/overview',authorized=False)[0],401)

    def test_gzip_roundtrip_handles_quality_zero_and_auth_errors(self):
        path = '/static/strategy-lab.js'
        plain = self.request(path)[1]
        status, compressed, headers = self.request(path,HTTP_ACCEPT_ENCODING='br, gzip;q=0.8')
        self.assertEqual(status,200)
        self.assertEqual(gzip.decompress(compressed),plain)
        self.assertLess(len(compressed),len(plain)//2)
        self.assertEqual(int(headers['Content-Length']),len(compressed))
        self.assertEqual(headers['Vary'],'Accept-Encoding')
        self.assertNotIn('Content-Encoding',self.request(path,HTTP_ACCEPT_ENCODING='gzip;q=0')[2])
        self.assertEqual(self.request('/api/stocks/overview',authorized=False,HTTP_ACCEPT_ENCODING='gzip')[0],401)

    def test_bad_backtest_options_fail_before_queueing(self):
        cases = [{'starting_balance':True},{'starting_balance':float('nan')},{'starting_balance':99},
                 {'starting_balance':1000001},{'fractional_shares':'yes'},{'mode':'swing'},
                 {'settings':{'risk_per_trade':.5}},{'end_date':'9999-12-31'},
                 {'end_date':'2026-02-31'},{'symbol':'BTC-USD'},
                 {'strategy':'trend_pullback_simple','news':True}]
        with patch.dict('os.environ',{'MASSIVE_API_KEY':''}):
            cases.append({'news':True})
            for request in cases:
                with self.subTest(request=request), self.assertRaises(ValueError):
                    self.service.strategy_lab.start(request)
        self.assertFalse(self.service.strategy_lab.status()['jobs'])

    def test_saved_full_report_uses_frozen_cutoff_and_exposes_trade_journal(self):
        jobs = self.service.strategy_lab
        identity = jobs.start({'strategy':'trend_pullback_simple','decision':'1h','context':'4h',
            'days':365,'starting_balance':1500,'fractional_shares':False,'mode':'swing','end_date':'2026-09-20'})['id']
        job = jobs.get(identity)
        rows = stock_rows(moving=True)
        source = snapshot(rows)
        with patch('lab.equity_data.EquityData.history',return_value=source) as history:
            # Context has different bars; use the correct session aggregation fixture.
            history.side_effect=[source, snapshot(stock_rows('4h',moving=True))]
            jobs._run({'id':identity,'request_json':json.dumps(job['request'])})
        self.assertEqual(jobs.get(identity)['status'],'complete',jobs.get(identity)['message'])
        self.assertEqual(len(history.call_args_list),2)
        for call in history.call_args_list:
            self.assertEqual(call.kwargs['cutoff'],job['request']['cutoff_ts'])
        report = jobs.report(identity)
        self.assertEqual(report['starting_balance'],1500)
        self.assertFalse(report['fractional_shares'])
        self.assertEqual(report['holding_mode'],'swing')
        self.assertEqual(report['requested_coverage'],source['quality'])
        self.assertEqual(set(report['trade_journal']),{'development','later','later_higher_cost'})
        for path in ('report','report/export'):
            url = '/api/strategy-lab/'+path+'?id='+identity
            self.assertEqual(self.request(url,authorized=False)[0],401)
            status, body, _ = self.request(url)
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body),report)
        self.assertLess(report['development']['end_ts'],report['later']['end_ts'])
        self.assertLessEqual(report['development']['end_ts'],report['later']['start_ts'])

    def test_journal_pnl_reconciles_and_missing_required_context_blocks_entries(self):
        rows = stock_rows()
        strategy = FixtureStrategy()
        report = run_backtest(strategy,rows,'1h',{'fee_rate':.0001,'slippage_rate':.0001},
                              stock_execution=True,close_at_session_end=True,starting_balance=1500)
        for window,trades in report['trade_journal'].items():
            metrics = report[window]
            self.assertAlmostEqual(sum(t['pnl'] for t in trades),metrics['net_pnl'])
            self.assertAlmostEqual(metrics['ending_balance'],1500+metrics['net_pnl'])
            self.assertEqual(metrics['trades'],sum(t['reason']!='END' for t in trades))
        self.assertTrue(report['trade_journal']['later'])
        strategy.require_context=('4h',)
        blocked=run_backtest(strategy,rows,'1h',{'fee_rate':.0001,'slippage_rate':.0001},
                              frames={'4h':[]},stock_execution=True,close_at_session_end=True)
        self.assertEqual(blocked['later']['trades'],0)
        self.assertFalse(blocked['eligible_for_bot'])
        self.assertGreater(blocked['later']['signal_funnel']['rejections']['higher_timeframe_not_ready:4h'],0)


if __name__ == '__main__':
    unittest.main()
