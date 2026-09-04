#!/usr/bin/env python3
"""V449 single frozen strict-T+1 replay for oracle-passed V447 SSL/BPR seeds."""
from __future__ import annotations
import csv, json, math, statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v448_ssl_bpr_independent_oracle_latest.json'
OUT=AUD/f"v449_ssl_bpr_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v449_ssl_bpr_frozen_t1_replay_latest.json'
YEARS=('2023','2024','2025','2026'); MAX_HOLD=30; FEE_PCT=.20
GATE={'n':300,'each_year_n':40,'gross_wr_pct':55.0,'avg_net_pnl_pct':0.5,'each_year_gross_wr_pct':50.0,'each_year_avg_net_pnl_pct':0.0,'profit_factor':1.15,'t1_violations':0}

def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0

def i(x): return int(float(x))
def day(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def load(sym):
    try: raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        d=day(b.get('t') or b.get('date')); r={k:f(b.get(k)) for k in ('o','h','l','c')}
        if d and all(r.values()): r['t']=d; rows.append(r)
    return sorted(rows,key=lambda x:x['t'])

def confirmed_highs(bars):
    out=[]
    for idx in range(3,len(bars)-3):
        price=bars[idx]['h']
        if all(bars[j]['h']<price for j in range(idx-3,idx+4) if j!=idx): out.append((idx,idx+3,price))
    return out

def target_before_entry(bars,highs,takeover,entry):
    candidates=[]
    for idx,confirm,price in highs:
        if confirm>takeover or price<=entry: continue
        if max(b['h'] for b in bars[idx+1:takeover+1])<price: candidates.append((price,idx,confirm))
    return min(candidates,key=lambda x:x[0]) if candidates else None

def replay(seed,bars,highs):
    entry_idx=i(seed['eligible_entry_idx']); takeover=i(seed['takeover_idx'])
    if entry_idx!=takeover+1 or entry_idx>=len(bars): return {'status':'BAD_ENTRY_INDEX'}
    if entry_idx+MAX_HOLD>=len(bars): return {'status':'OPEN_RIGHT_EDGE'}
    entry=bars[entry_idx]['o']; sl=f(seed['structural_sl_ref'])*.99
    if not 0<sl<entry: return {'status':'INVALID_RISK'}
    target=target_before_entry(bars,highs,takeover,entry); tp=target[0] if target else None
    risk_pct=(entry/sl-1)*100; planned_rr=((tp/entry-1)*100/risk_pct) if tp else None
    last=entry_idx+MAX_HOLD; exit_idx=last; exit_price=bars[last]['c']; reason='TIME30_NO_UNCONSUMED_BSL' if tp is None else 'TIME30_BSL_UNREACHED'; collision=False
    for idx in range(entry_idx+1,last+1):
        b=bars[idx]
        if b['o']<=sl: exit_idx,exit_price,reason=idx,b['o'],'SL_GAP_T1'; break
        if tp is not None and b['o']>=tp: exit_idx,exit_price,reason=idx,b['o'],'BSL_GAP_TP_T1'; break
        hit_sl=b['l']<=sl; hit_tp=tp is not None and b['h']>=tp
        if hit_sl and hit_tp: exit_idx,exit_price,reason,collision=idx,sl,'SL_TP_COLLISION_CONSERVATIVE_T1',True; break
        if hit_sl: exit_idx,exit_price,reason=idx,sl,'STRUCTURAL_SSL_SL_T1'; break
        if hit_tp: exit_idx,exit_price,reason=idx,tp,'UNCONSUMED_BSL_TP_T1'; break
    gross=(exit_price/entry-1)*100; net=gross-FEE_PCT; realized_r=gross/risk_pct
    return {'status':'CLOSED','entry_idx':entry_idx,'entry_date':bars[entry_idx]['t'],'entry_price':round(entry,6),'sl':round(sl,6),
      'risk_pct':round(risk_pct,6),'tp':'' if tp is None else round(tp,6),'tp_anchor_idx':'' if target is None else target[1],
      'planned_rr':'' if planned_rr is None else round(planned_rr,6),'exit_idx':exit_idx,'exit_date':bars[exit_idx]['t'],'exit_price':round(exit_price,6),
      'exit_reason':reason,'hold_bars':exit_idx-entry_idx,'gross_pnl_pct':round(gross,6),'fee_pct':FEE_PCT,'net_pnl_pct':round(net,6),
      'realized_r':round(realized_r,6),'t1_violation':bars[exit_idx]['t']<=bars[entry_idx]['t'],'same_bar_collision':collision}

def stats(rows):
    if not rows: return {'n':0,'gross_wr_pct':0,'net_wr_ge_0_8_pct':0,'avg_net_pnl_pct':0,'payoff_rr':0,'profit_factor':0}
    gross=[f(r['gross_pnl_pct']) for r in rows]; net=[f(r['net_pnl_pct']) for r in rows]; wins=[x for x in net if x>0]; losses=[x for x in net if x<=0]
    stop_reasons={'STRUCTURAL_SSL_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in gross)/len(rows)*100,4),'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in net)/len(rows)*100,4),
      'avg_gross_pnl_pct':round(sum(gross)/len(rows),4),'avg_net_pnl_pct':round(sum(net)/len(rows),4),'median_net_pnl_pct':round(statistics.median(net),4),
      'avg_win_pct':round(sum(wins)/len(wins),4) if wins else 0,'avg_loss_pct':round(sum(losses)/len(losses),4) if losses else 0,
      'payoff_rr':round((sum(wins)/len(wins))/abs(sum(losses)/len(losses)),4) if wins and losses and sum(losses) else 0,
      'profit_factor':round(sum(wins)/abs(sum(losses)),4) if losses and sum(losses) else 0,'cum_net_pnl_pct':round(sum(net),4),
      'avg_realized_r':round(sum(f(r['realized_r']) for r in rows)/len(rows),4),'sl_pct':round(sum(r['exit_reason'] in stop_reasons for r in rows)/len(rows)*100,4)}

def main():
    OUT.mkdir(parents=True,exist_ok=True); oracle=json.loads(SRC.read_text())
    if not oracle.get('oracle_gate_pass'): raise SystemExit('oracle gate failed')
    with open(oracle['artifacts']['passed_seeds']) as h: seeds=list(csv.DictReader(h))
    cache={}; high_cache={}; rows=[]
    for seed in seeds:
        sym=seed['symbol']
        if sym not in cache: cache[sym]=load(sym); high_cache[sym]=confirmed_highs(cache[sym])
        result=replay(seed,cache[sym],high_cache[sym]); rows.append({**seed,**result})
    closed=[r for r in rows if r['status']=='CLOSED']; overall=stats(closed); yearly={y:stats([r for r in closed if r['entry_date'][:4]==y]) for y in YEARS}
    t1=sum(bool(r['t1_violation']) for r in closed); gate=overall['n']>=GATE['n'] and overall['gross_wr_pct']>=GATE['gross_wr_pct'] and overall['avg_net_pnl_pct']>=GATE['avg_net_pnl_pct'] and overall['profit_factor']>=GATE['profit_factor'] and all(yearly[y]['n']>=GATE['each_year_n'] and yearly[y]['gross_wr_pct']>=GATE['each_year_gross_wr_pct'] and yearly[y]['avg_net_pnl_pct']>GATE['each_year_avg_net_pnl_pct'] for y in YEARS) and t1==0
    fields=sorted({k for r in rows for k in r}); trade_file=OUT/'v449_frozen_t1_rows.csv'
    with trade_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    report={'version':'V449_SSL_BPR_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_before_outcomes':{'entry':'next open after BPR retest/reclaim/hold','sl':'min(confirmed SSL, sweep low) * 0.99','target':'nearest pre-entry confirmed unconsumed 3L/3R swing high','exit':'strict T+1, target/SL/time30, gap-aware, collision=SL','fee_pct':FEE_PCT,'search_count':1,'promotion_gate':GATE},
      'seed_count':len(seeds),'status_counts':dict(Counter(r['status'] for r in rows)),'overall':overall,'yearly':yearly,'exit_reason_counts':dict(Counter(r['exit_reason'] for r in closed)),
      'invariants':{'t1_violations':t1,'same_bar_collisions':sum(bool(r['same_bar_collision']) for r in closed),'search_count':1,'source_oracle_pass':True},
      'promotion_gate_pass':gate,'decision':'SSL_BPR_RESEARCH_GATE_PASS' if gate else 'SSL_BPR_ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS',
      'artifacts':{'out_dir':str(OUT),'rows':str(trade_file),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v449_report.json').write_text(text); LATEST.write_text(text); print(text)
if __name__=='__main__': main()
