#!/usr/bin/env python3
"""
V25.6 Multi-tier Batch TP + Progressive Trailing
=================================================
三层分批止盈 + 渐进跟踪止损

TP structure:
  TP1 (30%) — 1st structural resistance above entry
  TP2 (30%) — 2nd structural resistance (or TP1 × 1.5)
  TP3 (40%) — RUNNER, no fixed target, progressive trailing only

Trailing levels (tightens with profit):
  Phase 1 (0-1R): No trail, SL at cost-line
  Phase 2 (1-2R): Trail = high - 0.3×ATR (loose)
  Phase 3 (2-3R): Trail = high - 0.2×ATR (moderate)
  Phase 4 (>3R):   Trail = high - 0.15×ATR (tight, lock in)

Exit simulation:
  - Walk bars forward, check TP1, TP2 hits in order
  - After each TP hit, reduce position size
  - Runner uses progressive trailing
  - Weighted avg exit price = TP1_price×0.3 + TP2_price×0.3 + trail_price×0.4
"""
import json, sys
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v25')

KLINE_DIR = Path('/root/.hermes/kline_cache')
PICKS_PATH = Path('/root/.hermes/smc_opt_v25/v25_picks.json')
OUT_DIR = Path('/root/.hermes/smc_opt_v25')


def load_kline(symbol):
    parts = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    path = KLINE_DIR / f'{parts}_daily_300.json'
    if path.exists():
        data = json.loads(path.read_text())
        for b in data:
            for k in ('o','h','l','c'):
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


def find_structural_tp_targets(klines, entry_idx, entry_price):
    """Find 2 structural TP targets above entry."""
    highs = sorted(set(
        round(float(klines[j].get('h', 0)), 2)
        for j in range(max(0, entry_idx-60), min(entry_idx+5, len(klines)))
        if float(klines[j].get('h', 0)) > entry_price * 1.03
    ))
    
    if len(highs) >= 2:
        return highs[0], highs[1]  # TP1 = 1st high, TP2 = 2nd high
    elif len(highs) == 1:
        return highs[0], highs[0] * 1.5  # TP2 = TP1 × 1.5
    else:
        tp1 = entry_price * 1.05
        return tp1, tp1 * 1.5


def progressive_trail_buffer(r_multiple, atr):
    """Tighten trail as profit increases."""
    if r_multiple >= 3:
        return atr * 0.15  # Tight lock-in
    elif r_multiple >= 2:
        return atr * 0.2
    elif r_multiple >= 1:
        return atr * 0.3
    else:
        return None  # No trail below 1R


def simulate_batch_exit(pick, klines, state_params):
    """Simulate batch TP + progressive trailing exit."""
    entry_date = str(pick.get('entry_date', ''))
    entry_idx = find_entry_bar(klines, entry_date)
    if entry_idx is None:
        entry_idx = pick.get('entry_idx', len(klines)-1)
    
    entry_price = pick.get('price', pick.get('entry_price', float(klines[entry_idx].get('c',0))))
    
    # Zone-based SL
    dz_low = pick.get('v25_zone_bottom', pick.get('dz_low', entry_price*0.95))
    atr = compute_atr(klines, 14, entry_idx)
    if atr == 0: atr = entry_price * 0.02
    
    sl_mult = state_params.get('sl_atr_mult', 0.5)
    sl_price = dz_low - atr * sl_mult
    sl_pct = abs(entry_price - sl_price) / entry_price * 100
    
    # Structural TP targets
    tp1_price, tp2_price = find_structural_tp_targets(klines, entry_idx, entry_price)
    tp1_pct = (tp1_price - entry_price) / entry_price * 100
    tp2_pct = (tp2_price - entry_price) / entry_price * 100
    
    # Skip if RR < 0.5
    if tp1_pct / max(sl_pct, 0.01) < 0.5:
        return None
    
    # ── Walk-forward simulation ──
    tp1_hit = False; tp1_bar = None; tp1_exit_price = 0
    tp2_hit = False; tp2_bar = None; tp2_exit_price = 0
    runner_exit_bar = None; runner_exit_price = 0; runner_exit_reason = 'timeout'
    
    highest = entry_price
    max_hold = state_params.get('max_hold', 60)
    
    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, len(klines))):
        bar = klines[i]
        lo = float(bar.get('l', 0))
        hi = float(bar.get('h', 0))
        if lo <= 0: continue
        if hi > highest: highest = hi
        
        # R-multiple for trail calculation
        r_mult = (highest - entry_price) / (entry_price - sl_price) if entry_price > sl_price else 0
        
        # ── TP1 check ──
        if not tp1_hit and hi >= tp1_price:
            tp1_hit = True
            tp1_bar = i
            tp1_exit_price = tp1_price
        
        # ── TP2 check ──
        if tp1_hit and not tp2_hit and hi >= tp2_price:
            tp2_hit = True
            tp2_bar = i
            tp2_exit_price = tp2_price
        
        # ── Runner trailing ──
        buf = progressive_trail_buffer(r_mult, atr)
        effective_sl = sl_price  # Default: static SL
        
        if buf is not None:
            trail_level = highest - buf
            if trail_level > sl_price:
                effective_sl = trail_level
        
        # Runner SL hit
        if lo <= effective_sl:
            runner_exit_bar = i
            runner_exit_price = effective_sl
            runner_exit_reason = 'runner_trail' if buf is not None else 'SL_hit'
            break
    
    # If no SL hit, runner exits at last bar
    if runner_exit_bar is None:
        runner_exit_bar = min(entry_idx + max_hold, len(klines) - 1)
        runner_exit_price = float(klines[runner_exit_bar].get('c', 0))
        runner_exit_reason = 'timeout'
    
    # ── Weighted exit price ──
    # 30% @ TP1, 30% @ TP2, 40% @ trailing
    w1 = 0.3 if tp1_hit else 0
    w2 = 0.3 if tp2_hit else 0
    w3 = 1.0 - w1 - w2  # Runner portion
    
    if w3 <= 0:
        w3 = 1.0  # Fallback: no TP hit
        runner_exit_price = tp1_exit_price if tp1_hit else sl_price
    
    avg_exit_price = (
        (tp1_exit_price if tp1_hit else 0) * w1 +
        (tp2_exit_price if tp2_hit else 0) * w2 +
        runner_exit_price * w3
    )
    
    pnl_pct = (avg_exit_price - entry_price) / entry_price * 100
    
    # Determine primary exit reason
    if tp1_hit and tp2_hit:
        primary_reason = f'Batch_TP1+TP2'
    elif tp1_hit:
        primary_reason = f'TP1_{runner_exit_reason}'
    else:
        primary_reason = runner_exit_reason
    
    return {
        'symbol': pick['symbol'],
        'entry_bar': int(entry_idx),
        'entry_price': round(entry_price, 2),
        'exit_bar': int(runner_exit_bar),
        'exit_price': round(avg_exit_price, 2),
        'exit_reason': primary_reason,
        'pnl_pct': round(pnl_pct, 2),
        'hold_bars': int(runner_exit_bar - entry_idx),
        'won': pnl_pct > 0,
        'sl_price': round(sl_price, 2),
        'sl_pct': round(sl_pct, 2),
        'tp1_price': round(tp1_price, 2),
        'tp1_pct': round(tp1_pct, 1),
        'tp1_hit': tp1_hit,
        'tp2_price': round(tp2_price, 2),
        'tp2_pct': round(tp2_pct, 1),
        'tp2_hit': tp2_hit,
        'runner_price': round(runner_exit_price, 2),
        'runner_reason': runner_exit_reason,
        'zone_type': pick.get('zone_type', ''),
        'conf_type': pick.get('conf_type', ''),
        'ctx_seq': pick.get('ctx_seq', ''),
        'market_state': pick.get('market_state', ''),
    }


def run_batch_backtest():
    """Run V25.6 batch TP + progressive trailing backtest."""
    from state_backtest import detect_market_state, STATE_PARAMS
    
    picks = json.loads(PICKS_PATH.read_text())
    print(f"V25.6 Batch TP Backtest: {len(picks)} picks")
    
    trades = []
    skipped_range = 0
    skipped_rr = 0
    skipped_kline = 0
    
    for i, p in enumerate(picks):
        sym = p['symbol']
        klines = load_kline(sym)
        if not klines:
            skipped_kline += 1; continue
        
        entry_date = str(p.get('entry_date', ''))
        entry_idx = find_entry_bar(klines, entry_date)
        if entry_idx is None:
            entry_idx = p.get('entry_idx', len(klines)-1)
        
        # Market state detection
        mkt_state = detect_market_state(klines, entry_idx)
        if mkt_state['state'] == 'RANGE':
            skipped_range += 1; continue
        
        state_params = mkt_state['params']
        
        # Simulate batch exit
        result = simulate_batch_exit(p, klines, state_params)
        if result is None:
            skipped_rr += 1; continue
        
        result['market_state'] = mkt_state['state']
        trades.append(result)
        
        if (i+1) % 100 == 0:
            print(f"  {i+1}/{len(picks)}...")
    
    # ── Stats ──
    n = len(trades)
    won = sum(1 for t in trades if t['won'])
    wr = won/n*100 if n > 0 else 0
    avg_pnl = sum(t['pnl_pct'] for t in trades)/n if n > 0 else 0
    total_pnl = sum(t['pnl_pct'] for t in trades)
    avg_win = sum(t['pnl_pct'] for t in trades if t['won'])/max(won,1)
    avg_loss = sum(t['pnl_pct'] for t in trades if not t['won'])/max(n-won,1)
    avg_hold = sum(t['hold_bars'] for t in trades)/n if n > 0 else 0
    
    exits = Counter(t['exit_reason'] for t in trades)
    tp1_hit_n = sum(1 for t in trades if t.get('tp1_hit'))
    tp2_hit_n = sum(1 for t in trades if t.get('tp2_hit'))
    
    print(f"\n═══ V25.6 Batch TP Backtest ═══")
    print(f"  Skipped: {skipped_range} RANGE, {skipped_rr} low RR, {skipped_kline} no kline")
    print(f"  Trades:     {n}")
    print(f"  Won:        {won} ({wr:.1f}%)")
    print(f"  Avg PnL:    {avg_pnl:+.2f}%")
    print(f"  Total PnL:  {total_pnl:+.2f}%")
    print(f"  Avg Win:    {avg_win:+.2f}%")
    print(f"  Avg Loss:   {avg_loss:+.2f}%")
    print(f"  Avg Hold:   {avg_hold:.1f} bars")
    
    print(f"\n  TP1 hit: {tp1_hit_n} ({tp1_hit_n/n*100:.0f}%), "
          f"TP2 hit: {tp2_hit_n} ({tp2_hit_n/n*100:.0f}%)")
    
    print(f"\n  Exit reasons:")
    for reason, count in exits.most_common(8):
        print(f"    {reason:30s}: {count:4d} ({count/n*100:5.1f}%)")
    
    # By state
    states = Counter(t['market_state'] for t in trades)
    print(f"\n  By market state:")
    for state in ['TREND_UP','TREND_DOWN','HIGH_VOL','LOW_VOL']:
        ts = [t for t in trades if t['market_state'] == state]
        if not ts: continue
        twr = sum(1 for t in ts if t['won'])/len(ts)*100
        tpnl = sum(t['pnl_pct'] for t in ts)/len(ts)
        ttp1 = sum(1 for t in ts if t.get('tp1_hit'))/len(ts)*100
        print(f"    {state:12s}: {len(ts):4d} WR={twr:.1f}% avgP={tpnl:+.2f}% TP1={ttp1:.0f}%")
    
    # By story length
    lens = Counter(len(t['ctx_seq'].split('→')) for t in trades)
    print(f"\n  By story length:")
    for l, c in sorted(lens.items()):
        lt = [t for t in trades if len(t['ctx_seq'].split('→')) == l]
        lwr = sum(1 for t in lt if t['won'])/len(lt)*100
        lpnl = sum(t['pnl_pct'] for t in lt)/len(lt)
        print(f"    {l}-signal: {c:3d} WR={lwr:.1f}% avgP={lpnl:+.2f}%")
    
    # Save
    out = OUT_DIR / 'v256_trades.json'
    out.write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    print(f"\nSaved: {out}")
    
    return trades


if __name__ == '__main__':
    run_batch_backtest()
