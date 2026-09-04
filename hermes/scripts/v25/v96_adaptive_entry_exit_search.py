#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SRC = Path('/root/.hermes/smc_opt_v88_production_contract/v88_trades.json')
KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v96_adaptive_entry_exit_search')
OUT.mkdir(parents=True, exist_ok=True)

ENTRY_RULES = [
    'zone_high_touch_5d',
    'zone_mid_touch_5d',
    'zone_low_touch_5d',
    'adaptive_width_mid_low_7d',
    'adaptive_risk_mid_high_7d',
]
SL_RULES = [
    'zone_low_1pct_buffer',
    'zone_low_half_vol_buffer',
    'structure_low_or_zone_1pct',
    'adaptive_zone_vol_cap',
]
EXIT_RULES = [
    'v88_like_1r_2r_3r_trail_1r',
    'runner_2r_trail_1p5r_after_3r',
    'runner_3r_wide_after_4r',
    'time_mfe_50pct_cap_3r',
    'adaptive_vol_runner',
]
MAX_HOLD = 40
POST_WINDOW = 20


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def date_key(v: Any) -> str:
    return ''.join(ch for ch in str(v or '') if ch.isdigit())[:8]


def bd(b: Dict[str, Any]) -> str:
    return date_key(b.get('t') or b.get('date'))


def symkey(sym: str) -> str:
    return str(sym).replace('.', '_')


def load_json(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def kpath(sym: str) -> Path:
    return KLINE / f'{symkey(sym)}_daily_750.json'


def clean_bars(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{'date': bd(b), 'o': num(b.get('o') or b.get('open')), 'h': num(b.get('h') or b.get('high')), 'l': num(b.get('l') or b.get('low')), 'c': num(b.get('c') or b.get('close'))} for b in rows if bd(b)]


def after_date(bars: List[Dict[str, Any]], date: str, n: Optional[int] = None) -> List[Dict[str, Any]]:
    ds = date_key(date)
    out = [b for b in bars if b['date'] > ds]
    return out if n is None else out[:n]


def entry_level(row: Dict[str, Any], rule: str) -> float:
    zl, zh = num(row.get('zone_low')), num(row.get('zone_high'))
    mid = (zl + zh) / 2 if zl and zh else num(row.get('entry_price'))
    width = (zh / zl - 1) * 100 if zl else num(row.get('volatility_pct'))
    risk = num(row.get('risk_pct'))
    if rule == 'zone_high_touch_5d':
        return zh
    if rule == 'zone_mid_touch_5d':
        return mid
    if rule == 'zone_low_touch_5d':
        return zl
    if rule == 'adaptive_width_mid_low_7d':
        return zl if width > 1.2 else mid
    if rule == 'adaptive_risk_mid_high_7d':
        return mid if risk > 1.4 else zh
    return num(row.get('entry_price'))


def wait_days_for_entry(rule: str) -> int:
    return 7 if '7d' in rule else 5


def find_limit_entry(row: Dict[str, Any], bars: List[Dict[str, Any]], rule: str) -> Optional[Dict[str, Any]]:
    start = date_key(row.get('pick_date') or row.get('select_date') or row.get('event_date'))
    level = entry_level(row, rule)
    if level <= 0:
        return None
    for i, b in enumerate(after_date(bars, start, wait_days_for_entry(rule))):
        # buy-limit: if market trades through limit; gap below is filled at open for conservative realism
        if b['l'] <= level and b['h'] >= level:
            fill = level
        elif b['o'] <= level and b['h'] >= b['o']:
            fill = min(level, b['o'])
        else:
            continue
        return {'entry_price_v96': round(fill, 4), 'entry_date_v96': b['date'], 'entry_wait_bars': i + 1}
    return None


def sl_price(row: Dict[str, Any], entry: float, rule: str) -> float:
    zl = num(row.get('zone_low'))
    prior = num(row.get('prior_structure_low'))
    vol = max(num(row.get('volatility_pct')), 0.5)
    if rule == 'zone_low_1pct_buffer':
        sl = zl * 0.99
    elif rule == 'zone_low_half_vol_buffer':
        sl = zl * (1 - min(max(vol * 0.5, 0.5), 1.5) / 100)
    elif rule == 'structure_low_or_zone_1pct':
        sl = min(prior if prior > 0 else zl, zl) * 0.99
    elif rule == 'adaptive_zone_vol_cap':
        # universal adaptive buffer: wide zones use smaller buffer, narrow zones use volatility buffer, cap risk.
        buffer_pct = min(max(vol * 0.45, 0.45), 1.2)
        sl = zl * (1 - buffer_pct / 100)
        max_risk_sl = entry * 0.972
        sl = max(sl, max_risk_sl)
    else:
        sl = zl * 0.99
    if sl >= entry:
        sl = entry * 0.985
    return round(sl, 4)


def tp_levels(row: Dict[str, Any], entry: float, sl: float, rule: str) -> Tuple[float, float, float]:
    risk = max(entry - sl, 1e-9)
    liq = num(row.get('liquidity_target'))
    if liq <= entry or liq > entry + 8 * risk:
        liq = entry + 2 * risk
    if rule == 'v88_like_1r_2r_3r_trail_1r':
        return (max(liq, entry + risk), max(liq, entry + 2 * risk), max(liq, entry + 3 * risk))
    if rule == 'runner_2r_trail_1p5r_after_3r':
        return (entry + 1.0 * risk, entry + 2.0 * risk, entry + 3.0 * risk)
    if rule == 'runner_3r_wide_after_4r':
        return (entry + 1.0 * risk, entry + 2.0 * risk, entry + 4.0 * risk)
    if rule == 'time_mfe_50pct_cap_3r':
        return (entry + 0.8 * risk, entry + 1.5 * risk, entry + 3.0 * risk)
    if rule == 'adaptive_vol_runner':
        vol = max(num(row.get('volatility_pct')), 0.5)
        tp1r = 0.8 if vol < 1.0 else 1.0
        tp2r = 1.6 if vol < 1.5 else 2.0
        tp3r = 3.0 if vol < 1.5 else 4.0
        return (entry + tp1r * risk, entry + tp2r * risk, entry + tp3r * risk)
    return (entry + risk, entry + 2 * risk, entry + 3 * risk)


def simulate_exit(row: Dict[str, Any], bars: List[Dict[str, Any]], entry_date: str, entry: float, sl: float, exit_rule: str) -> Optional[Dict[str, Any]]:
    risk = entry - sl
    if entry <= 0 or risk <= 0:
        return None
    t1_bars = after_date(bars, entry_date, MAX_HOLD)
    if not t1_bars:
        return None
    tp1, tp2, tp3 = tp_levels(row, entry, sl, exit_rule)
    weights = [('TP1_HIT', tp1, 0.25), ('TP2_HIT', tp2, 0.25)]
    if exit_rule == 'v88_like_1r_2r_3r_trail_1r':
        weights = [('TP1_HIT', tp1, 0.35), ('TP2_HIT', tp2, 0.35), ('TP3_HIT', tp3, 0.30)]
    remaining = 1.0
    pnl = 0.0
    legs = []
    hit = set()
    high_water = entry
    mfe_r = -999.0
    mae_r = 999.0
    exit_price = entry
    exit_date = entry_date
    reason = 'TIME_STOP'
    runner_active = False
    trail = None
    for i, b in enumerate(t1_bars):
        hi, lo, cl = b['h'], b['l'], b['c']
        high_water = max(high_water, hi)
        mfe_r = max(mfe_r, (hi - entry) / risk)
        mae_r = min(mae_r, (lo - entry) / risk)
        if lo <= sl and not legs:
            return {'exit_price_v96': round(sl, 4), 'exit_date_v96': b['date'], 'exit_reason_v96': 'SL_HIT', 'pnl_pct_v96': round((sl / entry - 1) * 100, 4), 'exit_legs_v96': [], 'mfe_r_v96': round(max(mfe_r, 0), 4), 'mae_r_v96': round(mae_r, 4), 'hold_bars_v96': i + 1}
        for name, tp, w in weights:
            if name not in hit and hi >= tp and remaining > 0:
                hit.add(name)
                take = min(w, remaining)
                pnl += take * (tp / entry - 1) * 100
                remaining -= take
                legs.append({'reason': name, 'price': round(tp, 4), 'weight': round(take, 4), 'date': b['date']})
                if name in {'TP2_HIT', 'TP3_HIT'}:
                    runner_active = True
        if exit_rule == 'v88_like_1r_2r_3r_trail_1r' and remaining <= 0:
            return {'exit_price_v96': round(tp3, 4), 'exit_date_v96': b['date'], 'exit_reason_v96': 'TP3_HIT', 'pnl_pct_v96': round(pnl, 4), 'exit_legs_v96': legs, 'mfe_r_v96': round(mfe_r, 4), 'mae_r_v96': round(mae_r, 4), 'hold_bars_v96': i + 1}
        if hi >= tp2:
            runner_active = True
        if runner_active and remaining > 0:
            if exit_rule == 'runner_2r_trail_1p5r_after_3r':
                if high_water >= entry + 3 * risk:
                    trail = max(entry + 1.0 * risk, high_water - 1.5 * risk)
            elif exit_rule == 'runner_3r_wide_after_4r':
                if high_water >= entry + 4 * risk:
                    trail = max(entry + 1.0 * risk, high_water - 3.0 * risk)
            elif exit_rule == 'adaptive_vol_runner':
                vol = max(num(row.get('volatility_pct')), 0.5)
                giveback = 1.5 if vol < 1.5 else 2.5
                activate = 2.5 if vol < 1.5 else 3.5
                if high_water >= entry + activate * risk:
                    trail = max(entry + 0.8 * risk, high_water - giveback * risk)
            elif exit_rule == 'time_mfe_50pct_cap_3r':
                if high_water >= entry + 3 * risk:
                    trail = max(entry + 1.0 * risk, high_water - 2.0 * risk)
            if trail is not None and lo <= trail:
                pnl += remaining * (trail / entry - 1) * 100
                legs.append({'reason': 'RUNNER_TRAIL', 'price': round(trail, 4), 'weight': round(remaining, 4), 'date': b['date']})
                return {'exit_price_v96': round(trail, 4), 'exit_date_v96': b['date'], 'exit_reason_v96': 'RUNNER_TRAIL', 'pnl_pct_v96': round(pnl, 4), 'exit_legs_v96': legs, 'mfe_r_v96': round(mfe_r, 4), 'mae_r_v96': round(mae_r, 4), 'hold_bars_v96': i + 1}
        exit_price = cl
        exit_date = b['date']
    # TIME_STOP close/capture.
    if remaining > 0:
        if exit_rule in {'time_mfe_50pct_cap_3r', 'adaptive_vol_runner'} and mfe_r >= 1.5:
            target_r = min(max(mfe_r * 0.5, 1.5), 3.0)
            exit_price = entry + target_r * risk
            reason = 'TIME_STOP_MFE_CAPTURE'
        else:
            reason = 'TIME_STOP_CLOSE'
        pnl += remaining * (exit_price / entry - 1) * 100
        legs.append({'reason': reason, 'price': round(exit_price, 4), 'weight': round(remaining, 4), 'date': exit_date})
    return {'exit_price_v96': round(exit_price, 4), 'exit_date_v96': exit_date, 'exit_reason_v96': reason, 'pnl_pct_v96': round(pnl, 4), 'exit_legs_v96': legs, 'mfe_r_v96': round(max(mfe_r, 0), 4), 'mae_r_v96': round(mae_r, 4), 'hold_bars_v96': len([b for b in t1_bars if b['date'] <= exit_date])}


def post_after_exit(bars: List[Dict[str, Any]], exit_date: str, exit_price: float) -> Dict[str, Any]:
    post = after_date(bars, exit_date, POST_WINDOW)
    if not post or exit_price <= 0:
        return {'post20_max_after_exit_pct_v96': 0.0, 'post20_min_after_exit_pct_v96': 0.0, 'post20_big_up10_v96': False}
    mx = max(b['h'] for b in post)
    mn = min(b['l'] for b in post)
    return {'post20_max_after_exit_pct_v96': round((mx / exit_price - 1) * 100, 4), 'post20_min_after_exit_pct_v96': round((mn / exit_price - 1) * 100, 4), 'post20_big_up10_v96': (mx / exit_price - 1) * 100 >= 10}


def metrics(rows: List[Dict[str, Any]], pnl='pnl_pct_v96', reason='exit_reason_v96') -> Dict[str, Any]:
    if not rows:
        return {'n': 0, 'wr': 0, 'avg': 0, 'cum': 0, 'sl_rate': 0, 'time_rate': 0, 'runner_rate': 0, 'post20_big_up10_rate': 0}
    vals = [num(r.get(pnl)) for r in rows]
    n = len(rows)
    return {
        'n': n,
        'wr': round(sum(v > 0 for v in vals) / n * 100, 2),
        'avg': round(sum(vals) / n, 4),
        'cum': round(sum(vals), 2),
        'sl_rate': round(sum(r.get(reason) == 'SL_HIT' for r in rows) / n * 100, 2),
        'time_rate': round(sum('TIME_STOP' in str(r.get(reason)) for r in rows) / n * 100, 2),
        'runner_rate': round(sum('RUNNER' in str(r.get(reason)) for r in rows) / n * 100, 2),
        'post20_big_up10_rate': round(sum(bool(r.get('post20_big_up10_v96')) for r in rows) / n * 100, 2),
    }


def baseline_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0, 'wr': 0, 'avg': 0}
    vals = [num(r.get('pnl_pct')) for r in rows]
    return {'n': len(rows), 'wr': round(sum(v > 0 for v in vals) / len(vals) * 100, 2), 'avg': round(sum(vals) / len(vals), 4), 'cum': round(sum(vals), 2)}


def bucket(rows: List[Dict[str, Any]], key) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def baseline_post_exit(trades: List[Dict[str, Any]], kcache: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    vals = []
    for r in trades:
        bars = kcache.get(r.get('symbol'), [])
        px = num(r.get('exit_price'))
        post = post_after_exit(bars, r.get('exit_date'), px)
        vals.append(post)
    return {'post20_big_up10_rate': round(sum(v['post20_big_up10_v96'] for v in vals) / len(vals) * 100, 2) if vals else 0}


def run_search(write_outputs: bool = True) -> Dict[str, Any]:
    trades = load_json(SRC, [])
    kcache = {r['symbol']: clean_bars(load_json(kpath(r['symbol']), [])) for r in trades}
    matrix: List[Dict[str, Any]] = []
    missing_kline = sorted({s for s, bars in kcache.items() if not bars})
    for r in trades:
        bars = kcache.get(r.get('symbol'), [])
        if not bars:
            continue
        for er in ENTRY_RULES:
            ent = find_limit_entry(r, bars, er)
            if not ent:
                continue
            entry = ent['entry_price_v96']
            for sr in SL_RULES:
                sl = sl_price(r, entry, sr)
                if sl <= 0 or sl >= entry:
                    continue
                for xr in EXIT_RULES:
                    sim = simulate_exit(r, bars, ent['entry_date_v96'], entry, sl, xr)
                    if not sim:
                        continue
                    row = {k: r.get(k) for k in ['symbol', 'pick_date', 'select_date', 'event_date', 'market_state', 'daily_state', 'v85_path', 'zone_low', 'zone_high', 'liquidity_target', 'volatility_pct']}
                    row.update(ent)
                    row.update({'entry_rule': er, 'sl_rule': sr, 'exit_rule': xr, 'sl_v96': sl})
                    tps = tp_levels(r, entry, sl, xr)
                    row.update({'tp1_v96': round(tps[0], 4), 'tp2_v96': round(tps[1], 4), 'tp3_v96': round(tps[2], 4)})
                    row.update(sim)
                    row.update(post_after_exit(bars, sim['exit_date_v96'], sim['exit_price_v96']))
                    row['t1_violation_v96'] = date_key(row['entry_date_v96']) >= date_key(row['exit_date_v96'])
                    matrix.append(row)
    by_combo: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in matrix:
        by_combo[f"{r['entry_rule']}|{r['sl_rule']}|{r['exit_rule']}"].append(r)
    scored = []
    for combo, rows in by_combo.items():
        m = metrics(rows)
        yy = bucket(rows, lambda x: date_key(x.get('entry_date_v96'))[:4])
        score = m['avg'] + 0.03 * m['wr'] - 0.01 * m['post20_big_up10_rate'] + min(m['n'], 532) / 532 * 0.2
        m.update({'combo': combo, 'entry_rule': combo.split('|')[0], 'sl_rule': combo.split('|')[1], 'exit_rule': combo.split('|')[2], 'score': round(score, 4), 'by_year': yy})
        scored.append(m)
    baseline = baseline_metrics(trades)
    base_post = baseline_post_exit(trades, kcache)
    production_like = [s for s in scored if s['n'] >= 300 and s['wr'] >= 80 and s['avg'] > baseline['avg'] and s['post20_big_up10_rate'] < base_post['post20_big_up10_rate']]
    best = sorted(production_like or scored, key=lambda x: (x['score'], x['avg'], x['wr'], x['n']), reverse=True)[:20]
    best_rows = by_combo.get(best[0]['combo'], []) if best else []
    report = {
        'engine': 'V96_ADAPTIVE_ENTRY_EXIT_SEARCH',
        'source': str(SRC),
        'source_trade_count': len(trades),
        'rules': {'entry': ENTRY_RULES, 'sl': SL_RULES, 'exit': EXIT_RULES},
        'matrix_rows': len(matrix),
        'baseline_v88': baseline,
        'baseline_post_exit': base_post,
        'best_by_score': best,
        'field_audit': {
            'missing_kline_count': len(missing_kline),
            't1_violation_count': sum(bool(r.get('t1_violation_v96')) for r in matrix),
            'stock_specific_rule_count': sum(('symbol' in x.lower() or '000' in x) for x in ENTRY_RULES + SL_RULES + EXIT_RULES),
        },
    }
    if write_outputs:
        (OUT / 'v96_matrix_rows.json').write_text(json.dumps(matrix, ensure_ascii=False, indent=2))
        (OUT / 'v96_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        (OUT / 'v96_best_rows.json').write_text(json.dumps(best_rows, ensure_ascii=False, indent=2))
        with (OUT / 'v96_best_rows.csv').open('w', newline='') as fp:
            fields = sorted({k for r in best_rows for k in r.keys() if k != 'exit_legs_v96'})
            w = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
            w.writeheader(); w.writerows(best_rows)
    return report


if __name__ == '__main__':
    rep = run_search(True)
    print(json.dumps({
        'engine': rep['engine'],
        'source_trade_count': rep['source_trade_count'],
        'matrix_rows': rep['matrix_rows'],
        'baseline_v88': rep['baseline_v88'],
        'baseline_post_exit': rep['baseline_post_exit'],
        'best_by_score_top5': rep['best_by_score'][:5],
        'field_audit': rep['field_audit'],
        'out': str(OUT),
    }, ensure_ascii=False, indent=2))
