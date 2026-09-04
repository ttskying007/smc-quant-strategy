#!/usr/bin/env python3
"""V423 frozen T+1 structural replay for V422 failed-breakdown breakers."""
from __future__ import annotations
import csv,json,math
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean,median
ROOT=Path('/root/.hermes'); AUD=ROOT/'smc_audit'; KDIR=ROOT/'kline_cache'
SRC=AUD/'v422_failed_breakdown_breaker_latest.json'
OUT=AUD/f'v423_failed_breakdown_frozen_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v423_failed_breakdown_frozen_replay_latest.json'; FEE=.2; HOLD=20

def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0
def day(b): return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]
def load(sym):
    try: raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except Exception:return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k))>0 for k in ('o','h','l','c'))],key=day)
def highs(ks):
    return [(i,f(ks[i]['h']),i+3) for i in range(3,len(ks)-3) if all(f(ks[i]['h'])>f(ks[j]['h']) for j in range(i-3,i+4) if j!=i)]
def met(rows):
    if not rows:return {'n':0}
    p=[r['net_pnl_pct'] for r in rows]; w=[x for x in p if x>0]; l=[x for x in p if x<=0]
    return {'n':len(rows),'win_rate_pct':round(len(w)/len(rows)*100,4),'avg_net_pnl_pct':round(mean(p),4),'median_net_pnl_pct':round(median(p),4),
      'profit_factor':round(sum(w)/abs(sum(l)),4) if l and sum(l) else None,'avg_win_pct':round(mean(w),4) if w else None,
      'avg_loss_pct':round(mean(l),4) if l else None,'payoff_ratio':round(mean(w)/abs(mean(l)),4) if w and l and mean(l) else None,
      'sl_rate_pct':round(sum(r['exit_reason'].startswith('SL') for r in rows)/len(rows)*100,4),
      'tp_rate_pct':round(sum(r['exit_reason']=='STRUCTURAL_TP' for r in rows)/len(rows)*100,4),
      'time_exit_rate_pct':round(sum(r['exit_reason']=='TIME_EXIT_20S' for r in rows)/len(rows)*100,4),
      'avg_planned_rr':round(mean(r['planned_rr'] for r in rows if r['planned_rr'] is not None),4) if any(r['planned_rr'] is not None for r in rows) else None,
      'target_coverage_pct':round(sum(r['tp_price'] is not None for r in rows)/len(rows)*100,4),'avg_hold_sessions':round(mean(r['hold_sessions'] for r in rows),2)}
def main():
    OUT.mkdir(parents=True,exist_ok=True); src=json.loads(SRC.read_text())
    with Path(src['artifacts']['rows']).open(newline='') as h: seeds=[r for r in csv.DictReader(h) if r['lifecycle_state']=='TAKEOVER_CONFIRMED']
    cache={}; rows=[]; skip=Counter()
    for s in seeds:
        sym=s['symbol']
        if sym not in cache:
            ks=load(sym); cache[sym]=(ks,{day(b):i for i,b in enumerate(ks)},highs(ks))
        ks,idxmap,ph=cache[sym]; ti=idxmap.get(s['takeover_date'])
        if ti is None or ti+2>=len(ks):skip['NO_T1_ENTRY_OR_EXIT_SESSION']+=1;continue
        ei=ti+1; entry=f(ks[ei]['o']); sl=f(s['break_low'])*.995
        if not entry>sl>0:skip['INVALID_STRUCTURAL_RISK']+=1;continue
        targets=[price for _,price,ci in ph if ci<=ti and price>entry]; tp=min(targets) if targets else None
        risk=entry-sl; rr=(tp-entry)/risk if tp is not None else None
        xi=min(len(ks)-1,ei+HOLD); xp=f(ks[xi]['c']); reason='TIME_EXIT_20S'
        for i in range(ei+1,min(len(ks),ei+HOLD+1)):
            o,lo,hi=f(ks[i]['o']),f(ks[i]['l']),f(ks[i]['h'])
            if o<=sl:xi,xp,reason=i,o,'SL_GAP';break
            if lo<=sl:xi,xp,reason=i,sl,'SL_HIT';break
            if tp is not None and hi>=tp:xi,xp,reason=i,tp,'STRUCTURAL_TP';break
        gross=(xp/entry-1)*100; net=gross-FEE
        rows.append({**{k:s[k] for k in ('symbol','combo_key','pivot_date','break_date','recovery_date','sos_date','takeover_date','break_low','zone_low','zone_high')},
          'entry_date':day(ks[ei]),'entry_price':round(entry,6),'sl_price':round(sl,6),'tp_price':round(tp,6) if tp is not None else None,
          'planned_rr':round(rr,6) if rr is not None else None,'exit_date':day(ks[xi]),'exit_price':round(xp,6),'exit_reason':reason,
          'hold_sessions':xi-ei,'gross_pnl_pct':round(gross,6),'fee_pct':FEE,'net_pnl_pct':round(net,6),'won':net>0,'t1_violation':xi<=ei})
    rp=OUT/'v423_trade_rows.csv'; fields=list(rows[0]) if rows else ['symbol']
    with rp.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    yearly={y:met([r for r in rows if r['entry_date'].startswith(y)]) for y in ('2023','2024','2025','2026')}
    report={'version':'V423_FAILED_BREAKDOWN_FROZEN_STRUCTURAL_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'source':str(SRC),
      'frozen_execution_contract':'takeover->next-session open; SL=breakdown low*0.995; TP=nearest higher confirmed pre-entry swing high; SL-first; 20-session time exit; 0.2% cost',
      'candidate_takeovers':len(seeds),'replayed':len(rows),'skipped':dict(skip),'overall':met(rows),'by_entry_year':yearly,
      'exit_reasons':dict(Counter(r['exit_reason'] for r in rows)),
      'invariants':{'all_t1_compliant':all(not r['t1_violation'] for r in rows),'no_parameter_or_exit_search':True,'one_frozen_replay':True},
      'decision':'RESEARCH_ONLY__ASSESS_ECONOMIC_AND_YEARLY_STABILITY_BEFORE_ANY_PROMOTION','artifacts':{'out_dir':str(OUT),'rows':str(rp),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2);(OUT/'v423_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
