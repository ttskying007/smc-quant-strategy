#!/usr/bin/env python3
"""SMC Setup回测: 流动性→结构→POI 完整流程"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, detect_smc_setups
from v11.v19_backtest_engine import find_tps, find_sls, TradeV19

KLINE_DIR = Path('/root/.hermes/kline_cache')
files = sorted(KLINE_DIR.glob('*_daily_300.json'))

# Accumulators
bl_stats = {'stocks':0,'trades':0,'wins':0,'total_pnl':0.0,'total_hold':0,'exit_methods':defaultdict(int)}
smc_stats = {'stocks':0,'trades':0,'wins':0,'total_pnl':0.0,'total_hold':0,'exit_methods':defaultdict(int),
             'setups':0,'long_setups':0,'short_setups':0}

t0 = time.time()
for fi, fp in enumerate(files):
    sym = fp.stem.replace('_daily_300', '')
    try:
        ohlcv = json.loads(fp.read_bytes())
        n = len(ohlcv)
        if n < 50: continue
    except: continue
    
    sigs, _, _, swings_dict = detect_all_signals_v20(ohlcv)
    
    # ── Baseline (FVG_Bull + OB_Bull) ──
    from v11.v19_backtest_engine import backtest_v19
    trades_bl = backtest_v19(sym, ohlcv, sigs, swings_dict)
    if isinstance(trades_bl, tuple): trades_bl = trades_bl[0]
    
    if trades_bl:
        bl_stats['stocks'] += 1
        for t in trades_bl:
            bl_stats['trades'] += 1
            bl_stats['total_pnl'] += t.pnl_pct
            bl_stats['total_hold'] += t.hold_bars
            bl_stats['exit_methods'][t.exit_method] += 1
            if t.pnl_pct > 0: bl_stats['wins'] += 1
    
    # ── SMC Setups ──
    setups = detect_smc_setups(sigs, ohlcv)
    if not setups:
        continue
    
    smc_stats['setups'] += len(setups)
    smc_stats['long_setups'] += sum(1 for s in setups if s['direction']=='long')
    smc_stats['short_setups'] += sum(1 for s in setups if s['direction']=='short')
    
    # Trade each setup
    used_bars = set()
    for su in setups:
        entry_bar = su['entry_bar']
        # Confirm on next bar
        confirmed_at = entry_bar + 1 if entry_bar + 1 < n else entry_bar
        if confirmed_at >= n - 2: continue
        if confirmed_at in used_bars: continue
        
        direction = su['direction']
        entry_price = ohlcv[confirmed_at]['o']  # Use actual open price
        
        # TP/SL from structural levels
        if direction == 'long':
            tp_price, tp_src, tp_bar = find_tps(entry_price, sigs, swings_dict, ohlcv)
            sl_price, sl_src, sl_bar = find_sls(entry_price, sigs, swings_dict, ohlcv)
        else:
            # Short: flip TP/SL
            sl_price, sl_src, sl_bar = find_tps(entry_price, sigs, swings_dict, ohlcv)
            tp_price, tp_src, tp_bar = find_sls(entry_price, sigs, swings_dict, ohlcv)
        
        # Cap TP at 5%
        max_tp = entry_price * (1.05 if direction == 'long' else 0.95)
        if (direction == 'long' and tp_price > max_tp) or (direction == 'short' and tp_price < max_tp):
            tp_price = max_tp
        
        # RR check
        tp_dist = abs(tp_price - entry_price) / entry_price * 100
        sl_dist = abs(sl_price - entry_price) / entry_price * 100
        if sl_dist > 0 and tp_dist / sl_dist < 1.0:
            continue
        
        # Walk forward (T+1: exclude same bar)
        exit_idx = -1; exit_price = 0; exit_method = 'eod'
        
        for i in range(confirmed_at + 1, n):
            bar = ohlcv[i]
            if direction == 'long':
                if bar['h'] >= tp_price:
                    exit_idx = i; exit_price = tp_price; exit_method = 'tp_hit'; break
                if bar['l'] <= sl_price:
                    exit_idx = i; exit_price = sl_price; exit_method = 'sl_hit'; break
            else:
                if bar['l'] <= tp_price:
                    exit_idx = i; exit_price = tp_price; exit_method = 'tp_hit'; break
                if bar['h'] >= sl_price:
                    exit_idx = i; exit_price = sl_price; exit_method = 'sl_hit'; break
        
        if exit_idx < 0:
            exit_idx = n - 1
            exit_price = ohlcv[exit_idx]['c']
            exit_method = 'eod'
        
        if exit_idx <= confirmed_at:
            continue  # T+1 violation
        
        pnl = (exit_price - entry_price) / entry_price * 100
        if direction == 'short':
            pnl = -pnl
        
        smc_stats['trades'] += 1
        smc_stats['total_pnl'] += pnl
        smc_stats['total_hold'] += (exit_idx - confirmed_at)
        smc_stats['exit_methods'][exit_method] += 1
        if pnl > 0: smc_stats['wins'] += 1
        used_bars.add(exit_idx)
        smc_stats['stocks'] += 1
    
    if (fi+1) % 1000 == 0:
        elapsed = time.time() - t0
        print(f"  [{fi+1}/4800] {elapsed:.0f}s bl={bl_stats['trades']} smc={smc_stats['trades']}")

elapsed = time.time() - t0

# Stats
def calc(stat, name):
    if not stat['trades']: return
    wr = stat['wins']/stat['trades']*100
    avg_pnl = stat['total_pnl']/stat['trades']
    avg_hold = stat['total_hold']/stat['trades']
    tp = stat['exit_methods'].get('tp_hit', 0)
    sl = stat['exit_methods'].get('sl_hit', 0)
    eod = stat['exit_methods'].get('eod', 0)
    print(f"  {name:15s}: stock={stat['stocks']:>5d} trades={stat['trades']:>5d} WR={wr:5.1f}% PnL={avg_pnl:+6.2f}% Hold={avg_hold:4.1f}b TP={tp}/{stat['trades']}({tp/stat['trades']*100:.0f}%) SL={sl}/{stat['trades']}({sl/stat['trades']*100:.0f}%)")

print(f"\n{'='*65}")
print(f"  SMC Setup回测 ({elapsed:.0f}s)")
print(f"{'='*65}")
print(f"  SMC Setups: {smc_stats['setups']} total ({smc_stats['long_setups']} long + {smc_stats['short_setups']} short)")
calc(bl_stats, 'Baseline')
calc(smc_stats, 'SMC_Setup')
