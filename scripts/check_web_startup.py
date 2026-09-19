"""Smoke-test the real Gunicorn entry point with an isolated temporary database.

Requires the project's requirements.txt. No monitoring, practice, exchange
runner or deployment is started. Requests stay on loopback.
"""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    checks = []
    with tempfile.TemporaryDirectory(prefix='predeploy-web-') as folder:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        token = secrets.token_urlsafe(24)
        env = dict(os.environ, APP_ACCESS_TOKEN=token, COINBASE_ALLOW_LIVE='0',
            RESEARCH_DB_PATH=folder+'/state.sqlite3', RESEARCH_DATA_DIR=folder+'/data')
        base = f'http://127.0.0.1:{port}'
        def request(path, body=None, auth=True):
            headers = {'Authorization':'Bearer '+token} if auth else {}
            if body is not None:
                headers['Content-Type'] = 'application/json'
            req = urllib.request.Request(base+path, headers=headers,
                data=json.dumps(body).encode() if body is not None else None)
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.status, response.read()
            except urllib.error.HTTPError as error:
                return error.code, error.read()
        for restart in (False, True):
            with open(folder+'/gunicorn.log', 'a') as log:
                proc = subprocess.Popen([sys.executable, '-m', 'gunicorn', 'app:app', '--bind',
                    f'127.0.0.1:{port}', '--workers','1','--threads','8','--timeout','300'],
                    env=env, cwd=root, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic()+30
                    while True:
                        try:
                            if request('/api/health', auth=False)[0] == 200:
                                break
                        except (OSError, urllib.error.URLError):
                            pass
                        if proc.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError('Local Gunicorn did not become healthy. Check dependencies and app startup.')
                        time.sleep(.1)
                    settings = json.loads(request('/api/continuous/settings')[1])
                    if restart:
                        assert settings['fee_rate'] == .003
                        status = json.loads(request('/api/learning/status')[1])
                        assert not status['enabled'] and not status['paper_running']
                        checks.append('settings survive restart; runners remain stopped')
                    else:
                        for path in ('/','/static/app.js','/static/coinbase.js','/static/style.css'):
                            code, body = request(path, auth=False)
                            assert code == 200 and body
                        checks.append('dashboard, assets and public health served by real Gunicorn')
                        assert request('/api/learning/status', auth=False)[0] == 401
                        assert request('/api/learning/status')[0] == 200
                        checks.append('private API requires access token')
                        assert request('/api/learning/practice', {'intervals':[]})[0] == 400
                        assert request('/api/continuous/settings', {'decision_interval':'6h'})[0] == 400
                        assert json.loads(request('/api/continuous/settings')[1])['decision_interval'] == '15m'
                        checks.append('invalid study plans and 6h trading interval rejected')
                        assert request('/api/continuous/settings', {'fee_rate':.003})[0] == 200
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
    record = {'passed':checks,
        'scope':'Fresh temporary database; local HTTP and Gunicorn only. No runners, external market calls, deployment or orders.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
