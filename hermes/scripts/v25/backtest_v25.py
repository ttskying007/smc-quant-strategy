#!/usr/bin/env python3
"""
V25 Backtest Engine
Simulates exits on V25 picks to compute real WR, PnL, hold_bars, exit reasons.
Supports: trailing stops, multi-tier TP, dynamic SL.
"""
import json, sys, os
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v25')

KLINE_DIR = Path('/root/.hermes/kline_cache')
PICKS_PATH = Path('/root/.hermes/smc_opt_v25/v25_picks.json')
OUT_DIR = Path('/root/.hermes/smc_opt_v25')


def load_kline(symbol: str) -> list:
    parts = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    path = KLINE_DIR / f'{parts}_daily_300.json'
    if path.exists():
        data = json.loads(path.read_text())
        for b in data:
            for k in ('o', 'h', 'l', 'c'):
                if k in b:
                    b[k] = float(b[k])
        return data
    return []


def find_entry_bar(klines, entry_date):
    """Find the bar index matching entry_date in klines."""
    if not entry_date:
        return None
    entry_date = str(entry_date)
    for i, b in enumerate(klines):
        bar_date = str(b.get('t', b.get('date', '')))
        if bar_date == entry_date:
            return i
    return None


def simulate_exit(pick, klines):
    """
    Simulate exit for a single pick.
    Walks forward from entry bar, checks SL hit / TP hit / timeout.
    Supports trailing stop.
    
    Returns: {
        'entry_bar', 'exit_bar', 'entry_price', 'exit_price',
        'exit_reason', 'pnl_pct', 'hold_bars', 'won',
        'sl_price', 'tp1_price', 'trail_activated'
    }
    """
    entry_date = str(pick.get('entry_date', ''))
    entry_idx = find_entry_bar(klines, entry_date)
    
    if entry_idx is None:
        # Fallback: use entry_idx from pick if available
        entry_idx = pick.get('entry_idx')
        if entry_idx is None or entry_idx >= len(klines):
            return None
    
    entry_price = pick.get('price', pick.get('entry_price', 0))
    if not entry_price or entry_price == 0:
        entry_price = float(klines[entry_idx].get('c', 0))
    
    # Use V25 SL price directly (already computed by engine)
    sl_price = pick.get('v25_sl_price', 0)
    if not sl_price:
        # Fallback
        sl_pct = pick.get('v25_sl_pct', pick.get('sl_initial_pct', 5))
        sl_price = entry_price * (1 - sl_pct / 100)
    
    # TP tiers from V25
    tp_tiers = pick.get('v25_tp_tiers', [])
    if not tp_tiers:
        tp_pct = 0
        tp_str = pick.get('tp_tiers', '')
        if isinstance(tp_str, str) and '(' in tp_str:
            import re
            m = re.search(r'\(([\d.]+)%\)', tp_str)
            if m: tp_pct = float(m.group(1))
        elif isinstance(tp_str, list) and tp_str:
            tp_pct = float(tp_str[0])
        tp_tiers = [{'price': entry_price * (1 + tp_pct/100) if tp_pct else 0, 'pct': tp_pct, 'alloc': 1.0}]
    
    tp1_price = tp_tiers[0]['price'] if tp_tiers else entry_price * 1.10
    tp1_alloc = tp_tiers[0].get('alloc', 1.0)
    
    # Trailing stop config
    trail_activate_r = 1.0  # Activate after 1R profit
    trail_buffer = pick.get('v25_atr', 1) * 0.5  # ATR-based buffer
    trail_active = False
    trail_level = None
    highest_high = entry_price
    
    # Walk forward
    exit_idx = entry_idx
    exit_price = entry_price
    exit_reason = 'timeout'
    max_hold = 120  # Max hold bars
    
    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, len(klines))):
        bar = klines[i]
        lo = float(bar.get('l', 0))
        hi = float(bar.get('h', 0))
        cl = float(bar.get('c', 0))
        
        if lo <= 0 or hi <= 0:
            continue
        
        # Update highest high (for trailing)
        if hi > highest_high:
            highest_high = hi
        
        # Check trailing stop activation
        if not trail_active and highest_high >= entry_price * (1 + trail_activate_r * abs(entry_price - sl_price) / entry_price):
            trail_active = True
            trail_level = highest_high - trail_buffer
        
        # Update trailing level
        if trail_active:
            trail_level = max(trail_level or 0, highest_high - trail_buffer)
        
        # Check SL hit (use trailing if active)
        effective_sl = trail_level if trail_active else sl_price
        if lo <= effective_sl:
            exit_idx = i
            exit_price = effective_sl
            exit_reason = 'trailing' if trail_active else 'SL_hit'
            break
        
        # Check TP1 hit (partial)
        if tp1_price > 0 and hi >= tp1_price:
            exit_idx = i
            # Weighted exit: TP1 portion at TP1 price, rest at close
            exit_price = tp1_price * tp1_alloc + cl * (1 - tp1_alloc)
            exit_reason = f'TP1_{tp_tiers[0].get("type", "target")}'
            break
    
    # Compute metrics
    pnl_pct = (exit_price - entry_price) / entry_price * 100
    hold_bars = exit_idx - entry_idx
    won = pnl_pct > 0
    
    return {
        'symbol': pick['symbol'],
        'entry_date': str(entry_date),
        'entry_bar': int(entry_idx),
        'entry_price': round(entry_price, 2),
        'exit_bar': int(exit_idx),
        'exit_price': round(exit_price, 2),
        'exit_reason': exit_reason,
        'pnl_pct': round(pnl_pct, 2),
        'hold_bars': int(hold_bars),
        'won': bool(won),
        'sl_price': round(sl_price, 2),
        'tp1_price': round(tp1_price, 2),
        'trail_activated': trail_active,
        'zone_type': pick.get('zone_type', ''),
        'conf_type': pick.get('conf_type', ''),
        'regime': pick.get('regime', ''),
        'ctx_seq': pick.get('ctx_seq', ''),
        'v253_quality': pick.get('v253_quality', 0),
        'v253_tier': pick.get('v253_tier', ''),
        'v25_sl_pct': round(pick.get('v25_sl_pct', 0), 2),
        'v25_atr_pct': round(pick.get('v25_atr_pct', 0), 2),
    }


def run_backtest(picks_path=None, output_path=None):
    """Run backtest on all V25 picks."""
    if picks_path is None:
        picks_path = PICKS_PATH
    if output_path is None:
        output_path = OUT_DIR / 'v25_trades.json'
    
    picks = json.loads(Path(picks_path).read_text())
    print(f"Backtesting {len(picks)} picks...")
    
    trades = []
    skipped_no_kline = 0
    skipped_no_entry = 0
    
    for i, p in enumerate(picks):
        sym = p['symbol']
        klines = load_kline(sym)
        if not klines:
            skipped_no_kline += 1
            continue
        
        result = simulate_exit(p, klines)
        if result is None:
            skipped_no_entry += 1
            continue
        
        trades.append(result)
        
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(picks)}...")
    
    # Save
    output_path = Path(output_path)
    output_path.write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    print(f"\nBacktest complete: {len(trades)} trades")
    print(f"  Skipped: {skipped_no_kline} no kline, {skipped_no_entry} no entry")
    
    # ── Stats ──
    n = len(trades)
    won_n = sum(1 for t in trades if t['won'])
    wr = won_n / n * 100
    avg_pnl = sum(t['pnl_pct'] for t in trades) / n
    total_pnl = sum(t['pnl_pct'] for t in trades)
    avg_win = sum(t['pnl_pct'] for t in trades if t['won']) / max(won_n, 1)
    avg_loss = sum(t['pnl_pct'] for t in trades if not t['won']) / max(n - won_n, 1)
    avg_hold = sum(t['hold_bars'] for t in trades) / n
    
    exits = Counter(t['exit_reason'] for t in trades)
    trail_rate = sum(1 for t in trades if t['trail_activated']) / n * 100
    
    print(f"\n═══ V25 Backtest Results ═══")
    print(f"  Trades:     {n}")
    print(f"  Won:        {won_n} ({wr:.1f}%)")
    print(f"  Avg PnL:    {avg_pnl:+.2f}%")
    print(f"  Total PnL:  {total_pnl:+.2f}%")
    print(f"  Avg Win:    {avg_win:+.2f}%")
    print(f"  Avg Loss:   {avg_loss:+.2f}%")
    print(f"  Avg Hold:   {avg_hold:.1f} bars")
    print(f"  Trail:      {trail_rate:.1f}% activated")
    
    print(f"\n  Exit reasons:")
    for reason, count in exits.most_common():
        print(f"    {reason:25s}: {count:4d} ({count/n*100:5.1f}%)")
    
    # Per-tier analysis
    tiers = Counter(t['v253_tier'] for t in trades)
    print(f"\n  By quality tier:")
    for tier in ['ELITE', 'STANDARD', 'SPECULATIVE']:
        tier_trades = [t for t in trades if t['v253_tier'] == tier]
        if not tier_trades: continue
        twr = sum(1 for t in tier_trades if t['won']) / len(tier_trades) * 100
        tpnl = sum(t['pnl_pct'] for t in tier_trades) / len(tier_trades)
        print(f"    {tier:12s}: {len(tier_trades):4d} WR={twr:.1f}% avgP={tpnl:+.2f}%")
    
    # Per-zone analysis
    zones = Counter(t['zone_type'] for t in trades)
    print(f"\n  By zone type:")
    for zone, count in zones.most_common(5):
        zt = [t for t in trades if t['zone_type'] == zone]
        zwr = sum(1 for t in zt if t['won']) / len(zt) * 100
        zpnl = sum(t['pnl_pct'] for t in zt) / len(zt)
        print(f"    {zone:25s}: {count:4d} WR={zwr:.1f}% avgP={zpnl:+.2f}%")
    
    # Per-conf analysis
    confs = Counter(t['conf_type'] for t in trades)
    print(f"\n  By confirmation:")
    for conf, count in confs.most_common(5):
        ct = [t for t in trades if t['conf_type'] == conf]
        cwr = sum(1 for t in ct if t['won']) / len(ct) * 100
        cpnl = sum(t['pnl_pct'] for t in ct) / len(ct)
        print(f"    {conf:25s}: {count:4d} WR={cwr:.1f}% avgP={cpnl:+.2f}%")
    
    # PnL distribution
    pnl_ranges = Counter()
    for t in trades:
        p = t['pnl_pct']
        if p <= -10: pnl_ranges['<= -10%'] += 1
        elif p <= -5: pnl_ranges['-10~-5%'] += 1
        elif p < 0: pnl_ranges['-5~0%'] += 1
        elif p == 0: pnl_ranges['0%'] += 1
        elif p < 5: pnl_ranges['0~5%'] += 1
        elif p < 10: pnl_ranges['5~10%'] += 1
        elif p < 20: pnl_ranges['10~20%'] += 1
        else: pnl_ranges['>20%'] += 1
    
    print(f"\n  PnL distribution:")
    for rng in ['<= -10%', '-10~-5%', '-5~0%', '0%', '0~5%', '5~10%', '10~20%', '>20%']:
        if rng in pnl_ranges:
            bar = '█' * (pnl_ranges[rng] * 50 // n)
            print(f"    {rng:10s}: {pnl_ranges[rng]:4d} {bar}")
    
    return trades


if __name__ == '__main__':
    run_backtest()
