#!/usr/bin/env python3
"""V328 no-write: current supply gap + relaxed gate audit.

V327 proved the only V246-lineage actionable row was already closed by T+1 replay.
This step answers the next concrete question: is the current gap caused by too
strict V164/V246 gates, and can any surgical relaxation pass historical quality
while producing open current non-history rows?

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import importlib.util
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
SRC = AUD / 'v164_corrected_scanner_dry_run_20260622/v164_dryrun_rows.json'
OUT = AUD / f"v328_current_supply_gap_relaxed_gate_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST = AUD / 'v328_current_supply_gap_relaxed_gate_latest.json'
MAX_HOLD = 10
GATE = {'n': 570, 'min_year_n': 70, 'wr': 93.0, 'avg': 7.6, 'min_year_wr': 91.0, 'micro': 1.0, 't1': 0}


def load_mod(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

v326 = load_mod('/root/.hermes/scripts/v25/v326_v246_lineage_current_supply_audit.py', 'v326_for_v328')


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '').replace('-', '')[:10] if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def sf(x: Any, default: float | None = None) -> float | None:
    try:
        if x is None or x == '': return default
        v = float(x)
        if math.isnan(v) or math.isinf(v): return default
        return v
    except Exception:
        return default


def boolish(x: Any) -> bool:
    return str(x).strip().lower() in {'true', '1', 'yes'}


def load_json(p: Path, default: Any) -> Any:
    try: return json.loads(p.read_text())
    except Exception: return default


def bars(sym: str) -> list[dict[str, Any]]:
    p = KDIR / f"{sym.replace('.', '_')}_daily_750.json"
    arr = []
    for b in load_json(p, []):
        d = dn(b.get('t') or b.get('date'))
        o,h,l,c = sf(b.get('o')), sf(b.get('h')), sf(b.get('l')), sf(b.get('c'))
        if d and None not in (o,h,l,c):
            arr.append({'date': d, 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(arr, key=lambda r: r['date'])


def actual_bars_since(sym: str, ed: str) -> int | None:
    ds = [b['date'] for b in bars(sym)]
    if ed not in ds: return None
    return sum(1 for d in ds if d > ed)


def replay(r: dict[str, Any]) -> dict[str, Any]:
    sym, ed = str(r.get('symbol') or ''), dn(r.get('entry_date'))
    ep, zl = sf(r.get('entry_price')), sf(r.get('zone_low'))
    if not sym or not ed or ep is None or zl is None or ep <= 0 or zl <= 0:
        return {'replay_status': 'FIELD_MISSING'}
    sl = zl * 0.99
    tp = ep + (ep - sl) * 1.5
    path = [b for b in bars(sym) if b['date'] > ed]
    out = {'replay_status': 'OPEN_UNEXPIRED', 'sl': sl, 'tp': tp, 'path_bars': len(path), 'latest_date': path[-1]['date'] if path else '', 'latest_close': path[-1]['c'] if path else None}
    for i, b in enumerate(path, 1):
        reason = ''; px = None
        if b['l'] <= sl:
            reason, px = 'SL', sl
        elif b['h'] >= tp:
            reason, px = 'TP', tp
        elif i >= MAX_HOLD:
            reason, px = 'TIME', b['c']
        if reason:
            out.update({'replay_status': 'CLOSED', 'exit_reason': reason, 'exit_date': b['date'], 'exit_price': px, 'hold_bars': i, 'pnl_pct': (px / ep - 1) * 100, 'same_day_exit_violation': b['date'] == ed})
            break
    return out


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [r for r in rows if r.get('replay_status') == 'CLOSED']
    if not closed:
        return {'n': 0, 'wr': 0, 'avg': 0, 'min_year_n': 0, 'year_counts': {}, 'year_wr': {}, 'min_year_wr': 0, 'micro': 0, 't1': 0, 'exit_counts': {}}
    p = pd.Series([sf(r.get('pnl_pct'), 0) for r in closed])
    yrs = pd.Series([dn(r.get('entry_date'))[:4] for r in closed])
    yc = yrs.value_counts().sort_index().to_dict()
    ywr = {str(y): round(float((p[yrs == y] > 0).mean() * 100), 2) for y in sorted(yc)}
    return {
        'n': len(closed), 'wr': round(float((p > 0).mean() * 100), 4), 'avg': round(float(p.mean()), 4),
        'min_year_n': int(min(yc.values()) if yc else 0), 'year_counts': {str(k): int(v) for k, v in yc.items()},
        'year_wr': ywr, 'min_year_wr': round(float(min(ywr.values()) if ywr else 0), 2),
        'micro': round(float(((p > 0) & (p < 1)).mean() * 100), 4),
        't1': int(sum(bool(r.get('same_day_exit_violation')) for r in closed)),
        'exit_counts': {str(k): int(v) for k, v in pd.Series([r.get('exit_reason') for r in closed]).value_counts().to_dict().items()},
    }


def pass_gate(m: dict[str, Any]) -> bool:
    return m['n'] >= GATE['n'] and m['min_year_n'] >= GATE['min_year_n'] and m['wr'] >= GATE['wr'] and m['avg'] >= GATE['avg'] and m['min_year_wr'] >= GATE['min_year_wr'] and m['micro'] <= GATE['micro'] and m['t1'] == 0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_json(SRC, [])
    all_strong, strong_dates = v326.build_all_market_strong1()
    br, br_dates = v326.load_breadth_above_ma20()
    sym_ind, ind_feats, ind_dates = v326.build_industry_features()
    hist = v326.load_history()
    enriched = []
    for r0 in rows:
        r = dict(r0)
        ed = dn(r.get('entry_date'))
        sym = str(r.get('symbol') or '')
        r['entry_date'] = ed
        r['v328_actual_bars_since_entry'] = actual_bars_since(sym, ed)
        r['v328_any_history_overlap'] = any((sym, ed) in s for s in hist.values())
        ps, pb = v326.previous(strong_dates, ed), v326.previous(br_dates, ed)
        ind = sym_ind.get(sym, 'UNKNOWN')
        pi = v326.previous(ind_dates, ed)
        r['v236_all_strong1_pct'] = all_strong.get(ps)
        r['v236_br_above_ma20'] = br.get(pb)
        r['v244_industry'] = ind
        r.update(ind_feats.get((pi, ind), {}))
        enriched.append(r)

    def industry(r): return v326.industry_addback_pass(r)
    def base_quality(r): return sf(r.get('entry_chase_above_zone_pct'), 999) <= 3.5 and sf(r.get('risk_pct'), 999) <= 8.0 and str(r.get('market_state')) in {'BEAR_RISK', 'RECOVERY', 'MIXED'}

    routes: dict[str, Callable[[dict[str, Any]], bool]] = {
        'strict_v164_industry': lambda r: boolish(r.get('v164_rule_pass')) and industry(r),
        'strict_v164_no_industry': lambda r: boolish(r.get('v164_rule_pass')),
        'relax_tt1_body_industry': lambda r: boolish(r.get('v132_true_takeover_1')) and sf(r.get('v132_reclaim_bull_body_pct'), 999) <= 87.1077 and industry(r),
        'relax_v160_rule_industry': lambda r: boolish(r.get('v160_rule_pass')) and industry(r),
        'surgical_current_quality': lambda r: boolish(r.get('v164_rule_pass')) and industry(r) and base_quality(r),
        'latest_window_any_takeover_quality': lambda r: (boolish(r.get('v132_true_takeover_1')) or boolish(r.get('v132_true_takeover_2')) or boolish(r.get('v132_true_takeover_3_strict'))) and industry(r) and base_quality(r),
    }

    route_reports = {}
    route_samples = []
    for name, fn in routes.items():
        picked = []
        seen = set()
        for r in enriched:
            if not fn(r): continue
            k = (str(r.get('symbol')), dn(r.get('entry_date')), str(r.get('poi_source')))
            if k in seen: continue
            seen.add(k)
            rr = dict(r)
            rr.update(replay(rr))
            picked.append(rr)
        hist_closed = [r for r in picked if (r.get('v328_actual_bars_since_entry') is not None and r.get('v328_actual_bars_since_entry') >= MAX_HOLD)]
        current_nonhist = [r for r in picked if (r.get('v328_actual_bars_since_entry') is not None and r.get('v328_actual_bars_since_entry') <= MAX_HOLD and not r.get('v328_any_history_overlap'))]
        open_current = [r for r in current_nonhist if r.get('replay_status') == 'OPEN_UNEXPIRED']
        closed_current = [r for r in current_nonhist if r.get('replay_status') == 'CLOSED']
        m = metrics(hist_closed)
        route_reports[name] = {
            'total_rows': len(picked), 'historical_closed_rows': len(hist_closed), 'current_nonhistory_actionable10_rows': len(current_nonhist),
            'open_current_rows': len(open_current), 'closed_current_rows': len(closed_current),
            'metrics': m, 'production_gate_pass': pass_gate(m),
            'current_open_slim': [{k: r.get(k) for k in ['symbol','entry_date','poi_source','event_type','market_state','entry_price','zone_low','risk_pct','entry_chase_above_zone_pct','v132_reclaim_class','latest_date','latest_close']} for r in open_current[:20]],
            'current_closed_slim': [{k: r.get(k) for k in ['symbol','entry_date','poi_source','exit_reason','exit_date','pnl_pct','same_day_exit_violation']} for r in closed_current[:20]],
        }
        for r in open_current[:50]:
            route_samples.append({**{k: r.get(k) for k in ['symbol','entry_date','poi_source','event_type','market_state','entry_price','zone_low','risk_pct','entry_chase_above_zone_pct','v132_reclaim_class','latest_date','latest_close']}, 'route': name})

    latest_window = [r for r in enriched if r.get('v328_actual_bars_since_entry') is not None and r.get('v328_actual_bars_since_entry') <= 20]
    fail_decomp = {
        'latest20_rows': len(latest_window),
        'latest20_by_entry_date': {str(k): int(v) for k, v in pd.Series([dn(r.get('entry_date')) for r in latest_window]).value_counts().sort_index().to_dict().items()},
        'latest20_by_v164_reason': {str(k): int(v) for k, v in pd.Series([r.get('v164_dry_reason') for r in latest_window]).value_counts().head(20).to_dict().items()},
        'latest20_by_reclaim_class': {str(k): int(v) for k, v in pd.Series([r.get('v132_reclaim_class') for r in latest_window]).value_counts().head(20).to_dict().items()},
        'latest20_v164_pass': int(sum(boolish(r.get('v164_rule_pass')) for r in latest_window)),
        'latest20_v160_pass': int(sum(boolish(r.get('v160_rule_pass')) for r in latest_window)),
        'latest20_tt1': int(sum(boolish(r.get('v132_true_takeover_1')) for r in latest_window)),
        'latest20_tt2': int(sum(boolish(r.get('v132_true_takeover_2')) for r in latest_window)),
        'latest20_tt3': int(sum(boolish(r.get('v132_true_takeover_3_strict')) for r in latest_window)),
    }

    pd.DataFrame(route_samples).to_csv(OUT / 'v328_current_open_route_samples.csv', index=False)
    report = {
        'version': 'V328_CURRENT_SUPPLY_GAP_RELAXED_GATE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': str(SRC), 'production_gate': GATE, 'fail_decomposition': fail_decomp, 'route_reports': route_reports,
        'decision': 'V328_NO_RELAXED_ROUTE_PASSES_HISTORICAL_GATE_AND_HAS_OPEN_CURRENT_SUPPLY__KEEP_V185' if not any(x['production_gate_pass'] and x['open_current_rows'] > 0 for x in route_reports.values()) else 'V328_RELAXED_ROUTE_FOUND_FOR_SHADOW_ENDPOINT_SMOKE__NO_WRITE',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST), 'current_open_samples': str(OUT / 'v328_current_open_route_samples.csv')},
    }
    (OUT / 'v328_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'latest': str(LATEST), 'decision': report['decision'], 'fail_decomposition': fail_decomp, 'route_reports': route_reports}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
