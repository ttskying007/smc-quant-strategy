#!/usr/bin/env python3
"""
V467改进测试 — 多变种并行测试
在导入时patch引擎的calc_v45_sl和震荡参数
"""
import sys, os, json, copy

# 引擎目录
sys.path.insert(0, '/root/.hermes/scripts')
from v11 import v467_engine as engine

# 替换calc_v45_sl — 强制adaptive SL
_original_sl = engine.calc_v45_sl

def calc_v45_sl_forced_adaptive(ohlcv, entry_idx, entry_price, signal, entry_type, direction, params, all_signals):
    """跳过信号边界SL和摆动点SL, 直接使用adaptive SL"""
    sig_type = signal.get('type', '')
    # 仍然保留FVG的信号边界SL (FVG更依赖区域价格)
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

# 变种配置
VARIANTS = {
    'A_adaptive_only': {
        'desc': '强制adaptive SL',
        'patches': {'calc_v45_sl': calc_v45_sl_forced_adaptive},
        'params': {},
    },
    'B_adaptive_tight_be': {
        'desc': '强制adaptive SL + 紧BE锁(hold>=2无利润→BE)',
        'patches': {'calc_v45_sl': calc_v45_sl_forced_adaptive},
        'params': {'PROGRESSIVE_BE': [(2, 0.0), (3, 0.1), (5, 0.3), (8, 0.5)]},
    },
    'C_adaptive_rr10': {
        'desc': '强制adaptive SL + MIN_PROJECTED_RR=10.0',
        'patches': {'calc_v45_sl': calc_v45_sl_forced_adaptive},
        'params': {'MIN_PROJECTED_RR': 10.0},
    },
}

# 加载K线(并行预加载)
CACHE_DIR = engine.Path('/root/.hermes/kline_cache_60min')
stock_list = [f.stem.replace('_60min_200', '').replace('_', '.') 
              for f in sorted(CACHE_DIR.glob('*_60min_200.json'))[:200]]

results = {}

for var_name, var_config in VARIANTS.items():
    print(f"\n{'='*60}")
    print(f"测试: {var_name} — {var_config['desc']}")
    print(f"{'='*60}")
    
    # 确认原始导入
    import importlib
    importlib.reload(engine)
    
    # 应用patches
    for func_name, new_func in var_config['patches'].items():
        setattr(engine, func_name, new_func)
    
    # 保存原始常量再修改
    originals = {}
    for param_name, param_val in var_config['params'].items():
        originals[param_name] = getattr(engine, param_name, None)
        setattr(engine, param_name, param_val)
    
    # 运行回测
    trades_all = []
    stock_count = 0
    trade_count = 0
    
    for i, symbol in enumerate(stock_list):
        if (i+1) % 50 == 0:
            print(f"  进度: {i+1}/{len(stock_list)}")
        
        ohlcv = engine.load_ohlcv(symbol)
        if ohlcv is None:
            continue
        
        try:
            result = engine.backtest_stock_v45(ohlcv, symbol)
            if result and result['trades']:
                trades_all.extend(result['trades'])
                stock_count += 1
                trade_count += len(result['trades'])
        except Exception as e:
            pass
        
        # 恢复原始常量
        for param_name, orig_val in originals.items():
            if orig_val is not None:
                setattr(engine, param_name, orig_val)
    
    # 结果计算
    wins = sum(1 for t in trades_all if t.get('won', False))
    total = len(trades_all)
    wr = wins / total * 100 if total else 0
    avg_pnl = sum(t['pnl_pct'] for t in trades_all) / total if total else 0
    avg_rr = sum(t['rr'] for t in trades_all) / total if total else 0
    rr_wp = sum(t['rr'] for t in trades_all if t.get('won', False))
    rr_lp = abs(sum(t['rr'] for t in trades_all if not t.get('won', False)))
    pf = rr_wp / rr_lp if rr_lp > 0 else 999
    
    # SL类型分布
    from collections import Counter
    sl_types = Counter(t.get('sl_type', 'unknown') for t in trades_all)
    
    # RR中位数
    import numpy as np
    rrs = [t['rr'] for t in trades_all if 'rr' in t]
    rr_med = np.median(rrs) if rrs else 0
    
    result_summary = {
        'stocks': stock_count,
        'trades': total,
        'WR': round(wr, 1),
        'RR_mean': round(avg_rr, 2),
        'RR_med': round(rr_med, 2),
        'PF': round(pf, 1),
        'PnL_avg': round(avg_pnl, 2),
        'sl_types': dict(sl_types),
    }
    
    print(f"\n结果:")
    print(f"  可交易股票: {stock_count}/{len(stock_list)}")
    print(f"  总交易: {total}")
    print(f"  WR: {wr:.1f}%")
    print(f"  RR: mean={avg_rr:.2f}x, median={rr_med:.2f}x")
    print(f"  PF: {pf:.1f}")
    print(f"  平均PnL: {avg_pnl:+.2f}%")
    print(f"  SL类型分布: {dict(sl_types)}")
    
    results[var_name] = result_summary

# 最终对比
print(f"\n\n{'='*60}")
print("最终对比 (200 stocks, 60min)")
print(f"{'='*60}")
print(f"{'变种':<25} {'股票':>6} {'交易':>6} {'WR%':>6} {'RR_mean':>8} {'RR_med':>8} {'PF':>8} {'PnL%':>8}")
print(f"{'-'*25} {'-'*6} {'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
for var_name, r in results.items():
    print(f"{VARIANTS[var_name]['desc']:<25} {r['stocks']:>6} {r['trades']:>6} {r['WR']:>6} {r['RR_mean']:>8} {r['RR_med']:>8} {r['PF']:>8} {r['PnL_avg']:>8}")

# V467 baseline reference
print(f"\n(参考) V467 baseline: 630/4552 股票, 1472 交易, WR=81.9%, RR_mean=16.49x")
print(f"(200 stocks V11: WR~85%, RR~14x)")
