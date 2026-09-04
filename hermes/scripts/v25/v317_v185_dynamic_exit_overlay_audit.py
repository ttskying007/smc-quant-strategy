#!/usr/bin/env python3
"""V317 no-write audit: pre-entry selected dynamic exit overlay for V185.

Uses only pre-entry/scanner features to decide which already-selected V185 entries
should use the V316 faster 1R exit; all other rows keep the materialized V185
contract. This tests whether V316's WR improvement can be captured without
sacrificing V185's average PnL.
"""
from __future__ import annotations

import importlib.util
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v185_combined_production_candidate' / 'v185_trades.json'
AUDIT = ROOT / 'smc_audit'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUTDIR = AUDIT / f'v317_v185_dynamic_exit_overlay_no_write_{TS}'
LATEST = AUDIT / 'v317_v185_dynamic_exit_overlay_latest.json'
V315_PATH = ROOT / 'scripts/v25/v315_v185_preentry_structural_frontier_audit.py'
V316_PATH = ROOT / 'scripts/v25/v316_v185_exit_mechanism_frontier_audit.py'

GATE = {'n_min': 300, 'min_year_n_min': 40, 'wr_min': 87.0, 'avg_min': 6.8, 'year_wr_min': 84.0, 'micro_max': 1.0}
FAST_EXIT = {'name': 'V317_OVERLAY_FAST_TP1R_H10', 'r_tp': 1.0, 'max_hold': 10}


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

v315 = load_mod('v315', V315_PATH)
v316 = load_mod('v316', V316_PATH)


def fnum(x, default=None):
    if x is None or x == '': return default
    try:
        if isinstance(x, bool): return default
        v = float(x)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default


def dkey(v):
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def materialized_row(r):
    return {
        'symbol': r.get('symbol'), 'entry_date': dkey(r.get('entry_date')), 'exit_date': dkey(r.get('exit_date')),
        'exit_reason': r.get('exit_reason'), 'pnl_pct': fnum(r.get('pnl_pct'), 0.0),
        'same_day_exit_violation': dkey(r.get('entry_date')) == dkey(r.get('exit_date')),
        'policy': 'KEEP_V185_MATERIALIZED', 'v185_source': r.get('v185_source'),
    }


def metrics(rows):
    n = len(rows)
    pnls = [fnum(r.get('pnl_pct'), 0.0) for r in rows]
    years = defaultdict(list)
    for r, p in zip(rows, pnls):
        years[str(r.get('entry_date') or '')[:4]].append(p)
    yc = {y: len(v) for y, v in sorted(years.items()) if y}
    yw = {y: round(sum(p >= 0.8 for p in v) / len(v) * 100, 4) for y, v in sorted(years.items()) if y}
    m = {
        'n': n,
        'wr': round(sum(p >= 0.8 for p in pnls) / n * 100, 4) if n else 0,
        'gross_wr': round(sum(p > 0 for p in pnls) / n * 100, 4) if n else 0,
        'avg': round(mean(pnls), 4) if n else 0,
        'median': round(median(pnls), 4) if n else 0,
        'loss_pct': round(sum(p < 0 for p in pnls) / n * 100, 4) if n else 0,
        'micro_profit_pct': round(sum(0 < p < 0.8 for p in pnls) / n * 100, 4) if n else 0,
        'min_year_n': min(yc.values()) if yc else 0,
        'year_counts': yc, 'year_wr': yw,
        'all_year_wr_min': round(min(yw.values()), 4) if yw else 0,
        'same_day_exit_violations': sum(1 for r in rows if r.get('same_day_exit_violation')),
        'exit_counts': dict(Counter(r.get('exit_reason') for r in rows)),
        'policy_counts': dict(Counter(r.get('policy') for r in rows)),
    }
    ok = (m['same_day_exit_violations'] == 0 and m['n'] >= GATE['n_min'] and m['min_year_n'] >= GATE['min_year_n_min'] and m['wr'] >= GATE['wr_min'] and m['avg'] >= GATE['avg_min'] and m['all_year_wr_min'] >= GATE['year_wr_min'] and m['micro_profit_pct'] <= GATE['micro_max'])
    m['gate_status'] = 'PRODUCTION_PASS' if ok else 'FAIL'
    return m


def cond_ok(fs, conds):
    for name, op, th in conds:
        v = fs.get(name)
        if v is None: return False
        if op == '<=' and not v <= th: return False
        if op == '>=' and not v >= th: return False
    return True


def run_policy(trades, feats, fast_by_id, conds):
    out = []
    for i, r in enumerate(trades):
        if cond_ok(feats[i], conds):
            rr = dict(fast_by_id[i])
            rr['policy'] = 'FAST_TP1R_SELECTED_BY_PREENTRY_RULE'
            out.append(rr)
        else:
            out.append(materialized_row(r))
    return out


def parse_rule(rule):
    if '<=' in rule:
        a, b = rule.split('<='); return (a, '<=', float(b))
    a, b = rule.split('>='); return (a, '>=', float(b))


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    trades = json.load(open(TRADES))
    feats = {i: v315.derive_preentry(r) for i, r in enumerate(trades)}
    base_rows = [materialized_row(r) for r in trades]
    base = metrics(base_rows)
    fast_rows = [v316.simulate(r, FAST_EXIT) for r in trades]
    if any(x is None for x in fast_rows):
        raise RuntimeError('fast exit replay incomplete')
    fast_by_id = {i: fast_rows[i] for i in range(len(trades))}

    safe_features = sorted({k for fs in feats.values() for k, v in fs.items() if isinstance(v, (int, float)) and not isinstance(v, bool)})
    single = []
    for name in safe_features:
        vals = sorted(fs.get(name) for fs in feats.values() if isinstance(fs.get(name), (int, float)))
        if len(vals) < 260: continue
        for q in (0.1,0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9):
            th = vals[int((len(vals)-1)*q)]
            for op in ('<=','>='):
                selected = [i for i in range(len(trades)) if cond_ok(feats[i], [(name,op,th)])]
                if not (20 <= len(selected) <= 220): continue
                rows = run_policy(trades, feats, fast_by_id, [(name,op,th)])
                m = metrics(rows); m['rule'] = f'{name}{op}{round(th,6)}'; m['selected_n'] = len(selected)
                single.append(m)
    best_singles = sorted(single, key=lambda x: (x['gate_status']=='PRODUCTION_PASS', x['wr'], x['avg'], x['all_year_wr_min']), reverse=True)[:80]
    parsed = [parse_rule(x['rule']) for x in best_singles]
    pairs = []
    seen = set()
    for i in range(len(parsed)):
        for j in range(i+1, len(parsed)):
            if parsed[i][0] == parsed[j][0]: continue
            key = tuple(sorted([parsed[i], parsed[j]]))
            if key in seen: continue
            seen.add(key)
            conds = [parsed[i], parsed[j]]
            selected = [k for k in range(len(trades)) if cond_ok(feats[k], conds)]
            if not (20 <= len(selected) <= 220): continue
            rows = run_policy(trades, feats, fast_by_id, conds)
            m = metrics(rows); m['rule'] = ' AND '.join(f'{a}{b}{round(c,6)}' for a,b,c in conds); m['selected_n'] = len(selected)
            pairs.append(m)
    allc = single + pairs
    ranked = sorted(allc, key=lambda x: (x['gate_status']=='PRODUCTION_PASS', x['wr'], x['avg'], x['all_year_wr_min'], x['selected_n']), reverse=True)
    pass_rows = [x for x in ranked if x['gate_status'] == 'PRODUCTION_PASS']
    best = ranked[0] if ranked else {}
    best_conds = [parse_rule(p.strip()) for p in best.get('rule','').split(' AND ')] if best else []
    best_rows = run_policy(trades, feats, fast_by_id, best_conds) if best_conds else base_rows
    report = {
        'version': 'V317_V185_DYNAMIC_EXIT_OVERLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input': str(TRADES), 'gate': GATE, 'fast_exit': FAST_EXIT,
        'baseline_v185': base, 'fast_exit_all_rows': metrics(fast_rows),
        'coverage': {'trades': len(trades), 'safe_features': len(safe_features), 'single_rules': len(single), 'pair_rules': len(pairs)},
        'production_pass_count': len(pass_rows), 'production_pass_top10': pass_rows[:10], 'frontier_top30': ranked[:30],
        'best_policy': best,
        'best_rows_path': str(OUTDIR / 'v317_best_rows.json'),
        'decision': 'DYNAMIC_EXIT_OVERLAY_CANDIDATE_FOUND__REQUIRES_OOS_SCANNER_SMOKE' if pass_rows else 'NO_DYNAMIC_EXIT_OVERLAY_PROMOTION__KEEP_V185',
        'artifacts': {'report': str(OUTDIR / 'v317_report.json'), 'latest': str(LATEST), 'all_rules': str(OUTDIR / 'v317_all_rules.json')},
    }
    json.dump(report, open(OUTDIR/'v317_report.json','w'), ensure_ascii=False, indent=2)
    json.dump(ranked, open(OUTDIR/'v317_all_rules.json','w'), ensure_ascii=False, indent=2)
    json.dump(best_rows, open(OUTDIR/'v317_best_rows.json','w'), ensure_ascii=False, indent=2)
    json.dump(report, open(LATEST,'w'), ensure_ascii=False, indent=2)
    print(json.dumps({'latest': str(LATEST), 'baseline': base, 'fast_all': report['fast_exit_all_rows'], 'coverage': report['coverage'], 'production_pass_count': len(pass_rows), 'decision': report['decision'], 'best_policy': best}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
