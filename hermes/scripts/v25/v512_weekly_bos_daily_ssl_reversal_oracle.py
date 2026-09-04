#!/usr/bin/env python3
"""V512 independent raw-bar semantic oracle for V511."""
from __future__ import annotations
import csv, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v511_weekly_bos_daily_ssl_reversal_latest.json'
OUT=AUD/f"v512_weekly_bos_daily_ssl_reversal_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v512_weekly_bos_daily_ssl_reversal_oracle_latest.json'
FORBIDDEN={'entry_price','exit_idx','exit_date','exit_price','exit_reason','pnl_pct','gross_pnl_pct','net_pnl_pct','mfe','mae','winner','won','outcome','tp','sl','hold_bars'}


def num(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def integer(x): return int(float(x))
def date8(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]


def bars(sym):
    try: raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    result=[]
    for b in raw:
        d=date8(b.get('t') or b.get('date')); values=[num(b.get(k)) for k in ('o','h','l','c')]
        if d and min(values)>0: result.append({'t':d,'o':values[0],'h':values[1],'l':values[2],'c':values[3]})
    return sorted(result,key=lambda b:b['t'])


def completed_weeks(daily):
    buckets=[]; prior=None
    for b in daily:
        key=datetime.strptime(b['t'],'%Y%m%d').date().isocalendar()[:2]
        if key!=prior: buckets.append([]); prior=key
        buckets[-1].append(b)
    return [{'start':g[0]['t'],'end':g[-1]['t'],'o':g[0]['o'],'h':max(x['h'] for x in g),'l':min(x['l'] for x in g),'c':g[-1]['c']} for g in buckets[:-1] if g]


def pivot_indices(seq,field,left,right,high):
    answer=[]
    for i in range(left,len(seq)-right):
        neighbours=[seq[j][field] for j in range(i-left,i+right+1) if j!=i]
        if (seq[i][field]>max(neighbours)) if high else (seq[i][field]<min(neighbours)):
            answer.append((i,i+right,seq[i][field]))
    return answer


def contexts(ws):
    highs=pivot_indices(ws,'h',2,2,True); lows=pivot_indices(ws,'l',2,2,False)
    result=[]; already_broken=set()
    for event in range(5,len(ws)):
        eligible=[p for p in highs if p[1]<event and p[0] not in already_broken and ws[event]['c']>p[2]*1.003]
        if not eligible: continue
        broken=max(eligible,key=lambda p:p[0]); already_broken.add(broken[0])
        protected=[p for p in lows if p[1]<event]
        if not protected: continue
        floor=max(protected,key=lambda p:p[0])
        invalid=next((j for j in range(event+1,len(ws)) if ws[j]['c']<floor[2]),None)
        result.append((event,broken,floor,invalid))
    return result


def context_at(items,ws,date):
    valid=[x for x in items if ws[x[0]]['end']<date and (x[3] is None or date<=ws[x[3]]['end'])]
    return max(valid,key=lambda x:x[0]) if valid else None


def selected_ssl_at(daily,weekly,items,raid):
    lows=pivot_indices(daily,'l',3,3,False); consumed=set(); selected=None
    for i in range(7,raid+1):
        if context_at(items,weekly,daily[i]['t']) is None: continue
        eligible=[p for p in lows if p[1]<=i and p[0]<i and p[0] not in consumed and daily[i]['l']<p[2]*.997 and daily[i]['c']>p[2]]
        if not eligible: continue
        chosen=max(eligible,key=lambda p:p[0]); consumed.add(chosen[0])
        if i==raid: selected=chosen
    return selected


def lifecycle(daily,choch,zl,zh):
    touch=reclaim=None
    for i in range(choch+1,min(len(daily),choch+21)):
        b=daily[i]
        if b['c']<zl: return None
        if touch is None:
            if b['l']<=zh and b['h']>=zl: touch=i
        elif reclaim is None:
            if i>touch and b['c']>zh: reclaim=i
        elif i>reclaim and b['c']>zh and b['l']>=zl:
            return touch,reclaim,i,i+1 if i+1<len(daily) else None
    return None


def audit(row,daily):
    weekly=completed_weeks(daily); items=contexts(weekly)
    raid=integer(row['daily_raid_idx']); choch=integer(row['daily_choch_idx']); ob=integer(row['daily_demand_ob_idx'])
    if max(raid,choch,ob)>=len(daily): return 'DAILY_INDEX_RANGE'
    ctx=context_at(items,weekly,daily[raid]['t'])
    if ctx is None: return 'NO_ACTIVE_WEEKLY_CONTEXT'
    event,broken,floor,invalid=ctx
    expected_context=(event,broken[0],broken[1],floor[0],floor[1],invalid if invalid is not None else '')
    actual_context=(integer(row['weekly_bos_idx']),integer(row['weekly_broken_high_idx']),integer(row['weekly_broken_high_confirm_idx']),integer(row['weekly_protected_low_idx']),integer(row['weekly_protected_low_confirm_idx']),integer(row['weekly_context_invalid_idx']) if row['weekly_context_invalid_idx'] else '')
    if expected_context!=actual_context: return 'WEEKLY_CONTEXT_MISMATCH'
    if weekly[event]['end']!=row['weekly_bos_end_date'] or abs(broken[2]-num(row['weekly_broken_high']))>1e-5 or abs(floor[2]-num(row['weekly_protected_low']))>1e-5: return 'WEEKLY_CONTEXT_FIELD_MISMATCH'
    ssl=selected_ssl_at(daily,weekly,items,raid)
    if ssl is None: return 'SSL_SELECTION_MISMATCH'
    if (ssl[0],ssl[1])!=(integer(row['daily_ssl_idx']),integer(row['daily_ssl_confirm_idx'])) or abs(ssl[2]-num(row['daily_ssl_level']))>1e-5: return 'SSL_FIELD_MISMATCH'
    highs=pivot_indices(daily,'h',3,3,True); visible=[p for p in highs if p[1]<=raid and p[0]<raid]
    if not visible: return 'NO_VISIBLE_DAILY_HIGH'
    high=max(visible,key=lambda p:p[0])
    if (high[0],high[1])!=(integer(row['daily_swing_high_idx']),integer(row['daily_swing_high_confirm_idx'])) or abs(high[2]-num(row['daily_choch_break_level']))>1e-5: return 'DAILY_HIGH_MISMATCH'
    first=next((j for j in range(raid+1,min(len(daily),raid+11)) if daily[j]['c']>high[2]*1.002),None)
    if first!=choch or daily[choch]['t']!=row['daily_choch_date']: return 'CHOCH_MISMATCH'
    nearest=next((j for j in range(choch-1,max(raid-1,choch-7),-1) if daily[j]['c']<daily[j]['o']),None)
    if nearest!=ob or daily[ob]['t']!=row['daily_demand_ob_date']: return 'OB_MISMATCH'
    zl=daily[ob]['l']; zh=max(daily[ob]['o'],daily[ob]['c'])
    if abs(zl-num(row['zone_low']))>1e-5 or abs(zh-num(row['zone_high']))>1e-5: return 'ZONE_MISMATCH'
    life=lifecycle(daily,choch,zl,zh)
    expected=(integer(row['touch_idx']),integer(row['reclaim_idx']),integer(row['hold_idx']),integer(row['eligible_entry_idx']))
    if life!=expected: return 'LIFECYCLE_MISMATCH'
    dates=tuple(daily[i]['t'] for i in expected)
    if dates!=(row['touch_date'],row['reclaim_date'],row['hold_date'],row['eligible_entry_date']): return 'DATE_MISMATCH'
    if not (event<len(weekly) and ssl[0]<ssl[1]<=raid<choch<=ob+6 and raid<=ob<choch<expected[0]<expected[1]<expected[2]<expected[3]): return 'CHRONOLOGY_MISMATCH'
    return 'PASS'


def main():
    source=json.loads(SRC.read_text())
    if source.get('decision')!='WEEKLY_BOS_DAILY_SSL_SEEDS_READY__INDEPENDENT_ORACLE_NEXT': raise RuntimeError('V511 gate failed')
    with open(source['artifacts']['seeds']) as h: rows=list(csv.DictReader(h))
    forbidden=sorted(set(rows[0])&FORBIDDEN) if rows else []
    grouped=defaultdict(list)
    for row in rows: grouped[row['symbol']].append(row)
    counts=Counter(); passed=[]; mismatch=[]; OUT.mkdir(parents=True,exist_ok=True)
    for n,(sym,items) in enumerate(grouped.items(),1):
        daily=bars(sym)
        for row in items:
            reason=audit(row,daily) if daily else 'MISSING_KLINE'; counts[reason]+=1
            if reason=='PASS': passed.append(row)
            elif len(mismatch)<200: mismatch.append({'symbol':sym,'eligible_entry_date':row['eligible_entry_date'],'reason':reason})
        if n%500==0: print(json.dumps({'symbols':n,'passed':counts['PASS'],'failed':sum(v for k,v in counts.items() if k!='PASS')}),flush=True)
    passed_file=OUT/'v512_oracle_passed_seeds.csv'; mismatch_file=OUT/'v512_oracle_mismatches.csv'; fields=list(rows[0]) if rows else ['symbol']
    with passed_file.open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(passed)
    with mismatch_file.open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=['symbol','eligible_entry_date','reason']); w.writeheader(); w.writerows(mismatch)
    failures=len(rows)-counts['PASS']; ok=bool(rows) and failures==0 and not forbidden
    result={'version':'V512_WEEKLY_BOS_DAILY_SSL_REVERSAL_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'source_seed_count':len(rows),'oracle_pass_count':counts['PASS'],'oracle_failure_count':failures,'reason_counts':dict(counts),'forbidden_outcome_headers':forbidden,
      'invariants':{'raw_bar_weekly_reaggregation':True,'weekly_context_rederived':True,'daily_pivots_and_first_events_rederived':True,'lifecycle_rederived':True,'zero_mismatch':failures==0,'no_outcome_fields':not forbidden},
      'decision':'WEEKLY_BOS_DAILY_SSL_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if ok else 'WEEKLY_BOS_DAILY_SSL_ORACLE_FAIL__NO_REPLAY','artifacts':{'out_dir':str(OUT),'passed_seeds':str(passed_file),'mismatches':str(mismatch_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v512_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
