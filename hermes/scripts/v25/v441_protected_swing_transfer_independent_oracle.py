#!/usr/bin/env python3
"""V441 independent no-write oracle for V440 Protected-Swing Transfer."""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SOURCE=AUD/'v440_protected_swing_transfer_latest.json'
OUT=AUD/f'v441_protected_swing_transfer_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v441_protected_swing_transfer_independent_oracle_latest.json'
LEFT=RIGHT=3; STRUCTURE_START=30; BREAK_BUFFER=.002; OB_BACKSCAN=10

def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0

def day(b): return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
def load_bars(path):
    try: raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        x={k:f(b.get(k)) for k in ('o','h','l','c')}
        if day(b) and all(x.values()): x['t']=day(b); rows.append(x)
    return sorted(rows,key=lambda x:x['t'])
def symbol(path):
    code,ex=path.name.removesuffix('_daily_750.json').split('_'); return f'{code}.{ex}'

def confirmed_swings(bars):
    highs=[]; lows=[]
    for i in range(LEFT+RIGHT,len(bars)-RIGHT):
        if all(bars[j]['h']<bars[i]['h'] for j in range(i-LEFT,i+RIGHT+1) if j!=i): highs.append({'idx':i,'price':bars[i]['h'],'confirm_idx':i+RIGHT})
        if all(bars[j]['l']>bars[i]['l'] for j in range(i-LEFT,i+RIGHT+1) if j!=i): lows.append({'idx':i,'price':bars[i]['l'],'confirm_idx':i+RIGHT})
    return highs,lows

def structure_events(bars,highs,lows):
    broken=set(); trend='unknown'; out=[]
    for i in range(STRUCTURE_START,len(bars)):
        hs=sorted((x for x in highs if x['confirm_idx']<=i and ('high',x['idx']) not in broken),key=lambda x:x['confirm_idx'],reverse=True)
        hit=next((x for x in hs if bars[i]['c']>x['price']*(1+BREAK_BUFFER)),None)
        if hit:
            out.append({'direction':'bull','type':'BOS' if trend=='bullish' else 'CHOCH','index':i,'broken_swing_idx':hit['idx']}); broken.add(('high',hit['idx'])); trend='bullish'; continue
        ls=sorted((x for x in lows if x['confirm_idx']<=i and ('low',x['idx']) not in broken),key=lambda x:x['confirm_idx'],reverse=True)
        hit=next((x for x in ls if bars[i]['c']<x['price']*(1-BREAK_BUFFER)),None)
        if hit:
            out.append({'direction':'bear','type':'BOS' if trend=='bearish' else 'CHOCH','index':i,'broken_swing_idx':hit['idx']}); broken.add(('low',hit['idx'])); trend='bearish'
    return out

def protected_transfer(bars,lows,previous_event_idx,event_idx):
    olds=[x for x in lows if x['confirm_idx']<previous_event_idx]
    news=[x for x in lows if x['idx']>previous_event_idx and x['confirm_idx']<event_idx]
    if not olds or not news: return None
    old=max(olds,key=lambda x:x['confirm_idx']); new=max(news,key=lambda x:x['confirm_idx'])
    if new['price']<=old['price'] or any(bars[i]['c']<old['price'] for i in range(previous_event_idx+1,event_idx)): return None
    return old,new

def demand_poi(bars,event_idx,new_idx):
    for i in range(event_idx-1,max(new_idx,event_idx-OB_BACKSCAN)-1,-1):
        if bars[i]['c']<bars[i]['o']: return i,bars[i]['l'],bars[i]['h']
    return None

def lifecycle(bars,event,low,high,protected):
    touch=reclaim=None
    for i in range(event+1,len(bars)):
        b=bars[i]
        if b['c']<protected: return None
        if touch is None:
            if b['l']<=high and b['h']>=low: touch=i
            continue
        if reclaim is None:
            if i>touch and b['c']>high: reclaim=i
            continue
        if i>reclaim and b['c']>high and b['l']>=protected:
            eligible=i+1
            if eligible>=len(bars) or bars[eligible]['o']<=protected: return None
            return touch,reclaim,i,eligible
    return None

def identity(r):
    return (str(r['symbol']),int(r['previous_bos_idx']),int(r['old_protected_low_idx']),round(f(r['old_protected_low_price']),6),int(r['new_protected_low_idx']),int(r['new_protected_low_confirm_idx']),round(f(r['new_protected_low_price']),6),int(r['transfer_bos_idx']),int(r['broken_swing_idx']),int(r['poi_idx']),round(f(r['zone_low']),6),round(f(r['zone_high']),6),int(r['touch_idx']),int(r['reclaim_idx']),int(r['takeover_idx']),int(r['eligible_entry_idx']))

def main():
    source=json.loads(SOURCE.read_text())
    if source.get('decision')!='PROTECTED_SWING_TRANSFER_SEMANTIC_READY__INDEPENDENT_ORACLE_NEXT': raise RuntimeError('V440 gate did not pass')
    with Path(source['artifacts']['unique_takeover']).open(newline='') as h: source_rows=list(csv.DictReader(h))
    source_set={identity(r) for r in source_rows}; OUT.mkdir(parents=True,exist_ok=True)
    rows=[]; counts=Counter(); chronology=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        bars=load_bars(path)
        if len(bars)<60: continue
        sym=symbol(path); counts['symbols_scanned']+=1
        highs,lows=confirmed_swings(bars); events=structure_events(bars,highs,lows)
        bull=[e for e in events if e['direction']=='bull' and e['type']=='BOS']; per={}
        for prev,event in zip(bull,bull[1:]):
            pi,ei=prev['index'],event['index']; transfer=protected_transfer(bars,lows,pi,ei)
            if transfer is None: continue
            old,new=transfer; poi=demand_poi(bars,ei,new['idx'])
            if poi is None: continue
            poi_idx,zl,zh=poi; life=lifecycle(bars,ei,zl,zh,new['price'])
            if life is None: continue
            touch,reclaim,takeover,eligible=life
            chronology+=int(not(old['confirm_idx']<pi<new['idx']<new['confirm_idx']<ei and poi_idx>=new['idx'] and poi_idx<ei and ei<touch<reclaim<takeover<eligible))
            r={'symbol':sym,'ontology':'PROTECTED_SWING_TRANSFER','previous_bos_idx':pi,'previous_bos_date':bars[pi]['t'],'old_protected_low_idx':old['idx'],'old_protected_low_date':bars[old['idx']]['t'],'old_protected_low_price':round(old['price'],6),'new_protected_low_idx':new['idx'],'new_protected_low_date':bars[new['idx']]['t'],'new_protected_low_confirm_idx':new['confirm_idx'],'new_protected_low_confirm_date':bars[new['confirm_idx']]['t'],'new_protected_low_price':round(new['price'],6),'transfer_bos_idx':ei,'transfer_bos_date':bars[ei]['t'],'broken_swing_idx':event['broken_swing_idx'],'poi_idx':poi_idx,'poi_date':bars[poi_idx]['t'],'zone_low':round(zl,6),'zone_high':round(zh,6),'touch_idx':touch,'touch_date':bars[touch]['t'],'reclaim_idx':reclaim,'reclaim_date':bars[reclaim]['t'],'takeover_idx':takeover,'takeover_date':bars[takeover]['t'],'eligible_entry_idx':eligible,'eligible_entry_date':bars[eligible]['t'],'tradable':'false','buy_enabled':'false','outcome_fields_present':'false'}
            key=(sym,r['takeover_date']); oldr=per.get(key); rank=(ei,new['idx'],poi_idx); oldrank=(oldr['transfer_bos_idx'],oldr['new_protected_low_idx'],oldr['poi_idx']) if oldr else None
            if oldr is None or rank<oldrank: per[key]=r
        rows.extend(per.values())
        if n%500==0: print(json.dumps({'progress':n,'oracle_unique':len(rows)}),flush=True)
    oracle_set={identity(r) for r in rows}; se=source_set-oracle_set; oe=oracle_set-source_set
    mism=[{'disposition':'V440_EXTRA','identity':repr(x)} for x in sorted(se)]+[{'disposition':'ORACLE_EXTRA','identity':repr(x)} for x in sorted(oe)]
    fields=list(rows[0]) if rows else ['symbol','ontology']
    with (OUT/'v441_oracle_unique_takeover_rows.csv').open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    with (OUT/'v441_differential_mismatches.csv').open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=['disposition','identity']); w.writeheader(); w.writerows(mism)
    report={'version':'V441_PROTECTED_SWING_TRANSFER_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source_count':len(source_set),'oracle_count':len(oracle_set),'v440_extra':len(se),'oracle_extra':len(oe),'mismatch_total':len(se)+len(oe),'stage_counts':dict(counts),'invariants':{'chronology_failures':chronology,'duplicate_oracle_identity':len(rows)-len(oracle_set),'identity_set_equal':source_set==oracle_set,'all_non_tradable':True,'no_outcome_fields':True},'decision':'INDEPENDENT_SEMANTIC_ORACLE_PASS__FROZEN_T1_REPLAY_NEXT' if source_set==oracle_set and chronology==0 else 'INDEPENDENT_SEMANTIC_ORACLE_FAIL__STOP_PROTECTED_SWING_TRANSFER','artifacts':{'out_dir':str(OUT),'oracle_rows':str(OUT/'v441_oracle_unique_takeover_rows.csv'),'mismatches':str(OUT/'v441_differential_mismatches.csv'),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v441_report.json').write_text(text); LATEST.write_text(text); print(text)
    if report['decision'].startswith('INDEPENDENT_SEMANTIC_ORACLE_FAIL'): raise SystemExit(2)
if __name__=='__main__': main()
