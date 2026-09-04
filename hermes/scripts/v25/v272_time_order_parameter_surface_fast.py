#!/usr/bin/env python3
"""V272 no-write: fast time-ordered SMC sequence parameter surface.

Same research purpose as V271, but aggregates online instead of materializing every
candidate row. It quantifies whether low volume comes from chronological combo
parameters: BOS lookback, demand lookback, retest wait, reclaim strictness, and
prior-SSL prerequisite.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
KLINE_DIR = BASE / 'kline_cache'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v272_time_order_parameter_surface_fast_no_write_{TS}'
LATEST = BASE / 'smc_audit/v272_time_order_parameter_surface_fast_latest.json'

BOS_LBS = [10, 20, 40]
DEMAND_LBS = [3, 5, 8, 12]
WAITS = [3, 5, 8, 12, 20]
MODES = ['strict_v262', 'soft_mid', 'touch_bull', 'support_hold']
SSL_WINS = [10, 20, 40]
PROD = dict(n=600, min_year_n=70, wr=94.0, avg=7.6, year_wr_min=92.0, micro=1.0, weak_month_count=6, t1=0)
RESEARCH = dict(n=590, min_year_n=70, wr=93.5, avg=7.5, year_wr_min=91.0, micro=1.0, weak_month_count=8, t1=0)


def fnum(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def date_s(b: dict[str, Any]) -> str:
    return str(b.get('t', b.get('date', ''))).replace('.0', '')[:8]


def symbol_from_path(p: Path) -> str:
    s = p.stem.replace('_daily_750', '')
    code, exch = s.split('_', 1)
    return f'{code}.{exch}'


class Agg:
    __slots__ = ('n','wins','sum','loss','micro','t1','years','ywins','months','msum','mwins','mloss')
    def __init__(self) -> None:
        self.n = self.wins = self.loss = self.micro = self.t1 = 0
        self.sum = 0.0
        self.years = defaultdict(int); self.ywins = defaultdict(int)
        self.months = defaultdict(int); self.msum = defaultdict(float); self.mwins = defaultdict(int); self.mloss = defaultdict(int)
    def add(self, date: str, pnl: float, t1: bool = False) -> None:
        self.n += 1; self.sum += pnl
        win = pnl > 0
        if win: self.wins += 1
        else: self.loss += 1
        if 0 < pnl < 1: self.micro += 1
        if t1: self.t1 += 1
        y = date[:4]; m = date[:6]
        self.years[y] += 1; self.months[m] += 1; self.msum[m] += pnl
        if win: self.ywins[y] += 1; self.mwins[m] += 1
        else: self.mloss[m] += 1
    def metrics(self) -> dict[str, Any]:
        if self.n == 0: return {'n': 0}
        ywr = {y: round(self.ywins[y] / c * 100, 2) for y, c in sorted(self.years.items())}
        weak = []
        for m, c in sorted(self.months.items()):
            if c >= 10:
                wr = self.mwins[m] / c * 100
                avg = self.msum[m] / c
                if wr < 90 or avg < 5.5:
                    weak.append({'period': m, 'n': c, 'wr': round(wr, 2), 'avg': round(avg, 4), 'loss': self.mloss[m]})
        return {
            'n': self.n,
            'wr': round(self.wins / self.n * 100, 4),
            'avg': round(self.sum / self.n, 4),
            'loss': self.loss,
            'min_year_n': min(self.years.values()) if self.years else 0,
            'year_counts': dict(sorted(self.years.items())),
            'year_wr': ywr,
            'all_year_wr_min': round(min(ywr.values()) if ywr else 0, 2),
            'micro': round(self.micro / self.n * 100, 4),
            'weak_month_count': len(weak),
            'weak_months': weak[:12],
            't1': self.t1,
        }


def pass_gate(m: dict[str, Any], g: dict[str, float]) -> bool:
    return (m.get('n',0)>=g['n'] and m.get('min_year_n',0)>=g['min_year_n'] and m.get('wr',0)>=g['wr']
            and m.get('avg',0)>=g['avg'] and m.get('all_year_wr_min',0)>=g['year_wr_min']
            and m.get('micro',99)<=g['micro'] and m.get('weak_month_count',99)<=g['weak_month_count'] and m.get('t1',1)==0)


def replay(bars: list[dict[str, Any]], entry_i: int, entry: float, sl: float) -> tuple[float, bool] | None:
    first = entry_i + 1
    if first >= len(bars): return None
    tp = entry + (entry - sl) * 1.5
    last = min(len(bars) - 1, entry_i + 10)
    exit_i = last; exit_p = fnum(bars[last].get('c'))
    for i in range(first, last + 1):
        if fnum(bars[i].get('l')) <= sl:
            exit_i = i; exit_p = sl; break
        if fnum(bars[i].get('h')) >= tp:
            exit_i = i; exit_p = tp; break
    return (exit_p / entry - 1) * 100, date_s(bars[exit_i]) == date_s(bars[entry_i])


def mode_ok(mode: str, b: dict[str, Any], zl: float, zh: float) -> bool:
    o = fnum(b.get('o')); c = fnum(b.get('c')); h = fnum(b.get('h')); l = fnum(b.get('l'))
    rng = max(h - l, 1e-9)
    if l > zh * 1.005: return False
    if mode == 'strict_v262': return c >= zh and c > o and (c - l) / rng >= 0.55
    if mode == 'soft_mid': return c >= (zl + zh) / 2 and (c - l) / rng >= 0.45
    if mode == 'touch_bull': return c > o and c >= zl
    if mode == 'support_hold': return c >= zl
    return False


def prior_ssl_flags(bars: list[dict[str, Any]], event_i: int) -> dict[int, bool]:
    out = {}
    for win in SSL_WINS:
        ok = False
        for i in range(max(20, event_i - win), event_i):
            pl = min(fnum(x.get('l')) for x in bars[i-20:i])
            if fnum(bars[i].get('l')) < pl and fnum(bars[i].get('c')) > pl:
                ok = True; break
        out[win] = ok
    return out


def scan(path: Path, sym_idx: int, aggs, ssl_aggs, funnel, seen, latest_holder) -> None:
    try: bars = json.loads(path.read_text())
    except Exception: return
    if len(bars) < 90: return
    symbol = symbol_from_path(path)
    for event_i in range(40, len(bars) - 2):
        e = bars[event_i]
        o = fnum(e.get('o')); c = fnum(e.get('c')); h = fnum(e.get('h')); l = fnum(e.get('l'))
        if c <= o or h <= l: continue
        ssl = None
        nearest_bear = []
        # nearest bearish distances for all demand lookbacks once
        for k in range(event_i - 1, max(event_i - max(DEMAND_LBS) - 1, -1), -1):
            if fnum(bars[k].get('c')) < fnum(bars[k].get('o')):
                nearest_bear.append(k)
                break
        if not nearest_bear: continue
        demand_i = nearest_bear[0]
        demand_dist = event_i - demand_i
        zl = fnum(bars[demand_i].get('l')); zh = max(fnum(bars[demand_i].get('o')), fnum(bars[demand_i].get('c')))
        if zl <= 0 or zh <= zl: continue
        for bos_lb in BOS_LBS:
            prev = bars[event_i-bos_lb:event_i]
            ph = max(fnum(x.get('h')) for x in prev)
            if c <= ph: continue
            funnel[f'bos{bos_lb}'] += 1
            if ssl is None: ssl = prior_ssl_flags(bars, event_i)
            first_by_mode = {}
            max_last = min(event_i + max(WAITS), len(bars) - 2)
            for mode in MODES:
                for ri in range(event_i + 1, max_last + 1):
                    if mode_ok(mode, bars[ri], zl, zh):
                        first_by_mode[mode] = ri; break
            for demand_lb in DEMAND_LBS:
                if demand_dist > demand_lb: continue
                funnel[f'bos{bos_lb}_zone{demand_lb}'] += 1
                for mode, ri in first_by_mode.items():
                    delay = ri - event_i
                    entry_i = ri + 1
                    if entry_i >= len(bars): continue
                    entry = fnum(bars[entry_i].get('o')); sl = zl * 0.99
                    risk = (entry / sl - 1) * 100
                    if not (0.8 <= risk <= 12.0): continue
                    rep = replay(bars, entry_i, entry, sl)
                    if rep is None: continue
                    pnl, t1 = rep
                    ed = date_s(bars[entry_i])
                    if ed > latest_holder[0]: latest_holder[0] = ed
                    for wait in WAITS:
                        if delay > wait: continue
                        key = (bos_lb, demand_lb, wait, mode)
                        uniq = (sym_idx, entry_i)
                        if uniq in seen[key]: continue
                        seen[key].add(uniq)
                        aggs[key].add(ed, pnl, t1)
                        for w, flag in ssl.items():
                            ssl_aggs[(key, w, flag)].add(ed, pnl, t1)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sorted(KLINE_DIR.glob('*_daily_750.json'))
    aggs = defaultdict(Agg); ssl_aggs = defaultdict(Agg); funnel = defaultdict(int); seen = defaultdict(set); latest = ['00000000']
    for i, p in enumerate(paths, 1):
        scan(p, i, aggs, ssl_aggs, funnel, seen, latest)
        if i % 500 == 0:
            print(f'scanned {i}/{len(paths)} variants={len(aggs)} latest={latest[0]}', flush=True)
    cutoff = (datetime.strptime(latest[0], '%Y%m%d') - timedelta(days=45)).strftime('%Y%m%d') if latest[0] != '00000000' else '99999999'

    rows = []
    for key, agg in aggs.items():
        bos, dlb, wait, mode = key
        m = agg.metrics()
        rows.append({
            'bos_lookback': bos, 'demand_lookback': dlb, 'wait_max': wait, 'reclaim_mode': mode,
            **{k:v for k,v in m.items() if k not in {'weak_months','year_counts','year_wr'}},
            'year_counts': m.get('year_counts', {}), 'year_wr': m.get('year_wr', {}),
            'prod_pass': pass_gate(m, PROD), 'research_pass': pass_gate(m, RESEARCH),
            'per_stock_3y': round(m.get('n',0) / max(len(paths),1), 3),
            'per_stock_per_year': round(m.get('n',0) / max(len(paths),1) / 3, 3),
        })
    rows.sort(key=lambda r: (r['prod_pass'], r['research_pass'], r['wr'], r['avg'], r['n']), reverse=True)

    ssl_rows = []
    for (key, win, flag), agg in ssl_aggs.items():
        m = agg.metrics(); bos, dlb, wait, mode = key
        ssl_rows.append({'bos_lookback': bos, 'demand_lookback': dlb, 'wait_max': wait, 'reclaim_mode': mode, 'prior_ssl_window': win, 'prior_ssl': flag, **{k:v for k,v in m.items() if k not in {'weak_months','year_counts','year_wr'}}})
    ssl_rows.sort(key=lambda r: (r['wr'], r['avg'], r['n']), reverse=True)

    mode_summary = []
    for mode in MODES:
        mr = [r for r in rows if r['reclaim_mode'] == mode]
        if mr:
            best = max(mr, key=lambda r: (r['wr'], r['avg']))
            vol = max(mr, key=lambda r: r['n'])
            mode_summary.append({'mode': mode, 'best_wr': best['wr'], 'best_avg_at_best_wr': best['avg'], 'best_n_at_best_wr': best['n'], 'max_n': vol['n'], 'wr_at_max_n': vol['wr'], 'avg_at_max_n': vol['avg']})

    (OUT / 'v272_variant_surface.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    (OUT / 'v272_prior_ssl_surface.json').write_text(json.dumps(ssl_rows, ensure_ascii=False, indent=2))
    summary = {
        'version': 'V272_TIME_ORDER_PARAMETER_SURFACE_FAST_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'kline_dir': str(KLINE_DIR), 'kline_files': len(paths)},
        'latest_entry_date': latest[0], 'current_cutoff': cutoff,
        'variant_count': len(rows), 'prod_pass_variants': sum(1 for r in rows if r['prod_pass']), 'research_pass_variants': sum(1 for r in rows if r['research_pass']),
        'top_quality': rows[:30],
        'top_volume': sorted(rows, key=lambda r: (r['n'], r['wr'], r['avg']), reverse=True)[:20],
        'reclaim_mode_summary': sorted(mode_summary, key=lambda x: x['best_wr'], reverse=True),
        'top_prior_ssl': ssl_rows[:30],
        'funnel_total': dict(sorted(funnel.items())),
        'artifacts': {'variant_surface': str(OUT/'v272_variant_surface.json'), 'prior_ssl_surface': str(OUT/'v272_prior_ssl_surface.json')},
    }
    (OUT / 'v272_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:8000])

if __name__ == '__main__':
    main()
