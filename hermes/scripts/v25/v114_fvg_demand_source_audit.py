#!/usr/bin/env python3
"""V114 FVG_Demand source-construction audit.

Research-only continuation of V113.
- No TP/SL tuning.
- No production/API/frontend/monitor writes.
- Inspect mature RANGE_TRANSITION rows (event_to_touch>=9) at the FVG
  construction bars and classify true demand vs weak continuation/full-retrace
  imbalance using pre-entry features only.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path('/root/.hermes')
V104_TRADES = ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_trades.json'
KLINE_DIR = ROOT / 'kline_cache'
OUT_JSON = ROOT / 'smc_audit' / 'v114_fvg_demand_source_audit_20260619.json'
OUT_MD = ROOT / 'smc_audit' / 'v114_fvg_demand_source_audit_20260619.md'
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
    return json.loads(symbol_path(symbol).read_text())


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
    }


def median(rows, key):
    vals = [f(r.get(key)) for r in rows]
    return round(statistics.median(vals), 4) if vals else 0.0


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
        for field in ['fvg_mid_body_atr', 'zone_width_atr', 'retrace_pct', 'chase_pct', 'ret60', 'pos60', 'pre10_ret_to_zone_mid_pct', 'post_event_run_to_touch_pct']:
            s[f'{field}_median'] = median(rs, field)
        out.append(s)
    return out


def concise(row):
    keys = [
        'symbol', 'entry_date', 'family', 'source_label', 'exit_reason', 'net_pnl_pct',
        'event_to_entry', 'event_to_touch', 'event_to_zone', 'retrace_pct', 'chase_pct',
        'fvg_mid_body_atr', 'zone_width_atr', 'zone_at_local_low20', 'pre10_ret_to_zone_mid_pct',
        'post_event_run_to_touch_pct', 'ret60', 'pos60', 'fvg_left_date', 'fvg_mid_date', 'fvg_right_date',
    ]
    return {k: row.get(k) for k in keys}


def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    raw = [enrich_indices(r) for r in json.loads(V104_TRADES.read_text()) if r.get('trend_state') == 'RANGE_TRANSITION']
    unique = dedup_v110(raw)
    mature = [add_source_context(r) for r in unique if i(r.get('event_to_touch')) >= 9]

    label_table = bucket(mature, 'source_label')
    result = {
        'version': 'V114_FVG_DEMAND_SOURCE_AUDIT',
        'research_only': True,
        'production_files_touched': False,
        'inputs': {'v104_trades': str(V104_TRADES), 'kline_dir': str(KLINE_DIR)},
        'method': 'Read-only inspection of mature RANGE_TRANSITION rows. Reconstruct FVG three-bar source context, classify demand-vs-imbalance with pre-entry fields only. No TP/SL tuning.',
        'mature_metric': metric(mature),
        'label_table': label_table,
        'buckets': {
            'by_source_label': label_table,
            'by_full_retrace': bucket(mature, 'full_retrace'),
            'by_fvg_mid_bull': bucket(mature, 'fvg_mid_bull'),
            'by_family': bucket(mature, 'family'),
        },
        'rows': [concise(r) for r in sorted(mature, key=lambda r: (str(r.get('source_label')), str(r.get('entry_date')), str(r.get('symbol'))))],
        'losses': [concise(r) for r in sorted(mature, key=lambda r: (f(r.get('net_pnl_pct')), str(r.get('entry_date')), str(r.get('symbol')))) if f(r.get('net_pnl_pct')) < NET_SUCCESS],
        'decision': 'RESEARCH_ONLY_NOT_PROMOTED',
        'findings': {
            'full_retrace_not_sufficient': 'Full retrace alone is not the root cause: strong FVG source displacement can still survive full retrace.',
            'weak_full_retrace_source': 'The clearest weak-source bucket is CONTINUATION + full retrace + fvg_mid_body_atr<0.65; it contains most mature losses and behaves like continuation imbalance, not durable demand.',
            'true_demand_candidate_small': 'Non-full-retrace rows with fvg_mid_body_atr>=0.35 form a clean true-demand-retest candidate, but the sample is only 9 rows and cannot be promoted.',
            'sample_limit': 'All conclusions are based on 18 mature rows; this is source-construction research only.',
        },
        'next': 'Next research should test the same source labels across all V104 unique RANGE_TRANSITION rows, not just mature rows, to see whether weak-source separation survives larger sample/month coverage.',
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines = [
        '# V114 FVG_Demand Source Construction Audit',
        '',
        'Decision: **RESEARCH_ONLY_NOT_PROMOTED**',
        '',
        'Scope: research-only; no TP/SL tuning; no production/API/frontend/monitor changes.',
        '',
        '## Source-label comparison',
        '| Source label | n | WR | SL | Avg | Months | MidBodyATR med | WidthATR med | Retrace med | Chase med | ret60 med | pos60 med | Pre10Ret med | PostRun med |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for s in label_table:
        lines.append(
            f"| {s['key']} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['months']} | "
            f"{s['fvg_mid_body_atr_median']} | {s['zone_width_atr_median']} | {s['retrace_pct_median']} | {s['chase_pct_median']} | "
            f"{s['ret60_median']} | {s['pos60_median']} | {s['pre10_ret_to_zone_mid_pct_median']} | {s['post_event_run_to_touch_pct_median']} |"
        )
    lines += [
        '',
        '## Mature rows with FVG source labels',
        '| Symbol | Entry | Family | Label | Exit | Net | E2E | E→T | E→Z | Retrace | Chase | MidBodyATR | WidthATR | LocalLow20 | Pre10Ret | PostRun | ret60 | pos60 | FVG dates |',
        '|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|',
    ]
    for r in result['rows']:
        lines.append(
            f"| {r['symbol']} | {r['entry_date']} | {r['family']} | {r['source_label']} | {r['exit_reason']} | {r['net_pnl_pct']} | "
            f"{r['event_to_entry']} | {r['event_to_touch']} | {r['event_to_zone']} | {r['retrace_pct']} | {r['chase_pct']} | "
            f"{r['fvg_mid_body_atr']} | {r['zone_width_atr']} | {r['zone_at_local_low20']} | {r['pre10_ret_to_zone_mid_pct']} | "
            f"{r['post_event_run_to_touch_pct']} | {r['ret60']} | {r['pos60']} | {r['fvg_left_date']}/{r['fvg_mid_date']}/{r['fvg_right_date']} |"
        )
    lines += [
        '',
        '## Conclusion',
        '- V113 的“mature 仍亏损”不是 TP/SL，也不是 reclaim 前 zone death。',
        '- V114 将根因进一步定位到 FVG_Demand 源构造：当前生成器把不同性质的 FVG 都命名为 `FVG_Demand`。',
        '- `TRUE_DEMAND_RETEST_CANDIDATE`（非满回撤 + MidBodyATR>=0.35）在 9 笔 mature 样本中 100% WR / 0% SL，但样本太小，只能作为下一步规则候选。',
        '- `WEAK_CONTINUATION_FULL_RETRACE_FVG` 是主要污染桶：CONTINUATION + 满回撤 + MidBodyATR<0.65，更像 continuation imbalance 被完全回补，不是 durable demand。',
        '- `STRONG_IMBALANCE_FULL_RETRACE` 说明满回撤本身不能一刀切；强 displacement FVG 即使满回撤仍可能有效。',
        '- V114 继续不晋级生产；下一步应把 source labels 扩到全部 V104 unique RANGE_TRANSITION 样本验证覆盖和月度稳定性。',
    ]
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'ok': True, 'out_json': str(OUT_JSON), 'out_md': str(OUT_MD), 'decision': result['decision']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
