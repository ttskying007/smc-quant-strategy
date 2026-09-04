#!/usr/bin/env python3
"""
SMC V10.0 — 失败模式分析 + 滚动窗口学习
========================================
1. 失败分析: SL击穿交易的信号特征(zone类型/模式/位置/波动率)
2. 滚动窗口: 切分数据为3段(full/mid/recent), 每段独立找最优模式
3. 模式漂移: 检测最佳模式是否随时间变化
4. 结论: 哪些股票的模式稳定,哪些需要动态切换
"""
import json, time
from pathlib import Path
from collections import defaultdict
import sys

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, _calc_atr

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

TARGET = 2.0; LOOKAHEAD = 5; MAX_GAP = 25
MIN_TRADES = 3

CATEGORIES = {
    'CTX_LONG':  ['BOS_Bull', 'CHOCH_Bull', 'MSS_Bull'],
    'LIQ_LONG':  ['Sweep_SSL', 'EQL'],
    'ZONE_LONG': ['OB_Bull', 'FVG_Bull'],
}
PATTERNS = {
    'LIQ→ZONE':     (['LIQ_LONG', 'ZONE_LONG'], [25]),
    'CTX→ZONE':     (['CTX_LONG', 'ZONE_LONG'], [20]),
    'ZONE_ONLY':    (['ZONE_LONG'], []),
    'LIQ→CTX→ZONE': (['LIQ_LONG', 'CTX_LONG', 'ZONE_LONG'], [30, 15]),
}

def daily_to_weekly(d):
    w=[]
    for i in range(0,len(d),5):
        c=d[i:i+5]
        if len(c)>=3: w.append({'o':c[0]['o'],'h':max(x['h'] for x in c),'l':min(x['l'] for x in c),'c':c[-1]['c']})
    return w

def weekly_trend(w):
    if len(w)<20: return 'neutral'
    sigs,st,_,_=detect_all_signals_v20(w)
    tc=st['type_counts']
    cb=tc.get('CHOCH_Bull',0);cbr=tc.get('CHOCH_Bear',0)
    bb=tc.get('BOS_Bull',0);bbr=tc.get('BOS_Bear',0)
    last=[s for s in sigs if 'CHOCH' in s.type]
    ld='bull' if last and 'Bull' in last[-1].type else ('bear' if last and 'Bear' in last[-1].type else None)
    if ld=='bull' and cb+bb>=cbr+bbr: return 'bullish'
    if ld=='bear' and cbr+bbr>cb+bb: return 'bearish'
    if cb+bb>(cbr+bbr)*1.5: return 'bullish'
    if cbr+bbr>(cb+bb)*1.5: return 'bearish'
    return 'neutral'

def detect_sequences(signals):
    sbb = defaultdict(list)
    for s in signals: sbb[s.idx].append(s)
    all_seqs = []
    for pname, (stages, gaps) in PATTERNS.items():
        stage_sigs = [CATEGORIES[st] for st in stages]
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb] if s.type in stage_sigs[0]]:
                chain=[sig];c=sig.idx;ok=True
                for si in range(1,len(stages)):
                    gap=gaps[si-1] if si-1<len(gaps) else MAX_GAP
                    fnd=False
                    for bi in range(c+1,c+gap+1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in stage_sigs[si] and cand not in chain:
                                    chain.append(cand);c=bi;fnd=True;break
                        if fnd:break
                    if not fnd:ok=False;break
                if ok and len(chain)==len(stages):
                    all_seqs.append({'pattern':pname,'seq_bar':chain[-1].idx,
                                     'zone_type':chain[-1].type,
                                     'zone_low':chain[-1].lower,'zone_high':chain[-1].upper})
    unique=[]
    for pn in PATTERNS:
        seen=set()
        for s in sorted([x for x in all_seqs if x['pattern']==pn],key=lambda x:x['seq_bar']):
            if s['seq_bar'] not in seen:seen.add(s['seq_bar']);unique.append(s)
    return unique

def backtest_window(ohlcv, seqs, window_start, window_end):
    """Backtest within a specific bar range"""
    n = len(ohlcv)
    trades = []
    for sq in seqs:
        eb = sq['seq_bar']
        if eb < window_start or eb >= window_end: continue
        if eb+1 >= n or eb+LOOKAHEAD+1 >= n: continue
        ep = ohlcv[eb+1]['o']
        sl = sq['zone_low'] * 0.995 if sq['zone_low'] > 0 else ep * 0.97
        tp = ep * 1.03
        exit_px=ep;reason='time_stop'
        for bi in range(eb+2, min(eb+LOOKAHEAD+1, n-1)+1):
            if ohlcv[bi]['l']<=sl:exit_px=sl;reason='sl_hit';break
            if ohlcv[bi]['h']>=tp:exit_px=tp;reason='tp_hit';break
        else: exit_px=ohlcv[min(eb+LOOKAHEAD,n-1)]['c']
        pnl=(exit_px-ep)/ep*100
        trades.append({
            'pattern':sq['pattern'],'zone_type':sq['zone_type'],
            'entry_bar':eb+1,'zone_low':sq['zone_low'],
            'pnl_pct':round(pnl,2),'won':pnl>0,'exit_reason':reason,
        })
    return trades


# ═══ MAIN ═══
print("V10.0: Failure Analysis + Rolling Window Learning")
daily_files = sorted(KLINE.glob('*_daily_300.json'))
t0 = time.time()

# Global accumulators
failure_stats = defaultdict(lambda: {'total':0,'fail':0,'sl_hit':0,'tp_hit':0,'time_stop':0,'pnls':[]})
rolling_drift = []  # stock-level: did best pattern change?
stock_windows = {}  # per-stock, per-window best pattern

for fi, df in enumerate(daily_files):
    name = df.stem.replace('_daily_300','')
    parts=name.rsplit('_',1)
    sym=f'{parts[0]}.{parts[1]}' if len(parts)==2 else name
    try:
        daily=json.loads(df.read_bytes())
        if len(daily)<50:continue
    except:continue
    
    try:
        sigs,_,_,_=detect_all_signals_v20(daily)
        seqs=detect_sequences(sigs)
    except:continue
    if not seqs:continue
    
    n=len(daily)
    atr_pct=_calc_atr(daily,14)
    avg_p=sum(b['c'] for b in daily[-50:])/min(50,n)
    if avg_p>0:atr_pct=atr_pct/avg_p
    
    # ── Rolling windows: 3 time segments ──
    windows = {
        'old':   (0, max(0, n-150)),       # oldest 2/3
        'mid':   (max(0, n-150), max(0, n-50)),  # middle
        'recent':(max(0, n-50), n),         # most recent
    }
    
    window_best = {}
    for wn, (wstart, wend) in windows.items():
        if wend - wstart < 30: continue
        all_trades = backtest_window(daily, seqs, wstart, wend)
        if len(all_trades) < MIN_TRADES: continue
        
        # Per-pattern stats
        pat_stats = defaultdict(lambda: {'hits':0,'total':0,'fails':0})
        for t in all_trades:
            p=t['pattern']
            pat_stats[p]['total']+=1
            if t['won']:pat_stats[p]['hits']+=1
            else:
                pat_stats[p]['fails']+=1
                # Failure analysis
                key = f"{p}|{t['zone_type']}"
                failure_stats[key]['total']+=1
                failure_stats[key]['fail']+=1
                failure_stats[key][t['exit_reason']]+=1
                failure_stats[key]['pnls'].append(t['pnl_pct'])
        
        # Best pattern for this window
        best_p=None;best_wr=0
        for p,s in pat_stats.items():
            if s['total']<MIN_TRADES:continue
            wr=s['hits']/s['total']
            if wr>best_wr:best_wr=wr;best_p=p
        if best_p:
            window_best[wn]={'pattern':best_p,'wr':round(best_wr,3),'total':sum(s['total'] for s in pat_stats.values())}
    
    if len(window_best)>=2:
        # Check for pattern drift
        patterns=[window_best[w]['pattern'] for w in ['old','mid','recent'] if w in window_best]
        if len(set(patterns))>1:
            rolling_drift.append({
                'symbol':sym,
                'old':window_best.get('old',{}).get('pattern','?'),
                'mid':window_best.get('mid',{}).get('pattern','?'),
                'recent':window_best.get('recent',{}).get('pattern','?'),
                'drift':f"{patterns[0]}→{patterns[-1]}",
            })
        stock_windows[sym]=window_best
    
    if (fi+1)%1000==0:
        r=time.time()-t0
        print(f"  [{fi+1}/{len(daily_files)}] {r:.0f}s drift={len(rolling_drift)}")

elapsed=time.time()-t0

# ═══ REPORT ═══
print(f"\n{'='*70}")
print(f"  V10.0 失败分析+滚动窗口 ({elapsed:.0f}s)")
print(f"  扫描:{len(daily_files)} → 窗口数据:{len(stock_windows)}只")
print(f"  模式漂移:{len(rolling_drift)}只 ({len(rolling_drift)/max(len(stock_windows),1)*100:.0f}%)")
print(f"{'='*70}")

# ── Failure Analysis ──
print(f"\n  【失败模式分析 — 什么信号在什么条件下被SL击穿】")
ranked_fails = sorted(failure_stats.items(), key=lambda x:-x[1]['fail'])
for i,(key,stats) in enumerate(ranked_fails[:15]):
    if stats['fail']<20:continue
    pattern,zone=key.split('|')
    fail_rate=stats['fail']/max(stats['total'],1)
    avg_loss=sum(stats['pnls'])/max(len(stats['pnls']),1)
    sl_pct=stats['sl_hit']/max(stats['fail'],1)
    print(f"  {i+1:2d}.{pattern:<15s}+{zone:<12s} fail={fail_rate:.0%} avg_loss={avg_loss:+.2f}% SL={sl_pct:.0%} N={stats['fail']}")

# ── Rolling Window Summary ──
print(f"\n  【滚动窗口 — 模式稳定性】")
stable_count=0;drift_count=0
drift_types=defaultdict(int)
for d in rolling_drift:
    drift_types[d['drift']]+=1
    drift_count+=1

print(f"  稳定(3窗口同模式): {len(stock_windows)-drift_count}只")
print(f"  漂移(模式变化): {drift_count}只")
print(f"\n  漂移类型:")
for dt,count in sorted(drift_types.items(),key=lambda x:-x[1])[:10]:
    print(f"    {dt}: {count}只")

# ── Window-by-window best pattern distribution ──
print(f"\n  【各窗口最优模式分布】")
for wn in ['old','mid','recent']:
    dist=defaultdict(int)
    for sym,wd in stock_windows.items():
        if wn in wd:
            dist[wd[wn]['pattern']]+=1
    print(f"  {wn}: " + ' | '.join(f"{p}:{c}" for p,c in sorted(dist.items(),key=lambda x:-x[1])))

# ── Drift sample ──
print(f"\n  【漂移样本 (前20)】")
for d in rolling_drift[:20]:
    print(f"  {d['symbol']:12s} {d['old']:>12s} → {d['mid']:>12s} → {d['recent']:>12s}")

# ═══ SAVE ═══
output={
    'meta':{'version':'10.0','date':time.strftime('%Y-%m-%d'),
            'stocks_with_windows':len(stock_windows),
            'drift_count':drift_count,
            'drift_pct':round(drift_count/max(len(stock_windows),1)*100,1)},
    'failures':[{'key':k,'pattern':k.split('|')[0],'zone':k.split('|')[1],
                 'fail':v['fail'],'total':v['total'],
                 'sl_hit':v.get('sl_hit',0),'avg_loss':round(sum(v['pnls'])/max(len(v['pnls']),1),2)}
                for k,v in sorted(failure_stats.items(),key=lambda x:-x[1]['fail'])],
    'drift':rolling_drift,
    'windows':stock_windows,
}
json.dump(output,open(OUT/'failure_rolling_v10.json','w'),ensure_ascii=False)
print(f"\n  Saved: {OUT/'failure_rolling_v10.json'}")
