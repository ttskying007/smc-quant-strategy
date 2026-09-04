#!/usr/bin/env python3
"""V116 source-quality-gate simulation.

Research-only validation of one isolated source-quality gate:
Reject / downgrade:
    family == CONTINUATION
    AND retrace_pct >= 95
    AND fvg_mid_body_atr < 0.65

No TP/SL tuning. No production/API/frontend/monitor writes.
Validates the gate over:
1) V104 unique RANGE_TRANSITION sample,
2) full-market raw-kline re-scan,
3) monthly distribution,
4) mature / not-mature layers.
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path('/root/.hermes')
SCRIPT_DIR = ROOT / 'scripts' / 'v25'
OUT_DIR = ROOT / 'smc_audit'
OUT_JSON = OUT_DIR / 'v116_source_quality_gate_simulation_20260619.json'
OUT_MD = OUT_DIR / 'v116_source_quality_gate_simulation_20260619.md'
V104_TRADES = ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_trades.json'
NET_SUCCESS = 0.8


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot import {path}')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


v115 = load_module('v115_fvg_source_label_fullsample_audit', SCRIPT_DIR / 'v115_fvg_source_label_fullsample_audit.py')
v104 = load_module('v104_strict_reclaim_backtest', SCRIPT_DIR / 'v104_strict_reclaim_backtest.py')


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if v == v else default
    except Exception:
        return default


def pct(a: float, b: float) -> float:
    return round(a * 100.0 / b, 2) if b else 0.0


def metric(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    return {
        'n': len(rows),
        'wr': pct(sum(v >= NET_SUCCESS for v in vals), len(rows)),
        'sl': pct(sum(r.get('exit_reason') == 'SL_HIT' for r in rows), len(rows)),
        'avg': round(statistics.mean(vals), 4) if vals else 0.0,
        'median': round(statistics.median(vals), 4) if vals else 0.0,
        'months': len({str(r.get('entry_date', ''))[:6] for r in rows}),
        'cum': round(sum(vals), 4),
    }


def delta(after: Dict[str, Any], before: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'n_removed': before.get('n', 0) - after.get('n', 0),
        'wr_pp': round(after.get('wr', 0.0) - before.get('wr', 0.0), 2),
        'sl_pp': round(after.get('sl', 0.0) - before.get('sl', 0.0), 2),
        'avg_pct': round(after.get('avg', 0.0) - before.get('avg', 0.0), 4),
        'cum_delta_pct': round(after.get('cum', 0.0) - before.get('cum', 0.0), 4),
    }


def gate_hit(row: Dict[str, Any]) -> bool:
    return (
        row.get('family') == 'CONTINUATION'
        and f(row.get('retrace_pct')) >= 95.0
        and f(row.get('fvg_mid_body_atr')) < 0.65
    )


def enrich_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        rr = v115.add_source_context(v115.enrich_indices(r))
        rr['v116_source_quality_gate'] = 'REJECT_OR_DOWNGRADE' if gate_hit(rr) else 'KEEP'
        rr['v116_gate_reason'] = 'CONTINUATION_FULL_RETRACE_WEAK_FVG_BODY' if gate_hit(rr) else ''
        out.append(rr)
    return out


def dedup(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return v115.dedup_v110([v115.enrich_indices(r) for r in rows])


def split_sets(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        'baseline': rows,
        'kept_after_gate': [r for r in rows if not gate_hit(r)],
        'rejected_or_downgraded': [r for r in rows if gate_hit(r)],
        'mature_baseline': [r for r in rows if r.get('mature')],
        'mature_kept_after_gate': [r for r in rows if r.get('mature') and not gate_hit(r)],
        'mature_rejected_or_downgraded': [r for r in rows if r.get('mature') and gate_hit(r)],
        'not_mature_baseline': [r for r in rows if not r.get('mature')],
        'not_mature_kept_after_gate': [r for r in rows if (not r.get('mature')) and not gate_hit(r)],
        'not_mature_rejected_or_downgraded': [r for r in rows if (not r.get('mature')) and gate_hit(r)],
    }


def simulation(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    sets = split_sets(rows)
    m = {k: metric(v) for k, v in sets.items()}
    return {
        'metrics': m,
        'gate_delta': delta(m['kept_after_gate'], m['baseline']),
        'mature_delta': delta(m['mature_kept_after_gate'], m['mature_baseline']),
        'not_mature_delta': delta(m['not_mature_kept_after_gate'], m['not_mature_baseline']),
        'by_source_label': bucket(rows, lambda r: r.get('source_label')),
        'by_family': bucket(rows, lambda r: r.get('family')),
        'by_gate': bucket(rows, lambda r: r.get('v116_source_quality_gate')),
        'month_stability': month_stability(rows),
        'rejected_rows': [concise(r) for r in sorted(sets['rejected_or_downgraded'], key=lambda x: (str(x.get('entry_date')), str(x.get('symbol'))))],
    }


def bucket(rows: List[Dict[str, Any]], fn) -> Dict[str, Dict[str, Any]]:
    d: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        d[str(fn(r))].append(r)
    return {k: metric(v) for k, v in sorted(d.items())}


def month_stability(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_month: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_month[str(r.get('entry_date', ''))[:6]].append(r)
    month_rows = []
    for month, rs in sorted(by_month.items()):
        base = metric(rs)
        kept = metric([r for r in rs if not gate_hit(r)])
        rej = metric([r for r in rs if gate_hit(r)])
        month_rows.append({
            'month': month,
            'baseline': base,
            'kept_after_gate': kept,
            'rejected_or_downgraded': rej,
            'delta': delta(kept, base),
        })
    eligible = [m for m in month_rows if m['baseline']['n'] >= 3]
    improved = [m for m in eligible if m['delta']['wr_pp'] > 0 or m['delta']['avg_pct'] > 0]
    worsened = [m for m in eligible if m['delta']['wr_pp'] < 0 or m['delta']['avg_pct'] < 0]
    hit_months = [m for m in month_rows if m['rejected_or_downgraded']['n'] > 0]
    hit_eligible = [m for m in hit_months if m['baseline']['n'] >= 3]
    return {
        'months': len(month_rows),
        'months_n_ge_3': len(eligible),
        'gate_hit_months': len(hit_months),
        'gate_hit_months_n_ge_3': len(hit_eligible),
        'improved_months_n_ge_3': len(improved),
        'worsened_months_n_ge_3': len(worsened),
        'months_table': month_rows,
        'worsened_months': [m for m in month_rows if m['delta']['wr_pp'] < 0 or m['delta']['avg_pct'] < 0],
    }


def concise(r: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        'symbol', 'entry_date', 'family', 'trend_state', 'source_label', 'v116_source_quality_gate',
        'exit_reason', 'net_pnl_pct', 'mature', 'event_to_touch', 'event_to_entry', 'retrace_pct',
        'fvg_mid_body_atr', 'zone_width_atr', 'chase_pct', 'risk_pct', 'ret60', 'pos60',
        'fvg_left_date', 'fvg_mid_date', 'fvg_right_date',
    ]
    return {k: r.get(k) for k in keys}


def run_full_market_rescan() -> List[Dict[str, Any]]:
    files = sorted(v104.KLINE_DIR.glob('*_daily_750.json'))
    rows: List[Dict[str, Any]] = []
    for n, path in enumerate(files, 1):
        rows.extend(v104.replay_file(path))
        if n % 500 == 0:
            print(json.dumps({'event': 'full_rescan_progress', 'files_done': n, 'rows': len(rows)}, ensure_ascii=False), flush=True)
    rows.sort(key=lambda r: (r.get('entry_date', ''), r.get('symbol', ''), r.get('family', '')))
    return rows


def md_metric_row(name: str, s: Dict[str, Any]) -> str:
    return f"| {name} | {s.get('n', 0)} | {s.get('wr', 0)}% | {s.get('sl', 0)}% | {s.get('avg', 0)}% | {s.get('median', 0)}% | {s.get('months', 0)} | {s.get('cum', 0)}% |"


def append_sim_section(lines: List[str], title: str, sim: Dict[str, Any]) -> None:
    m = sim['metrics']
    lines += [
        f'## {title}',
        '| Set | n | WR | SL | Avg | Median | Months | Cum |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
        md_metric_row('Baseline', m['baseline']),
        md_metric_row('Kept after gate', m['kept_after_gate']),
        md_metric_row('Rejected / downgraded', m['rejected_or_downgraded']),
        md_metric_row('Mature baseline', m['mature_baseline']),
        md_metric_row('Mature kept', m['mature_kept_after_gate']),
        md_metric_row('Mature rejected', m['mature_rejected_or_downgraded']),
        md_metric_row('Not-mature baseline', m['not_mature_baseline']),
        md_metric_row('Not-mature kept', m['not_mature_kept_after_gate']),
        md_metric_row('Not-mature rejected', m['not_mature_rejected_or_downgraded']),
        '',
        '| Delta | Removed | WR pp | SL pp | Avg pct | Cum delta |',
        '|---|---:|---:|---:|---:|---:|',
        f"| Overall gate | {sim['gate_delta']['n_removed']} | {sim['gate_delta']['wr_pp']} | {sim['gate_delta']['sl_pp']} | {sim['gate_delta']['avg_pct']} | {sim['gate_delta']['cum_delta_pct']} |",
        f"| Mature gate | {sim['mature_delta']['n_removed']} | {sim['mature_delta']['wr_pp']} | {sim['mature_delta']['sl_pp']} | {sim['mature_delta']['avg_pct']} | {sim['mature_delta']['cum_delta_pct']} |",
        f"| Not-mature gate | {sim['not_mature_delta']['n_removed']} | {sim['not_mature_delta']['wr_pp']} | {sim['not_mature_delta']['sl_pp']} | {sim['not_mature_delta']['avg_pct']} | {sim['not_mature_delta']['cum_delta_pct']} |",
        '',
    ]


def append_month_section(lines: List[str], title: str, sim: Dict[str, Any], limit: int = 80) -> None:
    st = sim['month_stability']
    lines += [
        f'## {title} monthly distribution',
        f"Summary: months={st['months']}, n>=3={st['months_n_ge_3']}, gate-hit-months={st['gate_hit_months']}, improved n>=3={st['improved_months_n_ge_3']}, worsened n>=3={st['worsened_months_n_ge_3']}",
        '',
        '| Month | Base n | Base WR | Base Avg | Gate n | Gate WR | Gate Avg | Kept n | Kept WR | Kept Avg | ΔWR | ΔAvg |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for m in st['months_table'][:limit]:
        b, r, k, de = m['baseline'], m['rejected_or_downgraded'], m['kept_after_gate'], m['delta']
        lines.append(f"| {m['month']} | {b['n']} | {b['wr']}% | {b['avg']}% | {r['n']} | {r['wr']}% | {r['avg']}% | {k['n']} | {k['wr']}% | {k['avg']}% | {de['wr_pp']} | {de['avg_pct']} |")
    lines.append('')


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    stored_raw = json.loads(V104_TRADES.read_text())
    stored_range_raw = [r for r in stored_raw if r.get('trend_state') == 'RANGE_TRANSITION']
    v104_unique_range = enrich_rows(dedup(stored_range_raw))

    full_rescan_raw = run_full_market_rescan()
    full_rescan_unique_all = enrich_rows(dedup(full_rescan_raw))
    full_rescan_unique_range = enrich_rows(dedup([r for r in full_rescan_raw if r.get('trend_state') == 'RANGE_TRANSITION']))

    v104_sim = simulation(v104_unique_range)
    full_all_sim = simulation(full_rescan_unique_all)
    full_range_sim = simulation(full_rescan_unique_range)

    # The gate is a source-quality downgrade candidate only when it never harms
    # the stored V104 unique RANGE sample and behaves similarly on a fresh
    # full-market rescan. Promotion remains forbidden in V116 by design.
    v104_ok = v104_sim['gate_delta']['wr_pp'] >= 0 and v104_sim['gate_delta']['avg_pct'] >= 0 and v104_sim['metrics']['rejected_or_downgraded']['wr'] < v104_sim['metrics']['baseline']['wr']
    rescan_ok = full_range_sim['gate_delta']['wr_pp'] >= 0 and full_range_sim['gate_delta']['avg_pct'] >= 0
    decision = 'RESEARCH_ONLY_GATE_DIRECTION_VALIDATED_NOT_PROMOTED' if (v104_ok and rescan_ok) else 'RESEARCH_ONLY_NOT_PROMOTED'

    result = {
        'version': 'V116_SOURCE_QUALITY_GATE_SIMULATION',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_files_touched': False,
        'tp_sl_tuning': False,
        'gate_rule': {
            'family': 'CONTINUATION',
            'retrace_pct_gte': 95.0,
            'fvg_mid_body_atr_lt': 0.65,
            'action_simulated': 'REJECT_OR_DOWNGRADE_TO_WATCH_ONLY',
        },
        'inputs': {
            'stored_v104_trades': str(V104_TRADES),
            'full_rescan_source': str(v104.KLINE_DIR),
            'full_rescan_raw_rows': len(full_rescan_raw),
            'full_rescan_unique_all_rows': len(full_rescan_unique_all),
            'full_rescan_unique_range_rows': len(full_rescan_unique_range),
        },
        'v104_unique_range_transition': v104_sim,
        'full_market_rescan_unique_all': full_all_sim,
        'full_market_rescan_unique_range_transition': full_range_sim,
        'decision': decision,
        'findings': {
            'isolated_gate_only': 'Only CONTINUATION + retrace_pct>=95 + fvg_mid_body_atr<0.65 was simulated; TP/SL and production routing were not changed.',
            'not_global_full_retrace_reject': 'Rows with strong FVG displacement and full retrace are not rejected unless fvg_mid_body_atr<0.65 and family is CONTINUATION.',
            'production_status': 'No production/API/frontend/monitor file is written by this script.',
        },
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines: List[str] = [
        '# V116 Source-Quality-Gate Simulation',
        '',
        f'Decision: **{decision}**',
        '',
        'Scope: research-only; no TP/SL tuning; no production/API/frontend/monitor writes.',
        '',
        'Gate simulated: `family == CONTINUATION AND retrace_pct >= 95 AND fvg_mid_body_atr < 0.65`.',
        '',
        '## Input counts',
        '| Input | Rows |',
        '|---|---:|',
        f"| Stored V104 raw RANGE_TRANSITION | {len(stored_range_raw)} |",
        f"| Stored V104 unique RANGE_TRANSITION | {len(v104_unique_range)} |",
        f"| Full-market rescan raw rows | {len(full_rescan_raw)} |",
        f"| Full-market rescan unique all rows | {len(full_rescan_unique_all)} |",
        f"| Full-market rescan unique RANGE_TRANSITION | {len(full_rescan_unique_range)} |",
        '',
    ]
    append_sim_section(lines, 'Stored V104 unique RANGE_TRANSITION 182 sample', v104_sim)
    append_sim_section(lines, 'Full-market rescan unique RANGE_TRANSITION', full_range_sim)
    append_sim_section(lines, 'Full-market rescan unique ALL trend states', full_all_sim)
    append_month_section(lines, 'Stored V104 unique RANGE_TRANSITION', v104_sim)
    append_month_section(lines, 'Full-market rescan unique RANGE_TRANSITION', full_range_sim)

    lines += [
        '## Rejected / downgraded rows: V104 unique RANGE_TRANSITION',
        '| Symbol | Entry | Family | Mature | Exit | Net | E→T | E→E | Retrace | MidBodyATR | Risk | ret60 | pos60 |',
        '|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for r in v104_sim['rejected_rows']:
        lines.append(f"| {r['symbol']} | {r['entry_date']} | {r['family']} | {r['mature']} | {r['exit_reason']} | {r['net_pnl_pct']} | {r['event_to_touch']} | {r['event_to_entry']} | {r['retrace_pct']} | {r['fvg_mid_body_atr']} | {r['risk_pct']} | {r['ret60']} | {r['pos60']} |")
    lines += [
        '',
        '## Conclusion',
        '- V116 only simulated the single weak-source gate; it did not tune TP/SL and did not alter production.',
        '- The rule is not a global full-retrace ban: strong full-retrace rows stay in the kept set unless they match the exact weak continuation source condition.',
        f'- Final decision: `{decision}`.',
    ]
    OUT_MD.write_text('\n'.join(lines) + '\n')

    print(json.dumps({
        'ok': True,
        'out_json': str(OUT_JSON),
        'out_md': str(OUT_MD),
        'decision': decision,
        'v104_gate_delta': v104_sim['gate_delta'],
        'full_range_gate_delta': full_range_sim['gate_delta'],
        'full_all_gate_delta': full_all_sim['gate_delta'],
        'full_rescan_raw_rows': len(full_rescan_raw),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
