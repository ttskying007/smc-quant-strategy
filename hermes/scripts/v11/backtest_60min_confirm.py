#!/usr/bin/env python3
"""
SMC 60min确认回测 — 测试60min是否提升做多WR
架构: 日线L→D序列 → 60min确认窗口 → T+1交易
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
KLINE_60 = Path('/root/.hermes/kline_cache_60min')
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
CONFIRM_WINDOW = 16   # 60min bars to check before signal (~2 days × 8 bars)
MIN_CONFIRM_BARS = 3  # minimum same-direction signals

LOOKAHEAD = 5
TP_CAP = 1.05

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
                    zone = chain[-1]
                    seqs.append({'p':pn,'bar':zone.idx,'zone_type':zone.type})
    seen=set(); u=[]
    for s in sorted(seqs,key=lambda x:x['bar']):
        if s['bar'] not in seen: seen.add(s['bar']);u.append(s)
    return u

def run_trades(ohlcv, sequences, signals, swings_dict):
    """T+1 backtest returning trades"""
    n = len(ohlcv)
    trades = []
    used = set()
    for seq in sequences:
        bar = seq['bar']
        entry_bar = bar + 1
        if entry_bar >= n-2 or entry_bar in used: continue
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
        trades.append({'pnl':pnl,'exit_method':exit_method,'hold':exit_idx-entry_bar,'pattern':seq['p']})
        used.add(exit_idx)
    return trades

def check_60min_support(daily_sig_date, daily_sig_bar, ohlcv_60min, sigs_60min):
    """Check if 60min shows supporting bull signals before daily bar"""
    if not ohlcv_60min or not sigs_60min:
        return {'supported': False, 'score': 0, 'signals': [], 'nodata': True}
    
    # Find 60min bars matching daily date
    # daily_sig_date format: 'YYYYMMDD'
    daily_date = str(daily_sig_date)[:8]
    matching_60min_indices = []
    for i, bar in enumerate(ohlcv_60min):
        bar_t = str(bar.get('t', ''))
        if bar_t[:8] == daily_date:
            matching_60min_indices.append(i)
    
    if not matching_60min_indices:
        return {'supported': False, 'score': 0, 'signals': [], 'nodata': True}
    
    # Use last matching 60min bar as reference
    ref_idx = matching_60min_indices[-1]
    window_start = max(0, ref_idx - CONFIRM_WINDOW)
    
    # Count supporting signals
    supporting = []
    score = 0
    for sig in sigs_60min:
        si = sig.idx
        if window_start <= si <= ref_idx:
            t = sig.type
            if 'Bull' in t or 'Sweep_SSL' in t or 'EQL' in t or 'BPR' in t:
                supporting.append(t)
                if 'FVG_Bull' in t: score += 3
                elif 'OB_Bull' in t: score += 2.5
                elif 'CHOCH_Bull' in t: score += 2.5
                elif 'BOS_Bull' in t: score += 2
                elif 'Sweep_SSL' in t: score += 2
                elif 'MSS_Bull' in t: score += 1.5
                elif 'EQL' in t: score += 1
                elif 'BPR' in t: score += 1
                else: score += 0.5
    
    supported = score >= 3 and len(supporting) >= MIN_CONFIRM_BARS
    
    return {
        'supported': supported,
        'score': score,
        'signal_count': len(supporting),
        'signals': supporting[:5],
        'nodata': False,
    }

def summary(trades, label=''):
    if not trades: return {'label':label,'n':0,'wr':0,'pnl':0,'pf':0,'tp':0,'sl':0,'hold':0}
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
all_trades_no60 = []
all_trades_60ok = []
stats_60 = []

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Load 60min
    m60_path = KLINE_60 / f'{sym}_60min_200.json'
    ohlcv_60min = None
    sigs_60min = []
    if m60_path.exists():
        try:
            ohlcv_60min = json.loads(m60_path.read_bytes())
            if len(ohlcv_60min) >= 20:
                sigs_60min, _, _, _ = detect_all_signals_v20(ohlcv_60min)
        except: pass
    
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
    
    # Run trades
    trades = run_trades(daily, sequences, sigs, swings_dict)
    if not trades: continue
    
    # For each trade, check 60min support
    for t in trades:
        all_trades_no60.append(t)
    
    # Also check 60min for each sequence
    for seq in sequences:
        bar = seq['bar']
        entry_bar = bar + 1
        if entry_bar >= len(daily): continue
        
        sig_date = str(daily[bar].get('t', daily[bar].get('date', '')))
        result = check_60min_support(sig_date, bar, ohlcv_60min, sigs_60min)
        stats_60.append(result)
        
        if result['supported']:
            all_trades_60ok.append({'sym': sym, 'seq_bar': bar, 'pattern': seq['p'], **result})
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s")

elapsed = time.time()-t0

# We need actual trade results for 60min-confirmed entries
# Run actual backtest only for confirmed sequences
confirmed_trades = []
for item in all_trades_60ok:
    sym = item['sym']
    seq_bar = item['seq_bar']
    try:
        daily = json.loads((KLINE / f'{sym}_daily_300.json').read_bytes())
        sigs, st, _, swings_dict = detect_all_signals_v20(daily)
        sequences = [s for s in detect_LD_sequences(sigs) if s['bar'] == seq_bar]
        if sequences:
            trades = run_trades(daily, sequences, sigs, swings_dict)
            confirmed_trades.extend(trades)
    except: pass

# ═══ REPORT ═══
print(f"\n{'='*70}")
print(f"  60min确认回测 — bullish + L→D序列 — {elapsed:.0f}s")
print(f"{'='*70}")

total_no60 = len(all_trades_no60)
with_60_data = sum(1 for s in stats_60 if not s.get('nodata'))
supported_count = sum(1 for s in stats_60 if s['supported'])
no_60_data = sum(1 for s in stats_60 if s.get('nodata'))
avg_score = sum(s['score'] for s in stats_60)/len(stats_60) if stats_60 else 0

print(f"  序列总数: {len(stats_60)}, 有60min数据: {with_60_data}, 无60min: {no_60_data}")
print(f"  确认通过: {supported_count} ({supported_count/with_60_data*100:.1f}% of available)")
print(f"  平均确认分: {avg_score:.1f}")

bs = summary(all_trades_no60, 'Baseline(全量bullish+L→D)')
cs = summary(confirmed_trades, '60min确认后')

print(f"\n  {'':20s} {'笔数':>6s} {'WR':>6s} {'PnL':>7s} {'PF':>6s} {'TP%':>5s} {'SL%':>5s} {'Hold':>5s}")
print(f"  {'-'*55}")
print(f"  {bs['label']:20s} {bs['n']:>6d} {bs['wr']:>5.1f}% {bs['avg_pnl']:>+6.2f}% {bs['pf']:>5.1f} {bs['tp']:>4.1f}% {bs['sl']:>4.1f}% {bs['hold']:>4.1f}b")
print(f"  {cs['label']:20s} {cs['n']:>6d} {cs['wr']:>5.1f}% {cs['avg_pnl']:>+6.2f}% {cs['pf']:>5.1f} {cs['tp']:>4.1f}% {cs['sl']:>4.1f}% {cs['hold']:>4.1f}b")

print(f"\n  结论: ", end='')
if cs['wr'] > bs['wr']:
    print(f"60min确认提升WR {cs['wr']-bs['wr']:+.1f}pp, PnL {cs['avg_pnl']-bs['avg_pnl']:+.2f}%")
else:
    print(f"60min确认未提升WR ({cs['wr']}% vs {bs['wr']}%)")

# Save
json.dump({
    'meta': {'version':'60min v1.0','date':time.strftime('%Y-%m-%d'),'elapsed':round(elapsed)},
    'baseline': bs, 'confirmed': cs,
    'stats_60': {'total': len(stats_60), 'with_data': with_60_data, 'supported': supported_count, 'avg_score': round(avg_score,1)},
}, open(OUT/'backtest_60min.json','w'), ensure_ascii=False)
