#!/usr/bin/env python3
"""V173: next quality frontier after V172.

Read-only research materialization. No production/frontend/watchlist writes.

Goal:
- Verify whether any scanner-time-only gate can produce a *new qualitative* improvement over V172.
- Separate production-upgrade candidates from research-only overlays to prevent endless iteration.

Acceptance:
- Production upgrade: n>=200, min_year_n>=35, WR>=84, AvgPnL>=6.2, micro<=1, T+1=0, all year WR>=82.
- Research overlay: n>=150, min_year_n>=25, WR>=85, AvgPnL>=6.0, micro<=1, T+1=0, all year WR>=83.
- Otherwise unusable for promotion.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path('/root/.hermes')
SRC = ROOT / 'smc_opt_v167_exact_scanner_gate' / 'v167_trades.json'
PICKS_SRC = ROOT / 'smc_opt_v172_v167_high_quality_gate' / 'v172_active_picks.json'
OUT = ROOT / 'smc_audit' / 'v173_v172_next_quality_frontier_20260623'
OUT.mkdir(parents=True, exist_ok=True)

PROD_UPGRADE = {'n': 200, 'min_year_n': 35, 'wr': 84.0, 'avg': 6.2, 'micro': 1.0, 'all_year_wr': 82.0, 't1': 0}
RESEARCH_OVERLAY = {'n': 150, 'min_year_n': 25, 'wr': 85.0, 'avg': 6.0, 'micro': 1.0, 'all_year_wr': 83.0, 't1': 0}

NON_OUTCOME_FIELDS = [
    'risk_pct','v85_zone_width_pct','v132_post_zone_pullback_depth_pct_3','v132_reclaim_bull_body_pct',
    'v132_reclaim_close_above_zone_high_pct','v132_reclaim_close_pos_pct','entry_chase_above_zone_pct',
    'touch_to_reclaim_bars','v132_bull_count_3',
]


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, '') or (isinstance(v, float) and math.isnan(v)):
            return default
        return float(v)
    except Exception:
        return default


def dkey(v: Any) -> str:
    return ''.join(ch for ch in str(v or '') if ch.isdigit())[:8]


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def v172_gate(r: dict[str, Any]) -> bool:
    return fnum(r.get('v85_zone_width_pct')) >= 2.0 and fnum(r.get('v132_post_zone_pullback_depth_pct_3'), 999.0) <= 2.0


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {'n':0,'wr':0.0,'avg':0.0,'median':0.0,'loss_n':0,'sl_rate':0.0,'tp_rate':0.0,'time_rate':0.0,'micro':0.0,'min_year_n':0,'year_counts':{},'year_wr':{},'all_year_wr_min':0.0,'t1':0}
    vals = [fnum(r.get('pnl_pct')) for r in rows]
    years: dict[str, list[float]] = defaultdict(list)
    exits = Counter(str(r.get('exit_reason') or '').upper() for r in rows)
    for r, v in zip(rows, vals):
        y = dkey(r.get('entry_date'))[:4]
        if y:
            years[y].append(v)
    year_counts = {y: len(vs) for y, vs in sorted(years.items())}
    year_wr = {y: round(sum(v > 0 for v in vs) / len(vs) * 100.0, 2) for y, vs in sorted(years.items()) if vs}
    return {
        'n': n,
        'wr': round(sum(v > 0 for v in vals) / n * 100.0, 2),
        'avg': round(sum(vals) / n, 4),
        'median': round(median(vals), 4),
        'loss_n': sum(v <= 0 for v in vals),
        'sl_rate': round((exits.get('SL', 0) + exits.get('GAP_SL', 0)) / n * 100.0, 2),
        'tp_rate': round(exits.get('TP', 0) / n * 100.0, 2),
        'time_rate': round(exits.get('TIME', 0) / n * 100.0, 2),
        'micro': round(sum(0 < v <= 0.55 for v in vals) / n * 100.0, 2),
        'min_year_n': min(year_counts.values()) if year_counts else 0,
        'year_counts': year_counts,
        'year_wr': year_wr,
        'all_year_wr_min': min(year_wr.values()) if year_wr else 0.0,
        't1': sum(1 for r in rows if r.get('t1_violation') is True or (dkey(r.get('exit_date')) and dkey(r.get('entry_date')) >= dkey(r.get('exit_date')))),
    }


def classify(m: dict[str, Any]) -> str:
    p = PROD_UPGRADE
    if m['n'] >= p['n'] and m['min_year_n'] >= p['min_year_n'] and m['wr'] >= p['wr'] and m['avg'] >= p['avg'] and m['micro'] <= p['micro'] and m['all_year_wr_min'] >= p['all_year_wr'] and m['t1'] == 0:
        return 'PRODUCTION_UPGRADE_USABLE'
    r = RESEARCH_OVERLAY
    if m['n'] >= r['n'] and m['min_year_n'] >= r['min_year_n'] and m['wr'] >= r['wr'] and m['avg'] >= r['avg'] and m['micro'] <= r['micro'] and m['all_year_wr_min'] >= r['all_year_wr'] and m['t1'] == 0:
        return 'RESEARCH_OVERLAY_USABLE'
    return 'UNUSABLE_FOR_PROMOTION'


def make_conditions():
    conds = []
    def add(name, pred):
        conds.append((name, pred))
    for lo, hi in [(3,8),(4,8),(5,8),(4,7),(5,7)]:
        add(f'risk_{lo}_{hi}', lambda r, lo=lo, hi=hi: lo <= fnum(r.get('risk_pct')) <= hi)
    for th in [2.5,3,3.5,4,5]:
        add(f'zone_width>={th}', lambda r, th=th: fnum(r.get('v85_zone_width_pct')) >= th)
    for th in [0,0.5,1,1.5]:
        add(f'pullback3<={th}', lambda r, th=th: fnum(r.get('v132_post_zone_pullback_depth_pct_3'), 999.0) <= th)
    for th in [45,50,55,60]:
        add(f'bull_body<={th}', lambda r, th=th: fnum(r.get('v132_reclaim_bull_body_pct')) <= th)
    for th in [0.5,1,1.5,2,3]:
        add(f'reclaim_above>={th}', lambda r, th=th: fnum(r.get('v132_reclaim_close_above_zone_high_pct')) >= th)
    for th in [80,85,90,95]:
        add(f'reclaim_pos>={th}', lambda r, th=th: fnum(r.get('v132_reclaim_close_pos_pct')) >= th)
    for th in [0,0.5,1,1.5,2]:
        add(f'entry_chase<={th}', lambda r, th=th: fnum(r.get('entry_chase_above_zone_pct')) <= th)
    for th in [1,2,3]:
        add(f'touch_bars<={th}', lambda r, th=th: fnum(r.get('touch_to_reclaim_bars')) <= th)
    for th in [1,2,3]:
        add(f'bull_count3>={th}', lambda r, th=th: fnum(r.get('v132_bull_count_3')) >= th)
    return conds


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(rows)


def main() -> None:
    all_rows = load_json(SRC, [])
    if not isinstance(all_rows, list) or not all_rows:
        raise SystemExit(f'missing source {SRC}')
    base = [r for r in all_rows if str(r.get('entry_date'))[:4] >= '2023']
    v172_rows = [r for r in base if v172_gate(r)]
    conds = make_conditions()
    candidates: list[dict[str, Any]] = []
    best_rows: list[dict[str, Any]] = []
    best_rule = ''

    for size in [0,1,2,3]:
        combos = [()] if size == 0 else itertools.combinations(conds, size)
        for combo in combos:
            names = [c[0] for c in combo]
            rows = v172_rows
            for _, pred in combo:
                rows = [r for r in rows if pred(r)]
            if len(rows) < 120:
                continue
            m = metrics(rows)
            cls = classify(m)
            if cls != 'UNUSABLE_FOR_PROMOTION' or (m['n'] >= 150 and m['avg'] >= 6.0 and m['wr'] >= 82):
                rec = {
                    'rule': 'V172' + ((' + ' + ' AND '.join(names)) if names else ''),
                    'extra_gate_count': size,
                    **m,
                    'classification': cls,
                }
                candidates.append(rec)
                if not best_rows or (cls != 'UNUSABLE_FOR_PROMOTION', m['wr'], m['avg'], m['n']) > (classify(metrics(best_rows)) != 'UNUSABLE_FOR_PROMOTION', metrics(best_rows)['wr'], metrics(best_rows)['avg'], metrics(best_rows)['n']):
                    best_rows = rows
                    best_rule = rec['rule']

    candidates.sort(key=lambda x: (x['classification'] != 'PRODUCTION_UPGRADE_USABLE', x['classification'] != 'RESEARCH_OVERLAY_USABLE', -x['wr'], -x['avg'], -x['n']))
    prod = [c for c in candidates if c['classification'] == 'PRODUCTION_UPGRADE_USABLE']
    research = [c for c in candidates if c['classification'] == 'RESEARCH_OVERLAY_USABLE']
    best_research = research[0] if research else None
    # materialize the exact top candidate with the same predicate set used during search.
    # Store predicates alongside their names so we do not parse/eval rule strings.
    material_rule = (best_research or (candidates[0] if candidates else {'rule':'NONE'}))['rule']
    selected_names: list[str] = []
    if material_rule.startswith('V172 + '):
        selected_names = [x.strip() for x in material_rule.split('V172 + ', 1)[1].split(' AND ')]
    pred_by_name = {name: pred for name, pred in conds}
    def selected_pass(r: dict[str, Any]) -> bool:
        return v172_gate(r) and all(pred_by_name[name](r) for name in selected_names if name in pred_by_name)
    material_rows = [r for r in base if selected_pass(r)] if selected_names else best_rows

    picks0 = load_json(PICKS_SRC, [])
    picks_v173 = [p for p in picks0 if selected_pass(p)] if isinstance(picks0, list) else []

    decision = 'V173_NO_PRODUCTION_UPGRADE__KEEP_V172_DEFAULT'
    if prod:
        decision = 'V173_PRODUCTION_UPGRADE_FOUND__REQUIRES_PROMOTION_DRYRUN'
    elif research:
        decision = 'V173_RESEARCH_OVERLAY_FOUND__DO_NOT_PROMOTE_PRODUCTION'

    report = {
        'decision': decision,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': str(SRC),
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'acceptance': {'production_upgrade': PROD_UPGRADE, 'research_overlay': RESEARCH_OVERLAY},
        'non_outcome_fields_used': NON_OUTCOME_FIELDS,
        'base_v167': metrics(base),
        'base_v172': metrics(v172_rows),
        'production_upgrade_count': len(prod),
        'research_overlay_count': len(research),
        'best_production': prod[0] if prod else None,
        'best_research': best_research,
        'top_candidates': candidates[:30],
        'materialized_rule': material_rule,
        'materialized_metrics': metrics(material_rows),
        'materialized_pick_count': len(picks_v173),
        'current_direction': f'Keep V172 as production default. Use V173 only as a high-conviction overlay under: {material_rule}. Next material research should not add more scalar gates; it should rebuild structure hierarchy/P4 wave-break layer because scalar gates hit coverage ceiling.',
        'unusable_boundary': 'Any rule below production_upgrade thresholds is not allowed to replace V172. Research overlay is allowed only as secondary label, not production default.',
    }
    (OUT / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    write_csv(OUT / 'v173_candidates.csv', candidates)
    write_csv(OUT / 'v173_materialized_rows.csv', material_rows)
    (OUT / 'v173_materialized_rows.json').write_text(json.dumps(material_rows, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'v173_overlay_picks.json').write_text(json.dumps(picks_v173, ensure_ascii=False, indent=2), encoding='utf-8')
    md = [
        '# V173 V172下一质量边界研究', '',
        f"Decision: **{decision}**", '',
        '## 可用/不可用预定义',
        f"- 生产升级可用: `{PROD_UPGRADE}`",
        f"- 研究叠加可用: `{RESEARCH_OVERLAY}`",
        '- 低于上述：不可替代V172，不进生产。', '',
        '## 结果',
        '|对象|n|WR|Avg|SL率|min_year|all_year_wr_min|结论|',
        '|---|---:|---:|---:|---:|---:|---:|---|',
        f"|V167|{report['base_v167']['n']}|{report['base_v167']['wr']}%|{report['base_v167']['avg']}%|{report['base_v167']['sl_rate']}%|{report['base_v167']['min_year_n']}|{report['base_v167']['all_year_wr_min']}%|生产基线|",
        f"|V172|{report['base_v172']['n']}|{report['base_v172']['wr']}%|{report['base_v172']['avg']}%|{report['base_v172']['sl_rate']}%|{report['base_v172']['min_year_n']}|{report['base_v172']['all_year_wr_min']}%|当前默认|",
    ]
    if best_research:
        md.append(f"|V173研究叠加|{best_research['n']}|{best_research['wr']}%|{best_research['avg']}%|{best_research['sl_rate']}%|{best_research['min_year_n']}|{best_research['all_year_wr_min']}%|{best_research['classification']}|")
        md += ['', '## 最佳研究叠加规则', f"`{best_research['rule']}`"]
    md += ['', '## 结论', report['current_direction'], '', f"Artifacts: `{OUT}`"]
    (OUT / 'report.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['decision','base_v167','base_v172','production_upgrade_count','research_overlay_count','best_production','best_research','materialized_metrics','materialized_pick_count','current_direction']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
