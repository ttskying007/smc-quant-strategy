#!/usr/bin/env python3
"""V280 no-write layered state grammar audit.

Goal: test whether opportunity scarcity/quality is caused by using one fixed
chronological combo.  Generate multiple SMC story families from the same
right-confirmed primitives, choose family by pre-event regime/DNA, and audit
coverage + quality.  No production/frontend/watchlist writes.
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
OUT = BASE / f'smc_audit/v280_layered_state_grammar_no_write_{TS}'
LATEST = BASE / 'smc_audit/v280_layered_state_grammar_latest.json'
YEARS = {'2023', '2024', '2025', '2026'}


def f(x: Any, d=math.nan) -> float:
    try:
        if x is None or x == '': return d
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
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 't1': 0, 'tp': 0, 'sl': 0, 'time': 0, 'years': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict, row: dict) -> None:
    pnl = float(row['pnl']); year = row['year']; reason = row['reason']
    a['n'] += 1
    a['wins'] += pnl > 0
    a['sum'] += pnl
    a['loss'] += pnl <= 0
    a['micro'] += 0 < pnl < 1
    a['t1'] += bool(row.get('t1'))
    a['tp'] += reason == 'TP'
    a['sl'] += reason == 'SL'
    a['time'] += reason.startswith('TIME')
    a['years'][year][0] += 1
    a['years'][year][1] += pnl > 0
    a['symbols'].add(row['symbol'])


def metrics(a: dict, stock_count: int) -> dict:
    n = a['n']
    if not n: return {'n': 0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items())}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    return {
        'n': int(n), 'wr': round(a['wins'] / n * 100, 4), 'avg': round(a['sum'] / n, 4),
        'loss': int(a['loss']), 'micro': round(a['micro'] / n * 100, 4),
        'min_year_n': min(yc.values()) if yc else 0, 'year_counts': yc, 'year_wr': ywr,
        'all_year_wr_min': round(min(ywr.values()) if ywr else 0, 2),
        'symbols': len(a['symbols']), 'per_stock_3y_all_stocks': round(n / stock_count, 4),
        'tp_pct': round(a['tp'] / n * 100, 2), 'sl_pct': round(a['sl'] / n * 100, 2),
        'time_pct': round(a['time'] / n * 100, 2), 't1': int(a['t1']),
    }


def bucket(v: float, cuts: list[float]) -> str:
    for cut in cuts:
        if v <= cut: return f'<= {cut:g}'
    return f'> {cuts[-1]:g}'


def replay(bars: list[dict], entry_i: int, entry: float, sl: float, rr: float = 1.5, hold: int = 10):
    if entry_i + 1 >= len(bars) or sl <= 0 or entry <= sl: return None
    tp = entry + (entry - sl) * rr
    last = min(len(bars) - 1, entry_i + hold)
    xp, xi, reason = f(bars[last].get('c')), last, f'TIME{hold}'
    for i in range(entry_i + 1, last + 1):  # T+1: exits start after buy day.
        lo, hi = f(bars[i].get('l')), f(bars[i].get('h'))
        if lo <= sl:
            xp, xi, reason = sl, i, 'SL'; break
        if hi >= tp:
            xp, xi, reason = tp, i, 'TP'; break
    return (xp / entry - 1) * 100, ds(bars[entry_i])[:4], reason, ds(bars[xi]) == ds(bars[entry_i])


def quantile(xs: list[float], p: float, default=math.nan) -> float:
    ys = sorted(x for x in xs if not math.isnan(x))
    if not ys: return default
    return ys[min(len(ys) - 1, int((len(ys) - 1) * p))]


def scan(path: Path):
    sym = symbol_from_path(path)
    try:
        bars = json.loads(path.read_text())
    except Exception:
        return {'symbol': sym, 'ok': False}, []
    n = len(bars)
    if n < 140: return {'symbol': sym, 'ok': False, 'bars': n}, []
    dates = [ds(b) for b in bars]
    o = [f(b.get('o')) for b in bars]; h = [f(b.get('h')) for b in bars]
    l = [f(b.get('l')) for b in bars]; c = [f(b.get('c')) for b in bars]
    v = [f(b.get('v'), 0.0) for b in bars]
    body_pct = [abs(c[i] - o[i]) / max(h[i] - l[i], 1e-9) * 100 if h[i] > l[i] else math.nan for i in range(n)]
    rng_pct = [(h[i] / max(l[i], 1e-9) - 1) * 100 if l[i] > 0 else math.nan for i in range(n)]
    vol_ratio = []
    for i in range(n):
        pre = [x for x in v[max(0, i - 20):i] if x > 0]
        vol_ratio.append(v[i] / (sum(pre) / len(pre)) if pre and v[i] > 0 else math.nan)

    swing_highs, swing_lows = [], []
    for p in range(3, n - 3):
        if h[p] == max(h[p - 3:p + 3]) and h[p] > max(h[p - 3:p]) and h[p] >= max(h[p + 1:p + 3]):
            swing_highs.append((p, p + 2, h[p]))
        if l[p] == min(l[p - 3:p + 3]) and l[p] < min(l[p - 3:p]) and l[p] <= min(l[p + 1:p + 3]):
            swing_lows.append((p, p + 2, l[p]))

    low_ptr = high_ptr = 0
    lows, highs, events = [], [], []
    last_ssl = None
    seen = set()

    def emit(i: int, entry_i: int, zl: float, zh: float, family: str, regime: str, info: dict):
        if entry_i >= n: return
        entry = o[entry_i]
        sl = zl * 0.99
        risk = (entry / sl - 1) * 100 if sl > 0 else 999
        if not (0.8 <= risk <= 12): return
        rep = replay(bars, entry_i, entry, sl)
        if rep is None: return
        pnl, year, reason, t1 = rep
        if year not in YEARS: return
        key = (entry_i, family)
        if key in seen: return
        seen.add(key)
        row = {
            'symbol': sym, 'entry_i': entry_i, 'entry_date': dates[entry_i], 'year': year,
            'pnl': pnl, 'reason': reason, 't1': t1, 'family': family, 'regime': regime,
            'risk': risk, 'zone_low': zl, 'zone_high': zh, **info,
        }
        events.append(row)

    for i in range(60, n - 14):
        while low_ptr < len(swing_lows) and swing_lows[low_ptr][1] <= i:
            lows.append(swing_lows[low_ptr]); low_ptr += 1
        while high_ptr < len(swing_highs) and swing_highs[high_ptr][1] <= i:
            highs.append(swing_highs[high_ptr]); high_ptr += 1
        if len(lows) < 2 or len(highs) < 2: continue
        lh1, lh2 = highs[-2], highs[-1]
        ll1, ll2 = lows[-2], lows[-1]
        if lh2[2] > lh1[2] and ll2[2] > ll1[2]: regime = 'UP'
        elif lh2[2] < lh1[2] and ll2[2] < ll1[2]: regime = 'DOWN'
        else: regime = 'RANGE'
        r60 = (max(h[max(0, i - 60):i]) / max(min(l[max(0, i - 60):i]), 1e-9) - 1) * 100
        med_rng = quantile(rng_pct[max(0, i - 80):i], .5, 3)
        vol_env = 'LOW_VOL' if med_rng < 3 else 'HIGH_VOL'
        prior_swings = sorted([x[0] for x in lows[-12:]] + [x[0] for x in highs[-12:]])
        gaps = [prior_swings[j] - prior_swings[j - 1] for j in range(1, len(prior_swings)) if prior_swings[j] > prior_swings[j - 1]]
        swing_gap = median(gaps) if gaps else 8
        liq_win = int(max(8, min(80, round(swing_gap * 4))))
        wait = int(max(3, min(18, round(swing_gap * 1.4))))

        recent_low = min(lows, key=lambda x: i - x[0] if i >= x[0] else 9999)
        if i - recent_low[0] <= liq_win and l[i] < recent_low[2] and c[i] > recent_low[2]:
            last_ssl = {'bar': i, 'level': recent_low[2], 'wick': (min(o[i], c[i]) - l[i]) / max(h[i] - l[i], 1e-9), 'regime': regime}

        last_high = max([x for x in highs if x[0] < i], key=lambda x: x[0], default=None)
        if last_high and c[i] > last_high[2]:
            body_q60 = quantile(body_pct[max(0, i - 80):i], .6, 55)
            displacement = c[i] > o[i] and body_pct[i] >= max(50, body_q60) and rng_pct[i] >= med_rng
            ob_i = None
            for k in range(i - 1, max(0, i - int(liq_win)) - 1, -1):
                if c[k] < o[k] and body_pct[k] >= 30:
                    ob_i = k; break
            if displacement and ob_i is not None and l[ob_i] > 0:
                zl, zh = l[ob_i], max(o[ob_i], c[ob_i])
                for ri in range(i + 1, min(n - 2, i + wait) + 1):
                    touched = l[ri] <= zh * 1.005
                    reclaimed = c[ri] >= zh and c[ri] > o[ri] and (c[ri] - l[ri]) / max(h[ri] - l[ri], 1e-9) >= .55
                    if touched and reclaimed:
                        fam = 'REV_SSL_CHOCH_OB' if last_ssl and 0 < i - last_ssl['bar'] <= liq_win and regime != 'UP' else 'UP_CONT_BOS_OB'
                        emit(i, ri + 1, zl, zh, fam, regime, {
                            'event_i': i, 'poi_i': ob_i, 'reaction_delay': ri - i, 'swing_gap': swing_gap,
                            'liq_age': i - last_ssl['bar'] if last_ssl else 999, 'range60': r60, 'vol_env': vol_env,
                            'vol_ratio': vol_ratio[i], 'displacement': displacement,
                        })
                        break

        # Fast absorption family: SSL sweep then local MSS, without requiring full swing-high BOS.
        if last_ssl and 0 < i - last_ssl['bar'] <= min(8, liq_win) and c[i] > max(h[max(0, i - 5):i]) and c[i] > o[i]:
            ob_i = None
            for k in range(i - 1, last_ssl['bar'] - 1, -1):
                if c[k] < o[k]: ob_i = k; break
            if ob_i is not None:
                zl, zh = l[ob_i], max(o[ob_i], c[ob_i])
                emit(i, i + 1, zl, zh, 'ABSORB_SSL_FAST_MSS', regime, {
                    'event_i': i, 'poi_i': ob_i, 'reaction_delay': 0, 'swing_gap': swing_gap,
                    'liq_age': i - last_ssl['bar'], 'range60': r60, 'vol_env': vol_env, 'vol_ratio': vol_ratio[i],
                    'displacement': body_pct[i] >= 45,
                })

        # Range-low sweep/reclaim: many stocks have opportunities inside range, not only BOS stories.
        if regime == 'RANGE' and r60 <= 35 and last_ssl and last_ssl['bar'] == i and c[i] > o[i]:
            zl, zh = l[i], min(o[i], c[i])
            emit(i, i + 1, zl, zh, 'RANGE_LOW_SWEEP_RECLAIM', regime, {
                'event_i': i, 'poi_i': i, 'reaction_delay': 0, 'swing_gap': swing_gap,
                'liq_age': 0, 'range60': r60, 'vol_env': vol_env, 'vol_ratio': vol_ratio[i],
                'displacement': body_pct[i] >= 35,
            })

    return {'symbol': sym, 'ok': True, 'bars': n, 'events': len(events)}, events


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sorted(KDIR.glob('*_daily_750.json'))
    stock_count = len(paths)
    stats, rows = [], []
    for p in paths:
        st, ev = scan(p)
        stats.append(st); rows.extend(ev)
    rows.sort(key=lambda r: (r['entry_i'], r['symbol'], r['family']))

    aggs = defaultdict(blank)
    for r in rows:
        add(aggs['ALL'], r)
        add(aggs[f"FAMILY::{r['family']}"], r)
        add(aggs[f"REGIME::{r['regime']}"], r)
        add(aggs[f"FAMILY_REGIME::{r['family']}|{r['regime']}"], r)
        add(aggs[f"VOL_ENV::{r['vol_env']}"], r)
        add(aggs[f"RISK::{bucket(float(r['risk']), [2,4,6,8])}"], r)
        add(aggs[f"REACTION::{bucket(float(r['reaction_delay']), [0,1,3,5])}"], r)
        add(aggs[f"LIQ_AGE::{bucket(float(r['liq_age']), [0,3,8,20,40])}"], r)
        add(aggs[f"RANGE60::{bucket(float(r['range60']), [15,25,35,50])}"], r)

    surfaces = []
    for k, a in aggs.items():
        if k == 'ALL': continue
        m = metrics(a, stock_count)
        if m.get('n', 0) >= 50:
            dim, val = k.split('::', 1)
            surfaces.append({'dimension': dim, 'value': val, **m})
    surfaces.sort(key=lambda x: (x['wr'], x['avg'], x['n']), reverse=True)

    per_stock = defaultdict(int)
    per_stock_family = defaultdict(lambda: defaultdict(int))
    for r in rows:
        per_stock[r['symbol']] += 1
        per_stock_family[r['symbol']][r['family']] += 1
    counts = sorted(per_stock.values())
    density = {
        'traded_symbols': len(per_stock), 'all_stocks': stock_count,
        'mean': round(sum(counts) / len(counts), 4) if counts else 0,
        'p25': counts[int((len(counts)-1)*.25)] if counts else 0,
        'p50': counts[int((len(counts)-1)*.50)] if counts else 0,
        'p75': counts[int((len(counts)-1)*.75)] if counts else 0,
        'p90': counts[int((len(counts)-1)*.90)] if counts else 0,
        'max': max(counts) if counts else 0,
    }

    summary = {
        'version': 'V280_LAYERED_STATE_GRAMMAR_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT), 'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'kline_files': stock_count, 'years': sorted(YEARS)},
        'all_layered_events': metrics(aggs['ALL'], stock_count),
        'opportunity_density': density,
        'top_surfaces': surfaces[:80],
        'family_breakdown': [x for x in surfaces if x['dimension'] == 'FAMILY'],
        'family_regime_breakdown': [x for x in surfaces if x['dimension'] == 'FAMILY_REGIME'][:30],
        'artifact_rows': str(OUT / 'v280_events.csv'), 'artifact_surfaces': str(OUT / 'v280_surfaces.csv'),
    }

    with (OUT / 'v280_events.csv').open('w', newline='') as fcsv:
        cols = ['symbol','entry_date','year','family','regime','pnl','reason','risk','zone_low','zone_high','event_i','poi_i','reaction_delay','swing_gap','liq_age','range60','vol_env','vol_ratio','displacement','t1']
        w = csv.DictWriter(fcsv, fieldnames=cols, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    with (OUT / 'v280_surfaces.csv').open('w', newline='') as fcsv:
        cols = ['dimension','value','n','wr','avg','loss','micro','min_year_n','all_year_wr_min','symbols','per_stock_3y_all_stocks','tp_pct','sl_pct','time_pct','t1','year_counts','year_wr']
        w = csv.DictWriter(fcsv, fieldnames=cols, extrasaction='ignore'); w.writeheader(); w.writerows(surfaces)
    (OUT / 'v280_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
