#!/usr/bin/env python3
"""
SMC 时间范围子集回测 — 分时段验证L→D序列稳定性
时段: 2022-2023(熊市), 2024-2025(牛市)
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

CATEGORIES = {
    'LIQ_LONG':  ['Sweep_SSL', 'EQL'],
    'ZONE_LONG': ['OB_Bull', 'FVG_Bull'],
    'STRUCT_LONG': ['CHOCH_Bull','BOS_Bull','MSS_Bull'],
}
PATTERNS = {
    'L→D':  (['LIQ_LONG','ZONE_LONG'],[25]),
    'S→D':  (['STRUCT_LONG','ZONE_LONG'],[20]),
    'L→S→D':(['LIQ_LONG','STRUCT_LONG','ZONE_LONG'],[30,15]),
}
LOOKAHEAD = 5; TP_CAP = 1.05

# ═══ Time ranges ═══
RANGES = {
    '2022-2023_熊市':  ('20220101','20231231'),
    '2024-2025_牛市':  ('20240101','20251231'),
    '2021_Before':     ('00000000','20211231'),
    '2026_Current':    ('20260101','99999999'),
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

def detect_LD_sequences(signals):
    sbb = defaultdict(list)
    for s in signals: sbb[s.idx].append(s)
    seqs = []
    for pn, (stages, gaps) in PATTERNS.items():
        ss = [CATEGORIES[s] for s in stages]
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb] if s.type in ss[0]]:
                chain = [sig]; c = sig.idx; ok = True
                for si in range(1, len(stages)):
                    gap = gaps[si-1] if si-1 < len(gaps) else 25
                    fnd = False
                    for bi in range(c+1, c+gap+1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in ss[si] and cand not in chain:
                                    chain.append(cand); c = bi; fnd = True; break
                        if fnd: break
                    if not fnd: ok = False; break
                if ok and len(chain) == len(stages):
                    seqs.append({'p':pn,'bar':chain[-1].idx,'zone_type':chain[-1].type})
    seen=set(); u=[]
    for s in sorted(seqs,key=lambda x:x['bar']):
        if s['bar'] not in seen: seen.add(s['bar']);u.append(s)
    return u

def run_trades(ohlcv, sequences, signals, swings_dict, date_range=None):
    """T+1 backtest, filtered by date range"""
    n = len(ohlcv)
    trades = []
    used = set()
    
    for seq in sequences:
        bar = seq['bar']
        entry_bar = bar + 1
        if entry_bar >= n-2 or entry_bar in used: continue
        
        # Date range filter
        if date_range:
            entry_date = str(ohlcv[entry_bar].get('t', ohlcv[entry_bar].get('date', '')))[:8]
            if entry_date < date_range[0] or entry_date > date_range[1]:
                continue
        
        entry_price = ohlcv[entry_bar]['o']
        if entry_price == 0: continue
        
        tp_price, tp_src, _ = find_tps(entry_price, signals, swings_dict, ohlcv)
        sl_price, sl_src, _ = find_sls(entry_price, signals, swings_dict, ohlcv)
        max_tp = entry_price * TP_CAP
        if tp_price > max_tp: tp_price = max_tp
        
        tp_dist = abs(tp_price-entry_price)/entry_price*100
        sl_dist = abs(sl_price-entry_price)/entry_price*100
        if sl_dist == 0 or tp_dist/sl_dist < 1.0: continue
        
        exit_idx=-1; exit_price=0; exit_method='eod'
        for i in range(entry_bar+1, n):
            bar_i = ohlcv[i]
            if bar_i['h'] >= tp_price: exit_idx=i; exit_price=tp_price; exit_method='tp_hit'; break
            if bar_i['l'] <= sl_price: exit_idx=i; exit_price=sl_price; exit_method='sl_hit'; break
        if exit_idx<0: exit_idx=n-1; exit_price=ohlcv[exit_idx]['c']
        if exit_idx<=entry_bar: continue
        
        pnl=(exit_price-entry_price)/entry_price*100
        trades.append({'pnl':pnl,'exit_method':exit_method,'hold':exit_idx-entry_bar,
                       'pattern':seq['p'],'entry_date':str(ohlcv[entry_bar].get('t',''))[:8]})
        used.add(exit_idx)
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
range_patterns = defaultdict(lambda: defaultdict(list))

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Weekly trend
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    weekly = None
    if weekly_path.exists():
        try: weekly = json.loads(weekly_path.read_bytes())
        except: pass
    if weekly is None or len(weekly) < 20:
        weekly = daily_to_weekly(daily)
    w_trend, _ = weekly_smc_trend(weekly)
    if w_trend != 'bullish': continue
    
    # Daily signals + sequences
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    sequences = detect_LD_sequences(sigs)
    if not sequences: continue
    
    # Run per range
    for rname, dr in RANGES.items():
        trades = run_trades(daily, sequences, sigs, swings_dict, dr)
        if trades:
            range_trades[rname].extend(trades)
            range_stocks[rname].add(sym)
            for t in trades:
                range_patterns[rname][t['pattern']].append(t['pnl'])
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s")

elapsed = time.time()-t0

# ═══ REPORT ═══
print(f"\n{'='*90}")
print(f"  SMC 时间范围子集回测 — bullish + L→D/S→D序列 — {elapsed:.0f}s")
print(f"{'='*90}")

print(f"  {'时段':<20s} {'股票':>5s} {'笔数':>6s} {'WR':>6s} {'PnL':>7s} {'PF':>6s} {'TP%':>5s} {'SL%':>5s} {'Hold':>5s}")
print(f"  {'-'*75}")

for rname in RANGES.keys():
    s = summary(range_trades[rname], rname)
    print(f"  {rname:<20s} {len(range_stocks[rname]):>5d} {s['n']:>6d} {s['wr']:>5.1f}% {s['avg_pnl']:>+6.2f}% {s['pf']:>5.1f} {s['tp']:>4.1f}% {s['sl']:>4.1f}% {s['hold']:>4.1f}b")

# Pattern breakdown per range
print(f"\n{'='*90}")
print(f"  按模式 × 时段")
print(f"{'='*90}")
for rname in ['2022-2023_熊市','2024-2025_牛市']:
    print(f"\n  {rname}:")
    for pat in ['L→D','S→D','L→S→D']:
        pnls = range_patterns[rname].get(pat, [])
        if not pnls: continue
        wins = sum(1 for p in pnls if p > 0)
        wr = wins/len(pnls)*100
        avg = sum(pnls)/len(pnls)
        print(f"    {pat:8s} {len(pnls):>5d}笔 WR={wr:.1f}% PnL={avg:+.2f}%")

# Save
output = {
    'meta': {'version':'timerange v1.0','date':time.strftime('%Y-%m-%d'),'elapsed':round(elapsed)},
    'ranges': {rname: {'stocks': len(range_stocks[rname]), **summary(range_trades[rname], rname)}
               for rname in RANGES.keys()},
    'patterns': {rname: {pat: {'n': len(pnls), 'wr': round(sum(1 for p in pnls if p>0)/len(pnls)*100,1) if pnls else 0,
                                'avg_pnl': round(sum(pnls)/len(pnls),2) if pnls else 0}
                          for pat, pnls in pats.items()}
                 for rname, pats in range_patterns.items()},
}
json.dump(output, open(OUT/'backtest_timerange.json','w'), ensure_ascii=False)
print(f"\n  保存: {OUT/'backtest_timerange.json'}")
