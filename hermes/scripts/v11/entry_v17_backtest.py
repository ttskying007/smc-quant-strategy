#!/usr/bin/env python3
"""
V17 Entry-at-Zone 快速回测 — 验证 ENTRY_AT_ZONE vs ENTRY_AT_CLOSE

200只股票对比:
- CLOSE模式: entry_price = ohlcv[entry_bar]['c'], SL=最近结构支撑, TP=最近结构阻力
- ZONE模式: entry_price = zone price (FVG.lower / OB.lower), SL=zone下方结构, TP=zone上方结构
"""

import sys, json, os
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts/v11')
from signals_v17 import detect_all_signals_v17
from structure_zones_v17 import scan_structure_zones

CACHE = Path('/root/.hermes/kline_cache')

def run_entry_test(n_stocks=200):
    """Run entry mode comparison on N stocks"""
    files = sorted(CACHE.glob('*_daily_300.json'))[:n_stocks]
    
    results = {
        'close': {'trades': 0, 'won': 0, 'total_pnl': 0, 'rejected': 0, 'scores': []},
        'zone': {'trades': 0, 'won': 0, 'total_pnl': 0, 'rejected': 0, 'scores': []},
    }
    
    min_quality = 3.0  # minimum entry quality score
    
    for fpath in files:
        try:
            ohlcv = json.loads(fpath.read_bytes())
        except:
            continue
        
        if len(ohlcv) < 50:
            continue
        
        signals = detect_all_signals_v17(ohlcv)
        
        # Test FVG_Bull entries
        for fvg in signals.get('fvg', []):
            if fvg.get('type') != 'FVG_Bull':
                continue
            
            entry_bar = fvg['confirmed_at']
            if entry_bar >= len(ohlcv) - 1:
                continue
            
            entry_close = ohlcv[entry_bar]['c']
            fvg_lower = fvg['lower']
            
            # --- CLOSE MODE ---
            zones_close = scan_structure_zones(ohlcv, signals, entry_bar, entry_close, 'bull')
            qc = zones_close['entry_quality']
            
            if qc['score'] >= min_quality and zones_close['sl_zones']:
                sl_price = zones_close['sl_zones'][0]['price']
                tp_price = zones_close['tp_zones'][0]['price'] if zones_close['tp_zones'] else entry_close * 1.05
                
                pnl = _simulate_exit(ohlcv, entry_bar, entry_close, sl_price, tp_price, 'bull')
                results['close']['trades'] += 1
                results['close']['scores'].append(qc['score'])
                if pnl > 0:
                    results['close']['won'] += 1
                results['close']['total_pnl'] += pnl
            else:
                results['close']['rejected'] += 1
            
            # --- ZONE MODE ---
            entry_zone = fvg_lower
            zones_zone = scan_structure_zones(ohlcv, signals, entry_bar, entry_zone, 'bull')
            qz = zones_zone['entry_quality']
            
            if qz['score'] >= min_quality and zones_zone['sl_zones']:
                sl_price = zones_zone['sl_zones'][0]['price']
                tp_price = zones_zone['tp_zones'][0]['price'] if zones_zone['tp_zones'] else entry_zone * 1.05
                
                pnl = _simulate_exit(ohlcv, entry_bar, entry_zone, sl_price, tp_price, 'bull')
                results['zone']['trades'] += 1
                results['zone']['scores'].append(qz['score'])
                if pnl > 0:
                    results['zone']['won'] += 1
                results['zone']['total_pnl'] += pnl
            else:
                results['zone']['rejected'] += 1
    
    return results


def _simulate_exit(ohlcv, entry_bar, entry_price, sl_price, tp_price, direction):
    """Simulate exit: walk forward from entry_bar+1, check SL/TP hit"""
    for i in range(entry_bar + 1, len(ohlcv)):
        bar = ohlcv[i]
        if direction == 'bull':
            if bar['l'] <= sl_price:
                return (sl_price - entry_price) / entry_price * 100  # SL hit = loss
            if bar['h'] >= tp_price:
                return (tp_price - entry_price) / entry_price * 100  # TP hit = win
    # End of data — exit at last close
    last_close = ohlcv[-1]['c']
    return (last_close - entry_price) / entry_price * 100


if __name__ == '__main__':
    import time
    t0 = time.time()
    results = run_entry_test(200)
    elapsed = time.time() - t0
    
    rc = results['close']
    rz = results['zone']
    
    print("=" * 70)
    print(f"V17 Entry Mode Comparison — 200 stocks ({elapsed:.1f}s)")
    print("=" * 70)
    print(f"{'Metric':<25} {'CLOSE':>15} {'ZONE':>15} {'Delta':>10}")
    print("-" * 70)
    print(f"{'Trades executed':<25} {rc['trades']:>15} {rz['trades']:>15}")
    print(f"{'Rejected (quality<3)':<25} {rc['rejected']:>15} {rz['rejected']:>15}")
    
    if rc['trades'] > 0:
        wr_close = rc['won'] / rc['trades'] * 100
        avg_pnl_close = rc['total_pnl'] / rc['trades']
        avg_score_close = sum(rc['scores']) / len(rc['scores'])
    else:
        wr_close = avg_pnl_close = avg_score_close = 0
    
    if rz['trades'] > 0:
        wr_zone = rz['won'] / rz['trades'] * 100
        avg_pnl_zone = rz['total_pnl'] / rz['trades']
        avg_score_zone = sum(rz['scores']) / len(rz['scores'])
    else:
        wr_zone = avg_pnl_zone = avg_score_zone = 0
    
    print(f"{'Win Rate':<25} {wr_close:>14.1f}% {wr_zone:>14.1f}% {wr_zone-wr_close:>+9.1f}%")
    print(f"{'Avg P&L/trade':<25} {avg_pnl_close:>+14.2f}% {avg_pnl_zone:>+14.2f}% {avg_pnl_zone-avg_pnl_close:>+9.2f}%")
    print(f"{'Total P&L':<25} {rc['total_pnl']:>+14.2f}% {rz['total_pnl']:>+14.2f}% {rz['total_pnl']-rc['total_pnl']:>+9.2f}%")
    print(f"{'Avg Quality Score':<25} {avg_score_close:>14.1f} {avg_score_zone:>14.1f}")
    
    # Distribution of SL distances
    print(f"\n{'SL Distance Distribution':<25} {'CLOSE':>15} {'ZONE':>15}")
    print("-" * 55)
