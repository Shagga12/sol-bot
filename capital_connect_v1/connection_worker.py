"""Hosted connection-check worker. This entry point never enables orders."""
import json
import os
from pathlib import Path
import signal
import threading
from capital_connect_v1.live import Config, main as check


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
        stop.wait()
        return
    # Run once only. A failure must be reviewed, not hidden by automatic retries.
    result = check(['check', '--config', path, '--db', str(Path(directory)/'connection-journal.sqlite3')])
    print(json.dumps({'state': 'CHECK_PASSED' if result == 0 else 'CHECK_FAILED',
                      'orders_enabled': False, 'dashboard_control_connected': False}), flush=True)
    stop.wait()


if __name__ == '__main__':
    run()
