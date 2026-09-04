#!/usr/bin/env python3
"""V99/V100 economic autopsy: frontend sync + low-PnL attribution + profit-protect matrix."""
from __future__ import annotations
import json, math, statistics
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

from v81_full_market_scan import KLINE_DIR
from v91_shadow_zone_entry_scanner import bar_date

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v99_high_wr_gate/v99_trades.json'
OUT = ROOT / 'smc_opt_v99_high_wr_gate/v99_economic_autopsy.json'
FEE_SLIP = 0.8
MAX_HOLD = 80

def f(x: Any, default: float=0.0) -> float:
    try:
        if x in (None, ''): return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default

def load_json(p: Path, default=None):
    try: return json.loads(p.read_text())
    except Exception: return default

def kline(symbol: str):
    p = KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"
    return load_json(p, []) or []

def rows():
    data = load_json(TRADES, []) or []
    return [r for r in data if r.get('v99_tier') in ('A_HIGH_WR_PRODUCTION','B_HIGH_WR_OBSERVE','C_ROBUST_OBSERVE')]

def stat(rs: List[Dict[str,Any]], fee: float=FEE_SLIP):
    if not rs: return {'n':0}
    pn = [f(r.get('pnl_pct')) for r in rs]
    wins = [x for x in pn if x > 0]
    net = [x for x in pn if x >= fee]
    small = [x for x in pn if 0 < x < fee]
    losses = [x for x in pn if x <= 0]
    avg = lambda xs: statistics.mean(xs) if xs else 0
    return {
        'n': len(rs),
        'gross_wr': round(len(wins)/len(rs)*100, 2),
        'net_wr_ge_0_8': round(len(net)/len(rs)*100, 2),
        'small_win_0_to_0_8': len(small),
        'small_win_pct': round(len(small)/len(rs)*100, 2),
        'loss_n': len(losses),
        'loss_pct': round(len(losses)/len(rs)*100, 2),
        'avg_pnl': round(avg(pn), 4),
        'avg_win': round(avg(wins), 4),
        'avg_loss': round(avg(losses), 4),
        'payoff_win_loss': round(abs(avg(wins)/avg(losses)), 4) if wins and losses and avg(losses) != 0 else None,
        'profit_factor': round(sum(wins)/abs(sum(losses)), 4) if losses and abs(sum(losses)) > 1e-12 else None,
    }

def sim(row: Dict[str,Any], mode: str) -> Dict[str,Any]:
    ks = kline(row.get('symbol',''))
    entry_idx = int(f(row.get('entry_idx'), -1))
    ep, sl0, tp1, tp2, tp3 = f(row.get('entry_price')), f(row.get('sl')), f(row.get('tp1')), f(row.get('tp2')), f(row.get('tp3'))
    risk = ep - sl0
    if entry_idx < 0 or ep <= 0 or risk <= 0 or entry_idx >= len(ks)-1:
        return dict(row, pnl_pct=f(row.get('pnl_pct')), exit_reason=row.get('exit_reason','NO_SIM'))
    # modes: no_protect, lock2_be, lock2_1r, lock3_1r, lock4_2r, lock5_2r, tp2_then_runner (existing target priority variants)
    active_sl = sl0
    active_mode = 'STRUCTURAL_SL'
    exit_idx = min(len(ks)-1, entry_idx+MAX_HOLD)
    exit_price = ep
    reason = 'TIME_STOP'
    max_h = ep
    min_l = ep
    hit_tp1 = False
    for i in range(entry_idx+1, min(len(ks), entry_idx+MAX_HOLD+1)):
        h,l,c = f(ks[i].get('h')), f(ks[i].get('l')), f(ks[i].get('c'))
        max_h=max(max_h,h); min_l=min(min_l,l)
        mfe=(max_h-ep)/risk
        if mode == 'lock2_be' and mfe >= 2 and active_sl < ep:
            active_sl=ep; active_mode='LOCK2_BE'
        elif mode == 'lock2_1r' and mfe >= 2 and active_sl < ep+risk:
            active_sl=ep+risk; active_mode='LOCK2_1R'
        elif mode == 'lock3_1r' and mfe >= 3 and active_sl < ep+risk:
            active_sl=ep+risk; active_mode='LOCK3_1R'
        elif mode == 'lock4_2r' and mfe >= 4 and active_sl < ep+2*risk:
            active_sl=ep+2*risk; active_mode='LOCK4_2R'
        elif mode == 'lock5_2r' and mfe >= 5 and active_sl < ep+2*risk:
            active_sl=ep+2*risk; active_mode='LOCK5_2R'
        elif mode == 'hybrid3_1r_5_2r':
            if mfe >= 5 and active_sl < ep+2*risk:
                active_sl=ep+2*risk; active_mode='LOCK5_2R'
            elif mfe >= 3 and active_sl < ep+risk:
                active_sl=ep+risk; active_mode='LOCK3_1R'
        elif mode == 'hybrid4_2r_6_3r':
            if mfe >= 6 and active_sl < ep+3*risk:
                active_sl=ep+3*risk; active_mode='LOCK6_3R'
            elif mfe >= 4 and active_sl < ep+2*risk:
                active_sl=ep+2*risk; active_mode='LOCK4_2R'
        # exit order: T+1 bar uses same OHLC ambiguity as V98/V99; stop checked first after active_sl update to avoid future after stop.
        if l <= active_sl:
            exit_idx=i; exit_price=active_sl; reason='PROTECT_STOP' if active_sl>sl0 else 'SL_HIT'; break
        if tp1 and h >= tp1: hit_tp1=True
        if tp2 and h >= tp2:
            exit_idx=i; exit_price=tp2; reason='TP2_MAIN_HIT'; break
        if tp3 and h >= tp3:
            exit_idx=i; exit_price=tp3; reason='TP3_RUNNER_HIT'; break
        exit_price=c
    pnl=(exit_price/ep-1)*100 if ep else 0
    out=dict(row)
    out.update({'pnl_pct':round(pnl,4),'exit_reason':reason,'active_sl_mode':active_mode,'mfe_r':round((max_h-ep)/risk,4),'mae_r':round((ep-min_l)/risk,4),'hold_bars_realized':exit_idx-entry_idx})
    return out

def grouped(rs, field):
    out={}
    for k, vals in defaultdict(list, ((None, []),)).items(): pass
    d=defaultdict(list)
    for r in rs: d[str(r.get(field) or '')].append(r)
    for k,v in d.items():
        if len(v) >= 10:
            out[k]=stat(v)
    return dict(sorted(out.items(), key=lambda kv: kv[1]['n'], reverse=True))

def main():
    abc=rows()
    low=[r for r in abc if 0 < f(r.get('pnl_pct')) < FEE_SLIP]
    loss=[r for r in abc if f(r.get('pnl_pct')) <= 0]
    matrix={}
    for mode in ['no_protect','lock2_be','lock2_1r','lock3_1r','lock4_2r','lock5_2r','hybrid3_1r_5_2r','hybrid4_2r_6_3r']:
        sims=[sim(r, mode) for r in abc]
        matrix[mode]=stat(sims)
        matrix[mode]['exit_counts']=dict(Counter(r.get('exit_reason') for r in sims))
        matrix[mode]['tier_stats']={t: stat([r for r in sims if r.get('v99_tier')==t]) for t in ['A_HIGH_WR_PRODUCTION','B_HIGH_WR_OBSERVE','C_ROBUST_OBSERVE']}
    report={
        'fee_slippage_threshold_pct':FEE_SLIP,
        'current_v99_abc': stat(abc),
        'current_v99_by_tier': grouped(abc,'v99_tier'),
        'low_pnl_attribution': {
            'n': len(low),
            'stats': stat(low),
            'by_tier': grouped(low,'v99_tier'),
            'by_exit_reason': grouped(low,'exit_reason'),
            'by_market_state': grouped(low,'market_state'),
            'by_event_type': grouped(low,'event_type'),
            'by_v91_gate_reason': grouped(low,'v91_gate_reason'),
            'root_cause': 'V99 profit protection exits at 0.25R after MFE>=2R; many trades have very small structural risk (~0.5%-1.1%), so locked profit is only ~0.13%-0.27%, below cost/slippage. This is TP/SL exit-policy issue, not primary signal absence; low winners all had MFE>=2R then were stopped by protection before TP2.'
        },
        'loss_attribution': {
            'n': len(loss),
            'stats': stat(loss),
            'by_tier': grouped(loss,'v99_tier'),
            'by_market_state': grouped(loss,'market_state'),
            'by_event_type': grouped(loss,'event_type'),
            'by_sl_mode': grouped(loss,'sl_mode'),
        },
        'profit_protect_matrix': matrix,
        'candidate_direction': 'Replace 0.25R lock with minimum economic lock: either no 2R lock, or lock at >=1R after MFE>=3R; enforce net-success metric >=0.8% and report net WR separately from gross WR. Current gross WR is inflated by sub-cost protective exits.'
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:report[k] for k in ['current_v99_abc','low_pnl_attribution','candidate_direction']},ensure_ascii=False,indent=2)[:12000])
    print('MATRIX')
    for k,v in matrix.items(): print(k,v)
    print('OUT',OUT)

if __name__=='__main__': main()
