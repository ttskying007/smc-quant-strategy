#!/usr/bin/env python3
"""V124 read-only reclaim-strength + no-hold source contract audit.

Regenerates V122 parallel POI rows with persisted zone/touch/reclaim/entry
geometry, then searches FVG_Demand no-hold reclaim-strength contracts.
No production writes. No TP/SL tuning. V116 remains shadow.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from v122_shadow_parallel_poi_generator_audit import (
    KLINE_DIR,
    ENV_PATH,
    atr,
    ds,
    f,
    generate_parallel,
    jload,
    normalize_env,
    symbol_from_path,
    v,
)

ROOT = Path('/root/.hermes')
OUT = ROOT / 'smc_audit' / 'v124_reclaim_strength_nohold_contract_20260620'
OUT.mkdir(parents=True, exist_ok=True)


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rs = list(rows)
    n = len(rs)
    if not n:
        return {'n': 0, 'wr': 0, 'avg': 0, 'sl': 0, 'tp': 0, 'cum': 0}
    vals = [f(r.get('pnl_pct')) for r in rs]
    return {
        'n': n,
        'wr': round(sum(x > 0 for x in vals) / n * 100, 2),
        'avg': round(sum(vals) / n, 4),
        'sl': round(sum(('EXIT_POI_CLOSE_BREAK' in str(r.get('exit_reason')) or x < -0.8) for r, x in zip(rs, vals)) / n * 100, 2),
        'tp': round(sum('TAKE_PROFIT' in str(r.get('exit_reason')) for r in rs) / n * 100, 2),
        'cum': round(sum(vals), 2),
    }


def stable(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_m: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_m[ds(r.get('entry_date'))[:6]].append(r)
    ms = [metrics(vv) for vv in by_m.values()]
    return {
        'months': len(ms),
        'stable3': sum(1 for x in ms if x['n'] >= 3 and x['wr'] >= 60),
        'months_n_ge_3': sum(1 for x in ms if x['n'] >= 3),
        'stable5': sum(1 for x in ms if x['n'] >= 5 and x['wr'] >= 60),
        'months_n_ge_5': sum(1 for x in ms if x['n'] >= 5),
        'bad5': sum(1 for x in ms if x['n'] >= 5 and x['wr'] < 50),
    }


def enrich_reclaim_fields(row: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    r = dict(row)
    zl, zh = f(r.get('zone_low')), f(r.get('zone_high'))
    ti, ri, ei = int(f(r.get('touch_idx'), -1)), int(f(r.get('reclaim_idx'), -1)), int(f(r.get('entry_idx'), -1))
    width = max(zh - zl, 1e-9)
    if 0 <= ti < len(ks):
        tb = ks[ti]
        touch_low = v(tb, 'l')
        r['touch_low'] = round(touch_low, 6)
        r['touch_depth_zone_pct'] = round(max(0.0, zh - touch_low) / width * 100, 4)
        r['touch_broke_zone_low'] = touch_low < zl
        r['touch_close_inside_or_below'] = v(tb, 'c') <= zh
    else:
        r['touch_low'] = ''
        r['touch_depth_zone_pct'] = 0.0
        r['touch_broke_zone_low'] = False
        r['touch_close_inside_or_below'] = False
    if 0 <= ri < len(ks):
        rb = ks[ri]
        a = atr(ks, ri)
        body = abs(v(rb, 'c') - v(rb, 'o'))
        r['reclaim_close'] = round(v(rb, 'c'), 6)
        r['reclaim_close_above_zone_pct'] = round((v(rb, 'c') / zh - 1) * 100, 4) if zh else 0.0
        r['reclaim_body_atr'] = round(body / max(a, 1e-9), 4)
        r['reclaim_range_atr'] = round((v(rb, 'h') - v(rb, 'l')) / max(a, 1e-9), 4)
        r['reclaim_bull_body'] = v(rb, 'c') > v(rb, 'o')
        rng = max(v(rb, 'h') - v(rb, 'l'), 1e-9)
        r['reclaim_close_pos'] = round((v(rb, 'c') - v(rb, 'l')) / rng, 4)
    else:
        r['reclaim_close'] = ''
        r['reclaim_close_above_zone_pct'] = 0.0
        r['reclaim_body_atr'] = 0.0
        r['reclaim_range_atr'] = 0.0
        r['reclaim_bull_body'] = False
        r['reclaim_close_pos'] = 0.0
    r['touch_to_reclaim_bars'] = max(0, ri - ti) if ti >= 0 and ri >= 0 else 0
    r['reclaim_to_entry_bars'] = max(0, ei - ri) if ei >= 0 and ri >= 0 else 0
    r['entry_chase_above_zone_pct'] = round((f(r.get('entry_price')) / zh - 1) * 100, 4) if zh else 0.0
    r['combo_family'] = 'CONTINUATION' if r.get('event_type') == 'BOS_CONTINUATION' else 'REVERSAL'
    return r


def dedupe_no_hold(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for r in rows:
        key = (str(r.get('symbol')), ds(r.get('entry_date')), str(r.get('poi_source')))
        # Ex-ante only: no pnl/exit/hold. Prefer lower risk, narrower zone, stronger displacement/reclaim.
        score = (
            f(r.get('risk_pct'), 999),
            f(r.get('v85_zone_width_pct'), 999),
            -f(r.get('source_mid_body_atr')), 
            -f(r.get('source_gap_atr')),
            -f(r.get('reclaim_close_above_zone_pct')),
            ds(r.get('event_date')),
        )
        old = best.get(key)
        if old is None or score < old.get('_dedupe_score'):
            r['_dedupe_score'] = score
            best[key] = r
    return list(best.values())


def pack(name: str, rows: List[Dict[str, Any]], min_n: int = 100) -> Dict[str, Any] | None:
    if len(rows) < min_n:
        return None
    m = metrics(rows)
    st = stable(rows)
    score = round(m['wr'] + min(m['n'], 1000) / 100 + st['stable5'] * 2 - st['bad5'] * 3 + max(m['avg'], -5) * 4 - m['sl'] * 0.25, 4)
    return {'contract': name, **m, **st, 'score': score}


def search_fvg(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    base = [r for r in rows if r.get('poi_source') == 'FVG_Demand']
    for mid in (0.65, 1.0, 1.3):
        a = [r for r in base if f(r.get('source_mid_body_atr')) >= mid]
        for gap in (0.5, 0.8, 1.2):
            b = [r for r in a if f(r.get('source_gap_atr')) >= gap]
            for rr in ((0.8, 2.5), (1.0, 3.0), (1.0, 2.0)):
                c = [r for r in b if rr[0] <= f(r.get('risk_pct')) <= rr[1]]
                for ww in ((1.0, 2.5), (1.2, 3.0), (1.2, 2.2)):
                    d = [r for r in c if ww[0] <= f(r.get('v85_zone_width_pct')) <= ww[1]]
                    for close_above in (0.0, 0.2, 0.5, 1.0):
                        e = [r for r in d if f(r.get('reclaim_close_above_zone_pct')) >= close_above]
                        for body in (0.0, 0.2, 0.4, 0.6):
                            g = [r for r in e if f(r.get('reclaim_body_atr')) >= body]
                            for depth in ((0, 200), (20, 120), (50, 160)):
                                h = [r for r in g if depth[0] <= f(r.get('touch_depth_zone_pct')) <= depth[1]]
                                for delay in ((1, 3), (1, 5), (2, 5)):
                                    i = [r for r in h if delay[0] <= f(r.get('touch_to_reclaim_bars')) <= delay[1]]
                                    for fam in ('ALL', 'REVERSAL', 'CONTINUATION'):
                                        j = i if fam == 'ALL' else [r for r in i if r.get('combo_family') == fam]
                                        name = f'mid>={mid}|gap>={gap}|risk{rr[0]}-{rr[1]}|width{ww[0]}-{ww[1]}|reclaim_above>={close_above}|body_atr>={body}|depth{depth[0]}-{depth[1]}|delay{delay[0]}-{delay[1]}|{fam}'
                                        p = pack(name, j, min_n=80)
                                        if p:
                                            out.append(p)
    return sorted(out, key=lambda x: (-x['score'], -x['wr'], -x['avg'], -x['n']))


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    with path.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def table(title: str, rows: List[Dict[str, Any]], n: int = 12) -> List[str]:
    lines = [f'## {title}', '|rank|contract|n|WR|Avg|SL|stable5|bad5|score|', '|---:|---|---:|---:|---:|---:|---:|---:|---:|']
    for idx, r in enumerate(rows[:n], 1):
        lines.append(f"|{idx}|`{r['contract']}`|{r['n']}|{r['wr']}|{r['avg']}|{r['sl']}|{r['stable5']}/{r['months_n_ge_5']}|{r['bad5']}|{r['score']}|")
    lines.append('')
    return lines


def main() -> None:
    env_raw = jload(ENV_PATH)
    env_by_date = {str(k)[:8]: normalize_env(vv) for k, vv in env_raw.items()}
    raw: List[Dict[str, Any]] = []
    scanned = 0
    for path in sorted(KLINE_DIR.glob('*_daily_750.json')):
        ks = jload(path)
        if len(ks) < 100:
            continue
        sym = symbol_from_path(path)
        for r in generate_parallel(sym, ks, env_by_date):
            if r.get('poi_source') == 'FVG_Demand':
                raw.append(enrich_reclaim_fields(r, ks))
        scanned += 1
    rows = dedupe_no_hold(raw)
    t1 = [r for r in rows if ds(r.get('entry_date')) == ds(r.get('exit_date'))]
    base = metrics(rows)
    by_base_contract = [r for r in rows if f(r.get('source_mid_body_atr')) >= 1.0 and f(r.get('source_gap_atr')) >= 0.8 and 1.0 <= f(r.get('risk_pct')) <= 3.0 and 1.2 <= f(r.get('v85_zone_width_pct')) <= 3.0]
    v123_like = metrics(by_base_contract)
    contracts = search_fvg(rows)

    fields = ['symbol','poi_source','combo_family','event_type','event_date','zone_date','entry_date','exit_date','pnl_pct','exit_reason','risk_pct','v85_zone_width_pct','source_mid_body_atr','source_gap_atr','zone_low','zone_high','touch_idx','reclaim_idx','entry_idx','entry_price','touch_low','touch_depth_zone_pct','touch_broke_zone_low','reclaim_close','reclaim_close_above_zone_pct','reclaim_body_atr','reclaim_range_atr','reclaim_bull_body','reclaim_close_pos','touch_to_reclaim_bars','entry_chase_above_zone_pct','market_state','daily_structure_state','m60_structure_state','v83_takeover_type']
    write_csv(OUT / 'fvg_demand_reclaim_fields_dedup_nohold.csv', rows, fields)
    write_csv(OUT / 'fvg_demand_reclaim_contracts.csv', contracts, ['contract','n','wr','avg','sl','tp','cum','months','stable3','months_n_ge_3','stable5','months_n_ge_5','bad5','score'])

    summary = {
        'decision': 'READ_ONLY_RECLAIM_STRENGTH_NOHOLD_CONTRACT_DONE_NO_CHANGE',
        'scanned_symbols': scanned,
        'raw_fvg_rows': len(raw),
        'dedup_nohold_rows': len(rows),
        't1_violations': len(t1),
        'fvg_demand_nohold_base': base,
        'v123_like_no_reclaim_contract': v123_like,
        'best_reclaim_contracts': contracts[:20],
        'no_production_change': True,
        'v116_remains_shadow': True,
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = ['# V124 Reclaim-strength + No-hold FVG_Demand Contract 只读审计', '', 'Decision: `READ_ONLY_RECLAIM_STRENGTH_NOHOLD_CONTRACT_DONE_NO_CHANGE`。未改生产、未调TP/SL、V116继续shadow。', '', f"Scanned symbols: {scanned}; raw FVG rows: {len(raw)}; dedup no-hold rows: {len(rows)}; T+1 violations: {len(t1)}.", '', '## 1. FVG_Demand 基线对照', '|slice|n|WR|Avg|SL|TP|Cum|', '|---|---:|---:|---:|---:|---:|---:|']
    lines.append(f"|FVG_Demand no-hold dedup all|{base['n']}|{base['wr']}|{base['avg']}|{base['sl']}|{base['tp']}|{base['cum']}|")
    lines.append(f"|V123-like no reclaim: mid>=1.0 gap>=0.8 risk1-3 width1.2-3|{v123_like['n']}|{v123_like['wr']}|{v123_like['avg']}|{v123_like['sl']}|{v123_like['tp']}|{v123_like['cum']}|")
    lines.append('')
    lines += table('2. FVG_Demand reclaim-strength no-hold contracts', contracts)
    lines += ['## 3. 结论', '1. 本轮已持久化 `zone_low/zone_high/touch_idx/reclaim_idx/entry_idx` 及 reclaim 派生强度字段。', '2. 所有搜索合同均不使用 `hold_bars`，避免 outcome leakage。', '3. 若最佳 reclaim 合同 SL 低于 V123 no-hold 的 24.10%，说明 reclaim 强度确实能继续压低 SL；否则说明主要瓶颈不在 reclaim 强度。', '4. 本轮仍是 shadow/research，不能直接接生产；下一步若要接 scanner，必须把这些字段接入 daily generator 的候选字段契约。']
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(OUT), 'decision': summary['decision'], 'dedup_nohold_rows': len(rows), 'base': base, 'v123_like': v123_like, 'top3': contracts[:3], 't1_violations': len(t1)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
