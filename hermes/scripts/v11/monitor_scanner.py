#!/usr/bin/env python3
"""
SMC 监控选股系统 V1.0
=====================
基于 combo_validation_v40.json 个股最佳组合
每日扫描: 哪些股票触发了它们的最佳信号组合
输出: JSON watchlist, 前端可展示
"""
import json, time
from pathlib import Path
from collections import defaultdict
import sys

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
COMBO_FILE = OUT / 'combo_validation_v40.json'
OUT.mkdir(exist_ok=True)

CTX_WINDOW = 20
ENTRY_SIGNALS = ['FVG_Bull', 'OB_Bull']

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        c = daily[i:i+5]
        if len(c) >= 3:
            w.append({'o': c[0]['o'], 'h': max(b['h'] for b in c),
                      'l': min(b['l'] for b in c), 'c': c[-1]['c']})
    return w

def weekly_smc(weekly):
    if len(weekly) < 20: return 'neutral'
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb = tc.get('CHOCH_Bull', 0); cbr = tc.get('CHOCH_Bear', 0)
    bb = tc.get('BOS_Bull', 0); bbr = tc.get('BOS_Bear', 0)
    last = [s for s in sigs if 'CHOCH' in s.type]
    last_dir = 'bull' if last and 'Bull' in last[-1].type else ('bear' if last and 'Bear' in last[-1].type else None)
    if last_dir == 'bull' and cb + bb >= cbr + bbr: return 'bullish'
    if last_dir == 'bear' and cbr + bbr > cb + bb: return 'bearish'
    if cb + bb > (cbr + bbr) * 1.5: return 'bullish'
    if cbr + bbr > (cb + bb) * 1.5: return 'bearish'
    return 'neutral'

def parse_combo(combo_str):
    """Parse combo string like "['FVG_Bear']" to set of types"""
    try:
        return frozenset(eval(combo_str))
    except:
        return frozenset()

def scan_stock(sym, ohlcv, best_combos):
    """Check if stock's best combo is currently active"""
    try:
        sigs, _, _, _ = detect_all_signals_v20(ohlcv)
    except:
        return None
    
    n = len(ohlcv)
    sig_by_bar = defaultdict(set)
    for s in sigs:
        sig_by_bar[s.idx].add(s.type)
    
    alerts = []
    
    # Check recent bars (last 5 bars) for entry signals
    for s in sigs:
        if s.type not in ENTRY_SIGNALS: continue
        bar = s.idx
        if bar < n - 10: continue  # only recent signals
        
        # Collect context
        ctx = set()
        for bi in range(max(0, bar - CTX_WINDOW), bar + 1):
            ctx.update(sig_by_bar.get(bi, set()))
        ctx.discard(s.type)
        
        if not ctx: continue
        
        # Check against each best combo
        ctx_frozen = frozenset(ctx)
        for combo_str, combo_info in best_combos.items():
            combo = parse_combo(combo_str)
            if combo and combo.issubset(ctx_frozen):
                # Zone info for entry
                zone_low = s.lower
                zone_high = s.upper
                current_price = ohlcv[-1]['c']
                
                # Check if price is near zone (within 3%)
                dist_to_zone = (current_price - zone_low) / zone_low * 100 if zone_low > 0 else 999
                
                alerts.append({
                    'symbol': sym,
                    'combo': combo_str,
                    'combo_rate': combo_info.get('rate', 0),
                    'entry_signal': s.type,
                    'entry_bar': bar,
                    'zone_low': round(zone_low, 2),
                    'zone_high': round(zone_high, 2),
                    'current_price': round(current_price, 2),
                    'dist_to_zone_pct': round(dist_to_zone, 1),
                    'action': 'ready' if dist_to_zone < 3 else 'watching',
                })
    
    return alerts if alerts else None


def main():
    # Load combo validation results
    if not COMBO_FILE.exists():
        print("ERROR: combo_validation_v40.json not found. Run combo_validation_v40.py first.")
        return
    
    with open(COMBO_FILE) as f:
        combo_data = json.load(f)
    
    print(f"Loaded {len(combo_data)} stock combo profiles")
    
    # Scan all stocks
    daily_files = sorted(KLINE.glob('*_daily_300.json'))
    t0 = time.time()
    
    all_alerts = []
    scan_stats = {'scanned': 0, 'with_combo': 0, 'triggered': 0}
    
    for fi, df in enumerate(daily_files):
        name = df.stem.replace('_daily_300', '')
        parts = name.rsplit('_', 1)
        sym = f'{parts[0]}.{parts[1]}' if len(parts) == 2 else name
        
        # Get best combos for this stock
        if sym not in combo_data:
            continue
        
        stock_combo = combo_data[sym]
        scan_stats['with_combo'] += 1
        
        # Get best combo from 'recent' window (prefer recent over full)
        best_combos = {}
        windows_data = stock_combo.get('windows', {})
        for wn in ['recent', 'mid', 'full']:
            wd = windows_data.get(wn, {})
            if wd:
                # Take top-3 combos from this window
                sorted_combos = sorted(wd.items(), key=lambda x: x[1].get('rate', 0), reverse=True)[:3]
                for combo_str, combo_info in sorted_combos:
                    if combo_str not in best_combos:
                        best_combos[combo_str] = combo_info
                break  # prefer first available window
        
        if not best_combos:
            continue
        
        try:
            daily = json.loads(df.read_bytes())
            if len(daily) < 50: continue
        except:
            continue
        
        scan_stats['scanned'] += 1
        
        # Weekly trend
        weekly_path = KLINE / f'{name}_weekly_200.json'
        try:
            if weekly_path.exists():
                weekly = json.loads(weekly_path.read_bytes())
                if len(weekly) < 20: weekly = daily_to_weekly(daily)
            else:
                weekly = daily_to_weekly(daily)
        except:
            weekly = daily_to_weekly(daily)
        w_trend = weekly_smc(weekly)
        
        alerts = scan_stock(sym, daily, best_combos)
        if alerts:
            for a in alerts:
                a['w_trend'] = w_trend
            all_alerts.extend(alerts)
            scan_stats['triggered'] += 1
        
        if (fi + 1) % 1000 == 0:
            elapsed = time.time() - t0
            print(f"  [{fi+1}/{len(daily_files)}] {elapsed:.0f}s alerts={len(all_alerts)}")
    
    elapsed = time.time() - t0
    
    # ═══ REPORT ═══
    print(f"\n{'='*60}")
    print(f"  SMC 监控选股扫描 ({elapsed:.0f}s)")
    print(f"  扫描: {scan_stats['scanned']}只 | 有组合: {scan_stats['with_combo']}只")
    print(f"  触发: {scan_stats['triggered']}只 | 告警: {len(all_alerts)}条")
    print(f"{'='*60}")
    
    # Sort: ready first (near zone), then watching
    all_alerts.sort(key=lambda a: (a['action'] != 'ready', -a['combo_rate']))
    
    print(f"\n  🟢 可入场 (距Zone<3%):")
    ready = [a for a in all_alerts if a['action'] == 'ready']
    for i, a in enumerate(ready[:20]):
        print(f"  {i+1:2d}. {a['symbol']:12s} {a['w_trend']:8s} [{a['combo'][:40]}] "
              f"rate={a['combo_rate']:.0%} zone={a['zone_low']} 现价={a['current_price']} 距={a['dist_to_zone_pct']}%")
    
    print(f"\n  🟡 观察中 (等回调):")
    watching = [a for a in all_alerts if a['action'] == 'watching']
    for i, a in enumerate(watching[:20]):
        print(f"  {i+1:2d}. {a['symbol']:12s} {a['w_trend']:8s} [{a['combo'][:40]}] "
              f"rate={a['combo_rate']:.0%} zone={a['zone_low']} 现价={a['current_price']} 距={a['dist_to_zone_pct']}%")
    
    # ═══ SAVE ═══
    output = {
        'meta': {
            'version': '1.0',
            'scan_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'method': 'per-stock best combo from combo_validation_v40.json',
            'stats': scan_stats,
        },
        'ready': ready,
        'watching': watching,
    }
    json.dump(output, open(OUT / 'monitor_watchlist.json', 'w'), ensure_ascii=False)
    print(f"\n  Saved: {OUT/'monitor_watchlist.json'}")
    print(f"  Ready: {len(ready)} | Watching: {len(watching)}")

if __name__ == '__main__':
    main()
