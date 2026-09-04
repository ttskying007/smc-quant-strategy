#!/usr/bin/env python3
"""V315 no-write audit: V185 pre-entry structural frontier.

Purpose:
- Do not touch production/frontend/watchlist.
- Derive only entry-time/pre-entry fields from local daily K-line cache.
- Search whether any simple non-leaking pre-entry gate improves V185 enough to supersede production.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v185_combined_production_candidate' / 'v185_trades.json'
KDIR = ROOT / 'kline_cache'
OUTDIR = ROOT / 'smc_audit' / f"v315_v185_preentry_structural_frontier_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST = ROOT / 'smc_audit' / 'v315_v185_preentry_structural_frontier_latest.json'

PRODUCTION_GATE = {
    'n_min': 300,
    'min_year_n_min': 40,
    'wr_min': 87.0,
    'avg_min': 6.8,
    'year_wr_min': 84.0,
    'micro_max': 1.0,
}
RESEARCH_GATE = {
    'n_min': 260,
    'min_year_n_min': 35,
    'wr_min': 88.0,
    'avg_min': 6.8,
    'year_wr_min': 84.0,
    'micro_max': 1.0,
}

OUTCOME_KEYS = {
    'pnl_pct', 'won', 'exit_reason', 'exit_date', 'exit_idx', 'hold_bars',
    'mfe_pct', 'mae_pct', 'rr_realized', 'partial_taken', 'bars_since_entry',
}


def fnum(x, default=None):
    if x is None or x == '':
        return default
    try:
        if isinstance(x, bool):
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def date_of_bar(b):
    return str(b.get('t') or b.get('date') or b.get('day') or '')


def load_kline(symbol: str):
    code, exch = symbol.split('.')
    p = KDIR / f'{code}_{exch}_daily_750.json'
    if not p.exists():
        return []
    data = json.load(open(p))
    if isinstance(data, dict):
        for key in ('data', 'klines', 'bars'):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    return data if isinstance(data, list) else []


def pct(a, b):
    if b in (None, 0) or a is None:
        return None
    return (a / b - 1.0) * 100.0


def close(b): return fnum(b.get('c') if isinstance(b, dict) else None)
def high(b): return fnum(b.get('h') if isinstance(b, dict) else None)
def low(b): return fnum(b.get('l') if isinstance(b, dict) else None)
def open_(b): return fnum(b.get('o') if isinstance(b, dict) else None)
def vol(b): return fnum(b.get('v') if isinstance(b, dict) else None)


def derive_preentry(row):
    sym = row.get('symbol')
    entry_date = str(row.get('entry_date') or '')
    bars = load_kline(sym) if sym else []
    idx = None
    for i, b in enumerate(bars):
        if date_of_bar(b) == entry_date:
            idx = i
            break
    feats = {}
    if idx is None or idx < 21:
        feats['kline_found'] = 0
        return feats
    feats['kline_found'] = 1
    entry_bar = bars[idx]
    prev = bars[idx - 1]
    entry_price = fnum(row.get('entry_price'), open_(entry_bar))
    prev_close = close(prev)
    feats['entry_gap_pct'] = pct(entry_price, prev_close)
    feats['entry_open_to_prev_close_pct'] = pct(open_(entry_bar), prev_close)

    for w in (3, 5, 10, 20, 60):
        if idx - w >= 0:
            c0 = close(bars[idx - w])
            feats[f'pre_ret_{w}d_pct'] = pct(prev_close, c0)
            window = bars[idx - w:idx]
            hs = [high(b) for b in window if high(b) is not None]
            ls = [low(b) for b in window if low(b) is not None]
            vs = [vol(b) for b in window if vol(b) is not None]
            if hs and ls:
                hi, lo = max(hs), min(ls)
                feats[f'pre_range_{w}d_pct'] = pct(hi, lo)
                feats[f'pre_close_pos_{w}d_pct'] = (prev_close - lo) / (hi - lo) * 100.0 if hi != lo and prev_close is not None else None
                feats[f'target_room_prior{w}_high_pct'] = pct(hi, entry_price)
                feats[f'discount_from_prior{w}_high_pct'] = pct(entry_price, hi)
            if len(vs) >= 2 and vs[-1] is not None:
                base = mean(vs[:-1]) if len(vs) > 1 else None
                feats[f'pre_vol_ratio_{w}d'] = vs[-1] / base if base else None
    # scanner/source-side fields already known by entry decision; exclude realized/path fields.
    for k in [
        'risk_pct', 'sl_pct', 'volatility_pct', 'entry_chase_above_zone_pct',
        'reclaim_close_above_zone_pct', 'reclaim_close_pos', 'v85_zone_width_pct',
        'v132_reclaim_body_range_pct', 'v132_reclaim_bull_body_pct',
        'v132_reclaim_close_pos_pct', 'v132_reclaim_close_above_zone_high_pct',
        'touch_to_reclaim_bars', 'v132_bull_count_3',
    ]:
        feats[k] = fnum(row.get(k))
    zl, zh = fnum(row.get('zone_low')), fnum(row.get('zone_high'))
    if zl and zh:
        feats['zone_width_from_raw_pct'] = pct(zh, zl)
        feats['entry_above_zone_high_raw_pct'] = pct(entry_price, zh)
        feats['entry_above_zone_low_raw_pct'] = pct(entry_price, zl)
    return feats


def metrics(rows):
    n = len(rows)
    if not n:
        return {'n': 0}
    pnls = [fnum(r.get('pnl_pct'), 0.0) for r in rows]
    net_wins = [p >= 0.8 for p in pnls]
    gross_wins = [p > 0 for p in pnls]
    years = defaultdict(list)
    months = defaultdict(list)
    for r, p in zip(rows, pnls):
        d = str(r.get('entry_date') or '')
        years[d[:4]].append(p)
        months[d[:6]].append(p)
    year_wr = {y: round(sum(p >= 0.8 for p in ps) / len(ps) * 100, 4) for y, ps in sorted(years.items()) if y}
    gross_year_wr = {y: round(sum(p > 0 for p in ps) / len(ps) * 100, 4) for y, ps in sorted(years.items()) if y}
    year_counts = {y: len(ps) for y, ps in sorted(years.items()) if y}
    month_wr = {m: round(sum(p >= 0.8 for p in ps) / len(ps) * 100, 4) for m, ps in sorted(months.items()) if m}
    return {
        'n': n,
        'wr': round(sum(net_wins) / n * 100, 4),
        'gross_wr': round(sum(gross_wins) / n * 100, 4),
        'avg': round(mean(pnls), 4),
        'median': round(median(pnls), 4),
        'net_wr_ge_0_8': round(sum(net_wins) / n * 100, 4),
        'small_win_n': sum(0 < p < 0.8 for p in pnls),
        'micro_profit_pct': round(sum(0 < p < 0.8 for p in pnls) / n * 100, 4),
        'loss_pct': round(sum(p < 0 for p in pnls) / n * 100, 4),
        'min_year_n': min(year_counts.values()) if year_counts else 0,
        'year_counts': year_counts,
        'year_wr': year_wr,
        'gross_year_wr': gross_year_wr,
        'all_year_wr_min': round(min(year_wr.values()), 4) if year_wr else 0,
        'gross_all_year_wr_min': round(min(gross_year_wr.values()), 4) if gross_year_wr else 0,
        'month_wr_min': round(min(month_wr.values()), 4) if month_wr else 0,
        'same_day_exit_violations': sum(str(r.get('entry_date')) == str(r.get('exit_date')) for r in rows),
        'exit_counts': dict(Counter(str(r.get('exit_reason') or '') for r in rows)),
    }


def gate_status(m):
    if m.get('same_day_exit_violations', 0) != 0:
        return 'FAIL_T1'
    prod = (
        m.get('n', 0) >= PRODUCTION_GATE['n_min'] and
        m.get('min_year_n', 0) >= PRODUCTION_GATE['min_year_n_min'] and
        m.get('wr', 0) >= PRODUCTION_GATE['wr_min'] and
        m.get('avg', 0) >= PRODUCTION_GATE['avg_min'] and
        m.get('all_year_wr_min', 0) >= PRODUCTION_GATE['year_wr_min'] and
        m.get('micro_profit_pct', 999) <= PRODUCTION_GATE['micro_max']
    )
    if prod:
        return 'PRODUCTION_USABLE'
    research = (
        m.get('n', 0) >= RESEARCH_GATE['n_min'] and
        m.get('min_year_n', 0) >= RESEARCH_GATE['min_year_n_min'] and
        m.get('wr', 0) >= RESEARCH_GATE['wr_min'] and
        m.get('avg', 0) >= RESEARCH_GATE['avg_min'] and
        m.get('all_year_wr_min', 0) >= RESEARCH_GATE['year_wr_min'] and
        m.get('micro_profit_pct', 999) <= RESEARCH_GATE['micro_max']
    )
    return 'RESEARCH_USABLE' if research else 'UNUSABLE_CLOSED'


def cond_rows(rows, feats, conds):
    out = []
    for r in rows:
        fs = feats.get(r['_v315_id'], {})
        ok = True
        for name, op, th in conds:
            v = fs.get(name)
            if v is None:
                ok = False; break
            if op == '<=' and not (v <= th):
                ok = False; break
            if op == '>=' and not (v >= th):
                ok = False; break
        if ok:
            out.append(r)
    return out


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    rows = json.load(open(TRADES))
    for i, r in enumerate(rows):
        r['_v315_id'] = i
    feats = {r['_v315_id']: derive_preentry(r) for r in rows}
    for r in rows:
        r['_v315_feats'] = feats[r['_v315_id']]

    base = metrics(rows)

    safe_features = sorted({k for fs in feats.values() for k, v in fs.items() if isinstance(v, (int, float)) and not isinstance(v, bool)})
    candidates = []
    for name in safe_features:
        vals = sorted([fs.get(name) for fs in feats.values() if isinstance(fs.get(name), (int, float))])
        if len(vals) < 260:
            continue
        qs = sorted(set([0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]))
        for q in qs:
            th = vals[int((len(vals)-1) * q)]
            for op in ('<=', '>='):
                selected = cond_rows(rows, feats, [(name, op, th)])
                if len(selected) < 180:
                    continue
                m = metrics(selected)
                m['gate_status'] = gate_status(m)
                m['rule'] = f'{name}{op}{round(th, 6)}'
                m['feature'] = name
                candidates.append(m)

    # Pair only from strongest single rules to avoid a combinatorial/overfit explosion.
    singles_for_pair = [c for c in sorted(candidates, key=lambda x: (x['wr'], x['avg'], x['n']), reverse=True) if c['n'] >= 220][:80]
    pair_candidates = []
    parsed = []
    for c in singles_for_pair:
        rule = c['rule']
        if '<=' in rule:
            name, th = rule.split('<='); parsed.append((name, '<=', float(th)))
        elif '>=' in rule:
            name, th = rule.split('>='); parsed.append((name, '>=', float(th)))
    seen = set()
    for i in range(len(parsed)):
        for j in range(i+1, len(parsed)):
            if parsed[i][0] == parsed[j][0]:
                continue
            key = tuple(sorted([parsed[i], parsed[j]]))
            if key in seen:
                continue
            seen.add(key)
            selected = cond_rows(rows, feats, [parsed[i], parsed[j]])
            if len(selected) < 180:
                continue
            m = metrics(selected)
            m['gate_status'] = gate_status(m)
            m['rule'] = ' AND '.join([f'{a}{b}{round(c,6)}' for a,b,c in [parsed[i], parsed[j]]])
            pair_candidates.append(m)

    allc = candidates + pair_candidates
    production_pass = [c for c in allc if c['gate_status'] == 'PRODUCTION_USABLE']
    research_pass = [c for c in allc if c['gate_status'] == 'RESEARCH_USABLE']
    near = sorted(allc, key=lambda x: (
        x.get('gate_status') == 'PRODUCTION_USABLE',
        x.get('gate_status') == 'RESEARCH_USABLE',
        x.get('wr', 0), x.get('avg', 0), x.get('all_year_wr_min', 0), x.get('n', 0)
    ), reverse=True)[:30]

    # Loser/winner source-feature delta for actual root cause evidence.
    wins = [r for r in rows if fnum(r.get('pnl_pct'), 0) >= 0.8]
    losses = [r for r in rows if fnum(r.get('pnl_pct'), 0) < 0]
    deltas = []
    for name in safe_features:
        wv = [feats[r['_v315_id']].get(name) for r in wins if feats[r['_v315_id']].get(name) is not None]
        lv = [feats[r['_v315_id']].get(name) for r in losses if feats[r['_v315_id']].get(name) is not None]
        if len(wv) >= 30 and len(lv) >= 15:
            deltas.append({
                'feature': name,
                'winner_mean': round(mean(wv), 4),
                'loser_mean': round(mean(lv), 4),
                'delta_loser_minus_winner': round(mean(lv) - mean(wv), 4),
                'winner_median': round(median(wv), 4),
                'loser_median': round(median(lv), 4),
            })
    deltas = sorted(deltas, key=lambda x: abs(x['delta_loser_minus_winner']), reverse=True)[:40]

    report = {
        'version': 'V315_V185_PREENTRY_STRUCTURAL_FRONTIER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input': str(TRADES),
        'baseline': base,
        'gates': {'production': PRODUCTION_GATE, 'research': RESEARCH_GATE},
        'feature_contract': {
            'allowed': 'entry-time/pre-entry K-line geometry and scanner/source fields only',
            'forbidden_outcome_fields': sorted(OUTCOME_KEYS),
            'kline_cache': str(KDIR),
        },
        'coverage': {
            'rows': len(rows),
            'kline_found_rows': sum(1 for fs in feats.values() if fs.get('kline_found') == 1),
            'safe_feature_count': len(safe_features),
            'single_rules_tested': len(candidates),
            'pair_rules_tested': len(pair_candidates),
        },
        'production_pass_count': len(production_pass),
        'research_pass_count': len(research_pass),
        'production_pass': production_pass[:10],
        'research_pass': research_pass[:10],
        'near_frontier_top30': near,
        'winner_loser_preentry_deltas_top40': deltas,
        'decision': 'KEEP_V185_PRODUCTION__NO_V315_PREENTRY_STRUCTURAL_GATE_PASS' if not production_pass else 'V315_GATE_PASS_REQUIRES_INDEPENDENT_SCANNER_CURRENT_SMOKE_BEFORE_PROMOTION',
    }
    json.dump(report, open(OUTDIR / 'v315_report.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(report, open(LATEST, 'w'), ensure_ascii=False, indent=2)
    # lean rows with features for manual audit
    lean = []
    for r in rows:
        lean.append({
            'symbol': r.get('symbol'), 'entry_date': r.get('entry_date'), 'exit_date': r.get('exit_date'),
            'pnl_pct': fnum(r.get('pnl_pct')), 'exit_reason': r.get('exit_reason'),
            'v185_source': r.get('v185_source'), 'features': feats[r['_v315_id']],
        })
    json.dump(lean, open(OUTDIR / 'v315_rows_with_preentry_features.json', 'w'), ensure_ascii=False)
    print(json.dumps({
        'latest': str(LATEST),
        'baseline': base,
        'coverage': report['coverage'],
        'production_pass_count': len(production_pass),
        'research_pass_count': len(research_pass),
        'decision': report['decision'],
        'top_near': near[:5],
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
