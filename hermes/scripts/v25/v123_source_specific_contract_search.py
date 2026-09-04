#!/usr/bin/env python3
"""V123 read-only source-specific contract search.

Consumes the V122 first-class parallel POI generator in memory and searches
separate ex-ante contracts for DEMAND_OB, FVG_Demand, and OB+FVG.

No production writes. No API/frontend/watchlist changes. No TP/SL tuning.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple

import v122_shadow_parallel_poi_generator_audit as v122
from v81_contextual_smc_generator import _date, f

ROOT = Path('/root/.hermes')
OUT = ROOT / 'smc_audit' / 'v123_source_specific_contract_search_20260620'
OUT.mkdir(parents=True, exist_ok=True)

Row = Dict[str, Any]
Predicate = Callable[[Row], bool]


def ds(x: Any) -> str:
    return ''.join(ch for ch in str(x or '') if ch.isdigit())[:8]


def pct(n: int, d: int) -> float:
    return round(n / d * 100, 2) if d else 0.0


def metrics(rows: Iterable[Row]) -> Dict[str, Any]:
    rs = list(rows)
    n = len(rs)
    if not n:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'sl': 0.0, 'tp': 0.0, 'cum': 0.0}
    vals = [f(r.get('pnl_pct')) for r in rs]
    return {
        'n': n,
        'wr': pct(sum(x > 0 for x in vals), n),
        'avg': round(sum(vals) / n, 4),
        'sl': pct(sum(('EXIT_POI_CLOSE_BREAK' in str(r.get('exit_reason')) or x < -0.8) for r, x in zip(rs, vals)), n),
        'tp': pct(sum('TAKE_PROFIT' in str(r.get('exit_reason')) for r in rs), n),
        'cum': round(sum(vals), 2),
    }


def month_stability(rows: List[Row]) -> Dict[str, Any]:
    by_m: Dict[str, List[Row]] = defaultdict(list)
    by_y: Dict[str, List[Row]] = defaultdict(list)
    for r in rows:
        d = ds(r.get('entry_date'))
        by_m[d[:6]].append(r)
        by_y[d[:4]].append(r)
    mm = {k: metrics(v) for k, v in sorted(by_m.items())}
    yy = {k: metrics(v) for k, v in sorted(by_y.items())}
    return {
        'months': len(mm),
        'stable3': sum(1 for x in mm.values() if x['n'] >= 3 and x['wr'] >= 60),
        'months_n_ge_3': sum(1 for x in mm.values() if x['n'] >= 3),
        'stable5': sum(1 for x in mm.values() if x['n'] >= 5 and x['wr'] >= 60),
        'months_n_ge_5': sum(1 for x in mm.values() if x['n'] >= 5),
        'bad5': sum(1 for x in mm.values() if x['n'] >= 5 and x['wr'] < 50),
        'by_year': yy,
    }


def v86_pass(r: Row) -> bool:
    return 1.0 < f(r.get('v85_zone_width_pct')) <= 1.6 and 1.0 < f(r.get('risk_pct')) <= 1.5 and f(r.get('hold_bars')) <= 2 and r.get('v83_takeover_type') == 'HOLD_ABOVE_POI' and ds(r.get('entry_date')) != ds(r.get('exit_date'))


def enrich_reclaim_geometry(rows: List[Row], by_symbol_ks: Dict[str, List[Dict[str, Any]]]) -> None:
    for r in rows:
        ks = by_symbol_ks.get(str(r.get('symbol')))
        if not ks:
            continue
        reclaim_idx = int(f(r.get('reclaim_idx'), -1))
        touch_idx = int(f(r.get('touch_idx'), -1))
        zone_low, zone_high = f(r.get('zone_low')), f(r.get('zone_high'))
        zone_w = max(zone_high - zone_low, 1e-9)
        if 0 <= reclaim_idx < len(ks):
            b = ks[reclaim_idx]
            a = v122.atr(ks, reclaim_idx)
            r['reclaim_strength_pct'] = round((f(b.get('c')) / max(zone_high, 1e-9) - 1) * 100, 4)
            r['reclaim_body_atr'] = round((f(b.get('c')) - f(b.get('o'))) / max(a, 1e-9), 4)
        else:
            r['reclaim_strength_pct'] = 0.0
            r['reclaim_body_atr'] = 0.0
        if 0 <= touch_idx < len(ks):
            r['touch_depth_pct'] = round(max(0.0, zone_high - f(ks[touch_idx].get('l'))) / zone_w * 100, 2)
        else:
            r['touch_depth_pct'] = 0.0
        r['v86_contract_pass_shadow'] = v86_pass(r)
        r['combo_family'] = 'CONTINUATION' if r.get('event_type') == 'BOS_CONTINUATION' else 'REVERSAL'


def build_rows() -> Tuple[List[Row], Dict[str, int]]:
    env_raw = v122.jload(v122.ENV_PATH)
    env_by_date = {str(k)[:8]: v122.normalize_env(v) for k, v in env_raw.items()}
    raw: List[Row] = []
    by_symbol_ks: Dict[str, List[Dict[str, Any]]] = {}
    scanned = 0
    for path in sorted(v122.KLINE_DIR.glob('*_daily_750.json')):
        ks = v122.jload(path)
        if len(ks) < 100:
            continue
        sym = v122.symbol_from_path(path)
        by_symbol_ks[sym] = ks
        raw.extend(v122.generate_parallel(sym, ks, env_by_date))
        scanned += 1
    rows = v122.dedupe(raw)
    enrich_reclaim_geometry(rows, by_symbol_ks)
    rows = [r for r in rows if ds(r.get('entry_date')) != ds(r.get('exit_date'))]
    return rows, {'scanned_symbols': scanned, 'raw_rows': len(raw), 'dedup_rows': len(rows)}


def in_range(val: float, lo: float, hi: float | None) -> bool:
    return val >= lo and (hi is None or val <= hi)


def contract(name: str, source: str, pred: Predicate, rows: List[Row], min_n: int) -> Dict[str, Any] | None:
    hit = [r for r in rows if r.get('poi_source') == source and pred(r)]
    if len(hit) < min_n:
        return None
    m = metrics(hit)
    st = month_stability(hit)
    return {
        'name': name,
        'source': source,
        **m,
        'months': st['months'],
        'stable3': st['stable3'],
        'months_n_ge_3': st['months_n_ge_3'],
        'stable5': st['stable5'],
        'months_n_ge_5': st['months_n_ge_5'],
        'bad5': st['bad5'],
        'by_year': st['by_year'],
        'score': round(m['wr'] * 1.0 + min(m['n'], 1000) / 100.0 + st['stable5'] * 2 - st['bad5'] * 3 + max(m['avg'], -5) * 4 - m['sl'] * 0.2, 4),
    }


def search_demand_ob(rows: List[Row]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    risk_ranges = [(0.8, 1.2), (0.8, 1.5), (1.0, 1.5), (1.0, 1.8), (1.2, 2.0)]
    width_ranges = [(0.8, 1.3), (1.0, 1.6), (1.2, 1.8), (0.8, 1.8)]
    hold_maxes = [1, 2, 3]
    families = ['ALL', 'CONTINUATION', 'REVERSAL']
    states = ['ALL', 'BULL_CONTINUATION', 'RECOVERY', 'MIXED', 'BEAR_RISK', 'DISTRIBUTION']
    for rr in risk_ranges:
        for ww in width_ranges:
            for hm in hold_maxes:
                for fam in families:
                    for st in states:
                        name = f"risk{rr[0]}-{rr[1]}|width{ww[0]}-{ww[1]}|hold<={hm}|{fam}|{st}"
                        def pred(r: Row, rr=rr, ww=ww, hm=hm, fam=fam, st=st) -> bool:
                            return in_range(f(r.get('risk_pct')), *rr) and in_range(f(r.get('v85_zone_width_pct')), *ww) and f(r.get('hold_bars')) <= hm and r.get('v83_takeover_type') == 'HOLD_ABOVE_POI' and (fam == 'ALL' or r.get('combo_family') == fam) and (st == 'ALL' or r.get('market_state') == st)
                        c = contract(name, 'DEMAND_OB', pred, rows, 100)
                        if c:
                            out.append(c)
    baseline = contract('V86_BASELINE risk1-1.5|width1-1.6|hold<=2|ALL|ALL', 'DEMAND_OB', v86_pass, rows, 50)
    if baseline:
        baseline['is_v86_baseline'] = True
        out.append(baseline)
    return sorted(out, key=lambda x: (-x['score'], -x['wr'], -x['avg'], -x['n']))


def search_fvg(rows: List[Row]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    mid_mins = [0.35, 0.65, 1.0, 1.3]
    gap_mins = [0.2, 0.5, 0.8, 1.2]
    risk_ranges = [(0.5, 2.0), (0.8, 2.5), (1.0, 3.0), (1.0, 1.8)]
    width_ranges = [(0.5, 1.5), (0.8, 2.0), (1.0, 2.5), (1.2, 3.0)]
    reclaim_mins = [0.0, 0.2, 0.5, 0.8]
    hold_maxes = [1, 2, 3]
    families = ['ALL', 'CONTINUATION', 'REVERSAL']
    for mid in mid_mins:
        for gap in gap_mins:
            for rr in risk_ranges:
                for ww in width_ranges:
                    for rec in reclaim_mins:
                        for hm in hold_maxes:
                            for fam in families:
                                name = f"mid>={mid}|gap>={gap}|risk{rr[0]}-{rr[1]}|width{ww[0]}-{ww[1]}|reclaim>={rec}|hold<={hm}|{fam}"
                                def pred(r: Row, mid=mid, gap=gap, rr=rr, ww=ww, rec=rec, hm=hm, fam=fam) -> bool:
                                    return f(r.get('source_mid_body_atr')) >= mid and f(r.get('source_gap_atr')) >= gap and in_range(f(r.get('risk_pct')), *rr) and in_range(f(r.get('v85_zone_width_pct')), *ww) and f(r.get('reclaim_strength_pct')) >= rec and f(r.get('hold_bars')) <= hm and r.get('v83_takeover_type') == 'HOLD_ABOVE_POI' and (fam == 'ALL' or r.get('combo_family') == fam)
                                c = contract(name, 'FVG_Demand', pred, rows, 80)
                                if c:
                                    out.append(c)
    return sorted(out, key=lambda x: (-x['score'], -x['wr'], -x['avg'], -x['n']))


def search_ob_fvg(rows: List[Row]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    overlap_mins = [20, 40, 60, 80]
    width_ranges = [(0.3, 1.2), (0.5, 1.6), (0.8, 2.0)]
    risk_ranges = [(0.5, 2.0), (0.8, 2.5), (1.0, 3.0)]
    reclaim_mins = [0.0, 0.3, 0.6]
    hold_maxes = [1, 2, 3]
    families = ['ALL', 'REVERSAL', 'CONTINUATION']
    states = ['ALL', 'RECOVERY', 'DISTRIBUTION', 'MIXED', 'BEAR_RISK']
    for ov in overlap_mins:
        for ww in width_ranges:
            for rr in risk_ranges:
                for rec in reclaim_mins:
                    for hm in hold_maxes:
                        for fam in families:
                            for st in states:
                                name = f"overlap>={ov}|width{ww[0]}-{ww[1]}|risk{rr[0]}-{rr[1]}|reclaim>={rec}|hold<={hm}|{fam}|{st}"
                                def pred(r: Row, ov=ov, ww=ww, rr=rr, rec=rec, hm=hm, fam=fam, st=st) -> bool:
                                    return f(r.get('ob_fvg_overlap_pct')) >= ov and in_range(f(r.get('v85_zone_width_pct')), *ww) and in_range(f(r.get('risk_pct')), *rr) and f(r.get('reclaim_strength_pct')) >= rec and f(r.get('hold_bars')) <= hm and r.get('v83_takeover_type') == 'HOLD_ABOVE_POI' and (fam == 'ALL' or r.get('combo_family') == fam) and (st == 'ALL' or r.get('market_state') == st)
                                c = contract(name, 'OB+FVG', pred, rows, 20)
                                if c:
                                    out.append(c)
    return sorted(out, key=lambda x: (-x['score'], -x['wr'], -x['avg'], -x['n']))


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    with path.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def markdown_table_contracts(title: str, rows: List[Dict[str, Any]], limit: int = 12) -> List[str]:
    lines = [f'## {title}', '|rank|contract|n|WR|Avg|SL|stable5|bad5|score|', '|---:|---|---:|---:|---:|---:|---:|---:|---:|']
    for i, r in enumerate(rows[:limit], 1):
        lines.append(f"|{i}|`{r['name']}`|{r['n']}|{r['wr']}|{r['avg']}|{r['sl']}|{r['stable5']}/{r['months_n_ge_5']}|{r['bad5']}|{r['score']}|")
    lines.append('')
    return lines


def source_metrics(rows: List[Row]) -> Dict[str, Any]:
    return {src: metrics([r for r in rows if r.get('poi_source') == src]) for src in sorted({r.get('poi_source') for r in rows})}


def main() -> None:
    rows, scan = build_rows()
    by_source = source_metrics(rows)
    t1_violations = [r for r in rows if ds(r.get('entry_date')) == ds(r.get('exit_date'))]
    demand = search_demand_ob(rows)
    fvg = search_fvg(rows)
    combo = search_ob_fvg(rows)

    fields = ['source','name','n','wr','avg','sl','tp','cum','months','stable3','months_n_ge_3','stable5','months_n_ge_5','bad5','score']
    write_csv(OUT / 'demand_ob_contracts.csv', demand, fields)
    write_csv(OUT / 'fvg_demand_contracts.csv', fvg, fields)
    write_csv(OUT / 'ob_fvg_contracts.csv', combo, fields)

    best = {'DEMAND_OB': demand[:20], 'FVG_Demand': fvg[:20], 'OB+FVG': combo[:20]}
    summary = {
        'decision': 'READ_ONLY_SOURCE_SPECIFIC_CONTRACT_SEARCH_DONE_NO_CHANGE',
        **scan,
        't1_violations': len(t1_violations),
        'by_source': by_source,
        'best_contracts': best,
        'no_production_change': True,
        'v116_remains_shadow': True,
        'notes': [
            'Contracts are ex-ante field predicates only; score is ranking aid, not production proof.',
            'No TP/SL parameters were changed; exits reused V122 semantic simulation.',
            'Continuation remains shadow-only; do not promote broad continuation from these search results.',
        ],
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    lines: List[str] = []
    lines.append('# V123 Source-specific Contract Search 只读审计')
    lines.append('')
    lines.append('Decision: `READ_ONLY_SOURCE_SPECIFIC_CONTRACT_SEARCH_DONE_NO_CHANGE`。未改生产、未调TP/SL、V116继续shadow。')
    lines.append('')
    lines.append(f"Scanned symbols: {scan['scanned_symbols']}; raw rows: {scan['raw_rows']}; dedup rows: {scan['dedup_rows']}; T+1 violations: {len(t1_violations)}.")
    lines.append('')
    lines.append('## 1. V122 base by source')
    lines.append('|source|n|WR|Avg|SL|TP|Cum|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for src, m in by_source.items():
        lines.append(f"|{src}|{m['n']}|{m['wr']}|{m['avg']}|{m['sl']}|{m['tp']}|{m['cum']}|")
    lines.append('')
    lines.extend(markdown_table_contracts('2. DEMAND_OB source-specific contracts', demand))
    lines.extend(markdown_table_contracts('3. FVG_Demand source-specific contracts', fvg))
    lines.extend(markdown_table_contracts('4. OB+FVG source-specific contracts', combo))
    lines.append('## 5. 结论')
    lines.append('1. `DEMAND_OB` 最稳的候选仍接近 V86 逻辑：窄 risk、窄 width、hold<=2/3、HOLD_ABOVE_POI。')
    lines.append('2. `FVG_Demand` 需要自己的 source displacement / gap_atr / reclaim 强度合同；裸 FVG 不能生产。')
    lines.append('3. `OB+FVG` 样本小，只有作为 REVERSAL/RECOVERY/DISTRIBUTION 等窄子族继续 shadow；不能用 overlap 直接放开。')
    lines.append('4. `CONTINUATION` 只可继续分层 shadow；不能整体上线。')
    lines.append('5. V116 exact weak-source gate 继续 shadow，等待 source-specific contract 稳定后再接 scanner/API 字段闭环。')
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(OUT), 'decision': summary['decision'], 'dedup_rows': scan['dedup_rows'], 't1_violations': len(t1_violations), 'top': {k: v[:3] for k, v in best.items()}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
