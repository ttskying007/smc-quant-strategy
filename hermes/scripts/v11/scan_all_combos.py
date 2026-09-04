#!/usr/bin/env python3
"""
全量信号组合扫描 — 不筛选, 全部输出
所有 bullish 股票的 LIQ/STRUCT → ZONE(OB/FVG) 组合
含完整时间/价格/间隔信息
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

# ═══ 全部信号类型 ═══
LIQ_LONG = ['Sweep_SSL', 'EQL']
STRUCT_LONG = ['CHOCH_Bull','BOS_Bull','MSS_Bull']
ZONE_LONG = ['OB_Bull','FVG_Bull']
ALL_START = LIQ_LONG + STRUCT_LONG

WINDOW_DAYS = 30
MAX_GAP = 25  # 最大间隔bar

def weekly_trend_simple(weekly):
    if len(weekly) < 20: return 'neutral'
    ma20 = sum(b['c'] for b in weekly[-20:]) / 20
    if weekly[-1]['c'] > ma20 * 1.02: return 'bullish'
    if weekly[-1]['c'] < ma20 * 0.98: return 'bearish'
    return 'neutral'

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        c = daily[i:i+5]
        if len(c) >= 3:
            w.append({'o':c[0]['o'],'h':max(b['h'] for b in c),'l':min(b['l'] for b in c),'c':c[-1]['c']})
    return w

# ═══ MAIN ═══
t0 = time.time()
daily_files = sorted(KLINE.glob('*_daily_300.json'))
all_combos = []
stats = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnls': []})

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Weekly filter
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    weekly = None
    if weekly_path.exists():
        try: weekly = json.loads(weekly_path.read_bytes())
        except: pass
    if weekly is None or len(weekly) < 20:
        weekly = daily_to_weekly(daily)
    if weekly_trend_simple(weekly) != 'bullish': continue
    
    # Signals
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    sbb = defaultdict(list)
    for s in sigs: sbb[s.idx].append(s)
    
    n = len(daily)
    last_date = datetime.strptime(str(daily[-1].get('t', daily[-1].get('date', '')))[:8], '%Y%m%d')
    cutoff = last_date - timedelta(days=WINDOW_DAYS)
    
    # ═══ Scan ALL bar pairs ═══
    for start_bar in range(max(0, n-60), n-3):
        if start_bar not in sbb: continue
        
        start_sigs = [s for s in sbb[start_bar] if s.type in ALL_START]
        if not start_sigs: continue
        
        sig_date = str(daily[start_bar].get('t', daily[start_bar].get('date', '')))[:8]
        try:
            if datetime.strptime(sig_date, '%Y%m%d') < cutoff: continue
        except: continue
        
        for start_sig in start_sigs:
            # Scan for ZONE signals within MAX_GAP
            for zone_bar in range(start_bar + 1, min(start_bar + MAX_GAP + 1, n)):
                if zone_bar not in sbb: continue
                
                zone_sigs = [s for s in sbb[zone_bar] if s.type in ZONE_LONG]
                if not zone_sigs: continue
                
                gap = zone_bar - start_bar
                zone_date = str(daily[zone_bar].get('t', daily[zone_bar].get('date', '')))[:8]
                
                for zone_sig in zone_sigs:
                    entry_bar = zone_bar + 1
                    if entry_bar >= n - 2: continue
                    ep = daily[entry_bar]['o']
                    if ep == 0: continue
                    
                    tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
                    sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
                    if tp is None: tp = ep * 1.05
                    if tp > ep * 1.05: tp = ep * 1.05
                    if sl is None: sl = ep * 0.97
                    
                    tpd = abs(tp-ep)/ep*100; sld = abs(sl-ep)/ep*100
                    
                    # Forward test
                    exit_idx = -1; exit_p = 0; exit_m = 'open'
                    for k in range(entry_bar+1, n):
                        b = daily[k]
                        if b['h'] >= tp: exit_idx = k; exit_p = tp; exit_m = 'tp_hit'; break
                        if b['l'] <= sl: exit_idx = k; exit_p = sl; exit_m = 'sl_hit'; break
                    if exit_idx < 0: exit_idx = n-1; exit_p = daily[exit_idx]['c']; exit_m = 'eod'
                    if exit_idx <= entry_bar: continue
                    
                    pnl = (exit_p - ep) / ep * 100
                    
                    # Zone details
                    zone_lo = zone_sig.lower if hasattr(zone_sig,'lower') and zone_sig.lower else 0
                    zone_up = zone_sig.upper if hasattr(zone_sig,'upper') and zone_sig.upper else 0
                    
                    chain_label = f'{start_sig.type}→{zone_sig.type}'
                    
                    combo = {
                        'symbol': sym,
                        'chain': chain_label,
                        'start_type': start_sig.type,
                        'start_bar': start_bar,
                        'start_date': sig_date,
                        'start_price': start_sig.price,
                        'start_o': daily[start_bar]['o'],
                        'start_h': daily[start_bar]['h'],
                        'start_l': daily[start_bar]['l'],
                        'start_c': daily[start_bar]['c'],
                        'zone_type': zone_sig.type,
                        'zone_bar': zone_bar,
                        'zone_date': zone_date,
                        'zone_price': zone_sig.price,
                        'zone_low': zone_lo,
                        'zone_up': zone_up,
                        'zone_o': daily[zone_bar]['o'],
                        'zone_h': daily[zone_bar]['h'],
                        'zone_l': daily[zone_bar]['l'],
                        'zone_c': daily[zone_bar]['c'],
                        'gap': gap,
                        'entry_bar': entry_bar,
                        'entry_date': str(daily[entry_bar].get('t', daily[entry_bar].get('date', '')))[:8],
                        'entry_price': ep,
                        'sl': round(sl,2),
                        'tp': round(tp,2),
                        'sl_pct': round(sld, 1),
                        'tp_pct': round(tpd, 1),
                        'rr': round(tpd/sld, 1) if sld > 0 else 0,
                        'pnl': round(pnl, 2),
                        'exit_method': exit_m,
                        'exit_bar': exit_idx,
                        'exit_date': str(daily[exit_idx].get('t', daily[exit_idx].get('date', '')))[:8],
                        'exit_price': round(exit_p, 2),
                        'hold_bars': exit_idx - entry_bar,
                        'current_price': daily[-1]['c'],
                    }
                    all_combos.append(combo)
                    stats[chain_label]['count'] += 1
                    if pnl > 0: stats[chain_label]['wins'] += 1
                    stats[chain_label]['pnls'].append(pnl)
    
    if (fi+1) % 500 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s combos={len(all_combos)}")

elapsed = time.time() - t0

# ═══ Stats Report ═══
print(f"\n{'='*100}")
print(f'全量信号组合 — {elapsed:.0f}s — {len(all_combos)}个组合')
print(f'{"="*100}')
print(f'\n{"链类型":<35s} {"数量":>5s} {"WR":>6s} {"avgPnL":>7s} {"cumPnL":>8s} {"avgGap":>7s}')
print(f'{"-"*72}')

for chain, s in sorted(stats.items(), key=lambda x: -x[1]['count']):
    if s['count'] == 0: continue
    wr = s['wins'] / s['count'] * 100
    avg = sum(s['pnls']) / len(s['pnls'])
    cum = sum(s['pnls'])
    # avg gap for this chain
    gaps = [c['gap'] for c in all_combos if c['chain'] == chain]
    avg_gap = sum(gaps) / len(gaps) if gaps else 0
    print(f'  {chain:<35s} {s["count"]:>5d} {wr:>5.1f}% {avg:>+6.2f}% {cum:>+7.1f}% {avg_gap:>6.1f}b')

# ═══ By gap buckets ═══
print(f'\n{"="*60}')
print(f'按间隔分桶 (全部组合)')
print(f'{"="*60}')
gap_buckets = defaultdict(lambda: {'t':0,'w':0,'pnls':[]})
for c in all_combos:
    gap = c['gap']
    bucket = f'gap={gap:2d}' if gap <= 10 else 'gap=11+'
    gap_buckets[bucket]['t'] += 1
    if c['pnl'] > 0: gap_buckets[bucket]['w'] += 1
    gap_buckets[bucket]['pnls'].append(c['pnl'])

for bucket in sorted(gap_buckets.keys()):
    d = gap_buckets[bucket]
    if d['t'] == 0: continue
    wr = d['w']/d['t']*100; avg = sum(d['pnls'])/len(d['pnls']); cum = sum(d['pnls'])
    print(f'  {bucket:12s}: {d["t"]:>4d}笔 WR={wr:.1f}% avgPnL={avg:+.2f}% cum={cum:+.1f}%')

# ═══ Top 20 individual combos ═══
print(f'\n{"="*100}')
print(f'最佳20个组合 (按PnL排序)')
print(f'{"="*100}')
best = sorted(all_combos, key=lambda x: -x['pnl'])[:20]
for i, c in enumerate(best):
    print(f'\n{i+1}. {c["symbol"]} {c["chain"]} gap={c["gap"]}b PnL={c["pnl"]:+.2f}%')
    print(f'   第1信号: {c["start_type"]} @ {c["start_date"]} bar={c["start_bar"]} 价格={c["start_price"]:.2f}')
    print(f'   K线: O={c["start_o"]:.2f} H={c["start_h"]:.2f} L={c["start_l"]:.2f} C={c["start_c"]:.2f}')
    print(f'   第2信号: {c["zone_type"]} @ {c["zone_date"]} bar={c["zone_bar"]} 价格={c["zone_price"]:.2f} 区间=[{c["zone_low"]:.2f},{c["zone_up"]:.2f}]')
    print(f'   K线: O={c["zone_o"]:.2f} H={c["zone_h"]:.2f} L={c["zone_l"]:.2f} C={c["zone_c"]:.2f}')
    print(f'   入场: {c["entry_date"]} 价格={c["entry_price"]:.2f} SL={c["sl"]:.2f}({c["sl_pct"]}%) TP={c["tp"]:.2f}({c["tp_pct"]}%) RR={c["rr"]}')
    print(f'   退出: {c["exit_date"]} 价格={c["exit_price"]:.2f} {c["exit_method"]} 持仓={c["hold_bars"]}b')

# Save
output = {
    'meta': {'version':'all-combos','window_days':WINDOW_DAYS,'total':len(all_combos),'elapsed':round(elapsed,1)},
    'stats': {chain: {'count':s['count'],'wr':round(s['wins']/s['count']*100,1) if s['count'] else 0,
                      'avg_pnl':round(sum(s['pnls'])/len(s['pnls']),2) if s['pnls'] else 0}
              for chain,s in stats.items()},
    'combos': all_combos,
}
json.dump(output, open(OUT/'all_combos_detail.json','w'), ensure_ascii=False)
print(f'\n保存: {OUT/"all_combos_detail.json"} ({len(all_combos)}条)')
