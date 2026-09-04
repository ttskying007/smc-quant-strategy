#!/usr/bin/env python3
"""V483 one-shot frozen strict-T+1 replay for V481/V482."""
from __future__ import annotations
import csv, json, math, statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
SRC=AUD/'v482_two_sided_liquidity_purge_oracle_latest.json'
OUT=AUD/f"v483_two_sided_liquidity_purge_frozen_t1_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v483_two_sided_liquidity_purge_frozen_t1_replay_latest.json'
STOP_BUFFER=.99; MAX_HOLD=20; FEE_PCT=.2
GATE={'n':300,'each_year_n':40,'gross_wr_pct':55.0,'avg_net_pnl_pct':.5,'each_year_gross_wr_pct':50.0,'each_year_avg_net_pnl_pct':0.0,'profit_factor':1.15,'t1_violations':0}
STOP_REASONS={'STRUCTURAL_SSL_RAID_SL_T1','SL_GAP_T1','SL_TP_COLLISION_CONSERVATIVE_T1'}


def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def integer(x): return int(float(x))
def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]


def load(sym):
    try: raw=json.loads((KDIR/f"{sym.replace('.','_')}_daily_750.json").read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}; d=ds(b.get('t') or b.get('date'))
        if d and all(r.values()): r['t']=d; rows.append(r)
    return sorted(rows,key=lambda r:r['t'])


def replay(seed,bars):
    eligible=integer(seed['eligible_entry_idx']); confirm=integer(seed['reversal_confirm_idx'])
    if eligible!=confirm+1 or eligible>=len(bars): return {'status':'UNOBSERVED_ENTRY'}
    entry=bars[eligible]['o']; sl=f(seed['structural_sl_ref'])*STOP_BUFFER; target=f(seed['structural_target_ref'])
    if entry<=0 or sl<=0 or sl>=entry: return {'status':'INVALID_RISK','entry_date':bars[eligible]['t']}
    if target<=entry: return {'status':'TARGET_CONSUMED_AT_ENTRY','entry_date':bars[eligible]['t']}
    first=eligible+1; last=eligible+MAX_HOLD
    if first>=len(bars) or last>=len(bars): return {'status':'OPEN_RIGHT_EDGE','entry_date':bars[eligible]['t']}
    exit_idx=last; exit_price=bars[last]['c']; reason='TIME20_BSL_RAID_HIGH_UNREACHED'; collision=False
    for idx in range(first,last+1):
        bar=bars[idx]
        if bar['o']<=sl: exit_idx,exit_price,reason=idx,bar['o'],'SL_GAP_T1'; break
        if bar['o']>=target: exit_idx,exit_price,reason=idx,bar['o'],'BSL_RAID_HIGH_GAP_TP_T1'; break
        hit_sl=bar['l']<=sl; hit_tp=bar['h']>=target
        if hit_sl and hit_tp: exit_idx,exit_price,reason,collision=idx,sl,'SL_TP_COLLISION_CONSERVATIVE_T1',True; break
        if hit_sl: exit_idx,exit_price,reason=idx,sl,'STRUCTURAL_SSL_RAID_SL_T1'; break
        if hit_tp: exit_idx,exit_price,reason=idx,target,'BSL_RAID_HIGH_TP_T1'; break
    gross=(exit_price/entry-1)*100; net=gross-FEE_PCT; risk=(entry/sl-1)*100; planned=(target/entry-1)*100/risk
    return {'status':'CLOSED','entry_idx':eligible,'entry_date':bars[eligible]['t'],'entry_price':round(entry,6),
      'sl':round(sl,6),'risk_pct':round(risk,4),'tp':round(target,6),'planned_rr':round(planned,4),
      'exit_idx':exit_idx,'exit_date':bars[exit_idx]['t'],'exit_price':round(exit_price,6),'exit_reason':reason,
      'hold_bars':exit_idx-eligible,'gross_pnl_pct':round(gross,4),'net_pnl_pct':round(net,4),
      'realized_r':round(gross/risk,4) if risk else 0.0,'t1_violation':bars[exit_idx]['t']<=bars[eligible]['t'],'same_bar_collision':collision}


def stats(rows):
    if not rows: return {'n':0}
    gross=[f(r['gross_pnl_pct']) for r in rows]; net=[f(r['net_pnl_pct']) for r in rows]
    wins=[x for x in net if x>0]; losses=[x for x in net if x<=0]
    aw=sum(wins)/len(wins) if wins else 0; al=sum(losses)/len(losses) if losses else 0
    return {'n':len(rows),'gross_wr_pct':round(sum(x>0 for x in gross)/len(rows)*100,4),
      'net_wr_ge_0_8_pct':round(sum(x>=.8 for x in net)/len(rows)*100,4),
      'avg_gross_pnl_pct':round(sum(gross)/len(rows),4),'avg_net_pnl_pct':round(sum(net)/len(rows),4),
      'median_net_pnl_pct':round(statistics.median(net),4),'avg_win_pct':round(aw,4),'avg_loss_pct':round(al,4),
      'payoff_rr':round(aw/abs(al),4) if al else 0,
      'profit_factor':round(sum(wins)/abs(sum(losses)),4) if losses and sum(losses) else 0,
      'cum_net_pnl_pct':round(sum(net),4),'avg_planned_rr':round(sum(f(r['planned_rr']) for r in rows)/len(rows),4),
      'avg_realized_r':round(sum(f(r['realized_r']) for r in rows)/len(rows),4),
      'sl_pct':round(sum(r['exit_reason'] in STOP_REASONS for r in rows)/len(rows)*100,4)}


def pass_gate(overall,yearly,t1):
    return (overall.get('n',0)>=GATE['n'] and overall.get('gross_wr_pct',0)>=GATE['gross_wr_pct']
      and overall.get('avg_net_pnl_pct',-999)>=GATE['avg_net_pnl_pct'] and overall.get('profit_factor',0)>=GATE['profit_factor']
      and all(yearly[y].get('n',0)>=GATE['each_year_n'] and yearly[y].get('gross_wr_pct',0)>=GATE['each_year_gross_wr_pct']
              and yearly[y].get('avg_net_pnl_pct',-999)>GATE['each_year_avg_net_pnl_pct'] for y in ('2023','2024','2025','2026'))
      and t1==0)


def main():
    source=json.loads(SRC.read_text())
    if source.get('decision')!='TWO_SIDED_PURGE_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED': raise RuntimeError('V482 oracle gate not passed')
    with open(source['artifacts']['passed_seeds']) as h: seeds=list(csv.DictReader(h))
    grouped=defaultdict(list)
    for seed in seeds: grouped[seed['symbol']].append(seed)
    rows=[]; OUT.mkdir(parents=True,exist_ok=True)
    for n,(sym,items) in enumerate(grouped.items(),1):
        bars=load(sym)
        for seed in items: rows.append({**seed,'execution_contract':'NEXT_OPEN__SSL_RAID_LOW_1PCT_SL__PRIOR_BSL_RAID_HIGH_TP__TIME20__STRICT_T1__FEE0P2',**replay(seed,bars)})
        if n%500==0: print(json.dumps({'symbols':n,'rows':len(rows)}),flush=True)
    closed=[r for r in rows if r.get('status')=='CLOSED' and r['entry_date'][:4] in {'2023','2024','2025','2026'}]
    yearly={y:stats([r for r in closed if r['entry_date'][:4]==y]) for y in ('2023','2024','2025','2026')}; overall=stats(closed)
    t1=sum(bool(r.get('t1_violation')) for r in closed); passed=pass_gate(overall,yearly,t1)
    row_file=OUT/'v483_frozen_t1_rows.csv'; fields=sorted({k for r in rows for k in r})
    with row_file.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    result={'version':'V483_TWO_SIDED_LIQUIDITY_PURGE_FROZEN_T1_REPLAY_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),
      'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_before_outcomes':{'entry':'next open after close above SSL-raid high','sl':'SSL raid low * 0.99','target':'prior BSL raid high','exit':'strict T+1, target/SL/time20, gap-aware, collision=SL','fee_pct':FEE_PCT,'search_count':1,'promotion_gate':GATE},
      'seed_count':len(seeds),'status_counts':dict(Counter(r.get('status') for r in rows)),'research_window_closed_n':len(closed),
      'overall':overall,'yearly':yearly,'exit_reason_counts':dict(Counter(r['exit_reason'] for r in closed)),
      'invariants':{'t1_violations':t1,'same_bar_collisions':sum(bool(r.get('same_bar_collision')) for r in closed),'search_count':1,'source_oracle_pass':True},
      'promotion_gate_pass':passed,'decision':'TWO_SIDED_PURGE_FROZEN_REPLAY_PASS__INDEPENDENT_METRIC_AUDIT_NEXT' if passed else 'TWO_SIDED_PURGE_ECONOMIC_GATE_FAIL__INDEPENDENT_METRIC_AUDIT_THEN_CLOSE',
      'artifacts':{'out_dir':str(OUT),'rows':str(row_file),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v483_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
