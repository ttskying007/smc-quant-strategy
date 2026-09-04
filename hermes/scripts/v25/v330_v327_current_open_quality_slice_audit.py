#!/usr/bin/env python3
"""V330 no-write: quality-slice V327 current open candidates.

V326/V327 proved fresh current supply exists again after refreshing the scanner,
but V328 showed the broad V164 lineage is historically too weak. V330 asks the
next concrete question: among the live V327 candidates, which *non-future*
quality slices both (a) preserve V246 historical selected quality and (b) avoid
obvious current replay loss concentration?

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V327 = AUD / 'v327_v326_current_candidate_executable_replay_latest.json'
V244 = AUD / 'v244_post_v243_industry_participation_probe_no_write_20260701_151619/v244_best_rows.csv'
OUT = AUD / f"v330_v327_current_open_quality_slice_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST = AUD / 'v330_v327_current_open_quality_slice_latest.json'

GATE = {'hist_n': 300, 'hist_wr': 93.0, 'hist_avg': 7.0, 'hist_min_year_wr': 90.0, 'current_n': 5, 'current_mtm_avg': 0.0}
WEAK_INDUSTRIES = {'C27医药制造业', 'C32有色金属冶炼和压延加工业'}


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


def boolish(x: Any) -> bool:
    return str(x).strip().lower() in {'true', '1', 'yes'}


def metrics_hist(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) == 0:
        return {'n': 0, 'wr': 0, 'avg': 0, 'min_year_wr': 0, 'year_counts': {}, 'year_wr': {}, 'micro': 0, 't1': 0}
    p = pd.to_numeric(df['pnl_pct'], errors='coerce')
    yrs = df['entry_date'].astype(str).str[:4]
    yc = yrs.value_counts().sort_index().to_dict()
    ywr = {str(y): round(float((p[yrs == y] > 0).mean() * 100), 2) for y in sorted(yc)}
    t1 = int(((df.get('exit_date', pd.Series('', index=df.index)).map(dn) == df['entry_date'].map(dn)) & df['entry_date'].map(dn).ne('')).sum())
    return {'n': int(len(df)), 'wr': round(float((p > 0).mean() * 100), 4), 'avg': round(float(p.mean()), 4), 'min_year_wr': round(float(min(ywr.values()) if ywr else 0), 2), 'year_counts': {str(k): int(v) for k, v in yc.items()}, 'year_wr': ywr, 'micro': round(float(((p > 0) & (p < 1)).mean() * 100), 4), 't1': t1}


def metrics_current(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) == 0:
        return {'n': 0, 'closed_n': 0, 'open_n': 0, 'closed_wr': 0, 'closed_avg': 0, 'mtm_avg': 0, 'mtm_wr': 0, 'sl_n': 0, 'tp_n': 0, 't1': 0}
    mtm = []
    for _, r in df.iterrows():
        p = sf(r.get('pnl_pct'))
        if p is None:
            ep, lc = sf(r.get('entry_price')), sf(r.get('latest_close'))
            p = (lc / ep - 1) * 100 if ep and lc else 0.0
        mtm.append(p)
    mtm_s = pd.Series(mtm)
    status = df['status'].astype(str)
    closed = df[status.str.contains('CLOSED', na=False)]
    open_mask = status.str.contains('OPEN', na=False) | closed.index.to_series().map(lambda _: False)
    cp = pd.to_numeric(closed.get('pnl_pct', pd.Series(dtype=float)), errors='coerce')
    return {
        'n': int(len(df)), 'closed_n': int(len(closed)), 'open_n': int((~status.str.contains('CLOSED', na=False)).sum()),
        'closed_wr': round(float((cp > 0).mean() * 100), 4) if len(closed) else 0,
        'closed_avg': round(float(cp.mean()), 4) if len(closed) else 0,
        'mtm_avg': round(float(mtm_s.mean()), 4), 'mtm_wr': round(float((mtm_s > 0).mean() * 100), 4),
        'sl_n': int((closed.get('exit_reason', pd.Series(dtype=str)).astype(str) == 'SL').sum()),
        'tp_n': int((closed.get('exit_reason', pd.Series(dtype=str)).astype(str) == 'TP').sum()),
        't1': int(closed.get('same_day_exit_violation', pd.Series(False, index=closed.index)).astype(str).str.lower().isin(['true','1']).sum()),
    }


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    rep = json.loads(V327.read_text())
    cur = pd.read_csv(rep['artifacts']['rows_csv'], low_memory=False)
    cur['entry_date'] = cur['entry_date'].map(dn)
    cur['status'] = cur['status'].fillna('OPEN_UNEXPIRED')
    hist = pd.read_csv(V244, low_memory=False)
    hist['entry_date'] = hist['entry_date'].map(dn)
    weak = hist['v244_industry'].astype(str).isin(WEAK_INDUSTRIES)
    add = (pd.to_numeric(hist['v244_ind_strong1_pct'], errors='coerce') >= 31.1688) | (pd.to_numeric(hist['v236_br_above_ma20'], errors='coerce') >= 46.8561)
    hist = hist[(~weak) | (weak & add)].copy()
    # keep only rows that are intended as V246 selected historical route. This is not
    # proof of broad production quality; it tests whether a live slice is consistent
    # with the historical high-quality V246 selected population.
    return cur, hist, rep


def predicate_bank(df: pd.DataFrame) -> dict[str, Callable[[pd.DataFrame], pd.Series]]:
    return {
        'route_v175': lambda x: x['routes'].astype(str).str.contains('line_v175', na=False) if 'routes' in x else pd.Series(False, index=x.index),
        'route_v161': lambda x: x['routes'].astype(str).str.contains('line_v161', na=False) if 'routes' in x else pd.Series(True, index=x.index),
        'tt3': lambda x: x.get('v132_true_takeover_3_strict', pd.Series(False, index=x.index)).map(boolish),
        'tt2_or_tt3': lambda x: x.get('v132_true_takeover_2', pd.Series(False, index=x.index)).map(boolish) | x.get('v132_true_takeover_3_strict', pd.Series(False, index=x.index)).map(boolish),
        'bear_risk': lambda x: x['market_state'].astype(str).eq('BEAR_RISK'),
        'ssl_reversal': lambda x: x['event_type'].astype(str).eq('SSL_SWEEP_CHOCH_REVERSAL'),
        'demand_ob': lambda x: x['poi_source'].astype(str).eq('DEMAND_OB'),
        'ob_or_obfvg': lambda x: x['poi_source'].astype(str).isin(['DEMAND_OB', 'OB+FVG']),
        'risk_le_4': lambda x: pd.to_numeric(x['risk_pct'], errors='coerce').le(4),
        'risk_2_6': lambda x: pd.to_numeric(x['risk_pct'], errors='coerce').between(2, 6, inclusive='both'),
        'chase_le_2': lambda x: pd.to_numeric(x['entry_chase_above_zone_pct'], errors='coerce').le(2),
        'chase_le_3': lambda x: pd.to_numeric(x['entry_chase_above_zone_pct'], errors='coerce').le(3),
        'zone_width_ge_1_5': lambda x: pd.to_numeric(x['v85_zone_width_pct'], errors='coerce').ge(1.5),
        'zone_width_ge_2': lambda x: pd.to_numeric(x['v85_zone_width_pct'], errors='coerce').ge(2),
        'pullback3_zero': lambda x: pd.to_numeric(x['v132_post_zone_pullback_depth_pct_3'], errors='coerce').fillna(999).le(0.0001),
        'bull3_ge_3': lambda x: pd.to_numeric(x['v132_bull_count_3'], errors='coerce').ge(3),
        'body_le_60': lambda x: pd.to_numeric(x['v132_reclaim_bull_body_pct'], errors='coerce').le(60),
        'breadth_25_70': lambda x: pd.to_numeric(x['v236_br_above_ma20'], errors='coerce').between(25, 70, inclusive='both'),
        'strong1_le_25': lambda x: pd.to_numeric(x['v236_all_strong1_pct'], errors='coerce').le(25),
        'ind_strong_ge_10': lambda x: pd.to_numeric(x['v244_ind_strong1_pct'], errors='coerce').ge(10),
        'ind_up_le_80': lambda x: pd.to_numeric(x['v244_ind_up1_pct'], errors='coerce').le(80),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cur, hist, rep = load_inputs()
    bank = predicate_bank(cur)
    names = list(bank)
    rows = []
    # singles, pairs, triples. Avoid very broad route_v161 alone noise but keep for baseline.
    for k in range(1, 4):
        for comb in itertools.combinations(names, k):
            try:
                mcur = pd.Series(True, index=cur.index)
                mh = pd.Series(True, index=hist.index)
                for name in comb:
                    mcur &= bank[name](cur).fillna(False)
                    mh &= bank[name](hist).fillna(False)
                cdf, hdf = cur[mcur].copy(), hist[mh].copy()
                cm, hm = metrics_current(cdf), metrics_hist(hdf)
                score = (hm['wr'] - 90) * min(hm['n'], 573) / 573 + cm['mtm_avg'] + cm['open_n'] * 0.05 - cm['sl_n'] * 0.4
                rows.append({'rule': ' & '.join(comb), 'score': round(float(score), 4), 'hist': hm, 'current': cm})
            except Exception as e:
                rows.append({'rule': ' & '.join(comb), 'error': str(e)})

    usable = [r for r in rows if 'hist' in r and r['hist']['n'] >= GATE['hist_n'] and r['hist']['wr'] >= GATE['hist_wr'] and r['hist']['avg'] >= GATE['hist_avg'] and r['hist']['min_year_wr'] >= GATE['hist_min_year_wr'] and r['current']['n'] >= GATE['current_n'] and r['current']['mtm_avg'] >= GATE['current_mtm_avg'] and r['current']['t1'] == 0]
    usable = sorted(usable, key=lambda r: (r['score'], r['current']['mtm_avg'], r['hist']['n']), reverse=True)
    all_sorted = sorted([r for r in rows if 'hist' in r], key=lambda r: (r['score'], r['hist']['wr'], r['current']['mtm_avg']), reverse=True)

    top_rule = usable[0] if usable else None
    if top_rule:
        mcur = pd.Series(True, index=cur.index)
        mh = pd.Series(True, index=hist.index)
        for name in top_rule['rule'].split(' & '):
            mcur &= bank[name](cur).fillna(False)
            mh &= bank[name](hist).fillna(False)
        cur_sel = cur[mcur].copy()
        hist_sel = hist[mh].copy()
    else:
        cur_sel = cur.iloc[0:0].copy(); hist_sel = hist.iloc[0:0].copy()

    cur_sel.to_csv(OUT / 'v330_top_current_rows.csv', index=False)
    hist_sel.to_csv(OUT / 'v330_top_historical_rows.csv', index=False)
    pd.DataFrame([{**{'rule': r['rule'], 'score': r.get('score')}, **{f"hist_{k}": v for k, v in r.get('hist', {}).items() if not isinstance(v, dict)}, **{f"cur_{k}": v for k, v in r.get('current', {}).items() if not isinstance(v, dict)}} for r in all_sorted[:200]]).to_csv(OUT / 'v330_rule_table_top200.csv', index=False)

    report = {
        'version': 'V330_V327_CURRENT_OPEN_QUALITY_SLICE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': {'v327': str(V327), 'v244': str(V244), 'v327_rows_csv': rep['artifacts']['rows_csv']},
        'gate': GATE,
        'baseline_current': metrics_current(cur),
        'baseline_historical_v246_selected': metrics_hist(hist),
        'usable_rule_count': len(usable),
        'top_usable_rules': usable[:20],
        'top_all_rules': all_sorted[:30],
        'decision': 'V330_FOUND_SHADOW_SLICE_FOR_ENDPOINT_MAPPING__NO_PRODUCTION_WRITE' if usable else 'V330_NO_CURRENT_SLICE_MEETS_HISTORICAL_AND_CURRENT_GATES__NO_WRITE',
        'caveat': 'Historical metric is measured only on the V246 selected population, not the full V164 universe; therefore a passing V330 slice is eligible for shadow endpoint smoke only, not production promotion.',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST), 'current_rows': str(OUT / 'v330_top_current_rows.csv'), 'historical_rows': str(OUT / 'v330_top_historical_rows.csv'), 'rule_table': str(OUT / 'v330_rule_table_top200.csv')},
    }
    (OUT / 'v330_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'latest': str(LATEST), 'decision': report['decision'], 'baseline_current': report['baseline_current'], 'baseline_historical': report['baseline_historical_v246_selected'], 'top_usable_rules': usable[:5], 'artifacts': report['artifacts']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
