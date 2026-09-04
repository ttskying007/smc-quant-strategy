#!/usr/bin/env python3
"""V296 no-write: second60 persistence + anti-chase + lifecycle gate.

V294 found executable second60 market/industry persistence improves V292/V293,
but V295 weak-month autopsy showed 202602-202604 failures come from shallow
sweep + loose accumulation + weak/mid impulse + chase/risk after persistence.

This script reruns the executable k2/k3 persistence simulation on the full V293
659-row source, then tests entry-time gates only.  It does not write production,
frontend, or watchlist artifacts.
"""
from __future__ import annotations

import csv
import importlib.util
import itertools
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V293 = json.loads((AUDIT / 'v293_entry60_participation_lifecycle_latest.json').read_text())
SOURCE = Path(V293['artifacts']['enriched_rows'])
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
V294_SCRIPT = BASE / 'scripts/v25/v294_entry60_persistence_audit.py'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v296_second60_antichase_lifecycle_no_write_{TS}'
LATEST = AUDIT / 'v296_second60_antichase_lifecycle_latest.json'


def load_v294():
    spec = importlib.util.spec_from_file_location('v294_core_for_v296', V294_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'micro': 0,
            'tp': 0, 'sl': 0, 'gap_sl': 0, 'time': 0,
            'years': defaultdict(lambda: [0, 0]),
            'months': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0)
    reason = str(r.get('reason', ''))
    a['n'] += 1
    a['wins'] += pnl > 0
    a['sum'] += pnl
    a['loss'] += pnl <= 0
    a['micro'] += 0 < pnl < 1
    a['tp'] += reason == 'TP'
    a['sl'] += reason == 'SL'
    a['gap_sl'] += reason == 'GAP_SL'
    a['time'] += reason.startswith('TIME')
    y = str(r.get('entry_date', ''))[:4]
    m = str(r.get('entry_date', ''))[:6]
    a['years'][y][0] += 1; a['years'][y][1] += pnl > 0
    a['months'][m][0] += 1; a['months'][m][1] += pnl > 0
    a['symbols'].add(r.get('symbol', ''))


def metrics(rows: list[dict[str, Any]], source_n: int = 0) -> dict[str, Any]:
    a = blank()
    for r in rows:
        add(a, r)
    n = a['n']
    if not n:
        return {'n': 0, 'fill_rate': 0.0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    mc = {m: int(v[0]) for m, v in sorted(a['months'].items()) if v[0]}
    mwr = {m: round(v[1] / v[0] * 100, 2) for m, v in sorted(a['months'].items()) if v[0]}
    return {'n': n, 'fill_rate': round(n / source_n * 100, 2) if source_n else 100.0,
            'wr': round(a['wins'] / n * 100, 4), 'avg': round(a['sum'] / n, 4),
            'loss': int(a['loss']), 'micro': round(a['micro'] / n * 100, 2),
            'tp_pct': round(a['tp'] / n * 100, 2), 'sl_pct': round(a['sl'] / n * 100, 2),
            'gap_sl_pct': round(a['gap_sl'] / n * 100, 2), 'time_pct': round(a['time'] / n * 100, 2),
            'symbols': len(a['symbols']), 'year_counts': yc, 'year_wr': ywr,
            'min_year_n': min(yc.values()) if yc else 0,
            'min_year_wr': round(min(ywr.values()) if ywr else 0, 2),
            'month_counts': mc, 'month_wr': mwr,
            'min_month_n': min(mc.values()) if mc else 0,
            'min_month_wr': round(min(mwr.values()) if mwr else 0, 2)}


def bad_lifecycle_shallow_weak(r: dict[str, Any]) -> bool:
    return r.get('sweep_bucket') == 'SWP_SHALLOW<1' and r.get('impulse_bucket') in {'IMP_WEAK<0.5', 'IMP_MID0.5_1.5'}


def bad_lifecycle_wide_shallow(r: dict[str, Any]) -> bool:
    return r.get('sweep_bucket') == 'SWP_SHALLOW<1' and r.get('acc_bucket') in {'ACC_WIDE>=7', 'ACC_MID4_7'} and r.get('impulse_bucket') != 'IMP_STRONG>=1.5'


def make_gates() -> dict[str, Callable[[dict[str, Any]], bool]]:
    return {
        'open_to_confirm<=1.5': lambda r: sf(r.get('open_to_confirm_pct')) <= 1.5,
        'open_to_confirm<=2.0': lambda r: sf(r.get('open_to_confirm_pct')) <= 2.0,
        'persist_stock_ret<=1.5': lambda r: sf(r.get('persist_stock_ret')) <= 1.5,
        'persist_stock_ret<=2.0': lambda r: sf(r.get('persist_stock_ret')) <= 2.0,
        'stock60_pos>=50': lambda r: sf(r.get('stock60_pos')) >= 50,
        'stock60_pos>=60': lambda r: sf(r.get('stock60_pos')) >= 60,
        'post_hold_min_pct<=4': lambda r: sf(r.get('post_hold_min_pct')) <= 4,
        'risk_after_persist<=6': lambda r: sf(r.get('risk_after_persist')) <= 6,
        'risk_after_persist<=7': lambda r: sf(r.get('risk_after_persist')) <= 7,
        'risk_after_persist<=8': lambda r: sf(r.get('risk_after_persist')) <= 8,
        'exclude_shallow_weak_mid_impulse': lambda r: not bad_lifecycle_shallow_weak(r),
        'exclude_midwide_shallow_nonstrong': lambda r: not bad_lifecycle_wide_shallow(r),
    }


def simulate_persistence(source: list[dict[str, Any]], core, sym_ind: dict[str, str], stock_ctx, mctx, ictx) -> list[dict[str, Any]]:
    cache_day: dict[str, list[dict[str, Any]]] = {}
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, float]] = set()
    configs = []
    for k in (2, 3):
        for mup in (65, 70):
            for iup in (50, 55, 65):
                configs.append({'k': k, 'mup': mup, 'iup': iup})
    for cfg in configs:
        for r in source:
            sym = r['symbol']; d = core.dn(r['entry_date']); ind = sym_ind.get(sym, '')
            zl = sf(r.get('zone_low')); zh = sf(r.get('zone_high'))
            s1 = stock_ctx.get((sym, d, 1), {})
            sk = stock_ctx.get((sym, d, cfg['k']), {})
            m1 = mctx.get((d, 1), {})
            mk = mctx.get((d, cfg['k']), {})
            i1 = ictx.get((d, ind, 1), {})
            ik = ictx.get((d, ind, cfg['k']), {})
            if not sk or not mk or not ik or zl <= 0 or zh <= 0:
                continue
            m_up = sf(mk.get('mkt_up_k')); i_up = sf(ik.get('ind_up_k'))
            if m_up < cfg['mup'] or i_up < cfg['iup']:
                continue
            if sf(sk.get('low')) <= zl or sf(sk.get('close')) <= zh:
                continue
            if cfg['k'] >= 2 and sf(sk.get('close')) < sf(s1.get('close')) * 0.995:
                continue
            entry = sf(sk.get('close'))
            key = (sym, d, cfg['k'], round(entry, 4))
            if key in seen:
                continue
            seen.add(key)
            sl = zl * 0.992
            res = core.replay(core.loadday(sym, cache_day), d, entry, sl)
            if not res:
                continue
            nr = dict(r)
            nr.update(res)
            nr.update({'entry': entry,
                       'entry_mode': f"k{cfg['k']}_persist_m{cfg['mup']}_i{cfg['iup']}",
                       'confirm_k': cfg['k'], 'persist_mkt_up': m_up, 'persist_ind_up': i_up,
                       'persist_mkt_decay': m_up - sf(m1.get('mkt_up_k')),
                       'persist_ind_decay': i_up - sf(i1.get('ind_up_k')),
                       'persist_stock_ret': sf(sk.get('ret')),
                       'persist_mkt_ret': sf(mk.get('mkt_ret_k')),
                       'persist_ind_ret': sf(ik.get('ind_ret_k')),
                       'persist_stock_hold_zone': True,
                       'risk_after_persist': (entry / sl - 1) * 100 if sl > 0 else math.nan,
                       't1_violation': res['exit_date'] <= d})
            candidates.append(nr)
    return candidates


def score_rules(rows: list[dict[str, Any]], source_n: int) -> list[dict[str, Any]]:
    gates = make_gates()
    names = list(gates)
    scored = []
    for width in (0, 1, 2, 3):
        combos = [()] if width == 0 else itertools.combinations(names, width)
        for combo in combos:
            if 'risk_after_persist<=6' in combo and 'risk_after_persist<=7' in combo:
                continue
            if 'open_to_confirm<=1.5' in combo and 'open_to_confirm<=2.0' in combo:
                continue
            kept = [r for r in rows if all(gates[name](r) for name in combo)]
            if len(kept) < 80:
                continue
            m = metrics(kept, source_n)
            if m['min_year_n'] < 20 or m['min_month_n'] < 5:
                continue
            m['rule'] = 'BASE_PERSISTENCE' if not combo else ' & '.join(combo)
            scored.append({'metrics': m, 'rows': kept})
    scored.sort(key=lambda x: (x['metrics']['min_month_wr'], x['metrics']['min_year_wr'], x['metrics']['wr'], x['metrics']['avg'], x['metrics']['n']), reverse=True)
    return scored


def group_decomp(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dims = ['entry_mode', 'acc_bucket', 'sweep_bucket', 'impulse_bucket', 'lifecycle_combo', 'industry', 'reason']
    out = []
    for dim in dims:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            buckets[str(r.get(dim, ''))].append(r)
        for val, rs in buckets.items():
            if len(rs) >= 5:
                out.append({'dimension': dim, 'value': val, **metrics(rs, len(rows))})
    out.sort(key=lambda x: (-x['n'], x['wr']))
    return out[:80]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    core = load_v294()
    with SOURCE.open() as f:
        source = list(csv.DictReader(f))
    sym_ind = {r['symbol']: r.get('industry', '') for r in json.loads(INDMAP.read_text()) if r.get('symbol')}
    stock_ctx, mctx, ictx, files60 = core.build_k_context(sym_ind, ks=(1, 2, 3))
    all_persist = simulate_persistence(source, core, sym_ind, stock_ctx, mctx, ictx)
    scored = score_rules(all_persist, len(source))
    best = scored[0] if scored else {'metrics': {'n': 0}, 'rows': []}

    best_rows = best['rows']
    rows_path = OUT / 'v296_best_rows.csv'
    if best_rows:
        fields = list(best_rows[0].keys())
        for r in best_rows:
            for k in r:
                if k not in fields:
                    fields.append(k)
        with rows_path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader(); w.writerows(best_rows)

    summary = {
        'version': 'V296_SECOND60_ANTICHASE_LIFECYCLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': str(SOURCE), 'source_n': len(source), 'sixty_min_files': files60,
        'hypothesis': 'Second60 persistence can be stabilized by entry-time anti-chase and lifecycle gates found in V295 weak-month autopsy.',
        'raw_v293_source': metrics(source, len(source)),
        'all_persistence_candidates': metrics(all_persist, len(source)),
        'top_rules': [x['metrics'] for x in scored[:30]],
        'best_rule': best['metrics'],
        'best_decomp': group_decomp(best_rows),
        't1_violations': sum(1 for r in best_rows if str(r.get('t1_violation')).lower() == 'true'),
        'artifacts': {'out_dir': str(OUT), 'best_rows': str(rows_path), 'summary': str(OUT / 'v296_summary.json')},
    }
    (OUT / 'v296_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'best_rule': summary['best_rule'], 'top10': summary['top_rules'][:10], 't1_violations': summary['t1_violations']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
