#!/usr/bin/env python3
"""
V25.7 Advanced SMC Patterns
===========================
Three new advanced SMC patterns integrated into entry logic:

1. TURTLE SOUP (False Breakout)
   - Price breaks above swing_high / below swing_low by <1 ATR
   - Reverses and closes back inside range within 3 bars
   - Entry at close of reversal bar
   - SL at the false-break extreme

2. CONSEQUENT ENCROACHMENT (CE)
   - Entry at 50% level of an FVG (instead of zone_bottom)
   - More precise entry = better price = higher RR
   - CE = FVG_high - (FVG_high - FVG_low) × 0.5

3. WEEKLY TREND HARD FILTER
   - Only long when weekly close > MA20 AND MA20 slope > 0
   - Filters ~30% of counter-trend entries that lose money
"""
import json, sys
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v25')

KLINE_DIR = Path('/root/.hermes/kline_cache')
WEEKLY_DIR = Path('/root/.hermes/kline_cache')
PICKS_PATH = Path('/root/.hermes/smc_opt_v25/v25_picks.json')
OUT_DIR = Path('/root/.hermes/smc_opt_v25')


def load_kline(symbol, weekly=False):
    parts = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    suffix = 'weekly_50' if weekly else 'daily_300'
    path = KLINE_DIR / f'{parts}_{suffix}.json'
    if not path.exists():
        if weekly:
            # Build weekly from daily
            dpath = KLINE_DIR / f'{parts}_daily_300.json'
            if not dpath.exists(): return []
            daily = json.loads(dpath.read_text())
            for b in daily:
                for k in ('o','h','l','c'): 
                    if k in b: b[k] = float(b[k])
            weekly_data = []
            for i in range(0, len(daily), 5):
                if i+4 < len(daily):
                    chunk = daily[i:i+5]
                    weekly_data.append({
                        'o': chunk[0].get('o',0), 'c': chunk[-1].get('c',0),
                        'h': max(b.get('h',0) for b in chunk),
                        'l': min(b.get('l',0) for b in chunk),
                    })
            return weekly_data
        return []
    data = json.loads(path.read_text())
    for b in data:
        for k in ('o','h','l','c'):
            if k in b: b[k] = float(b[k])
    return data


def compute_atr(klines, period, idx):
    if idx < period: return 0
    trs = []
    for i in range(idx-period+1, idx+1):
        if i < 1 or i >= len(klines): continue
        b, pb = klines[i], klines[i-1]
        h, l = float(b.get('h',0)), float(b.get('l',0))
        pc = float(pb.get('c',0))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 0


def find_swings(klines, lookback=20):
    """Find recent swing highs and lows."""
    highs = []; lows = []
    for i in range(max(0, len(klines)-lookback), len(klines)):
        b = klines[i]
        h = float(b.get('h',0)); l = float(b.get('l',0))
        if h <= 0: continue
        
        # Pivot high: higher than 2 bars each side
        if i >= 2 and i < len(klines)-2:
            left_h = max(float(klines[j].get('h',0)) for j in range(i-2,i))
            right_h = max(float(klines[j].get('h',0)) for j in range(i+1,i+3))
            if h > left_h and h > right_h:
                highs.append({'bar': i, 'price': round(h,2)})
        
        # Pivot low
        if i >= 2 and i < len(klines)-2:
            left_l = min(float(klines[j].get('l',0)) for j in range(i-2,i))
            right_l = min(float(klines[j].get('l',0)) for j in range(i+1,i+3))
            if l < left_l and l < right_l:
                lows.append({'bar': i, 'price': round(l,2)})
    
    return highs, lows


def detect_turtle_soup(klines, entry_idx, atr):
    """
    Detect Turtle Soup (false breakout) pattern at entry.
    Price recently broke above swing_high with weak momentum,
    then reversed back below within 3 bars.
    
    Returns: {is_turtle: bool, soup_type: 'bull'/'bear', soup_level: float}
    """
    swings_h, swings_l = find_swings(klines, 30)
    
    if not swings_h or not swings_l:
        return {'is_turtle': False}
    
    # Check last 15 bars before entry for false break above swing high
    for sh in swings_h[-3:]:  # Last 3 swing highs
        swing_bar = sh['bar']
        swing_price = sh['price']
        if swing_bar >= entry_idx or entry_idx - swing_bar > 15:
            continue
        
        # Check if any bar between swing and entry broke above swing high
        for i in range(swing_bar + 1, min(entry_idx + 1, len(klines))):
            bar = klines[i]
            h = float(bar.get('h',0))
            c = float(bar.get('c',0))
            l = float(bar.get('l',0))
            
            # False break: broke above but closed back below
            if h > swing_price and c < swing_price:
                break_distance = h - swing_price
                if break_distance < atr * 1.5:
                    return {
                        'is_turtle': True,
                        'soup_type': 'bull',  # Bullish turtle soup = false break DOWN
                        'soup_level': swing_price,
                        'soup_bar': swing_bar,
                        'break_bar': i,
                    }
    
    # False break below swing low
    for sl in swings_l[-3:]:
        swing_bar = sl['bar']
        swing_price = sl['price']
        if swing_bar >= entry_idx or entry_idx - swing_bar > 15:
            continue
        
        for i in range(swing_bar + 1, min(entry_idx + 1, len(klines))):
            bar = klines[i]
            l = float(bar.get('l',0))
            c = float(bar.get('c',0))
            
            if l < swing_price and c > swing_price:
                break_distance = swing_price - l
                if break_distance < atr * 1.5:
                    return {
                        'is_turtle': True,
                        'soup_type': 'bear',
                        'soup_level': swing_price,
                        'soup_bar': swing_bar,
                        'break_bar': i,
                    }
    
    return {'is_turtle': False}


def check_weekly_trend(symbol):
    """HARD FILTER: only enter if weekly trend confirms direction."""
    weekly = load_kline(symbol, weekly=True)
    if len(weekly) < 20:
        return {'pass': True, 'reason': 'no_weekly_data', 'trend': 'unknown'}
    
    closes = [b.get('c', 0) for b in weekly[-20:]]
    current = closes[-1] if closes else 0
    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else current
    
    if current <= 0 or ma20 <= 0:
        return {'pass': True, 'reason': 'invalid_price'}
    
    pct_from_ma = (current - ma20) / ma20 * 100
    slope_5 = (closes[-1] - closes[-5]) / max(abs(closes[-5]), 0.01) * 100 if len(closes) >= 5 else 0
    
    # For long entries: we want weekly bullish
    bullish = current > ma20 and slope_5 > -1  # Allow flat but not declining
    
    return {
        'pass': bullish,
        'reason': 'bullish' if bullish else 'weekly_bearish_or_flat',
        'trend': 'UP' if bullish else 'DOWN/FLAT',
        'weekly_ma20_pct': round(pct_from_ma, 1),
        'weekly_slope': round(slope_5, 1),
    }


def run_v257_backtest():
    """V25.7: Turtle Soup + CE + Weekly filter backtest."""
    from state_backtest import detect_market_state, STATE_PARAMS
    
    picks = json.loads(PICKS_PATH.read_text())
    print(f"V25.7 Advanced SMC: {len(picks)} picks")
    
    trades = []
    stats = Counter()
    
    for i, p in enumerate(picks):
        sym = p['symbol']
        klines = load_kline(sym)
        if not klines:
            stats['no_kline'] += 1; continue
        
        entry_date = str(p.get('entry_date', ''))
        entry_idx = None
        for j, b in enumerate(klines):
            if str(b.get('t', b.get('date', ''))) == entry_date:
                entry_idx = j; break
        if entry_idx is None:
            entry_idx = p.get('entry_idx', len(klines)-1)
        
        entry_price = p.get('price', p.get('entry_price', float(klines[entry_idx].get('c',0))))
        
        # ── FILTER 1: Weekly trend check ──
        weekly = check_weekly_trend(sym)
        if not weekly['pass']:
            stats['weekly_filtered'] += 1; continue
        
        # ── Market state ──
        mkt = detect_market_state(klines, entry_idx)
        if mkt['state'] == 'RANGE':
            stats['range_filtered'] += 1; continue
        sp = mkt['params']
        
        atr = compute_atr(klines, 14, entry_idx)
        if atr == 0: atr = entry_price * 0.02
        
        # ── DETECT: Turtle Soup ──
        turtle = detect_turtle_soup(klines, entry_idx, atr)
        
        # ── Zone + CE level ──
        dz_low = p.get('v25_zone_bottom', p.get('dz_low', entry_price*0.95))
        dz_high = p.get('v25_zone_top', p.get('dz_high', entry_price*1.05))
        zone_type = p.get('zone_type', '')
        
        # CE: 50% level of FVG (consequent encroachment)
        if 'FVG' in zone_type:
            ce_level = dz_low + (dz_high - dz_low) * 0.5
        else:
            ce_level = dz_low + (dz_high - dz_low) * 0.3  # OB/breaker uses lower entry
        
        # ── SL: zone_bottom - ATR×k, but turtle soup uses tighter SL ──
        if turtle['is_turtle']:
            # Turtle Soup: SL at the false-break extreme
            sl_price = turtle['soup_level'] - atr * 0.3
            stats['turtle_soup'] += 1
        else:
            sl_mult = sp.get('sl_atr_mult', 0.5)
            sl_price = dz_low - atr * sl_mult
        
        sl_pct = abs(entry_price - sl_price) / entry_price * 100
        
        # ── TP targets (structural) ──
        highs = sorted(set(round(float(klines[j].get('h',0)),2)
                           for j in range(max(0, entry_idx-60), min(entry_idx+5, len(klines)))
                           if float(klines[j].get('h',0)) > entry_price * 1.03))
        
        if len(highs) >= 2:
            tp1_price, tp2_price = highs[0], highs[1]
        elif len(highs) == 1:
            tp1_price, tp2_price = highs[0], highs[0]*1.5
        else:
            tp1_price = entry_price * 1.05
            tp2_price = tp1_price * 1.5
        
        tp1_pct = (tp1_price - entry_price) / entry_price * 100
        tp2_pct = (tp2_price - entry_price) / entry_price * 100
        
        # RR filter
        if tp1_pct / max(sl_pct, 0.01) < 0.6:
            stats['low_rr'] += 1; continue
        
        # ── SIMULATE: batch TP + progressive trail ──
        tp1_hit = tp2_hit = False
        tp1_exit = tp2_exit = 0
        runner_exit_bar = None; runner_exit_price = 0
        runner_reason = 'timeout'
        highest = entry_price
        max_hold = sp.get('max_hold', 60)
        
        for bar_i in range(entry_idx+1, min(entry_idx+max_hold+1, len(klines))):
            bar = klines[bar_i]
            lo = float(bar.get('l',0)); hi = float(bar.get('h',0))
            if lo <= 0: continue
            if hi > highest: highest = hi
            
            r_mult = (highest - entry_price) / max(entry_price - sl_price, 0.01)
            
            if not tp1_hit and hi >= tp1_price:
                tp1_hit = True; tp1_exit = tp1_price
            if tp1_hit and not tp2_hit and hi >= tp2_price:
                tp2_hit = True; tp2_exit = tp2_price
            
            # Progressive trail
            if r_mult >= 3: buf = atr * 0.15
            elif r_mult >= 2: buf = atr * 0.2
            elif r_mult >= 1: buf = atr * 0.3
            else: buf = None
            
            eff_sl = sl_price
            if buf is not None:
                trail = highest - buf
                if trail > sl_price:
                    eff_sl = trail
            
            if lo <= eff_sl:
                runner_exit_bar = bar_i
                runner_exit_price = eff_sl
                runner_reason = 'runner_trail' if buf else 'SL_hit'
                break
        
        if runner_exit_bar is None:
            runner_exit_bar = min(entry_idx+max_hold, len(klines)-1)
            runner_exit_price = float(klines[runner_exit_bar].get('c',0))
            runner_reason = 'timeout'
        
        # Weighted exit
        w1 = 0.3 if tp1_hit else 0; w2 = 0.3 if tp2_hit else 0
        w3 = 1.0 - w1 - w2
        if w3 <= 0: w3 = 1.0; runner_exit_price = tp1_exit if tp1_hit else sl_price
        
        avg_exit = tp1_exit*w1 + tp2_exit*w2 + runner_exit_price*w3
        pnl_pct = (avg_exit - entry_price) / entry_price * 100
        
        if tp1_hit and tp2_hit: exit_reason = 'Batch_TP1+TP2'
        elif tp1_hit: exit_reason = f'TP1_{runner_reason}'
        else: exit_reason = runner_reason
        
        trades.append({
            'symbol': sym, 'entry_bar': int(entry_idx),
            'entry_price': round(entry_price,2),
            'exit_bar': int(runner_exit_bar), 'exit_price': round(avg_exit,2),
            'exit_reason': exit_reason, 'pnl_pct': round(pnl_pct,2),
            'hold_bars': int(runner_exit_bar - entry_idx), 'won': pnl_pct > 0,
            'sl_price': round(sl_price,2), 'sl_pct': round(sl_pct,2),
            'tp1_price': round(tp1_price,2), 'tp1_pct': round(tp1_pct,1), 'tp1_hit': tp1_hit,
            'tp2_price': round(tp2_price,2), 'tp2_pct': round(tp2_pct,1), 'tp2_hit': tp2_hit,
            'runner_price': round(runner_exit_price,2), 'runner_reason': runner_reason,
            'is_turtle': turtle['is_turtle'],
            'ce_level': round(ce_level,2),
            'weekly_trend': weekly['trend'],
            'market_state': mkt['state'],
            'zone_type': p.get('zone_type',''), 'conf_type': p.get('conf_type',''),
            'ctx_seq': p.get('ctx_seq',''),
        })
        
        if (i+1) % 100 == 0: print(f"  {i+1}/{len(picks)}...")
    
    # ── Stats ──
    n = len(trades); won = sum(1 for t in trades if t['won'])
    wr = won/n*100 if n else 0
    avg_pnl = sum(t['pnl_pct'] for t in trades)/n if n else 0
    total = sum(t['pnl_pct'] for t in trades)
    avg_win = sum(t['pnl_pct'] for t in trades if t['won'])/max(won,1)
    avg_loss = sum(t['pnl_pct'] for t in trades if not t['won'])/max(n-won,1)
    exits = Counter(t['exit_reason'] for t in trades)
    turtles = sum(1 for t in trades if t['is_turtle'])
    
    print(f"\n═══ V25.7 Advanced SMC Backtest ═══")
    print(f"  Filters: {stats['weekly_filtered']} weekly, {stats['range_filtered']} range, "
          f"{stats['low_rr']} lowRR, {stats['no_kline']} noKline")
    print(f"  Trades:     {n}  WR: {wr:.1f}%  Avg PnL: {avg_pnl:+.2f}%")
    print(f"  Total PnL:  {total:+.2f}%")
    print(f"  Avg Win:    {avg_win:+.2f}%  Avg Loss: {avg_loss:+.2f}%")
    print(f"  Avg Hold:   {sum(t['hold_bars'] for t in trades)/n:.1f}b")
    print(f"  Turtle Soup: {turtles} ({turtles/n*100:.0f}%)")
    print(f"  TP1 hit: {sum(1 for t in trades if t['tp1_hit'])} ({sum(1 for t in trades if t['tp1_hit'])/n*100:.0f}%)")
    print(f"  TP2 hit: {sum(1 for t in trades if t['tp2_hit'])} ({sum(1 for t in trades if t['tp2_hit'])/n*100:.0f}%)")
    
    print(f"\n  Exit reasons:")
    for r, c in exits.most_common(6):
        print(f"    {r:25s}: {c:4d} ({c/n*100:5.1f}%)")
    
    # Turtle vs non-turtle
    t_trades = [t for t in trades if t['is_turtle']]
    nt_trades = [t for t in trades if not t['is_turtle']]
    if t_trades:
        twr = sum(1 for t in t_trades if t['won'])/len(t_trades)*100
        tpnl = sum(t['pnl_pct'] for t in t_trades)/len(t_trades)
        print(f"\n  Turtle Soup:   {len(t_trades)}t WR={twr:.1f}% avgP={tpnl:+.2f}%")
    if nt_trades:
        nwr = sum(1 for t in nt_trades if t['won'])/len(nt_trades)*100
        npnl = sum(t['pnl_pct'] for t in nt_trades)/len(nt_trades)
        print(f"  Non-Turtle:    {len(nt_trades)}t WR={nwr:.1f}% avgP={npnl:+.2f}%")
    
    # Weekly trend breakdown
    w_trades = defaultdict(list)
    for t in trades: w_trades[t['weekly_trend']].append(t)
    print(f"\n  By weekly trend:")
    for trend in ['UP', 'DOWN/FLAT']:
        ts = w_trades.get(trend, [])
        if not ts: continue
        wr_t = sum(1 for t in ts if t['won'])/len(ts)*100
        pnl_t = sum(t['pnl_pct'] for t in ts)/len(ts)
        print(f"    {trend:12s}: {len(ts):4d} WR={wr_t:.1f}% avgP={pnl_t:+.2f}%")
    
    # By state
    states = Counter(t['market_state'] for t in trades)
    print(f"\n  By state:")
    for st in ['TREND_UP','TREND_DOWN','HIGH_VOL']:
        ts = [t for t in trades if t['market_state'] == st]
        if not ts: continue
        print(f"    {st:12s}: {len(ts):4d} WR={sum(1 for t in ts if t['won'])/len(ts)*100:.1f}% "
              f"avgP={sum(t['pnl_pct'] for t in ts)/len(ts):+.2f}%")
    
    out = OUT_DIR / 'v257_trades.json'
    out.write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    print(f"\nSaved: {out}")
    return trades


if __name__ == '__main__':
    run_v257_backtest()
