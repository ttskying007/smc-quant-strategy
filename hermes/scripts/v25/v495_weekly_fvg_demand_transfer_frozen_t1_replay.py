#!/usr/bin/env python3
"""V495 one-shot frozen strict-T+1 replay for weekly-FVG demand transfer."""
from __future__ import annotations
import csv,json,math,statistics
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit';SRC=AUD/'v494_weekly_fvg_demand_transfer_oracle_latest.json'
OUT=AUD/f"v495_weekly_fvg_demand_transfer_frozen_t1_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v495_weekly_fvg_demand_transfer_frozen_t1_replay_latest.json'
FEE=.2;HOLD=30;GATE={'n':300,'each_year_n':40,'gross_wr_pct':55.0,'avg_net_pnl_pct':.5,'each_year_gross_wr_pct':50.0,'each_year_avg_net_pnl_pct':0.0,'profit_factor':1.15,'payoff_rr':.7,'t1_violations':0}
STOP={'WEEKLY_FVG_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}

def f(x):
    try:v=float(x);return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError):return 0.0

def integer(x):return int(float(x))
def ds(x):return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def load(sym):
    try:raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError):return []
    out=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')};d=ds(b.get('t') or b.get('date'))
        if d and min(r.values())>0:r['t']=d;out.append(r)
    return sorted(out,key=lambda x:x['t'])

def weeks(daily):
    groups=[];key=None
    for b in daily:
        d=datetime.strptime(b['t'],'%Y%m%d').date();k=d.isocalendar()[:2]
        if k!=key:groups.append([]);key=k
        groups[-1].append(b)
    return [{'end':g[-1]['t'],'h':max(x['h'] for x in g)} for g in groups[:-1]]

def weekly_targets(daily):
    ws=weeks(daily);cands=[]
    for i in range(2,len(ws)-2):
        if ws[i]['h']>max(ws[j]['h'] for j in range(i-2,i+3) if j!=i):
            cands.append((ws[i+2]['end'],ws[i]['h']))
    return cands

def target_visible(targets,hold_date,entry):
    cands=[price for confirm_date,price in targets if confirm_date<=hold_date and price>entry]
    return min(cands) if cands else None

def replay(seed,bars,targets):
    e=integer(seed['eligible_entry_idx']);h=integer(seed['hold_idx'])
    if e!=h+1 or e>=len(bars):return {'status':'UNOBSERVED_ENTRY'}
    entry=bars[e]['o'];sl=f(seed['zone_low'])*.99;target=target_visible(targets,seed['hold_date'],entry)
    if entry<=0 or sl<=0 or sl>=entry:return {'status':'INVALID_RISK','entry_date':bars[e]['t']}
    if target is not None and target<=entry:return {'status':'TARGET_CONSUMED_AT_ENTRY','entry_date':bars[e]['t']}
    first=e+1;last=e+HOLD
    if last>=len(bars):return {'status':'OPEN_RIGHT_EDGE','entry_date':bars[e]['t']}
    x=last;price=bars[last]['c'];reason='TIME30_NO_WEEKLY_BSL' if target is None else 'TIME30_WEEKLY_BSL_UNREACHED';collision=False
    for i in range(first,last+1):
        b=bars[i]
        if b['o']<=sl:x,price,reason=i,b['o'],'SL_GAP_T1';break
        if target is not None and b['o']>=target:x,price,reason=i,b['o'],'WEEKLY_BSL_GAP_TP_T1';break
        hs=b['l']<=sl;ht=target is not None and b['h']>=target
        if hs and ht:x,price,reason,collision=i,sl,'SL_TP_COLLISION_CONSERVATIVE_T1',True;break
        if hs:x,price,reason=i,sl,'WEEKLY_FVG_SL_T1';break
        if ht:x,price,reason=i,target,'WEEKLY_BSL_TP_T1';break
    gross=(price/entry-1)*100;net=gross-FEE;risk=(entry/sl-1)*100;planned=((target/entry-1)*100/risk) if target else None
    return {'status':'CLOSED','entry_idx':e,'entry_date':bars[e]['t'],'entry_price':round(entry,6),'sl':round(sl,6),'risk_pct':round(risk,4),'tp':round(target,6) if target else '',
      'planned_rr':round(planned,4) if planned is not None else '','exit_idx':x,'exit_date':bars[x]['t'],'exit_price':round(price,6),'exit_reason':reason,'hold_bars':x-e,
      'gross_pnl_pct':round(gross,4),'net_pnl_pct':round(net,4),'realized_r':round(gross/risk,4),'t1_violation':bars[x]['t']<=bars[e]['t'],'same_bar_collision':collision}

def stats(rows):
    if not rows:return {'n':0}
    g=[f(r['gross_pnl_pct']) for r in rows];n=[f(r['net_pnl_pct']) for r in rows];w=[x for x in n if x>0];l=[x for x in n if x<=0];aw=sum(w)/len(w) if w else 0;al=sum(l)/len(l) if l else 0
    planned=[f(r['planned_rr']) for r in rows if r.get('planned_rr') not in ('',None)]
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in g)/len(rows)*100,4),'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in n)/len(rows)*100,4),'avg_net_pnl_pct':round(sum(n)/len(rows),4),'median_net_pnl_pct':round(statistics.median(n),4),'avg_win_pct':round(aw,4),'avg_loss_pct':round(al,4),'payoff_rr':round(aw/abs(al),4) if al else 0,'profit_factor':round(sum(w)/abs(sum(l)),4) if l and sum(l) else 0,'cum_net_pnl_pct':round(sum(n),4),'avg_planned_rr':round(sum(planned)/len(planned),4) if planned else 0,'avg_realized_r':round(sum(f(r['realized_r']) for r in rows)/len(rows),4),'sl_pct':round(sum(r['exit_reason'] in STOP for r in rows)/len(rows)*100,4)}

def main():
    src=json.loads(SRC.read_text())
    if src.get('decision')!='WEEKLY_FVG_TRANSFER_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED':raise RuntimeError('V494 gate failed')
    with open(src['artifacts']['passed_seeds']) as h:seeds=list(csv.DictReader(h))
    grouped=defaultdict(list)
    for s in seeds:grouped[s['symbol']].append(s)
    rows=[];OUT.mkdir(parents=True,exist_ok=True)
    for i,(sym,items) in enumerate(grouped.items(),1):
        bars=load(sym);targets=weekly_targets(bars)
        for s in items:rows.append({**s,'execution_contract':'NEXT_OPEN__WEEKLY_FVG_SL1PCT__VISIBLE_WEEKLY_BSL__TIME30__T1__FEE0P2',**replay(s,bars,targets)})
        if i%500==0:print(json.dumps({'symbols':i,'rows':len(rows)}),flush=True)
    closed=[r for r in rows if r.get('status')=='CLOSED' and r['entry_date'][:4] in {'2023','2024','2025','2026'}];overall=stats(closed);yearly={y:stats([r for r in closed if r['entry_date'][:4]==y]) for y in ('2023','2024','2025','2026')};t1=sum(bool(r.get('t1_violation')) for r in closed)
    passed=overall['n']>=300 and overall['gross_wr_pct']>=55 and overall['avg_net_pnl_pct']>=.5 and overall['profit_factor']>=1.15 and overall['payoff_rr']>=.7 and all(yearly[y]['n']>=40 and yearly[y]['gross_wr_pct']>=50 and yearly[y]['avg_net_pnl_pct']>0 for y in yearly) and t1==0
    file=OUT/'v495_frozen_t1_rows.csv';fields=sorted({k for r in rows for k in r})
    with file.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    result={'version':'V495_WEEKLY_FVG_DEMAND_TRANSFER_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_before_outcomes':{'entry':'next open after daily hold','sl':'weekly bullish FVG zone_low*0.99','target':'nearest confirmed weekly swing high visible by hold','exit':'strict T+1 target/SL/time30, gap-aware, collision=SL','fee_pct':FEE,'search_count':1,'promotion_gate':GATE},
      'seed_count':len(seeds),'status_counts':dict(Counter(r.get('status') for r in rows)),'research_window_closed_n':len(closed),'overall':overall,'yearly':yearly,'exit_reason_counts':dict(Counter(r['exit_reason'] for r in closed)),
      'invariants':{'t1_violations':t1,'same_bar_collisions':sum(bool(r.get('same_bar_collision')) for r in closed),'search_count':1,'source_oracle_pass':True},'promotion_gate_pass':passed,
      'decision':'WEEKLY_FVG_TRANSFER_PROMOTION_GATE_PASS__INDEPENDENT_METRIC_AUDIT_NEXT' if passed else 'WEEKLY_FVG_TRANSFER_ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS','artifacts':{'out_dir':str(OUT),'rows':str(file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v495_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
