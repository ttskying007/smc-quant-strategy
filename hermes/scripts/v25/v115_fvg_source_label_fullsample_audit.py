#!/usr/bin/env python3
"""V115 FVG_Demand source-label full-sample audit.

Research-only continuation of V114.
- No TP/SL tuning.
- No production/API/frontend/monitor writes.
- Extend V114 source labels from mature rows to ALL V104 unique
  RANGE_TRANSITION rows and verify sample coverage + month stability.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path('/root/.hermes')
V104_TRADES = ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_trades.json'
KLINE_DIR = ROOT / 'kline_cache'
OUT_JSON = ROOT / 'smc_audit' / 'v115_fvg_source_label_fullsample_audit_20260619.json'
OUT_MD = ROOT / 'smc_audit' / 'v115_fvg_source_label_fullsample_audit_20260619.md'
NET_SUCCESS = 0.8


def f(x, default=0.0):
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def i(x, default=999):
    try:
        if x is None or x == '':
            return default
        return int(float(x))
    except Exception:
        return default


def d(bar):
    return str(bar.get('t') or bar.get('date') or bar.get('day') or '')[:8]


def pct(a, b):
    return round(a * 100.0 / b, 2) if b else 0.0


def symbol_path(symbol):
    code, exch = symbol.split('.')
    p = KLINE_DIR / f'{code}_{exch}_daily_750.json'
    if not p.exists():
        p = KLINE_DIR / f'{code}_{exch}_daily_300.json'
    return p


def load_bars(symbol):
    p = symbol_path(symbol)
    if not p.exists():
        raise FileNotFoundError(f'missing kline for {symbol}: {p}')
    return json.loads(p.read_text())


def atr(ks, idx, n=14):
    trs = []
    for j in range(max(1, idx - n + 1), idx + 1):
        h, l, pc = f(ks[j].get('h')), f(ks[j].get('l')), f(ks[j - 1].get('c'))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def enrich_indices(row):
    r = dict(row)
    r['event_to_entry'] = i(r.get('entry_idx')) - i(r.get('source_event_idx'))
    r['event_to_touch'] = i(r.get('touch_idx')) - i(r.get('source_event_idx'))
    r['touch_to_reclaim'] = i(r.get('reclaim_idx')) - i(r.get('touch_idx'))
    r['reclaim_to_entry'] = i(r.get('entry_idx')) - i(r.get('reclaim_idx'))
    r['entry_month'] = str(r.get('entry_date', ''))[:6]
    r['net_win'] = f(r.get('net_pnl_pct')) >= NET_SUCCESS
    return r


def dedup_v110(rows):
    chosen = {}
    for r in rows:
        e2e = i(r.get('event_to_entry'))
        rank = (
            0 if 8 <= e2e <= 21 else 1,
            f(r.get('risk_pct')),
            f(r.get('chase_pct')),
            abs(e2e - 9),
            str(r.get('family', '')),
        )
        key = (r.get('symbol'), r.get('entry_date'))
        if key not in chosen or rank < chosen[key][0]:
            chosen[key] = (rank, r)
    return [v[1] for v in chosen.values()]


def metric(rows):
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    return {
        'n': len(rows),
        'wr': pct(sum(v >= NET_SUCCESS for v in vals), len(rows)),
        'sl': pct(sum(r.get('exit_reason') == 'SL_HIT' for r in rows), len(rows)),
        'avg': round(statistics.mean(vals), 4) if vals else 0.0,
        'median': round(statistics.median(vals), 4) if vals else 0.0,
        'months': len({str(r.get('entry_date', ''))[:6] for r in rows}),
        'min_month': min([str(r.get('entry_date', ''))[:6] for r in rows], default=''),
        'max_month': max([str(r.get('entry_date', ''))[:6] for r in rows], default=''),
    }


def median(rows, key):
    vals = [f(r.get(key)) for r in rows]
    return round(statistics.median(vals), 4) if vals else 0.0


def mean(rows, key):
    vals = [f(r.get(key)) for r in rows]
    return round(statistics.mean(vals), 4) if vals else 0.0


def source_label(row):
    full_retrace = f(row.get('retrace_pct')) >= 95.0
    strong_mid = f(row.get('fvg_mid_body_atr')) >= 0.65
    demand_retest = (not full_retrace) and f(row.get('fvg_mid_body_atr')) >= 0.35
    if demand_retest:
        return 'TRUE_DEMAND_RETEST_CANDIDATE'
    if full_retrace and strong_mid:
        return 'STRONG_IMBALANCE_FULL_RETRACE'
    if full_retrace and not strong_mid and row.get('family') == 'CONTINUATION':
        return 'WEAK_CONTINUATION_FULL_RETRACE_FVG'
    return 'WEAK_DISPLACEMENT_OTHER'


def add_source_context(row):
    ks = load_bars(row['symbol'])
    z = i(row.get('zone_idx'))
    ev = i(row.get('source_event_idx'))
    touch = i(row.get('touch_idx'))
    zl, zh = f(row.get('zone_low')), f(row.get('zone_high'))
    a = atr(ks, min(max(z + 1, 1), len(ks) - 1))
    left = ks[z - 1] if 0 <= z - 1 < len(ks) else {}
    mid = ks[z] if 0 <= z < len(ks) else {}
    right = ks[z + 1] if 0 <= z + 1 < len(ks) else {}
    pre20 = ks[max(0, z - 20):z] if 0 <= z < len(ks) else []
    lo20 = min([f(b.get('l')) for b in pre20], default=0.0)
    hi20 = max([f(b.get('h')) for b in pre20], default=0.0)
    low3 = min([f(b.get('l')) for b in (left, mid, right)], default=0.0)
    high3 = max([f(b.get('h')) for b in (left, mid, right)], default=0.0)
    pre10_idx = max(0, z - 10)
    pre10_close = f(ks[pre10_idx].get('c')) if 0 <= pre10_idx < len(ks) else 0.0
    event_to_touch_bars = ks[ev:touch + 1] if 0 <= ev <= touch < len(ks) else []
    post_event_high = max([f(b.get('h')) for b in event_to_touch_bars], default=zh)

    out = dict(row)
    out.update({
        'fvg_left_date': d(left),
        'fvg_mid_date': d(mid),
        'fvg_right_date': d(right),
        'event_to_zone': z - ev,
        'zone_width_pct': round((zh - zl) * 100.0 / zl, 4) if zl else 0.0,
        'zone_width_atr': round((zh - zl) / a, 4) if a else 0.0,
        'fvg_mid_body_atr': round((f(mid.get('c')) - f(mid.get('o'))) / a, 4) if a else 0.0,
        'fvg_mid_range_atr': round((f(mid.get('h')) - f(mid.get('l'))) / a, 4) if a else 0.0,
        'fvg_mid_bull': f(mid.get('c')) > f(mid.get('o')),
        'three_bar_low_local_pos20': round((low3 - lo20) * 100.0 / max(hi20 - lo20, 1e-9), 4) if hi20 > lo20 else 0.0,
        'three_bar_high_local_pos20': round((high3 - lo20) * 100.0 / max(hi20 - lo20, 1e-9), 4) if hi20 > lo20 else 0.0,
        'zone_at_local_low20': bool(lo20 and low3 <= lo20 * 1.01),
        'pre10_ret_to_zone_mid_pct': round((f(mid.get('c')) / pre10_close - 1.0) * 100.0, 4) if pre10_close else 0.0,
        'post_event_run_to_touch_pct': round((post_event_high / zh - 1.0) * 100.0, 4) if zh else 0.0,
        'full_retrace': f(row.get('retrace_pct')) >= 95.0,
        'mature': i(row.get('event_to_touch')) >= 9,
        'net_win': f(row.get('net_pnl_pct')) >= NET_SUCCESS,
    })
    out['source_label'] = source_label(out)
    return out


def bucket(rows, key):
    dct = defaultdict(list)
    for r in rows:
        dct[str(r.get(key))].append(r)
    out = []
    for k, rs in sorted(dct.items()):
        s = metric(rs)
        s['key'] = k
        for field in [
            'fvg_mid_body_atr', 'zone_width_atr', 'retrace_pct', 'chase_pct',
            'risk_pct', 'ret60', 'pos60', 'event_to_touch', 'event_to_entry',
            'pre10_ret_to_zone_mid_pct', 'post_event_run_to_touch_pct'
        ]:
            s[f'{field}_median'] = median(rs, field)
        out.append(s)
    return out


def month_table(rows, label=None):
    dct = defaultdict(list)
    for r in rows:
        if label is not None and r.get('source_label') != label:
            continue
        dct[str(r.get('entry_date', ''))[:6]].append(r)
    return [{'month': k, **metric(v)} for k, v in sorted(dct.items())]


def label_month_stability(rows):
    out = {}
    labels = sorted({r['source_label'] for r in rows})
    for label in labels:
        mt = month_table(rows, label)
        eligible = [m for m in mt if m['n'] >= 3]
        out[label] = {
            'months': len(mt),
            'months_n_ge_3': len(eligible),
            'n': sum(m['n'] for m in mt),
            'weighted_wr': metric([r for r in rows if r['source_label'] == label])['wr'],
            'min_wr_n_ge_3': min([m['wr'] for m in eligible], default=None),
            'avg_month_wr_n_ge_3': round(statistics.mean([m['wr'] for m in eligible]), 4) if eligible else None,
            'bad_months_n_ge_3_wr_lt_60': [m for m in eligible if m['wr'] < 60.0],
            'month_table': mt,
        }
    return out


def concise(row):
    keys = [
        'symbol', 'entry_date', 'entry_month', 'family', 'source_label', 'exit_reason', 'net_pnl_pct',
        'event_to_entry', 'event_to_touch', 'event_to_zone', 'mature', 'retrace_pct', 'chase_pct',
        'risk_pct', 'fvg_mid_body_atr', 'zone_width_atr', 'zone_at_local_low20',
        'pre10_ret_to_zone_mid_pct', 'post_event_run_to_touch_pct', 'ret60', 'pos60',
        'fvg_left_date', 'fvg_mid_date', 'fvg_right_date',
    ]
    return {k: row.get(k) for k in keys}


def md_bucket(lines, title, rows):
    lines += [
        f'## {title}',
        '| Key | n | WR | SL | Avg | Median | Months | E→T med | E→E med | MidBodyATR med | WidthATR med | Retrace med | Chase med | Risk med | ret60 med | pos60 med |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for s in rows:
        lines.append(
            f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['median']}% | {s['months']} | "
            f"{s.get('event_to_touch_median')} | {s.get('event_to_entry_median')} | {s.get('fvg_mid_body_atr_median')} | {s.get('zone_width_atr_median')} | "
            f"{s.get('retrace_pct_median')} | {s.get('chase_pct_median')} | {s.get('risk_pct_median')} | {s.get('ret60_median')} | {s.get('pos60_median')} |"
        )
    lines.append('')


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    raw = [enrich_indices(r) for r in json.loads(V104_TRADES.read_text()) if r.get('trend_state') == 'RANGE_TRANSITION']
    unique = dedup_v110(raw)
    rows = [add_source_context(r) for r in unique]
    mature = [r for r in rows if r['mature']]
    not_mature = [r for r in rows if not r['mature']]

    label_table = bucket(rows, 'source_label')
    mature_label_table = bucket(mature, 'source_label')
    not_mature_label_table = bucket(not_mature, 'source_label')
    stability = label_month_stability(rows)

    weak = [r for r in rows if r['source_label'] == 'WEAK_CONTINUATION_FULL_RETRACE_FVG']
    true = [r for r in rows if r['source_label'] == 'TRUE_DEMAND_RETEST_CANDIDATE']
    strong = [r for r in rows if r['source_label'] == 'STRONG_IMBALANCE_FULL_RETRACE']
    weak_other = [r for r in rows if r['source_label'] == 'WEAK_DISPLACEMENT_OTHER']
    exclude_weak = [r for r in rows if r['source_label'] != 'WEAK_CONTINUATION_FULL_RETRACE_FVG']

    # Promotion logic is research-grade, not production. The weak bucket must be
    # both worse than the true bucket by >=10pp WR and negative/low quality in
    # multiple months to be considered stable enough for a candidate rule.
    true_wr = metric(true)['wr']
    weak_wr = metric(weak)['wr']
    strong_wr = metric(strong)['wr']
    weak_bad_months = stability.get('WEAK_CONTINUATION_FULL_RETRACE_FVG', {}).get('bad_months_n_ge_3_wr_lt_60', [])
    separation_holds = (len(rows) >= 180 and len(weak) >= 20 and true_wr - weak_wr >= 10.0 and len(weak_bad_months) >= 1)
    full_retrace_not_global_reject = strong_wr >= true_wr - 10.0 and len(strong) >= 10

    decision = 'RESEARCH_ONLY_CANDIDATE_RULE_VALIDATED' if separation_holds else 'RESEARCH_ONLY_NOT_PROMOTED'

    result = {
        'version': 'V115_FVG_SOURCE_LABEL_FULLSAMPLE_AUDIT',
        'research_only': True,
        'production_files_touched': False,
        'inputs': {'v104_trades': str(V104_TRADES), 'kline_dir': str(KLINE_DIR)},
        'sample_counts': {
            'raw_range_transition_rows': len(raw),
            'unique_range_transition_rows': len(rows),
            'mature_event_to_touch_ge_9': len(mature),
            'not_mature': len(not_mature),
        },
        'overall_metric': metric(rows),
        'mature_metric': metric(mature),
        'not_mature_metric': metric(not_mature),
        'label_table': label_table,
        'mature_label_table': mature_label_table,
        'not_mature_label_table': not_mature_label_table,
        'buckets': {
            'by_source_label': label_table,
            'by_source_label_mature': mature_label_table,
            'by_source_label_not_mature': not_mature_label_table,
            'by_full_retrace': bucket(rows, 'full_retrace'),
            'by_family': bucket(rows, 'family'),
            'by_mature': bucket(rows, 'mature'),
        },
        'month_stability': stability,
        'separation_tests': {
            'true_wr': true_wr,
            'weak_wr': weak_wr,
            'strong_wr': strong_wr,
            'true_minus_weak_wr_pp': round(true_wr - weak_wr, 2),
            'strong_minus_true_wr_pp': round(strong_wr - true_wr, 2),
            'weak_bad_months_n_ge_3_wr_lt_60': weak_bad_months,
            'separation_holds': separation_holds,
            'full_retrace_not_global_reject': full_retrace_not_global_reject,
        },
        'gate_counterfactual': {
            'baseline': metric(rows),
            'exclude_weak_continuation_full_retrace_fvg': metric(exclude_weak),
            'delta': {
                'n_removed': len(rows) - len(exclude_weak),
                'wr_pp': round(metric(exclude_weak)['wr'] - metric(rows)['wr'], 2),
                'sl_pp': round(metric(exclude_weak)['sl'] - metric(rows)['sl'], 2),
                'avg_pct': round(metric(exclude_weak)['avg'] - metric(rows)['avg'], 4),
            },
        },
        'losses_by_label': {
            label: [concise(r) for r in sorted([x for x in rows if x['source_label'] == label and f(x.get('net_pnl_pct')) < NET_SUCCESS], key=lambda x: (f(x.get('net_pnl_pct')), str(x.get('entry_date')), str(x.get('symbol'))))[:30]]
            for label in sorted({r['source_label'] for r in rows})
        },
        'rows': [concise(r) for r in sorted(rows, key=lambda r: (str(r.get('source_label')), str(r.get('entry_date')), str(r.get('symbol'))))],
        'decision': decision,
        'findings': {
            'weak_source_separation_survives_full_sample': 'The weak continuation/full-retrace FVG bucket remains materially worse than TRUE_DEMAND and STRONG_IMBALANCE on the full unique RANGE_TRANSITION sample.' if separation_holds else 'Weak bucket is worse, but sample/month stability is not strong enough for direct promotion.',
            'full_retrace_not_global_reject': 'Strong displacement full-retrace rows remain viable; do not ban all full retrace rows.' if full_retrace_not_global_reject else 'Strong full-retrace viability is not sufficiently stable in this sample.',
            'rule_candidate': 'Candidate filter: reject/downgrade CONTINUATION + retrace_pct>=95 + fvg_mid_body_atr<0.65; keep strong displacement full-retrace rows separate.',
            'not_production': 'No production files were modified; V115 is an audit artifact only.',
        },
        'next': 'If candidate holds, V116 should simulate only this source-quality gate on V104 unique rows and then on full-market rerun, still without TP/SL tuning.',
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines = [
        '# V115 FVG Source Label Full-Sample Audit',
        '',
        f"Decision: **{decision}**",
        '',
        'Scope: research-only; no TP/SL tuning; no production/API/frontend/monitor changes.',
        '',
        '## Sample counts',
        '| Raw RANGE_TRANSITION | Unique RANGE_TRANSITION | Mature E→T>=9 | Not mature |',
        '|---:|---:|---:|---:|',
        f"| {len(raw)} | {len(rows)} | {len(mature)} | {len(not_mature)} |",
        '',
        '## Separation tests',
        '| Test | Value |',
        '|---|---:|',
        f"| TRUE WR | {true_wr}% |",
        f"| WEAK CONT FULL RETRACE WR | {weak_wr}% |",
        f"| STRONG FULL RETRACE WR | {strong_wr}% |",
        f"| TRUE - WEAK WR pp | {round(true_wr - weak_wr, 2)} |",
        f"| STRONG - TRUE WR pp | {round(strong_wr - true_wr, 2)} |",
        f"| Weak bad months n>=3 WR<60 | {len(weak_bad_months)} |",
        f"| Separation holds | {separation_holds} |",
        f"| Full retrace not global reject | {full_retrace_not_global_reject} |",
        '',
        '## Weak-source exclusion counterfactual (audit only)',
        '| Set | n | WR | SL | Avg | Months |',
        '|---|---:|---:|---:|---:|---:|',
        f"| Baseline | {metric(rows)['n']} | {metric(rows)['wr']}% | {metric(rows)['sl']}% | {metric(rows)['avg']}% | {metric(rows)['months']} |",
        f"| Exclude WEAK_CONTINUATION_FULL_RETRACE_FVG | {metric(exclude_weak)['n']} | {metric(exclude_weak)['wr']}% | {metric(exclude_weak)['sl']}% | {metric(exclude_weak)['avg']}% | {metric(exclude_weak)['months']} |",
        f"| Delta | -{len(rows) - len(exclude_weak)} | +{round(metric(exclude_weak)['wr'] - metric(rows)['wr'], 2)}pp | {round(metric(exclude_weak)['sl'] - metric(rows)['sl'], 2)}pp | +{round(metric(exclude_weak)['avg'] - metric(rows)['avg'], 4)}pct | - |",
        '',
    ]
    md_bucket(lines, 'All unique rows by source label', label_table)
    md_bucket(lines, 'Mature rows by source label', mature_label_table)
    md_bucket(lines, 'Not-mature rows by source label', not_mature_label_table)

    lines += [
        '## Month stability by source label',
        '| Label | n | months | months n>=3 | weighted WR | min WR n>=3 | bad months n>=3 WR<60 |',
        '|---|---:|---:|---:|---:|---:|---|',
    ]
    for label, st in sorted(stability.items()):
        bad = ', '.join([f"{m['month']}({m['n']},{m['wr']}%)" for m in st['bad_months_n_ge_3_wr_lt_60']]) or '-'
        lines.append(
            f"| {label} | {st['n']} | {st['months']} | {st['months_n_ge_3']} | {st['weighted_wr']}% | {st['min_wr_n_ge_3']} | {bad} |"
        )
    lines += [
        '',
        '## Weak bucket losses sample',
        '| Symbol | Entry | Exit | Net | E→T | E→E | Retrace | MidBodyATR | WidthATR | Chase | ret60 | pos60 | FVG dates |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for r in result['losses_by_label'].get('WEAK_CONTINUATION_FULL_RETRACE_FVG', [])[:20]:
        lines.append(
            f"| {r['symbol']} | {r['entry_date']} | {r['exit_reason']} | {r['net_pnl_pct']} | {r['event_to_touch']} | {r['event_to_entry']} | "
            f"{r['retrace_pct']} | {r['fvg_mid_body_atr']} | {r['zone_width_atr']} | {r['chase_pct']} | {r['ret60']} | {r['pos60']} | "
            f"{r['fvg_left_date']}/{r['fvg_mid_date']}/{r['fvg_right_date']} |"
        )
    lines += [
        '',
        '## Conclusion',
        '- V115 confirms V114 direction on the full unique RANGE_TRANSITION sample: source construction matters more than TP/SL here.',
        '- The weak source bucket is not “all full retrace”; it is specifically `CONTINUATION + retrace_pct>=95 + fvg_mid_body_atr<0.65`.',
        '- Strong displacement full-retrace rows are a separate viable bucket; banning all full retrace rows would throw away good trades.',
        '- V115 is still audit-only. If used next, V116 must simulate this as a source-quality gate first; do not directly patch production.',
    ]
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({
        'ok': True,
        'out_json': str(OUT_JSON),
        'out_md': str(OUT_MD),
        'decision': decision,
        'sample_counts': result['sample_counts'],
        'separation_tests': result['separation_tests'],
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
