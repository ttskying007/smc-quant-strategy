#!/usr/bin/env python3
"""V309 no-write: scanner-time intraday continuation module audit.

V308 proved daily opening breadth is only a weak proxy; V307 proved recent
first120 industry leadership transmission is strong but not production-safe due
short 15m coverage. This script tests the next concrete scanner-time module:

  opening/industry state -> wait first 15/30/60/120m -> industry continuation
  + candidate same-source POI lifecycle -> executable intraday entry -> T+1 replay

It writes audit artifacts only. No production/frontend/watchlist writes.
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
V306_LATEST = AUDIT / 'v306_opening_gap_source_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v309_scanner_time_intraday_continuation_no_write_{TS}'
LATEST = AUDIT / 'v309_scanner_time_intraday_continuation_latest.json'

HORIZONS = {1: 'm15', 2: 'm30', 4: 'm60', 8: 'm120'}


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
    return bucket(x, [(45, 'UP<45'), (55, 'UP45_55'), (65, 'UP55_65'), (75, 'UP65_75')], 'UP>=75')


def b_ret(x: float) -> str:
    return bucket(x, [(-1, 'RET<-1'), (0, 'RET-1_0'), (0.5, 'RET0_0.5'), (1, 'RET0.5_1'), (2, 'RET1_2')], 'RET>=2')


def b_vr(x: float) -> str:
    return bucket(x, [(0.8, 'VR<0.8'), (1.2, 'VR0.8_1.2'), (2.0, 'VR1.2_2')], 'VR>=2')


def b_rel(x: float) -> str:
    return bucket(x, [(-1, 'REL<-1'), (0, 'REL-1_0'), (1, 'REL0_1')], 'REL>=1')


def b_risk(x: float) -> str:
    return bucket(x, [(3, 'RISK<3'), (5, 'RISK3_5'), (8, 'RISK5_8')], 'RISK>=8')


def b_dd(x: float) -> str:
    return bucket(x, [(-5, 'DD<-5'), (-2, 'DD-5_-2'), (-0.5, 'DD-2_-0.5'), (0, 'DD-0.5_0')], 'DD>=0')


def b_push(x: float) -> str:
    return bucket(x, [(0, 'PUSH<0'), (1, 'PUSH0_1'), (3, 'PUSH1_3'), (6, 'PUSH3_6')], 'PUSH>=6')


def b_rank(x: float) -> str:
    return bucket(x, [(20, 'TOP20'), (40, 'TOP20_40'), (60, 'MID40_60'), (80, 'LOW60_80')], 'LOW80_100')


def symbol_intraday_features(p: Path, need_dates: set[str]) -> dict[str, dict[str, Any]]:
    sym = sym_from_15_path(p)
    if not sym:
        return {}
    x = load_json(p)
    if not isinstance(x, list):
        return {}
    groups = day_groups(x)
    dates = sorted(groups)
    raw: dict[str, dict[str, Any]] = {}
    amt_hist: dict[str, dict[str, float]] = {h: {} for h in HORIZONS.values()}
    for d in dates:
        rows = groups[d]
        if len(rows) < 9:
            continue
        o0 = sf(rows[0].get('o'))
        if o0 <= 0:
            continue
        feat: dict[str, Any] = {'symbol': sym, 'date': d}
        ok = True
        for k, hname in HORIZONS.items():
            part = rows[:k]
            close = sf(part[-1].get('c'))
            low = min(sf(b.get('l')) for b in part)
            high = max(sf(b.get('h')) for b in part)
            entry_next = sf(rows[k].get('o')) if len(rows) > k else close
            amt = sum(sf(b.get('v'), 0.0) * sf(b.get('c'), 0.0) for b in part)
            if min(close, low, high, entry_next) <= 0:
                ok = False
                break
            feat[f'{hname}_ret'] = (close / o0 - 1) * 100
            feat[f'{hname}_low_dd'] = (low / o0 - 1) * 100
            feat[f'{hname}_push'] = (high / o0 - 1) * 100
            feat[f'{hname}_amt'] = amt
            feat[f'{hname}_entry_next'] = entry_next
            amt_hist[hname][d] = amt
        if ok:
            raw[d] = feat
    out: dict[str, dict[str, Any]] = {}
    for i, d in enumerate(dates):
        if d not in need_dates or d not in raw:
            continue
        r = dict(raw[d])
        for hname in HORIZONS.values():
            prev = [amt_hist[hname][x] for x in dates[max(0, i - 5):i] if x in amt_hist[hname] and amt_hist[hname][x] > 0]
            base = sum(prev) / len(prev) if prev else math.nan
            r[f'{hname}_amt_vr'] = r[f'{hname}_amt'] / base if base and not math.isnan(base) else math.nan
        out[d] = r
    return out


def build_features(need_dates: set[str], industry_map: dict[str, str]) -> dict[tuple[str, str], dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in K15.glob('*_15min_800.json'):
        for d, f in symbol_intraday_features(p, need_dates).items():
            f['industry'] = industry_map.get(f['symbol'], 'UNKNOWN')
            by_date[d].append(f)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for d, feats in by_date.items():
        ind_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in feats:
            ind_groups[str(f.get('industry') or 'UNKNOWN')].append(f)
        for hname in HORIZONS.values():
            all_rets = [sf(f[f'{hname}_ret']) for f in feats if not math.isnan(sf(f[f'{hname}_ret']))]
            if not all_rets:
                continue
            m_up = 100 * sum(x > 0 for x in all_rets) / len(all_rets)
            m_ret = median(all_rets)
            industry_feats: list[dict[str, Any]] = []
            for ind, peers in ind_groups.items():
                prets = [sf(x[f'{hname}_ret']) for x in peers if not math.isnan(sf(x[f'{hname}_ret']))]
                pvrs = [sf(x[f'{hname}_amt_vr']) for x in peers if not math.isnan(sf(x[f'{hname}_amt_vr']))]
                if len(prets) < 5:
                    continue
                industry_feats.append({
                    'industry': ind,
                    'i_ret': median(prets),
                    'i_up': 100 * sum(x > 0 for x in prets) / len(prets),
                    'i_hot': 100 * sum(x >= 1 for x in prets) / len(prets),
                    'i_vr': median(pvrs) if pvrs else math.nan,
                })
            ret_sorted = sorted(industry_feats, key=lambda x: x['i_ret'], reverse=True)
            up_sorted = sorted(industry_feats, key=lambda x: x['i_up'], reverse=True)
            n_ind = len(industry_feats)
            rank_map: dict[str, dict[str, float]] = defaultdict(dict)
            for rank, f in enumerate(ret_sorted, 1):
                rank_map[f['industry']]['ret_rank_pct'] = 100 * rank / n_ind if n_ind else math.nan
            for rank, f in enumerate(up_sorted, 1):
                rank_map[f['industry']]['up_rank_pct'] = 100 * rank / n_ind if n_ind else math.nan
            ind_by_name = {f['industry']: f for f in industry_feats}
            for f in feats:
                sym = f['symbol']; ind = str(f.get('industry') or 'UNKNOWN')
                inf = ind_by_name.get(ind)
                if not inf:
                    continue
                s_ret = sf(f[f'{hname}_ret'])
                key = (sym, f'{d}_{hname}')
                out[key] = {
                    f'{hname}_m_up': m_up,
                    f'{hname}_m_ret': m_ret,
                    f'{hname}_i_up': inf['i_up'],
                    f'{hname}_i_ret': inf['i_ret'],
                    f'{hname}_i_hot': inf['i_hot'],
                    f'{hname}_i_vr': inf['i_vr'],
                    f'{hname}_i_ret_rank_pct': rank_map[ind].get('ret_rank_pct', math.nan),
                    f'{hname}_i_up_rank_pct': rank_map[ind].get('up_rank_pct', math.nan),
                    f'{hname}_s_ret': s_ret,
                    f'{hname}_s_rel': s_ret - inf['i_ret'] if not math.isnan(s_ret) and not math.isnan(inf['i_ret']) else math.nan,
                    f'{hname}_s_vr': sf(f[f'{hname}_amt_vr']),
                    f'{hname}_low_dd': sf(f[f'{hname}_low_dd']),
                    f'{hname}_push': sf(f[f'{hname}_push']),
                    f'{hname}_entry_next': sf(f[f'{hname}_entry_next']),
                }
    return out


def entry_variants(row: dict[str, Any], day15: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(day15) < 9:
        return []
    day_open = sf(day15[0].get('o'))
    acc_hi, acc_lo, sl = sf(row.get('acc_hi')), sf(row.get('acc_lo')), sf(row.get('sl'))
    if min(day_open, acc_hi, acc_lo, sl) <= 0:
        return []
    out: list[dict[str, Any]] = []
    for k, hname in HORIZONS.items():
        part = day15[:k]
        close = sf(part[-1].get('c'))
        low = min(sf(b.get('l')) for b in part)
        high = max(sf(b.get('h')) for b in part)
        entry = sf(day15[k].get('o')) if len(day15) > k else close
        if not (entry > sl > 0):
            continue
        risk = (entry / sl - 1) * 100
        if risk <= 0 or risk > 20:
            continue
        base = {
            'horizon': hname,
            'wait_bars': k,
            'entry_price': entry,
            'obs_close': close,
            'obs_low': low,
            'obs_high': high,
            'risk_pct2': risk,
            'risk2_bucket': b_risk(risk),
            'dd_bucket': b_dd((low / entry - 1) * 100),
            'push_bucket': b_push((high / day_open - 1) * 100),
        }
        checks = {
            'CONT_NO_FADE': low > sl and close >= day_open,
            'HOLD_ZONE': low > acc_lo * 0.995 and close >= day_open,
            'TAKEOVER': low > acc_lo * 0.995 and close > acc_hi and close >= day_open,
            'STRONG_TAKEOVER': low > acc_lo and close > acc_hi and close > day_open * 1.005,
        }
        for mode, ok in checks.items():
            if ok:
                rr = dict(base)
                rr['entry_mode'] = mode
                out.append(rr)
    return out


def blank() -> dict[str, Any]:
    return {'n': 0, 'win': 0, 'sum': 0.0, 'loss': 0, 'micro': 0, 'tp': 0, 'sl': 0, 'gap': 0, 'time': 0, 'symbols': set(), 'mc': defaultdict(int), 'mw': defaultdict(int), 't1': 0}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'))
    a['n'] += 1; a['sum'] += pnl; a['symbols'].add(str(r.get('symbol') or ''))
    if pnl > 0:
        a['win'] += 1; a['mw'][str(r.get('month') or '')] += 1
    else:
        a['loss'] += 1
    if 0 < abs(pnl) < 0.6:
        a['micro'] += 1
    reason = str(r.get('reason') or '')
    if reason == 'TP': a['tp'] += 1
    elif reason == 'SL': a['sl'] += 1
    elif reason == 'GAP_SL': a['gap'] += 1
    elif reason.startswith('TIME'): a['time'] += 1
    a['mc'][str(r.get('month') or '')] += 1
    if str(r.get('t1_violation')).lower() == 'true':
        a['t1'] += 1


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
        leader = r[f'{h}_leader_state']
        combos = [
            f"h={h}|mode={r['entry_mode']}",
            f"h={h}|mode={r['entry_mode']}|leader={leader}",
            f"h={h}|mode={r['entry_mode']}|trans={r[f'{h}_leader_transmission']}",
            f"h={h}|mode={r['entry_mode']}|trans={r[f'{h}_leader_transmission']}|risk={r['risk2_bucket']}",
            f"h={h}|mode={r['entry_mode']}|iup={r[f'{h}_iup_bucket']}|mup={r[f'{h}_mup_bucket']}|rel={r[f'{h}_srel_bucket']}",
            f"h={h}|mode={r['entry_mode']}|trans={r[f'{h}_leader_transmission']}|gap={r.get('gap_source')}|risk={r['risk2_bucket']}",
            f"h={h}|mode={r['entry_mode']}|trans={r[f'{h}_leader_transmission']}|acc={r.get('acc_bucket')}|sweep={r.get('sweep_bucket')}",
            f"h={h}|mode={r['entry_mode']}|irank={r[f'{h}_irank_bucket']}|urank={r[f'{h}_urank_bucket']}|part={r[f'{h}_candidate_participation']}",
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
    return out[:80]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v306 = load_json(V306_LATEST) or {}
    source_rows = Path(v306.get('artifacts', {}).get('rows', ''))
    if not source_rows.exists():
        raise SystemExit(f'missing V306 rows: {source_rows}')
    source: list[dict[str, Any]] = []
    need_dates: set[str] = set()
    with source_rows.open() as fh:
        for r in csv.DictReader(fh):
            if str(r.get('t1_violation')).lower() == 'true':
                continue
            source.append(dict(r))
            d = dn(r.get('entry_date'))
            if d:
                need_dates.add(d)

    industry_map = load_industry_map()
    features = build_features(need_dates, industry_map)
    day_cache: dict[str, list[dict[str, Any]]] = {}
    m15_cache: dict[str, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    no_daily = no15 = no_feature = no_replay = 0

    for r in source:
        sym = str(r.get('symbol') or '')
        d = dn(r.get('entry_date'))
        daily = load_day(sym, day_cache)
        if not daily:
            no_daily += 1; continue
        day15 = bars_on_date(load15(sym, m15_cache), d)
        if len(day15) < 9:
            no15 += 1; continue
        for ev in entry_variants(r, day15):
            h = ev['horizon']
            feat = features.get((sym, f'{d}_{h}'))
            if not feat:
                no_feature += 1; continue
            rep = replay_t1_daily(daily, d, sf(ev['entry_price']), sf(r.get('sl')))
            if not rep:
                no_replay += 1; continue
            out = dict(r)
            out.update(ev)
            out.update(rep)
            out['entry_date'] = d
            out['month'] = d[:6]
            out['t1_violation'] = rep['exit_date'] == d
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
            out[f'{h}_irank_bucket'] = b_rank(sf(feat[f'{h}_i_ret_rank_pct']))
            out[f'{h}_urank_bucket'] = b_rank(sf(feat[f'{h}_i_up_rank_pct']))
            leader = sf(feat[f'{h}_i_ret_rank_pct']) <= 20 or sf(feat[f'{h}_i_up_rank_pct']) <= 20
            out[f'{h}_leader_state'] = 'LEADER_TOP20' if leader else ('LEADER_TOP40' if sf(feat[f'{h}_i_ret_rank_pct']) <= 40 or sf(feat[f'{h}_i_up_rank_pct']) <= 40 else 'NON_LEADER')
            participate = sf(feat[f'{h}_s_ret']) >= 0 and sf(feat[f'{h}_s_rel']) >= -0.5 and sf(feat[f'{h}_low_dd']) > -1.5
            out[f'{h}_candidate_participation'] = 'PARTICIPATE' if participate else 'FADE_OR_LAG'
            out[f'{h}_leader_transmission'] = f"{out[f'{h}_leader_state']}|{out[f'{h}_candidate_participation']}"
            rows.append(out)

    rows_path = OUT / 'v309_rows.csv'
    fields = sorted({k for r in rows for k in r.keys()})
    with rows_path.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(rows)

    mode_metrics = {m: metrics([r for r in rows if r['entry_mode'] == m]) for m in sorted({r['entry_mode'] for r in rows})}
    horizon_metrics = {h: metrics([r for r in rows if r['horizon'] == h]) for h in sorted({r['horizon'] for r in rows})}
    summary = {
        'version': 'V309_SCANNER_TIME_INTRADAY_CONTINUATION_NO_WRITE',
        'created_at': TS,
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'hypothesis': 'Scanner-time first15/30/60/120 industry continuation plus candidate POI lifecycle can improve V306/V307 beyond daily opening proxy.',
        'source': {'v306_latest': str(V306_LATEST), 'v306_rows': str(source_rows)},
        'inputs': {
            'v306_rows': len(source),
            'needed_entry_dates': len(need_dates),
            'k15_files': len(list(K15.glob('*_15min_800.json'))),
            'feature_keys': len(features),
            'industry_mapped_symbols': len(industry_map),
            'no_daily': no_daily,
            'no15': no15,
            'no_feature': no_feature,
            'no_replay': no_replay,
        },
        'coverage': {'rows': len(rows), 'symbols': len({r['symbol'] for r in rows}), 't1_violations': sum(1 for r in rows if r['t1_violation'])},
        'baseline': metrics(rows),
        'mode_metrics': mode_metrics,
        'horizon_metrics': horizon_metrics,
        'top_variants': top_variants(rows),
        'artifacts': {'dir': str(OUT), 'rows': str(rows_path), 'summary': str(OUT / 'v309_summary.json')},
    }
    (OUT / 'v309_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'coverage': summary['coverage'], 'baseline': summary['baseline'], 'best': summary['top_variants'][0] if summary['top_variants'] else None}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
