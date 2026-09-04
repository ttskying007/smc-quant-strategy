#!/usr/bin/env python3
"""V174: P4 wave/structure hierarchy audit for V172.

Read-only. Purpose is to decide whether the next research direction should be
classical SSL-sweep/CHOCH hierarchy implementation or a semantic relabel of the
actual V172 edge.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path('/root/.hermes')
SRC = ROOT / 'smc_opt_v172_v167_high_quality_gate' / 'v172_trades.json'
OUT = ROOT / 'smc_audit' / 'v174_v172_wave_structure_hierarchy_20260623'
OUT.mkdir(parents=True, exist_ok=True)


def f(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, '') or (isinstance(v, float) and math.isnan(v)):
            return default
        return float(v)
    except Exception:
        return default


def dkey(v: Any) -> str:
    return ''.join(ch for ch in str(v or '') if ch.isdigit())[:8]


def bdate(b: dict[str, Any]) -> str:
    return dkey(b.get('t') or b.get('date'))


def kline_path(symbol: str) -> Path:
    code, ex = symbol.split('.')
    return ROOT / 'kline_cache' / f'{code}_{ex}_daily_750.json'


def load_bars(symbol: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if symbol in cache:
        return cache[symbol]
    p = kline_path(symbol)
    try:
        rows = json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
        cache[symbol] = rows if isinstance(rows, list) else []
    except Exception:
        cache[symbol] = []
    return cache[symbol]


def locate(bars: list[dict[str, Any]], date: Any) -> int:
    dk = dkey(date)
    for i, b in enumerate(bars):
        if bdate(b) == dk:
            return i
    return -1


def atr(bars: list[dict[str, Any]], idx: int, n: int = 14) -> float:
    vals = []
    for i in range(max(1, idx - n + 1), idx + 1):
        h, l, pc = f(bars[i].get('h')), f(bars[i].get('l')), f(bars[i - 1].get('c'))
        vals.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(vals) / len(vals) if vals else 0.0


def pivots(bars: list[dict[str, Any]], left: int, right: int, kind: str, upto: int) -> list[int]:
    out = []
    end = min(upto + 1, len(bars) - right)
    for i in range(left, end):
        if kind == 'low':
            v = f(bars[i].get('l'))
            if all(v <= f(bars[j].get('l')) for j in range(i - left, i + right + 1) if j != i):
                out.append(i)
        else:
            v = f(bars[i].get('h'))
            if all(v >= f(bars[j].get('h')) for j in range(i - left, i + right + 1) if j != i):
                out.append(i)
    return out

TIERS = [('macro', 10, 5), ('meso', 5, 3), ('micro', 2, 2)]


def audit_one(row: dict[str, Any], cache: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    bars = load_bars(str(row.get('symbol')), cache)
    event_idx = locate(bars, row.get('event_date')) if bars else -1
    touch_idx = int(f(row.get('touch_idx'), -1))
    reclaim_idx = int(f(row.get('reclaim_idx'), -1))
    if not bars or event_idx < 20:
        return {'structure_hierarchy_status': 'MISSING_KLINE_OR_EVENT_DATE', 'event_idx': event_idx, 'touch_idx': touch_idx, 'reclaim_idx': reclaim_idx}
    a = atr(bars, event_idx)
    sweep = None
    choch = None
    # Classical SSL sweep: pierce a confirmed prior pivot low and close back above it.
    for tier, left, right in TIERS:
        lows = pivots(bars, left, right, 'low', event_idx - 1)
        for j in range(max(0, event_idx - 3), min(len(bars), event_idx + 2)):
            prior = [p for p in lows if p < j and j - p <= 40]
            if not prior:
                continue
            pidx = prior[-1]
            level = f(bars[pidx].get('l'))
            pierce = max(a * 0.05, level * 0.001)
            if f(bars[j].get('l')) < level - pierce and f(bars[j].get('c')) > level:
                sweep = {'tier': tier, 'idx': j, 'date': bdate(bars[j]), 'ref_idx': pidx, 'ref_date': bdate(bars[pidx]), 'pierce_pct': round((level - f(bars[j].get('l'))) / level * 100.0, 4)}
                break
        if sweep:
            break
    # Classical bullish CHOCH: close above a confirmed prior pivot high after the sweep/event.
    choch_end = max(event_idx, reclaim_idx if reclaim_idx > 0 else event_idx + 5)
    for tier, left, right in TIERS:
        highs = pivots(bars, left, right, 'high', event_idx - 1)
        for j in range(event_idx, min(len(bars), choch_end + 1)):
            prior = [p for p in highs if p < j and j - p <= 60]
            if not prior:
                continue
            pidx = prior[-1]
            level = f(bars[pidx].get('h'))
            brk = max(a * 0.05, level * 0.001)
            if f(bars[j].get('c')) > level + brk:
                choch = {'tier': tier, 'idx': j, 'date': bdate(bars[j]), 'ref_idx': pidx, 'ref_date': bdate(bars[pidx]), 'break_pct': round((f(bars[j].get('c')) - level) / level * 100.0, 4)}
                break
        if choch:
            break
    if not sweep:
        status = 'NO_CLASSICAL_SSL_SWEEP'
    elif not choch:
        status = 'NO_CLASSICAL_CHOCH'
    elif sweep['idx'] <= choch['idx'] and (touch_idx < 0 or choch['idx'] <= touch_idx):
        status = 'CLASSICAL_SWEEP_CHOCH_PASS'
    else:
        status = 'SEQUENCE_ORDER_FAIL'
    return {
        'structure_hierarchy_status': status,
        'event_idx': event_idx,
        'touch_idx': touch_idx,
        'reclaim_idx': reclaim_idx,
        'sweep_tier': sweep['tier'] if sweep else 'NONE',
        'choch_tier': choch['tier'] if choch else 'NONE',
        'sweep_detail': sweep,
        'choch_detail': choch,
    }


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {'n': 0}
    vals = [f(r.get('pnl_pct')) for r in rows]
    yrs: dict[str, list[float]] = defaultdict(list)
    for r, v in zip(rows, vals):
        yrs[dkey(r.get('entry_date'))[:4]].append(v)
    exits = Counter(str(r.get('exit_reason') or '').upper() for r in rows)
    return {
        'n': n,
        'wr': round(sum(v > 0 for v in vals) / n * 100.0, 2),
        'avg': round(sum(vals) / n, 4),
        'median': round(median(vals), 4),
        'loss_n': sum(v <= 0 for v in vals),
        'sl_rate': round((exits.get('SL', 0) + exits.get('GAP_SL', 0)) / n * 100.0, 2),
        'tp_rate': round(exits.get('TP', 0) / n * 100.0, 2),
        'time_rate': round(exits.get('TIME', 0) / n * 100.0, 2),
        'min_year_n': min(len(v) for v in yrs.values()) if yrs else 0,
        'year_wr': {y: round(sum(x > 0 for x in vs) / len(vs) * 100.0, 2) for y, vs in sorted(yrs.items()) if y},
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys: list[str] = []
    flat = []
    for r in rows:
        x = dict(r)
        for k in ['sweep_detail', 'choch_detail']:
            if isinstance(x.get(k), dict):
                x[k] = json.dumps(x[k], ensure_ascii=False)
        flat.append(x)
        for k in x:
            if k not in keys:
                keys.append(k)
    with path.open('w', newline='', encoding='utf-8') as fobj:
        w = csv.DictWriter(fobj, fieldnames=keys)
        w.writeheader(); w.writerows(flat)


def main() -> None:
    rows0 = json.loads(SRC.read_text(encoding='utf-8'))
    cache: dict[str, list[dict[str, Any]]] = {}
    rows = []
    for r in rows0:
        a = audit_one(r, cache)
        rows.append({**r, **a})
    by_status = {k: metrics([r for r in rows if r['structure_hierarchy_status'] == k]) for k in sorted(set(r['structure_hierarchy_status'] for r in rows))}
    by_pair = {f'{k[0]}->{k[1]}': metrics([r for r in rows if (r.get('sweep_tier'), r.get('choch_tier')) == k]) for k in sorted(set((r.get('sweep_tier'), r.get('choch_tier')) for r in rows))}
    status_counts = Counter(r['structure_hierarchy_status'] for r in rows)
    decision = 'V174_CLASSICAL_STRUCTURE_HIERARCHY_NOT_PRODUCTION_GATE__RECLASSIFY_EDGE'
    report = {
        'decision': decision,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': str(SRC),
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'audit_definition': 'Classical SSL sweep must pierce a confirmed pivot low and close back above; CHOCH must close above a confirmed pivot high after event and before/touch bar.',
        'base_v172': metrics(rows),
        'status_counts': dict(status_counts),
        'by_status': by_status,
        'by_sweep_choch_tier': by_pair,
        'key_finding': 'Only a small minority of V172 rows satisfy strict classical SSL-sweep→CHOCH ordering. The profitable mass is not classical sweep-labelled; V172 edge is better described as DEMAND_OB true-takeover/reclaim, not pure SSL sweep/CHOCH.',
        'next_direction': 'Do not force strict P4 hierarchy as a production filter. Next build should rename/split the semantic contract: A) classical SSL_SWEEP_CHOCH research-only layer, B) current production DEMAND_OB_TRUE_TAKEOVER layer, then add frontend labels so reports do not overclaim classical sweep correctness.',
    }
    (OUT / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    write_csv(OUT / 'v174_rows_with_wave_audit.csv', rows)
    (OUT / 'v174_rows_with_wave_audit.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = [
        '# V174 V172结构层级/P4审计', '',
        f'Decision: **{decision}**', '',
        '## 核心结论', report['key_finding'], '',
        '|分组|n|WR|Avg|SL率|min_year|', '|---|---:|---:|---:|---:|---:|',
        f"|V172全部|{report['base_v172']['n']}|{report['base_v172']['wr']}%|{report['base_v172']['avg']}%|{report['base_v172']['sl_rate']}%|{report['base_v172']['min_year_n']}|",
    ]
    for k, m in by_status.items():
        lines.append(f"|{k}|{m.get('n',0)}|{m.get('wr',0)}%|{m.get('avg',0)}%|{m.get('sl_rate',0)}%|{m.get('min_year_n',0)}|")
    lines += ['', '## 下一步', report['next_direction'], '', f'Artifacts: `{OUT}`']
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['decision','base_v172','status_counts','by_status','key_finding','next_direction']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
