#!/usr/bin/env python3
"""V11.2 — 拆解: 单信号 vs 序列 × OB vs ALL × per-stock vs global"""
import json,time
from pathlib import Path
from collections import defaultdict
import sys
sys.path.insert(0,'/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20,_calc_atr
KLINE=Path('/root/.hermes/kline_cache')
OUT=Path('/root/.hermes/smc_opt_v21')
TARGET=2.0;LOOKAHEAD=5;MAX_GAP=25;MIN_TRADES=3
CATEGORIES={'CTX_LONG':['BOS_Bull','CHOCH_Bull','MSS_Bull'],'LIQ_LONG':['Sweep_SSL','EQL'],'ZONE_LONG':['OB_Bull','FVG_Bull']}
PATTERNS={'LIQ→ZONE':(['LIQ_LONG','ZONE_LONG'],[25]),'CTX→ZONE':(['CTX_LONG','ZONE_LONG'],[20]),'ZONE_ONLY':(['ZONE_LONG'],[]),'LIQ→CTX→ZONE':(['LIQ_LONG','CTX_LONG','ZONE_LONG'],[30,15])}
def dw(d):
    w=[]
    for i in range(0,len(d),5):
        c=d[i:i+5]
        if len(c)>=3:w.append({'o':c[0]['o'],'h':max(x['h']for x in c),'l':min(x['l']for x in c),'c':c[-1]['c']})
    return w
def wt(w):
    if len(w)<20:return'neutral'
    sigs,st,_,_=detect_all_signals_v20(w)
    tc=st['type_counts'];cb=tc.get('CHOCH_Bull',0);cbr=tc.get('CHOCH_Bear',0)
    bb=tc.get('BOS_Bull',0);bbr=tc.get('BOS_Bear',0)
    last=[s for s in sigs if'CHOCH'in s.type]
    ld='bull'if last and'Bull'in last[-1].type else('bear'if last and'Bear'in last[-1].type else None)
    if ld=='bull'and cb+bb>=cbr+bbr:return'bullish'
    if ld=='bear'and cbr+bbr>cb+bb:return'bearish'
    if cb+bb>(cbr+bbr)*1.5:return'bullish'
    if cbr+bbr>(cb+bb)*1.5:return'bearish'
    return'neutral'
def ds(signals):
    sbb=defaultdict(list)
    for s in signals:sbb[s.idx].append(s)
    all_s=[]
    for pn,(stages,gaps)in PATTERNS.items():
        ss=[CATEGORIES[st]for st in stages]
        for sb in sorted(sbb):
            for sig in[s for s in sbb[sb]if s.type in ss[0]]:
                chain=[sig];c=sig.idx;ok=True
                for si in range(1,len(stages)):
                    gap=gaps[si-1]if si-1<len(gaps)else MAX_GAP;fnd=False
                    for bi in range(c+1,c+gap+1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in ss[si]and cand not in chain:chain.append(cand);c=bi;fnd=True;break
                        if fnd:break
                    if not fnd:ok=False;break
                if ok and len(chain)==len(stages):all_s.append({'pattern':pn,'seq_bar':chain[-1].idx,'zone_type':chain[-1].type,'zone_low':chain[-1].lower})
    unique=[]
    for pn in PATTERNS:
        seen=set()
        for s in sorted([x for x in all_s if x['pattern']==pn],key=lambda x:x['seq_bar']):
            if s['seq_bar']not in seen:seen.add(s['seq_bar']);unique.append(s)
    return unique
def bt(ohlcv,seqs):
    n=len(ohlcv);trades=[]
    for sq in seqs:
        eb=sq['seq_bar']
        if eb+1>=n or eb+LOOKAHEAD+1>=n:continue
        ep=ohlcv[eb+1]['o'];sl=sq['zone_low']*0.995 if sq['zone_low']>0 else ep*0.97;tp=ep*1.03
        exit_px=ep;reason='time_stop'
        for bi in range(eb+2,min(eb+LOOKAHEAD+1,n-1)+1):
            if ohlcv[bi]['l']<=sl:exit_px=sl;reason='sl_hit';break
            if ohlcv[bi]['h']>=tp:exit_px=tp;reason='tp_hit';break
        else:exit_px=ohlcv[min(eb+LOOKAHEAD,n-1)]['c']
        pnl=(exit_px-ep)/ep*100
        trades.append({'won':pnl>0,'pnl_pct':round(pnl,2),'exit_reason':reason,'zone_type':sq['zone_type'],'pattern':sq['pattern']})
    return trades

print("V11.2: 拆解单信号vs序列×OBvsALL×per-stock vs global")
dfs=sorted(KLINE.glob('*_daily_300.json'))
t0=time.time()
# 4 dimensions: ALL vs OB-only × ZONE_ONLY vs ALL_PATTERNS × global vs per-stock
results={'global_all_zone':[],'global_all_allpat':[],'global_ob_zone':[],'global_ob_allpat':[],
         'perstock_all_zone':[],'perstock_all_allpat':[],'perstock_ob_zone':[],'perstock_ob_allpat':[]}
for fi,df in enumerate(dfs):
    name=df.stem.replace('_daily_300','');parts=name.rsplit('_',1)
    sym=f'{parts[0]}.{parts[1]}'if len(parts)==2 else name
    try:
        daily=json.loads(df.read_bytes());n=len(daily)
        if n<50:continue
    except:continue
    try:
        sigs,_,_,_=detect_all_signals_v20(daily);seqs=ds(sigs)
    except:continue
    if not seqs:continue
    seqs_by_pat=defaultdict(list)
    for sq in seqs:seqs_by_pat[sq['pattern']].append(sq)
    zone_seqs=seqs_by_pat.get('ZONE_ONLY',[])
    allpat_seqs=seqs
    # Per-stock best pattern selection (ALL zones)
    best_pat='ZONE_ONLY';best_wr=0
    for pn,pseqs in seqs_by_pat.items():
        if len(pseqs)<MIN_TRADES:continue
        t=bt(daily,pseqs)
        if t:
            wr=sum(1 for x in t if x['won'])/len(t)
            if wr>best_wr:best_wr=wr;best_pat=pn
    best_seqs=seqs_by_pat.get(best_pat,seqs)
    # 8 variants
    for label,seqs_in,zone_filter in[
        ('global_all_zone',zone_seqs,None),
        ('global_all_allpat',allpat_seqs,None),
        ('global_ob_zone',zone_seqs,'OB_Bull'),
        ('global_ob_allpat',allpat_seqs,'OB_Bull'),
        ('perstock_all_zone',[s for s in zone_seqs if s['pattern']==best_pat],None),
        ('perstock_all_allpat',best_seqs,None),
        ('perstock_ob_zone',[s for s in zone_seqs if s['pattern']==best_pat and s['zone_type']=='OB_Bull'],None),
        ('perstock_ob_allpat',[s for s in best_seqs if s['zone_type']=='OB_Bull'],None),
    ]:
        if zone_filter:
            seqs_in=[s for s in seqs_in if s['zone_type']==zone_filter]
        if not seqs_in:continue
        t=bt(daily,seqs_in)
        for x in t:x['symbol']=sym
        results[label].extend(t)
    if (fi+1)%1000==0:print(f"  [{fi+1}/{len(dfs)}] {time.time()-t0:.0f}s")

elapsed=time.time()-t0
print(f"\n{'='*80}")
print(f"  V11.2 拆解对比 ({elapsed:.0f}s)")
print(f"{'='*80}")
print(f"  {'策略':<30s} {'WR':>7s} {'PnL':>8s} {'Trades':>7s} {'TP率':>6s}")
print(f"  {'-'*60}")
labels_map={
    'global_all_zone':'Global + ZONE_ONLY + ALL',
    'global_all_allpat':'Global + ALL_PATTERNS + ALL',
    'global_ob_zone':'Global + ZONE_ONLY + OB_only',
    'global_ob_allpat':'Global + ALL_PATTERNS + OB_only',
    'perstock_all_zone':'PerStock + ZONE_ONLY + ALL',
    'perstock_all_allpat':'PerStock + ALL_PATTERNS + ALL',
    'perstock_ob_zone':'PerStock + ZONE_ONLY + OB_only',
    'perstock_ob_allpat':'PerStock + ALL_PATTERNS + OB_only',
}
for key,label in sorted(labels_map.items()):
    t=results[key]
    if not t:continue
    wr=sum(1 for x in t if x['won'])/len(t);pnl=sum(x['pnl_pct']for x in t)/len(t)
    tp=sum(1 for x in t if x['exit_reason']=='tp_hit')/len(t)
    print(f"  {label:<30s} {wr:>6.1%} {pnl:>+7.2f}% {len(t):>7d} {tp:>5.0%}")

json.dump({k:len(v) for k,v in results.items()},open(OUT/'decompose_v112.json','w'))
print(f"\n  Saved: {OUT/'decompose_v112.json'}")
