"""Isolated read-only Testnet diagnostic; never modifies mainnet credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
from .live import Config


def run_testnet_check(directory, runner=subprocess.run):
    key = os.getenv('BYBIT_TESTNET_API_KEY')
    secret = os.getenv('BYBIT_TESTNET_API_SECRET')
    if not key or not secret:
        print('Testnet check: separate credentials not configured', flush=True)
        return None
    try:
        raw = json.loads(os.environ['CAPITAL_LIVE_CONFIG_JSON'])
        raw['environment'] = 'testnet'
        Config(**raw)
        root = Path(directory) / 'testnet-validation'
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = root / 'config.json'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(raw, handle)
        env = os.environ.copy()
        env['BYBIT_API_KEY'] = key
        env['BYBIT_API_SECRET'] = secret
        env.pop('CAPITAL_EXECUTION_VALIDATED_CONFIG_SHA256', None)
        args = [sys.executable, '-m', 'capital_connect_v1.live', 'check',
                '--config', str(path), '--db', str(root / 'journal.sqlite3')]
        print('Testnet check: starting isolated read-only check; no orders enabled', flush=True)
        result = runner(args, env=env, timeout=120, check=False)
        print('Testnet check: ' + ('PASSED' if result.returncode == 0 else 'FAILED'), flush=True)
        if result.returncode == 0 and os.getenv('CAPITAL_TESTNET_ORDER_TESTS') == 'run':
            for phase in ('buy','close'):
                args = [sys.executable,'-m','capital_connect_v1.testnet_exchange',
                    '--config',str(path),'--directory',str(root),'--phase',phase,'--testnet-orders']
                trial = runner(args,env=env,timeout=90,check=False)
                if trial.returncode != 0: return trial.returncode
            if os.getenv('CAPITAL_TESTNET_LIFECYCLE_TESTS') == 'run':
                args=[sys.executable,'-m','capital_connect_v1.testnet_lifecycle','--config',str(path),
                      '--directory',str(root),'--testnet-orders']
                trial=runner(args,env=env,timeout=180,check=False)
                if trial.returncode != 0: return trial.returncode
        if result.returncode == 0 and os.getenv('CAPITAL_TESTNET_PROTECTION_TESTS') == 'run':
            for phase in ('create','verify'):
                args=[sys.executable,'-m','capital_connect_v1.testnet_protection','--config',str(path),
                      '--directory',str(root),'--phase',phase,'--testnet-orders']
                trial=runner(args,env=env,timeout=120,check=False)
                if trial.returncode != 0:return trial.returncode
        return result.returncode
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError):
        print('Testnet check: setup or transport failure; credentials not logged', flush=True)
        return 1
