#!/usr/bin/env python3
"""
V5 时间范围子集回测 — L1 OB独立 + L2 ALL→ZONE + RR≥1
时段: Before22, 2022-2023, 2024-2025, 2026_Current
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

# V5 signal matrix
LIQ_LONG = ['Sweep_SSL', 'EQL']
STRUCT_LONG = ['CHOCH_Bull','BOS_Bull','MSS_Bull']
ALL_START = LIQ_LONG + STRUCT_LONG
MIN_GAP = 1; MAX_GAP = 10; TP_CAP = 1.05

RANGES = {
    'Before22':     ('00000000','20211231'),
    '2022-2023':    ('20220101','20231231'),
    '2024-2025':    ('20240101','20251231'),
    '2026':         ('20260101','99999999'),
}

def weekly_smc_trend(weekly):
    if len(weekly) < 20: return 'neutral', {}
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb=tc.get('CHOCH_Bull',0); cbr=tc.get('CHOCH_Bear',0)
    bb=tc.get('BOS_Bull',0); bbr=tc.get('BOS_Bear',0)
    last_ch = [s for s in sigs if 'CHOCH' in s.type]
    last_dir = 'bull' if last_ch and 'Bull' in last_ch[-1].type else ('bear' if last_ch and 'Bear' in last_ch[-1].type else None)
    if last_dir=='bull' and cb+bb>=cbr+bbr: return 'bullish', tc
    if last_dir=='bear' and cbr+bbr>cb+bb: return 'bearish', tc
    if cb+bb>(cbr+bbr)*1.5: return 'bullish', tc
    if cbr+bbr>(cb+bb)*1.5: return 'bearish', tc
    return 'neutral', tc

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        c = daily[i:i+5]
        if len(c) >= 3:
            w.append({'o':c[0]['o'],'h':max(b['h'] for b in c),'l':min(b['l'] for b in c),'c':c[-1]['c']})
    return w

def detect_fvg_fills(daily):
    """Calculate FVG回补率 for market state"""
    sigs, st, _, _ = detect_all_signals_v20(daily)
    fvg_sigs = [s for s in sigs if 'FVG' in s.type]
    if len(fvg_sigs) < 10: return 0, 0
    filled = 0
    for fvg in fvg_sigs:
        gap_high = fvg.upper if hasattr(fvg,'upper') else (fvg.lower+2 if hasattr(fvg,'lower') else 10)
        gap_low = fvg.lower if hasattr(fvg,'lower') else 0
        for k in range(fvg.idx+2, min(fvg.idx+22, len(daily))):
            c = daily[k]['c']
            if gap_low < c < gap_high: filled += 1; break
    return filled, len(fvg_sigs)

def market_state(fill_count, fvg_count):
    if fvg_count == 0: return 'transition'
    rate = fill_count/fvg_count
    if rate >= 0.6: return 'mean_reversion'
    if rate <= 0.4: return 'expansion'
    return 'transition'

def gather_v5_candidates(daily, sigs, sbb, w_trend, swings_dict):
    """V5: L1 OB_Bull always + L2 ALL→ZONE in MeanReversion"""
    n = len(daily)
    fill_c, fvg_c = detect_fvg_fills(daily)
    ms = market_state(fill_c, fvg_c)
    candidates = []
    
    for i in sorted(sbb.keys()):
        sigs_i = sbb[i]
        
        # L1: OB_Bull independent
        ob_sigs = [s for s in sigs_i if s.type == 'OB_Bull']
        if ob_sigs:
            entry_bar = i + 1
            if entry_bar >= n - 2: continue
            ep = daily[entry_bar]['o']
            if ep == 0: continue
            
            tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
            sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
            if tp is None: tp = ep * TP_CAP
            if tp > ep * TP_CAP: tp = ep * TP_CAP
            if sl is None: sl = ep * 0.97
            
            tpd = abs(tp-ep)/ep*100; sld = abs(sl-ep)/ep*100
            if sld > 0 and tpd/sld >= 1.0:
                candidates.append({
                    'tier': 'L1', 'signal': 'OB_Bull',
                    'ep': ep, 'sl': sl, 'tp': tp, 'entry_bar': entry_bar,
                    'gap': 0, 'state': ms, 'trend': w_trend,
                })
        
        # L2: ALL→ZONE (only in MeanReversion)
        l2_enabled = (ms == 'mean_reversion')
        if l2_enabled:
            start_sigs = [s for s in sigs_i if s.type in ALL_START]
            for start_s in start_sigs:
                best_zone = None; best_gap = 99
                for j in range(i+MIN_GAP, min(i+MAX_GAP+1, n)):
                    if j not in sbb: continue
                    zone_candidates = [s for s in sbb[j] if s.type in ['OB_Bull','FVG_Bull']]
                    if not zone_candidates: continue
                    zone_candidates.sort(key=lambda x: 0 if x.type=='OB_Bull' else 1)
                    zone = zone_candidates[0]
                    gap = j - i
                    if gap < best_gap:
                        best_gap = gap; best_zone = (zone, j)
                    break
                if not best_zone: continue
                zone, j = best_zone
                entry_bar = j + 1
                if entry_bar >= n - 2: continue
                ep = daily[entry_bar]['o']
                if ep == 0: continue
                
                tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
                sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
                if tp is None: tp = ep * TP_CAP
                if tp > ep * TP_CAP: tp = ep * TP_CAP
                if sl is None: sl = ep * 0.97
                
                tpd = abs(tp-ep)/ep*100; sld = abs(sl-ep)/ep*100
                if sld == 0 or tpd/sld < 1.0: continue
                
                candidates.append({
                    'tier': 'L2', 'signal': f'{start_s.type}→{zone.type}',
                    'ep': ep, 'sl': sl, 'tp': tp, 'entry_bar': entry_bar,
                    'gap': gap, 'state': ms, 'trend': w_trend,
                })
    
    # Dedup by entry_bar
    candidates.sort(key=lambda x: (x['entry_bar'], 0 if x['tier']=='L1' else 1))
    seen = set(); deduped = []
    for c in candidates:
        if c['entry_bar'] in seen: continue
        seen.add(c['entry_bar'])
        deduped.append(c)
    return deduped

def run_trades(ohlcv, candidates, signals, swings_dict, date_range=None):
    n = len(ohlcv)
    trades = []
    for c in candidates:
        entry_bar = c['entry_bar']
        if entry_bar >= n - 2: continue
        
        if date_range:
            entry_date = str(ohlcv[entry_bar].get('t', ohlcv[entry_bar].get('date','')))[:8]
            if entry_date < date_range[0] or entry_date > date_range[1]:
                continue
        
        ep = c['ep']; sl = c['sl']; tp = c['tp']
        exit_idx=-1; exit_price=0; exit_method='eod'
        for k in range(entry_bar+1, n):
            bk = ohlcv[k]
            if bk['h'] >= tp: exit_idx=k; exit_price=tp; exit_method='tp_hit'; break
            if bk['l'] <= sl: exit_idx=k; exit_price=sl; exit_method='sl_hit'; break
        if exit_idx<0: exit_idx=n-1; exit_price=ohlcv[exit_idx]['c']
        if exit_idx<=entry_bar: continue
        
        pnl=(exit_price-ep)/ep*100
        trades.append({
            'pnl':pnl, 'exit_method':exit_method, 'hold':exit_idx-entry_bar,
            'signal':c['signal'], 'tier':c['tier'], 'state':c['state'],
            'entry_date':str(ohlcv[entry_bar].get('t',''))[:8], 'trend':c['trend'],
        })
    return trades

def summary(trades, label=''):
    if not trades: return {'label':label,'n':0,'wr':0,'avg_pnl':0,'cum_pnl':0,'pf':0,'tp':0,'sl':0,'hold':0}
    n=len(trades); wins=sum(1 for t in trades if t['pnl']>0)
    cum=sum(t['pnl'] for t in trades); avg_pnl=cum/n
    win_pnls=[t['pnl'] for t in trades if t['pnl']>0]
    loss_pnls=[abs(t['pnl']) for t in trades if t['pnl']<=0]
    tp_hits=sum(1 for t in trades if t['exit_method']=='tp_hit')
    sl_hits=sum(1 for t in trades if t['exit_method']=='sl_hit')
    avg_hold=sum(t['hold'] for t in trades)/n
    pf=sum(win_pnls)/sum(loss_pnls) if loss_pnls else 999
    return {'label':label,'n':n,'wr':round(wins/n*100,1),'cum_pnl':round(cum,1),
            'avg_pnl':round(avg_pnl,2),'pf':round(pf,1),'tp':round(tp_hits/n*100,1),
            'sl':round(sl_hits/n*100,1),'hold':round(avg_hold,1)}

# ═══ MAIN ═══
t0 = time.time()
daily_files = sorted(KLINE.glob('*_daily_300.json'))

range_trades = defaultdict(list)
range_stocks = defaultdict(set)
range_l1 = defaultdict(list)
range_l2 = defaultdict(list)
range_by_state = defaultdict(lambda: defaultdict(list))

processed = 0
for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    weekly = None
    if weekly_path.exists():
        try: weekly = json.loads(weekly_path.read_bytes())
        except: pass
    if weekly is None or len(weekly) < 20:
        weekly = daily_to_weekly(daily)
    w_trend, _ = weekly_smc_trend(weekly)
    if w_trend != 'bullish': continue
    
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    sbb = defaultdict(list)
    for s in sigs: sbb[s.idx].append(s)
    
    candidates = gather_v5_candidates(daily, sigs, sbb, w_trend, swings_dict)
    if not candidates: continue
    
    processed += 1
    for rname, dr in RANGES.items():
        trades = run_trades(daily, candidates, sigs, swings_dict, dr)
        if trades:
            range_trades[rname].extend(trades)
            range_stocks[rname].add(sym)
            for t in trades:
                if t['tier'] == 'L1': range_l1[rname].append(t)
                else: range_l2[rname].append(t)
                range_by_state[rname][t['state']].append(t)
    
    if processed % 500 == 0:
        print(f"  [{processed} bullish stocks] {time.time()-t0:.0f}s")
        for rn in RANGES:
            tr = range_trades.get(rn, [])
            if tr: print(f"    {rn}: {len(tr)} trades")

elapsed = time.time() - t0

# ═══ REPORT ═══
print(f"\n{'='*100}")
print(f"  V5 时间范围回测 — {processed} bullish stocks — {elapsed:.0f}s")
print(f"{'='*100}")

print(f"  {'时段':<16s} {'股票':>5s} {'笔数':>6s} {'WR':>6s} {'PnLavg':>7s} {'PnLsum':>8s} {'PF':>6s} {'TP%':>5s} {'SL%':>5s} {'Hold':>5s}")
print(f"  {'-'*85}")

for rname in RANGES.keys():
    s = summary(range_trades.get(rname, []), rname)
    print(f"  {rname:<16s} {len(range_stocks.get(rname,set())):>5d} {s['n']:>6d} {s['wr']:>5.1f}% {s['avg_pnl']:>+6.2f}% {s['cum_pnl']:>+7.1f}% {s['pf']:>5.1f} {s['tp']:>4.1f}% {s['sl']:>4.1f}% {s['hold']:>4.1f}b")

# L1 vs L2 breakdown
print(f"\n{'='*100}")
print(f"  L1 (OB_Bull) vs L2 (ALL→ZONE)")
print(f"{'='*100}")
for rname in RANGES.keys():
    s1 = summary(range_l1.get(rname, []), 'L1')
    s2 = summary(range_l2.get(rname, []), 'L2')
    print(f"  {rname}:")
    print(f"    L1 OB:      {s1['n']:>5d}笔 WR={s1['wr']}% PnL={s1['avg_pnl']:+.2f}% Cum={s1['cum_pnl']:+.1f}%")
    print(f"    L2 COMBO:   {s2['n']:>5d}笔 WR={s2['wr']}% PnL={s2['avg_pnl']:+.2f}% Cum={s2['cum_pnl']:+.1f}%")

# By market state
print(f"\n{'='*100}")
print(f"  By Market State (within each range)")
print(f"{'='*100}")
for rname in RANGES.keys():
    print(f"  {rname}:")
    for state in ['mean_reversion','transition','expansion']:
        st_trades = range_by_state[rname].get(state, [])
        s = summary(st_trades, state)
        if s['n'] > 0:
            print(f"    {state:20s} {s['n']:>5d}笔 WR={s['wr']}% PnL={s['avg_pnl']:+.2f}%")

# L2 signal type breakdown
print(f"\n{'='*100}")
print(f"  L2 Signal Types")
print(f"{'='*100}")
l2_all = []
for rn in RANGES: l2_all.extend(range_l2.get(rn, []))
l2_by_sig = defaultdict(list)
for t in l2_all: l2_by_sig[t['signal']].append(t)
for sig, trades in sorted(l2_by_sig.items(), key=lambda x: -len(x[1])):
    s = summary(trades, sig)
    print(f"  {sig:<30s} {s['n']:>5d}笔 WR={s['wr']}% PnL={s['avg_pnl']:+.2f}% Cum={s['cum_pnl']:+.1f}%")

# Save
output = {
    'meta': {'version':'V5 timerange','date':time.strftime('%Y-%m-%d'),'elapsed':round(elapsed),'stocks':processed},
    'ranges': {rname: {'stocks': len(range_stocks.get(rname,set())), **summary(range_trades.get(rname,[]), rname)}
               for rname in RANGES},
    'l1': {rname: summary(range_l1.get(rname,[]), rname) for rname in RANGES},
    'l2': {rname: summary(range_l2.get(rname,[]), rname) for rname in RANGES},
    'l2_signals': {sig: summary(trades, sig) for sig, trades in l2_by_sig.items()},
}
json.dump(output, open(OUT/'backtest_timerange_v5.json','w'), ensure_ascii=False, indent=2)
print(f"\n  保存: {OUT/'backtest_timerange_v5.json'}")
