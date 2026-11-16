"""Hosted connection-check worker. This entry point never enables orders."""
import json
import os
from pathlib import Path
from urllib.request import Request, build_opener
from capital_connect_v1.live import NoRedirect
import signal
import threading
from capital_connect_v1.live import Config, main as check
from capital_connect_v1.supervised_worker import supervise
from capital_connect_v1.testnet_check import run_testnet_check


def prepare_config(raw, directory):
    data = json.loads(raw)
    Config(**data)  # Validate before writing. Credentials do not belong here.
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / 'connection-config.json'
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump(data, handle)
    return str(path)


def heartbeat(stop, state):
    token = os.getenv('CAPITAL_LIVE_REPORT_TOKEN')
    while True:
        if token:
            try:
                request = Request('https://capital-connect-preflight.onrender.com/api/live/report',
                    data=json.dumps({'state':state,'orders_enabled':False}).encode(),
                    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}, method='POST')
                with build_opener(NoRedirect).open(request, timeout=90) as response:
                    if response.status != 200: raise OSError()
                print('Connection worker heartbeat delivered', flush=True)
            except Exception:
                print('Connection worker heartbeat unavailable', flush=True)
        if stop.wait(60): return


def run():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    directory = os.getenv('CAPITAL_CONNECTION_DATA', '/var/data')
    try:
        raw = os.getenv('CAPITAL_LIVE_CONFIG_JSON')
        if not raw or not os.getenv('BYBIT_API_KEY') or not os.getenv('BYBIT_API_SECRET'):
            raise ValueError('missing setup')
        path = prepare_config(raw, directory)
    except (ValueError, TypeError, OSError):
        print(json.dumps({'state': 'SETUP_REQUIRED', 'orders_enabled': False,
                          'required': ['saved trading configuration', 'Bybit API credentials in Render']}), flush=True)
        heartbeat(stop, 'SETUP_REQUIRED')
        return
    # Run once only. A failure must be reviewed, not hidden by automatic retries.
    result = check(['check', '--config', path, '--db', str(Path(directory)/'connection-journal.sqlite3')])
    print(json.dumps({'state': 'CHECK_PASSED' if result == 0 else 'CHECK_FAILED',
                      'orders_enabled': False, 'dashboard_control_connected': False}), flush=True)
    run_testnet_check(directory)
    if result == 0:
        supervise(stop, path, directory)
    else:
        heartbeat(stop, 'CHECK_FAILED')


if __name__ == '__main__':
    run()
