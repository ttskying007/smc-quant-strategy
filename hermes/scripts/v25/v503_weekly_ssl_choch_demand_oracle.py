#!/usr/bin/env python3
"""V503 independent raw-bar oracle for V502 weekly SSL/CHOCH/demand transfer seeds."""
from __future__ import annotations
import csv, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v502_weekly_ssl_choch_demand_transfer_latest.json'
OUT=AUD/f"v503_weekly_ssl_choch_demand_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v503_weekly_ssl_choch_demand_oracle_latest.json'
FORBIDDEN_EXACT={'entry_price','exit_idx','exit_date','exit_price','exit_reason','pnl_pct','gross_pnl_pct','net_pnl_pct','mfe','mae','winner','won','outcome','tp','sl','hold_bars'}


def num(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def integer(x): return int(float(x))
def date8(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]


def daily_bars(sym):
    try: src=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    result=[]
    for item in src:
        d=date8(item.get('t') or item.get('date')); vals=[num(item.get(k)) for k in ('o','h','l','c')]
        if d and min(vals)>0: result.append({'t':d,'o':vals[0],'h':vals[1],'l':vals[2],'c':vals[3]})
    return sorted(result,key=lambda b:b['t'])


def completed_weeks(bars):
    buckets=[]; previous=None
    for bar in bars:
        key=datetime.strptime(bar['t'],'%Y%m%d').date().isocalendar()[:2]
        if key!=previous: buckets.append([]); previous=key
        buckets[-1].append(bar)
    answer=[]
    for group in buckets[:-1]:
        answer.append({'start':group[0]['t'],'end':group[-1]['t'],'o':group[0]['o'],'h':max(b['h'] for b in group),'l':min(b['l'] for b in group),'c':group[-1]['c']})
    return answer


def is_low(ws,i): return 2<=i<len(ws)-2 and all(ws[i]['l']<ws[j]['l'] for j in range(i-2,i+3) if j!=i)
def is_high(ws,i): return 2<=i<len(ws)-2 and all(ws[i]['h']>ws[j]['h'] for j in range(i-2,i+3) if j!=i)


def first_lifecycle(bars,after,zl,zh):
    start=next((i for i,b in enumerate(bars) if b['t']>after),None)
    if start is None: return None
    touch=reclaim=None
    for i in range(start,min(len(bars),start+41)):
        b=bars[i]
        if b['c']<zl: return None
        if touch is None:
            if b['l']<=zh and b['h']>=zl: touch=i
        elif reclaim is None:
            if i>touch and b['c']>zh: reclaim=i
        elif i>reclaim and b['c']>zh and b['l']>=zl:
            return touch,reclaim,i,i+1 if i+1<len(bars) else None
    return None


def audit(row,bars):
    ws=completed_weeks(bars)
    li=integer(row['weekly_ssl_idx']); lc=integer(row['weekly_ssl_confirm_idx']); raid=integer(row['weekly_raid_idx'])
    hi=integer(row['weekly_swing_high_idx']); hc=integer(row['weekly_swing_high_confirm_idx']); choch=integer(row['weekly_choch_idx']); ob=integer(row['weekly_demand_ob_idx'])
    indices=(li,lc,raid,hi,hc,choch,ob)
    if min(indices)<0 or max(indices)>=len(ws): return 'INDEX_OUT_OF_RANGE'
    if not is_low(ws,li) or lc!=li+2: return 'SSL_PIVOT_MISMATCH'
    if not is_high(ws,hi) or hc!=hi+2: return 'SWING_HIGH_MISMATCH'
    ssl=ws[li]['l']; level=ws[hi]['h']
    if abs(ssl-num(row['weekly_ssl_level']))>1e-5 or abs(level-num(row['weekly_choch_break_level']))>1e-5: return 'LEVEL_MISMATCH'
    eligible_lows=[i for i in range(2,raid) if is_low(ws,i) and i+2<=raid and ws[raid]['l']<ws[i]['l']*.997 and ws[raid]['c']>ws[i]['l']]
    if not eligible_lows or li!=max(eligible_lows): return 'SSL_SELECTION_MISMATCH'
    eligible_highs=[i for i in range(2,raid) if is_high(ws,i) and i+2<=raid]
    if not eligible_highs or hi!=max(eligible_highs): return 'PRE_RAID_HIGH_SELECTION_MISMATCH'
    if ws[raid]['end']!=row['weekly_raid_end_date'] or abs(ws[raid]['l']-num(row['weekly_raid_low']))>1e-5: return 'RAID_FIELD_MISMATCH'
    first_choch=next((j for j in range(raid+1,min(len(ws),raid+13)) if ws[j]['c']>level*1.003),None)
    if first_choch!=choch or ws[choch]['end']!=row['weekly_choch_end_date']: return 'CHOCH_MISMATCH'
    nearest_ob=next((j for j in range(choch-1,max(raid-1,choch-7),-1) if ws[j]['c']<ws[j]['o']),None)
    if nearest_ob!=ob or ws[ob]['end']!=row['weekly_demand_ob_end_date']: return 'OB_ANCHOR_MISMATCH'
    zl=ws[ob]['l']; zh=max(ws[ob]['o'],ws[ob]['c'])
    if abs(zl-num(row['zone_low']))>1e-5 or abs(zh-num(row['zone_high']))>1e-5: return 'ZONE_MISMATCH'
    life=first_lifecycle(bars,ws[choch]['end'],zl,zh)
    expected=(integer(row['touch_idx']),integer(row['reclaim_idx']),integer(row['hold_idx']),integer(row['eligible_entry_idx']))
    if life!=expected: return 'LIFECYCLE_MISMATCH'
    dates=(bars[expected[0]]['t'],bars[expected[1]]['t'],bars[expected[2]]['t'],bars[expected[3]]['t'])
    if dates!=(row['touch_date'],row['reclaim_date'],row['hold_date'],row['eligible_entry_date']): return 'DATE_MISMATCH'
    if not (li<lc<=raid<choch and hi<hc<=raid and raid<=ob<choch and expected[0]<expected[1]<expected[2]<expected[3]): return 'CHRONOLOGY_MISMATCH'
    return 'PASS'


def main():
    report=json.loads(SRC.read_text())
    if report.get('decision')!='WEEKLY_SSL_CHOCH_DEMAND_SEEDS_READY__INDEPENDENT_ORACLE_NEXT': raise RuntimeError('V502 gate failed')
    with open(report['artifacts']['seeds']) as h: rows=list(csv.DictReader(h))
    headers=set(rows[0]) if rows else set(); forbidden=sorted(headers & FORBIDDEN_EXACT)
    grouped=defaultdict(list)
    for row in rows: grouped[row['symbol']].append(row)
    counts=Counter(); passed=[]; mismatches=[]; OUT.mkdir(parents=True,exist_ok=True)
    for n,(sym,items) in enumerate(grouped.items(),1):
        bars=daily_bars(sym)
        for row in items:
            reason=audit(row,bars) if bars else 'MISSING_KLINE'; counts[reason]+=1
            if reason=='PASS': passed.append(row)
            elif len(mismatches)<200: mismatches.append({'symbol':sym,'eligible_entry_date':row['eligible_entry_date'],'reason':reason})
        if n%500==0: print(json.dumps({'symbols':n,'passed':counts['PASS'],'failed':sum(v for k,v in counts.items() if k!='PASS')}),flush=True)
    passed_file=OUT/'v503_oracle_passed_seeds.csv'; mismatch_file=OUT/'v503_oracle_mismatches.csv'
    fields=list(rows[0]) if rows else ['symbol']
    with passed_file.open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(passed)
    with mismatch_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=['symbol','eligible_entry_date','reason']); w.writeheader(); w.writerows(mismatches)
    failures=len(rows)-counts['PASS']; ok=bool(rows) and failures==0 and not forbidden
    result={'version':'V503_WEEKLY_SSL_CHOCH_DEMAND_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'source_seed_count':len(rows),'oracle_pass_count':counts['PASS'],'oracle_failure_count':failures,'reason_counts':dict(counts),'forbidden_outcome_headers':forbidden,
      'invariants':{'raw_bar_reaggregation':True,'independent_pivot_rederivation':True,'first_event_lifecycle_rederived':True,'zero_mismatch':failures==0,'no_outcome_fields':not forbidden},
      'decision':'WEEKLY_SSL_CHOCH_DEMAND_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if ok else 'WEEKLY_SSL_CHOCH_DEMAND_ORACLE_FAIL__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'passed_seeds':str(passed_file),'mismatches':str(mismatch_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v503_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
