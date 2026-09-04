#!/usr/bin/env python3
"""SMC V6.2 Monitor — Retrace Entry + Immediate Entry"""
import json, subprocess, time
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
MONITOR = OUT / 'live_monitor_v6'
MONITOR.mkdir(exist_ok=True)
PICKS_FILE = OUT / 'LD_picks_v6.json'
POSITIONS_FILE = MONITOR / 'active_positions.json'
LOG_FILE = MONITOR / 'pnl_log.json'
# Backtest-optimized retrace params (40-param grid search, 2000 stocks)
MAX_WAIT = 7       # WR=97.9% n=798  (3→98.2%n=758, 15→95.1%n=873)
SL_MUL = 0.96       # Best across all MW (0.97→-0.3pp WR, 0.99→-0.8pp WR)

def init_positions():
    existing = {}
    if POSITIONS_FILE.exists():
        for p in json.loads(POSITIONS_FILE.read_bytes()):
            key = f"{p['symbol']}|{p.get('signal_date','')}|{p.get('signal','')}"
            existing[key] = p
    
    picks = []
    if PICKS_FILE.exists():
        data = json.loads(PICKS_FILE.read_bytes())
        picks = data.get('picks', data) if isinstance(data, dict) else data
    picks = picks if isinstance(picks, list) else []
    
    positions = []
    seen = set()
    for p in existing.values():
        key = f"{p['symbol']}|{p.get('signal_date','')}|{p.get('signal','')}"
        seen.add(key); positions.append(p)
    
    for p in picks:
        key = f"{p['symbol']}|{p.get('signal_date','')}|{p.get('signal','')}"
        if key in seen: continue
        seen.add(key)
        
        entry_mode = p.get('entry_mode', 'immediate')
        zone_low = p.get('zone_low', p.get('entry_price', 0))
        
        if entry_mode == 'retrace':
            # Waiting for retrace — not yet entered
            status = 'waiting'
            actual_entry = 0
        else:
            # Immediate entry at next bar open
            status = 'open'
            actual_entry = float(p.get('entry_price', 0))
        
        positions.append({
            'symbol': p['symbol'], 'tier': p.get('tier','?'),
            'signal': p.get('signal','?'), 'score': p.get('score',0),
            'signal_date': str(p.get('signal_date','')),
            'entry_date': str(p.get('entry_date','')),
            'entry_price': actual_entry,
            'zone_price': zone_low,  # Target entry for retrace
            'entry_mode': entry_mode,
            'sl_price': float(p.get('sl',0)),
            'tp_price': float(p.get('tp',0)),
            'zone_type': p.get('zone_type','?'),
            'gap': p.get('gap',0),
            'trend': p.get('trend','?'),
            'state': p.get('state','?'),
            'status': status,
            'opened_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'checked_at': '', 'current_price': 0,
            'retrace_bars': 0,  # How many bars since signal (for waiting)
        })
    
    json.dump(positions, open(POSITIONS_FILE,'w'), ensure_ascii=False, indent=2)
    return positions

def check_exits():
    positions = init_positions()
    log = []
    if LOG_FILE.exists(): log = json.loads(LOG_FILE.read_bytes())
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    today = datetime.now().strftime('%Y%m%d')
    triggered = []; checked = 0
    
    for pos in positions:
        signal_day = str(pos.get('signal_date','')).replace('-','')[:8]
        entry_mode = pos.get('entry_mode', 'immediate')
        sym_clean = pos['symbol'].replace('.','_')
        df = KLINE / f'{sym_clean}_daily_300.json'
        if not df.exists(): continue
        try: daily = json.loads(df.read_bytes())
        except: continue
        
        # Find signal bar index
        sig_idx = -1
        for j, b in enumerate(daily):
            if str(b.get('t',b.get('date','')))[:8] == signal_day:
                sig_idx = j; break
        if sig_idx < 0: continue
        
        # ═══ RETRACE MODE: wait for price to touch zone ═══
        if entry_mode == 'retrace' and pos['status'] == 'waiting':
            zone_price = pos['zone_price']
            bars_since = len(daily) - sig_idx - 1
            pos['retrace_bars'] = bars_since
            
            # Check if retrace happened
            retraced = False; retrace_bar = -1
            for k in range(sig_idx+1, min(sig_idx+MAX_WAIT+1, len(daily))):
                if daily[k]['l'] <= zone_price:
                    retraced = True; retrace_bar = k; break
            
            if retraced:
                # Enter at zone price
                pos['status'] = 'open'
                pos['entry_price'] = zone_price
                pos['entry_date'] = str(daily[retrace_bar].get('t',''))[:8]
                pos['opened_at'] = now
                # Tight SL below zone
                pos['sl_price'] = round(zone_price * SL_MUL, 2)
                print(f"  ✅ {pos['symbol']} retrace entry at {zone_price:.2f} (zone hit)")
            elif bars_since >= MAX_WAIT:
                # No retrace — cancel
                pos['status'] = 'cancelled'
                pos['current_price'] = daily[-1]['c']
                print(f"  ❌ {pos['symbol']} cancelled (no retrace in {MAX_WAIT} bars)")
            else:
                # Still waiting
                pos['current_price'] = daily[-1]['c']
                pos['checked_at'] = now
            continue
        
        # ═══ OPEN POSITIONS: check TP/SL ═══
        if pos['status'] != 'open': continue
        entry_day = str(pos.get('entry_date','')).replace('-','')[:8]
        if entry_day == today: continue  # T+1: skip same-day exit
        
        checked += 1
        if checked > 500: break
        
        entry_date = pos.get('entry_date','')[:8]
        tp = pos['tp_price']; sl = pos['sl_price']; ep = pos['entry_price']
        if ep == 0: continue
        
        entry_idx = -1
        for j, b in enumerate(daily):
            if str(b.get('t',b.get('date','')))[:8] == entry_date:
                entry_idx = j; break
        if entry_idx < 0: continue
        
        # Scan forward for TP/SL
        exit_idx = -1; exit_price = 0; exit_method = 'eod'
        for k in range(entry_idx+1, len(daily)):
            bk = daily[k]
            if bk['h'] >= tp: exit_idx=k; exit_price=tp; exit_method='tp_hit'; break
            if bk['l'] <= sl: exit_idx=k; exit_price=sl; exit_method='sl_hit'; break
        if exit_idx < 0:
            exit_idx = len(daily) - 1; exit_price = daily[exit_idx]['c']
        
        if exit_idx <= entry_idx: continue
        
        pnl = (exit_price - ep) / ep * 100
        pos['status'] = 'closed'
        pos['current_price'] = exit_price
        pos['pnl'] = round(pnl, 2)
        pos['exit_method'] = exit_method
        pos['exit_date'] = str(daily[exit_idx].get('t',''))[:8]
        pos['closed_at'] = now
        
        log.append({
            'symbol': pos['symbol'], 'tier': pos['tier'],
            'signal': pos.get('signal','?'), 'entry': ep, 'exit': exit_price,
            'pnl': round(pnl, 2), 'reason': exit_method,
            'date': pos['exit_date'],
        })
        
        em = '🟢' if pnl > 0 else '🔴'
        print(f"  {em} {pos['symbol']} [{pos['tier']}] {pos['signal']} e={ep:.2f} x={exit_price:.2f} pnl={pnl:+.2f}% {exit_method}")
    
    # Save
    json.dump(positions, open(POSITIONS_FILE,'w'), ensure_ascii=False, indent=2)
    json.dump(log, open(LOG_FILE,'w'), ensure_ascii=False)
    
    # Summary
    open_pos = [p for p in positions if p['status'] == 'open']
    waiting = [p for p in positions if p['status'] == 'waiting']
    closed = [p for p in positions if p['status'] == 'closed']
    cancelled = [p for p in positions if p['status'] == 'cancelled']
    
    tp_hits = sum(1 for e in log if e.get('reason') == 'tp_hit')
    sl_hits = sum(1 for e in log if e.get('reason') == 'sl_hit')
    total_pnl = sum(e.get('pnl', 0) for e in log)
    wr = tp_hits / (tp_hits + sl_hits) * 100 if (tp_hits + sl_hits) > 0 else 0
    
    print(f"\n  📊 持仓={len(open_pos)} 等待回调={len(waiting)} 已平={len(closed)} 取消={len(cancelled)}")
    if log:
        recent = log[-10:]
        wr_r = sum(1 for e in recent if e['pnl'] > 0) / len(recent) * 100
        avg_tp = sum(e['pnl'] for e in recent if e['pnl']>0) / max(1,sum(1 for e in recent if e['pnl']>0))
        avg_sl = sum(abs(e['pnl']) for e in recent if e['pnl']<=0) / max(1,sum(1 for e in recent if e['pnl']<=0))
        print(f"  WR={wr:.1f}% avgTP=+{avg_tp:.2f}% avgSL=-{avg_sl:.2f}% totalPnL={total_pnl:+.1f}%")
    
    json.dump(positions, open(POSITIONS_FILE,'w'), ensure_ascii=False, indent=2)
    json.dump(log, open(LOG_FILE,'w'), ensure_ascii=False)

if __name__ == '__main__':
    check_exits()
