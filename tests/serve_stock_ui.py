"""Ephemeral, loopback-only service for browser checks; no real account files."""
import tempfile
import os
import json
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from lab.service import Service
from lab.stock_service import StockService
from lab.http import wsgi_application


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        legacy = os.getenv('EXPERIMENT_UI_FIXTURES') == '1'
        factory = Service if legacy else StockService
        service = factory(Path(__file__).resolve().parents[1], Path(directory) / 'browser.sqlite3',
                          Path(directory) / 'data', token='stock-ui-test-token',
                          **({} if legacy else {'resume':False}))
        if legacy:
            from lab.website_lab import attach
            attach(service)
        if os.getenv('STRATEGY_LAB_UI_FIXTURES') == '1':
            service.strategy_lab.resume = lambda: None
            first = service.strategy_lab.start({})
            service.strategy_lab._patch(first['id'], status='complete', message='Generated incomplete test fixture',
                result={'report_version':3, 'eligible_for_bot':False,
                        'later':{'complete':False, 'trades':24, 'net_pnl':None, 'mean_r':None,
                                 'incomplete_reason':'Candles went missing while a position was open.'},
                        'later_higher_cost':{'complete':False}})
            second = service.strategy_lab.start({})
            service.strategy_lab._patch(second['id'], status='complete', message='Legacy test fixture',
                result={'eligible_for_bot':True, 'later':{'complete':True, 'trades':25, 'net_pnl':99, 'mean_r':1}})
            from unittest.mock import patch
            from tests.test_equity_practice import stock_rows, snapshot
            from tests.test_strategy_lab import FixtureStrategy
            third = service.strategy_lab.start({'strategy':'trend_pullback_simple','decision':'1h','days':365})
            job = service.strategy_lab.get(third['id'])
            with patch('lab.equity_data.EquityData.history',return_value=snapshot(stock_rows())), \
                 patch('strategies.load_strategy',return_value=FixtureStrategy()):
                service.strategy_lab._run({'id':job['id'],'request_json':json.dumps(job['request'])})
            assert service.strategy_lab.get(third['id'])['status'] == 'complete'
        if os.getenv('EXPERIMENT_UI_FIXTURES') == '1':
            from unittest.mock import patch
            from tests.test_execution import candles
            from lab.experiment_jobs import ExperimentHistory
            service.experiments.resume = lambda: None
            queued = service.experiments.start({'symbol':'BTC-USD','interval':'15m','days':40,
                                               'recipes':['breakout_retest']},service.agent.settings)
            job = service.experiments.get(queued['ids'][0])
            rows = candles(3100,start=job['manifest']['cutoff_ts']-3100*900000)
            with patch.object(ExperimentHistory,'_history',return_value=rows):
                service.experiments._run_job(job)
        if os.getenv('EQUITY_UI_FIXTURES') == '1' or os.getenv('STOCK_DASHBOARD_UI_FIXTURES') == '1':
            from unittest.mock import Mock
            from tests.test_equity_practice import stock_rows, snapshot
            service.equities.resume = lambda: None
            service.equities.client.history = Mock(return_value=snapshot(stock_rows(moving=True)))
            queued = service.equities.start({'symbol':'SPY','interval':'1h','days':365})
            service.equities._run_job(service.equities.get(queued['ids'][0]))
        try:
            with make_server('127.0.0.1', 0, wsgi_application(service), server_class=ThreadedServer,
                             handler_class=QuietHandler) as server:
                print(f'http://127.0.0.1:{server.server_port}', flush=True)
                server.serve_forever()
        finally:
            if legacy:
                service.strategy_lab.shutdown()
                service.experiments.shutdown()
                service.equities.shutdown()
                service.forward.shutdown()
                service.events.stop(persist=False)
                service.agent.stop()
            else:
                service.shutdown()
