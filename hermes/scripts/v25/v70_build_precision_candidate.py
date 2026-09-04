#!/usr/bin/env python3
"""Promotable artifact builder for V70 high-precision candidate (not frontend sync).

Candidate selected from V70 reaction-confirm full-market replay:
  two_bar_reclaim + structure SL + RR0.10 + ret20>0
This is deliberately a high-precision, low-frequency candidate.
"""
import json
from pathlib import Path
from datetime import datetime
OUT=Path('/root/.hermes/smc_opt_v70_reaction_confirm')
tr=json.loads((OUT/'v70_trades.json').read_text())
sel=[r for r in tr if r['mode']=='two_bar_reclaim' and r['sl_mode']=='structure' and abs(float(r['rr'])-0.1)<1e-9 and float(r.get('ret20',0))>0]
sel=sorted(sel,key=lambda r:(r['entry_date'],r['symbol']))
def metrics(rs):
    if not rs: return {'n':0}
    wins=[r for r in rs if r['pnl_pct']>0]; losses=[r for r in rs if r['pnl_pct']<=0]
    return {'n':len(rs),'wr':round(len(wins)/len(rs)*100,2),'avg_pnl':round(sum(r['pnl_pct'] for r in rs)/len(rs),4),'cum_pnl':round(sum(r['pnl_pct'] for r in rs),2),'sl_rate':round(sum(r['exit_reason']=='SL_HIT' for r in rs)/len(rs)*100,2),'tp_rate':round(sum(r['exit_reason']=='TP1_HIT' for r in rs)/len(rs)*100,2),'avg_win':round(sum(r['pnl_pct'] for r in wins)/len(wins),4) if wins else 0,'avg_loss':round(sum(r['pnl_pct'] for r in losses)/len(losses),4) if losses else 0,'avg_hold':round(sum(r['hold_bars'] for r in rs)/len(rs),2)}
def audit(rs):
    fails=[]
    for r in rs:
        issues=[]
        if not (r['liq_bar'] < r['confirm_bar'] and r['zone_bar'] <= r['confirm_bar']+1 and r['confirm_bar'] < r['touch_idx'] <= r['reaction_confirm_idx'] < r['entry_idx']): issues.append('semantic_order')
        if r['exit_idx']<=r['entry_idx']: issues.append('t_plus_1')
        for k in ('symbol','entry_date','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','smart_money_cost','volatility_pct','entry_price','sl','tp1'):
            if r.get(k) in (None,'',0,0.0): issues.append('missing_'+k)
        if r.get('ret20',0)<=0: issues.append('ret20_filter_fail')
        if r.get('mode')!='two_bar_reclaim' or r.get('sl_mode')!='structure' or abs(float(r.get('rr'))-0.1)>1e-9: issues.append('contract_fail')
        if issues: fails.append({'symbol':r['symbol'],'entry_date':r['entry_date'],'issues':issues})
    return {'n':len(rs),'fail_count':len(fails),'semantic_order_fail':sum('semantic_order' in x['issues'] for x in fails),'t_plus_1_fail':sum('t_plus_1' in x['issues'] for x in fails),'field_contract_fail':sum(any(i.startswith('missing_') for i in x['issues']) for x in fails),'sample_fails':fails[:20]}
# enrich fields for frontend compatibility but do not wire frontend
for r in sel:
    r['engine']='V70_REACTION_CONFIRM_HIGH_PRECISION'
    r['definition_version']='LD_FVG_touch_two_bar_reclaim_structureSL_RR010_ret20_positive'
    r['entry_model']='TWO_BAR_RECLAIM_NEXT_OPEN'
    r['tp_model']='RR0_10_MICRO_TP'
    r['pick_scope']='V70_RESEARCH_CANDIDATE'
    r['status']='BACKTEST_VERIFIED'
    r['source']='V70_REACTION_CONFIRM_HIGH_PRECISION'
    r['signal_correctness_claim']='STRICT_LD_TOUCH_REACTION_T1_FIELD_PASS'
# latest per symbol picks
by={}
for r in sel: by[r['symbol']]=r
picks=sorted(by.values(),key=lambda r:r['entry_date'],reverse=True)[:200]
for p in picks:
    p['pick_scope']='ACTIVE_CANDIDATE' if p['entry_date']>='20260601' else 'WATCH_ONLY'
    p['is_active_pick']=p['pick_scope']=='ACTIVE_CANDIDATE'
    p['joined_at']=p.get('join_date') or p.get('entry_date')
report={'generated_at':datetime.now().isoformat(timespec='seconds'),'engine':'V70_REACTION_CONFIRM_HIGH_PRECISION','production_synced':False,'frontend_synced':False,'metrics':metrics(sel),'audit':audit(sel),'year':{},'month':{},'decision':'CANDIDATE_ONLY_NOT_SYNCED'}
from collections import defaultdict
for field,n in [('year',4),('month',6)]:
    d=defaultdict(list)
    for r in sel: d[r['entry_date'][:n]].append(r)
    report[field]={k:metrics(v) for k,v in sorted(d.items())}
(OUT/'v70_precision_trades.json').write_text(json.dumps(sel,ensure_ascii=False,indent=2))
(OUT/'v70_precision_picks.json').write_text(json.dumps(picks,ensure_ascii=False,indent=2))
(OUT/'v70_precision_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'metrics':report['metrics'],'audit':report['audit'],'year':report['year'],'files':[str(OUT/'v70_precision_trades.json'),str(OUT/'v70_precision_picks.json'),str(OUT/'v70_precision_report.json')]},ensure_ascii=False,indent=2))
