#!/usr/bin/env python3
"""V489 outcome-blind weekly BOS -> weekly demand -> daily transfer generator."""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v489_weekly_bos_demand_transfer_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v489_weekly_bos_demand_transfer_latest.json'; YEARS=('2023','2024','2025','2026')


def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]


def load(path):
    try: raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}; d=ds(b.get('t') or b.get('date'))
        if d and min(r.values())>0: r['t']=d; rows.append(r)
    return sorted(rows,key=lambda x:x['t'])


def symbol(path):
    code,ex=path.name.removesuffix('_daily_750.json').split('_'); return f'{code}.{ex}'


def weeks(daily):
    groups=[]; key=None
    for b in daily:
        d=datetime.strptime(b['t'],'%Y%m%d').date(); k=d.isocalendar()[:2]
        if k!=key: groups.append([]); key=k
        groups[-1].append(b)
    groups=groups[:-1]
    return [{'start_date':g[0]['t'],'end_date':g[-1]['t'],'o':g[0]['o'],'h':max(x['h'] for x in g),'l':min(x['l'] for x in g),'c':g[-1]['c']} for g in groups if g]


def weekly_highs(ws):
    return [{'idx':i,'confirm_idx':i+2,'price':ws[i]['h']} for i in range(2,len(ws)-2)
            if ws[i]['h']>max(ws[j]['h'] for j in range(i-2,i+3) if j!=i)]


def lifecycle(daily,start_date,zl,zh):
    start=next((i for i,b in enumerate(daily) if b['t']>start_date),None)
    if start is None:return None
    touch=reclaim=None
    for i in range(start,min(len(daily),start+31)):
        b=daily[i]
        if b['c']<zl:return None
        if touch is None:
            if b['l']<=zh: touch=i
            continue
        if reclaim is None:
            if i>touch and b['c']>zh: reclaim=i
            continue
        if i>reclaim and b['c']>zh and b['l']>=zl:
            return touch,reclaim,i,i+1 if i+1<len(daily) else None
    return None


def generate(sym,daily):
    ws=weeks(daily); piv=weekly_highs(ws); rows=[]; rejects=Counter()
    for bos in range(7,len(ws)):
        visible=[x for x in piv if x['confirm_idx']<bos and bos-x['idx']<=52 and ws[bos]['c']>x['price']*1.003]
        if not visible:continue
        broken=max(visible,key=lambda x:x['idx'])
        ob_idx=next((i for i in range(bos-1,max(-1,bos-7),-1) if ws[i]['c']<ws[i]['o']),None)
        if ob_idx is None: rejects['NO_BEARISH_WEEKLY_OB_6W']+=1; continue
        ob=ws[ob_idx]; zl=ob['l']; zh=max(ob['o'],ob['c'])
        if any(ws[j]['l']<=zh for j in range(ob_idx+1,bos)):
            rejects['WEEKLY_OB_MITIGATED_BEFORE_BOS']+=1; continue
        life=lifecycle(daily,ws[bos]['end_date'],zl,zh)
        if life is None: rejects['NO_VALID_DAILY_TOUCH_RECLAIM_HOLD_30D']+=1; continue
        touch,reclaim,hold,eligible=life
        if eligible is None: rejects['ENTRY_RIGHT_EDGE']+=1; continue
        order=broken['confirm_idx']<bos and ob_idx<bos and ws[bos]['end_date']<daily[touch]['t']<daily[reclaim]['t']<daily[hold]['t']<daily[eligible]['t']
        rows.append({'symbol':sym,'ontology':'WEEKLY_BOS_DEMAND_OB_DAILY_TRANSFER',
          'weekly_broken_high_idx':broken['idx'],'weekly_broken_high_confirm_idx':broken['confirm_idx'],'weekly_broken_high':round(broken['price'],6),
          'weekly_ob_idx':ob_idx,'weekly_ob_start_date':ob['start_date'],'weekly_ob_end_date':ob['end_date'],'zone_low':round(zl,6),'zone_high':round(zh,6),
          'weekly_bos_idx':bos,'weekly_bos_end_date':ws[bos]['end_date'],'weekly_bos_close':round(ws[bos]['c'],6),
          'touch_idx':touch,'touch_date':daily[touch]['t'],'reclaim_idx':reclaim,'reclaim_date':daily[reclaim]['t'],
          'hold_idx':hold,'hold_date':daily[hold]['t'],'eligible_entry_idx':eligible,'eligible_entry_date':daily[eligible]['t'],
          'semantic_order_valid':order,'tradable':False,'buy_enabled':False,'no_outcome_fields':True})
    return rows,rejects


def main():
    OUT.mkdir(parents=True,exist_ok=True); raw=[]; rejects=Counter(); scanned=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        daily=load(path)
        if len(daily)<150:continue
        scanned+=1; rows,bad=generate(symbol(path),daily); raw.extend(rows); rejects.update(bad)
        if n%500==0:print(json.dumps({'progress':n,'raw':len(raw)}),flush=True)
    dedup={}
    for r in raw:
        key=(r['symbol'],r['eligible_entry_date']); old=dedup.get(key)
        if old is None or r['weekly_bos_idx']<old['weekly_bos_idx']:dedup[key]=r
    rows=list(dedup.values()); yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    seed=OUT/'v489_semantic_seeds.csv'; fields=list(rows[0]) if rows else ['symbol','ontology']
    with seed.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    result={'version':'V489_WEEKLY_BOS_DEMAND_TRANSFER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'completed weekly 2L/2R BSL -> weekly close BOS 0.3% -> nearest bearish weekly demand OB <=6 weeks, unmitigated before BOS -> post-BOS daily touch -> later reclaim -> later hold -> next-open eligibility',
      'distinct_information':'Higher-timeframe continuation state transferred into a lower-timeframe demand lifecycle; distinct from weekly SSL rejection, daily C1 BOS/OB, and BSL flip retest.',
      'symbols_scanned':scanned,'raw_seed_count':len(raw),'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),'rejection_counts':dict(rejects),'support_gate_pass':support,
      'invariants':{'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)},
      'decision':'WEEKLY_BOS_DEMAND_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if support and all(r['semantic_order_valid'] for r in rows) else 'WEEKLY_BOS_DEMAND_SUPPORT_OR_SEMANTIC_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'seeds':str(seed),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v489_report.json').write_text(text);LATEST.write_text(text);print(text)

if __name__=='__main__':main()
