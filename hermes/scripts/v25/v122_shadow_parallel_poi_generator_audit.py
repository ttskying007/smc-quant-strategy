#!/usr/bin/env python3
"""V122 read-only shadow parallel POI generator audit.

Builds first-class parallel POI rows from the same raw SMC events:
- DEMAND_OB (existing V81/V85 source)
- FVG_Demand (true three-bar demand FVG)
- OB+FVG (overlap/intersection of OB and FVG zones)

No production writes. No API/frontend/watchlist changes. No TP/SL tuning.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from v81_contextual_smc_generator import (
    _date,
    classify_context,
    detect_event,
    f,
    locate_entry,
    locate_poi,
    next_exit_semantic,
)
from v85_mixed_accumulation_generator import (
    _env_state,
    _expanded_bos_event,
    classify_mixed_after_poi,
    zone_width_pct,
)
from v83_post_reclaim_takeover_gate import evaluate_post_reclaim_takeover

ROOT = Path('/root/.hermes')
KLINE_DIR = ROOT / 'kline_cache'
ENV_PATH = ROOT / 'smc_opt_v74_env_state_machine' / 'v74_env_by_date.json'
OUT = ROOT / 'smc_audit' / 'v122_shadow_parallel_poi_generator_20260620'
OUT.mkdir(parents=True, exist_ok=True)


def jload(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def symbol_from_path(path: Path) -> str:
    parts = path.name.replace('_daily_750.json', '').split('_')
    return f'{parts[0]}.{parts[1]}' if len(parts) == 2 else path.stem


def v(b: Dict[str, Any], key: str) -> float:
    return f(b.get(key))


def ds(x: Any) -> str:
    return ''.join(ch for ch in str(x or '') if ch.isdigit())[:8]


def normalize_env(row: Dict[str, Any]) -> Dict[str, Any]:
    nr = dict(row or {})
    nr['market_state'] = row.get('market_state_v74') or row.get('market_state') or row.get('state') or ''
    return nr


def atr(ks: List[Dict[str, Any]], idx: int, n: int = 14) -> float:
    vals: List[float] = []
    for i in range(max(1, idx - n + 1), min(idx + 1, len(ks))):
        vals.append(max(v(ks[i], 'h') - v(ks[i], 'l'), abs(v(ks[i], 'h') - v(ks[i - 1], 'c')), abs(v(ks[i], 'l') - v(ks[i - 1], 'c'))))
    return sum(vals) / len(vals) if vals else 0.0


def overlap_pct(a_low: float, a_high: float, b_low: float, b_high: float) -> float:
    inter = max(0.0, min(a_high, b_high) - max(a_low, b_low))
    base = max(min(a_high - a_low, b_high - b_low), 1e-9)
    return inter / base * 100.0


def source_start_bar(event: Dict[str, Any], event_idx: int) -> int:
    for key in ('sweep_idx', 'broken_high_bar', 'swing_low_idx'):
        if event.get(key) not in (None, ''):
            return int(f(event.get(key), event_idx))
    return max(0, event_idx - 5)


def fvg_near_event(ks: List[Dict[str, Any]], event: Dict[str, Any]) -> List[Dict[str, Any]]:
    event_idx = int(f(event.get('event_idx'), -1))
    if event_idx < 2:
        return []
    start = source_start_bar(event, event_idx)
    lo = max(start + 2, event_idx - 2)
    hi = min(event_idx + 3, len(ks))
    out: List[Dict[str, Any]] = []
    for i in range(lo, hi):
        h0, l2, a = v(ks[i - 2], 'h'), v(ks[i], 'l'), atr(ks, i)
        if h0 > 0 and l2 > h0 and (l2 - h0) >= a * 0.20:
            mid = ks[i - 1]
            out.append({
                'valid': True,
                'poi_type': 'FVG_Demand',
                'zone_idx': i - 1,
                'zone_date': _date(mid),
                'zone_low': round(h0, 6),
                'zone_high': round(l2, 6),
                'source_mid_body_atr': round((v(mid, 'c') - v(mid, 'o')) / max(a, 1e-9), 4),
                'source_mid_range_atr': round((v(mid, 'h') - v(mid, 'l')) / max(a, 1e-9), 4),
                'source_gap_atr': round((l2 - h0) / max(a, 1e-9), 4),
            })
    return out


def enrich_poi_geometry(ks: List[Dict[str, Any]], event: Dict[str, Any], poi: Dict[str, Any], env: Dict[str, Any]) -> Dict[str, Any]:
    nr = dict(poi)
    event_idx = int(f(event.get('event_idx'), -1))
    zl, zh = f(nr.get('zone_low')), f(nr.get('zone_high'))
    swing_low_idx = int(f(event.get('swing_low_idx'), max(0, event_idx - 5)))
    swing_high_idx = int(f(event.get('swing_high_idx'), event_idx))
    a, b = min(swing_low_idx, swing_high_idx), max(swing_low_idx, swing_high_idx)
    swing_low = min((v(x, 'l') for x in ks[a:b + 1]), default=zl)
    swing_high = max((v(x, 'h') for x in ks[a:b + 1]), default=zh)
    eq = swing_low + (swing_high - swing_low) * 0.5
    discount = swing_low + (swing_high - swing_low) * 0.79
    if zh <= eq:
        pd_zone = 'DEEP_DISCOUNT'
    elif zh <= discount:
        pd_zone = 'DISCOUNT'
    else:
        nr.update({'valid': False, 'reason': 'POI_NOT_IN_DISCOUNT'})
        return nr
    prior = min((v(x, 'l') for x in ks[max(0, int(f(nr.get('zone_idx'), event_idx)) - 6):int(f(nr.get('zone_idx'), event_idx))]), default=zl)
    min_price = max(v(ks[event_idx], 'h'), zh) if 0 <= event_idx < len(ks) else zh
    target = min_price
    for j in range(event_idx + 1, min(len(ks), event_idx + 21)):
        if v(ks[j], 'h') > min_price:
            target = v(ks[j], 'h')
            break
    nr.update({
        'valid': True,
        'pd_zone': pd_zone,
        'equilibrium': round(eq, 6),
        'prior_structure_low': round(prior, 6),
        'liquidity_target': round(target, 6),
        'source_event': event.get('event_type'),
    })
    return nr


def overlap_poi(ob: Dict[str, Any], fvg: Dict[str, Any]) -> Dict[str, Any] | None:
    pct = overlap_pct(f(ob.get('zone_low')), f(ob.get('zone_high')), f(fvg.get('zone_low')), f(fvg.get('zone_high')))
    if pct < 20.0:
        return None
    low = max(f(ob.get('zone_low')), f(fvg.get('zone_low')))
    high = min(f(ob.get('zone_high')), f(fvg.get('zone_high')))
    if not (low > 0 and high > low):
        return None
    nr = dict(fvg)
    nr.update({
        'poi_type': 'OB+FVG',
        'zone_low': round(low, 6),
        'zone_high': round(high, 6),
        'ob_fvg_overlap_pct': round(pct, 2),
        'ob_zone_idx': ob.get('zone_idx'),
        'fvg_zone_idx': fvg.get('zone_idx'),
    })
    return nr


def simulate_trade(c: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    entry_idx = int(c['entry_idx'])
    entry = f(c.get('entry_price'))
    poi = {
        'zone_low': c.get('zone_low'),
        'zone_high': c.get('zone_high'),
        'prior_structure_low': c.get('prior_structure_low'),
        'liquidity_target': c.get('liquidity_target'),
    }
    horizon = ks[entry_idx:min(len(ks), entry_idx + 21)]
    if len(horizon) <= 1:
        b = ks[min(entry_idx, len(ks) - 1)]
        exit_idx, exit_date, exit_price, reason = min(entry_idx, len(ks) - 1), _date(b), f(b.get('c')), 'NO_T1_EXIT_BAR_AVAILABLE'
    else:
        ex = next_exit_semantic(horizon, poi, 1)
        if ex.get('exit_idx') is None:
            local = len(horizon) - 1
            b = horizon[local]
            exit_idx, exit_date, exit_price, reason = entry_idx + local, _date(b), f(b.get('c')), 'TIME_STOP_NO_SEMANTIC_EXIT'
        else:
            exit_idx = entry_idx + int(ex['exit_idx'])
            exit_date, exit_price, reason = ex.get('exit_date'), f(ex.get('exit_price')), ex.get('exit_signal')
    if ds(exit_date) == ds(c.get('entry_date')) and exit_idx + 1 < len(ks):
        exit_idx += 1
        b = ks[exit_idx]
        exit_date, exit_price, reason = _date(b), f(b.get('c')), f'{reason}_T1_SHIFTED'
    pnl = (exit_price / entry - 1) * 100 if entry else 0.0
    risk = (entry / f(c.get('zone_low'), entry) - 1) * 100 if f(c.get('zone_low')) else 0.0
    out = dict(c)
    out.update({
        'exit_idx': exit_idx,
        'exit_date': exit_date,
        'exit_price': round(exit_price, 6),
        'exit_reason': reason,
        'pnl_pct': round(pnl, 4),
        'hold_bars': max(0, exit_idx - entry_idx),
        'risk_pct': round(risk, 4),
        'v85_zone_width_pct': round(zone_width_pct(c), 4),
        'select_date': c.get('event_date'),
        'pick_date': c.get('event_date'),
        'join_date': c.get('entry_date'),
        'zone_type': c.get('poi_type'),
        'signal_type': c.get('event_type'),
    })
    out.update(evaluate_post_reclaim_takeover(out, ks))
    if str(out.get('exit_reason')).startswith('NO_T1_EXIT_BAR_AVAILABLE'):
        out['invalid_reason'] = 'NO_T1_EXIT_BAR_AVAILABLE'
        return out
    mixed = classify_mixed_after_poi(ks, out, out.get('market_state', ''))
    out.update(mixed)
    return out


def candidate_from_poi(symbol: str, ks: List[Dict[str, Any]], env: Dict[str, Any], context: Dict[str, Any], event: Dict[str, Any], poi: Dict[str, Any], source: str, max_wait: int = 8) -> Dict[str, Any] | None:
    event_idx = int(f(event.get('event_idx'), -1))
    if not poi.get('valid') or event_idx < 0:
        return None
    entry = locate_entry(ks, poi, event_idx, max_wait=max_wait)
    if not entry.get('entry_valid'):
        return None
    story = 'UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM' if event.get('event_type') == 'BOS_CONTINUATION' else 'DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM'
    row = {
        'symbol': symbol,
        'story': story,
        'poi_source': source,
        'market_state': _env_state(env),
        **context,
        **event,
        **poi,
        **entry,
    }
    out = simulate_trade(row, ks)
    if out.get('invalid_reason') == 'NO_T1_EXIT_BAR_AVAILABLE':
        return None
    return out


def event_records(symbol: str, ks: List[Dict[str, Any]], env_by_date: Dict[str, Dict[str, Any]]) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
    for idx in range(4, max(0, len(ks) - 2)):
        env = env_by_date.get(str(_date(ks[idx]))[:8], {})
        ctx = classify_context(ks, idx, env, lookback=5)
        if ctx.get('environment_permission') == 'BLOCKED':
            continue
        ev = detect_event(ks, idx, ctx, lookback=5)
        if ev.get('event_type') != 'NO_VALID_SMC_EVENT':
            yield env, ctx, ev
    for lookback in (5, 8, 13):
        for idx in range(max(lookback - 1, 3), max(0, len(ks) - 2)):
            env = env_by_date.get(str(_date(ks[idx]))[:8], {})
            if _env_state(env) not in {'BULL_CONTINUATION', 'RECOVERY', 'ACCUMULATION', 'MIXED'}:
                continue
            ev = _expanded_bos_event(ks, idx, lookback)
            if ev.get('event_type') == 'NO_VALID_SMC_EVENT':
                continue
            ctx = {
                'environment_permission': 'DEMAND_CONTINUATION_OR_REVERSAL',
                'environment_allows_demand': True,
                'trend_regime': 'UP_CONTINUATION',
                'trend_reason': f'V122_EXPANDED_BOS_{lookback}',
            }
            yield env, ctx, ev


def generate_parallel(symbol: str, ks: List[Dict[str, Any]], env_by_date: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen_event = set()
    for env, ctx, ev in event_records(symbol, ks, env_by_date):
        event_idx = int(f(ev.get('event_idx'), -1))
        event_key = (event_idx, ev.get('event_type'), ev.get('trend_reason'))
        if event_key in seen_event:
            continue
        seen_event.add(event_key)
        ob = locate_poi(ks, ev, env)
        ob_valid = ob if ob.get('valid') else None
        if ob_valid:
            row = candidate_from_poi(symbol, ks, env, ctx, ev, ob_valid, 'DEMAND_OB')
            if row:
                rows.append(row)
        fvgs = [enrich_poi_geometry(ks, ev, x, env) for x in fvg_near_event(ks, ev)]
        fvgs = [x for x in fvgs if x.get('valid')]
        for fvg in fvgs[:2]:
            row = candidate_from_poi(symbol, ks, env, ctx, ev, fvg, 'FVG_Demand')
            if row:
                rows.append(row)
            if ob_valid:
                combo = overlap_poi(ob_valid, fvg)
                if combo:
                    combo = enrich_poi_geometry(ks, ev, combo, env)
                    row2 = candidate_from_poi(symbol, ks, env, ctx, ev, combo, 'OB+FVG')
                    if row2:
                        rows.append(row2)
    return rows


def dedupe(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rank = {'OB+FVG': 0, 'FVG_Demand': 1, 'DEMAND_OB': 2}
    best: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for r in rows:
        key = (r.get('symbol'), ds(r.get('entry_date')), str(r.get('poi_source')))
        score = (
            rank.get(str(r.get('poi_source')), 9),
            f(r.get('risk_pct'), 999),
            f(r.get('v85_zone_width_pct'), 999),
            abs(int(f(r.get('hold_bars'), 99)) - 2),
            ds(r.get('event_date')),
        )
        old = best.get(key)
        if old is None:
            r['_dedupe_score'] = score
            best[key] = r
        elif score < old.get('_dedupe_score'):
            r['_dedupe_score'] = score
            best[key] = r
    return list(best.values())


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


def bucket(rows: Iterable[Dict[str, Any]], keyfn) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(keyfn(r))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def stable(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_m = bucket(rows, lambda r: ds(r.get('entry_date'))[:6])
    by_y = bucket(rows, lambda r: ds(r.get('entry_date'))[:4])
    return {
        'months': len(by_m),
        'stable3': sum(1 for x in by_m.values() if x['n'] >= 3 and x['wr'] >= 60),
        'months_n_ge_3': sum(1 for x in by_m.values() if x['n'] >= 3),
        'stable5': sum(1 for x in by_m.values() if x['n'] >= 5 and x['wr'] >= 60),
        'months_n_ge_5': sum(1 for x in by_m.values() if x['n'] >= 5),
        'by_year': by_y,
    }


def v86_pass(r: Dict[str, Any]) -> bool:
    return 1.0 < f(r.get('v85_zone_width_pct')) <= 1.6 and 1.0 < f(r.get('risk_pct')) <= 1.5 and f(r.get('hold_bars')) <= 2 and r.get('v83_takeover_type') == 'HOLD_ABOVE_POI' and ds(r.get('entry_date')) != ds(r.get('exit_date'))


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    with path.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> None:
    env_raw = jload(ENV_PATH)
    env_by_date = {str(k)[:8]: normalize_env(v) for k, v in env_raw.items()}
    raw: List[Dict[str, Any]] = []
    scanned = 0
    for path in sorted(KLINE_DIR.glob('*_daily_750.json')):
        ks = jload(path)
        if len(ks) < 100:
            continue
        sym = symbol_from_path(path)
        raw.extend(generate_parallel(sym, ks, env_by_date))
        scanned += 1
    rows = dedupe(raw)
    for r in rows:
        r['v86_contract_pass_shadow'] = v86_pass(r)
        r['combo_family'] = 'CONTINUATION' if r.get('event_type') == 'BOS_CONTINUATION' else 'REVERSAL'
    by_source = bucket(rows, lambda r: r.get('poi_source'))
    by_source_v86 = {src: metrics([r for r in rows if r.get('poi_source') == src and r.get('v86_contract_pass_shadow')]) for src in sorted({r.get('poi_source') for r in rows})}
    cont = [r for r in rows if r.get('combo_family') == 'CONTINUATION']
    rev = [r for r in rows if r.get('combo_family') == 'REVERSAL']
    t1_viol = [r for r in rows if ds(r.get('entry_date')) == ds(r.get('exit_date'))]
    sub = bucket(rows, lambda r: f"{r.get('poi_source')}|{r.get('combo_family')}|{r.get('market_state')}|{r.get('daily_structure_state')}|{r.get('m60_structure_state')}|{r.get('v83_takeover_type')}")
    top = sorted(([{'key': k, **v} for k, v in sub.items() if v['n'] >= 20]), key=lambda x: (-x['wr'], -x['avg'], -x['n']))[:20]

    fields = ['symbol','poi_source','combo_family','event_type','event_date','zone_date','entry_date','exit_date','pnl_pct','exit_reason','risk_pct','v85_zone_width_pct','hold_bars','v83_takeover_type','market_state','daily_structure_state','m60_structure_state','source_mid_body_atr','source_gap_atr','ob_fvg_overlap_pct','v86_contract_pass_shadow']
    write_csv(OUT / 'parallel_poi_candidates_dedup.csv', rows, fields)
    write_csv(OUT / 'parallel_poi_v86_shadow_pass.csv', [r for r in rows if r.get('v86_contract_pass_shadow')], fields)
    write_csv(OUT / 'parallel_poi_top_losses.csv', sorted([r for r in rows if f(r.get('pnl_pct')) <= 0], key=lambda r: f(r.get('pnl_pct')))[:200], fields)

    summary = {
        'decision': 'READ_ONLY_SHADOW_PARALLEL_POI_GENERATOR_DONE_NO_CHANGE',
        'scanned_symbols': scanned,
        'raw_rows_before_dedupe': len(raw),
        'dedup_rows': len(rows),
        't1_violations': len(t1_viol),
        'overall': metrics(rows),
        'by_source': by_source,
        'by_source_v86_shadow_pass': by_source_v86,
        'continuation': metrics(cont),
        'reversal': metrics(rev),
        'stability_by_source': {src: stable([r for r in rows if r.get('poi_source') == src]) for src in sorted({r.get('poi_source') for r in rows})},
        'top_subfamilies_n20': top,
        'no_production_change': True,
        'v116_remains_shadow': True,
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = []
    lines.append('# V122 Shadow Parallel POI Generator 只读审计')
    lines.append('')
    lines.append('Decision: `READ_ONLY_SHADOW_PARALLEL_POI_GENERATOR_DONE_NO_CHANGE`。未改生产、未调TP/SL、V116继续shadow。')
    lines.append('')
    lines.append(f"Scanned symbols: {scanned}; raw rows: {len(raw)}; dedup rows: {len(rows)}; T+1 violations: {len(t1_viol)}.")
    lines.append('')
    lines.append('## 1. 并行POI一等源结果')
    lines.append('|POI源|n|WR|Avg|SL|TP|Cum|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for src, m in by_source.items():
        lines.append(f"|{src}|{m['n']}|{m['wr']}|{m['avg']}|{m['sl']}|{m['tp']}|{m['cum']}|")
    lines.append('')
    lines.append('## 2. V86 shadow contract pass')
    lines.append('|POI源|n|WR|Avg|SL|TP|Cum|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for src, m in by_source_v86.items():
        lines.append(f"|{src}|{m['n']}|{m['wr']}|{m['avg']}|{m['sl']}|{m['tp']}|{m['cum']}|")
    lines.append('')
    lines.append('## 3. Continuation / Reversal')
    lines.append('|Family|n|WR|Avg|SL|TP|Cum|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for name, m in [('CONTINUATION', metrics(cont)), ('REVERSAL', metrics(rev))]:
        lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['sl']}|{m['tp']}|{m['cum']}|")
    lines.append('')
    lines.append('## 4. 月度稳定')
    lines.append('|POI源|months|stable3|stable5|')
    lines.append('|---|---:|---:|---:|')
    for src, st in summary['stability_by_source'].items():
        lines.append(f"|{src}|{st['months']}|{st['stable3']}/{st['months_n_ge_3']}|{st['stable5']}/{st['months_n_ge_5']}|")
    lines.append('')
    lines.append('## 5. Top 子族 n>=20')
    lines.append('|rank|key|n|WR|Avg|SL|TP|')
    lines.append('|---:|---|---:|---:|---:|---:|---:|')
    for i, r in enumerate(top[:12], 1):
        lines.append(f"|{i}|{r['key']}|{r['n']}|{r['wr']}|{r['avg']}|{r['sl']}|{r['tp']}|")
    lines.append('')
    lines.append('## 6. 结论')
    lines.append('1. 本轮首次把 `DEMAND_OB / FVG_Demand / OB+FVG` 作为一等并行POI源从raw event层生成；不是事后贴标签。')
    lines.append('2. `FVG_Demand` 与 `OB+FVG` 的质量必须按自己的entry/reclaim/T+1路径判断，不能复用OB候选结果。')
    lines.append('3. V86 shadow pass 只是研究对照；没有写入V90/V102/watchlist/API。')
    lines.append('4. V116继续shadow；生产前仍需稳定性、去重、source contract和前端字段闭环。')
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(OUT), 'decision': summary['decision'], 'dedup_rows': len(rows), 'by_source': by_source, 't1_violations': len(t1_viol)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
