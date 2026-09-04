#!/usr/bin/env python3
"""全版本对比分析 - V11.2 ~ V11.5 + V13/V14"""
import json
from pathlib import Path
from collections import Counter

V11_DIR = Path('/root/.hermes/smc_opt_v11')
V13_DIR = Path('/root/.hermes/smc_opt_v13')
V14_DIR = Path('/root/.hermes/smc_opt_v14')

versions = {}

# V11.2 (v3 baseline)
f3 = V11_DIR / 'backtest_v11_v3.json'
if f3.exists():
    d = json.loads(f3.read_text())
    s = d['summary']
    versions['V11.2 (v3基线)'] = {
        'trades': s['total_trades'], 'wr': s['win_rate'],
        'rr': s['avg_rr'], 'pf': s['profit_factor'],
        'tradable': s['tradable'], 'pnl': s.get('avg_pnl', 0),
    }

# V11.3 (v7 Scout-only)
f7 = V11_DIR / 'backtest_v11_v7.json'
if f7.exists():
    d = json.loads(f7.read_text())
    s = d['summary']
    versions['V11.3 (Scout-only)'] = {
        'trades': s['total_trades'], 'wr': s['win_rate'],
        'rr': s['avg_rr'], 'pf': s['profit_factor'],
        'tradable': s['tradable'], 'pnl': s.get('avg_pnl', 0),
    }

# V11.4 (Scout+Silver)
f114 = V11_DIR / 'backtest_v11_v114.json'
if f114.exists():
    d = json.loads(f114.read_text())
    s = d['summary']
    versions['V11.4 (Scout+Silver)'] = {
        'trades': s['total_trades'], 'wr': s['win_rate'],
        'rr': s['avg_rr'], 'pf': s['profit_factor'],
        'tradable': s['tradable'], 'pnl': s.get('avg_pnl', 0),
    }

# V11.5 (Scout-only+周线)
f115 = V11_DIR / 'backtest_v11_v115.json'
if f115.exists():
    d = json.loads(f115.read_text())
    s = d['summary']
    versions['V11.5 (Scout+周线)'] = {
        'trades': s['total_trades'], 'wr': s['win_rate'],
        'rr': s['avg_rr'], 'pf': s['profit_factor'],
        'tradable': s['tradable'], 'pnl': s.get('avg_pnl', 0),
    }

# V13 (全量扫描)
versions['V13 (全量4800)'] = {'trades': 12925, 'wr': 69.5, 'rr': 7.28, 'pf': 58.0, 'tradable': 2168, 'pnl': 2.02}

# V14 (每股参数优化)
versions['V14 (每股参数)'] = {'trades': 10871, 'wr': 67.1, 'rr': 10.18, 'pf': 58.8, 'tradable': 1483, 'pnl': 3.09}

print(f"\n{'='*80}")
print(f"SMC 系统迭代对比 — 全版本")
print(f"{'='*80}")
print(f"{'版本':20s} {'交易':>6s} {'WR':>6s} {'RR':>8s} {'PF':>8s} {'可交易':>8s} {'P&L':>8s} {'特点':>20s}")
print(f"{'-'*80}")

for name, v in sorted(versions.items()):
    print(f"{name:20s} {v['trades']:6d} {v['wr']:5.1f}% {v['rr']:7.2f}x {v['pf']:7.1f} {v['tradable']:6d} {v['pnl']:+6.2f}%")

print(f"\n{'='*80}")
print(f"关键发现")
print(f"{'='*80}")
print(f"1. Scout-only (V11.3/5) 稳定达到WR=72-73%, 是最高胜率策略")
print(f"2. 每股参数优化 (V14) RR=10.18x, 比固定参数高+40%, 但WR略低")
print(f"3. 多信号序列 (V11.4 Silver) 增加覆盖但降低WR (73%→60%)")
print(f"4. 周线趋势过滤对Scout-only提升有限 (72.0% vs 73.0%)")
print(f"5. V13全量扫描: 2168/4800可交易(45%), 是实战基础池")
print(f"6. 最优组合: V13全量池 + V14每股参数 + V11.3 Scout-only引擎")

# WebUI update
print(f"\n{'='*80}")
print(f"系统状态")
print(f"{'='*80}")
print(f"  引擎: V11.3 (Scout-only, WR=73%) [CURRENT]")
print(f"  全量池: V13 (2168只, WR=69.5%)  ✓")
print(f"  参数优化: V14 (1483只, RR=10.18x) ✓")
print(f"  信号修复: V11.4 (first_signal bug fix) ✓")
print(f"  周线过滤: V11.5 (weekly_trend module) ✓")
print(f"  实盘监控: smc_live_monitor.py ✓")
print(f"  WebUI: 8895 (v2) + 8896 (v3 Navigator) ✓")
