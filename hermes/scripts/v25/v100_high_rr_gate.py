#!/usr/bin/env python3
"""V100 candidate: V99 high-WR gate, V98 structural TP/SL exits preserved.

Purpose: remove V99 sub-cost 0.25R profit-protect exits. A/B remain high-WR production/observe;
C stays watch-only. This is an analysis candidate, not automatically promoted.
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path
from typing import Any, Dict, List
from collections import Counter, defaultdict

SRC = Path('/root/.hermes/smc_opt_v98_reachable_5r_probability_gate')
OUT = Path('/root/.hermes/smc_opt_v100_high_rr_gate')
OUT.mkdir(parents=True, exist_ok=True)
TRADES_IN = SRC / 'v98_structural_trades.json'
PICKS_IN = SRC / 'v98_active_picks.json'
FEE_SLIP = 0.8

def f(x: Any, default: float=0.0) -> float:
    try:
        if x in (None, ''): return default
        v=float(x); return v if math.isfinite(v) else default
    except Exception: return default

def load(p: Path, default):
    try: return json.loads(p.read_text())
    except Exception: return default

def is_a_v98(r: Dict[str, Any]) -> bool:
    return r.get('production_grade_v98') == 'A_PRODUCTION' or r.get('production_grade') == 'A_PRODUCTION'

def weak_recovery(r: Dict[str, Any]) -> bool:
    market = r.get('market_state') or ''
    sub = r.get('v90_recovery_substate') or ''
    pd = r.get('pd_zone') or ''
    vol = f(r.get('volatility_pct'))
    risk = f(r.get('risk_pct'))
    event = r.get('event_type') or ''
    if market == 'RECOVERY' and pd != 'DEEP_DISCOUNT': return True
    if market == 'RECOVERY' and (vol > 0.8 or risk > 1.0) and event != 'SSL_SWEEP_CHOCH_REVERSAL': return True
    if sub.startswith('WEAK') or sub in ('FAILED_RECOVERY', 'NO_RECLAIM'): return True
    return False

def tier(r: Dict[str, Any]) -> str:
    if not is_a_v98(r): return 'REJECT_NOT_V98_A'
    market,event,pd = r.get('market_state'), r.get('event_type'), r.get('pd_zone')
    tp2,tp3,vol,risk = f(r.get('tp2_rr')), f(r.get('tp3_rr')), f(r.get('volatility_pct')), f(r.get('risk_pct'))
    if weak_recovery(r): return 'RECOVERY_WEAK_DOWNGRADED'
    if market == 'MIXED' and event == 'SSL_SWEEP_CHOCH_REVERSAL' and tp2 <= 5.2 and vol <= 0.8 and risk <= 1.0:
        return 'A_HIGH_WR_PRODUCTION'
    if market == 'MIXED' and pd == 'DISCOUNT' and tp2 <= 5.2 and vol <= 0.8 and risk <= 1.0:
        return 'B_HIGH_WR_OBSERVE'
    if pd == 'DEEP_DISCOUNT' and tp2 <= 5.5 and tp3 <= 14:
        return 'C_ROBUST_OBSERVE'
    return 'WATCH_ONLY_LOW_WR'

def grade(t: str) -> str:
    return {'A_HIGH_WR_PRODUCTION':'A_PRODUCTION','B_HIGH_WR_OBSERVE':'B_LIGHT_OR_OBSERVE','C_ROBUST_OBSERVE':'C_WATCH_ONLY','RECOVERY_WEAK_DOWNGRADED':'D_RECOVERY_WEAK_WATCH_ONLY'}.get(t,'D_REJECT_OR_WATCH')

def contract(x: Dict[str, Any]) -> Dict[str, Any]:
    x=dict(x)
    t=tier(x)
    x['v100_tier']=t
    x['v99_tier']=t
    x['engine']='V100_HIGH_RR_GATE_V98_STRUCTURAL_EXIT'
    x['contract_source']='V100_FROM_V98_SIGNAL_ENTRY_STRUCTURAL_EXIT_NO_SUBCOST_PROTECT'
    x['production_grade_v98']=x.get('production_grade_v98') or x.get('production_grade')
    x['production_grade']=grade(t)
    x['setup_status']=t
    x['is_active_pick']=t == 'A_HIGH_WR_PRODUCTION'
    x['pick_scope']='ACTIVE_CANDIDATE' if t == 'A_HIGH_WR_PRODUCTION' else ('WATCH_ONLY' if t in ('B_HIGH_WR_OBSERVE','C_ROBUST_OBSERVE') else 'REJECTED_OR_DOWNGRADED')
    x['entry_semantic_v98']=x.get('entry_semantic_v98') or x.get('entry_semantic')
    x['entry_semantic']='PRE_RECLAIM_ZONE_MID_LIMIT_ANTICIPATION'
    x['entry_layer']='L1_ANTICIPATION'
    x['pick_date']=x.get('pick_date') or x.get('select_date') or x.get('entry_date')
    x['join_date']=x.get('join_date') or x.get('entry_date')
    x['pickDate']=x.get('pickDate') or x.get('pick_date')
    x['joinDate']=x.get('joinDate') or x.get('join_date')
    x['selectDate']=x.get('selectDate') or x.get('pick_date')
    x['entryDate']=x.get('entryDate') or x.get('entry_date') or x.get('join_date')
    x['选股日期']=x.get('选股日期') or x.get('pick_date')
    x['加入日期']=x.get('加入日期') or x.get('join_date')
    x['zone_type']=x.get('zone_type') or x.get('poi_type') or x.get('signal_type') or 'DEMAND_OB'
    zl,zh=f(x.get('zone_low')),f(x.get('zone_high'))
    if not x.get('zone') and zl and zh: x['zone']=f'{zl:.4f}~{zh:.4f}'
    if not x.get('cost_line'): x['cost_line']=x.get('smart_money_cost') or (round((zl+zh)/2,4) if zl and zh else x.get('entry_price'))
    if not x.get('smart_money_cost'): x['smart_money_cost']=x.get('cost_line') or x.get('entry_price')
    if x.get('volatility_pct') in (None,''): x['volatility_pct']=x.get('volatility') if x.get('volatility') not in (None,'') else f(x.get('risk_pct'))
    if x.get('volatility') in (None,''): x['volatility']=x.get('volatility_pct')
    return x

def stats(rows: List[Dict[str,Any]]) -> Dict[str, Any]:
    if not rows: return {'n':0}
    pn=[f(r.get('pnl_pct')) for r in rows]
    wins=[x for x in pn if x>0]; net=[x for x in pn if x>=FEE_SLIP]; small=[x for x in pn if 0<x<FEE_SLIP]; losses=[x for x in pn if x<=0]
    avg=lambda xs: statistics.mean(xs) if xs else 0
    return {'n':len(rows),'gross_wr':round(len(wins)/len(rows)*100,2),'net_wr_ge_0_8':round(len(net)/len(rows)*100,2),'small_win_pct':round(len(small)/len(rows)*100,2),'loss_pct':round(len(losses)/len(rows)*100,2),'avg_pnl':round(avg(pn),4),'avg_win':round(avg(wins),4),'avg_loss':round(avg(losses),4),'payoff':round(abs(avg(wins)/avg(losses)),4) if wins and losses and avg(losses) else None,'profit_factor':round(sum(wins)/abs(sum(losses)),4) if losses and abs(sum(losses))>1e-12 else None}

def group(rows, key):
    d=defaultdict(list)
    for r in rows: d[str(r.get(key) or '')].append(r)
    return {k:stats(v) for k,v in sorted(d.items(), key=lambda kv: len(kv[1]), reverse=True) if len(v)>=5}

def main():
    trades=[contract(r) for r in load(TRADES_IN, [])]
    picks=[contract(r) for r in load(PICKS_IN, [])]
    active=[p for p in picks if p.get('v100_tier') in ('A_HIGH_WR_PRODUCTION','B_HIGH_WR_OBSERVE','C_ROBUST_OBSERVE')]
    abc=[r for r in trades if r.get('v100_tier') in ('A_HIGH_WR_PRODUCTION','B_HIGH_WR_OBSERVE','C_ROBUST_OBSERVE')]
    report={
        'engine':'V100_HIGH_RR_GATE_V98_STRUCTURAL_EXIT',
        'purpose':'Remove V99 sub-cost 0.25R protect exits; preserve V98 structural TP/SL; evaluate net WR and payoff.',
        'fee_slippage_threshold_pct':FEE_SLIP,
        'rules':{
            'A':'V98 A + MIXED + SSL_SWEEP_CHOCH_REVERSAL + TP2<=5.2R + vol<=0.8 + risk<=1.0',
            'B':'V98 A + MIXED + DISCOUNT + TP2<=5.2R + vol<=0.8 + risk<=1.0',
            'C':'V98 A + DEEP_DISCOUNT + TP2<=5.5R + TP3<=14R',
            'exit':'V98 structural TP2/SL, no V99 0.25R profit-protect stop'
        },
        'active_pick_counts':dict(Counter(p.get('v100_tier') for p in active)),
        'active_pick_total':len(active),
        'tradable_ABC':stats(abc),
        'tradable_A_only':stats([r for r in abc if r.get('v100_tier')=='A_HIGH_WR_PRODUCTION']),
        'by_tier':group(abc,'v100_tier'),
        'by_market_state':group(abc,'market_state'),
        'by_event_type':group(abc,'event_type'),
        'exit_counts':dict(Counter(r.get('exit_reason') for r in abc)),
        'field_missing_active':{f:sum(1 for p in active if p.get(f) in (None,'',[],{})) for f in ['symbol','pick_date','join_date','zone_type','zone','cost_line','smart_money_cost','volatility_pct','risk_pct','tp1','tp2','tp3','sl','engine']},
    }
    (OUT/'v100_trades.json').write_text(json.dumps(trades,ensure_ascii=False))
    (OUT/'v100_active_picks.json').write_text(json.dumps(active,ensure_ascii=False,indent=2))
    (OUT/'v100_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__ == '__main__': main()
