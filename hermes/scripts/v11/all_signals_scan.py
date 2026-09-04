#!/usr/bin/env python3
"""全信号扫描 — 不遗漏任何信号/组合"""
import json,sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0,'/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20,_calc_atr

KLINE=Path('/root/.hermes/kline_cache')
OUT=Path('/root/.hermes/smc_opt_v21')
DNA_FILE=OUT/'stock_dna_v11.json'
dna={}
if DNA_FILE.exists():
    with open(DNA_FILE) as f: dna=json.load(f).get('dna',{})

CATEGORIES = {
    'LIQ_LONG':  ['Sweep_SSL', 'EQL'],
    'LIQ_SHORT': ['Sweep_BSL', 'EQH'],
    'STRUCT_LONG': ['CHOCH_Bull','BOS_Bull','MSS_Bull'],
    'STRUCT_SHORT':['CHOCH_Bear','BOS_Bear','MSS_Bear'],
    'ZONE_LONG': ['OB_Bull','FVG_Bull'],
    'ZONE_SHORT':['OB_Bear','FVG_Bear'],
    'CONTEXT':   ['BPR'],
}

PATTERNS = {
    'LIQ→ZONE': (['LIQ_LONG','ZONE_LONG'],[25]),
    'CTX→ZONE': (['STRUCT_LONG','ZONE_LONG'],[20]),
    'ZONE_ONLY':(['ZONE_LONG'],[]),
    'LIQ→CTX→ZONE':(['LIQ_LONG','STRUCT_LONG','ZONE_LONG'],[30,15]),
    'LIQ_S→ZONE_S':(['LIQ_SHORT','ZONE_SHORT'],[25]),
    'CTX_S→ZONE_S':(['STRUCT_SHORT','ZONE_SHORT'],[20]),
}

def detect_sequences(signals):
    sbb=defaultdict(list)
    for s in signals:sbb[s.idx].append(s)
    seqs=[]
    for pn,(stages,gaps) in PATTERNS.items():
        ss=[CATEGORIES[s] for s in stages]
        for sb in sorted(sbb):
            for sig in[s for s in sbb[sb]if s.type in ss[0]]:
                chain=[sig];c=sig.idx;ok=True
                for si in range(1,len(stages)):
                    gap=gaps[si-1]if si-1<len(gaps)else 25;fnd=False
                    for bi in range(c+1,c+gap+1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in ss[si]and cand not in chain:
                                    chain.append(cand);c=bi;fnd=True;break
                        if fnd:break
                    if not fnd:ok=False;break
                if ok and len(chain)==len(stages):
                    seqs.append({'pattern':pn,'seq_bar':chain[-1].idx,
                        'zone_type':chain[-1].type,
                        'zone_low':chain[-1].lower,'zone_high':chain[-1].upper,
                        'signals':[{'type':x.type,'bar':x.idx} for x in chain]})
    return seqs

SIG_SHORT={'OB_Bull':'OB↑','OB_Bear':'OB↓','FVG_Bull':'FVG↑','FVG_Bear':'FVG↓',
           'Sweep_SSL':'S_SSL','Sweep_BSL':'S_BSL','CHOCH_Bull':'CH↑','CHOCH_Bear':'CH↓',
           'BOS_Bull':'BOS↑','BOS_Bear':'BOS↓','MSS_Bull':'MSS↑','MSS_Bear':'MSS↓',
           'EQL':'EQL','EQH':'EQH','BPR':'BPR'}

# Scan
picks=[]
signal_counts=defaultdict(int)
combo_counts=defaultdict(int)
for fp in sorted(KLINE.glob('*_daily_300.json')):
    name=fp.stem.replace('_daily_300','')
    parts=name.rsplit('_',1)
    if len(parts)!=2:continue
    sym=f'{parts[0]}.{parts[1]}'
    try:
        daily=json.loads(fp.read_bytes());n=len(daily)
        if n<50:continue
    except:continue
    last=daily[-1];ld=str(last.get('t',last.get('date','')))[:10]
    try:
        if int(ld.replace('-',''))<20260401:continue
    except:continue
    
    try:
        sigs,st,_,_=detect_all_signals_v20(daily)
        seqs=detect_sequences(sigs)
    except:continue
    
    sd=dna.get(sym,{})
    
    # 1. All single signals on last 2 bars
    recent=[s for s in sigs if s.idx>=n-2]
    for s in recent:
        signal_counts[s.type]+=1
        sl=s.lower*0.995 if s.lower>0 else last['c']*0.97
        picks.append({
            'symbol':sym,'type':'single','signal':s.type,
            'date':str(daily[s.idx].get('t',daily[s.idx].get('date','')))[:10],
            'bar':s.idx,'price':round(s.price,2),
            'zone_low':round(s.lower,2) if s.lower>0 else 0,
            'close':round(last['c'],2),
            'sl':round(sl,2),'tp':round(last['c']*1.03,2),
            'hist_wr':sd.get('v11_wr',0),'ob_wr':sd.get('ob_wr',0),
            'trend':sd.get('trend','?'),
        })
    
    # 2. All sequence/combination signals on last 2 bars
    recent_seqs=[s for s in seqs if s['seq_bar']>=n-2]
    for sq in recent_seqs:
        combo_counts[sq['pattern']]+=1
        sig_chain='→'.join(SIG_SHORT.get(x['type'],x['type'][:4]) for x in sq['signals'])
        sl=sq['zone_low']*0.995 if sq['zone_low']>0 else last['c']*0.97
        picks.append({
            'symbol':sym,'type':'combo','signal':sq['pattern'],
            'chain':sig_chain,
            'date':str(daily[sq['seq_bar']].get('t',daily[sq['seq_bar']].get('date','')))[:10],
            'bar':sq['seq_bar'],'price':round(daily[sq['seq_bar']]['c'],2),
            'zone_low':round(sq['zone_low'],2),
            'close':round(last['c'],2),
            'sl':round(sl,2),'tp':round(last['c']*1.03,2),
            'hist_wr':sd.get('v11_wr',0),'ob_wr':sd.get('ob_wr',0),
            'trend':sd.get('trend','?'),
        })

picks.sort(key=lambda x:(x['type']!='combo',x['signal'],-x['hist_wr']))

print(f"扫描: 4836只")
print(f"\n=== 信号统计 ===")
print(f"单信号:")
for sig,count in sorted(signal_counts.items(),key=lambda x:-x[1]):
    print(f"  {sig:<15s} {count}")
print(f"\n组合信号:")
for combo,count in sorted(combo_counts.items(),key=lambda x:-x[1]):
    print(f"  {combo:<20s} {count}")

print(f"\n=== 全量选股清单 (共{len(picks)}个) ===")
# Group by signal type for readability
for sig_type in ['single','combo']:
    group=[p for p in picks if p['type']==sig_type]
    print(f"\n--- {sig_type} ({len(group)}个) ---")
    print(f"  {'代码':<12s} {'信号':<18s} {'日期':<10s} {'信号价':>7s} {'现价':>7s} {'SL':>7s} {'TP':>7s} {'histWR':>7s} {'趋势':>5s}")
    print(f"  {'-'*85}")
    for p in group[:60]:
        sig_display=p.get('chain',p['signal'])[:18]
        print(f"  {p['symbol']:<12s} {sig_display:<18s} {p['date']:<10s} {p['price']:>7.2f} {p['close']:>7.2f} {p['sl']:>7.2f} {p['tp']:>7.2f} {p['hist_wr']:>6.1%} {p['trend']:>5s}")

json.dump(picks,open(OUT/'all_signals_picks.json','w'),ensure_ascii=False)
print(f"\nSaved: {len(picks)} picks")
