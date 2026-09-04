#!/usr/bin/env python3
"""V326 no-write: exact-ish V246 lineage current supply audit.

V325 proved the single V246 current strict parent is stale and reconstructs only
3.7% of historical V246 rows. V326 separates the actual V246 source lineages and
checks whether any line has *current executable non-history supply*:
- V161/V164 scanner contract line;
- V175 baseline line (V172 gate + semantic split over current V164 rows);
- V211 child line (true_takeover_2 persistence add-on);
- V185 production active line (existing baseline, not new V246 supply).

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import glob, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
V164 = AUD / 'v164_corrected_scanner_dry_run_20260622/v164_dryrun_rows.json'
V185_TRADES = ROOT / 'smc_opt_v185_combined_production_candidate/v185_trades.json'
V185_ACTIVE = ROOT / 'smc_opt_v185_combined_production_candidate/v185_active_picks.json'
OUT = AUD / f"v326_v246_lineage_current_supply_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST = AUD / 'v326_v246_lineage_current_supply_latest.json'

WEAK_INDUSTRIES = {'C27医药制造业', 'C32有色金属冶炼和压延加工业'}
MAX_ACTIONABLE_BARS = 10


def sf(x: Any, default: float | None = None) -> float | None:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '').replace('-', '')[:10] if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def sym_from_file(path: str) -> str | None:
    parts = Path(path).name.split('_')
    if len(parts) >= 2 and parts[0].isdigit():
        return parts[0] + '.' + parts[1]
    return None


def kline_dates(symbol: str) -> list[str]:
    p = KDIR / f"{symbol.replace('.', '_')}_daily_750.json"
    arr = load_json(p, []) if p.exists() else []
    out = []
    for b in arr:
        d = dn(b.get('t') or b.get('date'))
        if d:
            out.append(d)
    return sorted(set(out))


def actual_bars_since(symbol: str, entry_date: str) -> int | None:
    ds = kline_dates(symbol)
    if not ds or not entry_date:
        return None
    return sum(1 for d in ds if d > entry_date)


def row_key(r: dict[str, Any]) -> tuple[str, str]:
    return str(r.get('symbol') or ''), dn(r.get('entry_date') or r.get('pick_date') or r.get('select_date'))


def build_all_market_strong1() -> tuple[dict[str, float], list[str]]:
    rows_by_date: dict[str, list[float]] = defaultdict(list)
    for fp in glob.glob(str(KDIR / '*_daily_750.json')):
        if not sym_from_file(fp):
            continue
        data = load_json(Path(fp), [])
        bars = []
        for b in data:
            d = dn(b.get('t') or b.get('date'))
            c = sf(b.get('c'))
            if d and c:
                bars.append((d, float(c)))
        bars.sort()
        for i in range(1, len(bars)):
            d, c = bars[i]
            pc = bars[i-1][1]
            if pc:
                rows_by_date[d].append((c / pc - 1) * 100)
    return {d: sum(x > 3 for x in vals) / len(vals) * 100 for d, vals in rows_by_date.items() if vals}, sorted(rows_by_date)


def load_breadth_above_ma20() -> tuple[dict[str, float], list[str]]:
    p = AUD / 'v185_market_breadth_cache.csv'
    if not p.exists():
        return {}, []
    df = pd.read_csv(p)
    out = {dn(r.get('breadth_date')): sf(r.get('br_above_ma20')) for r in df.to_dict('records') if dn(r.get('breadth_date'))}
    return {k: v for k, v in out.items() if v is not None}, sorted(out)


def previous(dates: list[str], d: str) -> str:
    # list is small enough for linear reverse; avoids importing bisect edge mistakes.
    prev = ''
    for x in dates:
        if x < d:
            prev = x
        else:
            break
    return prev


def build_industry_features() -> tuple[dict[str, str], dict[tuple[str, str], dict[str, float]], list[str]]:
    indmap = AUD / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
    items = load_json(indmap, [])
    sym_ind = {r.get('symbol'): (r.get('industry') or 'UNKNOWN') for r in items if r.get('symbol')}
    daily: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for fp in glob.glob(str(KDIR / '*_daily_750.json')):
        sym = sym_from_file(fp)
        if not sym:
            continue
        ind = sym_ind.get(sym, 'UNKNOWN')
        if ind == 'UNKNOWN':
            continue
        data = load_json(Path(fp), [])
        bars = []
        for b in data:
            d = dn(b.get('t') or b.get('date'))
            c = sf(b.get('c'))
            if d and c:
                bars.append((d, float(c)))
        bars.sort()
        for i in range(1, len(bars)):
            d, c = bars[i]
            pc = bars[i-1][1]
            if pc:
                daily[d][ind].append((c / pc - 1) * 100)
    feats: dict[tuple[str, str], dict[str, float]] = {}
    for d, mp in daily.items():
        for ind, vals in mp.items():
            s = pd.Series(vals)
            feats[(d, ind)] = {
                'v244_ind_n': float(len(vals)),
                'v244_ind_up1_pct': float((s > 1).mean() * 100),
                'v244_ind_strong1_pct': float((s > 3).mean() * 100),
                'v244_ind_mean_ret1': float(s.mean()),
            }
    return sym_ind, feats, sorted({d for d, _ in feats})


def industry_addback_pass(r: dict[str, Any]) -> bool:
    weak = str(r.get('v244_industry')) in WEAK_INDUSTRIES
    add = sf(r.get('v244_ind_strong1_pct'), -999) >= 31.1688 or sf(r.get('v236_br_above_ma20'), -999) >= 46.8561
    return (not weak) or add


def boolish(x: Any) -> bool:
    return str(x).strip().lower() in {'true', '1', 'yes'}


def line_v161(r: dict[str, Any]) -> bool:
    return boolish(r.get('v164_rule_pass')) and industry_addback_pass(r)


def line_v175(r: dict[str, Any]) -> bool:
    return (
        boolish(r.get('v164_rule_pass'))
        and str(r.get('poi_source')) == 'DEMAND_OB'
        and str(r.get('market_state')) == 'BEAR_RISK'
        and boolish(r.get('v132_true_takeover_3_strict'))
        and sf(r.get('v85_zone_width_pct'), -999) >= 2.0
        and sf(r.get('v132_post_zone_pullback_depth_pct_3'), 999) <= 2.0
        and industry_addback_pass(r)
    )


def line_v211(r: dict[str, Any]) -> bool:
    return (
        boolish(r.get('v132_true_takeover_2'))
        and not boolish(r.get('v132_true_takeover_3_strict'))
        and sf(r.get('v132_bull_count_3'), -1) >= 3
        and sf(r.get('v132_post_zone_pullback_depth_pct_3'), 999) <= 3
        and industry_addback_pass(r)
    )


def line_v246_stale_parent(r: dict[str, Any]) -> bool:
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
        and industry_addback_pass(r)
    )


def load_history() -> dict[str, set[tuple[str, str]]]:
    hist: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for name, path in [('v185_trades', V185_TRADES), ('v185_active', V185_ACTIVE)]:
        for r in load_json(path, []):
            hist[name].add(row_key(r))
    for name, pat in [
        ('v231_history', 'v231_v230_candidate_independent_audit_no_write_* /v231_combined_rows.csv'.replace(' ', '')),
        ('v236_history', 'v236_v235_independent_audit_current_smoke_no_write_* /v236_independent_combined_rows.csv'.replace(' ', '')),
        ('v246_history', 'v248_v246_independent_audit_no_write_* /v248_recomputed_selected_rows.csv'.replace(' ', '')),
    ]:
        paths = [Path(p) for p in glob.glob(str(AUD / pat))]
        if paths:
            p = max(paths, key=lambda x: x.stat().st_mtime)
            for r in pd.read_csv(p, low_memory=False).to_dict('records'):
                hist[name].add(row_key(r))
    return hist


def summarize(rows: list[dict[str, Any]], hist: dict[str, set[tuple[str, str]]]) -> dict[str, Any]:
    if not rows:
        return {'rows': 0, 'actual_recent45_rows': 0, 'actionable10_rows': 0, 'nonhistory_actionable10_rows': 0, 'history_overlap_rows': 0, 'latest_entry_date': '', 'entry_dates_top': {}}
    dedup_map: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        k = row_key(r)
        # source-side deterministic preference: lower risk then lower chase.
        if k not in dedup_map or (sf(r.get('risk_pct'), 999), sf(r.get('entry_chase_above_zone_pct'), 999)) < (sf(dedup_map[k].get('risk_pct'), 999), sf(dedup_map[k].get('entry_chase_above_zone_pct'), 999)):
            dedup_map[k] = r
    arr = list(dedup_map.values())
    for r in arr:
        ed = dn(r.get('entry_date'))
        r['v326_actual_bars_since_entry'] = actual_bars_since(str(r.get('symbol')), ed)
        k = row_key(r)
        r['v326_any_history_overlap'] = any(k in s for s in hist.values())
        r['v326_actionable10'] = (r['v326_actual_bars_since_entry'] is not None and r['v326_actual_bars_since_entry'] <= MAX_ACTIONABLE_BARS)
        r['v326_actual_recent45'] = (r['v326_actual_bars_since_entry'] is not None and r['v326_actual_bars_since_entry'] <= 45)
    eds = [dn(r.get('entry_date')) for r in arr if dn(r.get('entry_date'))]
    vc = pd.Series(eds).value_counts().head(12).to_dict() if eds else {}
    return {
        'rows': len(arr),
        'actual_recent45_rows': int(sum(r['v326_actual_recent45'] for r in arr)),
        'actionable10_rows': int(sum(r['v326_actionable10'] for r in arr)),
        'nonhistory_actionable10_rows': int(sum(r['v326_actionable10'] and not r['v326_any_history_overlap'] for r in arr)),
        'history_overlap_rows': int(sum(r['v326_any_history_overlap'] for r in arr)),
        'latest_entry_date': max(eds) if eds else '',
        'entry_dates_top': {str(k): int(v) for k, v in vc.items()},
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dry0 = load_json(V164, [])
    all_strong, strong_dates = build_all_market_strong1()
    br, br_dates = load_breadth_above_ma20()
    sym_ind, ind_feats, ind_dates = build_industry_features()
    hist = load_history()
    rows = []
    for r0 in dry0:
        r = dict(r0)
        ed = dn(r.get('entry_date'))
        sym = str(r.get('symbol') or '')
        r['entry_date'] = ed
        ps = previous(strong_dates, ed)
        pb = previous(br_dates, ed)
        ind = sym_ind.get(sym, 'UNKNOWN')
        pi = previous(ind_dates, ed)
        r['v236_prev_market_date'] = ps
        r['v236_all_strong1_pct'] = all_strong.get(ps)
        r['v236_breadth_date'] = pb
        r['v236_br_above_ma20'] = br.get(pb)
        r['v244_industry'] = ind
        r['v244_industry_prev_date'] = pi
        r.update(ind_feats.get((pi, ind), {}))
        rows.append(r)

    routes = {
        'line_v161_v164_plus_v246_industry': [r for r in rows if line_v161(r)],
        'line_v175_current_v172_gate_plus_v246_industry': [r for r in rows if line_v175(r)],
        'line_v211_tt2_persistence_plus_v246_industry': [r for r in rows if line_v211(r)],
        'line_v246_old_strict_parent_for_comparison': [r for r in rows if line_v246_stale_parent(r)],
    }
    summaries = {k: summarize(v, hist) for k, v in routes.items()}
    for k, v in routes.items():
        pd.DataFrame(v).to_csv(OUT / f'{k}.csv', index=False)

    active_v185 = load_json(V185_ACTIVE, [])
    v185_active_summary = summarize([dict(r, entry_date=dn(r.get('entry_date') or r.get('pick_date'))) for r in active_v185], hist)

    blockers = []
    for name, s in summaries.items():
        if name != 'line_v246_old_strict_parent_for_comparison' and s['nonhistory_actionable10_rows'] == 0:
            blockers.append(f'{name}:0_nonhistory_actionable10')
    if v185_active_summary['actionable10_rows'] == 0:
        blockers.append('v185_active_baseline_has_no_actionable10_rows_now')

    decision = 'V326_NO_V246_LINEAGE_HAS_CURRENT_NONHISTORY_ACTIONABLE_SUPPLY__NO_WRITE'
    if any(s['nonhistory_actionable10_rows'] > 0 for k, s in summaries.items() if k != 'line_v246_old_strict_parent_for_comparison'):
        decision = 'V326_HAS_SHADOW_CURRENT_ROWS_REQUIRING_ENDPOINT_SMOKE__NO_WRITE'

    report = {
        'version': 'V326_V246_LINEAGE_CURRENT_SUPPLY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source': str(V164),
        'dry_rows': len(rows),
        'route_definitions': {
            'line_v161': 'v164_rule_pass AND V246 weak-industry addback',
            'line_v175': 'current V164 rows satisfying V172 gate: DEMAND_OB, BEAR_RISK, true_takeover_3_strict, zone_width>=2, post_pullback3<=2, then V246 industry',
            'line_v211': 'true_takeover_2 AND NOT true_takeover_3_strict AND bull_count3>=3 AND post_pullback3<=3, then V246 industry',
            'old_strict_parent': 'stale V246 current-shadow parent from v246_daily_current_shadow_audit.py',
        },
        'summaries': summaries,
        'v185_active_baseline_summary': v185_active_summary,
        'blockers': blockers,
        'decision': decision,
        'conclusion': 'V246 historical pass is real, but current executable supply is not available as non-history <=10-bar candidates on this scanner snapshot. Keep V185 production; keep V246/V211/V175 as shadow research until a fresh scanner run yields actionable rows.',
        'artifacts': {
            'out_dir': str(OUT),
            'latest': str(LATEST),
            **{k: str(OUT / f'{k}.csv') for k in routes},
        },
    }
    (OUT / 'v326_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'latest': str(LATEST), 'decision': decision, 'summaries': summaries, 'v185_active': v185_active_summary, 'blockers': blockers}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
