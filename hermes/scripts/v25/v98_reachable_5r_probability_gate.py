#!/usr/bin/env python3
from __future__ import annotations

import json, math, statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from v81_full_market_scan import ENV_PATH, KLINE_DIR, load_json, normalize_env, symbol_from_path
from v85_mixed_accumulation_generator import generate_v85_candidates, zone_width_pct
from v90_daily_full_market_scanner import recovery_substate
from v91_shadow_zone_entry_scanner import date_key, bar_date, num, price_in_bar, v91_gate_reason, entry_plan_for, fill_idx_for_limit

OUT = Path('/root/.hermes/smc_opt_v98_reachable_5r_probability_gate')
OUT.mkdir(parents=True, exist_ok=True)
ENGINE = 'V98_REACHABLE_5R_PROBABILITY_GATE'
SIGNAL_LAYER = 'V85_SIGNAL_LAYER_ZONE_ENTRY_RECOVERY'
CONTRACT_SOURCE = 'V98_REACHABLE_5R_PROBABILITY_GATE'
RECENT_BARS = 45
MAX_HOLD = 80


def f(x: Any, default: float = 0.0) -> float:
    return num(x, default)


def confirmed_pivots(ks: List[Dict[str, Any]], end_idx: int, left: int, right: int, kind: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    last = min(end_idx - right, len(ks) - right - 1)
    for i in range(left, max(left, last) + 1):
        window = ks[i-left:i+right+1]
        if len(window) < left + right + 1:
            continue
        if kind == 'high':
            val = f(ks[i].get('h'))
            if val and val >= max(f(b.get('h')) for b in window):
                out.append({'idx': i, 'price': val, 'date': bar_date(ks[i]), 'scale': f'L{left}R{right}', 'type': 'SWING_HIGH'})
        else:
            val = f(ks[i].get('l'))
            if val and val <= min(f(b.get('l')) for b in window):
                out.append({'idx': i, 'price': val, 'date': bar_date(ks[i]), 'scale': f'L{left}R{right}', 'type': 'SWING_LOW'})
    return out


def equal_high_targets(highs: List[Dict[str, Any]], entry: float, tol_pct: float = 0.35) -> List[Dict[str, Any]]:
    groups: List[List[Dict[str, Any]]] = []
    for h in sorted([x for x in highs if x['price'] > entry], key=lambda x: x['price']):
        placed = False
        for g in groups:
            avg = sum(x['price'] for x in g) / len(g)
            if abs(h['price'] - avg) / avg * 100 <= tol_pct:
                g.append(h); placed = True; break
        if not placed:
            groups.append([h])
    out = []
    for g in groups:
        if len(g) >= 2:
            out.append({'idx': max(x['idx'] for x in g), 'price': round(sum(x['price'] for x in g) / len(g), 4), 'date': g[-1]['date'], 'scale': 'EQH', 'type': 'EQH_BSL', 'touches': len(g)})
    return out


def structural_targets(ks: List[Dict[str, Any]], entry_idx: int, entry: float, sl: float) -> List[Dict[str, Any]]:
    risk = entry - sl
    if risk <= 0:
        return []
    highs: List[Dict[str, Any]] = []
    for left, right, label in [(2, 2, 'micro_BSL'), (5, 3, 'meso_BSL'), (10, 5, 'macro_BSL'), (20, 5, 'major_BSL')]:
        for h in confirmed_pivots(ks, entry_idx, left, right, 'high'):
            if h['price'] > entry:
                h = dict(h); h['target_type'] = label; highs.append(h)
    highs.extend(equal_high_targets(highs, entry))
    lookbacks = [(60, 'micro_range_high'), (120, 'meso_range_high'), (250, 'macro_range_high')]
    for lb, typ in lookbacks:
        start = max(0, entry_idx - lb)
        prior = ks[start:entry_idx]
        if prior:
            mx = max(f(b.get('h')) for b in prior)
            if mx > entry:
                idx = max(range(start, entry_idx), key=lambda i: f(ks[i].get('h')))
                highs.append({'idx': idx, 'price': mx, 'date': bar_date(ks[idx]), 'scale': typ, 'type': 'RANGE_HIGH', 'target_type': typ})
    dedup: Dict[float, Dict[str, Any]] = {}
    for h in highs:
        price = round(f(h.get('price')), 4)
        if price <= entry:
            continue
        rr = (price - entry) / risk
        rec = {**h, 'price': price, 'rr': round(rr, 4)}
        key = round(price / max(entry, 0.01), 4)
        old = dedup.get(key)
        if old is None or rec['rr'] > old['rr'] or 'EQH' in rec.get('type', ''):
            dedup[key] = rec
    return sorted(dedup.values(), key=lambda x: (x['rr'], x['price']))


def structural_sl(ks: List[Dict[str, Any]], entry_idx: int, entry: float, zone_low: float) -> Tuple[float, str, Dict[str, Any]]:
    lows = []
    for left, right, typ in [(2, 2, 'micro_HL'), (5, 3, 'meso_HL'), (10, 5, 'macro_HL')]:
        for lo in confirmed_pivots(ks, entry_idx, left, right, 'low')[-8:]:
            if 0 < lo['price'] < entry:
                rrisk = (entry / lo['price'] - 1) * 100
                if rrisk <= 4.0:
                    lows.append({**lo, 'support_type': typ})
    if zone_low and zone_low < entry:
        lows.append({'idx': entry_idx, 'price': zone_low, 'date': bar_date(ks[entry_idx]), 'support_type': 'POI_LOW'})
    prior = ks[max(0, entry_idx - 20):entry_idx]
    if prior:
        ssl = min(f(b.get('l')) for b in prior)
        if 0 < ssl < entry and (entry / ssl - 1) * 100 <= 4.0:
            idx = max(0, entry_idx - 20) + min(range(len(prior)), key=lambda j: f(prior[j].get('l')))
            lows.append({'idx': idx, 'price': ssl, 'date': bar_date(ks[idx]), 'support_type': 'SSL_SWEEP_LOW'})
    if not lows:
        sl = entry * 0.975
        return sl, 'FALLBACK_2_5PCT_NO_STRUCTURE', {'price': sl}
    chosen = max(lows, key=lambda x: x['price'])
    sl = min(chosen['price'] * 0.995, entry * 0.995)
    return sl, f"{chosen.get('support_type')}_BUFFER_0_5PCT", chosen


def classify(rr2: float, rr3: float, has_struct_sl: bool, tp2_type: str, tp3_type: str, pd_zone: str = '', zone_width: float = 0.0, market_state: str = '') -> str:
    strong_target = any(x in (tp2_type + '|' + tp3_type) for x in ['BSL', 'EQH', 'range_high', 'RANGE_HIGH'])
    reachable_5r = 5 <= rr2 < 6.5
    high_quality_deep_or_narrow = rr2 < 8 and (pd_zone == 'DEEP_DISCOUNT' or zone_width < 0.8)
    avoid_weak_macro_chase = rr2 < 12
    if has_struct_sl and strong_target and rr2 >= 5 and rr3 >= 8 and avoid_weak_macro_chase and (reachable_5r or high_quality_deep_or_narrow):
        return 'A_PRODUCTION'
    if has_struct_sl and strong_target and rr2 >= 5 and rr3 >= 8:
        return 'B_LIGHT_OR_OBSERVE'
    if has_struct_sl and strong_target and rr2 >= 4 and rr3 >= 6:
        return 'C_WATCH_ONLY'
    if rr2 >= 2:
        return 'C_WATCH_ONLY'
    return 'D_REJECT'


def build_contract(c: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    gate = v91_gate_reason(c)
    if gate == 'REJECT':
        return None
    entry_mode, entry = entry_plan_for(c)
    if not entry:
        return None
    fill_idx = fill_idx_for_limit(c, ks, entry)
    if fill_idx < 1 or fill_idx >= len(ks) - 2:
        return None
    pick_date = date_key(c.get('pick_date') or c.get('select_date') or c.get('event_date'))
    join_date = bar_date(ks[fill_idx])
    if not pick_date or not join_date or pick_date == join_date:
        return None
    zl, zh = f(c.get('zone_low')), f(c.get('zone_high'))
    sl, sl_mode, sl_ref = structural_sl(ks, fill_idx, entry, zl)
    risk = entry - sl
    if risk <= 0:
        return None
    targets = structural_targets(ks, fill_idx, entry, sl)
    tp1 = next((x for x in targets if x['rr'] >= 2), None) or (targets[0] if targets else None)
    tp2 = next((x for x in targets if x['rr'] >= 5), None)
    tp3 = next((x for x in targets if x['rr'] >= 8), None)
    if tp2 is None and targets:
        tp2 = targets[-1]
    if tp3 is None and targets:
        tp3 = targets[-1]
    rr2 = f(tp2.get('rr')) if tp2 else 0
    rr3 = f(tp3.get('rr')) if tp3 else 0
    grade = classify(rr2, rr3, not sl_mode.startswith('FALLBACK'), tp2.get('target_type','') if tp2 else '', tp3.get('target_type','') if tp3 else '', c.get('pd_zone') or '', zone_width_pct(c) or 0.0, c.get('market_state') or '')
    substate = recovery_substate(c, ks)
    row = dict(c)
    row.update({
        'engine': ENGINE, 'signal_engine': SIGNAL_LAYER, 'contract_source': CONTRACT_SOURCE,
        'v98_reachable_5r_gate': True, 'v97_structural_contract': True, 'v91_gate_reason': gate, 'v90_recovery_substate': substate,
        'entry_mode': entry_mode, 'sl_mode': sl_mode, 'tp_mode': 'STRUCTURAL_5R_REACHABILITY_GATE',
        'pick_date': pick_date, 'select_date': pick_date, 'join_date': join_date, 'entry_date': join_date,
        'entry_idx': fill_idx, 'price': round(entry,4), 'entry_price': round(entry,4),
        'sl': round(sl,4), 'sl_price': round(sl,4), 'risk_abs': round(risk,4), 'risk_pct': round((entry/sl-1)*100,4),
        'tp1': round(f(tp1.get('price')) if tp1 else 0,4), 'tp2': round(f(tp2.get('price')) if tp2 else 0,4), 'tp3': round(f(tp3.get('price')) if tp3 else 0,4),
        'tp': round(f(tp2.get('price')) if tp2 else 0,4), 'tp1_price': round(f(tp1.get('price')) if tp1 else 0,4),
        'tp1_rr': round(f(tp1.get('rr')) if tp1 else 0,4), 'tp2_rr': round(rr2,4), 'tp3_rr': round(rr3,4), 'rr': round(rr2,4),
        'tp1_target_type': tp1.get('target_type','') if tp1 else 'NO_STRUCTURAL_TARGET',
        'tp2_target_type': tp2.get('target_type','') if tp2 else 'NO_STRUCTURAL_TARGET',
        'tp3_target_type': tp3.get('target_type','') if tp3 else 'NO_STRUCTURAL_TARGET',
        'structural_targets': targets[:20], 'structural_sl_ref': sl_ref,
        'production_grade': grade,
        'pick_scope': 'ACTIVE_CANDIDATE' if grade == 'A_PRODUCTION' else 'WATCH_ONLY',
        'is_active_pick': grade == 'A_PRODUCTION',
        'setup_status': 'V98_REACHABLE_5R_PRODUCTION' if grade == 'A_PRODUCTION' else grade,
        'state': 'ACTIVE_CANDIDATE' if grade == 'A_PRODUCTION' else 'WATCH_ONLY',
        'zone_type': c.get('zone_type') or c.get('poi_type') or 'DEMAND_OB',
        'signal_type': c.get('signal_type') or c.get('event_type') or c.get('poi_type') or 'DEMAND_OB',
        'zone_low': round(zl,4), 'zone_high': round(zh,4), 'zone': f"{round(zl,4):.4f}~{round(zh,4):.4f}",
        'smart_money_cost': round((zl+zh)/2 if zl and zh else entry,4), 'cost_line': round((zl+zh)/2 if zl and zh else entry,4),
        'volatility_pct': round(zone_width_pct(c) or f(c.get('risk_pct')) or 0.01,4), 'volatility': round(zone_width_pct(c) or f(c.get('risk_pct')) or 0.01,4),
        'pickDate': pick_date, 'joinDate': join_date, 'selectDate': pick_date, 'entryDate': join_date,
        '选股日期': pick_date, '加入日期': join_date,
        'planned_exit_legs': [
            {'name': 'TP1_PROTECT_STRUCT', 'price': round(f(tp1.get('price')) if tp1 else 0,4), 'rr': round(f(tp1.get('rr')) if tp1 else 0,4), 'weight': 0.20},
            {'name': 'TP2_MAIN_STRUCT_GE_5R', 'price': round(f(tp2.get('price')) if tp2 else 0,4), 'rr': round(rr2,4), 'weight': 0.50},
            {'name': 'TP3_RUNNER_STRUCT_GE_8R', 'price': round(f(tp3.get('price')) if tp3 else 0,4), 'rr': round(rr3,4), 'weight': 0.30},
        ],
    })
    return row


def simulate(ks: List[Dict[str, Any]], row: Dict[str, Any]) -> Dict[str, Any]:
    entry_idx = int(f(row.get('entry_idx'))); ep=f(row.get('entry_price')); sl=f(row.get('sl')); tp1=f(row.get('tp1')); tp2=f(row.get('tp2')); tp3=f(row.get('tp3'))
    hit1=False; exit_price=ep; reason='TIME_STOP'; exit_idx=min(len(ks)-1, entry_idx+MAX_HOLD); max_h=ep; min_l=ep
    for i in range(entry_idx+1, min(len(ks), entry_idx+MAX_HOLD+1)):
        h=f(ks[i].get('h')); l=f(ks[i].get('l')); c=f(ks[i].get('c'))
        max_h=max(max_h,h); min_l=min(min_l,l)
        if l <= sl:
            exit_idx=i; exit_price=sl; reason='SL_HIT'; break
        if tp1 and h>=tp1: hit1=True
        if tp2 and h>=tp2:
            exit_idx=i; exit_price=tp2; reason='TP2_MAIN_HIT'; break
        if tp3 and h>=tp3:
            exit_idx=i; exit_price=tp3; reason='TP3_RUNNER_HIT'; break
        exit_price=c
    pnl=(exit_price/ep-1)*100 if ep else 0
    risk=ep-sl
    return {**row, 'active_sl': round(sl,4), 'active_sl_mode': 'STRUCTURAL_SL', 'exit_idx': exit_idx, 'exit_date': bar_date(ks[exit_idx]), 'exit_price': round(exit_price,4), 'exit_reason': reason, 'pnl_pct': round(pnl,4), 'hit_tp1': hit1, 'hit_tp2': reason in ('TP2_MAIN_HIT','TP3_RUNNER_HIT'), 'mfe_r': round((max_h-ep)/risk,4) if risk>0 else 0, 'mae_r': round((ep-min_l)/risk,4) if risk>0 else 0, 'hold_bars_realized': exit_idx-entry_idx}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_grade=Counter(r.get('production_grade') for r in rows)
    trades=[r for r in rows if r.get('production_grade')=='A_PRODUCTION']
    wins=[r for r in trades if f(r.get('pnl_pct'))>0]
    return {
        'generated_at': datetime.now().isoformat(timespec='seconds'), 'engine': ENGINE,
        'rows': len(rows), 'grade_counts': dict(by_grade), 'production_trades': len(trades),
        'production_wr': round(len(wins)/len(trades)*100,2) if trades else 0,
        'production_avg_pnl': round(sum(f(r.get('pnl_pct')) for r in trades)/len(trades),4) if trades else 0,
        'production_cum_pnl': round(sum(f(r.get('pnl_pct')) for r in trades),4) if trades else 0,
        'production_sl_rate': round(sum(1 for r in trades if r.get('exit_reason')=='SL_HIT')/len(trades)*100,2) if trades else 0,
        'rr2_distribution': dist([f(r.get('tp2_rr')) for r in rows]),
        'rr3_distribution': dist([f(r.get('tp3_rr')) for r in rows]),
        'exit_counts': dict(Counter(r.get('exit_reason') for r in trades)),
    }


def dist(vals: List[float]) -> Dict[str, Any]:
    vals=sorted([v for v in vals if v>0])
    if not vals: return {}
    return {'n':len(vals),'min':round(vals[0],3),'p25':round(vals[int(.25*(len(vals)-1))],3),'median':round(statistics.median(vals),3),'p75':round(vals[int(.75*(len(vals)-1))],3),'p95':round(vals[int(.95*(len(vals)-1))],3),'max':round(vals[-1],3)}


def main() -> None:
    env_raw=load_json(ENV_PATH); env_by_date={str(k)[:8]: normalize_env(v) for k,v in env_raw.items()}
    all_rows=[]; active_by_symbol={}; scanned=0; latest_date=''; rejects=Counter()
    for path in sorted(KLINE_DIR.glob('*_daily_750.json')):
        ks=load_json(path)
        if len(ks)<120: continue
        scanned+=1; sym=symbol_from_path(path); latest_date=max(latest_date, bar_date(ks[-1]))
        try: cands=generate_v85_candidates(sym, ks, env_by_date)
        except Exception as e: rejects[f'GENERATOR_ERROR:{type(e).__name__}']+=1; continue
        for c in cands:
            c=dict(c); c['v85_zone_width_pct']=round(zone_width_pct(c),4)
            entry_idx=int(f(c.get('entry_idx'),-1)); takeover_idx=int(f(c.get('v83_takeover_idx'), c.get('reclaim_idx') or -1))
            c['hold_bars']=max(0, entry_idx-takeover_idx) if entry_idx>=0 and takeover_idx>=0 else 999
            row=build_contract(c,ks)
            if row is None: rejects['NO_CONTRACT_OR_GATE_REJECT']+=1; continue
            sim=simulate(ks,row); all_rows.append(sim)
            if latest_date and date_key(sim.get('entry_date')) >= date_key(latest_date):
                pass
            # recent active/watch list by last 45 bars
            if int(f(sim.get('entry_idx'))) >= len(ks)-RECENT_BARS:
                old=active_by_symbol.get(sym)
                if old is None or date_key(sim.get('entry_date')) > date_key(old.get('entry_date')):
                    active_by_symbol[sym]=sim
    active=sorted(active_by_symbol.values(), key=lambda r:(r.get('production_grade'), r.get('entry_date'), r.get('symbol')), reverse=True)
    report=summarize(all_rows); report.update({'scanned':scanned,'latest_date':latest_date,'reject_counts':dict(rejects),'active_rows':len(active),'active_grade_counts':dict(Counter(r.get('production_grade') for r in active))})
    (OUT/'v98_structural_trades.json').write_text(json.dumps(all_rows, ensure_ascii=False, indent=2))
    (OUT/'v98_active_picks.json').write_text(json.dumps(active, ensure_ascii=False, indent=2))
    (OUT/'v98_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
