#!/usr/bin/env python3
"""V77 recovery-quality state machine audit.

V76 proved that environment persistence helps, but RECOVERY remains too broad.
This script adds the next signal-layer state split:

1. Market story remains separate: continuation, reversal, transition.
2. RECOVERY is split into true recovery vs weak rebound using only pre-entry facts:
   - clean 10-day environment history (no distribution after recent demand-valid regime),
   - enough demand-valid days in the prior environment window,
   - stock-level HH/HL improvement before entry,
   - POI durability before entry (no close below POI),
   - bounded entry risk.
3. Search is reported as an audit, not production promotion.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

KLINE_DIR = Path('/root/.hermes/kline_cache')
V75_DIR = Path('/root/.hermes/smc_opt_v75_post_entry_invalidation')
V76_DIR = Path('/root/.hermes/smc_opt_v76_env_persistence_story_machine')
OUT_DIR = Path('/root/.hermes/smc_opt_v77_recovery_quality_state_machine')
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORE_STORIES = {
    'UP_CONTINUATION_BOS_POI_RECLAIM',
    'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM',
    'BULL_TRANSITION_POI_RECLAIM',
}


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def date_key(r: Dict[str, Any]) -> str:
    return str(r.get('entry_date') or r.get('pick_date') or r.get('select_date') or '')[:8]


def trade_key(r: Dict[str, Any]) -> Tuple[Any, Any, Any]:
    return (r.get('symbol'), r.get('entry_date'), r.get('entry_idx'))


def load_klines(symbol: str) -> List[Dict[str, Any]]:
    path = KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"
    if not path.exists():
        return []
    rows = load_json(path)
    out = []
    for b in rows:
        nb = dict(b)
        for k in ('o', 'h', 'l', 'c'):
            nb[k] = f(nb.get(k))
        out.append(nb)
    return out


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'sl_rate': 0, 'poi_break_rate': 0, 'cum': 0}
    vals = [f(r.get('pnl_pct')) for r in rs]
    return {
        'n': len(rs),
        'wr': round(sum(v > 0 for v in vals) / len(rs) * 100, 2),
        'avg_pnl': round(sum(vals) / len(vals), 4),
        'sl_rate': round(sum(r.get('exit_reason') == 'SL_HIT' for r in rs) / len(rs) * 100, 2),
        'poi_break_rate': round(sum(r.get('v75_primary_post_entry_fail') == 'LOSS_POI_CLOSE_BREAK_BEFORE_TP' for r in rs) / len(rs) * 100, 2),
        'cum': round(sum(vals), 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(grouped.items())}


def attach_v76_env_fields(rows: List[Dict[str, Any]]) -> None:
    v76_rows = load_json(V76_DIR / 'v76_annotated_trades.json')
    v76_by_key = {trade_key(r): r for r in v76_rows}
    keys = [
        'v76_prior5_env_states', 'v76_prior10_env_states',
        'v76_prior5_distribution_days', 'v76_prior10_distribution_days',
        'v76_prior5_demand_valid_days', 'v76_prior10_demand_valid_days',
    ]
    for r in rows:
        src = v76_by_key.get(trade_key(r), {})
        for k in keys:
            r[k] = src.get(k, r.get(k))


def enrich_stock_pre_entry_features(rows: List[Dict[str, Any]]) -> None:
    cache: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        symbol = str(r.get('symbol') or '')
        if symbol not in cache:
            cache[symbol] = load_klines(symbol)
        ks = cache[symbol]
        entry_idx = int(f(r.get('entry_idx'), -1))
        zone_bar = int(f(r.get('zone_bar'), -1))
        reaction_idx = int(f(r.get('reaction_idx'), entry_idx - 1))
        zone_low = f(r.get('zone_low'))
        zone_high = f(r.get('zone_high'))
        if not ks or entry_idx <= 0 or entry_idx >= len(ks):
            r['v77_missing_kline'] = True
            continue
        r['v77_missing_kline'] = False
        prev_close = ks[entry_idx - 1]['c']
        for n in (5, 10, 20, 40, 60):
            if entry_idx - n >= 0 and ks[entry_idx - n]['c']:
                r[f'v77_stock_ret{n}_pct'] = round((prev_close / ks[entry_idx - n]['c'] - 1) * 100, 4)
        if entry_idx >= 20:
            last10 = ks[entry_idx - 10:entry_idx]
            prev10 = ks[entry_idx - 20:entry_idx - 10]
            r['v77_hl_improving'] = min(b['l'] for b in last10) > min(b['l'] for b in prev10)
            r['v77_hh_improving'] = max(b['h'] for b in last10) > max(b['h'] for b in prev10)
        start = max(0, zone_bar if zone_bar >= 0 else entry_idx - 10)
        pre = ks[start:entry_idx]
        if pre and zone_low:
            closes = [b['c'] for b in pre]
            lows = [b['l'] for b in pre]
            r['v77_pre_entry_close_below_poi_count'] = sum(1 for c in closes if c < zone_low)
            r['v77_min_close_vs_poi_pct'] = round((min(closes) / zone_low - 1) * 100, 4)
            r['v77_max_poi_pierce_pct'] = round((min(lows) / zone_low - 1) * 100, 4)
        if 0 <= reaction_idx < len(ks) and zone_high:
            r['v77_reaction_close_over_zone_high_pct'] = round((ks[reaction_idx]['c'] / zone_high - 1) * 100, 4)
            r['v77_reaction_body_pct'] = round((ks[reaction_idx]['c'] / ks[reaction_idx]['o'] - 1) * 100, 4) if ks[reaction_idx]['o'] else 0


def classify_recovery_quality(r: Dict[str, Any]) -> str:
    state = str(r.get('market_state_v74') or '')
    if state != 'RECOVERY':
        return 'NOT_RECOVERY'
    prior10_dist = f(r.get('v76_prior10_distribution_days'), 99)
    prior10_demand = f(r.get('v76_prior10_demand_valid_days'), 0)
    hl_ok = bool(r.get('v77_hl_improving'))
    hh_ok = bool(r.get('v77_hh_improving'))
    poi_intact = f(r.get('v77_pre_entry_close_below_poi_count'), 0) == 0
    risk_ok = f(r.get('risk_pct'), 999) <= 5.0
    if prior10_dist == 0 and prior10_demand >= 3 and hl_ok and hh_ok and poi_intact and risk_ok:
        return 'TRUE_RECOVERY_DEMAND_VALID'
    if prior10_dist >= 1 and prior10_demand <= 3:
        return 'FALSE_RECOVERY_AFTER_WEAK_OR_DISTRIBUTION'
    if not (hl_ok and hh_ok):
        return 'FALSE_RECOVERY_STOCK_STRUCTURE_WEAK'
    if not poi_intact:
        return 'FALSE_RECOVERY_POI_ALREADY_DAMAGED'
    if not risk_ok:
        return 'FALSE_RECOVERY_ENTRY_RISK_WIDE'
    return 'MIXED_RECOVERY_UNPROVEN'


def passes_v77_gate(r: Dict[str, Any]) -> bool:
    if not bool(r.get('v74_core_gate')):
        return False
    if str(r.get('setup_story_v74') or '') not in CORE_STORIES:
        return False
    if f(r.get('v77_pre_entry_close_below_poi_count'), 0) > 0:
        return False
    if f(r.get('risk_pct'), 999) > 5.0:
        return False
    if not bool(r.get('v77_hl_improving')) or not bool(r.get('v77_hh_improving')):
        return False
    state = str(r.get('market_state_v74') or '')
    story = str(r.get('setup_story_v74') or '')
    if story == 'UP_CONTINUATION_BOS_POI_RECLAIM':
        return state in {'BULL_CONTINUATION', 'RECOVERY', 'ACCUMULATION'}
    if story == 'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM':
        return state == 'ACCUMULATION' or r.get('v77_recovery_quality') == 'TRUE_RECOVERY_DEMAND_VALID'
    if story == 'BULL_TRANSITION_POI_RECLAIM':
        return state in {'ACCUMULATION', 'BULL_CONTINUATION'}
    return False


def reject_reason(r: Dict[str, Any]) -> str:
    reasons = []
    if not bool(r.get('v74_core_gate')):
        reasons.append('FAIL_V74_CORE')
    if str(r.get('setup_story_v74') or '') not in CORE_STORIES:
        reasons.append('FAIL_UNKNOWN_STORY')
    if f(r.get('v77_pre_entry_close_below_poi_count'), 0) > 0:
        reasons.append('POI_CLOSED_BELOW_PRE_ENTRY')
    if f(r.get('risk_pct'), 999) > 5.0:
        reasons.append('ENTRY_RISK_GT_5P0')
    if not bool(r.get('v77_hl_improving')):
        reasons.append('STOCK_HL_NOT_IMPROVING')
    if not bool(r.get('v77_hh_improving')):
        reasons.append('STOCK_HH_NOT_IMPROVING')
    state = str(r.get('market_state_v74') or '')
    story = str(r.get('setup_story_v74') or '')
    if story == 'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM' and state == 'RECOVERY' and r.get('v77_recovery_quality') != 'TRUE_RECOVERY_DEMAND_VALID':
        reasons.append('RECOVERY_NOT_DEMAND_VALID')
    if not passes_v77_gate(r) and not reasons:
        reasons.append('FAIL_STORY_STATE_MATCH')
    return '+'.join(reasons) if reasons else 'PASS'


def gate_search(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for max_risk in (4.5, 5.0, 5.2, 5.5, 6.0):
        for require_hl in (False, True):
            for require_hh in (False, True):
                for allow_recovery_cont in (False, True):
                    for allow_recovery_reversal in (False, True):
                        sel = []
                        for r in rows:
                            state = str(r.get('market_state_v74') or '')
                            story = str(r.get('setup_story_v74') or '')
                            if f(r.get('risk_pct'), 999) > max_risk:
                                continue
                            if f(r.get('v77_pre_entry_close_below_poi_count'), 0) > 0:
                                continue
                            if require_hl and not r.get('v77_hl_improving'):
                                continue
                            if require_hh and not r.get('v77_hh_improving'):
                                continue
                            ok = False
                            if story == 'UP_CONTINUATION_BOS_POI_RECLAIM':
                                ok = state in {'BULL_CONTINUATION', 'ACCUMULATION'} or (allow_recovery_cont and state == 'RECOVERY')
                            elif story == 'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM':
                                ok = state == 'ACCUMULATION' or (allow_recovery_reversal and r.get('v77_recovery_quality') == 'TRUE_RECOVERY_DEMAND_VALID')
                            elif story == 'BULL_TRANSITION_POI_RECLAIM':
                                ok = state in {'ACCUMULATION', 'BULL_CONTINUATION'}
                            if ok:
                                sel.append(r)
                        year = bucket(sel, lambda x: date_key(x)[:4])
                        usable_year = {k: v for k, v in year.items() if k in {'2023', '2024', '2025', '2026'}}
                        m = metrics(sel)
                        if m['n'] >= 120 and len(usable_year) == 4:
                            out.append({
                                'max_risk_pct': max_risk,
                                'require_hl_improving': require_hl,
                                'require_hh_improving': require_hh,
                                'allow_recovery_continuation': allow_recovery_cont,
                                'allow_true_recovery_reversal': allow_recovery_reversal,
                                **m,
                                'min_year_wr': min(v['wr'] for v in usable_year.values()),
                                'min_year_avg_pnl': min(v['avg_pnl'] for v in usable_year.values()),
                                'year': usable_year,
                            })
    out.sort(key=lambda x: (x['min_year_wr'], x['wr'], x['avg_pnl'], x['n']), reverse=True)
    return out[:30]


def main() -> None:
    rows = load_json(V75_DIR / 'v75_annotated_trades.json')
    attach_v76_env_fields(rows)
    enrich_stock_pre_entry_features(rows)
    for r in rows:
        r['v77_recovery_quality'] = classify_recovery_quality(r)
        r['v77_gate'] = passes_v77_gate(r)
        r['v77_reject_reason'] = reject_reason(r)
    selected = [r for r in rows if r.get('v77_gate')]
    search = gate_search(rows)
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V77_RECOVERY_QUALITY_STATE_MACHINE_AUDIT',
        'hypothesis': 'RECOVERY must be split; demand POI is tradable only when recovery is demand-valid and the stock POI/structure is intact before entry.',
        'base_v74_selected': metrics(rows),
        'v77_gate': metrics(selected),
        'buckets': {
            'year': bucket(selected, lambda r: date_key(r)[:4]),
            'market_state': bucket(selected, lambda r: r.get('market_state_v74')),
            'story': bucket(selected, lambda r: r.get('setup_story_v74')),
            'recovery_quality_all': bucket(rows, lambda r: r.get('v77_recovery_quality')),
            'recovery_quality_selected': bucket(selected, lambda r: r.get('v77_recovery_quality')),
            'reject_reason': bucket(rows, lambda r: r.get('v77_reject_reason')),
        },
        'top_gate_search': search,
        'production_readiness': {
            'min_required_n': 500,
            'min_required_each_year_n': 50,
            'min_required_each_year_wr': 65.0,
            'passes': bool(metrics(selected)['n'] >= 500 and all(v['n'] >= 50 and v['wr'] >= 65 for k, v in bucket(selected, lambda r: date_key(r)[:4]).items() if k in {'2023', '2024', '2025', '2026'})),
            'reason': 'V77 is still an audit layer; it improves 2024 but 2023 remains below 65% and total sample is below production threshold.'
        },
        'files': {
            'annotated': str(OUT_DIR / 'v77_annotated_trades.json'),
            'selected': str(OUT_DIR / 'v77_selected_trades.json'),
            'report': str(OUT_DIR / 'v77_report.json'),
            'markdown': str(OUT_DIR / 'v77_report.md'),
        },
    }
    (OUT_DIR / 'v77_annotated_trades.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v77_selected_trades.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v77_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    md = [
        '# V77 Recovery Quality State Machine Audit', '',
        '## 结论',
        'V77 把 RECOVERY 拆成 demand-valid recovery / false recovery，并加入个股 HH/HL 与 POI 入场前完整性过滤。2024 明显修复，但 2023 仍未过生产线，因此继续不接生产。', '',
        '| 版本 | 笔数 | WR | 均盈亏 | SL率 | POI跌破率 |',
        '|---|---:|---:|---:|---:|---:|',
        f"| V74基线 | {report['base_v74_selected']['n']} | {report['base_v74_selected']['wr']}% | {report['base_v74_selected']['avg_pnl']}% | {report['base_v74_selected']['sl_rate']}% | {report['base_v74_selected']['poi_break_rate']}% |",
        f"| V77门禁 | {report['v77_gate']['n']} | {report['v77_gate']['wr']}% | {report['v77_gate']['avg_pnl']}% | {report['v77_gate']['sl_rate']}% | {report['v77_gate']['poi_break_rate']}% |",
        '', '## V77分年',
        '| 年份 | 笔数 | WR | 均盈亏 | SL率 | POI跌破率 |', '|---|---:|---:|---:|---:|---:|'
    ]
    for y, m in report['buckets']['year'].items():
        md.append(f"| {y} | {m['n']} | {m['wr']}% | {m['avg_pnl']}% | {m['sl_rate']}% | {m['poi_break_rate']}% |")
    md += ['', '## Recovery质量分桶（全体850笔）', '| Recovery状态 | 笔数 | WR | 均盈亏 | SL率 | POI跌破率 |', '|---|---:|---:|---:|---:|---:|']
    for k, m in report['buckets']['recovery_quality_all'].items():
        md.append(f"| {k} | {m['n']} | {m['wr']}% | {m['avg_pnl']}% | {m['sl_rate']}% | {m['poi_break_rate']}% |")
    if search:
        top = search[0]
        md += ['', '## 最佳搜索门禁', json.dumps({k: top[k] for k in top if k != 'year'}, ensure_ascii=False, indent=2), '', '### 最佳搜索门禁分年', '| 年份 | 笔数 | WR | 均盈亏 | SL率 | POI跌破率 |', '|---|---:|---:|---:|---:|---:|']
        for y, m in top['year'].items():
            md.append(f"| {y} | {m['n']} | {m['wr']}% | {m['avg_pnl']}% | {m['sl_rate']}% | {m['poi_break_rate']}% |")
    md += ['', '## 下一步', 'V78 不能继续在 RECOVERY 上调门禁；下一步应重建趋势/结构事件层，区分 2023 类型的弱 continuation：需要把 BOS/CHOCH/MSS 的结构级别、突破后是否形成新HL、以及 BSL/前高目标是否真实纳入事件状态机。']
    (OUT_DIR / 'v77_report.md').write_text('\n'.join(md))
    print(json.dumps({k: report[k] for k in ['base_v74_selected', 'v77_gate', 'buckets', 'production_readiness', 'top_gate_search', 'files']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
