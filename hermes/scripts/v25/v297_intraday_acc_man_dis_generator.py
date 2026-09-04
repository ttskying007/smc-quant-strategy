#!/usr/bin/env python3
"""V297 no-write: same-source 60m ACC->MAN->DIS lifecycle generator.

Hypothesis after V296: the useful signal is not a daily zone with a later
60m overlay, but an intraday operator lifecycle built from the same 60m source:
accumulation range -> downside manipulation/sweep -> reclaim -> distribution /
takeover.  This script scans all available local 60m files and replays next-day
A-share execution on daily bars.  It writes only audit artifacts.
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
K60_DIRS = [BASE / 'kline_cache_60min', BASE / 'kline_cache']
KDAY_DIR = BASE / 'kline_cache'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v297_intraday_acc_man_dis_no_write_{TS}'
LATEST = AUDIT / 'v297_intraday_acc_man_dis_latest.json'


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def dn(t: Any) -> str:
    s = str(t or '')
    return s[:8] if len(s) >= 8 else ''


def sym_from_path(p: Path) -> str:
    parts = p.name.split('_')
    if len(parts) >= 2:
        return f'{parts[0]}.{parts[1]}'
    return p.stem


def path60(sym: str) -> Path | None:
    code, ex = sym.split('.')
    names = [f'{code}_{ex}_60min_500.json', f'{code}_{ex}_60min_200.json']
    for d in K60_DIRS:
        for name in names:
            p = d / name
            if p.exists():
                return p
    return None


def pathday(sym: str) -> Path | None:
    code, ex = sym.split('.')
    for name in (f'{code}_{ex}_daily_750.json', f'{code}_{ex}_daily_300.json'):
        p = KDAY_DIR / name
        if p.exists():
            return p
    return None


def load_json(p: Path | None) -> list[dict[str, Any]]:
    if not p or not p.exists():
        return []
    try:
        x = json.loads(p.read_text())
        return x if isinstance(x, list) else []
    except Exception:
        return []


def load60(sym: str) -> list[dict[str, Any]]:
    rows = []
    for b in load_json(path60(sym)):
        d = dn(b.get('t'))
        if not d:
            continue
        rows.append({'t': str(b.get('t')), 'd': d, 'o': sf(b.get('o')), 'h': sf(b.get('h')),
                     'l': sf(b.get('l')), 'c': sf(b.get('c')), 'v': sf(b.get('v'), 0.0)})
    rows.sort(key=lambda x: x['t'])
    return [r for r in rows if all(not math.isnan(r[k]) for k in ('o', 'h', 'l', 'c'))]


def loadday(sym: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if sym in cache:
        return cache[sym]
    rows = []
    for b in load_json(pathday(sym)):
        d = dn(b.get('t') or b.get('date'))
        if d:
            rows.append({'d': d, 'o': sf(b.get('o')), 'h': sf(b.get('h')), 'l': sf(b.get('l')), 'c': sf(b.get('c'))})
    rows.sort(key=lambda x: x['d'])
    cache[sym] = rows
    return rows


def next_day_open(daily: list[dict[str, Any]], signal_date: str) -> tuple[str, float] | None:
    idx = next((i for i, b in enumerate(daily) if b['d'] == signal_date), None)
    if idx is None or idx + 1 >= len(daily):
        return None
    b = daily[idx + 1]
    if math.isnan(b['o']) or b['o'] <= 0:
        return None
    return b['d'], b['o']


def replay(daily: list[dict[str, Any]], entry_date: str, entry: float, sl: float, rr: float = 1.2, max_hold: int = 20) -> dict[str, Any] | None:
    idx = next((i for i, b in enumerate(daily) if b['d'] == entry_date), None)
    if idx is None or idx >= len(daily) - 2 or entry <= 0 or sl <= 0 or sl >= entry:
        return None
    tp = entry + rr * (entry - sl)
    for j in range(idx + 1, min(len(daily), idx + 1 + max_hold)):
        b = daily[j]
        o, h, l = b['o'], b['h'], b['l']
        if math.isnan(o) or math.isnan(h) or math.isnan(l):
            continue
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
    for c, name in cuts:
        if x < c:
            return name
    return last


def scan_symbol(sym: str, bars: list[dict[str, Any]], daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if len(bars) < 80 or len(daily) < 50:
        return out
    seen: set[tuple[str, str, int, int]] = set()
    for i in range(25, len(bars) - 10):
        for acc_len in (8, 12, 16, 20):
            if i - acc_len < 0:
                continue
            acc = bars[i - acc_len:i]
            acc_hi = max(b['h'] for b in acc); acc_lo = min(b['l'] for b in acc)
            acc_mid = (acc_hi + acc_lo) / 2
            if acc_mid <= 0:
                continue
            acc_range = (acc_hi / acc_lo - 1) * 100
            if not (1.2 <= acc_range <= 10.0):
                continue
            prev = bars[max(0, i - acc_len - 20):i - acc_len]
            prev_range = (max([b['h'] for b in prev] or [acc_hi]) / min([b['l'] for b in prev] or [acc_lo]) - 1) * 100
            acc_vol = sum(b['v'] for b in acc) / max(1, len(acc))
            prev_vol = sum(b['v'] for b in prev) / max(1, len(prev)) if prev else acc_vol
            vol_quiet = acc_vol / prev_vol if prev_vol > 0 else 1.0
            if vol_quiet > 1.6:
                continue
            man_idx = None
            for j in range(i, min(len(bars), i + 3)):
                if bars[j]['l'] < acc_lo * 0.998:
                    man_idx = j
                    break
            if man_idx is None:
                continue
            man_low = min(b['l'] for b in bars[i:man_idx + 1])
            sweep_pct = (acc_lo / man_low - 1) * 100 if man_low > 0 else 0
            if sweep_pct < 0.2:
                continue
            reclaim_idx = None
            for j in range(man_idx, min(len(bars), man_idx + 4)):
                if bars[j]['c'] > acc_lo:
                    reclaim_idx = j
                    break
            if reclaim_idx is None:
                continue
            takeover_idx = None
            for j in range(reclaim_idx + 1, min(len(bars), reclaim_idx + 5)):
                if bars[j]['c'] > acc_hi and bars[j]['c'] > bars[reclaim_idx]['h']:
                    takeover_idx = j
                    break
            if takeover_idx is None:
                continue
            tk = bars[takeover_idx]
            signal_date = tk['d']
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
            impulse = (tk['c'] / bars[reclaim_idx]['c'] - 1) * 100 if bars[reclaim_idx]['c'] > 0 else math.nan
            risk = (entry / sl - 1) * 100 if sl > 0 else math.nan
            held = [b for b in daily if entry_date <= b['d'] <= res['exit_date']]
            post_hold_min = min((b['l'] / entry - 1) * 100 for b in held) if held and entry > 0 else math.nan
            row = {'symbol': sym, 'signal_date': signal_date, 'entry_date': entry_date,
                   'acc_len': acc_len, 'man_wait': man_idx - i + 1, 'dis_wait': takeover_idx - reclaim_idx,
                   'acc_range_pct': round(acc_range, 4), 'prev_range_pct': round(prev_range, 4),
                   'vol_quiet': round(vol_quiet, 4), 'sweep_pct': round(sweep_pct, 4),
                   'reclaim_delay': reclaim_idx - man_idx + 1, 'takeover_delay': takeover_idx - reclaim_idx,
                   'impulse_pct': round(impulse, 4), 'risk_pct': round(risk, 4),
                   'post_hold_min_pct': round(post_hold_min, 4), 'entry': round(entry, 4),
                   'sl': round(sl, 4), 'acc_hi': round(acc_hi, 4), 'acc_lo': round(acc_lo, 4),
                   'man_low': round(man_low, 4), 't1_violation': res['exit_date'] <= entry_date,
                   'acc_bucket': bucket(acc_range, [(3, 'ACC_TIGHT<3'), (5, 'ACC_MID3_5'), (7, 'ACC_WIDE5_7')], 'ACC_VWIDE>=7'),
                   'sweep_bucket': bucket(sweep_pct, [(1, 'SWP_SHALLOW<1'), (2, 'SWP_MID1_2')], 'SWP_DEEP>=2'),
                   'impulse_bucket': bucket(impulse, [(0.5, 'IMP_WEAK<0.5'), (1.5, 'IMP_MID0.5_1.5')], 'IMP_STRONG>=1.5'),
                   'risk_bucket': bucket(risk, [(4, 'RISK<4'), (6, 'RISK4_6'), (8, 'RISK6_8')], 'RISK>=8')}
            row.update(res)
            out.append(row)
    return out


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 'tp': 0, 'sl': 0,
            'gap_sl': 0, 'time': 0, 'years': defaultdict(lambda: [0, 0]),
            'months': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0); reason = str(r.get('reason', ''))
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl; a['loss'] += pnl <= 0
    a['micro'] += 0 < pnl < 1; a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'
    a['gap_sl'] += reason == 'GAP_SL'; a['time'] += reason.startswith('TIME')
    y = str(r.get('entry_date', ''))[:4]; m = str(r.get('entry_date', ''))[:6]
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
            'min_year_n': min(yc.values()) if yc else 0, 'min_year_wr': round(min(ywr.values()) if ywr else 0, 2),
            'month_counts': mc, 'month_wr': mwr, 'min_month_n': min(mc.values()) if mc else 0,
            'min_month_wr': round(min(mwr.values()) if mwr else 0, 2)}


def bucket_metrics(rows: list[dict[str, Any]], source_n: int) -> list[dict[str, Any]]:
    dims = ['acc_len', 'man_wait', 'dis_wait', 'acc_bucket', 'sweep_bucket', 'impulse_bucket', 'risk_bucket', 'reason']
    out = []
    for dim in dims:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            groups[str(r.get(dim, ''))].append(r)
        for val, rs in groups.items():
            if len(rs) >= 20:
                out.append({'dimension': dim, 'value': val, **metrics(rs, source_n)})
    out.sort(key=lambda x: (-x['n'], x.get('wr', 0)))
    return out[:120]


def score_rules(rows: list[dict[str, Any]], source_n: int) -> list[dict[str, Any]]:
    gates = {
        'risk<=8': lambda r: sf(r.get('risk_pct')) <= 8,
        'risk<=6': lambda r: sf(r.get('risk_pct')) <= 6,
        'sweep>=1': lambda r: sf(r.get('sweep_pct')) >= 1,
        'impulse>=1.5': lambda r: sf(r.get('impulse_pct')) >= 1.5,
        'acc_range<=5': lambda r: sf(r.get('acc_range_pct')) <= 5,
        'vol_quiet<=1.0': lambda r: sf(r.get('vol_quiet')) <= 1.0,
        'reclaim_delay<=2': lambda r: int(sf(r.get('reclaim_delay'), 9)) <= 2,
        'takeover_delay<=2': lambda r: int(sf(r.get('takeover_delay'), 9)) <= 2,
        'exclude_midwide_shallow_nonstrong': lambda r: not (r.get('sweep_bucket') == 'SWP_SHALLOW<1' and r.get('acc_bucket') in {'ACC_MID3_5', 'ACC_WIDE5_7', 'ACC_VWIDE>=7'} and r.get('impulse_bucket') != 'IMP_STRONG>=1.5'),
    }
    names = list(gates)
    scored = []
    combos = [()]
    for a in range(len(names)):
        combos.append((names[a],))
        for b in range(a + 1, len(names)):
            combos.append((names[a], names[b]))
            for c in range(b + 1, len(names)):
                combos.append((names[a], names[b], names[c]))
    for combo in combos:
        if 'risk<=6' in combo and 'risk<=8' in combo:
            continue
        kept = [r for r in rows if all(gates[x](r) for x in combo)]
        if len(kept) < 80:
            continue
        m = metrics(kept, source_n)
        if m['min_month_n'] < 5 or m['min_year_n'] < 20:
            continue
        m['rule'] = 'BASE_ACC_MAN_DIS' if not combo else ' & '.join(combo)
        scored.append(m)
    scored.sort(key=lambda x: (x['min_month_wr'], x['min_year_wr'], x['wr'], x['avg'], x['n']), reverse=True)
    return scored[:80]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    for d in K60_DIRS:
        for p in d.glob('*_60min_500.json'):
            files.setdefault(sym_from_path(p), p)
    day_cache: dict[str, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    scanned = 0
    for sym in sorted(files):
        b60 = load60(sym)
        daily = loadday(sym, day_cache)
        if b60 and daily:
            scanned += 1
            rows.extend(scan_symbol(sym, b60, daily))
    rows.sort(key=lambda r: (r['entry_date'], r['symbol'], r['acc_len'], r['man_wait'], r['dis_wait']))
    rows_path = OUT / 'v297_rows.csv'
    if rows:
        with rows_path.open('w', newline='') as fh:
            fieldnames = list(rows[0].keys())
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader(); w.writerows(rows)
    t1 = sum(1 for r in rows if r.get('t1_violation'))
    summary = {
        'version': 'V297_INTRADAY_ACC_MAN_DIS_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'hypothesis': 'Same-source 60m ACC->MAN->DIS lifecycle can outperform daily zone plus 60m overlay.',
        'inputs': {'sixty_min_files': len(files), 'symbols_scanned': scanned, 'daily_symbols': len(day_cache)},
        'raw_acc_man_dis': metrics(rows, scanned),
        't1_violations': t1,
        'top_rules': score_rules(rows, len(rows)),
        'bucket_metrics': bucket_metrics(rows, len(rows)),
        'artifacts': {'rows': str(rows_path), 'summary': str(OUT / 'v297_summary.json')},
    }
    (OUT / 'v297_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
