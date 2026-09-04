#!/usr/bin/env python3
"""V303 no-write: executable 15m entry timing overlay on V302 lifecycle rows.

V302 generated same-source 15m ACC->MAN->DIS candidates but bought blindly at
next daily open. This audit tests whether entry-day executable first/second 15m
confirmation improves quality while preserving A-share T+1 exits. It writes only
audit artifacts, never production/frontend/watchlist files.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
KDAY = BASE / 'kline_cache'
K15 = BASE / 'kline_cache_15min'
V302_LATEST = AUDIT / 'v302_15m_same_source_lifecycle_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v303_executable_15m_entry_timing_no_write_{TS}'
LATEST = AUDIT / 'v303_executable_15m_entry_timing_latest.json'


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def dn(x: Any) -> str:
    s = str(x or '')
    return s[:8] if len(s) >= 8 else ''


def load_json(p: Path | None) -> Any:
    if not p or not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def day_path(sym: str) -> Path | None:
    code, ex = sym.split('.')
    for name in (f'{code}_{ex}_daily_750.json', f'{code}_{ex}_daily_300.json'):
        p = KDAY / name
        if p.exists():
            return p
    return None


def cache15_path(sym: str) -> Path:
    code, ex = sym.split('.')
    return K15 / f'{code}_{ex}_15min_800.json'


def loadday(sym: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if sym in cache:
        return cache[sym]
    rows = []
    x = load_json(day_path(sym))
    if isinstance(x, list):
        for b in x:
            d = dn(b.get('t') or b.get('date'))
            if d:
                rows.append({'d': d, 'o': sf(b.get('o')), 'h': sf(b.get('h')), 'l': sf(b.get('l')), 'c': sf(b.get('c'))})
    rows.sort(key=lambda r: r['d'])
    cache[sym] = rows
    return rows


def load15(sym: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if sym in cache:
        return cache[sym]
    x = load_json(cache15_path(sym))
    rows = x if isinstance(x, list) else []
    rows.sort(key=lambda r: r.get('t', ''))
    cache[sym] = rows
    return rows


def bars_on_date(bars: list[dict[str, Any]], date: str) -> list[dict[str, Any]]:
    return [b for b in bars if dn(b.get('d') or b.get('t')) == date]


def replay_t1_daily(daily: list[dict[str, Any]], entry_date: str, entry: float, sl: float, rr: float = 1.2, max_hold: int = 20) -> dict[str, Any] | None:
    idx = next((i for i, b in enumerate(daily) if b['d'] == entry_date), None)
    if idx is None or idx >= len(daily) - 2 or not (0 < sl < entry):
        return None
    tp = entry + rr * (entry - sl)
    for j in range(idx + 1, min(len(daily), idx + 1 + max_hold)):
        b = daily[j]
        o, h, l = b['o'], b['h'], b['l']
        if o <= sl:
            return {'exit_date': b['d'], 'exit': o, 'reason': 'GAP_SL', 'pnl': (o / entry - 1) * 100, 'hold': j - idx}
        if l <= sl:
            return {'exit_date': b['d'], 'exit': sl, 'reason': 'SL', 'pnl': (sl / entry - 1) * 100, 'hold': j - idx}
        if h >= tp:
            return {'exit_date': b['d'], 'exit': tp, 'reason': 'TP', 'pnl': (tp / entry - 1) * 100, 'hold': j - idx}
    j = min(len(daily) - 1, idx + max_hold)
    b = daily[j]
    return {'exit_date': b['d'], 'exit': b['c'], 'reason': f'TIME{max_hold}', 'pnl': (b['c'] / entry - 1) * 100, 'hold': j - idx}


def bucket(x: float, cuts: list[tuple[float, str]], last: str) -> str:
    if math.isnan(x):
        return 'NA'
    for c, name in cuts:
        if x < c:
            return name
    return last


def entry_candidates(row: dict[str, Any], day15: list[dict[str, Any]], day_open: float) -> list[dict[str, Any]]:
    if len(day15) < 2 or day_open <= 0:
        return []
    acc_hi, acc_lo, sl = sf(row['acc_hi']), sf(row['acc_lo']), sf(row['sl'])
    if min(acc_hi, acc_lo, sl) <= 0:
        return []
    b1, b2 = day15[0], day15[1]
    first1_low = sf(b1['l']); first1_high = sf(b1['h']); first1_vol = sf(b1.get('v'), 0)
    first2_low = min(sf(b1['l']), sf(b2['l']))
    first2_high = max(sf(b1['h']), sf(b2['h']))
    first2_vol = first1_vol + sf(b2.get('v'), 0)
    out = []

    def add_mode(mode: str, price: float, bar_no: int, ok: bool, obs_low: float, obs_high: float, obs_vol: float) -> None:
        if not ok or not (price > sl > 0):
            return
        gap_acc = (day_open / acc_hi - 1) * 100 if acc_hi > 0 else math.nan
        risk = (price / sl - 1) * 100
        obs_dd = (obs_low / price - 1) * 100 if price > 0 else math.nan
        obs_push = (obs_high / day_open - 1) * 100 if day_open > 0 else math.nan
        if math.isnan(risk) or risk <= 0 or risk > 20:
            return
        out.append({
            'entry_mode': mode, 'entry_bar_no': bar_no, 'entry_price': price,
            'gap_to_acc_hi_pct': gap_acc, 'risk_pct2': risk, 'obs_dd_pct': obs_dd,
            'obs_push_pct': obs_push, 'obs_vol': obs_vol,
            'open_bucket': bucket(gap_acc, [(-2, 'GAP<-2'), (0, 'GAP-2_0'), (1, 'GAP0_1'), (3, 'GAP1_3')], 'GAP>=3'),
            'dd_bucket': bucket(obs_dd, [(-5, 'DD<-5'), (-2, 'DD-5_-2'), (-0.5, 'DD-2_-0.5'), (0, 'DD-0.5_0')], 'DD>=0'),
            'push_bucket': bucket(obs_push, [(0, 'PUSH<0'), (1, 'PUSH0_1'), (3, 'PUSH1_3'), (6, 'PUSH3_6')], 'PUSH>=6'),
            'risk2_bucket': bucket(risk, [(3, 'RISK<3'), (5, 'RISK3_5'), (8, 'RISK5_8')], 'RISK>=8'),
        })

    add_mode('DAY_OPEN_BASE', day_open, 0, day_open > sl, day_open, day_open, 0.0)
    add_mode('FIRST15_ACC_HOLD', sf(b1['c']), 1, sf(b1['l']) > sl and sf(b1['c']) > acc_lo and sf(b1['c']) >= sf(b1['o']), first1_low, first1_high, first1_vol)
    add_mode('FIRST15_TAKEOVER', sf(b1['c']), 1, sf(b1['l']) > acc_lo and sf(b1['c']) > acc_hi and sf(b1['c']) >= sf(b1['o']), first1_low, first1_high, first1_vol)
    add_mode('SECOND15_CONT', sf(b2['c']), 2, first2_low > sl and sf(b1['c']) > acc_lo and sf(b2['c']) > max(acc_hi, sf(b1['c']) * 0.995) and sf(b2['c']) >= sf(b2['o']), first2_low, first2_high, first2_vol)
    add_mode('FIRST30_NO_DUMP', sf(b2['c']), 2, first2_low > acc_lo * 0.995 and sf(b2['c']) > day_open and sf(b2['c']) > sl, first2_low, first2_high, first2_vol)
    return out


def blank() -> dict[str, Any]:
    return {'n': 0, 'win': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 'tp': 0, 'sl': 0, 'gap': 0, 'time': 0, 'symbols': set(), 'mc': defaultdict(int), 'mw': defaultdict(int), 't1': 0}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'))
    a['n'] += 1; a['sum'] += pnl; a['symbols'].add(r['symbol'])
    if pnl > 0: a['win'] += 1; a['mw'][r['month']] += 1
    else: a['loss'] += 1
    if 0 < abs(pnl) < 0.6: a['micro'] += 1
    reason = str(r.get('reason', ''))
    if reason == 'TP': a['tp'] += 1
    elif reason == 'SL': a['sl'] += 1
    elif reason == 'GAP_SL': a['gap'] += 1
    elif reason.startswith('TIME'): a['time'] += 1
    a['mc'][r['month']] += 1
    if str(r.get('t1_violation')).lower() == 'true': a['t1'] += 1


def finalize(a: dict[str, Any]) -> dict[str, Any]:
    n = a['n']
    if n == 0:
        return {'n': 0}
    mwr = {k: round(a['mw'][k] / v * 100, 2) for k, v in sorted(a['mc'].items()) if v}
    return {
        'n': n, 'wr': round(a['win'] / n * 100, 4), 'avg': round(a['sum'] / n, 4), 'loss': a['loss'],
        'micro': round(a['micro'] / n * 100, 2), 'tp_pct': round(a['tp'] / n * 100, 2),
        'sl_pct': round(a['sl'] / n * 100, 2), 'gap_sl_pct': round(a['gap'] / n * 100, 2),
        'time_pct': round(a['time'] / n * 100, 2), 'symbols': len(a['symbols']),
        'month_count': len(a['mc']), 'month_counts': dict(sorted(a['mc'].items())), 'month_wr': mwr,
        'min_month_n': min(a['mc'].values()) if a['mc'] else 0, 'min_month_wr': min(mwr.values()) if mwr else None,
        't1_violations': a['t1'],
    }


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    a = blank()
    for r in rows:
        add(a, r)
    return finalize(a)


def top_variants(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(blank)
    for r in rows:
        combos = [
            f"mode={r['entry_mode']}",
            f"mode={r['entry_mode']}|open={r['open_bucket']}",
            f"mode={r['entry_mode']}|dd={r['dd_bucket']}",
            f"mode={r['entry_mode']}|risk={r['risk2_bucket']}",
            f"mode={r['entry_mode']}|push={r['push_bucket']}",
            f"mode={r['entry_mode']}|acc={r['acc_bucket']}|sweep={r['sweep_bucket']}|risk={r['risk2_bucket']}",
            f"mode={r['entry_mode']}|open={r['open_bucket']}|dd={r['dd_bucket']}|risk={r['risk2_bucket']}",
            f"mode={r['entry_mode']}|push={r['push_bucket']}|risk={r['risk2_bucket']}",
        ]
        for c in combos:
            add(groups[c], r)
    out = []
    for name, a in groups.items():
        m = finalize(a)
        if m.get('n', 0) >= 50:
            m['variant'] = name
            out.append(m)
    out.sort(key=lambda x: (x.get('min_month_wr') or 0, x.get('wr') or 0, x.get('n') or 0), reverse=True)
    return out[:40]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v302 = load_json(V302_LATEST) or {}
    source_rows = Path(v302.get('artifacts', {}).get('rows', ''))
    if not source_rows.exists():
        raise SystemExit(f'missing V302 rows: {source_rows}')
    day_cache: dict[str, list[dict[str, Any]]] = {}
    m15_cache: dict[str, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    source_count = 0; eligible_days = 0; no15 = 0
    with source_rows.open() as fh:
        for r in csv.DictReader(fh):
            source_count += 1
            sym, entry_date = r['symbol'], r['entry_date']
            daily = loadday(sym, day_cache)
            day15 = bars_on_date(load15(sym, m15_cache), entry_date)
            if len(day15) < 2:
                no15 += 1
                continue
            eligible_days += 1
            day_open = sf(r.get('entry'))
            for ec in entry_candidates(r, day15, day_open):
                sl = sf(r['sl'])
                res = replay_t1_daily(daily, entry_date, ec['entry_price'], sl)
                if not res:
                    continue
                out = dict(r)
                out.update({
                    'entry_mode': ec['entry_mode'], 'entry_bar_no': ec['entry_bar_no'],
                    'exec_entry': round(ec['entry_price'], 4), 'orig_daily_open': r['entry'],
                    'gap_to_acc_hi_pct': round(ec['gap_to_acc_hi_pct'], 4), 'risk_pct2': round(ec['risk_pct2'], 4),
                    'obs_dd_pct': round(ec['obs_dd_pct'], 4), 'obs_push_pct': round(ec['obs_push_pct'], 4),
                    'open_bucket': ec['open_bucket'], 'dd_bucket': ec['dd_bucket'], 'push_bucket': ec['push_bucket'], 'risk2_bucket': ec['risk2_bucket'],
                    'exit_date': res['exit_date'], 'exit': round(res['exit'], 4), 'reason': res['reason'], 'pnl': round(res['pnl'], 4), 'hold': res['hold'],
                    't1_violation': res['exit_date'] <= entry_date,
                })
                rows.append(out)
    rows_path = OUT / 'v303_rows.csv'
    if rows:
        with rows_path.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    by_mode = []
    mode_groups: dict[str, dict[str, Any]] = defaultdict(blank)
    for r in rows:
        add(mode_groups[r['entry_mode']], r)
    for mode, a in sorted(mode_groups.items()):
        m = finalize(a); m['mode'] = mode; by_mode.append(m)
    by_mode.sort(key=lambda x: (x.get('min_month_wr') or 0, x.get('wr') or 0), reverse=True)
    summary = {
        'version': 'V303_EXECUTABLE_15M_ENTRY_TIMING_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'hypothesis': 'Entry-day executable first/second 15m persistence may filter V302 fake takeovers before buying, while exits remain strict T+1.',
        'source': {'v302_latest': str(V302_LATEST), 'v302_rows': str(source_rows), 'source_count': source_count, 'eligible_entry_days': eligible_days, 'missing_entry_day_15m': no15},
        'base_all_modes': metrics(rows), 'by_mode': by_mode, 'top_variants': top_variants(rows),
        'artifacts': {'dir': str(OUT), 'rows': str(rows_path), 'latest': str(LATEST)},
        'data_limitation': 'Uses V302 recent 2026 15m cache only; this is executable-timing diagnosis, not multi-year production proof.',
    }
    (OUT / 'v303_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
