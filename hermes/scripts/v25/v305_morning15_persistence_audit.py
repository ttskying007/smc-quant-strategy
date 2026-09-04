#!/usr/bin/env python3
"""V305 no-write: executable morning 15m persistence + diffusion audit.

V303/V304 showed first/second 15m confirmation and same-window diffusion help only
small pockets. This audit tests the next concrete branch: whether waiting for a
longer executable morning persistence window (first 60m / first 120m) filters fake
same-source 15m lifecycle takeovers. It reads V302 rows + local 15m/industry data
and writes audit artifacts only.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
KDAY = BASE / 'kline_cache'
K15 = BASE / 'kline_cache_15min'
INDUSTRY_JSON = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854' / 'baostock_stock_industry.json'
V302_LATEST = AUDIT / 'v302_15m_same_source_lifecycle_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v305_morning15_persistence_no_write_{TS}'
LATEST = AUDIT / 'v305_morning15_persistence_latest.json'


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


def sym_from_15_path(p: Path) -> str:
    parts = p.name.split('_')
    if len(parts) < 3:
        return ''
    return f'{parts[0]}.{parts[1]}'


def load_industry_map() -> dict[str, str]:
    x = load_json(INDUSTRY_JSON)
    out: dict[str, str] = {}
    if isinstance(x, list):
        for r in x:
            sym = str(r.get('symbol') or '')
            ind = str(r.get('industry') or '').strip() or 'UNKNOWN'
            if sym:
                out[sym] = ind
    return out


def load_day(sym: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if sym in cache:
        return cache[sym]
    rows: list[dict[str, Any]] = []
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
    rows.sort(key=lambda r: str(r.get('t') or ''))
    cache[sym] = rows
    return rows


def day_groups(bars: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    g: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for b in bars:
        d = dn(b.get('d') or b.get('t'))
        if d:
            g[d].append(b)
    for rows in g.values():
        rows.sort(key=lambda r: str(r.get('t') or ''))
    return g


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


def b_up(x: float) -> str:
    return bucket(x, [(45, 'UP<45'), (55, 'UP45_55'), (65, 'UP55_65')], 'UP>=65')


def b_ret(x: float) -> str:
    return bucket(x, [(-0.5, 'RET<-0.5'), (0, 'RET-0.5_0'), (0.5, 'RET0_0.5'), (1.0, 'RET0.5_1')], 'RET>=1')


def b_vr(x: float) -> str:
    return bucket(x, [(0.8, 'VR<0.8'), (1.2, 'VR0.8_1.2'), (2.0, 'VR1.2_2')], 'VR>=2')


def b_rel(x: float) -> str:
    return bucket(x, [(-1, 'REL<-1'), (0, 'REL-1_0'), (1, 'REL0_1')], 'REL>=1')


def b_risk(x: float) -> str:
    return bucket(x, [(3, 'RISK<3'), (5, 'RISK3_5'), (8, 'RISK5_8')], 'RISK>=8')


def b_gap(x: float) -> str:
    return bucket(x, [(-2, 'GAP<-2'), (0, 'GAP-2_0'), (1, 'GAP0_1'), (3, 'GAP1_3')], 'GAP>=3')


def symbol_morning_features(p: Path, need_dates: set[str]) -> dict[str, dict[str, Any]]:
    sym = sym_from_15_path(p)
    if not sym:
        return {}
    x = load_json(p)
    if not isinstance(x, list):
        return {}
    groups = day_groups(x)
    dates = sorted(groups)
    first4_amt: dict[str, float] = {}
    first8_amt: dict[str, float] = {}
    raw: dict[str, dict[str, Any]] = {}
    for d in dates:
        rows = groups[d]
        if len(rows) < 8:
            continue
        o0 = sf(rows[0].get('o'))
        if o0 <= 0:
            continue
        def feat(k: int) -> tuple[float, float, float, float, bool]:
            part = rows[:k]
            close = sf(part[-1].get('c'))
            low = min(sf(b.get('l')) for b in part)
            high = max(sf(b.get('h')) for b in part)
            amt = sum(sf(b.get('v'), 0.0) * sf(b.get('c'), 0.0) for b in part)
            green = close >= o0
            return close, low, high, amt, green
        c4, l4, h4, a4, g4 = feat(4)
        c8, l8, h8, a8, g8 = feat(8)
        if min(c4, l4, h4, c8, l8, h8) <= 0:
            continue
        first4_amt[d] = a4
        first8_amt[d] = a8
        raw[d] = {
            'symbol': sym, 'date': d,
            'm60_ret': (c4 / o0 - 1) * 100,
            'm60_low_dd': (l4 / o0 - 1) * 100,
            'm60_push': (h4 / o0 - 1) * 100,
            'm60_green': g4,
            'm60_amt': a4,
            'm120_ret': (c8 / o0 - 1) * 100,
            'm120_low_dd': (l8 / o0 - 1) * 100,
            'm120_push': (h8 / o0 - 1) * 100,
            'm120_green': g8,
            'm120_amt': a8,
        }
    out: dict[str, dict[str, Any]] = {}
    for i, d in enumerate(dates):
        if d not in need_dates or d not in raw:
            continue
        prev4 = [first4_amt[x] for x in dates[max(0, i - 5):i] if x in first4_amt and first4_amt[x] > 0]
        prev8 = [first8_amt[x] for x in dates[max(0, i - 5):i] if x in first8_amt and first8_amt[x] > 0]
        r = dict(raw[d])
        b4 = sum(prev4) / len(prev4) if prev4 else math.nan
        b8 = sum(prev8) / len(prev8) if prev8 else math.nan
        r['m60_amt_vr'] = r['m60_amt'] / b4 if b4 and not math.isnan(b4) else math.nan
        r['m120_amt_vr'] = r['m120_amt'] / b8 if b8 and not math.isnan(b8) else math.nan
        out[d] = r
    return out


def build_market_features(need_dates: set[str], industry_map: dict[str, str]) -> dict[tuple[str, str], dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in K15.glob('*_15min_800.json'):
        for d, f in symbol_morning_features(p, need_dates).items():
            f['industry'] = industry_map.get(f['symbol'], 'UNKNOWN')
            by_date[d].append(f)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for d, feats in by_date.items():
        if not feats:
            continue
        for horizon in ('m60', 'm120'):
            rets = [sf(f[f'{horizon}_ret']) for f in feats if not math.isnan(sf(f[f'{horizon}_ret']))]
            if not rets:
                continue
            m_up = sum(1 for x in rets if x > 0) / len(rets) * 100
            m_med = median(rets)
            ind_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for f in feats:
                ind_groups[str(f.get('industry') or 'UNKNOWN')].append(f)
            for f in feats:
                sym = f['symbol']; ind = str(f.get('industry') or 'UNKNOWN')
                peers = ind_groups[ind]
                prets = [sf(x[f'{horizon}_ret']) for x in peers if not math.isnan(sf(x[f'{horizon}_ret']))]
                pvrs = [sf(x[f'{horizon}_amt_vr']) for x in peers if not math.isnan(sf(x[f'{horizon}_amt_vr']))]
                i_up = sum(1 for x in prets if x > 0) / len(prets) * 100 if prets else math.nan
                i_med = median(prets) if prets else math.nan
                i_vr = median(pvrs) if pvrs else math.nan
                s_ret = sf(f[f'{horizon}_ret'])
                out[(sym, f'{d}_{horizon}')] = {
                    f'{horizon}_m_up': m_up,
                    f'{horizon}_m_ret': m_med,
                    f'{horizon}_i_up': i_up,
                    f'{horizon}_i_ret': i_med,
                    f'{horizon}_i_vr': i_vr,
                    f'{horizon}_s_ret': s_ret,
                    f'{horizon}_s_rel': s_ret - i_med if not math.isnan(i_med) and not math.isnan(s_ret) else math.nan,
                    f'{horizon}_s_vr': sf(f[f'{horizon}_amt_vr']),
                    f'{horizon}_low_dd': sf(f[f'{horizon}_low_dd']),
                    f'{horizon}_push': sf(f[f'{horizon}_push']),
                }
    return out


def entry_candidates(row: dict[str, Any], day15: list[dict[str, Any]], day_open: float) -> list[dict[str, Any]]:
    if len(day15) < 9 or day_open <= 0:
        return []
    acc_hi, acc_lo, sl = sf(row['acc_hi']), sf(row['acc_lo']), sf(row['sl'])
    if min(acc_hi, acc_lo, sl) <= 0:
        return []
    out: list[dict[str, Any]] = []

    def span(k: int) -> tuple[float, float, float, float]:
        part = day15[:k]
        c = sf(part[-1].get('c'))
        lo = min(sf(b.get('l')) for b in part)
        hi = max(sf(b.get('h')) for b in part)
        nxt = sf(day15[k].get('o')) if len(day15) > k else c
        return c, lo, hi, nxt

    def add_mode(mode: str, horizon: str, k: int, ok: bool, obs_close: float, obs_low: float, obs_high: float, entry: float) -> None:
        if not ok or not (entry > sl > 0):
            return
        risk = (entry / sl - 1) * 100
        if math.isnan(risk) or risk <= 0 or risk > 20:
            return
        gap_acc = (day_open / acc_hi - 1) * 100 if acc_hi > 0 else math.nan
        obs_dd = (obs_low / entry - 1) * 100 if entry > 0 else math.nan
        push = (obs_high / day_open - 1) * 100 if day_open > 0 else math.nan
        out.append({
            'entry_mode': mode,
            'horizon': horizon,
            'entry_bar_no': k + 1,
            'entry_price': entry,
            'obs_close': obs_close,
            'obs_dd_pct': obs_dd,
            'obs_push_pct': push,
            'risk_pct2': risk,
            'open_bucket': b_gap(gap_acc),
            'risk2_bucket': b_risk(risk),
            'dd_bucket': bucket(obs_dd, [(-5, 'DD<-5'), (-2, 'DD-5_-2'), (-0.5, 'DD-2_-0.5'), (0, 'DD-0.5_0')], 'DD>=0'),
            'push_bucket': bucket(push, [(0, 'PUSH<0'), (1, 'PUSH0_1'), (3, 'PUSH1_3'), (6, 'PUSH3_6')], 'PUSH>=6'),
        })

    c4, l4, h4, e4 = span(4)
    c8, l8, h8, e8 = span(8)
    add_mode('MORNING60_HOLD', 'm60', 4, l4 > sl and c4 > acc_lo and c4 >= day_open, c4, l4, h4, e4)
    add_mode('MORNING60_TAKEOVER', 'm60', 4, l4 > acc_lo and c4 > acc_hi and c4 >= day_open, c4, l4, h4, e4)
    add_mode('MORNING120_PERSIST', 'm120', 8, l8 > acc_lo * 0.995 and c8 > max(acc_hi, day_open), c8, l8, h8, e8)
    add_mode('MORNING120_NO_FADE', 'm120', 8, l8 > sl and c8 > c4 * 0.995 and c8 > day_open, c8, l8, h8, e8)
    return out


def blank() -> dict[str, Any]:
    return {'n': 0, 'win': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 'tp': 0, 'sl': 0, 'gap': 0, 'time': 0, 'symbols': set(), 'mc': defaultdict(int), 'mw': defaultdict(int), 't1': 0}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'))
    a['n'] += 1; a['sum'] += pnl; a['symbols'].add(r['symbol'])
    if pnl > 0:
        a['win'] += 1; a['mw'][r['month']] += 1
    else:
        a['loss'] += 1
    if 0 < abs(pnl) < 0.6:
        a['micro'] += 1
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
        'min_month_n': min(a['mc'].values()) if a['mc'] else 0,
        'min_month_wr': min(mwr.values()) if mwr else None,
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
        h = r['horizon']
        combos = [
            f"mode={r['entry_mode']}",
            f"mode={r['entry_mode']}|risk={r['risk2_bucket']}",
            f"mode={r['entry_mode']}|mup={r[f'{h}_mup_bucket']}|iup={r[f'{h}_iup_bucket']}",
            f"mode={r['entry_mode']}|sret={r[f'{h}_sret_bucket']}|rel={r[f'{h}_srel_bucket']}",
            f"mode={r['entry_mode']}|ivr={r[f'{h}_ivr_bucket']}|svr={r[f'{h}_svr_bucket']}",
            f"mode={r['entry_mode']}|risk={r['risk2_bucket']}|mup={r[f'{h}_mup_bucket']}|iup={r[f'{h}_iup_bucket']}",
            f"mode={r['entry_mode']}|risk={r['risk2_bucket']}|sret={r[f'{h}_sret_bucket']}|rel={r[f'{h}_srel_bucket']}",
            f"mode={r['entry_mode']}|risk={r['risk2_bucket']}|ivr={r[f'{h}_ivr_bucket']}|svr={r[f'{h}_svr_bucket']}",
            f"mode={r['entry_mode']}|open={r['open_bucket']}|risk={r['risk2_bucket']}|iup={r[f'{h}_iup_bucket']}|svr={r[f'{h}_svr_bucket']}",
            f"mode={r['entry_mode']}|dd={r['dd_bucket']}|push={r['push_bucket']}|iup={r[f'{h}_iup_bucket']}|rel={r[f'{h}_srel_bucket']}",
        ]
        for c in combos:
            add(groups[c], r)
    out: list[dict[str, Any]] = []
    for name, a in groups.items():
        m = finalize(a)
        if m.get('n', 0) >= 80:
            m['variant'] = name
            out.append(m)
    out.sort(key=lambda x: (x.get('min_month_wr') or 0, x.get('wr') or 0, x.get('avg') or -999, x.get('n') or 0), reverse=True)
    return out[:60]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v302 = load_json(V302_LATEST) or {}
    source_rows = Path(v302.get('artifacts', {}).get('rows', ''))
    if not source_rows.exists():
        raise SystemExit(f'missing V302 rows: {source_rows}')

    source: list[dict[str, Any]] = []
    need_dates: set[str] = set()
    with source_rows.open() as fh:
        for r in csv.DictReader(fh):
            source.append(r)
            d = str(r.get('entry_date') or '')[:8]
            if d:
                need_dates.add(d)

    industry_map = load_industry_map()
    market_features = build_market_features(need_dates, industry_map)
    day_cache: dict[str, list[dict[str, Any]]] = {}
    m15_cache: dict[str, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    source_count = 0; no15 = 0; no_daily = 0; no_feature = 0

    for r in source:
        source_count += 1
        sym = r['symbol']; entry_date = str(r.get('entry_date') or '')[:8]
        daily = load_day(sym, day_cache)
        if not daily:
            no_daily += 1; continue
        day15 = bars_on_date(load15(sym, m15_cache), entry_date)
        if len(day15) < 9:
            no15 += 1; continue
        day_open = sf(day15[0].get('o'))
        for cand in entry_candidates(r, day15, day_open):
            h = cand['horizon']
            feat = market_features.get((sym, f'{entry_date}_{h}'))
            if not feat:
                no_feature += 1; continue
            rep = replay_t1_daily(daily, entry_date, cand['entry_price'], sf(r['sl']))
            if not rep:
                continue
            out = dict(r)
            out.update(cand)
            out.update(rep)
            out['entry_date'] = entry_date
            out['month'] = entry_date[:6]
            out['t1_violation'] = rep['exit_date'] == entry_date
            for k, v in feat.items():
                out[k] = v
            out[f'{h}_mup_bucket'] = b_up(sf(feat[f'{h}_m_up']))
            out[f'{h}_iup_bucket'] = b_up(sf(feat[f'{h}_i_up']))
            out[f'{h}_mret_bucket'] = b_ret(sf(feat[f'{h}_m_ret']))
            out[f'{h}_iret_bucket'] = b_ret(sf(feat[f'{h}_i_ret']))
            out[f'{h}_sret_bucket'] = b_ret(sf(feat[f'{h}_s_ret']))
            out[f'{h}_srel_bucket'] = b_rel(sf(feat[f'{h}_s_rel']))
            out[f'{h}_ivr_bucket'] = b_vr(sf(feat[f'{h}_i_vr']))
            out[f'{h}_svr_bucket'] = b_vr(sf(feat[f'{h}_s_vr']))
            rows.append(out)

    rows_path = OUT / 'v305_rows.csv'
    fields = sorted({k for r in rows for k in r.keys()})
    with rows_path.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(rows)

    mode_metrics: dict[str, Any] = {}
    for mode in sorted({r['entry_mode'] for r in rows}):
        mode_metrics[mode] = metrics([r for r in rows if r['entry_mode'] == mode])
    horizon_metrics: dict[str, Any] = {}
    for h in sorted({r['horizon'] for r in rows}):
        horizon_metrics[h] = metrics([r for r in rows if r['horizon'] == h])

    summary = {
        'version': 'V305_MORNING15_PERSISTENCE_NO_WRITE',
        'created_at': TS,
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'hypothesis': 'Longer executable first60/first120 15m persistence plus market/industry/amount diffusion can filter fake V302 takeovers better than first/second 15m only.',
        'source': {'v302_latest': str(V302_LATEST), 'v302_rows': str(source_rows)},
        'inputs': {
            'v302_rows': source_count,
            'needed_entry_dates': len(need_dates),
            'k15_files': len(list(K15.glob('*_15min_800.json'))),
            'market_feature_keys': len(market_features),
            'industry_mapped_symbols': len(industry_map),
            'no_daily': no_daily,
            'no15': no15,
            'no_feature': no_feature,
        },
        'coverage': {'rows': len(rows), 'symbols': len({r['symbol'] for r in rows}), 't1_violations': sum(1 for r in rows if r['t1_violation'])},
        'baseline': metrics(rows),
        'mode_metrics': mode_metrics,
        'horizon_metrics': horizon_metrics,
        'top_variants': top_variants(rows),
        'artifacts': {'dir': str(OUT), 'rows': str(rows_path)},
    }
    summary_path = OUT / 'v305_summary.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:5000])


if __name__ == '__main__':
    main()
