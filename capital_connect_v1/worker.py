"""Retired simulation service. Preserves its historical disk without trading."""
import argparse
import logging
import os
import signal
import threading

log=logging.getLogger('capital_connect')

def run(path, once=False):
    stop=threading.Event()
    signal.signal(signal.SIGTERM,lambda *_:stop.set())
    signal.signal(signal.SIGINT,lambda *_:stop.set())
    log.info('Simulation service RETIRED: no market reads, scans, reports or ledger writes; historical data preserved')
    if not once:stop.wait()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--db',default=os.getenv('CAPITAL_CONNECT_DB','capital-connect-demo.sqlite3'))
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    run(args.db,args.once)
