#!/usr/bin/env python3
"""Phase 2 Backtest: Compare Old (immediate) vs New (POI retrace) entry logic"""
import json, sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v11')

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v25')

# Use v22 signals
from signals_v22 import detect_all_signals_v22

print(f"=== Phase 2 Backtest: Old vs New Entry Logic ===")
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

kfiles = sorted(KLINE_DIR.glob('*_daily_750.json'))[:300]
print(f"Scanning {len(kfiles)} stocks...\n")

results_old = []
results_new = []

def compute_atr(klines, bar, n=14):
    start = max(1, bar - n)
    trs = []
    for i in range(start, bar + 1):
        hi = klines[i].get('h', 0)
        lo = klines[i].get('l', 0)
        pc = klines[i-1].get('c', lo)
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    return sum(trs) / max(1, len(trs))

def simulate(klines, entry_bar, entry_price, sl, tp1, symbol, sig_type, mode):
    n = len(klines)
    max_hold = 60
    for i in range(entry_bar + 1, min(entry_bar + max_hold, n)):
        hi = klines[i].get('h', 0)
        lo = klines[i].get('l', 0)
        cl = klines[i].get('c', 0)
        
        if lo <= sl:
            pnl = (sl / entry_price - 1) * 100
            return {'pnl_pct': pnl, 'exit_reason': 'SL_HIT', 'hold_bars': i - entry_bar, 'mode': mode, 'symbol': symbol, 'sig': sig_type}
        if hi >= tp1:
            pnl = (tp1 / entry_price - 1) * 100
            return {'pnl_pct': pnl, 'exit_reason': 'TP1_HIT', 'hold_bars': i - entry_bar, 'mode': mode, 'symbol': symbol, 'sig': sig_type}
    # Time stop
    if entry_bar + max_hold < n:
        exit_price = klines[entry_bar + max_hold].get('c', 0)
        pnl = (exit_price / entry_price - 1) * 100
        return {'pnl_pct': pnl, 'exit_reason': 'TIME_STOP', 'hold_bars': max_hold, 'mode': mode, 'symbol': symbol, 'sig': sig_type}
    return None

for ki, kf in enumerate(kfiles[:300]):
    if ki % 50 == 0 and ki > 0:
        print(f"  {ki}/{min(len(kfiles),300)} processed...")
    
    sym = kf.stem.replace('_daily_750', '')
    symbol = sym.replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
    
    try:
        klines = json.loads(kf.read_text())
    except:
        continue
    
    if len(klines) < 100:
        continue
    
    for b in klines:
        for k in ('o', 'h', 'l', 'c', 'v'):
            if k in b:
                b[k] = float(b[k])
    
    try:
        sigs, summary, swings, sig_dict = detect_all_signals_v22(klines)
    except:
        continue
    
    if not sigs:
        continue
    
    processed_zones = set()
    
    for sig in sigs:
        sig_type = sig.type if hasattr(sig, 'type') else ''
        if sig_type not in ('OB_Bull', 'FVG_Bull'):
            continue
        
        zone_bar = sig.bar if hasattr(sig, 'bar') else (sig.idx if hasattr(sig, 'idx') else 0)
        if zone_bar < 14 or zone_bar >= len(klines) - 45:
            continue
        
        zone_key = (symbol, zone_bar, sig_type)
        if zone_key in processed_zones:
            continue
        processed_zones.add(zone_key)
        
        # Zone boundaries
        if hasattr(sig, 'meta') and sig.meta:
            zone_low = sig.meta.get('ob_low', klines[zone_bar].get('l', 0))
            zone_high = sig.meta.get('ob_high', klines[zone_bar].get('h', 0))
        else:
            zone_low = klines[zone_bar].get('l', 0)
            zone_high = klines[zone_bar].get('h', 0)
        
        if zone_low <= 0 or zone_high <= zone_low:
            continue
        
        atr = compute_atr(klines, zone_bar)
        
        # SL: zone_low - 0.5 * ATR with floor
        sl = zone_low - atr * 0.5
        hard_floor = zone_low * 0.995
        sl = min(sl, hard_floor)
        
        # TP1: 1.5R
        risk = abs(zone_low - sl) / zone_low * 100
        if risk < 0.5:
            risk = 1.5  # Minimum 1.5%
        tp1 = zone_high * (1 + risk * 1.5 / 100)
        
        # === OLD: Immediate entry on next bar ===
        entry_bar_old = zone_bar + 1
        if entry_bar_old < len(klines):
            entry_price_old = klines[entry_bar_old].get('o', 0)
            trade_old = simulate(klines, entry_bar_old, entry_price_old, sl, tp1, symbol, sig_type, 'immediate')
            if trade_old:
                results_old.append(trade_old)
        
        # === NEW: POI retrace entry within 30 bars ===
        found_retrace = False
        for eb in range(zone_bar + 3, min(zone_bar + 31, len(klines) - 5)):
            lo = klines[eb].get('l', 0)
            hi = klines[eb].get('h', 0)
            
            if lo > zone_high:
                continue
            if lo < zone_low * 0.95:
                break
            
            touches_zone = lo <= zone_high and hi >= zone_low
            if touches_zone:
                entry_price_new = klines[eb].get('c', 0)
                trade_new = simulate(klines, eb, entry_price_new, sl, tp1, symbol, sig_type, 'poi_retrace')
                if trade_new:
                    results_new.append(trade_new)
                found_retrace = True
                break

print(f"\n{'='*60}")
print(f"=== BACKTEST RESULTS ===")
print(f"{'='*60}\n")
print(f"Stocks scanned: {len(kfiles[:300])}")
print(f"Old (immediate entry): {len(results_old)} trades")
print(f"New (POI retrace entry): {len(results_new)} trades")
print()

def metrics(trades, label):
    if not trades:
        print(f"{label}: No trades\n")
        return {}
    
    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]
    sl_hits = [t for t in trades if t['exit_reason'] == 'SL_HIT']
    tp_hits = [t for t in trades if 'TP' in t['exit_reason']]
    
    wr = len(wins) / len(trades) * 100
    avg_win = sum(t['pnl_pct'] for t in wins) / max(1, len(wins))
    avg_loss = sum(t['pnl_pct'] for t in losses) / max(1, len(losses))
    rr = avg_win / abs(avg_loss) if avg_loss else 0
    cum = sum(t['pnl_pct'] for t in trades)
    sl_rate = len(sl_hits) / len(trades) * 100
    avg_hold = sum(t['hold_bars'] for t in trades) / len(trades)
    
    print(f"  {label}:")
    print(f"    Trades: {len(trades)}")
    print(f"    Win Rate: {wr:.1f}% ({len(wins)}W/{len(losses)}L)")
    print(f"    Avg Win: {avg_win:+.2f}%")
    print(f"    Avg Loss: {avg_loss:+.2f}%")
    print(f"    RR Ratio: {rr:.2f}x")
    print(f"    SL Hits: {len(sl_hits)} ({sl_rate:.1f}%)")
    print(f"    TP Hits: {len(tp_hits)}")
    print(f"    Cumulative: {cum:+.1f}%")
    print(f"    Avg Hold: {avg_hold:.1f} bars")
    print()
    
    return {'wr': wr, 'cum': cum, 'rr': rr, 'sl_rate': sl_rate, 'n': len(trades), 'avg_win': avg_win, 'avg_loss': avg_loss}

print("-"*60)
old_m = metrics(results_old, "OLD (立即入场)")
print("-"*60)
new_m = metrics(results_new, "NEW (POI回撤入场)")
print("-"*60)

if old_m and new_m:
    print(f"\n{'='*60}")
    print(f"=== PHASE 2 IMPROVEMENT ===")
    print(f"{'='*60}")
    print(f"  WR: {old_m['wr']:.1f}% → {new_m['wr']:.1f}% ({new_m['wr']-old_m['wr']:+.1f}%)")
    print(f"  RR: {old_m['rr']:.2f}x → {new_m['rr']:.2f}x ({new_m['rr']-old_m['rr']:+.2f}x)")
    print(f"  SL Rate: {old_m['sl_rate']:.1f}% → {new_m['sl_rate']:.1f}% ({new_m['sl_rate']-old_m['sl_rate']:+.1f}%)")
    print(f"  Cum PnL: {old_m['cum']:+.1f}% → {new_m['cum']:+.1f}%")
    print(f"  Trades: {old_m['n']} → {new_m['n']}")
    
    # Per-trade efficiency
    old_per = old_m['cum'] / max(1, old_m['n'])
    new_per = new_m['cum'] / max(1, new_m['n'])
    print(f"  Per-trade: {old_per:+.2f}% → {new_per:+.2f}% ({new_per-old_per:+.2f}%)")
else:
    print("\nInsufficient data for comparison")

# Save results
output = {
    'timestamp': datetime.now().isoformat(),
    'stocks': len(kfiles[:300]),
    'old': {'trades': len(results_old), **old_m} if old_m else {},
    'new': {'trades': len(results_new), **new_m} if new_m else {},
    'old_trades_sample': results_old[:10],
    'new_trades_sample': results_new[:10],
}
OUT_DIR.mkdir(exist_ok=True)
with open(OUT_DIR / 'phase2_backtest_results.json', 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\nSaved to: {OUT_DIR}/phase2_backtest_results.json")
