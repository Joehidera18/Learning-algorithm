"""Ephemeral, loopback-only service for browser checks; no real account files."""
import tempfile
import os
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from lab.service import Service, wsgi_application


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        service = Service(Path(__file__).resolve().parents[1], Path(directory) / 'browser.sqlite3',
                          Path(directory) / 'data', token='stock-ui-test-token')
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
        if os.getenv('EQUITY_UI_FIXTURES') == '1':
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
            service.experiments.shutdown()
            service.equities.shutdown()
            service.forward.shutdown()
            service.events.stop(persist=False)
            service.agent.stop()
