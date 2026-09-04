#!/usr/bin/env python3
"""V279 no-write adaptive chronological SMC grammar audit.

Goal: test whether adaptive stock-DNA timing/interval parameters plus a stricter
chronological grammar beats V278's generic BOS->recent-demand->retest failure.
No production/frontend/watchlist writes.
"""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

BASE = Path('/root/.hermes')
KDIR = BASE / 'kline_cache'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v279_adaptive_temporal_grammar_no_write_{TS}'
LATEST = BASE / 'smc_audit/v279_adaptive_temporal_grammar_latest.json'
YEARS = {'2023', '2024', '2025', '2026'}


def f(x: Any, d=math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def ds(b: dict) -> str:
    return str(b.get('t', b.get('date', ''))).replace('.0', '')[:8]


def symbol_from_path(p: Path) -> str:
    stem = p.stem.replace('_daily_750', '')
    code, exch = stem.split('_', 1)
    return f'{code}.{exch}'


def blank() -> dict:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 't1': 0, 'tp': 0, 'sl': 0, 'time': 0, 'years': defaultdict(lambda: [0, 0])}


def add(a: dict, pnl: float, year: str, reason: str, t1: bool) -> None:
    a['n'] += 1
    a['wins'] += pnl > 0
    a['sum'] += pnl
    a['loss'] += pnl <= 0
    a['micro'] += 0 < pnl < 1
    a['t1'] += bool(t1)
    a['tp'] += reason == 'TP'
    a['sl'] += reason == 'SL'
    a['time'] += reason.startswith('TIME')
    a['years'][year][0] += 1
    a['years'][year][1] += pnl > 0


def metrics(a: dict, stock_count: int) -> dict:
    n = a['n']
    if not n:
        return {'n': 0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items())}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    return {
        'n': int(n),
        'wr': round(a['wins'] / n * 100, 4),
        'avg': round(a['sum'] / n, 4),
        'loss': int(a['loss']),
        'micro': round(a['micro'] / n * 100, 4),
        'min_year_n': min(yc.values()) if yc else 0,
        'year_counts': yc,
        'year_wr': ywr,
        'all_year_wr_min': round(min(ywr.values()) if ywr else 0, 2),
        'per_stock_3y_all_stocks': round(n / stock_count, 4),
        'tp_pct': round(a['tp'] / n * 100, 2),
        'sl_pct': round(a['sl'] / n * 100, 2),
        'time_pct': round(a['time'] / n * 100, 2),
        't1': int(a['t1']),
    }


def replay(bars: list[dict], entry_i: int, entry: float, sl: float, rr: float = 1.5, hold: int = 10):
    if entry_i + 1 >= len(bars) or sl <= 0 or entry <= sl:
        return None
    tp = entry + (entry - sl) * rr
    last = min(len(bars) - 1, entry_i + hold)
    xp, xi, reason = f(bars[last].get('c')), last, f'TIME{hold}'
    for i in range(entry_i + 1, last + 1):
        lo, hi = f(bars[i].get('l')), f(bars[i].get('h'))
        if lo <= sl:
            xp, xi, reason = sl, i, 'SL'
            break
        if hi >= tp:
            xp, xi, reason = tp, i, 'TP'
            break
    return (xp / entry - 1) * 100, ds(bars[entry_i])[:4], reason, ds(bars[xi]) == ds(bars[entry_i])


def pct_rank(vals: list[float], idx: int, lb: int = 80) -> dict:
    start = max(0, idx - lb)
    xs = [v for v in vals[start:idx] if not math.isnan(v)]
    if not xs:
        return {'med': math.nan, 'q60': math.nan, 'q75': math.nan}
    xs.sort()
    def q(p: float) -> float:
        return xs[min(len(xs) - 1, int((len(xs) - 1) * p))]
    return {'med': q(.5), 'q60': q(.6), 'q75': q(.75)}


def scan(path: Path):
    sym = symbol_from_path(path)
    try:
        bars = json.loads(path.read_text())
    except Exception:
        return {'symbol': sym, 'ok': False}, []
    n = len(bars)
    if n < 120:
        return {'symbol': sym, 'ok': False, 'bars': n}, []
    dates = [ds(b) for b in bars]
    o = [f(b.get('o')) for b in bars]
    h = [f(b.get('h')) for b in bars]
    l = [f(b.get('l')) for b in bars]
    c = [f(b.get('c')) for b in bars]
    v = [f(b.get('v'), 0.0) for b in bars]
    body_pct = [abs(c[i] - o[i]) / max(h[i] - l[i], 1e-9) * 100 if h[i] > l[i] else math.nan for i in range(n)]
    rng_pct = [(h[i] / max(l[i], 1e-9) - 1) * 100 if l[i] > 0 else math.nan for i in range(n)]
    vol_ratio = []
    for i in range(n):
        pre = [x for x in v[max(0, i - 20):i] if x > 0]
        vol_ratio.append(v[i] / (sum(pre) / len(pre)) if pre and v[i] > 0 else math.nan)

    swing_highs, swing_lows = [], []
    # right-confirmed pivots: the pivot at p is only usable from p+2 onward.
    for p in range(3, n - 3):
        if h[p] == max(h[p - 3:p + 3]) and h[p] > max(h[p - 3:p]) and h[p] >= max(h[p + 1:p + 3]):
            swing_highs.append((p, p + 2, h[p]))
        if l[p] == min(l[p - 3:p + 3]) and l[p] < min(l[p - 3:p]) and l[p] <= min(l[p + 1:p + 3]):
            swing_lows.append((p, p + 2, l[p]))

    low_ptr = high_ptr = 0
    confirmed_lows, confirmed_highs = [], []
    last_ssl = None
    events = []
    for i in range(45, n - 12):
        while low_ptr < len(swing_lows) and swing_lows[low_ptr][1] <= i:
            confirmed_lows.append(swing_lows[low_ptr]); low_ptr += 1
        while high_ptr < len(swing_highs) and swing_highs[high_ptr][1] <= i:
            confirmed_highs.append(swing_highs[high_ptr]); high_ptr += 1
        if not confirmed_lows or not confirmed_highs:
            continue
        # Adaptive DNA: current stock's prior swing rhythm and volatility decide windows.
        prior_swings = sorted([x[0] for x in confirmed_lows[-12:]] + [x[0] for x in confirmed_highs[-12:]])
        gaps = [prior_swings[j] - prior_swings[j - 1] for j in range(1, len(prior_swings)) if prior_swings[j] > prior_swings[j - 1]]
        swing_gap = median(gaps) if gaps else 8
        liq_win = int(max(8, min(80, round(swing_gap * 4))))
        poi_wait = int(max(3, min(20, round(swing_gap * 1.5))))
        recent_low = min(confirmed_lows, key=lambda x: i - x[0] if i >= x[0] else 9999)
        if i - recent_low[0] <= liq_win and l[i] < recent_low[2] and c[i] > recent_low[2]:
            wick_ratio = (min(o[i], c[i]) - l[i]) / max(h[i] - l[i], 1e-9)
            last_ssl = {'bar': i, 'level': recent_low[2], 'wick_ratio': wick_ratio, 'age_window': liq_win}
        # Structure shift / BOS after liquidity: close must break confirmed swing high.
        last_high = max([x for x in confirmed_highs if x[0] < i], key=lambda x: x[0], default=None)
        if not last_ssl or not last_high or i <= last_ssl['bar']:
            continue
        if i - last_ssl['bar'] > liq_win or c[i] <= last_high[2]:
            continue
        body_q = pct_rank(body_pct, i)
        rng_q = pct_rank(rng_pct, i)
        displacement = body_pct[i] >= max(55, body_q['q60'] if not math.isnan(body_q['q60']) else 55)
        big_range = rng_pct[i] >= (rng_q['med'] if not math.isnan(rng_q['med']) else 0)
        if not (c[i] > o[i] and displacement and big_range):
            continue
        # True OB: last bearish candle between SSL and structure break, with non-trivial body.
        ob_i = None
        for k in range(i - 1, max(last_ssl['bar'], i - liq_win) - 1, -1):
            if c[k] < o[k] and body_pct[k] >= 35:
                ob_i = k; break
        if ob_i is None:
            continue
        ob_zl, ob_zh = l[ob_i], max(o[ob_i], c[ob_i])
        if not (ob_zl > 0 and ob_zh > ob_zl):
            continue
        # FVG near displacement. Bullish visible gap: high[t-2] < low[t].
        fvg = None
        for t in range(max(last_ssl['bar'] + 2, i - 3), min(i + 2, n - 2)):
            if h[t - 2] < l[t]:
                fvg = (t, h[t - 2], l[t])
                break
        has_overlap = bool(fvg and max(ob_zl, fvg[1]) <= min(ob_zh, fvg[2]) * 1.005)
        env = 'LOW_VOL' if not math.isnan(rng_q['med']) and rng_q['med'] < 3 else 'HIGH_VOL'
        if not math.isnan(vol_ratio[i]) and vol_ratio[i] >= 1.2:
            env += '_VOLCONF'
        for ri in range(i + 1, min(n - 2, i + poi_wait) + 1):
            touched = l[ri] <= ob_zh * 1.005
            reclaimed = c[ri] >= ob_zh and c[ri] > o[ri] and (c[ri] - l[ri]) / max(h[ri] - l[ri], 1e-9) >= .55
            if not (touched and reclaimed):
                continue
            entry_i = ri + 1
            entry = o[entry_i]
            sl = ob_zl * 0.99
            risk = (entry / sl - 1) * 100 if sl > 0 else 999
            if not (0.8 <= risk <= 12):
                continue
            rep = replay(bars, entry_i, entry, sl)
            if rep is None:
                continue
            pnl, year, reason, t1 = rep
            if year not in YEARS:
                continue
            events.append({
                'symbol': sym, 'entry_i': entry_i, 'entry_date': dates[entry_i], 'year': year,
                'pnl': pnl, 'reason': reason, 't1': t1, 'ssl_age': i - last_ssl['bar'],
                'liq_win': liq_win, 'poi_wait': poi_wait, 'swing_gap': swing_gap,
                'ob_age': i - ob_i, 'reaction_delay': ri - i, 'risk': risk,
                'has_fvg': bool(fvg), 'ob_fvg_overlap': has_overlap, 'env': env,
                'grammar': 'ENV_SSL_SWEEP_TO_BOS_DISPLACE_TRUE_OB_RECLAIM',
            })
            break
    st = {'symbol': sym, 'ok': True, 'bars': n, 'events': len(events)}
    return st, events


def bucket(v: float, cuts: list[float]) -> str:
    for cut in cuts:
        if v <= cut:
            return f'<= {cut:g}'
    return f'> {cuts[-1]:g}'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sorted(KDIR.glob('*_daily_750.json'))
    stock_count = len(paths)
    stats, rows = [], []
    agg = defaultdict(blank)
    seen_global = set()
    for idx, p in enumerate(paths, 1):
        st, evs = scan(p)
        stats.append(st)
        for e in evs:
            rk = (e['symbol'], e['entry_i'])
            if rk in seen_global:
                continue
            seen_global.add(rk)
            rows.append(e)
            keys = [
                ('ALL',),
                ('FVG', e['has_fvg']),
                ('OB_FVG_OVERLAP', e['ob_fvg_overlap']),
                ('ENV', e['env']),
                ('SWING_GAP', bucket(e['swing_gap'], [5, 8, 13, 21])),
                ('SSL_AGE', bucket(e['ssl_age'], [5, 10, 20, 40])),
                ('OB_AGE', bucket(e['ob_age'], [3, 5, 8, 13])),
                ('REACTION_DELAY', bucket(e['reaction_delay'], [1, 2, 3, 5, 8])),
                ('RISK', bucket(e['risk'], [2, 4, 6, 8])),
            ]
            for key in keys:
                add(agg[key], e['pnl'], e['year'], e['reason'], e['t1'])
        if idx % 500 == 0:
            print(f'scanned {idx}/{stock_count} events={len(rows)}', flush=True)
    with (OUT / 'v279_events.csv').open('w', newline='') as fh:
        if rows:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    with (OUT / 'v279_per_stock_counts.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in stats for k in r.keys()}))
        w.writeheader(); w.writerows(stats)
    surfaces = []
    for key, a in agg.items():
        m = metrics(a, stock_count)
        if m['n'] >= 20:
            surfaces.append({'surface': str(key[0]), 'key': '|'.join(map(str, key[1:])), **m})
    surfaces = sorted(surfaces, key=lambda r: (r['wr'], r['avg'], r['n']), reverse=True)
    with (OUT / 'v279_surfaces.csv').open('w', newline='') as fh:
        if surfaces:
            w = csv.DictWriter(fh, fieldnames=list(surfaces[0].keys()))
            w.writeheader(); w.writerows(surfaces)
    summary = {
        'version': 'V279_ADAPTIVE_TEMPORAL_GRAMMAR_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'inputs': {'kline_files': stock_count, 'years': sorted(YEARS)},
        'base_grammar': metrics(agg[('ALL',)], stock_count),
        'top_surfaces': surfaces[:30],
        'largest_surfaces': sorted(surfaces, key=lambda r: (r['n'], r['wr'], r['avg']), reverse=True)[:30],
        'artifacts': {
            'events': str(OUT / 'v279_events.csv'),
            'surfaces': str(OUT / 'v279_surfaces.csv'),
            'per_stock_counts': str(OUT / 'v279_per_stock_counts.csv'),
        },
        'decision': 'NO_PRODUCTION_WRITE__ADAPTIVE_GRAMMAR_RESEARCH_ONLY',
    }
    (OUT / 'v279_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:20000])


if __name__ == '__main__':
    main()
