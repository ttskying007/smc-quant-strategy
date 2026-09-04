#!/usr/bin/env python3
"""V100: economic net-WR repair after V99 small-profit autopsy.

Preserves V98 signal/entry and V99 semantic gates, removes sub-cost 0.25R lock.
Uses bar-by-bar hybrid economic exit: after live MFE>=4R lock +2R; after live MFE>=6R lock +3R.
Promotion gate: A/B tiers are production-quality; C remains watch only because net WR <90 under economic accounting.
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any, Dict, List

from v81_full_market_scan import KLINE_DIR, load_json
from v91_shadow_zone_entry_scanner import bar_date
from v99_high_wr_production_gate import normalize_row, v99_tier, apply_frontend_contract

ROOT=Path('/root/.hermes')
SRC=ROOT/'smc_opt_v98_reachable_5r_probability_gate'
OUT=ROOT/'smc_opt_v100_economic_net_wr_gate'
OUT.mkdir(parents=True, exist_ok=True)
TRADES_IN=SRC/'v98_structural_trades.json'
PICKS_IN=SRC/'v98_active_picks.json'
ENGINE='V100_ECONOMIC_NET_WR_GATE'
FEE_SLIP=0.8
MAX_HOLD=80

def f(x: Any, default: float=0.0) -> float:
    try:
        if x in (None,''): return default
        v=float(x); return v if math.isfinite(v) else default
    except Exception: return default

def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"

def load_ks_cache(rows: List[Dict[str,Any]]) -> Dict[str,List[Dict[str,Any]]]:
    cache={}
    for sym in sorted({r.get('symbol') for r in rows if r.get('symbol')}):
        p=kline_path(sym)
        if p.exists(): cache[sym]=load_json(p)
    return cache

def simulate_economic_exit(ks: List[Dict[str,Any]], row: Dict[str,Any]) -> Dict[str,Any]:
    entry_idx=int(f(row.get('entry_idx'),-1)); ep=f(row.get('entry_price')); sl0=f(row.get('sl'))
    tp1=f(row.get('tp1')); tp2=f(row.get('tp2')); tp3=f(row.get('tp3'))
    risk=ep-sl0
    if entry_idx < 0 or ep <= 0 or risk <= 0 or entry_idx >= len(ks)-1:
        return dict(row)
    active_sl=sl0; active_sl_mode='STRUCTURAL_SL'
    exit_idx=min(len(ks)-1, entry_idx+MAX_HOLD); exit_price=ep; reason='TIME_STOP'
    max_h=ep; min_l=ep; hit1=False; trail=[]
    for i in range(entry_idx+1, min(len(ks), entry_idx+MAX_HOLD+1)):
        h=f(ks[i].get('h')); l=f(ks[i].get('l')); c=f(ks[i].get('c'))
        max_h=max(max_h,h); min_l=min(min_l,l)
        mfe=(max_h-ep)/risk
        # no sub-cost lock. Both locks are >= economic threshold for normal V98 risks.
        if mfe >= 6 and active_sl < ep + 3*risk:
            active_sl=ep+3*risk; active_sl_mode='V100_LOCK6_3R'
            trail.append({'idx':i,'date':bar_date(ks[i]),'mfe_r':round(mfe,4),'active_sl':round(active_sl,4),'mode':active_sl_mode})
        elif mfe >= 4 and active_sl < ep + 2*risk:
            active_sl=ep+2*risk; active_sl_mode='V100_LOCK4_2R'
            trail.append({'idx':i,'date':bar_date(ks[i]),'mfe_r':round(mfe,4),'active_sl':round(active_sl,4),'mode':active_sl_mode})
        if l <= active_sl:
            exit_idx=i; exit_price=active_sl; reason='V100_ECONOMIC_PROTECT_STOP' if active_sl>sl0 else 'SL_HIT'; break
        if tp1 and h >= tp1: hit1=True
        if tp2 and h >= tp2:
            exit_idx=i; exit_price=tp2; reason='TP2_MAIN_HIT'; break
        if tp3 and h >= tp3:
            exit_idx=i; exit_price=tp3; reason='TP3_RUNNER_HIT'; break
        exit_price=c
    pnl=(exit_price/ep-1)*100 if ep else 0
    out=dict(row)
    out.update({
        'engine':ENGINE,
        'contract_source':'V100_FROM_V98_SIGNAL_ENTRY_V99_GATE_ECONOMIC_EXIT',
        'v100_economic_exit':True,
        'v100_exit_rule':'BAR_BY_BAR_MFE>=4R_LOCK_2R__MFE>=6R_LOCK_3R__NO_0_25R_LOCK',
        'active_sl':round(active_sl,4),'active_sl_mode':active_sl_mode,
        'exit_idx':exit_idx,'exit_date':bar_date(ks[exit_idx]),'exit_price':round(exit_price,4),
        'exit_reason_v98':row.get('exit_reason'),'pnl_pct_v98':row.get('pnl_pct'),
        'exit_reason':reason,'pnl_pct':round(pnl,4),'net_success_0_8': pnl>=FEE_SLIP,
        'hit_tp1':hit1,'hit_tp2':reason in ('TP2_MAIN_HIT','TP3_RUNNER_HIT'),
        'mfe_r':round((max_h-ep)/risk,4),'mae_r':round((ep-min_l)/risk,4),'hold_bars_realized':exit_idx-entry_idx,
        'v100_trail_events':trail[:10]
    })
    return out

def v100_grade(tier: str) -> str:
    if tier in ('A_HIGH_WR_PRODUCTION','B_HIGH_WR_OBSERVE'):
        return 'A_PRODUCTION_ECONOMIC_NET_WR'
    if tier == 'C_ROBUST_OBSERVE':
        return 'C_WATCH_ONLY_ECONOMIC_WR_LT_90'
    if tier == 'RECOVERY_WEAK_DOWNGRADED':
        return 'D_RECOVERY_WEAK_WATCH_ONLY'
    return 'D_REJECT_OR_WATCH'

def normalize_v100(r: Dict[str,Any], ks: List[Dict[str,Any]]|None=None) -> Dict[str,Any]:
    # first reuse V99 semantic tiering on V98 raw row, but without V99 0.25R exit
    base=normalize_row(r, None)
    if ks: base=simulate_economic_exit(ks, base)
    tier=base.get('v99_tier') or v99_tier(base)
    base['v100_tier']=tier
    base['v100_public_grade']=v100_grade(tier)
    base['production_grade']=base['v100_public_grade']
    base['is_active_pick']=tier in ('A_HIGH_WR_PRODUCTION','B_HIGH_WR_OBSERVE')
    base['pick_scope']='ACTIVE_CANDIDATE' if base['is_active_pick'] else ('WATCH_ONLY' if tier=='C_ROBUST_OBSERVE' else 'REJECTED_OR_DOWNGRADED')
    base['state']=base['pick_scope']; base['setup_status']=tier
    return apply_frontend_contract(base)

def stat(rows: List[Dict[str,Any]]) -> Dict[str,Any]:
    if not rows: return {'n':0}
    pn=[f(r.get('pnl_pct')) for r in rows]
    wins=[x for x in pn if x>0]; net=[x for x in pn if x>=FEE_SLIP]; small=[x for x in pn if 0<x<FEE_SLIP]; losses=[x for x in pn if x<=0]
    avg=lambda xs: statistics.mean(xs) if xs else 0
    return {
        'n':len(rows),'gross_wr':round(len(wins)/len(rows)*100,2),'net_wr_ge_0_8':round(len(net)/len(rows)*100,2),
        'small_win_0_to_0_8':len(small),'small_win_pct':round(len(small)/len(rows)*100,2),'loss_n':len(losses),'loss_pct':round(len(losses)/len(rows)*100,2),
        'avg_pnl':round(avg(pn),4),'avg_win':round(avg(wins),4),'avg_loss':round(avg(losses),4),
        'payoff_win_loss':round(abs(avg(wins)/avg(losses)),4) if wins and losses and avg(losses)!=0 else None,
        'profit_factor':round(sum(wins)/abs(sum(losses)),4) if losses and abs(sum(losses))>1e-12 else None,
    }

def grouped(rows: List[Dict[str,Any]], field: str) -> Dict[str,Any]:
    d=defaultdict(list)
    for r in rows: d[str(r.get(field) or '')].append(r)
    return {k:stat(v) for k,v in sorted(d.items(), key=lambda kv: kv[0]) if v}

def year_stat(rows: List[Dict[str,Any]]) -> Dict[str,Any]:
    d=defaultdict(list)
    for r in rows:
        y=str(r.get('entry_date') or '')[:4]
        if y: d[y].append(r)
    return {k:stat(v) for k,v in sorted(d.items())}

def missing(rows: List[Dict[str,Any]]) -> Dict[str,int]:
    keys=['pick_date','join_date','选股日期','加入日期','zone','zone_type','cost_line','smart_money_cost','volatility_pct','volatility','tp1','tp2','tp3','sl','rr']
    return {k:sum(1 for r in rows if r.get(k) in (None,'',0)) for k in keys}

def main() -> None:
    raw=json.loads(TRADES_IN.read_text())
    ks_cache=load_ks_cache(raw)
    trades=[normalize_v100(r, ks_cache.get(r.get('symbol'))) for r in raw]
    raw_picks=json.loads(PICKS_IN.read_text()) if PICKS_IN.exists() else []
    picks=[normalize_v100(r, ks_cache.get(r.get('symbol'))) for r in raw_picks]
    tradable=[r for r in trades if r.get('is_active_pick')]
    abc=[r for r in trades if r.get('v100_tier') in ('A_HIGH_WR_PRODUCTION','B_HIGH_WR_OBSERVE','C_ROBUST_OBSERVE')]
    tradable_stat=stat(tradable)
    abc_stat=stat(abc)
    t1_violations=sum(1 for r in trades if str(r.get('entry_date'))==str(r.get('exit_date')))
    promotion_pass=bool(
        tradable_stat.get('n',0) >= 100 and
        tradable_stat.get('net_wr_ge_0_8',0) >= 90 and
        tradable_stat.get('small_win_0_to_0_8',1) == 0 and
        t1_violations == 0
    )
    active_picks=[p for p in picks if p.get('is_active_pick')] if promotion_pass else []
    decision=(
        'PROMOTE_V100_AB_ECONOMIC_PRODUCTION'
        if promotion_pass else
        f"REJECT_V100_FOR_PRODUCTION: economic exit removes sub-cost small-win pollution, but A/B net WR is "
        f"{tradable_stat.get('net_wr_ge_0_8',0)}% (gate >=90%) and ABC net WR is {abc_stat.get('net_wr_ge_0_8',0)}%; "
        f"active picks suppressed; keep as economic autopsy artifact, not production."
    )
    report={
        'engine':ENGINE,'latest_market_date':max([str(p.get('pick_date') or '')[:8] for p in picks], default=''),
        'source':str(TRADES_IN),'fee_slippage_threshold_pct':FEE_SLIP,
        'rules':{
            'signal_entry':'UNCHANGED_FROM_V98','semantic_gate':'V99 tiers reused; A/B tested as candidate, C watch-only',
            'economic_exit':'MFE>=4R lock 2R, MFE>=6R lock 3R, no 0.25R sub-cost lock',
            'production':'Promote only if A/B n>=100, net WR>=90%, small_win=0, and T+1 violations=0; otherwise no active picks are exported.'
        },
        'gate':{'pass':promotion_pass,'min_n':100,'min_net_wr_ge_0_8':90,'require_small_win_0':True,'require_t1_violations_0':True},
        'tradable_AB':tradable_stat,'tradable_AB_by_year':year_stat(tradable),'tradable_AB_by_tier':grouped(tradable,'v100_tier'),
        'ABC_watch_pool':abc_stat,'ABC_by_tier':grouped(abc,'v100_tier'),'ABC_by_year':year_stat(abc),
        'all_by_tier':grouped(trades,'v100_tier'),
        'exit_counts_tradable':dict(Counter(r.get('exit_reason') for r in tradable)),
        'exit_counts_ABC':dict(Counter(r.get('exit_reason') for r in abc)),
        'active_pick_total':len(active_picks),'active_pick_counts':dict(Counter(p.get('v100_tier') for p in active_picks)),
        't1_violations':t1_violations,
        'field_missing_active':missing(active_picks),'field_contract':['pick_date','join_date','zone','cost_line','volatility_pct','tp1','tp2','tp3','sl','rr'],
        'promotion_decision':decision
    }
    (OUT/'v100_trades.json').write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    (OUT/'v100_active_picks.json').write_text(json.dumps(active_picks, ensure_ascii=False, indent=2))
    (OUT/'v100_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__=='__main__': main()
