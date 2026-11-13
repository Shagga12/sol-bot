"""Browser-independent DEMO worker. Public market reads only; no API keys used."""
import argparse
import fcntl
import json
import logging
import os
import signal
import threading
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler
from capital_connect_v1.engine import get_public_price, SYMBOLS
from capital_connect_v1.paper import PaperLedger, INTERVAL

log = logging.getLogger('capital_connect')

def publish_status(ledger):
    url = os.getenv('CAPITAL_REPORT_URL')
    token = os.getenv('CAPITAL_REPORT_TOKEN')
    if not url or not token:
        return
    if url != 'https://capital-connect-preflight.onrender.com/api/report':
        log.error('Dashboard report destination rejected')
        return
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        request = Request(url, data=json.dumps(ledger.status()).encode(), method='POST',
                          headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
        with build_opener(NoRedirect).open(request, timeout=15) as response:
            if response.status != 200:
                raise RuntimeError()
        log.info('Dashboard demo report delivered')
    except Exception as error:
        log.error('Dashboard report unavailable (%s); demo ledger preserved', type(error).__name__)


def run(path, once=False):
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    # Protects workers sharing this database on one machine/filesystem.
    # Cross-host workers must use a shared transactional database before deployment.
    with open(path + '.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another demo worker already owns this database')
        ledger = PaperLedger(path)
        try:
            while not stop.is_set():
                try:
                    prices = {s: get_public_price(s) for s in SYMBOLS}
                    result = ledger.scan(prices, time.time())
                    log.info('%s', json.dumps({'mode': 'DEMO', 'decisions': result}))
                    publish_status(ledger)
                except Exception as error:
                    # No invented price, no ledger mutation after failed fetch.
                    log.error('Scan failed; no demo trades submitted (%s)', type(error).__name__)
                if once:
                    return
                stop.wait(INTERVAL - (time.time() % INTERVAL))
        finally:
            ledger.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--db', default=os.getenv('CAPITAL_CONNECT_DB', 'capital-connect-demo.sqlite3'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    run(args.db, args.once)
