#!/usr/bin/env python3
"""V513 one-shot frozen strict-T+1 replay for V512 cross-timeframe reversal seeds."""
from __future__ import annotations
import csv,json,math,statistics
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes');KDIR=ROOT/'kline_cache';AUD=ROOT/'smc_audit';SRC=AUD/'v512_weekly_bos_daily_ssl_reversal_oracle_latest.json'
OUT=AUD/f"v513_weekly_bos_daily_ssl_reversal_frozen_t1_no_write_{datetime.now():%Y%m%d_%H%M%S}";LATEST=AUD/'v513_weekly_bos_daily_ssl_reversal_frozen_t1_replay_latest.json'
FEE=.2;HOLD=30;YEARS=('2023','2024','2025','2026')
GATE={'n':300,'each_year_n':40,'gross_wr_pct':55.0,'avg_net_pnl_pct':.5,'each_year_gross_wr_pct':50.0,'each_year_avg_net_pnl_pct':0.0,'profit_factor':1.15,'payoff_rr':.7,'t1_violations':0}
STOP={'DAILY_RAID_STRUCTURE_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}


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
        q={k:f(b.get(k)) for k in ('o','h','l','c')};d=ds(b.get('t') or b.get('date'))
        if d and min(q.values())>0:q['t']=d;out.append(q)
    return sorted(out,key=lambda x:x['t'])


def completed_week_highs(daily):
    groups=[];key=None
    for b in daily:
        k=datetime.strptime(b['t'],'%Y%m%d').date().isocalendar()[:2]
        if k!=key:groups.append([]);key=k
        groups[-1].append(b)
    ws=[{'end':g[-1]['t'],'h':max(x['h'] for x in g)} for g in groups[:-1] if g]
    return [(ws[i+2]['end'],ws[i]['h']) for i in range(2,len(ws)-2) if all(ws[i]['h']>ws[j]['h'] for j in range(i-2,i+3) if j!=i)]


def visible_target(targets,hold_date,entry):
    candidates=[price for visible,price in targets if visible<=hold_date and price>entry]
    return min(candidates) if candidates else None


def replay(seed,bars,targets):
    e=integer(seed['eligible_entry_idx']);h=integer(seed['hold_idx'])
    if e!=h+1 or e>=len(bars):return {'status':'UNOBSERVED_ENTRY'}
    entry=bars[e]['o'];sl=f(seed['daily_raid_low'])*.99;target=visible_target(targets,seed['hold_date'],entry)
    if entry<=0 or sl<=0 or sl>=entry:return {'status':'INVALID_RISK','entry_idx':e,'entry_date':bars[e]['t']}
    first=e+1;last=e+HOLD
    if last>=len(bars):return {'status':'OPEN_RIGHT_EDGE','entry_idx':e,'entry_date':bars[e]['t']}
    x=last;price=bars[last]['c'];reason='TIME30_NO_VISIBLE_WEEKLY_BSL' if target is None else 'TIME30_WEEKLY_BSL_UNREACHED';collision=False
    for i in range(first,last+1):
        b=bars[i]
        if b['o']<=sl:x,price,reason=i,b['o'],'SL_GAP_T1';break
        if target is not None and b['o']>=target:x,price,reason=i,b['o'],'WEEKLY_BSL_GAP_TP_T1';break
        hit_sl=b['l']<=sl;hit_tp=target is not None and b['h']>=target
        if hit_sl and hit_tp:x,price,reason,collision=i,sl,'SL_TP_COLLISION_CONSERVATIVE_T1',True;break
        if hit_sl:x,price,reason=i,sl,'DAILY_RAID_STRUCTURE_SL_T1';break
        if hit_tp:x,price,reason=i,target,'WEEKLY_BSL_TP_T1';break
    gross=(price/entry-1)*100;net=gross-FEE;risk=(entry/sl-1)*100;planned=((target/entry-1)*100/risk) if target else None
    return {'status':'CLOSED','entry_idx':e,'entry_date':bars[e]['t'],'entry_price':round(entry,6),'sl':round(sl,6),'risk_pct':round(risk,4),'tp':round(target,6) if target else '',
      'planned_rr':round(planned,4) if planned is not None else '','exit_idx':x,'exit_date':bars[x]['t'],'exit_price':round(price,6),'exit_reason':reason,'hold_bars':x-e,
      'gross_pnl_pct':round(gross,4),'net_pnl_pct':round(net,4),'realized_r':round(gross/risk,4),'t1_violation':bars[x]['t']<=bars[e]['t'],'same_bar_collision':collision}


def stats(rows):
    if not rows:return {'n':0}
    gross=[f(r['gross_pnl_pct']) for r in rows];net=[f(r['net_pnl_pct']) for r in rows];wins=[x for x in net if x>0];losses=[x for x in net if x<=0]
    aw=sum(wins)/len(wins) if wins else 0;al=sum(losses)/len(losses) if losses else 0;planned=[f(r['planned_rr']) for r in rows if r.get('planned_rr') not in ('',None)]
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in gross)/len(rows)*100,4),'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in net)/len(rows)*100,4),'avg_net_pnl_pct':round(sum(net)/len(rows),4),'median_net_pnl_pct':round(statistics.median(net),4),'avg_win_pct':round(aw,4),'avg_loss_pct':round(al,4),'payoff_rr':round(aw/abs(al),4) if al else 0,'profit_factor':round(sum(wins)/abs(sum(losses)),4) if losses and sum(losses) else 0,'cum_net_pnl_pct':round(sum(net),4),'avg_planned_rr':round(sum(planned)/len(planned),4) if planned else 0,'avg_realized_r':round(sum(f(r['realized_r']) for r in rows)/len(rows),4),'sl_pct':round(sum(r['exit_reason'] in STOP for r in rows)/len(rows)*100,4)}


def main():
    src=json.loads(SRC.read_text())
    if src.get('decision')!='WEEKLY_BOS_DAILY_SSL_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED':raise RuntimeError('V512 gate failed')
    with open(src['artifacts']['passed_seeds']) as h:seeds=list(csv.DictReader(h))
    grouped=defaultdict(list)
    for seed in seeds:grouped[seed['symbol']].append(seed)
    rows=[];OUT.mkdir(parents=True,exist_ok=True)
    for n,(sym,items) in enumerate(grouped.items(),1):
        daily=load(sym);targets=completed_week_highs(daily);busy_until=-1
        for seed in sorted(items,key=lambda x:integer(x['eligible_entry_idx'])):
            entry_idx=integer(seed['eligible_entry_idx'])
            if entry_idx<=busy_until:
                rows.append({**seed,'status':'OVERLAP_SUPPRESSED_SERIAL','entry_idx':entry_idx});continue
            result=replay(seed,daily,targets);rows.append({**seed,'execution_contract':'NEXT_OPEN__DAILY_RAID_STRUCTURE_SL1PCT__VISIBLE_WEEKLY_BSL__TIME30__SERIAL_T1__FEE0P2',**result})
            if result.get('status')=='CLOSED':busy_until=integer(result['exit_idx'])
        if n%500==0:print(json.dumps({'symbols':n,'rows':len(rows)}),flush=True)
    closed=[r for r in rows if r.get('status')=='CLOSED' and r['entry_date'][:4] in set(YEARS)];overall=stats(closed);yearly={y:stats([r for r in closed if r['entry_date'][:4]==y]) for y in YEARS};t1=sum(bool(r.get('t1_violation')) for r in closed)
    passed=overall['n']>=GATE['n'] and overall['gross_wr_pct']>=GATE['gross_wr_pct'] and overall['avg_net_pnl_pct']>=GATE['avg_net_pnl_pct'] and overall['profit_factor']>=GATE['profit_factor'] and overall['payoff_rr']>=GATE['payoff_rr'] and all(yearly[y]['n']>=GATE['each_year_n'] and yearly[y]['gross_wr_pct']>=GATE['each_year_gross_wr_pct'] and yearly[y]['avg_net_pnl_pct']>0 for y in YEARS) and t1==0
    file=OUT/'v513_frozen_t1_rows.csv';fields=sorted({k for r in rows for k in r})
    with file.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    result={'version':'V513_WEEKLY_BOS_DAILY_SSL_REVERSAL_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_before_outcomes':{'entry':'next open after daily SSL/CHOCH demand touch/reclaim/hold inside active weekly bull BOS context','sl':'daily raid low*0.99','target':'nearest higher confirmed weekly swing high visible by hold','exit':'strict T+1 target/SL/time30, gap-aware, collision=SL','serial':'one open setup per symbol; overlapping entries suppressed','fee_pct':FEE,'search_count':1,'promotion_gate':GATE},
      'seed_count':len(seeds),'status_counts':dict(Counter(r.get('status') for r in rows)),'research_window_closed_n':len(closed),'overall':overall,'yearly':yearly,'exit_reason_counts':dict(Counter(r['exit_reason'] for r in closed)),
      'invariants':{'t1_violations':t1,'same_bar_collisions':sum(bool(r.get('same_bar_collision')) for r in closed),'duplicate_symbol_entry':len(closed)-len(set((r['symbol'],r['entry_date']) for r in closed)),'serial_overlap_suppressed':sum(r.get('status')=='OVERLAP_SUPPRESSED_SERIAL' for r in rows),'search_count':1,'source_oracle_pass':True},'promotion_gate_pass':passed,
      'decision':'WEEKLY_BOS_DAILY_SSL_PROMOTION_GATE_PASS__INDEPENDENT_METRIC_AUDIT_NEXT' if passed else 'WEEKLY_BOS_DAILY_SSL_ECONOMIC_GATE_FAIL__INDEPENDENT_METRIC_AUDIT_THEN_CLOSE','artifacts':{'out_dir':str(OUT),'rows':str(file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v513_report.json').write_text(text);LATEST.write_text(text);print(text)

if __name__=='__main__':main()
