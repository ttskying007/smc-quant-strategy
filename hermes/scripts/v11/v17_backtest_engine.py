#!/usr/bin/env python3
"""
V17 完整回测引擎 — ENTRY_AT_ZONE + 多源结构SL/TP + Trailing

集成:
- V17 Pine-Exact 信号检测
- structure_zones_v17 多源TP/SL扫描
- ENTRY_AT_ZONE: 入场价=FVG.lower/OB.lower
- 质量过滤: score>=3.0
- 简单trailing: 保本+分段锁利
"""

import sys, json, time, math
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts/v11')
from signals_v17 import detect_all_signals_v17
from structure_zones_v17 import scan_structure_zones
from split_adjuster import load_adjusted

CACHE = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v17')


def backtest_stock_v17(ohlcv, min_quality=3.0, direction='bull'):
    """
    单只股票V17完整回测。
    
    Returns: list of trade dicts
    """
    n = len(ohlcv)
    signals = detect_all_signals_v17(ohlcv)
    
    trades = []
    used_entries = set()  # prevent re-entry on same bar
    
    # Entry sources: FVG_Bull + OB_Bull
    entry_signals = []
    for s in signals.get('fvg', []):
        if s.get('type') == 'FVG_Bull':
            entry_signals.append(('FVG', s))
    for s in signals.get('ob', []):
        if s.get('type') == 'OB_Bull':
            entry_signals.append(('OB', s))
    
    for source, sig in entry_signals:
        entry_bar = sig['confirmed_at']
        if entry_bar >= n - 1 or entry_bar in used_entries:
            continue
        
        # Entry price at zone
        zone_lower = sig.get('lower', 0)
        if zone_lower <= 0:
            continue
        entry_price = zone_lower
        
        # OB entries need: higher quality, minimum RR, better SL selection
        is_ob = (source == 'OB')
        effective_min_quality = max(min_quality, 7.5) if is_ob else min_quality
        
        # Scan structure zones
        zones = scan_structure_zones(ohlcv, signals, entry_bar, entry_price, direction)
        quality = zones['entry_quality']
        
        if quality['score'] < effective_min_quality:
            continue
        
        # SL selection: for OB, skip very close SLs (likely OB_lower position noise)
        sl_candidates = zones['sl_zones']
        if not sl_candidates:
            continue
        
        sl_idx = 0
        if is_ob:
            # Skip SL candidates within 1.0% (includes OB_lower noise)
            while sl_idx < len(sl_candidates) - 1 and sl_candidates[sl_idx]['distance_pct'] < 1.0:
                sl_idx += 1
        elif sl_idx < len(sl_candidates) - 1 and sl_candidates[0]['distance_pct'] < 0.3:
            sl_idx = 1  # FVG: skip only very tight SL
        
        sl_price = sl_candidates[sl_idx]['price']
        sl_distance_pct = sl_candidates[sl_idx]['distance_pct']
        sl_source = sl_candidates[sl_idx]['type']
        
        # TP selection
        if zones['tp_zones']:
            tp_price = zones['tp_zones'][0]['price']
            tp_source = zones['tp_zones'][0]['type']
            tp_distance_pct = zones['tp_zones'][0]['distance_pct']
        else:
            tp_price = entry_price * 1.10  # fallback 10%
            tp_source = 'fallback'
            tp_distance_pct = 10.0
        
        # Minimum RR check for OB: TP must be at least 2x SL distance
        if is_ob:
            rr_ratio = tp_distance_pct / max(sl_distance_pct, 0.01)
            if rr_ratio < 2.0:
                continue
            # Also reject if TP too close (within 2%)
            if tp_distance_pct < 2.0:
                continue
        
        # Simulate exit with simple trailing
        result = _simulate_trailing_exit(ohlcv, entry_bar, entry_price, sl_price, tp_price)
        
        if result:
            used_entries.add(entry_bar)
            trade = {
                'symbol': '',
                'entry_idx': entry_bar,
                'entry_price': round(entry_price, 4),
                'source': source,
                'direction': direction,
                'sl_price': round(sl_price, 4),
                'sl_source': sl_source,
                'tp_price': round(tp_price, 4),
                'tp_source': tp_source,
                'entry_score': round(quality['score'], 1),
                'sl_distance_pct': round(sl_distance_pct, 2),
                'tp_distance_pct': round(tp_distance_pct, 2),
                'tp_count': quality.get('tp_count', 0),
                'rr_ratio': round(tp_distance_pct / max(sl_distance_pct, 0.01), 2),
                **result,
            }
            trades.append(trade)
    
    return trades


def _simulate_trailing_exit(ohlcv, entry_bar, entry_price, sl_price, tp_price):
    """
    带简单trailing的退出模拟。
    
    Rules:
    - 保本: P&L≥0.5% → SL移到entry+0.1%
    - 锁利1: P&L≥1.5% → SL移到entry+0.5%
    - 锁利2: P&L≥3.0% → SL移到entry+1.5%
    - 硬SL: 始终在initial SL
    - 硬TP: 到达target TP
    """
    n = len(ohlcv)
    entry_idx = entry_bar + 1  # exit simulation starts from next bar
    
    if entry_idx >= n:
        return None
    
    highest_high = entry_price
    lowest_low = entry_price
    trailing_sl = sl_price
    exit_bar = None
    exit_price = None
    exit_method = 'eod'
    
    for i in range(entry_idx, n):
        bar = ohlcv[i]
        h, l, c = bar['h'], bar['l'], bar['c']
        
        highest_high = max(highest_high, h)
        lowest_low = min(lowest_low, l)
        
        # Check hard SL
        if l <= sl_price:
            exit_bar = i
            exit_price = sl_price
            exit_method = 'sl_hit'
            break
        
        # Check hard TP
        if h >= tp_price:
            exit_bar = i
            exit_price = tp_price
            exit_method = 'tp_hit'
            break
        
        # Trailing stop updates
        pnl_pct = (c - entry_price) / entry_price * 100
        
        if pnl_pct >= 3.0:
            trailing_sl = max(trailing_sl, entry_price * 1.015)  # lock 1.5%
        elif pnl_pct >= 1.5:
            trailing_sl = max(trailing_sl, entry_price * 1.005)  # lock 0.5%
        elif pnl_pct >= 0.5:
            trailing_sl = max(trailing_sl, entry_price * 1.001)  # breakeven
        
        # Check trailing SL
        if l <= trailing_sl:
            exit_bar = i
            exit_price = trailing_sl
            exit_method = 'trailing'
            break
    
    if exit_bar is None:
        # End of data — close at last close
        exit_bar = n - 1
        exit_price = ohlcv[-1]['c']
        exit_method = 'eod'
    
    pnl_pct = (exit_price - entry_price) / entry_price * 100
    hold_bars = exit_bar - entry_bar
    
    return {
        'exit_idx': exit_bar,
        'exit_price': round(exit_price, 4),
        'exit_method': exit_method,
        'pnl_pct': round(pnl_pct, 4),
        'hold_bars': hold_bars,
        'won': pnl_pct > 0,
    }


def run_backtest(stock_files, min_quality=3.0, verbose=False):
    """
    多股票V17回测。
    
    Args:
        stock_files: list of Path objects
        min_quality: 最低入场质量评分
    
    Returns:
        {summary: {}, stock_results: [], all_trades: []}
    """
    all_trades = []
    stock_results = []
    
    for fpath in stock_files:
        try:
            ohlcv, was_adjusted = load_adjusted(fpath.stem.replace('_daily_300', '').replace('_', '.'))
            if ohlcv is None:
                ohlcv = json.loads(fpath.read_bytes())
        except:
            continue
        
        if len(ohlcv) < 50:
            continue
        
        sym = fpath.stem.replace('_daily_300', '').replace('_', '.')
        
        try:
            trades = backtest_stock_v17(ohlcv, min_quality=min_quality)
        except Exception as e:
            if verbose:
                print(f"  {sym}: ERROR {e}")
            continue
        
        if not trades:
            stock_results.append({
                'symbol': sym, 'n_trades': 0, 'wr': 0, 'avg_pnl': 0, 'total_pnl': 0,
                'adjusted': was_adjusted,
            })
            continue
        
        for t in trades:
            t['symbol'] = sym
        all_trades.extend(trades)
        
        won = sum(1 for t in trades if t['won'])
        wr = won / len(trades) * 100
        avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
        total_pnl = sum(t['pnl_pct'] for t in trades)
        
        stock_results.append({
            'symbol': sym,
            'n_trades': len(trades),
            'wr': round(wr, 1),
            'avg_pnl': round(avg_pnl, 4),
            'total_pnl': round(total_pnl, 4),
            'adjusted': was_adjusted,
        })
    
    # Summary
    n_traded = sum(1 for s in stock_results if s['n_trades'] > 0)
    n_trades = len(all_trades)
    n_won = sum(1 for t in all_trades if t['won'])
    wr = n_won / n_trades * 100 if n_trades > 0 else 0
    avg_pnl = sum(t['pnl_pct'] for t in all_trades) / n_trades if n_trades > 0 else 0
    
    # Exit method distribution
    exit_methods = defaultdict(int)
    for t in all_trades:
        exit_methods[t['exit_method']] += 1
    
    # Entry source distribution  
    entry_sources = defaultdict(int)
    for t in all_trades:
        entry_sources[t['source']] += 1
    
    summary = {
        'engine': 'V17',
        'stocks_scanned': len(stock_files),
        'stocks_traded': n_traded,
        'total_trades': n_trades,
        'wr': round(wr, 1),
        'avg_pnl': round(avg_pnl, 4),
        'total_pnl': round(sum(t['pnl_pct'] for t in all_trades), 4),
        'avg_hold_bars': round(sum(t['hold_bars'] for t in all_trades) / n_trades, 1) if n_trades > 0 else 0,
        'exit_methods': dict(exit_methods),
        'entry_sources': dict(entry_sources),
        'min_quality': min_quality,
    }
    
    # SL source distribution
    sl_sources = defaultdict(int)
    for t in all_trades:
        sl_sources[t['sl_source']] += 1
    summary['sl_sources'] = dict(sl_sources)
    
    # Quality score distribution
    score_bins = defaultdict(int)
    for t in all_trades:
        bucket = int(t['entry_score'])
        score_bins[bucket] += 1
    summary['score_distribution'] = {str(k): v for k, v in sorted(score_bins.items())}
    
    return {
        'summary': summary,
        'stock_results': stock_results,
        'all_trades': all_trades,
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--stocks', type=int, default=200, help='Number of stocks')
    parser.add_argument('--quality', type=float, default=3.0, help='Min quality score')
    parser.add_argument('--output', type=str, default='v17_backtest_200.json', help='Output file')
    args = parser.parse_args()
    
    files = sorted(CACHE.glob('*_daily_300.json'))[:args.stocks]
    
    print(f"V17 Backtest: {len(files)} stocks, min_quality={args.quality}")
    t0 = time.time()
    
    result = run_backtest(files, min_quality=args.quality, verbose=True)
    
    elapsed = time.time() - t0
    summary = result['summary']
    
    print(f"\n{'='*60}")
    print(f"V17 Backtest Complete — {elapsed:.1f}s")
    print(f"{'='*60}")
    print(f"Stocks: {summary['stocks_scanned']} scanned, {summary['stocks_traded']} traded")
    print(f"Trades: {summary['total_trades']} | WR: {summary['wr']}% | Avg P&L: {summary['avg_pnl']}%")
    print(f"Hold: {summary['avg_hold_bars']} bars avg")
    print(f"\nExit methods: {summary['exit_methods']}")
    print(f"Entry sources: {summary['entry_sources']}")
    print(f"SL sources: {summary['sl_sources']}")
    print(f"Score distribution: {summary['score_distribution']}")
    
    # Save
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / args.output
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nSaved to {out_path}")
