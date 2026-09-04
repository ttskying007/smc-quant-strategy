#!/usr/bin/env python3
"""
V467改进变种测试 — 单个变种运行器
用法: python3 _run_variant.py <variant_name>
variant_name: adaptive, adaptive_be, adaptive_rr10
"""
import sys, os, json, copy, importlib
from pathlib import Path
from collections import Counter
import numpy as np

variant = sys.argv[1] if len(sys.argv) > 1 else 'adaptive'

# 导入引擎
sys.path.insert(0, '/root/.hermes/scripts')
import v11.v467_engine as engine

# ── 替换calc_v45_sl — 强制adaptive SL ──
def calc_v45_sl_forced_adaptive(ohlcv, entry_idx, entry_price, signal, entry_type, direction, params, all_signals):
    """跳过信号边界SL和摆动点SL, 直接使用adaptive SL"""
    sig_type = signal.get('type', '')
    # FVG仍然保留信号边界SL (FVG更依赖区域价格)
    if direction == 'bull' and 'FVG' in sig_type:
        lower = signal.get('lower', 0)
        if lower > 0 and lower < entry_price:
            pct = (entry_price - lower) / entry_price * 100
            if 0.08 <= pct <= 1.5:
                return lower, 'fvg_lower', round(pct, 2)
    
    # 直接adaptive SL (跳过OB边界和摆动点)
    atr = engine.calc_atr_v45(ohlcv, entry_idx)
    sl_mult = params.get('sl_mult', 0.3)
    base_sl = max(0.15, min(1.5, atr * sl_mult * 0.3))
    if direction == 'bull':
        return round(entry_price * (1 - base_sl/100), 4), 'adaptive', round(base_sl, 2)
    else:
        return round(entry_price * (1 + base_sl/100), 4), 'adaptive', round(base_sl, 2)

# 应用patch
engine.calc_v45_sl = calc_v45_sl_forced_adaptive

# 变种参数
if variant == 'adaptive':
    desc = '强制adaptive SL'
elif variant == 'adaptive_be':
    desc = '强制adaptive SL + 紧BE锁'
    engine.PROGRESSIVE_BE = [(2, 0.0), (3, 0.1), (5, 0.3), (8, 0.5)]
elif variant == 'adaptive_rr10':
    desc = '强制adaptive SL + MIN_PROJECTED_RR=10.0'
    engine.MIN_PROJECTED_RR = 10.0
else:
    print(f"未知变种: {variant}")
    sys.exit(1)

# 加载K线
CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
stock_list = [f.stem.replace('_60min_200', '').replace('_', '.') 
              for f in sorted(CACHE_DIR.glob('*_60min_200.json'))[:200]]

trades_all = []
stock_count = 0

for i, symbol in enumerate(stock_list):
    if (i+1) % 50 == 0:
        print(f"进度: {i+1}/{len(stock_list)} stocks", file=sys.stderr)
    
    ohlcv = engine.load_ohlcv(symbol)
    if ohlcv is None:
        continue
    
    try:
        result = engine.backtest_stock_v45(ohlcv, symbol)
        if result and result['trades']:
            trades_all.extend(result['trades'])
            stock_count += 1
    except Exception as e:
        pass

# 结果
total = len(trades_all)
wins = sum(1 for t in trades_all if t.get('won', False))
wr = wins / total * 100 if total else 0
avg_pnl = sum(t['pnl_pct'] for t in trades_all) / total if total else 0
avg_rr = sum(t['rr'] for t in trades_all) / total if total else 0

rrs = [t['rr'] for t in trades_all if 'rr' in t]
rr_med = np.median(rrs) if rrs else 0

# PF
wp = sum(t['pnl_pct'] for t in trades_all if t.get('won', False))
lp = abs(sum(t['pnl_pct'] for t in trades_all if not t.get('won', False)))
pf = wp / lp if lp > 0 else 999

sl_types = Counter(t.get('sl_type', 'unknown') for t in trades_all)

# RR by sl_type
rr_by_sl = {}
for sl_type in set(t.get('sl_type','') for t in trades_all):
    sub = [t['rr'] for t in trades_all if t.get('sl_type','')==sl_type and 'rr' in t]
    if sub:
        rr_by_sl[sl_type] = {'med': round(np.median(sub),2), 'mean': round(np.mean(sub),2), 'n': len(sub)}

# Hold dist
holds = [t.get('hold_bars',0) for t in trades_all]
hold_1bar = sum(1 for h in holds if h==1)

# 输出
print(json.dumps({
    'variant': variant,
    'desc': desc,
    'stocks': stock_count,
    'total': total,
    'WR': round(wr, 1),
    'RR_mean': round(avg_rr, 2),
    'RR_med': round(rr_med, 2),
    'PF': round(pf, 1),
    'PnL_avg': round(avg_pnl, 2),
    '1bar_pct': round(hold_1bar/total*100, 1) if total else 0,
    'sl_types': dict(sl_types),
    'rr_by_sl': rr_by_sl,
}))
