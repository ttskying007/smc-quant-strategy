#!/usr/bin/env python3
"""V246 daily current shadow audit (no production/frontend/watchlist writes).

Directly rematerializes the V246 historical candidate on the latest dry scanner rows:
- compute previous-market broad breadth and industry participation from local caches;
- apply V244 parent semantics (base-like OR child-like current rows);
- apply V246 weak-industry addback rule;
- emit only non-expired, non-overlap actionable rows for endpoint smoke.
"""
from __future__ import annotations

import bisect
import glob
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
KDIR = BASE / 'kline_cache'
AUDIT = BASE / 'smc_audit'
ACTIVE = BASE / 'smc_opt_v185_combined_production_candidate/v185_active_picks.json'
V185_TRADES = BASE / 'smc_opt_v185_combined_production_candidate/v185_trades.json'
BREADTH_CACHE = AUDIT / 'v185_market_breadth_cache.csv'
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
RULE_VERSION = 'V246_DAILY_CURRENT_SHADOW_AUDIT'
MAX_ACTIONABLE_BARS = 10
WEAK_INDUSTRIES = {'C27医药制造业', 'C32有色金属冶炼和压延加工业'}


def sf(x: Any, default: float | None = None) -> float | None:
    try:
        if x is None or x == '':
            return default
        if isinstance(x, float) and math.isnan(x):
            return default
        v = float(x)
        return v if not math.isnan(v) else default
    except Exception:
        return default


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '').replace('-', '')[:10] if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def row_key(r: dict[str, Any]) -> tuple[str, str]:
    return str(r.get('symbol') or ''), dn(r.get('entry_date') or r.get('pick_date'))


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def latest_path(pattern: str) -> Path | None:
    paths = [Path(p) for p in glob.glob(pattern)]
    paths = [p for p in paths if p.exists()]
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def latest_v164_dryrun() -> Path:
    p = latest_path(str(AUDIT / 'v164_corrected_scanner_dry_run_*' / 'v164_dryrun_rows.json'))
    if p is None:
        raise FileNotFoundError('missing latest v164_dryrun_rows.json')
    return p


def sym_from_file(path: str) -> str | None:
    parts = Path(path).name.split('_')
    if len(parts) >= 2 and parts[0].isdigit():
        return parts[0] + '.' + parts[1]
    return None


def previous_market_date(dates: list[str], entry_date: str) -> str:
    i = bisect.bisect_left(dates, entry_date) - 1
    return dates[i] if i >= 0 else ''


def build_all_market_strong1() -> tuple[dict[str, float], list[str]]:
    rows_by_date: dict[str, list[float]] = defaultdict(list)
    for fp in glob.glob(str(KDIR / '*_daily_750.json')):
        if not sym_from_file(fp):
            continue
        try:
            data = json.loads(Path(fp).read_text())
        except Exception:
            continue
        bars: list[tuple[str, float]] = []
        for b in data:
            d = dn(b.get('t') or b.get('date'))
            c = sf(b.get('c'))
            if d and c:
                bars.append((d, float(c)))
        bars.sort()
        for i, (d, c) in enumerate(bars):
            if i < 1:
                continue
            prev_c = bars[i - 1][1]
            if prev_c:
                rows_by_date[d].append((c / prev_c - 1.0) * 100.0)
    all_strong = {d: sum(x > 3.0 for x in vals) / len(vals) * 100.0 for d, vals in rows_by_date.items() if vals}
    return all_strong, sorted(all_strong)


def load_breadth_above_ma20() -> tuple[dict[str, float], list[str]]:
    if not BREADTH_CACHE.exists():
        return {}, []
    df = pd.read_csv(BREADTH_CACHE)
    out = {dn(r['breadth_date']): sf(r['br_above_ma20']) for r in df.to_dict('records') if dn(r.get('breadth_date'))}
    return {k: v for k, v in out.items() if v is not None}, sorted(out)


def build_industry_features() -> tuple[dict[str, str], dict[tuple[str, str], dict[str, float]], list[str]]:
    items = load_json(INDMAP, [])
    sym_ind = {r.get('symbol'): (r.get('industry') or 'UNKNOWN') for r in items if r.get('symbol')}
    industry_daily: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for fp in glob.glob(str(KDIR / '*_daily_750.json')):
        sym = sym_from_file(fp)
        if not sym:
            continue
        ind = sym_ind.get(sym, 'UNKNOWN')
        if not ind or ind == 'UNKNOWN':
            continue
        try:
            data = json.loads(Path(fp).read_text())
        except Exception:
            continue
        bars: list[tuple[str, float]] = []
        for b in data:
            d = dn(b.get('t') or b.get('date'))
            c = sf(b.get('c'))
            if d and c:
                bars.append((d, float(c)))
        bars.sort()
        for i in range(1, len(bars)):
            d, c = bars[i]
            pc = bars[i - 1][1]
            if pc:
                industry_daily[d][ind].append((c / pc - 1.0) * 100.0)
    feature_by_date_ind: dict[tuple[str, str], dict[str, float]] = {}
    for d, mp in industry_daily.items():
        for ind, vals in mp.items():
            if not vals:
                continue
            s = pd.Series(vals)
            feature_by_date_ind[(d, ind)] = {
                'v244_ind_n': float(len(vals)),
                'v244_ind_up1_pct': float((s > 1).mean() * 100),
                'v244_ind_strong1_pct': float((s > 3).mean() * 100),
                'v244_ind_mean_ret1': float(s.mean()),
            }
    return sym_ind, feature_by_date_ind, sorted({d for d, _ in feature_by_date_ind})


def latest_history_csv(pattern: str) -> Path | None:
    return latest_path(str(AUDIT / pattern))


def load_history_keys() -> dict[str, set[tuple[str, str]]]:
    keys: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for name, path in [('v185_trades', V185_TRADES), ('v185_active', ACTIVE)]:
        for r in load_json(path, []):
            keys[name].add(row_key(r))
    for name, pattern in [
        ('v231_history', 'v231_v230_candidate_independent_audit_no_write_* /v231_combined_rows.csv'.replace(' ', '')),
        ('v236_history', 'v236_v235_independent_audit_current_smoke_no_write_* /v236_independent_combined_rows.csv'.replace(' ', '')),
        ('v246_history', 'v248_v246_independent_audit_no_write_* /v248_recomputed_selected_rows.csv'.replace(' ', '')),
    ]:
        p = latest_history_csv(pattern)
        if p:
            for r in pd.read_csv(p, low_memory=False).to_dict('records'):
                keys[name].add(row_key(r))
    return keys


def selector_leak_fields(fields: list[str]) -> list[str]:
    bad_tokens = ['pnl', 'exit_', 'won', 'mae', 'mfe', 'hold_bars', 'hit', 'rr_realized', 'base_', 'future', 'post_exit']
    return [f for f in fields if any(tok in f.lower() for tok in bad_tokens)]


def parent_rule_pass(r: dict[str, Any]) -> bool:
    # Current dry scanner rows do not carry the historical V236-base materialization identity.
    # Applying the historical base breadth rule to every scanner row over-selects unrelated rows.
    # Therefore daily current monitoring only uses the current-scanner-compatible new-supply branch
    # from V239/V244; historical base rows stay historical until a dedicated base generator exists.
    return (
        str(r.get('market_state')) in ('ACCUMULATION', 'BEAR_RISK')
        and str(r.get('event_type')) == 'SSL_SWEEP_CHOCH_REVERSAL'
        and str(r.get('poi_source')) in ('DEMAND_OB', 'OB+FVG')
        and sf(r.get('v132_bull_count_3'), -1) >= 3
        and sf(r.get('v132_post_zone_pullback_depth_pct_3'), 999) <= 40
        and 10 <= sf(r.get('v236_all_strong1_pct'), 999) <= 55
        and 35 <= sf(r.get('v236_br_above_ma20'), -999) <= 70
        and sf(r.get('entry_chase_above_zone_pct'), 999) <= 2.5
        and sf(r.get('v244_ind_up1_pct'), 999) <= 80
    )


def v246_rule_pass(r: dict[str, Any]) -> bool:
    if not parent_rule_pass(r):
        return False
    weak = str(r.get('v244_industry')) in WEAK_INDUSTRIES
    addback = sf(r.get('v244_ind_strong1_pct'), -999) >= 31.1688 or sf(r.get('v236_br_above_ma20'), -999) >= 46.8561
    return (not weak) or addback


def main() -> None:
    dry_path = latest_v164_dryrun()
    dry = load_json(dry_path, [])
    all_strong, strong_dates = build_all_market_strong1()
    br_ma20, br_dates = load_breadth_above_ma20()
    sym_ind, ind_features, ind_dates = build_industry_features()
    history = load_history_keys()
    out = AUDIT / ('v246_daily_current_shadow_audit_no_write_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True, exist_ok=True)

    selector_fields = [
        'market_state', 'event_type', 'poi_source', 'v132_bull_count_3',
        'v132_post_zone_pullback_depth_pct_3', 'entry_chase_above_zone_pct',
        'v246_prev_market_date', 'v236_all_strong1_pct', 'v246_breadth_date',
        'v236_br_above_ma20', 'v244_industry', 'v244_industry_prev_date',
        'v244_ind_strong1_pct', 'v244_ind_up1_pct', 'v244_ind_vs_all_strong1',
        'bars_since_entry',
    ]
    leak = selector_leak_fields(selector_fields)

    parent_raw: list[dict[str, Any]] = []
    selected_raw: list[dict[str, Any]] = []
    for r in dry:
        if not r.get('v161_recent45'):
            continue
        ed = dn(r.get('entry_date'))
        if not ed:
            continue
        sym = str(r.get('symbol') or '')
        prev_strong_d = previous_market_date(strong_dates, ed)
        prev_breadth_d = previous_market_date(br_dates, ed)
        ind = sym_ind.get(sym, 'UNKNOWN')
        prev_ind_d = previous_market_date(ind_dates, ed)
        feats = ind_features.get((prev_ind_d, ind), {})
        rr = dict(r)
        rr['entry_date'] = ed
        rr['v246_prev_market_date'] = prev_strong_d
        rr['v236_all_strong1_pct'] = all_strong.get(prev_strong_d)
        rr['v246_breadth_date'] = prev_breadth_d
        rr['v236_br_above_ma20'] = br_ma20.get(prev_breadth_d)
        rr['v244_industry'] = ind
        rr['v244_industry_prev_date'] = prev_ind_d
        rr.update(feats)
        rr['v244_ind_vs_all_strong1'] = sf(rr.get('v244_ind_strong1_pct'), 0) - sf(rr.get('v236_all_strong1_pct'), 0)
        rr['v246_parent_rule_pass'] = parent_rule_pass(rr)
        rr['v246_daily_shadow_rule_pass'] = v246_rule_pass(rr)
        if rr['v246_parent_rule_pass']:
            parent_raw.append(rr)
        if rr['v246_daily_shadow_rule_pass']:
            selected_raw.append(rr)

    pri_poi = {'DEMAND_OB': 0, 'OB+FVG': 1, 'FVG_Demand': 2}
    pri_event = {'SSL_SWEEP_CHOCH_REVERSAL': 0, 'BOS_CONTINUATION': 1}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in selected_raw:
        groups[row_key(r)].append(r)

    dedup: list[dict[str, Any]] = []
    duplicate_keys: list[dict[str, Any]] = []
    for k, arr in groups.items():
        if len(arr) > 1:
            duplicate_keys.append({'symbol': k[0], 'entry_date': k[1], 'raw_count': len(arr)})
        arr = sorted(arr, key=lambda r: (
            0 if str(r.get('v244_industry')) not in WEAK_INDUSTRIES else 1,
            pri_poi.get(str(r.get('poi_source')), 9),
            pri_event.get(str(r.get('event_type')), 9),
            sf(r.get('risk_pct'), 999),
            sf(r.get('entry_chase_above_zone_pct'), 999),
        ))
        best = dict(arr[0])
        k2 = row_key(best)
        for name, vals in history.items():
            best['overlap_' + name] = k2 in vals
        best['actionable_by_maxhold10'] = sf(best.get('bars_since_entry'), 999) <= MAX_ACTIONABLE_BARS
        best['time_order_bad'] = any(
            bool(dn(best.get(f)) and dn(best.get(f)) >= dn(best.get('entry_date')))
            for f in ('v246_prev_market_date', 'v246_breadth_date', 'v244_industry_prev_date')
        )
        dedup.append(best)

    actionable = [
        r for r in dedup
        if r['actionable_by_maxhold10']
        and not any(r.get('overlap_' + name) for name in history)
        and not r['time_order_bad']
    ]
    expired = [r for r in dedup if not r['actionable_by_maxhold10']]
    overlap = [r for r in dedup if any(r.get('overlap_' + name) for name in history)]
    time_bad = [r for r in dedup if r['time_order_bad']]
    active_pollution = [r for r in actionable if any(str(r.get(f) or '') for f in ('exit_date', 'exit_reason', 'pnl_pct', 'won', 'base_exit_reason', 'base_pnl_pct'))]

    pd.DataFrame(parent_raw).to_csv(out / 'v246_current_parent_raw_rows.csv', index=False)
    pd.DataFrame(dedup).to_csv(out / 'v246_current_rule_dedup_rows.csv', index=False)
    pd.DataFrame(actionable).to_csv(out / 'v246_current_actionable_rows.csv', index=False)
    pd.DataFrame(expired).to_csv(out / 'v246_current_expired_rows.csv', index=False)

    summary = {
        'version': RULE_VERSION,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(out),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'dry_source': str(dry_path),
        'latest_market_date': max(strong_dates) if strong_dates else '',
        'dry_recent45_rows': sum(1 for r in dry if r.get('v161_recent45')),
        'parent_raw_rule_rows': len(parent_raw),
        'raw_rule_rows': len(selected_raw),
        'dedup_rule_rows': len(dedup),
        'duplicate_symbol_entry_keys': len(duplicate_keys),
        'expired_rows': len(expired),
        'overlap_rows': len(overlap),
        'time_order_bad_count': len(time_bad),
        'active_outcome_pollution': len(active_pollution),
        'new_actionable_rows': len(actionable),
        'selector_fields': selector_fields,
        'selector_leak_fields': leak,
        'history_key_counts': {k: len(v) for k, v in history.items()},
        'new_actionable_symbols': [
            {
                'symbol': r.get('symbol'),
                'entry_date': dn(r.get('entry_date')),
                'bars_since_entry': r.get('bars_since_entry'),
                'market_state': r.get('market_state'),
                'event_type': r.get('event_type'),
                'poi_source': r.get('poi_source'),
                'industry': r.get('v244_industry'),
                'allStrongPrev': r.get('v236_all_strong1_pct'),
                'brAboveMA20Prev': r.get('v236_br_above_ma20'),
                'indStrongPrev': r.get('v244_ind_strong1_pct'),
                'indVsAllStrong': r.get('v244_ind_vs_all_strong1'),
                'risk_pct': r.get('risk_pct'),
                'entry_chase_above_zone_pct': r.get('entry_chase_above_zone_pct'),
            }
            for r in actionable
        ],
        'decision': 'V246_CURRENT_ACTIONABLE_ROWS_FOUND__SHADOW_ONLY_ENDPOINT_MAPPING_NEXT' if actionable else 'V246_NO_CURRENT_ACTIONABLE_ROWS__KEEP_SHADOW_MONITORING_NO_WRITE',
    }
    (out / 'v246_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (AUDIT / 'v246_daily_current_shadow_audit_latest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
