#!/usr/bin/env python3
"""V121 read-only audit: parallel POI supply + continuation stability.

No production writes. No strategy/API/frontend/watchlist changes. No TP/SL tuning.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path('/root/.hermes')
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_audit' / 'v121_parallel_poi_continuation_stability_20260619'
OUT.mkdir(parents=True, exist_ok=True)

V85_ALL = ROOT / 'smc_opt_v85_mixed_accumulation_generator' / 'v85_candidates.json'
V86_TRADES = ROOT / 'smc_opt_v86_production_gate' / 'v86_trades.json'
V90_ALL = ROOT / 'smc_opt_v90_daily_full_market_scanner' / 'v90_all_contract_candidates.json'
V102_CAND = ROOT / 'smc_opt_v102_balanced_volume_gate' / 'v102_candidate_picks.json'
V102_ACTIVE = ROOT / 'smc_opt_v102_balanced_volume_gate' / 'v102_active_picks.json'


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x in (None, ''):
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def d(b: Dict[str, Any]) -> str:
    return str(b.get('t') or b.get('date') or b.get('day') or '')[:8]


def date_s(x: Any) -> str:
    return ''.join(ch for ch in str(x or '') if ch.isdigit())[:8]


def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding='utf-8'))


def kline_path(symbol: str) -> Path:
    s = str(symbol).replace('.', '_')
    p = KLINE_DIR / f'{s}_daily_750.json'
    if not p.exists():
        p = KLINE_DIR / f'{s}_daily_300.json'
    return p


def load_ks(symbol: str, cache: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if symbol in cache:
        return cache[symbol]
    p = kline_path(symbol)
    cache[symbol] = load_json(p) if p.exists() else []
    return cache[symbol]


def atr(ks: List[Dict[str, Any]], idx: int, n: int = 14) -> float:
    trs: List[float] = []
    for i in range(max(1, idx - n + 1), min(idx + 1, len(ks))):
        h, l, pc = f(ks[i].get('h')), f(ks[i].get('l')), f(ks[i - 1].get('c'))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def idx_from_date(ks: List[Dict[str, Any]], day: Any) -> Optional[int]:
    target = date_s(day)
    for i, b in enumerate(ks):
        if d(b) == target:
            return i
    return None


def demand_fvg_near(ks: List[Dict[str, Any]], start_bar: int, event_bar: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not ks or event_bar < 2:
        return out
    lo = max(start_bar + 2, event_bar - 2)
    hi = min(event_bar + 3, len(ks))
    for i in range(lo, hi):
        h0, l2, a = f(ks[i - 2].get('h')), f(ks[i].get('l')), atr(ks, i)
        if h0 > 0 and l2 > h0 and (l2 - h0) >= a * 0.20:
            out.append({
                'bar': i - 1,
                'date': d(ks[i - 1]),
                'low': h0,
                'high': l2,
                'atr': a,
                'mid_body_atr': (f(ks[i - 1].get('c')) - f(ks[i - 1].get('o'))) / max(a, 1e-9),
                'mid_range_atr': (f(ks[i - 1].get('h')) - f(ks[i - 1].get('l'))) / max(a, 1e-9),
            })
    return out


def reclaim_after_touch(ks: List[Dict[str, Any]], poi: Dict[str, Any], event_bar: int, max_wait: int = 20) -> Optional[Dict[str, Any]]:
    zl, zh = f(poi.get('low')), f(poi.get('high'))
    touch = None
    start = max(event_bar + 1, int(poi.get('bar', event_bar)) + 1)
    stop = min(len(ks) - 63, event_bar + max_wait)
    for i in range(start, stop + 1):
        op, cl, hi, lo = f(ks[i].get('o')), f(ks[i].get('c')), f(ks[i].get('h')), f(ks[i].get('l'))
        if touch is None:
            if lo <= zh and hi >= zl:
                touch = i
                if cl < zl:
                    return None
            continue
        if cl < zl:
            return None
        if cl > zh and cl > op:
            eidx = i + 1
            if eidx < len(ks) and f(ks[eidx].get('o')) > zh:
                return {'touch_idx': touch, 'reclaim_idx': i, 'entry_idx': eidx, 'entry_date': d(ks[eidx])}
    return None


def overlap_pct(a_low: float, a_high: float, b_low: float, b_high: float) -> float:
    inter = max(0.0, min(a_high, b_high) - max(a_low, b_low))
    base = max(min(a_high - a_low, b_high - b_low), 1e-9)
    return inter / base * 100.0


def source_start_bar(row: Dict[str, Any], event_bar: int) -> int:
    for key in ('sweep_idx', 'broken_high_bar', 'swing_low_idx'):
        if row.get(key) not in (None, ''):
            return int(f(row.get(key), event_bar))
    return max(0, event_bar - 5)


def annotate_parallel_poi(rows: Iterable[Dict[str, Any]], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    cache: Dict[str, List[Dict[str, Any]]] = {}
    out: List[Dict[str, Any]] = []
    for n, row in enumerate(rows, 1):
        if limit and n > limit:
            break
        sym = str(row.get('symbol'))
        ks = load_ks(sym, cache)
        event_bar = int(f(row.get('event_idx'), -1))
        if event_bar < 0:
            event_bar = idx_from_date(ks, row.get('event_date')) or -1
        start_bar = source_start_bar(row, event_bar) if event_bar >= 0 else -1
        fvgs = demand_fvg_near(ks, start_bar, event_bar) if event_bar >= 0 else []
        zl, zh = f(row.get('zone_low')), f(row.get('zone_high'))
        overlaps = [overlap_pct(zl, zh, fvg['low'], fvg['high']) for fvg in fvgs]
        fvg_entries = []
        for fvg in fvgs:
            ent = reclaim_after_touch(ks, {'bar': fvg['bar'], 'low': fvg['low'], 'high': fvg['high']}, event_bar)
            if ent:
                fvg_entries.append(ent)
        out.append({
            'symbol': sym,
            'entry_date': date_s(row.get('entry_date')),
            'event_date': date_s(row.get('event_date')),
            'event_type': row.get('event_type') or row.get('source_event'),
            'combo_family': row.get('combo_family') or ('CONTINUATION' if row.get('event_type') == 'BOS_CONTINUATION' else 'REVERSAL'),
            'market_state': row.get('market_state'),
            'daily_structure_state': row.get('daily_structure_state'),
            'm60_structure_state': row.get('m60_structure_state'),
            'poi_type': row.get('poi_type'),
            'has_true_fvg_near': bool(fvgs),
            'fvg_count_near': len(fvgs),
            'ob_fvg_overlap': bool(overlaps and max(overlaps) >= 20.0),
            'max_overlap_pct': round(max(overlaps), 2) if overlaps else 0.0,
            'fvg_reclaim_entry': bool(fvg_entries),
            'fvg_same_entry_date': any(e.get('entry_date') == date_s(row.get('entry_date')) for e in fvg_entries),
            'best_fvg_mid_body_atr': round(max((x['mid_body_atr'] for x in fvgs), default=0.0), 4),
            'pnl_pct': f(row.get('net_pnl_pct'), f(row.get('pnl_pct'))),
            'exit_reason': row.get('exit_reason'),
            'risk_pct': f(row.get('risk_pct')),
            'v85_zone_width_pct': f(row.get('v85_zone_width_pct')),
            'hold_bars': f(row.get('hold_bars')),
        })
    return out


def pnl(row: Dict[str, Any]) -> float:
    return f(row.get('net_pnl_pct'), f(row.get('pnl_pct')))


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rs = list(rows)
    n = len(rs)
    if not n:
        return {'n': 0, 'wr': 0, 'avg': 0, 'sl': 0, 'cum': 0}
    ps = [pnl(r) for r in rs]
    return {
        'n': n,
        'wr': round(sum(1 for x in ps if x > 0) / n * 100, 2),
        'avg': round(sum(ps) / n, 4),
        'sl': round(sum(1 for r in rs if 'SL' in str(r.get('exit_reason')) or pnl(r) < -0.8) / n * 100, 2),
        'cum': round(sum(ps), 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], fn) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(fn(r))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def month_key(r: Dict[str, Any]) -> str:
    return date_s(r.get('entry_date'))[:6]


def year_key(r: Dict[str, Any]) -> str:
    return date_s(r.get('entry_date'))[:4]


def stability(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_m = bucket(rows, month_key)
    by_y = bucket(rows, year_key)
    stable3 = sum(1 for m in by_m.values() if m['n'] >= 3 and m['wr'] >= 60)
    total3 = sum(1 for m in by_m.values() if m['n'] >= 3)
    stable5 = sum(1 for m in by_m.values() if m['n'] >= 5 and m['wr'] >= 60)
    total5 = sum(1 for m in by_m.values() if m['n'] >= 5)
    return {'months': len(by_m), 'stable3': stable3, 'months_n_ge_3': total3, 'stable5': stable5, 'months_n_ge_5': total5, 'by_month': by_m, 'by_year': by_y}


def band(x: Any, cuts: List[float], labels: List[str]) -> str:
    v = f(x, 999.0)
    for c, lab in zip(cuts, labels):
        if v <= c:
            return lab
    return labels[-1]


def main() -> None:
    v85 = load_json(V85_ALL)
    v86 = load_json(V86_TRADES)
    v90 = load_json(V90_ALL)
    v102 = load_json(V102_CAND)
    v102_active = load_json(V102_ACTIVE)

    # POI parallel source audit on production-relevant layers plus full V102 candidate.
    p_v86 = annotate_parallel_poi(v86)
    p_v90 = annotate_parallel_poi(v90)
    p_v102 = annotate_parallel_poi(v102)

    def poi_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            'rows': len(rows),
            'has_true_fvg_near': sum(1 for r in rows if r['has_true_fvg_near']),
            'ob_fvg_overlap': sum(1 for r in rows if r['ob_fvg_overlap']),
            'fvg_reclaim_entry': sum(1 for r in rows if r['fvg_reclaim_entry']),
            'fvg_same_entry_date': sum(1 for r in rows if r['fvg_same_entry_date']),
            'metrics_by_true_fvg': bucket(rows, lambda r: 'HAS_TRUE_FVG' if r['has_true_fvg_near'] else 'NO_TRUE_FVG'),
            'metrics_by_overlap': bucket(rows, lambda r: 'OB_FVG_OVERLAP' if r['ob_fvg_overlap'] else 'NO_OVERLAP'),
            'metrics_by_fvg_reclaim': bucket(rows, lambda r: 'FVG_RECLAIM' if r['fvg_reclaim_entry'] else 'NO_FVG_RECLAIM'),
        }

    cont = [r for r in v102 if r.get('combo_family') == 'CONTINUATION' or 'CONTINUATION' in str(r.get('combo_contract_key') or r.get('event_type'))]
    cont_parallel = annotate_parallel_poi(cont)

    # Continuation subfamily stability from V120 keys.
    groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for r in cont:
        key = (
            r.get('market_state'),
            r.get('daily_structure_state'),
            r.get('m60_structure_state'),
            band(r.get('risk_pct'), [0.8, 1.0, 1.3, 1.5, 2.0, 999], ['<=0.8','0.8-1.0','1.0-1.3','1.3-1.5','1.5-2.0','>2.0']),
            band(r.get('v85_zone_width_pct'), [0.8, 1.0, 1.3, 1.6, 2.0, 999], ['<=0.8','0.8-1.0','1.0-1.3','1.3-1.6','1.6-2.0','>2.0']),
            r.get('v83_takeover_type'),
        )
        groups[key].append(r)

    subfamilies = []
    for key, rows in groups.items():
        if len(rows) >= 5:
            st = stability(rows)
            m = metrics(rows)
            subfamilies.append({
                'key': key,
                **m,
                'months': st['months'],
                'stable3': st['stable3'],
                'months_n_ge_3': st['months_n_ge_3'],
                'stable5': st['stable5'],
                'months_n_ge_5': st['months_n_ge_5'],
                'years': st['by_year'],
            })
    subfamilies.sort(key=lambda x: (x['stable3'], x['wr'], x['avg'], x['n']), reverse=True)

    # Loss autopsy for top continuation subfamilies.
    loss_rows = []
    top_keys = {tuple(x['key']) for x in subfamilies[:8]}
    for r in cont:
        key = (
            r.get('market_state'), r.get('daily_structure_state'), r.get('m60_structure_state'),
            band(r.get('risk_pct'), [0.8, 1.0, 1.3, 1.5, 2.0, 999], ['<=0.8','0.8-1.0','1.0-1.3','1.3-1.5','1.5-2.0','>2.0']),
            band(r.get('v85_zone_width_pct'), [0.8, 1.0, 1.3, 1.6, 2.0, 999], ['<=0.8','0.8-1.0','1.0-1.3','1.3-1.6','1.6-2.0','>2.0']),
            r.get('v83_takeover_type'),
        )
        if key in top_keys and pnl(r) <= 0:
            loss_rows.append({
                'key': ' / '.join(map(str, key)),
                'symbol': r.get('symbol'),
                'entry_date': date_s(r.get('entry_date')),
                'exit_date': date_s(r.get('exit_date')),
                'pnl_pct': pnl(r),
                'exit_reason': r.get('exit_reason'),
                'risk_pct': r.get('risk_pct'),
                'v85_zone_width_pct': r.get('v85_zone_width_pct'),
                'hold_bars': r.get('hold_bars'),
                'market_state': r.get('market_state'),
                'daily_structure_state': r.get('daily_structure_state'),
                'm60_structure_state': r.get('m60_structure_state'),
            })

    summary = {
        'decision': 'READ_ONLY_PARALLEL_POI_AND_CONTINUATION_STABILITY_DONE_NO_CHANGE',
        'production_changed': False,
        'tp_sl_tuning': False,
        'v116_gate_mode': 'SHADOW_ONLY_UNCHANGED',
        'poi_parallel': {
            'v86': poi_summary(p_v86),
            'v90': poi_summary(p_v90),
            'v102_candidate': poi_summary(p_v102),
            'v102_continuation': poi_summary(cont_parallel),
        },
        'v102_continuation': {
            'overall': metrics(cont),
            'stability': stability(cont),
            'subfamilies_n_ge_5': subfamilies,
            'loss_rows_top_subfamilies': loss_rows[:80],
        },
        'v102_active': metrics(v102_active),
    }

    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    with open(OUT / 'parallel_poi_v102_candidate.csv', 'w', newline='', encoding='utf-8') as fh:
        fields = ['symbol','entry_date','event_date','event_type','combo_family','market_state','daily_structure_state','m60_structure_state','poi_type','has_true_fvg_near','fvg_count_near','ob_fvg_overlap','max_overlap_pct','fvg_reclaim_entry','fvg_same_entry_date','best_fvg_mid_body_atr','pnl_pct','exit_reason','risk_pct','v85_zone_width_pct','hold_bars']
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in p_v102:
            w.writerow({k: r.get(k) for k in fields})

    with open(OUT / 'v102_continuation_subfamily_stability.csv', 'w', newline='', encoding='utf-8') as fh:
        fields = ['rank','key','n','wr','avg','sl','cum','months','stable3','months_n_ge_3','stable5','months_n_ge_5','years']
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for i, r in enumerate(subfamilies, 1):
            w.writerow({'rank': i, 'key': ' / '.join(map(str, r['key'])), **{k: r[k] for k in fields if k not in {'rank','key'}}})

    with open(OUT / 'v102_continuation_loss_autopsy.csv', 'w', newline='', encoding='utf-8') as fh:
        fields = ['key','symbol','entry_date','exit_date','pnl_pct','exit_reason','risk_pct','v85_zone_width_pct','hold_bars','market_state','daily_structure_state','m60_structure_state']
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in loss_rows:
            w.writerow(r)

    md = []
    md.append('# V121 Parallel POI + Continuation Stability 只读审计')
    md.append('')
    md.append('Decision: `READ_ONLY_PARALLEL_POI_AND_CONTINUATION_STABILITY_DONE_NO_CHANGE`。未改生产、未调TP/SL、V116继续shadow。')
    md.append('')
    md.append('## 1. Parallel POI 是否真实存在')
    md.append('|层级|rows|true FVG near|OB-FVG overlap|FVG reclaim entry|same entry date|')
    md.append('|---|---:|---:|---:|---:|---:|')
    for name, s in summary['poi_parallel'].items():
        md.append(f"|{name}|{s['rows']}|{s['has_true_fvg_near']}|{s['ob_fvg_overlap']}|{s['fvg_reclaim_entry']}|{s['fvg_same_entry_date']}|")
    md.append('')
    md.append('### V102 candidate: true-FVG 分组表现')
    md.append('|分组|n|WR|Avg|SL|')
    md.append('|---|---:|---:|---:|---:|')
    for k, m in summary['poi_parallel']['v102_candidate']['metrics_by_true_fvg'].items():
        md.append(f"|{k}|{m['n']}|{m['wr']}|{m['avg']}|{m['sl']}|")
    md.append('')
    md.append('## 2. V102 Continuation 稳定性')
    ov = summary['v102_continuation']['overall']
    st = summary['v102_continuation']['stability']
    md.append(f"Continuation overall: n={ov['n']}, WR={ov['wr']}%, Avg={ov['avg']}%, SL={ov['sl']}%。")
    md.append(f"Month stability: months={st['months']}, stable3={st['stable3']}/{st['months_n_ge_3']}, stable5={st['stable5']}/{st['months_n_ge_5']}。")
    md.append('')
    md.append('### Top 子族（n>=5，按 stable3/WR/Avg 排序；审计用不生产）')
    md.append('|rank|key|n|WR|Avg|SL|months|stable3|stable5|')
    md.append('|---:|---|---:|---:|---:|---:|---:|---:|---:|')
    for i, r in enumerate(subfamilies[:15], 1):
        md.append(f"|{i}|{' / '.join(map(str, r['key']))}|{r['n']}|{r['wr']}|{r['avg']}|{r['sl']}|{r['months']}|{r['stable3']}/{r['months_n_ge_3']}|{r['stable5']}/{r['months_n_ge_5']}|")
    md.append('')
    md.append('## 3. Top 子族亏损归因样本')
    md.append('|key|symbol|entry|exit|pnl|reason|risk|width|hold|')
    md.append('|---|---|---|---|---:|---|---:|---:|---:|')
    for r in loss_rows[:30]:
        md.append(f"|{r['key']}|{r['symbol']}|{r['entry_date']}|{r['exit_date']}|{r['pnl_pct']}|{r['exit_reason']}|{r['risk_pct']}|{r['v85_zone_width_pct']}|{r['hold_bars']}|")
    if not loss_rows:
        md.append('| none | | | | | | | | |')
    md.append('')
    md.append('## 4. 结论')
    md.append('1. 当前 `DEMAND_OB` 候选附近确实能找到部分 true FVG / OB-FVG overlap，但它们没有作为一等 POI 源进入候选生成器。')
    md.append('2. `same entry date` 数量很低，说明不能简单把 OB 行贴上 FVG 标签；需要并行生成 true FVG candidate，而不是事后改名。')
    md.append('3. V102 continuation 子族存在局部高质量，但月度稳定性仍不足；下一步应对 top 子族做去重+月份覆盖+FVG并行源回测。')
    md.append('4. V116 继续 shadow；daily scanner 未输出 true FVG source 前，不做生产 hard reject。')
    (OUT / 'report.md').write_text('\n'.join(md) + '\n', encoding='utf-8')

    print(json.dumps({
        'out': str(OUT),
        'decision': summary['decision'],
        'poi_parallel_counts': {k: {kk: vv for kk, vv in v.items() if kk in {'rows','has_true_fvg_near','ob_fvg_overlap','fvg_reclaim_entry','fvg_same_entry_date'}} for k, v in summary['poi_parallel'].items()},
        'continuation_overall': ov,
        'top_subfamilies': subfamilies[:5],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
