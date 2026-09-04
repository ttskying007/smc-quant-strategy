#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

BASE_TRADES = Path('/root/.hermes/smc_opt_v86_production_gate/v86_trades.json')
BASE_PICKS = Path('/root/.hermes/smc_opt_v86_production_gate/v86_picks.json')
V87_ROWS = Path('/root/.hermes/smc_opt_v87_mtf_entry_rr_matrix/v87_matrix_rows.json')
KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v88_production_contract')
OUT.mkdir(parents=True, exist_ok=True)

# V88 chooses the balanced production candidate from V87:
# - fixes low RR (RR<1 = 0)
# - materially improves avg RR versus V86
# - keeps WR > 80 and every year > 75
# - avoids 60min entry hard dependency because 60min history coverage is incomplete.
ENTRY_MODE = 'zone_limit'
SL_MODE = 'hybrid_tight'
TP_MODE = 'liq_then_2r_runner'
ENGINE = 'V88_PRODUCTION_CONTRACT'


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def date_key(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def kline_path(symbol: str) -> Path:
    stem = str(symbol or '').replace('.', '_')
    p = KLINE / f'{stem}_daily_750.json'
    return p if p.exists() else KLINE / f'{stem}_daily_300.json'


def bar_date(b: Dict[str, Any]) -> str:
    return date_key(b.get('t') or b.get('date'))


def slice_after(bars: List[Dict[str, Any]], date: str, max_days: int = 80) -> List[Dict[str, Any]]:
    ds = date_key(date)
    return [b for b in bars if bar_date(b) > ds][:max_days]


def tp_plan(entry: float, sl: float, liq: float) -> tuple[float, float, float]:
    risk = entry - sl
    tp1 = max(liq, entry + risk)
    return tp1, max(liq, entry + 2 * risk), max(liq, entry + 3 * risk)


def simulate_exit_legs(daily: List[Dict[str, Any]], entry_price: float, sl: float, tp1: float, tp2: float, tp3: float, max_hold: int = 40) -> Dict[str, Any]:
    ep, sl, tp1, tp2, tp3 = map(f, [entry_price, sl, tp1, tp2, tp3])
    risk = ep - sl
    legs = []
    remaining = 1.0
    exit_price = ep
    reason = 'TIME_STOP'
    pnl = 0.0
    mfe = -999.0
    mae = 999.0
    trail = None
    weights = [('TP1_HIT', tp1, 0.35), ('TP2_HIT', tp2, 0.35), ('TP3_HIT', tp3, 0.30)]
    hit = set()
    for b in daily[:max_hold]:
        hi, lo, cl = f(b.get('h')), f(b.get('l')), f(b.get('c'))
        mfe = max(mfe, (hi / ep - 1) * 100)
        mae = min(mae, (lo / ep - 1) * 100)
        if lo <= sl and not legs:
            pnl = (sl / ep - 1) * 100
            exit_price = sl
            reason = 'SL_HIT'
            remaining = 0
            break
        for name, tp, w in weights:
            if name not in hit and hi >= tp and remaining > 0:
                take = min(w, remaining)
                legs.append({'reason': name, 'price': round(tp, 4), 'weight': take, 'date': bar_date(b)})
                pnl += take * (tp / ep - 1) * 100
                remaining -= take
                hit.add(name)
                if name in {'TP2_HIT', 'TP3_HIT'}:
                    trail = max(trail or sl, ep + risk)
        if remaining <= 0:
            exit_price = tp3
            reason = 'TP3_HIT'
            break
        if trail and lo <= trail:
            pnl += remaining * (trail / ep - 1) * 100
            exit_price = trail
            reason = 'RUNNER_TRAIL'
            remaining = 0
            break
        exit_price = cl
    if remaining > 0:
        last = daily[min(len(daily), max_hold) - 1] if daily else {'c': ep}
        exit_price = f(last.get('c'), ep)
        pnl += remaining * (exit_price / ep - 1) * 100
        reason = 'TIME_STOP'
    return {
        'exit_price': round(exit_price, 4),
        'pnl_pct': round(pnl, 4),
        'exit_reason': reason,
        'exit_legs': legs,
        'mfe_pct': round(mfe if mfe != -999 else 0, 4),
        'mae_pct': round(mae if mae != 999 else 0, 4),
        'mfe_r': round((mfe / 100 * ep) / risk, 4) if risk > 0 and mfe != -999 else 0,
        'mae_r': round((mae / 100 * ep) / risk, 4) if risk > 0 and mae != 999 else 0,
    }


def metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'avg_rr': 0, 'low_rr_rate': 0, 'sl_rate': 0}
    n = len(rows)
    pnl = [f(r.get('pnl_pct')) for r in rows]
    rr = [f(r.get('rr')) for r in rows]
    return {
        'n': n,
        'wr': round(sum(x > 0 for x in pnl) / n * 100, 2),
        'avg_pnl': round(sum(pnl) / n, 4),
        'cum': round(sum(pnl), 2),
        'avg_rr': round(sum(rr) / n, 4),
        'low_rr_rate': round(sum(x < 1 for x in rr) / n * 100, 2),
        'sl_rate': round(sum(str(r.get('exit_reason')) == 'SL_HIT' for r in rows) / n * 100, 2),
        'avg_mfe_r': round(sum(f(r.get('mfe_r')) for r in rows) / n, 4),
        'avg_mae_r': round(sum(f(r.get('mae_r')) for r in rows) / n, 4),
    }


def bucket(rows: List[Dict[str, Any]], key):
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(groups.items())}


def apply_contract(base: Dict[str, Any], v87: Dict[str, Any], daily_bars: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    row = dict(base)
    original_entry = f(base.get('entry_price'))
    entry = f(v87.get('entry_price'))
    sl = f(v87.get('sl'))
    tp1 = f(v87.get('tp1'))
    tp2 = f(v87.get('tp2'))
    tp3 = f(v87.get('tp3'))
    execution_repair = ''
    entry_date = date_key(base.get('entry_date'))
    if daily_bars and entry_date:
        day = next((b for b in daily_bars if bar_date(b) == entry_date), None)
        if day and entry and not (f(day.get('l')) <= entry <= f(day.get('h'))):
            execution_repair = 'ZONE_LIMIT_NOT_TOUCHED_USE_NEXT_OPEN'
            old_risk_pct = (entry - sl) / entry * 100 if entry and sl else 0
            fallback_entry = original_entry
            day_open = f(day.get('o'))
            day_low = f(day.get('l'))
            day_high = f(day.get('h'))
            if fallback_entry and day_low and day_high and not (day_low <= fallback_entry <= day_high):
                fallback_entry = day_open if day_low <= day_open <= day_high else day.get('c')
            entry = f(fallback_entry)
            sl = entry * (1 - old_risk_pct / 100) if entry and old_risk_pct else sl
            tp1, tp2, tp3 = tp_plan(entry, sl, f(base.get('liquidity_target')))
            sim = simulate_exit_legs(slice_after(daily_bars, entry_date, 60), entry, sl, tp1, tp2, tp3, max_hold=40)
            v87 = {
                **v87,
                **sim,
                'rr': (tp2 - entry) / (entry - sl) if entry > sl else 0,
                'rr_realized': sim['pnl_pct'] / old_risk_pct if old_risk_pct else 0,
            }
    risk_pct = (entry - sl) / entry * 100 if entry and sl else 0
    row.update({
        'engine': ENGINE,
        'signal_engine': base.get('engine') or 'V86_PRODUCTION_GATE',
        'contract_source': 'V86_SIGNAL_LAYER_PLUS_V87_RISK_CONTRACT',
        'v88_combo': f'{ENTRY_MODE}|{SL_MODE}|{TP_MODE}',
        'entry_mode': ENTRY_MODE,
        'execution_repair': execution_repair,
        'sl_mode': SL_MODE,
        'tp_mode': TP_MODE,
        'entry_price_original_v86': round(original_entry, 4),
        'entry_price_fallback_source': 'entry_day_open' if execution_repair and abs(entry - f(day.get('o') if 'day' in locals() else 0)) < 1e-6 else ('original_v86' if execution_repair else ''),
        'entry_price': round(entry, 4),
        'price': round(entry, 4),
        'sl': round(sl, 4),
        'sl_price': round(sl, 4),
        'tp1': round(tp1, 4),
        'tp2': round(tp2, 4),
        'tp3': round(tp3, 4),
        'tp': round(tp1, 4),
        'tp1_price': round(tp1, 4),
        'risk_pct': round(risk_pct, 4),
        'risk_pct_v86': base.get('risk_pct'),
        'risk_pct_v87': v87.get('risk_pct_v87'),
        'rr': v87.get('rr'),
        'rr_realized': v87.get('rr_realized'),
        'exit_price': v87.get('exit_price'),
        'exit_reason': v87.get('exit_reason'),
        'pnl_pct': v87.get('pnl_pct'),
        'exit_legs': v87.get('exit_legs') or [],
        'mfe_pct': v87.get('mfe_pct'),
        'mae_pct': v87.get('mae_pct'),
        'mfe_r': v87.get('mfe_r'),
        'mae_r': v87.get('mae_r'),
        'weekly_state': v87.get('weekly_state'),
        'daily_state': v87.get('daily_state'),
        'm60_state': v87.get('m60_state'),
        'mtf_score': v87.get('mtf_score'),
        'm60_entry_state': v87.get('m60_entry_state'),
        'planned_exit_signal': 'TP1_TP2_RUNNER_CONTRACT',
        'planned_exit_price': round(tp1, 4),
        'planned_exit_legs': [
            {'name': 'TP1', 'price': round(tp1, 4), 'weight': 0.35},
            {'name': 'TP2', 'price': round(tp2, 4), 'weight': 0.35},
            {'name': 'TP3_RUNNER', 'price': round(tp3, 4), 'weight': 0.30},
        ],
        'smart_money_cost': round(f(base.get('smart_money_cost')) or (f(base.get('zone_low')) + f(base.get('zone_high'))) / 2 or entry, 4),
        'cost_line': round(f(base.get('cost_line') or base.get('smart_money_cost')) or (f(base.get('zone_low')) + f(base.get('zone_high'))) / 2 or entry, 4),
        'volatility_pct': round(f(base.get('volatility_pct') or base.get('v85_zone_width_pct') or risk_pct), 4),
        'zone_type': base.get('zone_type') or base.get('poi_type') or 'DEMAND_OB',
        'signal_type': base.get('signal_type') or base.get('zone_type') or base.get('poi_type') or 'DEMAND_OB',
        'pick_date': date_key(base.get('pick_date') or base.get('select_date') or base.get('event_date')),
        'select_date': date_key(base.get('select_date') or base.get('pick_date') or base.get('event_date')),
        'join_date': date_key(base.get('join_date') or base.get('entry_date')),
        'pick_scope': 'ACTIVE_CANDIDATE',
        'is_active_pick': True,
        'setup_status': 'V88_PRODUCTION_READY',
        'state': 'ACTIVE_CANDIDATE',
        'sample_class': 'PRODUCTION_CLEAN',
        'sample_issue_flags': [],
        't1_violation': date_key(base.get('entry_date')) >= date_key(v87.get('exit_date')) if v87.get('exit_date') else False,
    })
    return row


def main() -> None:
    base_trades = load(BASE_TRADES, [])
    base_picks = load(BASE_PICKS, [])
    v87_rows = load(V87_ROWS, [])
    daily_cache: Dict[str, List[Dict[str, Any]]] = {}
    chosen = [r for r in v87_rows if r.get('entry_mode') == ENTRY_MODE and r.get('sl_mode') == SL_MODE and r.get('tp_mode') == TP_MODE]
    v87_by_key = {(r.get('symbol'), date_key(r.get('entry_date'))): r for r in chosen}
    trades = []
    missing = []
    for b in base_trades:
        k = (b.get('symbol'), date_key(b.get('entry_date')))
        v = v87_by_key.get(k)
        if not v:
            missing.append(k)
            continue
        sym = b.get('symbol')
        if sym not in daily_cache:
            daily_cache[sym] = load(kline_path(sym), [])
        trades.append(apply_contract(b, v, daily_cache[sym]))
    pick_by_key = {(p.get('symbol'), date_key(p.get('entry_date'))): p for p in base_picks}
    picks = []
    for t in trades:
        k = (t.get('symbol'), date_key(t.get('entry_date')))
        base = pick_by_key.get(k, t)
        sym = t.get('symbol')
        if sym not in daily_cache:
            daily_cache[sym] = load(kline_path(sym), [])
        p = apply_contract(base, v87_by_key[k], daily_cache[sym])
        # Picks are current candidates/watchlist contract rows; keep historical outcome fields
        # for audit, but front-end execution should consume explicit risk contract fields.
        p['source_trade_outcome'] = {
            'exit_reason': p.get('exit_reason'),
            'pnl_pct': p.get('pnl_pct'),
            'exit_legs': p.get('exit_legs'),
        }
        picks.append(p)
    field_keys = ['engine','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','volatility_pct','entry_price','sl','tp1','tp2','tp3','rr','rr_realized','exit_legs','mfe_r','mae_r','weekly_state','daily_state','m60_state','mtf_score']
    field_audit = {k: sum(1 for r in trades if r.get(k) in (None, '') or (k in {'zone_low','zone_high','cost_line','entry_price','sl','tp1','tp2','tp3','rr'} and f(r.get(k)) <= 0)) for k in field_keys}
    t1_violations = [r for r in trades if date_key(r.get('entry_date')) >= date_key(r.get('exit_date'))]
    report = {
        'engine': ENGINE,
        'source_signal_layer': str(BASE_TRADES),
        'source_contract_matrix': str(V87_ROWS),
        'combo': f'{ENTRY_MODE}|{SL_MODE}|{TP_MODE}',
        'base_rows': len(base_trades),
        'chosen_contract_rows': len(chosen),
        'trades': metrics(trades),
        'by_year': bucket(trades, lambda r: date_key(r.get('entry_date'))[:4]),
        'by_market_state': bucket(trades, lambda r: r.get('market_state')),
        'by_path': bucket(trades, lambda r: r.get('v85_path')),
        'by_mtf_score': bucket(trades, lambda r: r.get('mtf_score')),
        'by_exit_reason': bucket(trades, lambda r: r.get('exit_reason')),
        'field_audit': field_audit,
        'execution_repair_count': sum(1 for r in trades if r.get('execution_repair')),
        't1_violation_count': len(t1_violations),
        'missing_contract_keys': missing[:20],
        'production_gate': {
            'total_ge_500': len(trades) >= 500,
            'field_missing_zero': all(v == 0 for v in field_audit.values()),
            't1_zero': len(t1_violations) == 0,
            'low_rr_zero': metrics(trades)['low_rr_rate'] == 0,
            'year_min_ge_50_and_wr_ge_65': all((bucket(trades, lambda r: date_key(r.get('entry_date'))[:4]).get(y, {}).get('n', 0) >= 50 and bucket(trades, lambda r: date_key(r.get('entry_date'))[:4]).get(y, {}).get('wr', 0) >= 65) for y in ['2023','2024','2025','2026'])
        }
    }
    (OUT / 'v88_trades.json').write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    (OUT / 'v88_picks.json').write_text(json.dumps(picks, ensure_ascii=False, indent=2))
    (OUT / 'v88_production_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    with (OUT / 'v88_trades.csv').open('w', newline='') as fp:
        fields = sorted({k for r in trades for k in r.keys()}) if trades else []
        w = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(trades)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
