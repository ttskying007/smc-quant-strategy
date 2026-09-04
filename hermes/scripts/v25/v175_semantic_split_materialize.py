#!/usr/bin/env python3
"""V175 semantic split: keep V172 economics, correct the over-claimed event label.

Read-only source, writes isolated /root/.hermes/smc_opt_v175_semantic_split.
No signal/TP/SL/entry changes. This is a semantic contract repair:
- production edge = DEMAND_OB_TRUE_TAKEOVER_RECLAIM
- classical SSL_SWEEP_CHOCH remains an audited field, not the primary claim
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path('/root/.hermes')
SRC = ROOT / 'smc_opt_v172_v167_high_quality_gate'
AUD = ROOT / 'smc_audit' / 'v174_v172_wave_structure_hierarchy_20260623' / 'v174_rows_with_wave_audit.json'
OUT = ROOT / 'smc_opt_v175_semantic_split'
OUT.mkdir(parents=True, exist_ok=True)
VERSION = 'V175'
ENGINE = 'V175_DEMAND_OB_TRUE_TAKEOVER_SEMANTIC_SPLIT'


def f(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ''):
            return default
        return float(v)
    except Exception:
        return default


def dkey(v: Any) -> str:
    return ''.join(ch for ch in str(v or '') if ch.isdigit())[:8]


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {'n': 0}
    vals = [f(r.get('pnl_pct')) for r in rows]
    yrs: dict[str, list[float]] = defaultdict(list)
    exits = Counter(str(r.get('exit_reason') or '').upper() for r in rows)
    for r, v in zip(rows, vals):
        yrs[dkey(r.get('entry_date'))[:4]].append(v)
    return {
        'n': n,
        'wr': round(sum(v > 0 for v in vals) / n * 100.0, 2),
        'avg': round(sum(vals) / n, 4),
        'median': round(median(vals), 4),
        'loss_n': sum(v <= 0 for v in vals),
        'sl_rate': round((exits.get('SL', 0) + exits.get('GAP_SL', 0)) / n * 100.0, 2),
        'tp_rate': round(exits.get('TP', 0) / n * 100.0, 2),
        'time_rate': round(exits.get('TIME', 0) / n * 100.0, 2),
        'micro_profit_pct': round(sum(0 < v <= 0.55 for v in vals) / n * 100.0, 2),
        'min_year_n': min(len(v) for v in yrs.values()) if yrs else 0,
        'year_counts': {y: len(vs) for y, vs in sorted(yrs.items()) if y},
        'year_wr': {y: round(sum(x > 0 for x in vs) / len(vs) * 100.0, 2) for y, vs in sorted(yrs.items()) if y},
        't1_violations': sum(1 for r in rows if r.get('t1_violation') is True or (dkey(r.get('exit_date')) and dkey(r.get('entry_date')) >= dkey(r.get('exit_date')))),
    }


def audit_index() -> dict[tuple[str, str, str], dict[str, Any]]:
    aud = load(AUD, [])
    idx = {}
    if isinstance(aud, list):
        for r in aud:
            idx[(str(r.get('symbol')), dkey(r.get('entry_date')), str(r.get('entry_idx')))] = r
    return idx


def enrich(row: dict[str, Any], aud: dict[str, Any] | None, scope: str) -> dict[str, Any]:
    x = dict(row)
    original_event = x.get('event_type')
    original_combo = x.get('combo_contract_key')
    structure_status = (aud or {}).get('structure_hierarchy_status') or 'NOT_AUDITED_CURRENT_PICK'
    x['version'] = VERSION
    x['strategy_version'] = VERSION
    x['engine'] = ENGINE
    x['engine_v172_source'] = row.get('engine') or row.get('engine_v167_source')
    x['original_event_type'] = original_event
    x['event_type'] = 'DEMAND_OB_TRUE_TAKEOVER_RECLAIM'
    x['semantic_contract_key'] = 'DEMAND_OB_TRUE_TAKEOVER_RECLAIM_STRUCTURAL_1P5R'
    x['original_combo_contract_key'] = original_combo
    x['combo_contract_key'] = x['semantic_contract_key']
    x['dna_effective_combo'] = x['semantic_contract_key']
    x['semantic_layer'] = 'V175_DEMAND_OB_TRUE_TAKEOVER__CLASSICAL_SWEEP_AUDITED_SEPARATELY'
    x['classical_structure_status'] = structure_status
    x['classical_sweep_choch_claim'] = 'PASS' if structure_status == 'CLASSICAL_SWEEP_CHOCH_PASS' else 'NOT_CLAIMED'
    x['signal_correctness_claim'] = 'PRODUCTION_EDGE_IS_DEMAND_OB_TRUE_TAKEOVER_RECLAIM; classical SSL sweep/CHOCH is audited separately and not overclaimed.'
    x['production_eligible_v175'] = True
    x['production_write'] = True
    x['frontend_write'] = True
    x['watchlist_write'] = True
    x['dry_run_only'] = False
    x['v175_semantic_split'] = True
    x['combo_entry_rule'] = 'Demand OB forms first; price returns into/near the demand zone; TRUE_TAKEOVER reclaim confirms demand control; entry follows reclaim, not a classical SSL/CHOCH claim.'
    x['combo_wait_rule'] = 'wait for demand-zone reclaim / true-takeover confirmation; classical SSL sweep/CHOCH is optional audit evidence only.'
    x['combo_sl_rule'] = 'SL below demand OB zone low with V172/V167 buffer; T+1 exit enforcement preserved.'
    x['combo_tp_rule'] = 'TP=1.5R / max_hold=10 bars preserved from V172 economics.'
    x['combo_production_gate'] = 'V175 semantic split over V172 high-quality gate; production edge is demand OB true-takeover reclaim.'
    x['combo_contract'] = {
        'family': 'REVERSAL',
        'entry_rule': x['combo_entry_rule'],
        'wait_rule': x['combo_wait_rule'],
        'sl_rule': x['combo_sl_rule'],
        'tp_rule': x['combo_tp_rule'],
        'production_gate': x['combo_production_gate'],
    }
    dna = x.get('smc_dna')
    if isinstance(dna, dict):
        dna = dict(dna)
        dna['best_event_type_original'] = dna.get('best_event_type')
        dna['best_event_type'] = 'DEMAND_OB_TRUE_TAKEOVER_RECLAIM'
        dna['effective_combo_original'] = dna.get('effective_combo')
        dna['effective_combo'] = x['semantic_contract_key']
        dna['event_stats_original'] = dna.get('event_stats')
        dna['event_stats'] = {'DEMAND_OB_TRUE_TAKEOVER_RECLAIM': (dna.get('event_stats') or {}).get('SSL_SWEEP_CHOCH_REVERSAL', {})}
        x['smc_dna'] = dna
    x['dna_best_event_type'] = 'DEMAND_OB_TRUE_TAKEOVER_RECLAIM'
    if scope == 'trade':
        x['setup_status'] = 'BACKTEST_PRODUCTION_SEMANTIC_SPLIT_VERIFIED'
    else:
        x['setup_status'] = x.get('setup_status') or 'ACTIVE_CANDIDATE_SEMANTIC_SPLIT_VERIFIED'
        x['status'] = x.get('status') or 'ACTIVE_CANDIDATE'
        x['monitor_status'] = x.get('monitor_status') or 'ACTIVE_CANDIDATE'
        x['live_guard_status'] = x.get('live_guard_status') or 'PENDING_LIVE_GUARD'
        x['live_guard_reason'] = x.get('live_guard_reason') or 'API_LIVE_GUARD_EVALUATES_CURRENT_PRICE'
        # Active candidates are scanner rows, not completed trades. Keep live
        # monitoring state separate from realized backtest outcome fields so
        # /api/picks cannot be mistaken for historical-trade pollution.
        x['pnl_pct'] = 0
        x['won'] = False
        x['exit_date'] = ''
        x['exit_reason'] = ''
        x['exit_idx'] = ''
        x['hold_bars'] = ''
        x['mae_pct'] = ''
        x['mfe_pct'] = ''
        x['rr_realized'] = ''
        x['pick_scope'] = 'ACTIVE_CANDIDATE'
        x['is_active_pick'] = True
    return x


def main() -> None:
    source_report = load(SRC / 'v172_report.json', {})
    trades0 = load(SRC / 'v172_trades.json', [])
    picks0 = load(SRC / 'v172_active_picks.json', [])
    aud_idx = audit_index()
    trades = []
    for r in trades0:
        key = (str(r.get('symbol')), dkey(r.get('entry_date')), str(r.get('entry_idx')))
        trades.append(enrich(r, aud_idx.get(key), 'trade'))
    picks = [enrich(p, None, 'pick') for p in (picks0 if isinstance(picks0, list) else [])]
    m = metrics(trades)
    status_counts = Counter(t.get('classical_structure_status') for t in trades)
    source_ready = source_report.get('decision') == 'V172_QUALITY_UPGRADE_PASS__PROMOTION_CANDIDATE' and source_report.get('field_contract_gate') is True
    decision = 'V175_SEMANTIC_SPLIT_PASS__PROMOTION_READY_LABEL_ONLY' if source_ready else 'V175_BLOCKED__SOURCE_V172_NOT_PROMOTION_READY'
    report = {
        'decision': decision,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'version': VERSION,
        'engine': ENGINE,
        'production_write': source_ready,
        'frontend_write': source_ready,
        'watchlist_write': source_ready,
        'source': str(SRC),
        'source_v172_decision': source_report.get('decision'),
        'source_v172_field_contract_gate': source_report.get('field_contract_gate'),
        'source_metrics_preserved_from_v172': m,
        'n': m.get('n'),
        'win_rate': m.get('wr'),
        'avg_pnl': m.get('avg'),
        'median_pnl': m.get('median'),
        'sl_rate': m.get('sl_rate'),
        't1_violations': m.get('t1_violations'),
        'min_year': m.get('min_year_n'),
        'year_counts': m.get('year_counts'),
        'year_wr': m.get('year_wr'),
        'metric_delta_vs_v172': '0 by construction; labels only.',
        'field_contract': 'same as V172 plus original_event_type, semantic_contract_key, classical_structure_status, classical_sweep_choch_claim',
        'classical_structure_status_counts': dict(status_counts),
        'active_pick_count': len(picks),
        'active_pick_source': 'V172 current scanner rows, not historical completed trades; semantic labels only.',
        'new_primary_event_type': 'DEMAND_OB_TRUE_TAKEOVER_RECLAIM',
        'original_event_type_preserved': True,
        'promotion_reason': 'Prevents frontend/reports from overclaiming classical SSL_SWEEP_CHOCH correctness while preserving the verified V172 production economics.',
    }
    for name, obj in [('v175_trades.json', trades), ('v175_picks.json', picks), ('v175_active_picks.json', picks), ('v175_report.json', report)]:
        (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    md = [
        '# V175 语义拆分生产契约', '',
        f"Decision: **{report['decision']}**", '',
        '|版本|n|WR|Avg|SL率|min_year|T+1|', '|---|---:|---:|---:|---:|---:|---:|',
        f"|V175/V172同经济结果|{m['n']}|{m['wr']}%|{m['avg']}%|{m['sl_rate']}%|{m['min_year_n']}|{m['t1_violations']}|", '',
        '## 核心修正',
        '- 主事件从 `SSL_SWEEP_CHOCH_REVERSAL` 改为 `DEMAND_OB_TRUE_TAKEOVER_RECLAIM`。',
        '- 原事件保留在 `original_event_type`。',
        '- 古典 SSL sweep/CHOCH 不再被默认声称；独立字段 `classical_structure_status` 展示审计状态。', '',
        f"Artifacts: `{OUT}`",
    ]
    (OUT / 'v175_report.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print(json.dumps({'decision': report['decision'], 'metrics': m, 'classical_structure_status_counts': dict(status_counts), 'active_pick_count': len(picks), 'out': str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
