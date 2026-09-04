#!/usr/bin/env python3
"""V335 no-write: exit-contract frontier after V334 signal-family ceiling.

V333/V334 showed V164/V246-style full-universe pre-entry filters cannot pass the
production gate under the fixed executable contract (SL=zone_low*0.99, TP=1.5R,
max_hold=10). V335 changes direction: keep pre-entry signal rules fixed and test
whether the remaining gap is an exit-contract problem (TP/SL/hold) or a true
signal-family ceiling.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import itertools, json, math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
V333 = AUD / 'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT = AUD / f"v335_exit_contract_frontier_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST = AUD / 'v335_exit_contract_frontier_latest.json'
GATE = {'n': 570, 'min_year_n': 70, 'wr': 93.0, 'avg': 7.6, 'min_year_wr': 91.0, 'micro': 1.0, 't1': 0, 'current_open': 1}
MAX_ACTIONABLE = 10
WEAK = {'C27医药制造业', 'C32有色金属冶炼和压延加工业'}


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
    p = KDIR / f"{sym.replace('.', '_')}_daily_750.json"
    out = []
    for b in load_json(p, []):
        d = dn(b.get('t') or b.get('date'))
        o, h, l, c = sf(b.get('o')), sf(b.get('h')), sf(b.get('l')), sf(b.get('c'))
        if d and None not in (o, h, l, c):
            out.append({'date': d, 'o': float(o), 'h': float(h), 'l': float(l), 'c': float(c)})
    return sorted(out, key=lambda r: r['date'])


def replay_contract(r: dict[str, Any], bar_cache: dict[str, list[dict[str, Any]]], sl_buf: float, r_mult: float, max_hold: int) -> dict[str, Any]:
    sym, ed = str(r.get('symbol') or ''), dn(r.get('entry_date'))
    ep, zl = sf(r.get('entry_price')), sf(r.get('zone_low') or r.get('dz_low'))
    if sym not in bar_cache:
        bar_cache[sym] = load_bars(sym)
    bars = bar_cache[sym]
    dates = [b['date'] for b in bars]
    actual_since = sum(1 for d in dates if d > ed) if ed in dates else None
    out = {'actual_bars_since_entry': actual_since, 'status': 'FIELD_MISSING'}
    if not sym or not ed or ep is None or zl is None or ep <= 0 or zl <= 0:
        return out
    sl = zl * (1 - sl_buf)
    if sl >= ep:
        sl = ep * 0.985
    risk = ep - sl
    tp = ep + risk * r_mult
    path = [b for b in bars if b['date'] > ed]
    out.update({'status': 'OPEN_UNEXPIRED', 'sl': sl, 'tp': tp, 'latest_date': path[-1]['date'] if path else '', 'latest_close': path[-1]['c'] if path else None})
    for i, b in enumerate(path, 1):
        reason, px = '', None
        # Conservative when both hit in one day: count SL first.
        if b['l'] <= sl:
            reason, px = 'SL', sl
        elif b['h'] >= tp:
            reason, px = 'TP', tp
        elif i >= max_hold:
            reason, px = 'TIME', b['c']
        if reason:
            out.update({'status': 'CLOSED', 'exit_reason': reason, 'exit_date': b['date'], 'exit_price': px, 'hold_bars': i, 'pnl_pct': (px / ep - 1) * 100, 'same_day_exit_violation': b['date'] == ed})
            break
    return out


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [r for r in rows if r.get('status') == 'CLOSED']
    if not closed:
        return {'n': 0, 'wr': 0, 'avg': 0, 'min_year_n': 0, 'year_counts': {}, 'year_wr': {}, 'min_year_wr': 0, 'micro': 0, 't1': 0, 'exit_counts': {}}
    p = pd.Series([sf(r.get('pnl_pct'), 0) for r in closed])
    yrs = pd.Series([dn(r.get('entry_date'))[:4] for r in closed])
    yc = yrs.value_counts().sort_index().to_dict()
    # Exclude tiny 2017 cache remnant from min_year gate if sample starts before 2023 accidentally.
    yc_gate = {k: v for k, v in yc.items() if str(k) >= '2023'}
    ywr = {str(y): round(float((p[yrs == y] > 0).mean() * 100), 2) for y in sorted(yc_gate)}
    return {
        'n': int(len(closed)),
        'wr': round(float((p > 0).mean() * 100), 4),
        'avg': round(float(p.mean()), 4),
        'min_year_n': int(min(yc_gate.values()) if yc_gate else 0),
        'year_counts': {str(k): int(v) for k, v in yc_gate.items()},
        'year_wr': ywr,
        'min_year_wr': round(float(min(ywr.values()) if ywr else 0), 2),
        'micro': round(float(((p > 0) & (p < 1)).mean() * 100), 4),
        't1': int(sum(bool(r.get('same_day_exit_violation')) for r in closed)),
        'exit_counts': {str(k): int(v) for k, v in pd.Series([r.get('exit_reason') for r in closed]).value_counts().to_dict().items()},
    }


def gate_ok(m: dict[str, Any]) -> bool:
    return m['n'] >= GATE['n'] and m['min_year_n'] >= GATE['min_year_n'] and m['wr'] >= GATE['wr'] and m['avg'] >= GATE['avg'] and m['min_year_wr'] >= GATE['min_year_wr'] and m['micro'] <= GATE['micro'] and m['t1'] == 0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rep = load_json(V333, {})
    df = pd.read_csv(rep['artifacts']['replayed_csv'], low_memory=False)
    df['entry_date'] = df['entry_date'].map(dn)
    actual = pd.to_numeric(df['v333_actual_bars_since_entry'], errors='coerce')
    hist_base = actual.ge(MAX_ACTIONABLE)
    cur_base = actual.le(MAX_ACTIONABLE) & (~df['v333_any_history_overlap'].astype(str).str.lower().isin(['true', '1']))
    weak = df['v244_industry'].astype(str).isin(WEAK)
    add = pd.to_numeric(df['v244_ind_strong1_pct'], errors='coerce').ge(31.1688) | pd.to_numeric(df['v236_br_above_ma20'], errors='coerce').ge(46.8561)
    base = df['v164_rule_pass'].map(boolish) & ((~weak) | add)
    n = lambda c: pd.to_numeric(df.get(c, pd.Series(index=df.index)), errors='coerce')
    s = lambda c: df.get(c, pd.Series('', index=df.index)).astype(str)

    families = {
        'F1_bull3_body60_pull2': base & n('v132_bull_count_3').ge(3) & n('v132_reclaim_bull_body_pct').le(60) & n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2),
        'F2_bull3_zone2_ob': base & n('v132_bull_count_3').ge(3) & n('v85_zone_width_pct').ge(2) & s('poi_source').isin(['DEMAND_OB', 'OB+FVG']),
        'F3_bull3_zone2_pull2': base & n('v132_bull_count_3').ge(3) & n('v85_zone_width_pct').ge(2) & n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2),
        'F4_bull3_body60_pull2_chase3': base & n('v132_bull_count_3').ge(3) & n('v132_reclaim_bull_body_pct').le(60) & n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2) & n('entry_chase_above_zone_pct').le(3),
        'F5_bull3_body60_pull2_br20_55': base & n('v132_bull_count_3').ge(3) & n('v132_reclaim_bull_body_pct').le(60) & n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2) & n('v236_br_above_ma20').between(20, 55, inclusive='both'),
        'F6_bull3_body60_pull2_reclaim_le2': base & n('v132_bull_count_3').ge(3) & n('v132_reclaim_bull_body_pct').le(60) & n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2) & n('reclaim_close_above_zone_pct').le(2),
    }
    contracts = list(itertools.product([0.005, 0.01, 0.015, 0.02], [1.2, 1.5, 1.8, 2.0, 2.5, 3.0], [10, 15, 20]))

    bar_cache: dict[str, list[dict[str, Any]]] = {}
    results = []
    best_rows = []
    for fname, fmask in families.items():
        idx = df.index[fmask.fillna(False)].tolist()
        if len(idx) < 250:
            continue
        records = df.loc[idx].to_dict('records')
        for sl_buf, r_mult, max_hold in contracts:
            replayed = []
            for r in records:
                rr = {'symbol': r.get('symbol'), 'entry_date': r.get('entry_date')}
                rr.update(replay_contract(r, bar_cache, sl_buf, r_mult, max_hold))
                replayed.append(rr)
            hist_rows = [r for r, ix in zip(replayed, idx) if bool(hist_base.loc[ix])]
            cur_rows = [r for r, ix in zip(replayed, idx) if bool(cur_base.loc[ix])]
            hm = metrics(hist_rows)
            cm = metrics([r for r in cur_rows if r.get('status') == 'CLOSED'])
            open_n = sum(r.get('status') == 'OPEN_UNEXPIRED' for r in cur_rows)
            score = (hm['wr'] - 90) * min(hm['n'], 1200) / 1200 + hm['avg'] * 0.55 + hm['min_year_wr'] * 0.03 - hm['micro'] * 0.4 + open_n * 0.05
            results.append({'family': fname, 'sl_buf': sl_buf, 'r_mult': r_mult, 'max_hold': max_hold, 'score': round(float(score), 4), 'hist': hm, 'current_closed': cm, 'current_rows': len(cur_rows), 'current_open_rows': open_n, 'pass_gate': gate_ok(hm) and open_n >= GATE['current_open']})
    results = sorted(results, key=lambda r: (r['pass_gate'], r['hist']['wr'], r['hist']['avg'], r['hist']['n'], r['current_open_rows']), reverse=True)
    passing = [r for r in results if r['pass_gate']]
    top = passing[0] if passing else results[0]

    pd.DataFrame([{**{k: r[k] for k in ['family', 'sl_buf', 'r_mult', 'max_hold', 'score', 'current_rows', 'current_open_rows', 'pass_gate']}, **{f"hist_{k}": v for k, v in r['hist'].items() if not isinstance(v, dict)}, **{f"cur_{k}": v for k, v in r['current_closed'].items() if not isinstance(v, dict)}} for r in results[:500]]).to_csv(OUT / 'v335_exit_rule_table_top500.csv', index=False)

    report = {
        'version': 'V335_EXIT_CONTRACT_FRONTIER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': rep['artifacts']['replayed_csv'],
        'gate': GATE,
        'families': list(families.keys()),
        'contract_grid': {'sl_buf': [0.005, 0.01, 0.015, 0.02], 'r_mult': [1.2, 1.5, 1.8, 2.0, 2.5, 3.0], 'max_hold': [10, 15, 20]},
        'evaluated_contracts': len(results),
        'passing_rule_count': len(passing),
        'top_passing_rules': passing[:20],
        'top_rules': results[:40],
        'decision': 'V335_EXIT_CONTRACT_CAN_RECOVER_PRODUCTION_GATE__SHADOW_ONLY_NO_WRITE' if passing else 'V335_NO_EXIT_CONTRACT_RECOVERS_GATE__SIGNAL_FAMILY_CEILING_CONFIRMED',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST), 'rule_table': str(OUT / 'v335_exit_rule_table_top500.csv')},
    }
    (OUT / 'v335_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'latest': str(LATEST), 'decision': report['decision'], 'passing_rule_count': len(passing), 'top_passing': passing[:5], 'top_rules': results[:10]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
