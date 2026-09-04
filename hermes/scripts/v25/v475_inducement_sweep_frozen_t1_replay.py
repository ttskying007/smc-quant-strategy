#!/usr/bin/env python3
"""V475 one-shot frozen strict-T+1 replay for V473/V474 inducement sweep."""
from __future__ import annotations
import csv,json,math,statistics
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v474_inducement_sweep_oracle_latest.json'; OUT=AUD/f"v475_inducement_sweep_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}"; LATEST=AUD/'v475_inducement_sweep_frozen_t1_replay_latest.json'
STOP_BUFFER=.99; MAX_HOLD=20; FEE_PCT=.2; YEARS=('2023','2024','2025','2026')
GATE={'n':300,'each_year_n':40,'gross_wr_pct':55.0,'avg_net_pnl_pct':.5,'each_year_gross_wr_pct':50.0,'each_year_avg_net_pnl_pct':0.0,'profit_factor':1.15,'payoff_rr':.7,'t1_violations':0}
STOP_REASONS={'STRUCTURAL_INDUCEMENT_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}
def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0
def ii(x): return int(float(x))
def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]
def load(sym):
    try: raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}; d=ds(b.get('t') or b.get('date'))
        if d and all(r.values()): r['t']=d; rows.append(r)
    return sorted(rows,key=lambda x:x['t'])
def highs(bars):
    return [(p,p+3,bars[p]['h'],bars[p]['t']) for p in range(3,len(bars)-3) if all(bars[p]['h']>bars[j]['h'] for j in range(p-3,p+4) if j!=p)]
def target_at(items,cutoff,entry): return min(((v,d) for _,visible,v,d in items if visible<=cutoff and v>entry),default=(None,''),key=lambda x:x[0])
def replay(seed,bars,hh):
    entry_i=ii(seed['eligible_entry_idx']); confirm=ii(seed['reversal_confirm_idx'])
    if entry_i!=confirm+1 or entry_i>=len(bars): return {'status':'UNOBSERVED_ENTRY'}
    entry=bars[entry_i]['o']; sl=f(seed['structural_sl_ref'])*STOP_BUFFER
    if entry<=0 or sl<=0 or sl>=entry: return {'status':'INVALID_RISK','entry_date':bars[entry_i]['t']}
    target,target_date=target_at(hh,confirm,entry); first=entry_i+1; last=entry_i+MAX_HOLD
    if last>=len(bars): return {'status':'OPEN_RIGHT_EDGE','entry_date':bars[entry_i]['t']}
    exit_i=last; exit_price=bars[last]['c']; reason='TIME20_NO_KNOWN_BSL' if target is None else 'TIME20_BSL_UNREACHED'; collision=False
    for j in range(first,last+1):
        b=bars[j]
        if b['o']<=sl: exit_i,exit_price,reason=j,b['o'],'SL_GAP_T1'; break
        if target is not None and b['o']>=target: exit_i,exit_price,reason=j,b['o'],'BSL_GAP_TP_T1'; break
        hit_sl=b['l']<=sl; hit_tp=target is not None and b['h']>=target
        if hit_sl and hit_tp: exit_i,exit_price,reason,collision=j,sl,'SL_TP_COLLISION_CONSERVATIVE_T1',True; break
        if hit_sl: exit_i,exit_price,reason=j,sl,'STRUCTURAL_INDUCEMENT_SL_T1'; break
        if hit_tp: exit_i,exit_price,reason=j,target,'KNOWN_BSL_TP_T1'; break
    gross=(exit_price/entry-1)*100; net=gross-FEE_PCT; risk=(entry/sl-1)*100
    return {'status':'CLOSED','entry_idx':entry_i,'entry_date':bars[entry_i]['t'],'entry_price':round(entry,6),'sl':round(sl,6),'risk_pct':round(risk,4),'tp':'' if target is None else round(target,6),'tp_anchor_date':target_date,'exit_idx':exit_i,'exit_date':bars[exit_i]['t'],'exit_price':round(exit_price,6),'exit_reason':reason,'hold_bars':exit_i-entry_i,'gross_pnl_pct':round(gross,4),'net_pnl_pct':round(net,4),'realized_r':round(gross/risk,4) if risk else 0.0,'t1_violation':bars[exit_i]['t']<=bars[entry_i]['t'],'same_bar_collision':collision}
def stats(rows):
    if not rows:return {'n':0}
    gross=[f(r['gross_pnl_pct']) for r in rows]; net=[f(r['net_pnl_pct']) for r in rows]; pos=[x for x in net if x>0]; neg=[x for x in net if x<=0]
    aw=sum(pos)/len(pos) if pos else 0; al=sum(neg)/len(neg) if neg else 0; pf=sum(pos)/abs(sum(neg)) if neg and sum(neg) else 0
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in gross)/len(rows)*100,4),'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in net)/len(rows)*100,4),'avg_gross_pnl_pct':round(sum(gross)/len(rows),4),'avg_net_pnl_pct':round(sum(net)/len(rows),4),'median_net_pnl_pct':round(statistics.median(net),4),'avg_win_pct':round(aw,4),'avg_loss_pct':round(al,4),'payoff_rr':round(aw/abs(al),4) if al else 0,'profit_factor':round(pf,4),'cum_net_pnl_pct':round(sum(net),4),'avg_realized_r':round(sum(f(r['realized_r']) for r in rows)/len(rows),4),'sl_pct':round(sum(r['exit_reason'] in STOP_REASONS for r in rows)/len(rows)*100,4)}
def gate(overall,yearly,t1):
    return overall.get('n',0)>=GATE['n'] and overall.get('gross_wr_pct',0)>=GATE['gross_wr_pct'] and overall.get('avg_net_pnl_pct',-99)>=GATE['avg_net_pnl_pct'] and overall.get('profit_factor',0)>=GATE['profit_factor'] and overall.get('payoff_rr',0)>=GATE['payoff_rr'] and all(yearly[y].get('n',0)>=GATE['each_year_n'] and yearly[y].get('gross_wr_pct',0)>=GATE['each_year_gross_wr_pct'] and yearly[y].get('avg_net_pnl_pct',-99)>0 for y in YEARS) and t1==0
def main():
    src=json.loads(SRC.read_text())
    if src.get('decision')!='INDEPENDENT_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED': raise RuntimeError('V474 oracle gate failed')
    with open(src['artifacts']['passed_seeds']) as h: seeds=list(csv.DictReader(h))
    OUT.mkdir(parents=True,exist_ok=True); grouped=defaultdict(list)
    for s in seeds: grouped[s['symbol']].append(s)
    rows=[]
    for n,(sym,items) in enumerate(grouped.items(),1):
        bars=load(sym); hh=highs(bars)
        for seed in items: rows.append({**seed,'execution_contract':'NEXT_OPEN__RAID_LOW_1PCT_SL__KNOWN_BSL_OR_TIME20__STRICT_T1__FEE0P2',**replay(seed,bars,hh)})
        if n%500==0: print(json.dumps({'symbols':n,'rows':len(rows)}),flush=True)
    closed=[r for r in rows if r.get('status')=='CLOSED' and r['entry_date'][:4] in YEARS]; yearly={y:stats([r for r in closed if r['entry_date'][:4]==y]) for y in YEARS}; overall=stats(closed); t1=sum(bool(r.get('t1_violation')) for r in closed); passed=gate(overall,yearly,t1)
    row_file=OUT/'v475_frozen_t1_rows.csv'; fields=sorted({k for r in rows for k in r})
    with row_file.open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    result={'version':'V475_INDUCEMENT_SWEEP_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'frozen_before_outcomes':{'entry':'next open after internal-low raid reversal confirmation','sl':'raid low * 0.99','target':'nearest pre-entry confirmed swing high','exit':'strict T+1 target/SL/time20, gap-aware, collision=SL','fee_pct':FEE_PCT,'search_count':1,'promotion_gate':GATE},'seed_count':len(seeds),'status_counts':dict(Counter(r.get('status') for r in rows)),'research_window_closed_n':len(closed),'overall':overall,'yearly':yearly,'exit_reason_counts':dict(Counter(r['exit_reason'] for r in closed)),'invariants':{'t1_violations':t1,'same_bar_collisions':sum(bool(r.get('same_bar_collision')) for r in closed),'search_count':1,'source_oracle_pass':True},'promotion_gate_pass':passed,'decision':'INDUCEMENT_SWEEP_FROZEN_REPLAY_PASS__SHADOW_NEXT' if passed else 'INDUCEMENT_SWEEP_ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS','artifacts':{'out_dir':str(OUT),'rows':str(row_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2);(OUT/'v475_report.json').write_text(text);LATEST.write_text(text);print(text)
if __name__=='__main__':main()
