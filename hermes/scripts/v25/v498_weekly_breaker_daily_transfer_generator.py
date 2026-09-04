#!/usr/bin/env python3
"""V498 outcome-blind weekly bearish-OB failure -> breaker -> daily transfer generator."""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v498_weekly_breaker_daily_transfer_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v498_weekly_breaker_daily_transfer_latest.json'; YEARS=('2023','2024','2025','2026')


def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]


def load(path):
    try: raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError): return []
    out=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}; d=ds(b.get('t') or b.get('date'))
        if d and min(r.values())>0: r['t']=d; out.append(r)
    return sorted(out,key=lambda x:x['t'])


def symbol(path):
    code,ex=path.name.removesuffix('_daily_750.json').split('_'); return f'{code}.{ex}'


def weeks(daily):
    groups=[]; key=None
    for b in daily:
        d=datetime.strptime(b['t'],'%Y%m%d').date(); k=d.isocalendar()[:2]
        if k!=key: groups.append([]); key=k
        groups[-1].append(b)
    return [{'start_date':g[0]['t'],'end_date':g[-1]['t'],'o':g[0]['o'],'h':max(x['h'] for x in g),'l':min(x['l'] for x in g),'c':g[-1]['c']} for g in groups[:-1] if g]


def confirmed_swing_lows(ws):
    return [(i,i+2,ws[i]['l']) for i in range(2,len(ws)-2) if ws[i]['l']<min(ws[j]['l'] for j in range(i-2,i+3) if j!=i)]


def lifecycle(daily,activation_date,zl,zh):
    start=next((i for i,b in enumerate(daily) if b['t']>activation_date),None)
    if start is None: return None,'NO_DAILY_AFTER_ACTIVATION'
    touch=reclaim=None
    for i in range(start,min(len(daily),start+41)):
        b=daily[i]
        if b['c']<zl: return None,'BREAKER_INVALIDATED_BEFORE_HOLD'
        if touch is None:
            if b['l']<=zh and b['h']>=zl: touch=i
            continue
        if reclaim is None:
            if i>touch and b['c']>zh: reclaim=i
            continue
        if i>reclaim and b['c']>zh and b['l']>=zl:
            return (touch,reclaim,i,i+1 if i+1<len(daily) else None),'PASS'
    if touch is None: return None,'NO_TOUCH_40D'
    if reclaim is None: return None,'NO_RECLAIM_40D'
    return None,'NO_HOLD_40D'


def generate(sym,daily):
    ws=weeks(daily); swings=confirmed_swing_lows(ws); rows=[]; rejects=Counter(); raw=0
    consumed=set()
    for event in range(6,len(ws)):
        visible=[x for x in swings if x[1]<=event and x[0]<event and ws[event]['c']<x[2]*.997]
        if not visible: continue
        pivot,confirm,level=max(visible,key=lambda x:x[0])
        ob=next((j for j in range(event-1,max(-1,event-7),-1) if ws[j]['c']>ws[j]['o']),None)
        if ob is None: rejects['NO_BEARISH_OB_SOURCE']+=1; continue
        identity=(ob,event)
        if identity in consumed: continue
        zl=min(ws[ob]['o'],ws[ob]['c']); zh=ws[ob]['h']
        activation=next((j for j in range(event+1,min(len(ws),event+21)) if ws[j]['c']>zh),None)
        if activation is None: rejects['NO_WEEKLY_BREAKER_ACTIVATION_20W']+=1; continue
        raw+=1; consumed.add(identity)
        life,reason=lifecycle(daily,ws[activation]['end_date'],zl,zh)
        if life is None: rejects[reason]+=1; continue
        touch,reclaim,hold,eligible=life
        if eligible is None: rejects['ENTRY_RIGHT_EDGE']+=1; continue
        order=(pivot<confirm<=event and ob<event<activation and ws[activation]['end_date']<daily[touch]['t']<daily[reclaim]['t']<daily[hold]['t']<daily[eligible]['t'] and eligible==hold+1)
        rows.append({'symbol':sym,'ontology':'WEEKLY_BEARISH_OB_FAILURE_BREAKER_DAILY_TRANSFER',
          'weekly_swing_low_idx':pivot,'weekly_swing_confirm_idx':confirm,'weekly_swing_low':round(level,6),
          'weekly_bear_bos_idx':event,'weekly_bear_bos_end_date':ws[event]['end_date'],
          'weekly_bearish_ob_idx':ob,'weekly_bearish_ob_end_date':ws[ob]['end_date'],
          'weekly_breaker_activation_idx':activation,'weekly_breaker_activation_end_date':ws[activation]['end_date'],
          'zone_low':round(zl,6),'zone_high':round(zh,6),
          'touch_idx':touch,'touch_date':daily[touch]['t'],'reclaim_idx':reclaim,'reclaim_date':daily[reclaim]['t'],
          'hold_idx':hold,'hold_date':daily[hold]['t'],'eligible_entry_idx':eligible,'eligible_entry_date':daily[eligible]['t'],
          'semantic_order_valid':order,'tradable':False,'buy_enabled':False,'no_outcome_fields':True})
    return rows,rejects,raw


def main():
    OUT.mkdir(parents=True,exist_ok=True); all_rows=[]; rejects=Counter(); scanned=raw_n=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        daily=load(path)
        if len(daily)<150: continue
        scanned+=1; rows,bad,raw=generate(symbol(path),daily); all_rows.extend(rows); rejects.update(bad); raw_n+=raw
        if n%500==0: print(json.dumps({'progress':n,'seeds':len(all_rows)}),flush=True)
    dedup={}
    for r in all_rows:
        key=(r['symbol'],r['eligible_entry_date']); old=dedup.get(key)
        if old is None or r['weekly_breaker_activation_idx']<old['weekly_breaker_activation_idx']: dedup[key]=r
    rows=list(dedup.values()); yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    seed=OUT/'v498_semantic_seeds.csv'; fields=list(rows[0]) if rows else ['symbol','ontology']
    with seed.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    inv={'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)}
    ok=support and not inv['semantic_order_failures'] and not inv['duplicate_symbol_entry']
    result={'version':'V498_WEEKLY_BREAKER_DAILY_TRANSFER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'confirmed weekly swing low -> weekly bearish BOS close<low*0.997 -> nearest prior bullish candle within 6 weeks as bearish OB -> later weekly close above OB high activates breaker -> first post-activation daily touch -> later reclaim -> later hold -> next-open eligibility; close below breaker low cancels',
      'distinct_information':'Failure-and-role-reversal ontology: a weekly bearish order block must first create downside structure and later fail upward before acting as demand; not a weekly BOS-demand or FVG variant.',
      'symbols_scanned':scanned,'raw_activated_breakers':raw_n,'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),'rejection_counts':dict(rejects),'support_gate_pass':support,'invariants':inv,
      'decision':'WEEKLY_BREAKER_TRANSFER_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if ok else 'WEEKLY_BREAKER_TRANSFER_SUPPORT_OR_SEMANTIC_FAIL__NO_REPLAY','artifacts':{'out_dir':str(OUT),'seeds':str(seed),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v498_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
