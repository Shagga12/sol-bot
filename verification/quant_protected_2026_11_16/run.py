"""Run offline protected Quant tests with fixed owner settings, no optimization."""
import datetime
import csv
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capital_connect_v1.live import Config
from capital_connect_v1.quant_risk_backtest import Assumptions, simulate

C = Config('mainnet', 'BTCUSDT', '56', '15', '10', '.01', '.04', '.10')
results = {'configuration': C.__dict__, 'actual_exchange_validation': False,
           'live_activation_approved': False, 'years': {}}
for year in (2024, 2025):
    path = Path(f'/tmp/quant-official-btcusd-{year}.json')
    data = json.loads(path.read_text())
    if data['missing']:
        raise ValueError('Incomplete yearly dataset')
    rows = data['rows']
    output = {'candles': len(rows), 'data_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'scenarios': {}, 'quarterly': {}}
    for fee, slip in (('.001', '.001'), ('.001', '.002'), ('.002', '.002')):
        assumptions = Assumptions(fee, slip, '.1', '.000001', '5')
        result = simulate(rows, C, assumptions)
        key = f'fee_{fee}_exit_slippage_{slip}'
        output['scenarios'][key] = {k: v for k, v in result.items() if k != 'trades'}
        # Full fills retained for audit, not only favorable summary metrics.
        Path(f'/tmp/quant-protected-{year}-{fee}-{slip}-trades.json').write_text(json.dumps(result['trades'], indent=2))
        if fee == '.001' and slip == '.001':
            with Path(__file__).with_name(f'trades_{year}_baseline.csv').open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=['entry', 'exit', 'reason', 'cost', 'pnl', 'stop', 'take', 'exit_price'])
                writer.writeheader(); writer.writerows(result['trades'])
    for quarter in range(1, 5):
        part = [r for r in rows if (datetime.datetime.fromtimestamp(int(r['timestamp']),
                  datetime.timezone.utc).month - 1) // 3 + 1 == quarter]
        result = simulate(part, C, Assumptions('.001', '.001', '.1', '.000001', '5'))
        output['quarterly'][str(quarter)] = {k: v for k, v in result.items() if k != 'trades'}
    results['years'][str(year)] = output
results['historical_profitability_check_passed'] = all(
    case['net_return_pct'] > 0
    for year in results['years'].values() for case in year['scenarios'].values())
results['readiness'] = ('NEEDS_EXCHANGE_AND_INTEGRATION_VALIDATION'
    if results['historical_profitability_check_passed'] else 'STRATEGY_REWORK_REQUIRED')
output_path = Path(__file__).with_name('results.json')
output_path.write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
