"""Ephemeral, loopback-only service for browser checks; no real account files."""
import tempfile
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
        try:
            with make_server('127.0.0.1', 0, wsgi_application(service), server_class=ThreadedServer,
                             handler_class=QuietHandler) as server:
                print(f'http://127.0.0.1:{server.server_port}', flush=True)
                server.serve_forever()
        finally:
            service.forward.shutdown()
            service.events.stop(persist=False)
            service.agent.stop()
