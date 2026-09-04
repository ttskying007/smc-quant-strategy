#!/usr/bin/env python3
"""V302 no-write: 15m same-source ACC->MAN->DIS lifecycle audit.

After V297-V301 showed 60m/daily-board threshold branches remain weak-month
unstable, this script tests the next causal layer that is available locally via
Tencent: recent 15m bars. It scans all daily-cache symbols, fetches/reuses m15
bars, builds same-source intraday lifecycle candidates, and replays strict T+1
A-share daily exits. It writes only cache/audit artifacts, never production,
frontend, or watchlist files.
"""
from __future__ import annotations

import csv
import json
import math
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
KDAY = BASE / 'kline_cache'
K15 = BASE / 'kline_cache_15min'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v302_15m_same_source_lifecycle_no_write_{TS}'
LATEST = AUDIT / 'v302_15m_same_source_lifecycle_latest.json'
MAX_WORKERS = 18
M15_COUNT = 800


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


def symbol_from_daily_path(p: Path) -> str | None:
    parts = p.name.split('_')
    if len(parts) < 3:
        return None
    return f'{parts[0]}.{parts[1]}'


def tencent_code(sym: str) -> str:
    code, ex = sym.split('.')
    return ex.lower() + code


def cache15_path(sym: str) -> Path:
    code, ex = sym.split('.')
    return K15 / f'{code}_{ex}_15min_{M15_COUNT}.json'


def day_path(sym: str) -> Path | None:
    code, ex = sym.split('.')
    for name in (f'{code}_{ex}_daily_750.json', f'{code}_{ex}_daily_300.json'):
        p = KDAY / name
        if p.exists():
            return p
    return None


def load_json(p: Path | None) -> Any:
    if not p or not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def normalize_m15(raw: Any, sym: str) -> list[dict[str, Any]]:
    key = tencent_code(sym)
    rows = []
    try:
        data = raw['data'][key].get('m15', [])
    except Exception:
        return rows
    for r in data:
        if not isinstance(r, list) or len(r) < 6:
            continue
        t = str(r[0]); d = dn(t)
        o, c, h, l, v = sf(r[1]), sf(r[2]), sf(r[3]), sf(r[4]), sf(r[5], 0.0)
        if d and all(not math.isnan(x) for x in (o, c, h, l)) and o > 0 and h > 0 and l > 0 and c > 0:
            rows.append({'t': t, 'd': d, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    rows.sort(key=lambda x: x['t'])
    return rows


def fetch_one(sym: str) -> dict[str, Any]:
    p = cache15_path(sym)
    cached = load_json(p)
    if isinstance(cached, list) and cached:
        return {'sym': sym, 'status': 'cached', 'n': len(cached), 'path': str(p)}
    key = tencent_code(sym)
    url = f'http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={key},m15,,{M15_COUNT}'
    last_err = ''
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=12) as resp:
                raw = json.loads(resp.read().decode('utf-8'))
            rows = normalize_m15(raw, sym)
            if rows:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(rows, ensure_ascii=False, separators=(',', ':')))
                return {'sym': sym, 'status': 'fetched', 'n': len(rows), 'path': str(p)}
            last_err = 'empty_rows'
        except Exception as e:
            last_err = repr(e)
            time.sleep(0.25 * (attempt + 1))
    return {'sym': sym, 'status': 'failed', 'n': 0, 'error': last_err}


def load15(sym: str) -> list[dict[str, Any]]:
    x = load_json(cache15_path(sym))
    return x if isinstance(x, list) else []


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


def next_day_open(daily: list[dict[str, Any]], signal_date: str) -> tuple[str, float] | None:
    idx = next((i for i, b in enumerate(daily) if b['d'] == signal_date), None)
    if idx is None or idx + 1 >= len(daily):
        return None
    b = daily[idx + 1]
    return (b['d'], b['o']) if b['o'] > 0 and not math.isnan(b['o']) else None


def replay(daily: list[dict[str, Any]], entry_date: str, entry: float, sl: float, rr: float = 1.2, max_hold: int = 20) -> dict[str, Any] | None:
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


def scan_symbol(sym: str, bars: list[dict[str, Any]], daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(bars) < 80 or len(daily) < 50:
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    for i in range(24, len(bars) - 8):
        for acc_len in (8, 12, 16):
            if i - acc_len < 0:
                continue
            acc = bars[i - acc_len:i]
            acc_hi = max(b['h'] for b in acc); acc_lo = min(b['l'] for b in acc)
            if acc_lo <= 0:
                continue
            acc_range = (acc_hi / acc_lo - 1) * 100
            if not (0.6 <= acc_range <= 7.0):
                continue
            prev = bars[max(0, i - acc_len - 24):i - acc_len]
            acc_vol = sum(b['v'] for b in acc) / len(acc)
            prev_vol = sum(b['v'] for b in prev) / len(prev) if prev else acc_vol
            vol_quiet = acc_vol / prev_vol if prev_vol > 0 else 1.0
            if vol_quiet > 1.5:
                continue
            man_idx = None
            for j in range(i, min(len(bars), i + 5)):
                if bars[j]['l'] < acc_lo * 0.998:
                    man_idx = j
                    break
            if man_idx is None:
                continue
            man_low = min(b['l'] for b in bars[i:man_idx + 1])
            sweep_pct = (acc_lo / man_low - 1) * 100 if man_low > 0 else math.nan
            if math.isnan(sweep_pct) or not (0.2 <= sweep_pct <= 8.0):
                continue
            reclaim_idx = None
            for j in range(man_idx, min(len(bars), man_idx + 5)):
                if bars[j]['c'] > acc_lo and bars[j]['c'] > bars[j]['o']:
                    reclaim_idx = j
                    break
            if reclaim_idx is None:
                continue
            takeover_idx = None
            for j in range(reclaim_idx + 1, min(len(bars), reclaim_idx + 7)):
                if bars[j]['c'] > acc_hi and bars[j]['c'] > bars[reclaim_idx]['h']:
                    takeover_idx = j
                    break
            if takeover_idx is None:
                continue
            signal_date = bars[takeover_idx]['d']
            nd = next_day_open(daily, signal_date)
            if not nd:
                continue
            entry_date, entry = nd
            sl = min(man_low, acc_lo) * 0.992
            res = replay(daily, entry_date, entry, sl)
            if not res:
                continue
            key = (sym, signal_date, acc_len, takeover_idx)
            if key in seen:
                continue
            seen.add(key)
            tk = bars[takeover_idx]
            impulse = (tk['c'] / bars[reclaim_idx]['c'] - 1) * 100 if bars[reclaim_idx]['c'] > 0 else math.nan
            risk = (entry / sl - 1) * 100 if sl > 0 else math.nan
            if math.isnan(risk) or risk <= 0 or risk > 20:
                continue
            out.append({
                'symbol': sym, 'signal_date': signal_date, 'entry_date': entry_date, 'exit_date': res['exit_date'],
                'year': entry_date[:4], 'month': entry_date[:6], 'acc_len': acc_len,
                'acc_range_pct': round(acc_range, 4), 'vol_quiet': round(vol_quiet, 4),
                'man_wait': man_idx - i + 1, 'reclaim_delay': reclaim_idx - man_idx + 1,
                'takeover_delay': takeover_idx - reclaim_idx, 'sweep_pct': round(sweep_pct, 4),
                'impulse_pct': round(impulse, 4), 'risk_pct': round(risk, 4),
                'entry': round(entry, 4), 'sl': round(sl, 4), 'acc_hi': round(acc_hi, 4), 'acc_lo': round(acc_lo, 4),
                'man_low': round(man_low, 4), 'pnl': round(res['pnl'], 4), 'reason': res['reason'], 'hold': res['hold'],
                't1_violation': res['exit_date'] <= entry_date,
                'acc_bucket': bucket(acc_range, [(1.5, 'ACC_TIGHT<1.5'), (3, 'ACC_MID1.5_3'), (5, 'ACC_WIDE3_5')], 'ACC_VWIDE>=5'),
                'volq_bucket': bucket(vol_quiet, [(0.7, 'VQ<0.7'), (1.0, 'VQ0.7_1'), (1.3, 'VQ1_1.3')], 'VQ>=1.3'),
                'sweep_bucket': bucket(sweep_pct, [(0.6, 'SWEEP<0.6'), (1.2, 'SWEEP0.6_1.2'), (2.5, 'SWEEP1.2_2.5')], 'SWEEP>=2.5'),
                'risk_bucket': bucket(risk, [(3, 'RISK<3'), (5, 'RISK3_5'), (8, 'RISK5_8')], 'RISK>=8'),
                'impulse_bucket': bucket(impulse, [(0.8, 'IMP<0.8'), (1.5, 'IMP0.8_1.5'), (3, 'IMP1.5_3')], 'IMP>=3'),
            })
    return out


def blank() -> dict[str, Any]:
    return {'n': 0, 'win': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 'tp': 0, 'sl': 0, 'gap': 0, 'time': 0, 'symbols': set(), 'yc': defaultdict(int), 'yw': defaultdict(int), 'mc': defaultdict(int), 'mw': defaultdict(int), 't1': 0}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'))
    a['n'] += 1; a['sum'] += pnl; a['symbols'].add(r['symbol'])
    if pnl > 0: a['win'] += 1
    else: a['loss'] += 1
    if 0 < abs(pnl) < 0.6: a['micro'] += 1
    reason = str(r.get('reason', ''))
    if reason == 'TP': a['tp'] += 1
    elif reason == 'SL': a['sl'] += 1
    elif reason == 'GAP_SL': a['gap'] += 1
    elif reason.startswith('TIME'): a['time'] += 1
    y = r.get('year', ''); m = r.get('month', '')
    a['yc'][y] += 1; a['mc'][m] += 1
    if pnl > 0: a['yw'][y] += 1; a['mw'][m] += 1
    if str(r.get('t1_violation')).lower() == 'true': a['t1'] += 1


def finalize(a: dict[str, Any]) -> dict[str, Any]:
    n = a['n']
    if n == 0:
        return {'n': 0}
    ywr = {k: round(a['yw'][k] / v * 100, 2) for k, v in sorted(a['yc'].items()) if v}
    mwr = {k: round(a['mw'][k] / v * 100, 2) for k, v in sorted(a['mc'].items()) if v}
    return {
        'n': n, 'wr': round(a['win'] / n * 100, 4), 'avg': round(a['sum'] / n, 4), 'loss': a['loss'],
        'micro': round(a['micro'] / n * 100, 2), 'tp_pct': round(a['tp'] / n * 100, 2),
        'sl_pct': round(a['sl'] / n * 100, 2), 'gap_sl_pct': round(a['gap'] / n * 100, 2),
        'time_pct': round(a['time'] / n * 100, 2), 'symbols': len(a['symbols']),
        'year_counts': dict(sorted(a['yc'].items())), 'year_wr': ywr, 'min_year_wr': min(ywr.values()) if ywr else None,
        'month_count': len(a['mc']), 'min_month_n': min(a['mc'].values()) if a['mc'] else 0,
        'min_month_wr': min(mwr.values()) if mwr else None, 't1_violations': a['t1'],
    }


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    a = blank()
    for r in rows: add(a, r)
    return finalize(a)


def top_variants(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dims = ['acc_len', 'acc_bucket', 'volq_bucket', 'sweep_bucket', 'risk_bucket', 'impulse_bucket']
    groups: dict[str, dict[str, Any]] = defaultdict(blank)
    for r in rows:
        combos = []
        for d in dims:
            combos.append(f'{d}={r[d]}')
        combos += [
            f"acc={r['acc_bucket']}|risk={r['risk_bucket']}",
            f"sweep={r['sweep_bucket']}|imp={r['impulse_bucket']}",
            f"acc={r['acc_bucket']}|sweep={r['sweep_bucket']}|risk={r['risk_bucket']}",
            f"acc={r['acc_bucket']}|volq={r['volq_bucket']}|imp={r['impulse_bucket']}",
        ]
        for k in combos:
            add(groups[k], r)
    out = []
    for name, a in groups.items():
        m = finalize(a)
        if m.get('n', 0) >= 50:
            m['variant'] = name
            out.append(m)
    out.sort(key=lambda x: (x.get('min_year_wr') or 0, x.get('wr') or 0, x.get('n') or 0), reverse=True)
    return out[:30]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True); K15.mkdir(parents=True, exist_ok=True)
    syms = sorted({s for p in KDAY.glob('*_daily_750.json') if (s := symbol_from_daily_path(p))})
    fetch_stats = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(fetch_one, s): s for s in syms}
        done = 0
        for fut in as_completed(futs):
            fetch_stats.append(fut.result())
            done += 1
            if done % 500 == 0:
                print(f'fetched/check {done}/{len(syms)}', file=sys.stderr)
    daily_cache: dict[str, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    scanned = 0; covered = 0
    for sym in syms:
        b15 = load15(sym)
        if not b15:
            continue
        covered += 1
        day = loadday(sym, daily_cache)
        rs = scan_symbol(sym, b15, day)
        rows.extend(rs)
        scanned += 1
        if scanned % 500 == 0:
            print(f'scanned {scanned}/{covered}, rows={len(rows)}', file=sys.stderr)
    rows_path = OUT / 'v302_rows.csv'
    if rows:
        with rows_path.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    fetch_counts = defaultdict(int)
    fetch_ns = []
    for r in fetch_stats:
        fetch_counts[r['status']] += 1
        if r.get('n'): fetch_ns.append(r['n'])
    summary = {
        'version': 'V302_15M_SAME_SOURCE_LIFECYCLE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'hypothesis': '15m same-source ACC->MAN->DIS lifecycle may provide more causal takeover evidence than 60m/daily-board thresholds.',
        'symbols_total': len(syms), 'symbols_15m_covered': covered, 'fetch_counts': dict(fetch_counts),
        'm15_count_requested': M15_COUNT, 'm15_rows_median': median(fetch_ns) if fetch_ns else 0,
        'base': metrics(rows), 'top_variants': top_variants(rows),
        'artifacts': {'dir': str(OUT), 'rows': str(rows_path), 'latest': str(LATEST)},
        'data_limitation': 'Tencent m15 max observed around 800 bars, so V302 is recent-period 2026-only/near-term evidence, not a multi-year production backtest.',
    }
    (OUT / 'v302_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
