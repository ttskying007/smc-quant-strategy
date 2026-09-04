#!/usr/bin/env python3
"""V107B signal semantic audit inside tradeable regimes.

Research-only. Reads V104 strict-reclaim trades and V107 market-regime logic,
then attributes BULL_EXPANSION misses, MIXED_CHOP sample quality, and
NO_TRADE_BEAR_STRESS 2023/2024 failures without touching production files.
"""
from __future__ import annotations

import importlib.util
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
SCRIPT = ROOT / 'scripts' / 'v25' / 'v107_tradeable_regime_audit.py'
OUT_JSON = ROOT / 'smc_audit' / 'v107b_signal_semantic_audit_20260619.json'
OUT_MD = ROOT / 'smc_audit' / 'v107b_signal_semantic_audit_20260619.md'


def load_v107_module():
    spec = importlib.util.spec_from_file_location('v107_tradeable_regime_audit', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def f(x, default=0.0):
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def bucket(v, cuts):
    v = f(v)
    lo = None
    for hi in cuts:
        if v <= hi:
            return f'<= {hi:g}' if lo is None else f'{lo:g}-{hi:g}'
        lo = hi
    return f'> {cuts[-1]:g}'


def shallow(rows):
    n = len(rows)
    if not n:
        return {'n': 0, 'wr': 0.0, 'sl': 0.0, 'avg': 0.0, 'median': 0.0, 'cum': 0.0}
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    return {
        'n': n,
        'wr': round(sum(v >= 0.8 for v in vals) * 100.0 / n, 2),
        'sl': round(sum(r.get('exit_reason') == 'SL_HIT' for r in rows) * 100.0 / n, 2),
        'avg': round(mean(vals), 4),
        'median': round(median(vals), 4),
        'cum': round(sum(vals), 4),
    }


def group(rows, key_fn, min_n=1):
    d = defaultdict(list)
    for r in rows:
        d[key_fn(r)].append(r)
    out = []
    for k, rs in d.items():
        if len(rs) >= min_n:
            s = shallow(rs)
            s['key'] = str(k)
            out.append(s)
    out.sort(key=lambda x: (-x['n'], x['wr'], x['avg']))
    return out


def month_table(rows):
    return group(rows, lambda r: str(r.get('entry_date'))[:6])


def enrich_rows():
    v107 = load_v107_module()
    rows = v107.load_trades()
    entry_dates = sorted({str(r.get('entry_date')) for r in rows if r.get('entry_date')})
    stats = v107.compute_full_market_stats(entry_dates)
    return v107.enrich(rows, stats)


def add_semantic_features(rows):
    for r in rows:
        r['win'] = f(r.get('net_pnl_pct')) >= 0.8
        r['risk_bucket'] = bucket(r.get('risk_pct'), [3, 5, 6, 8, 10])
        r['retrace_bucket'] = bucket(r.get('retrace_pct'), [10, 20, 30, 40, 50, 70])
        r['chase_bucket'] = bucket(r.get('chase_pct'), [1, 2, 3, 4, 6])
        r['disp_bucket'] = bucket(r.get('disp_atr'), [1, 2, 3, 5])
        r['pierce_bucket'] = bucket(r.get('pierce_atr'), [0.25, 0.5, 1, 2])
        r['pos60_bucket'] = bucket(r.get('pos60'), [20, 40, 60, 80])
        r['ret20_bucket'] = bucket(r.get('ret20'), [-10, -5, 0, 5, 10])
        r['zone_to_touch'] = int(r.get('touch_idx', 0)) - int(r.get('zone_idx', 0))
        r['touch_to_reclaim'] = int(r.get('reclaim_idx', 0)) - int(r.get('touch_idx', 0))
        r['event_to_entry'] = int(r.get('entry_idx', 0)) - int(r.get('source_event_idx', r.get('event_idx', 0)))
        r['zone_to_touch_bucket'] = bucket(r['zone_to_touch'], [1, 2, 3, 5, 8, 13])
        r['touch_to_reclaim_bucket'] = bucket(r['touch_to_reclaim'], [1, 2, 3, 5])
        r['event_to_entry_bucket'] = bucket(r['event_to_entry'], [3, 5, 8, 13, 21])
    return rows


def bad_buckets(rows, min_n=8):
    fields = [
        'family', 'trend_state', 'combo', 'risk_bucket', 'retrace_bucket', 'chase_bucket',
        'disp_bucket', 'pierce_bucket', 'pos60_bucket', 'ret20_bucket',
        'above_ma20', 'above_ma60', 'zone_to_touch_bucket', 'touch_to_reclaim_bucket',
        'event_to_entry_bucket', 'exit_reason',
    ]
    out = {}
    for field in fields:
        arr = group(rows, lambda r, ff=field: r.get(ff), min_n=min_n)
        out[field] = arr
    return out


def concise_rows(rows, limit=None):
    rs = sorted(rows, key=lambda r: (str(r.get('entry_date')), str(r.get('symbol'))))
    if limit:
        rs = rs[:limit]
    keys = ['symbol', 'entry_date', 'tradeable_regime', 'family', 'trend_state', 'combo',
            'risk_pct', 'retrace_pct', 'chase_pct', 'disp_atr', 'pierce_atr', 'pos60',
            'ret20', 'exit_reason', 'net_pnl_pct', 'month']
    return [{k: r.get(k) for k in keys} for r in rs]


def candidate_rule(rows, name, pred):
    rs = [r for r in rows if pred(r)]
    s = shallow(rs)
    s['name'] = name
    months = month_table(rs)
    s['months'] = len(months)
    s['stable3'] = sum(1 for m in months if m['n'] >= 3 and m['wr'] >= 70 and m['sl'] <= 30)
    s['stable5'] = sum(1 for m in months if m['n'] >= 5 and m['wr'] >= 70 and m['sl'] <= 30)
    return s


def main():
    rows = add_semantic_features(enrich_rows())
    bull = [r for r in rows if r['tradeable_regime'] == 'BULL_EXPANSION']
    bull_loss = [r for r in bull if not r['win']]
    mixed = [r for r in rows if r['tradeable_regime'] == 'MIXED_CHOP']
    bear_2324 = [r for r in rows if r['tradeable_regime'] == 'NO_TRADE_BEAR_STRESS' and str(r.get('entry_date'))[:4] in {'2023', '2024'}]

    bull_rules = [
        candidate_rule(bull, 'BULL_EXPANSION_BASE', lambda r: True),
        candidate_rule(bull, 'skip_risk_gt8', lambda r: f(r.get('risk_pct')) <= 8),
        candidate_rule(bull, 'retr_20_40', lambda r: 20 <= f(r.get('retrace_pct')) <= 40),
        candidate_rule(bull, 'retr_20_40_risk_lte8', lambda r: 20 <= f(r.get('retrace_pct')) <= 40 and f(r.get('risk_pct')) <= 8),
        candidate_rule(bull, 'retr_20_40_risk_lte8_chase_lte4', lambda r: 20 <= f(r.get('retrace_pct')) <= 40 and f(r.get('risk_pct')) <= 8 and f(r.get('chase_pct')) <= 4),
        candidate_rule(bull, 'continuation_retr_20_40_risk_lte8', lambda r: r.get('family') == 'CONTINUATION' and 20 <= f(r.get('retrace_pct')) <= 40 and f(r.get('risk_pct')) <= 8),
    ]

    mixed_years = group(mixed, lambda r: str(r.get('entry_date'))[:4])
    mixed_months = month_table(mixed)
    mixed_symbols = concise_rows(mixed)

    result = {
        'version': 'V107B_SIGNAL_SEMANTIC_AUDIT',
        'research_only': True,
        'production_files_touched': False,
        'input': '/root/.hermes/smc_opt_v104_strict_reclaim/v104_trades.json + V107 regime classifier',
        'bull_expansion': {
            'summary': shallow(bull),
            'loss_summary': shallow(bull_loss),
            'bad_buckets': bad_buckets(bull, min_n=8),
            'candidate_rules': bull_rules,
            'loss_rows': concise_rows(bull_loss, limit=80),
        },
        'mixed_chop': {
            'summary': shallow(mixed),
            'by_year': mixed_years,
            'by_month': mixed_months,
            'rows': mixed_symbols,
            'judgement': '样本仅16笔/5个月，WR高但覆盖不足；只能作为特殊结构假设池，不能作为生产状态。',
        },
        'bear_stress_2023_2024': {
            'summary': shallow(bear_2324),
            'by_year': group(bear_2324, lambda r: str(r.get('entry_date'))[:4]),
            'by_month': month_table(bear_2324),
            'by_exit': group(bear_2324, lambda r: r.get('exit_reason')),
            'by_family': group(bear_2324, lambda r: r.get('family')),
            'by_trend': group(bear_2324, lambda r: r.get('trend_state')),
            'by_risk': group(bear_2324, lambda r: r.get('risk_bucket')),
            'market_averages': {
                'avg_up20_pct': round(mean([f(r.get('market', {}).get('up20_pct')) for r in bear_2324]), 4) if bear_2324 else 0.0,
                'avg_up60_pct': round(mean([f(r.get('market', {}).get('up60_pct')) for r in bear_2324]), 4) if bear_2324 else 0.0,
                'avg_ret20': round(mean([f(r.get('market', {}).get('avg_ret20')) for r in bear_2324]), 4) if bear_2324 else 0.0,
                'avg_ret60': round(mean([f(r.get('market', {}).get('avg_ret60')) for r in bear_2324]), 4) if bear_2324 else 0.0,
            },
        },
        'decision': 'RESEARCH_ONLY_NOT_PROMOTED',
        'non_promotion_reasons': [
            'BULL_EXPANSION内最佳语义子集仍未满足n>=100且稳定月>=12。',
            'MIXED_CHOP只有16笔/5个月，属于待验证特殊结构，不可生产。',
            'NO_TRADE_BEAR_STRESS在2023/2024集中失败，应硬跳过，不是TP/SL可修复问题。',
        ],
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines = []
    lines.append('# V107B Signal Semantic Audit')
    lines.append('')
    lines.append('Decision: **RESEARCH_ONLY_NOT_PROMOTED**')
    lines.append('')
    lines.append('## 1) BULL_EXPANSION 内部语义拆解')
    lines.append('| Rule/Bucket | n | WR | SL | Avg | Median | Cum | Months | Stable3 | Stable5 |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for r in bull_rules:
        lines.append(f"| {r['name']} | {r['n']} | {r['wr']}% | {r['sl']}% | {r['avg']}% | {r['median']}% | {r['cum']}% | {r['months']} | {r['stable3']} | {r['stable5']} |")
    lines.append('')
    lines.append('### BULL_EXPANSION 关键分桶')
    for field in ['family', 'trend_state', 'risk_bucket', 'retrace_bucket', 'chase_bucket', 'disp_bucket', 'touch_to_reclaim_bucket', 'event_to_entry_bucket']:
        lines.append(f'#### {field}')
        lines.append('| bucket | n | WR | SL | Avg |')
        lines.append('|---|---:|---:|---:|---:|')
        for s in result['bull_expansion']['bad_buckets'][field][:10]:
            lines.append(f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% |")
        lines.append('')
    lines.append('## 2) MIXED_CHOP 16笔审计')
    m = result['mixed_chop']['summary']
    lines.append(f"MIXED_CHOP: n={m['n']}, WR={m['wr']}%, SL={m['sl']}%, Avg={m['avg']}%, Months={len(mixed_months)}。判断：样本太小，不能生产晋级。")
    lines.append('| symbol | entry | family | trend | risk | retrace | chase | exit | net |')
    lines.append('|---|---|---|---|---:|---:|---:|---|---:|')
    for r in mixed_symbols:
        lines.append(f"| {r['symbol']} | {r['entry_date']} | {r['family']} | {r['trend_state']} | {r['risk_pct']} | {r['retrace_pct']} | {r['chase_pct']} | {r['exit_reason']} | {r['net_pnl_pct']} |")
    lines.append('')
    lines.append('## 3) NO_TRADE_BEAR_STRESS 2023/2024 失败归因')
    b = result['bear_stress_2023_2024']['summary']
    ma = result['bear_stress_2023_2024']['market_averages']
    lines.append(f"BEAR_STRESS_2324: n={b['n']}, WR={b['wr']}%, SL={b['sl']}%, Avg={b['avg']}%。市场均值 up20={ma['avg_up20_pct']}%, up60={ma['avg_up60_pct']}%, avg_ret20={ma['avg_ret20']}%, avg_ret60={ma['avg_ret60']}%。")
    for field, rows2 in [('by_year', result['bear_stress_2023_2024']['by_year']), ('by_exit', result['bear_stress_2023_2024']['by_exit']), ('by_family', result['bear_stress_2023_2024']['by_family']), ('by_trend', result['bear_stress_2023_2024']['by_trend']), ('by_risk', result['bear_stress_2023_2024']['by_risk'])]:
        lines.append(f'### {field}')
        lines.append('| bucket | n | WR | SL | Avg |')
        lines.append('|---|---:|---:|---:|---:|')
        for s in rows2:
            lines.append(f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% |")
        lines.append('')
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({
        'out_json': str(OUT_JSON),
        'out_md': str(OUT_MD),
        'decision': result['decision'],
        'bull': result['bull_expansion']['summary'],
        'mixed': result['mixed_chop']['summary'],
        'bear_2324': result['bear_stress_2023_2024']['summary'],
        'bull_rules': bull_rules,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
