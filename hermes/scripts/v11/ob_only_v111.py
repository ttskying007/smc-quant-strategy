#!/usr/bin/env python3
"""V11.1 — OB_Bull Only vs Baseline 对比"""
import json, time
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

def daily_to_weekly(d):
    w=[]
    for i in range(0,len(d),5):
        c=d[i:i+5]
        if len(c)>=3:w.append({'o':c[0]['o'],'h':max(x['h'] for x in c),'l':min(x['l'] for x in c),'c':c[-1]['c']})
    return w

def weekly_trend(w):
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

def detect_sequences(signals):
    sbb=defaultdict(list)
    for s in signals:sbb[s.idx].append(s)
    all_s=[]
    for pn,(stages,gaps) in PATTERNS.items():
        ss=[CATEGORIES[st]for st in stages]
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb]if s.type in ss[0]]:
                chain=[sig];c=sig.idx;ok=True
                for si in range(1,len(stages)):
                    gap=gaps[si-1]if si-1<len(gaps)else MAX_GAP
                    fnd=False
                    for bi in range(c+1,c+gap+1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in ss[si]and cand not in chain:
                                    chain.append(cand);c=bi;fnd=True;break
                        if fnd:break
                    if not fnd:ok=False;break
                if ok and len(chain)==len(stages):
                    all_s.append({'pattern':pn,'seq_bar':chain[-1].idx,'zone_type':chain[-1].type,'zone_low':chain[-1].lower,'zone_high':chain[-1].upper})
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
        trades.append({'won':(exit_px-ep)/ep*100>0,'pnl_pct':round((exit_px-ep)/ep*100,2),'exit_reason':reason,'zone_type':sq['zone_type'],'pattern':sq['pattern']})
    return trades

print("V11.1: OB_Bull Only vs All Zones")
daily_files=sorted(KLINE.glob('*_daily_300.json'))
t0=time.time()
all_v8=[];all_ob=[];dna={}
for fi,df in enumerate(daily_files):
    name=df.stem.replace('_daily_300','');parts=name.rsplit('_',1)
    sym=f'{parts[0]}.{parts[1]}'if len(parts)==2 else name
    try:
        daily=json.loads(df.read_bytes());n=len(daily)
        if n<50:continue
    except:continue
    try:
        sigs,_,_,_=detect_all_signals_v20(daily);seqs=detect_sequences(sigs)
    except:continue
    if not seqs:continue
    wp=KLINE/f'{name}_weekly_200.json'
    try:
        w=json.loads(wp.read_bytes())if wp.exists()else daily_to_weekly(daily)
        if len(w)<20:w=daily_to_weekly(daily)
    except:w=daily_to_weekly(daily)
    trend=weekly_trend(w)
    # Per-pattern best
    seqs_by_pat=defaultdict(list)
    for sq in seqs:seqs_by_pat[sq['pattern']].append(sq)
    best_pat='ZONE_ONLY';best_wr=0
    for pn,pseqs in seqs_by_pat.items():
        if len(pseqs)<MIN_TRADES:continue
        t=bt(daily,pseqs)
        if t:
            wr=sum(1 for x in t if x['won'])/len(t)
            if wr>best_wr:best_wr=wr;best_pat=pn
    best_seqs=seqs_by_pat.get(best_pat,seqs)
    # V8: all zones
    t8=bt(daily,best_seqs)
    for t in t8:t['symbol']=sym
    all_v8.extend(t8)
    # OB-only: filter out FVG_Bull zones
    ob_seqs=[s for s in best_seqs if s['zone_type']=='OB_Bull']
    t_ob=bt(daily,ob_seqs)
    for t in t_ob:t['symbol']=sym
    all_ob.extend(t_ob)
    dna[sym]={'best_pat':best_pat,'trend':trend,'all_trades':len(t8),'ob_trades':len(t_ob),
              'all_wr':round(sum(1 for t in t8 if t['won'])/max(len(t8),1),3)if t8 else 0,
              'ob_wr':round(sum(1 for t in t_ob if t['won'])/max(len(t_ob),1),3)if t_ob else 0}
    if (fi+1)%1000==0:print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s")

elapsed=time.time()-t0
v8_wr=sum(1 for t in all_v8 if t['won'])/max(len(all_v8),1)
v8_pnl=sum(t['pnl_pct']for t in all_v8)/max(len(all_v8),1)
ob_wr=sum(1 for t in all_ob if t['won'])/max(len(all_ob),1)
ob_pnl=sum(t['pnl_pct']for t in all_ob)/max(len(all_ob),1)

print(f"\n{'='*60}")
print(f"  V11.1: All Zones vs OB_Bull Only ({elapsed:.0f}s)")
print(f"{'='*60}")
print(f"  {'':20s} {'WR':>7s} {'PnL':>8s} {'Trades':>7s}")
print(f"  {'All Zones':20s} {v8_wr:>6.1%} {v8_pnl:>+7.2f}% {len(all_v8):>7d}")
print(f"  {'OB_Bull Only':20s} {ob_wr:>6.1%} {ob_pnl:>+7.2f}% {len(all_ob):>7d}")
if ob_wr>v8_wr:print(f"  ✅ OB-only improves WR by {ob_wr-v8_wr:+.1%}")
print(f"\n  【OB-only by trend】")
for trend in['bullish','bearish','neutral']:
    tt=[t for t in all_ob if dna.get(t['symbol'],{}).get('trend')==trend]
    if tt:print(f"  {trend:8s} WR={sum(1 for t in tt if t['won'])/len(tt):.1%} N={len(tt)}")
print(f"\n  【个股OB覆盖率】")
has_ob=sum(1 for d in dna.values() if d['ob_trades']>0)
print(f"  有OB交易: {has_ob}/{len(dna)}({has_ob/len(dna)*100:.0f}%)")
json.dump({'meta':{'version':'11.1'},'all_wr':round(v8_wr,4),'ob_wr':round(ob_wr,4),'dna':dna},open(OUT/'ob_only_v111.json','w'),ensure_ascii=False)
print(f"\n  Saved: {OUT/'ob_only_v111.json'}")
