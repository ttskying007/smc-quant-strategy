#!/usr/bin/env python3
"""V333 no-write: refreshed-breadth full-universe rule search.

After V332 rebuilt stale breadth cache, V326/V327 again found current shadow rows,
but V331 showed the hand-picked V330 slices fail on the full V164 universe. This
script performs a broader, non-selected-only rule search on the full V164 dry-run
universe with executable T+1 replay precomputed once per candidate.

Goal: find a rule that simultaneously:
- passes historical full-universe production gate;
- has current non-history executable open/actionable rows;
- has no T+1 violations and low micro-profit pollution.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import itertools, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
SRC = AUD / 'v164_corrected_scanner_dry_run_20260622/v164_dryrun_rows.json'
OUT = AUD / f"v333_full_universe_rule_search_after_breadth_refresh_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST = AUD / 'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
MAX_HOLD = 10
GATE = {'n': 570, 'min_year_n': 70, 'wr': 93.0, 'avg': 7.6, 'min_year_wr': 91.0, 'micro': 1.0, 't1': 0, 'current_open': 1}
WEAK_INDUSTRIES = {'C27医药制造业', 'C32有色金属冶炼和压延加工业'}


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '').replace('-', '')[:10] if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


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


def boolish(x: Any) -> bool:
    return str(x).strip().lower() in {'true', '1', 'yes'}


def load_json(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def load_bars(sym: str) -> list[dict[str, Any]]:
    arr = []
    p = KDIR / f"{sym.replace('.', '_')}_daily_750.json"
    for b in load_json(p, []):
        d = dn(b.get('t') or b.get('date'))
        o, h, l, c = sf(b.get('o')), sf(b.get('h')), sf(b.get('l')), sf(b.get('c'))
        if d and None not in (o, h, l, c):
            arr.append({'date': d, 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(arr, key=lambda r: r['date'])


def replay_row(r: dict[str, Any], bar_cache: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    sym, ed = str(r.get('symbol') or ''), dn(r.get('entry_date'))
    ep, zl = sf(r.get('entry_price')), sf(r.get('zone_low') or r.get('dz_low'))
    if sym not in bar_cache:
        bar_cache[sym] = load_bars(sym)
    bars = bar_cache[sym]
    dates = [b['date'] for b in bars]
    actual_since = sum(1 for d in dates if d > ed) if ed in dates else None
    out = {'entry_date': ed, 'v333_actual_bars_since_entry': actual_since}
    if not sym or not ed or ep is None or zl is None or ep <= 0 or zl <= 0:
        out.update({'replay_status': 'FIELD_MISSING'})
        return out
    sl = zl * 0.99
    tp = ep + (ep - sl) * 1.5
    path = [b for b in bars if b['date'] > ed]
    out.update({'replay_status': 'OPEN_UNEXPIRED', 'sl': sl, 'tp': tp, 'latest_date': path[-1]['date'] if path else '', 'latest_close': path[-1]['c'] if path else None})
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


def pass_industry(df: pd.DataFrame) -> pd.Series:
    weak = df['v244_industry'].astype(str).isin(WEAK_INDUSTRIES)
    add = pd.to_numeric(df.get('v244_ind_strong1_pct', pd.Series(index=df.index)), errors='coerce').ge(31.1688) | pd.to_numeric(df.get('v236_br_above_ma20', pd.Series(index=df.index)), errors='coerce').ge(46.8561)
    return (~weak) | add


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    closed = df[df['replay_status'].astype(str).eq('CLOSED')].copy()
    if len(closed) == 0:
        return {'n': 0, 'wr': 0, 'avg': 0, 'min_year_n': 0, 'year_wr': {}, 'min_year_wr': 0, 'micro': 0, 't1': 0, 'exit_counts': {}}
    p = pd.to_numeric(closed['pnl_pct'], errors='coerce')
    yrs = closed['entry_date'].astype(str).str[:4]
    yc = yrs.value_counts().sort_index().to_dict()
    ywr = {str(y): round(float((p[yrs == y] > 0).mean() * 100), 2) for y in sorted(yc)}
    return {
        'n': int(len(closed)), 'wr': round(float((p > 0).mean() * 100), 4), 'avg': round(float(p.mean()), 4),
        'min_year_n': int(min(yc.values()) if yc else 0), 'year_counts': {str(k): int(v) for k, v in yc.items()},
        'year_wr': ywr, 'min_year_wr': round(float(min(ywr.values()) if ywr else 0), 2),
        'micro': round(float(((p > 0) & (p < 1)).mean() * 100), 4),
        't1': int(closed.get('same_day_exit_violation', pd.Series(False, index=closed.index)).astype(str).str.lower().isin(['true', '1']).sum()),
        'exit_counts': {str(k): int(v) for k, v in closed['exit_reason'].astype(str).value_counts().to_dict().items()},
    }


def gate_ok(m: dict[str, Any]) -> bool:
    return m['n'] >= GATE['n'] and m['min_year_n'] >= GATE['min_year_n'] and m['wr'] >= GATE['wr'] and m['avg'] >= GATE['avg'] and m['min_year_wr'] >= GATE['min_year_wr'] and m['micro'] <= GATE['micro'] and m['t1'] == 0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = load_json(SRC, [])
    # enrichment uses V326 helpers after V332 breadth refresh
    import importlib.util
    spec = importlib.util.spec_from_file_location('v326_for_v333', '/root/.hermes/scripts/v25/v326_v246_lineage_current_supply_audit.py')
    v326 = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(v326)
    all_strong, strong_dates = v326.build_all_market_strong1(); br, br_dates = v326.load_breadth_above_ma20(); sym_ind, ind_feats, ind_dates = v326.build_industry_features(); hist = v326.load_history()

    bar_cache: dict[str, list[dict[str, Any]]] = {}
    rows = []
    seen = set()
    for r0 in raw:
        r = dict(r0)
        sym, ed = str(r.get('symbol') or ''), dn(r.get('entry_date'))
        # dedupe by symbol/date/poi to prevent duplicate scanner surfaces overweighting search
        k = (sym, ed, str(r.get('poi_source')))
        if k in seen:
            continue
        seen.add(k)
        ps, pb = v326.previous(strong_dates, ed), v326.previous(br_dates, ed)
        ind = sym_ind.get(sym, 'UNKNOWN'); pi = v326.previous(ind_dates, ed)
        r['entry_date'] = ed
        r['v236_all_strong1_pct'] = all_strong.get(ps)
        r['v236_br_above_ma20'] = br.get(pb)
        r['v244_industry'] = ind
        r.update(ind_feats.get((pi, ind), {}))
        r['v333_any_history_overlap'] = any((sym, ed) in s for s in hist.values())
        r.update(replay_row(r, bar_cache))
        rows.append(r)
    df = pd.DataFrame(rows)
    # Use CSV instead of parquet: pyarrow/fastparquet is not guaranteed in the runtime.
    df.to_csv(OUT / 'v333_full_universe_replayed.csv', index=False)

    b = lambda col: df.get(col, pd.Series(False, index=df.index)).map(boolish)
    n = lambda col: pd.to_numeric(df.get(col, pd.Series(index=df.index)), errors='coerce')
    predicates: dict[str, pd.Series] = {
        'v164': b('v164_rule_pass'),
        'v160': b('v160_rule_pass'),
        'industry': pass_industry(df),
        'tt3': b('v132_true_takeover_3_strict'),
        'tt2_or_tt3': b('v132_true_takeover_2') | b('v132_true_takeover_3_strict'),
        'tt2_only': b('v132_true_takeover_2') & ~b('v132_true_takeover_3_strict'),
        'bull3_ge3': n('v132_bull_count_3').ge(3),
        'bull3_ge2': n('v132_bull_count_3').ge(2),
        'body_le60': n('v132_reclaim_bull_body_pct').le(60),
        'body_le75': n('v132_reclaim_bull_body_pct').le(75),
        'chase_le2': n('entry_chase_above_zone_pct').le(2),
        'chase_le3': n('entry_chase_above_zone_pct').le(3),
        'risk_2_6': n('risk_pct').between(2, 6, inclusive='both'),
        'risk_le5': n('risk_pct').le(5),
        'zone_ge2': n('v85_zone_width_pct').ge(2),
        'pull3_le2': n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2),
        'pull3_le0': n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(0.0001),
        'bear_risk': df.get('market_state', pd.Series('', index=df.index)).astype(str).eq('BEAR_RISK'),
        'recovery_or_bear': df.get('market_state', pd.Series('', index=df.index)).astype(str).isin(['RECOVERY', 'BEAR_RISK']),
        'demand_ob': df.get('poi_source', pd.Series('', index=df.index)).astype(str).eq('DEMAND_OB'),
        'ob_or_obfvg': df.get('poi_source', pd.Series('', index=df.index)).astype(str).isin(['DEMAND_OB', 'OB+FVG']),
        'ssl_reversal': df.get('event_type', pd.Series('', index=df.index)).astype(str).eq('SSL_SWEEP_CHOCH_REVERSAL'),
        'strong1_le25': n('v236_all_strong1_pct').le(25),
        'strong1_5_35': n('v236_all_strong1_pct').between(5, 35, inclusive='both'),
        'br_20_55': n('v236_br_above_ma20').between(20, 55, inclusive='both'),
        'br_25_45': n('v236_br_above_ma20').between(25, 45, inclusive='both'),
        'ind_strong_ge10': n('v244_ind_strong1_pct').ge(10),
        'ind_up_le80': n('v244_ind_up1_pct').le(80),
    }
    # seed mandatory non-outcome route predicates; search 2-5 conjunctions with at least v164+industry
    names = list(predicates)
    base_names = ['v164', 'industry']
    candidates = []
    current_base = (df['v333_actual_bars_since_entry'].notna()) & (df['v333_actual_bars_since_entry'] <= MAX_HOLD) & (~df['v333_any_history_overlap'].astype(bool))
    hist_base = (df['v333_actual_bars_since_entry'].notna()) & (df['v333_actual_bars_since_entry'] >= MAX_HOLD)

    extras = [x for x in names if x not in base_names]
    for k in range(0, 4):
        for comb_extra in itertools.combinations(extras, k):
            comb = tuple(base_names + list(comb_extra))
            mask = pd.Series(True, index=df.index)
            for name in comb:
                mask &= predicates[name].fillna(False)
            hist_df = df[mask & hist_base]
            cur_df = df[mask & current_base]
            hm = metrics(hist_df)
            open_cur = cur_df[cur_df['replay_status'].astype(str).eq('OPEN_UNEXPIRED')]
            closed_cur = cur_df[cur_df['replay_status'].astype(str).eq('CLOSED')]
            cm = metrics(closed_cur)
            score = (hm['wr'] - 90) * min(hm['n'], 1000) / 1000 + hm['avg'] * 0.4 + len(open_cur) * 0.08 + cm['wr'] * 0.02 - hm['micro'] * 0.5
            candidates.append({'rule': ' & '.join(comb), 'score': round(float(score), 4), 'hist': hm, 'current_rows': int(len(cur_df)), 'current_open_rows': int(len(open_cur)), 'current_closed': cm})
    candidates = sorted(candidates, key=lambda r: (gate_ok(r['hist']) and r['current_open_rows'] >= GATE['current_open'], r['score'], r['hist']['wr'], r['hist']['avg']), reverse=True)
    passing = [r for r in candidates if gate_ok(r['hist']) and r['current_open_rows'] >= GATE['current_open']]

    top_rule = passing[0] if passing else candidates[0]
    mask = pd.Series(True, index=df.index)
    for name in top_rule['rule'].split(' & '):
        mask &= predicates[name].fillna(False)
    df[mask & hist_base].to_csv(OUT / 'v333_top_rule_historical_rows.csv', index=False)
    df[mask & current_base].to_csv(OUT / 'v333_top_rule_current_rows.csv', index=False)
    pd.DataFrame([{**{'rule': r['rule'], 'score': r['score'], 'current_rows': r['current_rows'], 'current_open_rows': r['current_open_rows']}, **{f"hist_{k}": v for k, v in r['hist'].items() if not isinstance(v, dict)}, **{f"cur_closed_{k}": v for k, v in r['current_closed'].items() if not isinstance(v, dict)}} for r in candidates[:300]]).to_csv(OUT / 'v333_rule_table_top300.csv', index=False)

    report = {
        'version': 'V333_FULL_UNIVERSE_RULE_SEARCH_AFTER_BREADTH_REFRESH_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': str(SRC), 'gate': GATE, 'replayed_rows': int(len(df)), 'predicate_count': len(predicates), 'searched_rules': len(candidates),
        'baseline_v164_industry': next((r for r in candidates if r['rule'] == 'v164 & industry'), None),
        'passing_rule_count': len(passing), 'top_passing_rules': passing[:20], 'top_rules': candidates[:30],
        'decision': 'V333_FULL_UNIVERSE_PASSING_CURRENT_RULE_FOUND__SHADOW_ONLY_NO_WRITE' if passing else 'V333_NO_FULL_UNIVERSE_RULE_PASSES_PRODUCTION_GATE__CLOSE_V246_PROMOTION_ROUTE_KEEP_RESEARCH',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST), 'replayed_csv': str(OUT / 'v333_full_universe_replayed.csv'), 'top_hist_csv': str(OUT / 'v333_top_rule_historical_rows.csv'), 'top_current_csv': str(OUT / 'v333_top_rule_current_rows.csv'), 'rule_table': str(OUT / 'v333_rule_table_top300.csv')},
    }
    (OUT / 'v333_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'latest': str(LATEST), 'decision': report['decision'], 'passing_rule_count': len(passing), 'top_passing': passing[:5], 'top_rules': candidates[:10]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
