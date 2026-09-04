#!/usr/bin/env python3
"""提取最优参数并更新V11系统"""
import json
from pathlib import Path

v3_path = Path('/root/.hermes/smc_opt_v11/backtest_v11_v3.json')
data = json.loads(v3_path.read_text())

stocks = data['stocks']
summary = data['summary']

# 生成每股票最优参数配置
per_stock_params = {}
for s in stocks:
    per_stock_params[s['symbol']] = {
        'sl_pct': s['sl_pct'],
        'tp_pct': s['tp_pct'],
    }

print(f"Total tradable stocks: {len(stocks)}/{data['config']['max_stocks']}")
print(f"Total trades: {summary['total_trades']}")
print(f"WR: {summary['win_rate']}%  RR: {summary['avg_rr']}x  PF: {summary['profit_factor']}")
print(f"Avg P&L: {data['summary'].get('avg_pnl', 0)}%")

# 按胜率分组
wr_groups = {'90-100': 0, '80-89': 0, '70-79': 0, '60-69': 0, '50-59': 0, '<50': 0}
for s in stocks:
    wr = s['win_rate']
    if wr >= 90: wr_groups['90-100'] += 1
    elif wr >= 80: wr_groups['80-89'] += 1
    elif wr >= 70: wr_groups['70-79'] += 1
    elif wr >= 60: wr_groups['60-69'] += 1
    elif wr >= 50: wr_groups['50-59'] += 1
    else: wr_groups['<50'] += 1

print(f"\nWR distribution:")
for k, v in wr_groups.items():
    print(f"  {k}: {v} stocks")

# 高胜率股票清单
high_wr = [s for s in stocks if s['win_rate'] >= 70]
print(f"\nHigh WR stocks (>=70%): {len(high_wr)}")
for s in sorted(high_wr, key=lambda x: x['score'], reverse=True)[:20]:
    print(f"  {s['symbol']:12s} WR={s['win_rate']:.0f}% RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} SL={s['sl_pct']:.1f}% TP={s['tp_pct']:.1f}% trades={s['n_trades']}")

# 保存最优参数
param_path = Path('/root/.hermes/smc_opt_v11/optimal_params.json')
param_path.write_text(json.dumps(per_stock_params, ensure_ascii=False, indent=2))
print(f"\nOptimal params saved: {param_path}")
