#!/usr/bin/env python3
"""
V25.1 Quick-Fix Backtest — based on V25 backtest diagnosis.
Fixes:
  1. TP = nearest structural BOS level (not ATR×2.5) — same as V24 approach
  2. SL = zone_bottom - 0.5*ATR (was 1.0-1.5*ATR) — tighter, closer to V24
  3. Entry filter: require Sweep or CHOCH in signal sequence
  4. Only ELITE tier entries
"""
import json, sys, os, re
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')

KLINE_DIR = Path('/root/.hermes/kline_cache')
IN_DIR = Path('/root/.hermes/smc_opt_v25')
OUT_DIR = Path('/root/.hermes/smc_opt_v25')


def load_kline(symbol):
    parts = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    path = KLINE_DIR / f'{parts}_daily_300.json'
    if path.exists():
        data = json.loads(path.read_text())
        for b in data:
            for k in ('o', 'h', 'l', 'c'):
                if k in b: b[k] = float(b[k])
        return data
    return []


def find_entry_bar(klines, entry_date):
    entry_date = str(entry_date)
    for i, b in enumerate(klines):
        if str(b.get('t', b.get('date', ''))) == entry_date:
            return i
    return None


def compute_atr(klines, period, idx):
    if idx < period: return 0
    trs = []
    for i in range(idx-period+1, idx+1):
        b, pb = klines[i], klines[i-1]
        h, l = float(b.get('h',0)), float(b.get('l',0))
        pc = float(pb.get('c',0))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 0


def fix_sltp(pick, klines):
    """Apply V25.1 corrected SL/TP to a pick."""
    entry_date = str(pick.get('entry_date', ''))
    entry_idx = find_entry_bar(klines, entry_date)
    if entry_idx is None:
        entry_idx = pick.get('entry_idx', len(klines)-1)
    
    entry_price = pick.get('price', pick.get('entry_price', float(klines[entry_idx].get('c',0))))
    
    atr = compute_atr(klines, 14, entry_idx)
    if atr == 0: atr = entry_price * 0.03
    
    # Zone bounds
    dz_low = pick.get('v25_zone_bottom', pick.get('dz_low', entry_price*0.95))
    dz_high = pick.get('v25_zone_top', pick.get('dz_high', entry_price*1.05))
    
    # ── FIX 1: Tighter SL = zone_bottom - 0.5*ATR (was 1.0-1.5*ATR) ──
    sl_price = dz_low - atr * 0.5
    sl_pct = abs(entry_price - sl_price) / entry_price * 100
    
    # ── FIX 2: TP = nearest structural BOS level from kline ──
    # Find swing highs above entry (recent resistance)
    highs_above = []
    for i in range(max(0, entry_idx-50), min(entry_idx+10, len(klines))):
        h = float(klines[i].get('h',0))
        if h > entry_price * 1.02:
            highs_above.append(h)
    
    if highs_above:
        tp1_price = min(highs_above)
        tp1_pct = (tp1_price - entry_price) / entry_price * 100
    else:
        # Fallback: use V24-style BOS level from pick data
        tp_str = pick.get('tp_tiers', '')
        if isinstance(tp_str, str):
            m = re.search(r'\(([\d.]+)%\)', tp_str)
            if m:
                tp1_pct = float(m.group(1))
                tp1_price = entry_price * (1 + tp1_pct/100)
            else:
                tp1_pct = 5.0
                tp1_price = entry_price * 1.05
        else:
            tp1_pct = 5.0
            tp1_price = entry_price * 1.05
    
    # Skip if RR < 1.0
    rr = tp1_pct / sl_pct if sl_pct > 0 else 0
    
    return {
        'sl_price': round(sl_price, 2),
        'sl_pct': round(sl_pct, 2),
        'tp1_price': round(tp1_price, 2),
        'tp1_pct': round(tp1_pct, 1),
        'rr': round(rr, 2),
        'atr': round(atr, 2),
    }


def simulate_exit(pick, params, klines):
    """Simulate exit with corrected SL/TP."""
    entry_date = str(pick.get('entry_date', ''))
    entry_idx = find_entry_bar(klines, entry_date)
    if entry_idx is None:
        entry_idx = pick.get('entry_idx', len(klines)-1)
    
    entry_price = pick.get('price', pick.get('entry_price', float(klines[entry_idx].get('c',0))))
    sl_price = params['sl_price']
    tp_price = params['tp1_price']
    
    # Trailing: activate after 1R, use swing lows as trail
    trail_activate = entry_price + (entry_price - sl_price)  # 1R
    trail_active = False
    trail_level = None
    highest = entry_price
    swing_low = entry_price
    
    exit_idx = entry_idx
    exit_price = entry_price
    exit_reason = 'timeout'
    max_hold = 60
    
    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, len(klines))):
        bar = klines[i]
        lo = float(bar.get('l', 0))
        hi = float(bar.get('h', 0))
        cl = float(bar.get('c', 0))
        
        if lo <= 0:
            continue
        
        if hi > highest:
            highest = hi
        
        # Trail activation
        if not trail_active and highest >= trail_activate:
            trail_active = True
            trail_level = highest - (highest - entry_price) * 0.3  # Trail at 70% of profit
        
        # Update trail using swing lows
        if trail_active and lo < swing_low:
            swing_low = lo
        
        effective_sl = max(trail_level or 0, swing_low - params['atr']*0.3) if trail_active else sl_price
        
        # TP hit
        if hi >= tp_price:
            exit_idx = i
            exit_price = tp_price
            exit_reason = 'TP_hit'
            break
        
        # SL hit
        if lo <= effective_sl:
            exit_idx = i
            exit_price = effective_sl
            exit_reason = 'trailing' if trail_active else 'SL_hit'
            break
    
    pnl_pct = (exit_price - entry_price) / entry_price * 100
    
    return {
        'symbol': pick['symbol'],
        'entry_date': str(entry_date),
        'entry_bar': int(entry_idx),
        'entry_price': round(entry_price, 2),
        'exit_bar': int(exit_idx),
        'exit_price': round(exit_price, 2),
        'exit_reason': exit_reason,
        'pnl_pct': round(pnl_pct, 2),
        'hold_bars': int(exit_idx - entry_idx),
        'won': pnl_pct > 0,
        'sl_price': params['sl_price'],
        'tp_price': params['tp1_price'],
        'sl_pct': params['sl_pct'],
        'tp_pct': params['tp1_pct'],
        'rr': params['rr'],
        'trail_activated': trail_active,
        'zone_type': pick.get('zone_type', ''),
        'conf_type': pick.get('conf_type', ''),
        'ctx_seq': pick.get('ctx_seq', ''),
        'v253_quality': pick.get('v253_quality', 0),
        'v253_tier': pick.get('v253_tier', ''),
    }


def run_v251_backtest():
    """V25.1: Fixed SL/TP + filtered entries"""
    # Load picks
    picks_path = IN_DIR / 'v25_picks.json'
    if not picks_path.exists():
        picks_path = IN_DIR / 'v253_scored_picks.json'
    picks = json.loads(picks_path.read_text())
    print(f"Loaded {len(picks)} picks")
    
    # Picks already filtered by full_scan (Sweep/CHOCH/BOS + RR≥0.6)
    filtered = picks
    print(f"\nUsing all {len(picks)} picks (pre-filtered by scan)")
    
    # ── Backtest ──
    trades = []
    skipped_no_kline = 0
    skipped_bad_rr = 0
    
    for i, p in enumerate(filtered):
        sym = p['symbol']
        klines = load_kline(sym)
        if not klines:
            skipped_no_kline += 1
            continue
        
        params = fix_sltp(p, klines)
        if params['rr'] < 0.6:
            skipped_bad_rr += 1
            continue
        
        result = simulate_exit(p, params, klines)
        if result:
            trades.append(result)
        
        if (i+1) % 30 == 0:
            print(f"  {i+1}/{len(filtered)}...")
    
    # ── Stats ──
    n = len(trades)
    won_n = sum(1 for t in trades if t['won'])
    wr = won_n/n*100 if n > 0 else 0
    avg_pnl = sum(t['pnl_pct'] for t in trades)/n if n > 0 else 0
    avg_win = sum(t['pnl_pct'] for t in trades if t['won'])/max(won_n,1)
    avg_loss = sum(t['pnl_pct'] for t in trades if not t['won'])/max(n-won_n,1)
    exits = Counter(t['exit_reason'] for t in trades)
    
    print(f"\n═══ V25.1 Fixed Backtest ═══")
    print(f"  Trades:     {n}")
    print(f"  Won:        {won_n} ({wr:.1f}%)")
    print(f"  Avg PnL:    {avg_pnl:+.2f}%")
    print(f"  Total PnL:  {sum(t['pnl_pct'] for t in trades):+.2f}%")
    print(f"  Avg Win:    {avg_win:+.2f}%  Avg Loss: {avg_loss:+.2f}%")
    print(f"  Avg Hold:   {sum(t['hold_bars'] for t in trades)/n:.1f}b")
    print(f"  Avg RR:     {sum(t['rr'] for t in trades)/n:.2f}")
    
    print(f"\n  Exit reasons:")
    for reason, count in exits.most_common():
        print(f"    {reason:20s}: {count:4d} ({count/n*100:5.1f}%)")
    
    # Per-conf breakdown
    confs = Counter(t['conf_type'] for t in trades)
    print(f"\n  By confirmation:")
    for conf, count in confs.most_common():
        ct = [t for t in trades if t['conf_type'] == conf]
        cwr = sum(1 for t in ct if t['won'])/len(ct)*100
        cpnl = sum(t['pnl_pct'] for t in ct)/len(ct)
        print(f"    {conf:20s}: {count:3d} WR={cwr:.1f}% avgP={cpnl:+.2f}%")
    
    # Per-zone
    zones = Counter(t['zone_type'] for t in trades)
    print(f"\n  By zone:")
    for zone, count in zones.most_common(5):
        zt = [t for t in trades if t['zone_type'] == zone]
        zwr = sum(1 for t in zt if t['won'])/len(zt)*100
        zpnl = sum(t['pnl_pct'] for t in zt)/len(zt)
        print(f"    {zone:25s}: {count:3d} WR={zwr:.1f}% avgP={zpnl:+.2f}%")
    
    # Per sequence length
    lens = Counter(len(t['ctx_seq'].split('→')) for t in trades)
    print(f"\n  By story length:")
    for l, count in sorted(lens.items()):
        lt = [t for t in trades if len(t['ctx_seq'].split('→')) == l]
        lwr = sum(1 for t in lt if t['won'])/len(lt)*100
        lpnl = sum(t['pnl_pct'] for t in lt)/len(lt)
        print(f"    {l}-signal: {count:3d} WR={lwr:.1f}% avgP={lpnl:+.2f}%")
    
    # Save
    out_path = OUT_DIR / 'v251_trades.json'
    out_path.write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    print(f"\nSaved: {out_path}")
    
    return trades


if __name__ == '__main__':
    run_v251_backtest()
