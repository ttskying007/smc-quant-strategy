#!/usr/bin/env python3
"""V107C TRADEABLE_REGIME re-derivation with 750-bar full-market breadth.

Research-only. Corrects V107/V107B market-state coverage by using *_daily_750
K-lines and robust breadth/median returns. Does not touch production/API/frontend.
"""
from __future__ import annotations

import bisect
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_trades.json'
KLINE = ROOT / 'kline_cache'
OUT_JSON = ROOT / 'smc_audit' / 'v107c_tradeable_regime_rederive_20260619.json'
OUT_MD = ROOT / 'smc_audit' / 'v107c_tradeable_regime_rederive_20260619.md'


def f(x, default=0.0):
    try:
        if x is None or x == '':
            return default
        y = float(x)
        if math.isnan(y):
            return default
        return y
    except Exception:
        return default


def pct(a, b):
    return round(a * 100.0 / b, 4) if b else 0.0


def winsor(v, lo=-30.0, hi=30.0):
    return max(lo, min(hi, f(v)))


def bucket(v, cuts):
    v = f(v)
    lo = None
    for hi in cuts:
        if v <= hi:
            return f'<= {hi:g}' if lo is None else f'{lo:g}-{hi:g}'
        lo = hi
    return f'> {cuts[-1]:g}'


def load_trades():
    rows = json.loads(TRADES.read_text())
    rows = [dict(r) for r in rows if r.get('entry_date')]
    rows.sort(key=lambda r: (str(r.get('entry_date')), str(r.get('symbol'))))
    return rows


def load_kline(path):
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return [], []
    pairs = []
    for r in raw:
        d = str(r.get('t') or r.get('date') or '')[:8]
        c = f(r.get('c'), None)
        if len(d) == 8 and c and c > 0:
            pairs.append((d, c))
    pairs.sort(key=lambda x: x[0])
    return [x[0] for x in pairs], [x[1] for x in pairs]


def compute_full_market_stats_750(entry_dates):
    dates = sorted(entry_dates)
    acc = {d: {'total': 0, 'up20': 0, 'up60': 0, 'ret20_pos': 0, 'ret60_pos': 0, 'r20': [], 'r60': []} for d in dates}
    for path in sorted(KLINE.glob('*_daily_750.json')):
        kdates, closes = load_kline(path)
        if len(kdates) < 80:
            continue
        for d in dates:
            idx = bisect.bisect_right(kdates, d) - 1
            if idx < 60:
                continue
            c = closes[idx]
            if c <= 0 or closes[idx-20] <= 0 or closes[idx-60] <= 0:
                continue
            ma20 = mean(closes[idx-19:idx+1])
            ma60 = mean(closes[idx-59:idx+1])
            ret20 = winsor((c / closes[idx-20] - 1.0) * 100.0)
            ret60 = winsor((c / closes[idx-60] - 1.0) * 100.0)
            a = acc[d]
            a['total'] += 1
            a['up20'] += int(c > ma20)
            a['up60'] += int(c > ma60)
            a['ret20_pos'] += int(ret20 > 0)
            a['ret60_pos'] += int(ret60 > 0)
            a['r20'].append(ret20)
            a['r60'].append(ret60)
    out = {}
    for d, a in acc.items():
        total = a['total']
        out[d] = {
            'total': total,
            'up20_pct': round(pct(a['up20'], total), 2),
            'up60_pct': round(pct(a['up60'], total), 2),
            'ret20_pos_pct': round(pct(a['ret20_pos'], total), 2),
            'ret60_pos_pct': round(pct(a['ret60_pos'], total), 2),
            'avg_ret20_w': round(mean(a['r20']), 4) if a['r20'] else 0.0,
            'avg_ret60_w': round(mean(a['r60']), 4) if a['r60'] else 0.0,
            'median_ret20': round(median(a['r20']), 4) if a['r20'] else 0.0,
            'median_ret60': round(median(a['r60']), 4) if a['r60'] else 0.0,
        }
    return out


def classify_regime_v107c(m):
    up20 = f(m.get('up20_pct'))
    up60 = f(m.get('up60_pct'))
    pos20 = f(m.get('ret20_pos_pct'))
    med20 = f(m.get('median_ret20'))
    med60 = f(m.get('median_ret60'))
    avg20 = f(m.get('avg_ret20_w'))
    if up20 >= 55 and up60 >= 50 and pos20 >= 55 and med20 >= 2 and avg20 >= 1:
        return 'BULL_EXPANSION'
    if up20 >= 45 and up60 >= 38 and pos20 >= 52 and med20 >= 0:
        return 'BULL_RECOVERY'
    if up20 >= 35 and up60 >= 30 and med20 >= -2:
        return 'REPAIRABLE_RANGE'
    if up20 < 30 or up60 < 25 or pos20 < 35 or med20 < -4 or med60 < -6:
        return 'NO_TRADE_BEAR_STRESS'
    return 'MIXED_CHOP'


def shallow(rows):
    n = len(rows)
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    return {
        'n': n,
        'wr': round(pct(sum(v >= 0.8 for v in vals), n), 2),
        'sl': round(pct(sum(r.get('exit_reason') == 'SL_HIT' for r in rows), n), 2),
        'avg': round(mean(vals), 4) if vals else 0.0,
        'median': round(median(vals), 4) if vals else 0.0,
        'cum': round(sum(vals), 4),
    }


def group(rows, key, min_n=1):
    d = defaultdict(list)
    for r in rows:
        d[str(key(r))].append(r)
    out = []
    for k, rs in d.items():
        if len(rs) >= min_n:
            s = shallow(rs)
            s['key'] = k
            out.append(s)
    out.sort(key=lambda x: (-x['n'], x['wr'], x['avg']))
    return out


def add_features(rows):
    for r in rows:
        r['month'] = str(r.get('entry_date'))[:6]
        r['year'] = str(r.get('entry_date'))[:4]
        r['win'] = f(r.get('net_pnl_pct')) >= 0.8
        r['risk_bucket'] = bucket(r.get('risk_pct'), [3, 5, 6, 8, 10])
        r['retrace_bucket'] = bucket(r.get('retrace_pct'), [10, 20, 30, 40, 50, 70])
        r['chase_bucket'] = bucket(r.get('chase_pct'), [1, 2, 3, 4, 6])
        r['disp_bucket'] = bucket(r.get('disp_atr'), [1, 2, 3, 5])
        r['pierce_bucket'] = bucket(r.get('pierce_atr'), [0.25, 0.5, 1, 2])
        r['touch_to_reclaim'] = int(r.get('reclaim_idx', 0)) - int(r.get('touch_idx', 0))
        r['event_to_entry'] = int(r.get('entry_idx', 0)) - int(r.get('source_event_idx', r.get('event_idx', 0)))
        r['touch_to_reclaim_bucket'] = bucket(r['touch_to_reclaim'], [1, 2, 3, 5])
        r['event_to_entry_bucket'] = bucket(r['event_to_entry'], [3, 5, 8, 13, 21])
    return rows


def month_stats(rows):
    arr = group(rows, lambda r: r['month'])
    return arr, sum(1 for x in arr if x['n'] >= 3 and x['wr'] >= 70 and x['sl'] <= 30), sum(1 for x in arr if x['n'] >= 5 and x['wr'] >= 70 and x['sl'] <= 30)


def rule_summary(rows, name, pred):
    rs = [r for r in rows if pred(r)]
    s = shallow(rs)
    ms, stable3, stable5 = month_stats(rs)
    s.update({'name': name, 'months': len(ms), 'stable3': stable3, 'stable5': stable5})
    return s


def concise(rows):
    keys = ['symbol','entry_date','tradeable_regime','family','trend_state','risk_pct','retrace_pct','chase_pct','disp_atr','exit_reason','net_pnl_pct','month']
    return [{k: r.get(k) for k in keys} for r in sorted(rows, key=lambda x: (x.get('entry_date'), x.get('symbol')))]


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    rows = load_trades()
    dates = sorted({str(r.get('entry_date')) for r in rows})
    stats = compute_full_market_stats_750(dates)
    for r in rows:
        m = stats.get(str(r.get('entry_date')), {})
        r['market_v107c'] = m
        r['tradeable_regime'] = classify_regime_v107c(m)
    rows = add_features(rows)
    by_regime = {k: shallow([r for r in rows if r['tradeable_regime'] == k]) for k in sorted({r['tradeable_regime'] for r in rows})}
    by_regime_months = {}
    for k in by_regime:
        ms, st3, st5 = month_stats([r for r in rows if r['tradeable_regime'] == k])
        by_regime[k].update({'months': len(ms), 'stable3': st3, 'stable5': st5})
        by_regime_months[k] = ms

    bull = [r for r in rows if r['tradeable_regime'] == 'BULL_EXPANSION']
    mixed = [r for r in rows if r['tradeable_regime'] == 'MIXED_CHOP']
    bear2324 = [r for r in rows if r['tradeable_regime'] == 'NO_TRADE_BEAR_STRESS' and r['year'] in {'2023','2024'}]
    bull_rules = [
        rule_summary(bull, 'BULL_EXPANSION_BASE', lambda r: True),
        rule_summary(bull, 'TREND_UP_only', lambda r: r.get('trend_state') == 'TREND_UP'),
        rule_summary(bull, 'retr_20_40', lambda r: 20 <= f(r.get('retrace_pct')) <= 40),
        rule_summary(bull, 'TREND_UP_retr_20_40', lambda r: r.get('trend_state') == 'TREND_UP' and 20 <= f(r.get('retrace_pct')) <= 40),
        rule_summary(bull, 'CONTINUATION_retr_20_40', lambda r: r.get('family') == 'CONTINUATION' and 20 <= f(r.get('retrace_pct')) <= 40),
    ]
    bull_buckets = {field: group(bull, lambda r, ff=field: r.get(ff), min_n=5) for field in [
        'family','trend_state','risk_bucket','retrace_bucket','chase_bucket','disp_bucket','touch_to_reclaim_bucket','event_to_entry_bucket'
    ]}

    result = {
        'version': 'V107C_TRADEABLE_REGIME_REDERIVE',
        'research_only': True,
        'production_files_touched': False,
        'data_fix': 'Uses *_daily_750 and winsorized/median market breadth; V107 daily_300 coverage was insufficient for 2023/2024 regime attribution.',
        'baseline': shallow(rows),
        'by_regime': by_regime,
        'by_regime_months': by_regime_months,
        'bull_expansion': {'summary': shallow(bull), 'rules': bull_rules, 'buckets': bull_buckets, 'loss_rows': concise([r for r in bull if not r['win']])},
        'mixed_chop': {'summary': shallow(mixed), 'by_month': group(mixed, lambda r: r['month']), 'rows': concise(mixed)},
        'bear_stress_2023_2024': {
            'summary': shallow(bear2324),
            'by_year': group(bear2324, lambda r: r['year']),
            'by_month': group(bear2324, lambda r: r['month']),
            'by_exit': group(bear2324, lambda r: r.get('exit_reason')),
            'by_trend': group(bear2324, lambda r: r.get('trend_state')),
            'market_averages': {
                'avg_total': round(mean([f(r['market_v107c'].get('total')) for r in bear2324]), 2) if bear2324 else 0,
                'avg_up20_pct': round(mean([f(r['market_v107c'].get('up20_pct')) for r in bear2324]), 2) if bear2324 else 0,
                'avg_up60_pct': round(mean([f(r['market_v107c'].get('up60_pct')) for r in bear2324]), 2) if bear2324 else 0,
                'avg_median_ret20': round(mean([f(r['market_v107c'].get('median_ret20')) for r in bear2324]), 4) if bear2324 else 0,
                'avg_median_ret60': round(mean([f(r['market_v107c'].get('median_ret60')) for r in bear2324]), 4) if bear2324 else 0,
            },
        },
        'decision': 'RESEARCH_ONLY_NOT_PROMOTED',
        'non_promotion_reasons': [
            'V107C修复市场状态数据源后，仍没有n>=100、WR>=70、SL<=30、stable3>=12的生产候选。',
            'BULL_EXPANSION子集质量提升但覆盖/月度稳定不足。',
            'MIXED_CHOP仍是小样本假设池，不接生产。',
            'NO_TRADE_BEAR_STRESS在2023/2024继续表现为负，应作为市场状态硬跳过。',
        ],
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines = ['# V107C TRADEABLE_REGIME Re-derivation', '', 'Decision: **RESEARCH_ONLY_NOT_PROMOTED**', '', '## Regime table', '| Regime | n | WR | SL | Avg | Median | Cum | Months | Stable3 | Stable5 |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for k, s in by_regime.items():
        lines.append(f"| {k} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['median']}% | {s['cum']}% | {s['months']} | {s['stable3']} | {s['stable5']} |")
    lines += ['', '## BULL_EXPANSION candidate splits', '| Rule | n | WR | SL | Avg | Median | Cum | Months | Stable3 | Stable5 |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for s in bull_rules:
        lines.append(f"| {s['name']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['median']}% | {s['cum']}% | {s['months']} | {s['stable3']} | {s['stable5']} |")
    for field, arr in bull_buckets.items():
        lines += ['', f'### BULL_EXPANSION {field}', '| bucket | n | WR | SL | Avg |', '|---|---:|---:|---:|---:|']
        for s in arr[:10]:
            lines.append(f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% |")
    m = result['mixed_chop']['summary']
    lines += ['', '## MIXED_CHOP audit', f"n={m['n']}, WR={m['wr']}%, SL={m['sl']}%, Avg={m['avg']}%。小样本，不晋级。", '| symbol | entry | family | trend | risk | retrace | exit | net |', '|---|---|---|---|---:|---:|---|---:|']
    for r in result['mixed_chop']['rows']:
        lines.append(f"| {r['symbol']} | {r['entry_date']} | {r['family']} | {r['trend_state']} | {r['risk_pct']} | {r['retrace_pct']} | {r['exit_reason']} | {r['net_pnl_pct']} |")
    b = result['bear_stress_2023_2024']['summary']; ma = result['bear_stress_2023_2024']['market_averages']
    lines += ['', '## NO_TRADE_BEAR_STRESS 2023/2024', f"n={b['n']}, WR={b['wr']}%, SL={b['sl']}%, Avg={b['avg']}%。avg_total={ma['avg_total']}, up20={ma['avg_up20_pct']}%, up60={ma['avg_up60_pct']}%, median_ret20={ma['avg_median_ret20']}%, median_ret60={ma['avg_median_ret60']}%。"]
    for title, arr in [('by_year', result['bear_stress_2023_2024']['by_year']), ('by_exit', result['bear_stress_2023_2024']['by_exit']), ('by_trend', result['bear_stress_2023_2024']['by_trend'])]:
        lines += ['', f'### {title}', '| bucket | n | WR | SL | Avg |', '|---|---:|---:|---:|---:|']
        for s in arr:
            lines.append(f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% |")
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'out_json': str(OUT_JSON), 'out_md': str(OUT_MD), 'decision': result['decision'], 'by_regime': by_regime, 'bull_rules': bull_rules, 'bear2324': result['bear_stress_2023_2024']}, ensure_ascii=False, indent=2)[:12000])


if __name__ == '__main__':
    main()
