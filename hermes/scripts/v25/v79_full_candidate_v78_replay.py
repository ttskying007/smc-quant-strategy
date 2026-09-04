#!/usr/bin/env python3
"""V79 full-candidate-layer replay of V78 rules.

V78 was originally evaluated from V77/V75 files (the already-selected V74
850-trade layer). This script recomputes every V76/V77/V78 field directly on
the full V71/V74 annotated candidate universe (9,931 trades), then applies the
same V78 gate and T+1 environment exit. This verifies whether the gate was only
working because of the selected subset.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

KLINE_DIR = Path('/root/.hermes/kline_cache')
V74_DIR = Path('/root/.hermes/smc_opt_v74_env_state_machine')
OUT_DIR = Path('/root/.hermes/smc_opt_v79_full_candidate_v78_replay')
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEMAND_VALID_MARKETS = {'ACCUMULATION', 'RECOVERY', 'BULL_CONTINUATION'}
RISK_EXIT_STATES = {'DISTRIBUTION', 'BEAR_RISK'}
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


def dt(b: Dict[str, Any]) -> str:
    return str(b.get('t') or b.get('date') or b.get('d') or '')[:8]


def trade_year(r: Dict[str, Any]) -> str:
    return str(r.get('entry_date') or r.get('pick_date') or '')[:4]


def date_key(r: Dict[str, Any]) -> str:
    return str(r.get('entry_date') or r.get('pick_date') or r.get('select_date') or '')[:8]


def load_klines(symbol: str) -> List[Dict[str, Any]]:
    path = KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"
    if not path.exists():
        return []
    out = []
    for b in load_json(path):
        nb = dict(b)
        for k in ('o', 'h', 'l', 'c'):
            nb[k] = f(nb.get(k))
        out.append(nb)
    return out


def add_env_window_fields(rows: List[Dict[str, Any]], env_by_date: Dict[str, Dict[str, Any]]) -> None:
    dates = sorted(env_by_date)
    date_pos = {d: i for i, d in enumerate(dates)}
    for r in rows:
        d = date_key(r)
        pos = date_pos.get(d)
        if pos is None:
            r['v79_missing_env_date'] = True
            prev = []
        else:
            r['v79_missing_env_date'] = False
            prev = [env_by_date[x] for x in dates[max(0, pos - 10):pos]]
        states10 = [str(x.get('market_state_v74') or '') for x in prev]
        states5 = states10[-5:]
        r['v76_prior5_env_states'] = states5
        r['v76_prior10_env_states'] = states10
        r['v76_prior5_distribution_days'] = sum(s == 'DISTRIBUTION' for s in states5)
        r['v76_prior10_distribution_days'] = sum(s == 'DISTRIBUTION' for s in states10)
        r['v76_prior5_demand_valid_days'] = sum(s in DEMAND_VALID_MARKETS for s in states5)
        r['v76_prior10_demand_valid_days'] = sum(s in DEMAND_VALID_MARKETS for s in states10)


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
            r.setdefault('v77_hl_improving', False)
            r.setdefault('v77_hh_improving', False)
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
        else:
            r['v77_hl_improving'] = False
            r['v77_hh_improving'] = False
        start = max(0, zone_bar if zone_bar >= 0 else entry_idx - 10)
        pre = ks[start:entry_idx]
        if pre and zone_low:
            closes = [b['c'] for b in pre]
            lows = [b['l'] for b in pre]
            r['v77_pre_entry_close_below_poi_count'] = sum(1 for c in closes if c < zone_low)
            r['v77_min_close_vs_poi_pct'] = round((min(closes) / zone_low - 1) * 100, 4)
            r['v77_max_poi_pierce_pct'] = round((min(lows) / zone_low - 1) * 100, 4)
        else:
            r['v77_pre_entry_close_below_poi_count'] = 99
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


def passes_v78_gate(r: Dict[str, Any]) -> bool:
    if not bool(r.get('v74_core_gate')):
        return False
    if str(r.get('setup_story_v74') or '') not in CORE_STORIES:
        return False
    if f(r.get('risk_pct'), 999) > 5.5:
        return False
    if f(r.get('v76_prior5_distribution_days'), 99) > 0:
        return False
    if f(r.get('v76_prior10_distribution_days'), 99) > 3:
        return False
    if f(r.get('v76_prior10_demand_valid_days'), 0) < 3:
        return False
    if f(r.get('market_bull_breadth'), 0) > 0.50:
        return False
    if f(r.get('v77_pre_entry_close_below_poi_count'), 0) > 0:
        return False
    if not bool(r.get('v77_hl_improving')):
        return False
    if str(r.get('pd_zone') or '') == 'STRUCTURE_LOW_RISK':
        return False
    state = str(r.get('market_state_v74') or '')
    story = str(r.get('setup_story_v74') or '')
    if story == 'UP_CONTINUATION_BOS_POI_RECLAIM':
        return state in {'BULL_CONTINUATION', 'RECOVERY', 'ACCUMULATION'}
    if story == 'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM':
        return state == 'ACCUMULATION' or (state == 'RECOVERY' and r.get('v77_recovery_quality') == 'TRUE_RECOVERY_DEMAND_VALID')
    if story == 'BULL_TRANSITION_POI_RECLAIM':
        return state in {'ACCUMULATION', 'BULL_CONTINUATION'}
    return False


def reject_reason(r: Dict[str, Any]) -> str:
    reasons = []
    if not bool(r.get('v74_core_gate')):
        reasons.append('FAIL_V74_CORE')
    if str(r.get('setup_story_v74') or '') not in CORE_STORIES:
        reasons.append('FAIL_UNKNOWN_STORY')
    if f(r.get('risk_pct'), 999) > 5.5:
        reasons.append('RISK_GT_5P5')
    if f(r.get('v76_prior5_distribution_days'), 99) > 0:
        reasons.append('PRIOR5_DISTRIBUTION')
    if f(r.get('v76_prior10_distribution_days'), 99) > 3:
        reasons.append('PRIOR10_DISTRIBUTION_GT3')
    if f(r.get('v76_prior10_demand_valid_days'), 0) < 3:
        reasons.append('PRIOR10_DEMAND_LT3')
    if f(r.get('market_bull_breadth'), 0) > 0.50:
        reasons.append('BULL_BREADTH_OVERHEATED_GT50')
    if f(r.get('v77_pre_entry_close_below_poi_count'), 0) > 0:
        reasons.append('POI_DAMAGED_PRE_ENTRY')
    if not bool(r.get('v77_hl_improving')):
        reasons.append('HL_NOT_IMPROVING')
    if str(r.get('pd_zone') or '') == 'STRUCTURE_LOW_RISK':
        reasons.append('STRUCTURE_LOW_RISK_ZONE')
    if not reasons and not passes_v78_gate(r):
        reasons.append('STORY_STATE_MISMATCH')
    return '+'.join(reasons) if reasons else 'PASS'


def simulate_env_exit(trade: Dict[str, Any], klines: List[Dict[str, Any]], env_by_date: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    nt = dict(trade)
    entry_idx = int(f(nt.get('entry_idx'), -1))
    original_exit_idx = int(f(nt.get('exit_idx'), entry_idx))
    entry_price = f(nt.get('entry_price'))
    sl = f(nt.get('sl'))
    tp1 = f(nt.get('tp1'))
    if entry_idx < 0 or not klines or not entry_price:
        nt['v79_pnl_pct'] = f(nt.get('pnl_pct'))
        nt['v79_exit_reason'] = nt.get('exit_reason')
        nt['v79_exit_date'] = nt.get('exit_date')
        return nt
    end = min(len(klines) - 1, original_exit_idx if original_exit_idx > entry_idx else entry_idx + 45)
    for i in range(entry_idx + 1, end + 1):
        b = klines[i]
        day = dt(b)
        if sl and b['l'] <= sl:
            nt['v79_pnl_pct'] = round((sl / entry_price - 1) * 100, 4)
            nt['v79_exit_reason'] = 'SL_HIT'
            nt['v79_exit_date'] = day
            nt['v79_exit_price'] = round(sl, 4)
            nt['v79_hold_bars'] = max(1, i - entry_idx)
            return nt
        if tp1 and b['h'] >= tp1:
            nt['v79_pnl_pct'] = round((tp1 / entry_price - 1) * 100, 4)
            nt['v79_exit_reason'] = 'TP1_HIT'
            nt['v79_exit_date'] = day
            nt['v79_exit_price'] = round(tp1, 4)
            nt['v79_hold_bars'] = max(1, i - entry_idx)
            return nt
        env_state = str((env_by_date.get(day) or {}).get('market_state_v74') or '')
        if env_state in RISK_EXIT_STATES:
            nt['v79_pnl_pct'] = round((b['c'] / entry_price - 1) * 100, 4)
            nt['v79_exit_reason'] = 'ENV_RISK_EXIT'
            nt['v79_exit_date'] = day
            nt['v79_exit_price'] = round(b['c'], 4)
            nt['v79_hold_bars'] = max(1, i - entry_idx)
            return nt
    nt['v79_pnl_pct'] = f(nt.get('pnl_pct'))
    nt['v79_exit_reason'] = nt.get('exit_reason')
    nt['v79_exit_date'] = nt.get('exit_date')
    nt['v79_exit_price'] = nt.get('exit_price')
    nt['v79_hold_bars'] = nt.get('hold_bars')
    return nt


def metrics(rows: Iterable[Dict[str, Any]], prefix: str = '') -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'sl_rate': 0, 'env_exit_rate': 0, 'cum': 0}
    pnl_key = f'{prefix}pnl_pct' if prefix else 'pnl_pct'
    exit_key = f'{prefix}exit_reason' if prefix else 'exit_reason'
    vals = [f(r.get(pnl_key)) for r in rs]
    return {
        'n': len(rs),
        'wr': round(sum(v > 0 for v in vals) / len(rs) * 100, 2),
        'avg_pnl': round(sum(vals) / len(vals), 4),
        'sl_rate': round(sum(str(r.get(exit_key) or '').startswith('SL') for r in rs) / len(rs) * 100, 2),
        'env_exit_rate': round(sum(r.get(exit_key) == 'ENV_RISK_EXIT' for r in rs) / len(rs) * 100, 2),
        'cum': round(sum(vals), 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key, prefix: str = '') -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[str(key(r))].append(r)
    return {k: metrics(v, prefix=prefix) for k, v in sorted(grouped.items())}


def production_readiness(simulated: List[Dict[str, Any]]) -> Dict[str, Any]:
    y = {k: v for k, v in bucket(simulated, trade_year, prefix='v79_').items() if k in {'2023', '2024', '2025', '2026'}}
    failures = []
    if metrics(simulated, prefix='v79_')['n'] < 500:
        failures.append('TOTAL_TRADES_LT_500')
    for yr in ('2023', '2024', '2025', '2026'):
        m = y.get(yr, {'n': 0, 'wr': 0, 'avg_pnl': 0})
        if m['n'] < 50:
            failures.append(f'{yr}_N_LT_50')
        if m['wr'] < 65:
            failures.append(f'{yr}_WR_LT_65')
        if m['avg_pnl'] <= 0:
            failures.append(f'{yr}_AVG_NOT_POSITIVE')
    return {'passes': not failures, 'failures': failures, 'year': y}


def main() -> None:
    rows = load_json(V74_DIR / 'v74_annotated_trades.json')
    env_by_date = load_json(V74_DIR / 'v74_env_by_date.json')
    rows = [dict(r) for r in rows]
    add_env_window_fields(rows, env_by_date)
    enrich_stock_pre_entry_features(rows)
    for r in rows:
        r['v77_recovery_quality'] = classify_recovery_quality(r)
        r['v79_v78_gate'] = passes_v78_gate(r)
        r['v79_v78_reject_reason'] = reject_reason(r)

    selected = [r for r in rows if r.get('v79_v78_gate')]
    cache: Dict[str, List[Dict[str, Any]]] = {}
    simulated = []
    for r in selected:
        sym = str(r.get('symbol') or '')
        if sym not in cache:
            cache[sym] = load_klines(sym)
        simulated.append(simulate_env_exit(r, cache[sym], env_by_date))

    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V79_FULL_CANDIDATE_LAYER_REPLAY_OF_V78_RULES',
        'input_layer': {
            'source': str(V74_DIR / 'v74_annotated_trades.json'),
            'full_candidate_trades': len(rows),
            'v74_core_gate_count': sum(bool(r.get('v74_core_gate')) for r in rows),
        },
        'metrics': {
            'full_v71_v74_candidate_layer': metrics(rows),
            'v74_core_gate': metrics([r for r in rows if r.get('v74_core_gate')]),
            'v79_v78_gate_original_exit': metrics(selected),
            'v79_v78_gate_env_exit': metrics(simulated, prefix='v79_'),
        },
        'year_original_exit': bucket(selected, trade_year),
        'year_env_exit': bucket(simulated, trade_year, prefix='v79_'),
        'state_env_exit': bucket(simulated, lambda r: r.get('market_state_v74'), prefix='v79_'),
        'story_env_exit': bucket(simulated, lambda r: r.get('setup_story_v74'), prefix='v79_'),
        'reject_reason': bucket(rows, lambda r: r.get('v79_v78_reject_reason')),
        'reject_reason_counts': dict(Counter(r.get('v79_v78_reject_reason') for r in rows)),
        'exit_reason_counts': dict(Counter(r.get('v79_exit_reason') for r in simulated)),
        't1_audit': {
            'violations': sum(1 for r in simulated if str(r.get('v79_exit_date')) == str(r.get('entry_date'))),
            'checked': len(simulated),
        },
        'production_readiness': production_readiness(simulated),
        'files': {
            'annotated': str(OUT_DIR / 'v79_full_annotated_trades.json'),
            'selected': str(OUT_DIR / 'v79_selected_trades.json'),
            'simulated': str(OUT_DIR / 'v79_simulated_trades.json'),
            'report': str(OUT_DIR / 'v79_report.json'),
            'markdown': str(OUT_DIR / 'v79_report.md'),
        },
    }

    (OUT_DIR / 'v79_full_annotated_trades.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v79_selected_trades.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v79_simulated_trades.json').write_text(json.dumps(simulated, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v79_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))

    md = [
        '# V79 全量候选层回灌 V78 规则验证', '',
        '## 结论',
        'V79 已从 V71/V74 全量候选层 9,931 笔重新计算 V76/V77/V78 字段，不再读取 V75/V77 的 850 笔子集文件。',
        '结果显示：V78 规则本身不是生产解，回灌全量后仍被 V74 core gate 限制在同一候选域，最终覆盖不足。不能接生产。', '',
        '## 总览',
        '| 层级 | 笔数 | WR | 均盈亏 | SL率 | 环境退出率 | 累计 |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for label, key, prefix in [
        ('全量候选层', 'full_v71_v74_candidate_layer', ''),
        ('V74 core', 'v74_core_gate', ''),
        ('V79/V78原出场', 'v79_v78_gate_original_exit', ''),
        ('V79/V78环境退出', 'v79_v78_gate_env_exit', ''),
    ]:
        m = report['metrics'][key]
        md.append(f"| {label} | {m['n']} | {m['wr']}% | {m['avg_pnl']}% | {m['sl_rate']}% | {m['env_exit_rate']}% | {m['cum']}% |")
    md += ['', '## 分年（环境退出）', '| 年份 | 笔数 | WR | 均盈亏 | SL率 | 环境退出率 | 累计 |', '|---|---:|---:|---:|---:|---:|---:|']
    for y, m in report['year_env_exit'].items():
        if y in {'2023', '2024', '2025', '2026'}:
            md.append(f"| {y} | {m['n']} | {m['wr']}% | {m['avg_pnl']}% | {m['sl_rate']}% | {m['env_exit_rate']}% | {m['cum']}% |")
    md += ['', '## 生产闸门', f"- 通过: {report['production_readiness']['passes']}", f"- 失败项: {', '.join(report['production_readiness']['failures'])}", f"- T+1违规: {report['t1_audit']['violations']} / {report['t1_audit']['checked']}", '', '## 文件', f"- 报告: `{report['files']['report']}`", f"- 交易: `{report['files']['simulated']}`"]
    (OUT_DIR / 'v79_report.md').write_text('\n'.join(md))
    print(json.dumps({
        'metrics': report['metrics'],
        'year_env_exit': {k: v for k, v in report['year_env_exit'].items() if k in {'2023','2024','2025','2026'}},
        't1_audit': report['t1_audit'],
        'production_readiness': report['production_readiness'],
        'files': report['files'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
