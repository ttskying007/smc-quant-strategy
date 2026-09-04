#!/usr/bin/env python3
"""V427 no-outcome R5 generator: PO3 accumulation -> SSL manipulation -> bull distribution -> breaker reclaim."""
from __future__ import annotations
import csv, importlib.util, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes'); KDIR, AUD = ROOT/'kline_cache', ROOT/'smc_audit'
OUT = AUD/f'v427_po3_breaker_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD/'v427_po3_breaker_latest.json'
spec = importlib.util.spec_from_file_location('v27', ROOT/'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v27)

def f(x):
    try:
        x=float(x); return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError): return 0.0

def day(b): return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
def load(p):
    try: raw=json.loads(p.read_text())
    except Exception: return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k))>0 for k in ('o','h','l','c'))], key=day)
def sym(p):
    code,ex=p.name.replace('_daily_750.json','').split('_'); return f'{code}.{ex}'

def lifecycle(ks,start,low,high):
    touch=reclaim=None
    for i in range(start+1,min(len(ks),start+31)):
        b=ks[i]
        if f(b['c'])<low: return 'CANCEL_ZONE_INVALIDATED',touch,reclaim,i
        if touch is None:
            if f(b['l'])<=high: touch=i
        elif reclaim is None:
            if f(b['c'])>high: reclaim=i
        elif f(b['c'])>high and f(b['l'])>=low: return 'TAKEOVER_CONFIRMED',touch,reclaim,i
    observed=start+30<len(ks)
    if touch is None: return ('EXPIRE_NO_TOUCH_30B' if observed else 'WAIT_TOUCH_UNOBSERVED'),None,None,None
    if reclaim is None: return ('EXPIRE_NO_RECLAIM_30B' if observed else 'WAIT_RECLAIM_UNOBSERVED'),touch,None,None
    return ('EXPIRE_NO_HOLD_30B' if observed else 'WAIT_HOLD_UNOBSERVED'),touch,reclaim,None

def fresh_breaker(ks,sweep,event):
    for i in range(event-1,sweep-1,-1):
        if f(ks[i]['c'])<f(ks[i]['o']):
            lo,hi=f(ks[i]['l']),f(ks[i]['h'])
            if not any(f(b['c'])<lo or f(b['l'])<=hi for b in ks[i+1:event]): return i,lo,hi
    return None

def main():
    OUT.mkdir(parents=True,exist_ok=True); rows=[]; counts=Counter()
    for p in sorted(KDIR.glob('*_daily_750.json')):
        ks=load(p)
        if len(ks)<100: continue
        counts['symbols_scanned']+=1
        swings=v27.confirmed_swings(ks); events=v27.structure_signals(ks,swings); sweeps=v27.sweep_signals(ks,swings)
        for q in v27.po3_signals(ks,sweeps,events):
            if q['direction']!='bull': continue
            sweep,event=q['phase_manip_idx'],q['phase_dist_idx']
            if not (q['phase_accum_start']<q['phase_accum_end']==sweep<event):
                counts['PO3_ORDER_INVALID']+=1; continue
            breaker=fresh_breaker(ks,sweep,event)
            if breaker is None:
                counts['NO_FRESH_PO3_BREAKER']+=1; continue
            poi,lo,hi=breaker; state,touch,reclaim,takeover=lifecycle(ks,event,lo,hi)
            rows.append({'symbol':sym(p),'combo_key':'R5_PO3_SSL_DISTRIBUTION_BREAKER','lifecycle_state':state,
                'accum_start_idx':q['phase_accum_start'],'accum_end_idx':q['phase_accum_end'],'accum_low':round(f(q['range_low']),6),'accum_high':round(f(q['range_high']),6),
                'sweep_idx':sweep,'sweep_date':day(ks[sweep]),'event_idx':event,'event_date':day(ks[event]),'event_type':q['phase_dist_event'],
                'poi_idx':poi,'poi_date':day(ks[poi]),'poi_type':'FRESH_BEARISH_BREAKER','zone_low':round(lo,6),'zone_high':round(hi,6),'strict_lifecycle_start_idx':event,
                'touch_idx':'' if touch is None else touch,'reclaim_idx':'' if reclaim is None else reclaim,'takeover_idx':'' if takeover is None else takeover,'takeover_date':day(ks[takeover]) if state=='TAKEOVER_CONFIRMED' else '',
                'semantic_contract':'compact PO3 accumulation -> confirmed SSL manipulation -> bull distribution event -> fresh bearish breaker at/after SSL -> first touch/reclaim/hold',
                'tradable':'false','buy_enabled':'false','outcome_fields_present':'false'})
    # source-event uniqueness, then one execution per stock/day; both rules use source order only.
    first={}
    for r in rows:
        key=(r['symbol'],r['event_idx'],r['poi_idx']); rank=(int(r['accum_end_idx']),int(r['sweep_idx']))
        if key not in first or rank>first[key][0]: first[key]=(rank,r)
    execs={}; other=[]
    for _,r in first.values():
        if r['lifecycle_state']!='TAKEOVER_CONFIRMED': other.append(r); continue
        key=(r['symbol'],r['takeover_idx']); rank=(int(r['event_idx']),int(r['poi_idx']))
        if key not in execs or rank>execs[key][0]: execs[key]=(rank,r)
    rows=other+[r for _,r in execs.values()]
    stages=Counter(r['lifecycle_state'] for r in rows); yearly=Counter(r['takeover_date'][:4] for r in rows if r['lifecycle_state']=='TAKEOVER_CONFIRMED')
    with (OUT/'v427_rows.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0]) if rows else ['symbol']);w.writeheader();w.writerows(rows)
    support=all(yearly[y]>=40 for y in ('2023','2024','2025','2026'))
    report={'version':'V427_PO3_BREAKER_GENERATOR_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
        'contract':'R5: compact PO3 accumulation -> SSL manipulation -> bull distribution event -> fresh bearish breaker -> first touch/reclaim/hold','qualitative_distinction':'PO3 is a three-phase accumulation/manipulation/distribution state machine and does not require R4 two-sided confirmed balance pivots or its exact range-high BOS.',
        'counts':dict(counts),'candidates':len(rows),'lifecycle':dict(stages),'takeover_by_year':dict(yearly),'fixed_pre_outcome_gate':{'minimum_takeovers_per_year':40,'minimum_total_takeovers':160},'pre_outcome_support_pass':support,
        'invariants':{'all_non_tradable':all(r['tradable']=='false' for r in rows),'no_outcomes':all(r['outcome_fields_present']=='false' for r in rows),'no_entries_exits_or_marks_created':True},
        'decision':'R5_SUPPORT_GATE_PASS__REQUIRES_INDEPENDENT_SEMANTIC_AUDIT_BEFORE_ANY_REPLAY' if support else 'R5_INSUFFICIENT_FULL_HISTORY_SUPPORT__NO_OUTCOME_REPLAY_OR_THRESHOLD_MINING','artifacts':{'out_dir':str(OUT),'rows':str(OUT/'v427_rows.csv'),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v427_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
