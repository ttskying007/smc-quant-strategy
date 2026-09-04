#!/usr/bin/env python3
"""V105-A structural TP2 re-entry audit artifact.

This is a research/pre-promotion generator only. It does not alter frontend
routing. It reuses V103-A enrichment, then applies the V105-A selector found
in /root/audit_20260617_full_backtest/v105a_validation.md.

Selector, evaluated only inside V103-A production_eligible_v102 rows:
  V104B = G1_STRICT_STRUCTURAL_TP2 OR G4_RISK_1P1_NO_MICROHL_NO_B_TIER
  G1 = v100_tier != B_OBSERVE_HIGH_WR
       AND mtf_trend_permission != REVERSAL_ONLY_HIGH_RISK
       AND tp2_target_type is non-empty
  G4 = v100_tier != B_OBSERVE_HIGH_WR
       AND sl_mode != micro_HL_BUFFER_0_5PCT
       AND risk_pct <= 1.1
  V105A = V104B OR ((NOT V104B) AND tp2_rr <= 5.059)

Meaning: keep the proven V104B core, then restore coverage only when the
structural TP2 is not overextended. This is a scanner-time field gate; no
outcome/PnL/exit fields are used by the selector.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

sys.path.insert(0, '/root/.hermes/scripts/v25')
import v103a_risk_gate as v103a  # noqa: E402

ROOT = Path('/root/.hermes')
OUT_DIR = ROOT / 'smc_opt_v105a_structural_tp2_reentry'
OUT_DIR.mkdir(parents=True, exist_ok=True)
ENGINE = 'V105A_STRUCTURAL_TP2_REENTRY'
NET_SUCCESS_PCT = v103a.NET_SUCCESS_PCT
FEE_PCT = v103a.FEE_PCT
TP2_RR_REENTRY_MAX = 5.059


def fnum(x: Any, default: float = 0.0) -> float:
    return v103a.fnum(x, default)


def dkey(v: Any) -> str:
    return v103a.dkey(v)


def nonempty(x: Any) -> bool:
    return str(x or '').strip() != ''


def v104b_gate(row: Dict[str, Any]) -> bool:
    tier_ok = row.get('v100_tier') != 'B_OBSERVE_HIGH_WR'
    g1 = (
        tier_ok
        and row.get('mtf_trend_permission') != 'REVERSAL_ONLY_HIGH_RISK'
        and nonempty(row.get('tp2_target_type'))
    )
    g4 = (
        tier_ok
        and row.get('sl_mode') != 'micro_HL_BUFFER_0_5PCT'
        and 0 < fnum(row.get('risk_pct')) <= 1.1
    )
    return bool(g1 or g4)


def v105a_gate(row: Dict[str, Any]) -> bool:
    if not row.get('production_eligible_v102'):
        return False
    core = v104b_gate(row)
    reentry = (not core) and (0 < fnum(row.get('tp2_rr')) <= TP2_RR_REENTRY_MAX)
    return bool(core or reentry)


def clean_sequence_gate(row: Dict[str, Any]) -> bool:
    """Hard audit only: do not accept same-day exits or event after entry."""
    entry = dkey(row.get('entry_date'))
    exit_ = dkey(row.get('exit_date'))
    event = dkey(row.get('event_date'))
    if entry and exit_ and entry == exit_:
        return False
    if event and entry and event > entry:
        return False
    return True


def stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0, 'wr': 0, 'avg': 0, 'sl_rate': 0, 'sl_n': 0}
    wins = [r for r in rows if fnum(r.get('net_pnl_pct'), fnum(r.get('pnl_pct')) - FEE_PCT) >= NET_SUCCESS_PCT]
    sl = [r for r in rows if str(r.get('exit_reason') or '') == 'SL_HIT']
    return {
        'n': len(rows),
        'wr': round(len(wins) / len(rows) * 100, 2),
        'avg': round(sum(fnum(r.get('net_pnl_pct'), fnum(r.get('pnl_pct')) - FEE_PCT) for r in rows) / len(rows), 4),
        'sl_rate': round(len(sl) / len(rows) * 100, 2),
        'sl_n': len(sl),
    }


def by_year(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        y = dkey(r.get('entry_date'))[:4] or 'UNKNOWN'
        buckets[y].append(r)
    return {y: stats(buckets[y]) for y in sorted(buckets)}


def rolling_sl(rows: List[Dict[str, Any]], win: int) -> Dict[str, Any]:
    ordered = sorted(rows, key=lambda r: (dkey(r.get('entry_date')), str(r.get('symbol') or '')))
    vals: List[float] = []
    for i in range(0, len(ordered) - win + 1):
        chunk = ordered[i:i + win]
        vals.append(sum(1 for r in chunk if r.get('exit_reason') == 'SL_HIT') / win * 100)
    if not vals:
        return {'windows': 0}
    vals_sorted = sorted(vals)
    p90 = vals_sorted[int(0.9 * (len(vals_sorted) - 1))]
    return {
        'windows': len(vals),
        'avg_sl_rate': round(sum(vals) / len(vals), 2),
        'p90_sl_rate': round(p90, 2),
        'max_sl_rate': round(max(vals), 2),
    }


def field_missing(rows: List[Dict[str, Any]], keys: Iterable[str]) -> Dict[str, int]:
    return {k: sum(1 for r in rows if r.get(k) in (None, '', {}, [])) for k in keys}


def failure_buckets(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    failed = [r for r in rows if fnum(r.get('net_pnl_pct'), fnum(r.get('pnl_pct')) - FEE_PCT) < NET_SUCCESS_PCT]
    cols = [
        'exit_reason', 'event_type', 'combo_family', 'daily_phase', 'daily_structure_state',
        'm60_phase', 'm60_structure_state', 'weekly_phase', 'weekly_structure_state',
        'mtf_trend_permission', 'pd_zone', 'v100_tier', 'sl_mode', 'tp2_target_type',
        'tp3_target_type',
    ]
    out: List[Dict[str, Any]] = []
    for c in cols:
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in failed:
            groups[str(r.get(c) or '')].append(r)
        for val, rs in groups.items():
            if len(rs) >= 2 or val == 'SL_HIT':
                out.append({
                    'col': c,
                    'val': val,
                    'fail_n': len(rs),
                    'sl_n': sum(1 for r in rs if r.get('exit_reason') == 'SL_HIT'),
                    'avg': round(sum(fnum(r.get('net_pnl_pct'), fnum(r.get('pnl_pct')) - FEE_PCT) for r in rs) / len(rs), 4),
                    'symbols': [r.get('symbol') for r in rs[:10]],
                })
    return sorted(out, key=lambda x: (-x['fail_n'], -x['sl_n'], x['avg']))[:40]


def main() -> None:
    trades = v103a.load_json(v103a.SRC_DIR / 'v100_trades.json', [])
    active_picks = v103a.load_json(v103a.SRC_DIR / 'v100_active_picks.json', [])
    watch_picks = v103a.load_json(v103a.SRC_DIR / 'v100_watch_picks.json', [])
    if not isinstance(trades, list):
        raise SystemExit('v100_trades.json is not a list')

    dna = v103a.build_dna(trades)
    enriched_trades = [v103a.enrich_row(r, dna) for r in trades if isinstance(r, dict)]
    for r in enriched_trades:
        r['v104b_core_gate'] = v104b_gate(r)
        r['v105a_structural_tp2_reentry_gate'] = v105a_gate(r)
        r['v105a_clean_sequence_gate'] = clean_sequence_gate(r)
        r['engine_v103a'] = r.get('engine')
        if r['v105a_structural_tp2_reentry_gate']:
            r['engine'] = ENGINE
            r['production_grade_v105a'] = 'V105A_PRODUCTION_CANDIDATE'
        else:
            r['production_grade_v105a'] = 'V105A_REJECTED'

    base = [r for r in enriched_trades if r.get('production_eligible_v102')]
    v104b = [r for r in base if r.get('v104b_core_gate')]
    v105a_raw = [r for r in base if r.get('v105a_structural_tp2_reentry_gate')]
    v105a_clean = [r for r in v105a_raw if r.get('v105a_clean_sequence_gate')]
    reentry = [r for r in v105a_clean if not r.get('v104b_core_gate')]
    rejected = [r for r in base if not r.get('v105a_structural_tp2_reentry_gate')]

    enriched_active = [v103a.enrich_row(r, dna) for r in active_picks if isinstance(r, dict)]
    enriched_watch = [v103a.enrich_row(r, dna) for r in watch_picks if isinstance(r, dict)]
    active_v105a = [r for r in enriched_active if v105a_gate(r) and clean_sequence_gate(r)]
    candidate_watch = [r for r in enriched_active + enriched_watch if not (v105a_gate(r) and clean_sequence_gate(r))]

    required_fields = [
        'symbol', 'entry_date', 'event_date', 'entry_price', 'risk_pct', 'tp2_rr',
        'tp2_target_type', 'v100_tier', 'mtf_trend_permission', 'sl_mode',
        'daily_phase', 'daily_structure_state', 'm60_phase', 'weekly_phase',
        'pick_date', 'join_date', 'zone_type', 'cost_line', 'smart_money_cost',
    ]
    report = {
        'engine': ENGINE,
        'version': 'V105-A',
        'source': str(v103a.SRC_DIR),
        'decision': 'RESEARCH_CANDIDATE__NEEDS_LATEST_FULL_MARKET_SCANNER_DRY_RUN',
        'selector': {
            'base': 'production_eligible_v102 from V103-A',
            'v104b_core': 'G1_STRICT_STRUCTURAL_TP2 OR G4_RISK_1P1_NO_MICROHL_NO_B_TIER',
            'reentry': f'not v104b_core AND 0 < tp2_rr <= {TP2_RR_REENTRY_MAX}',
            'hard_clean': 'entry_date != exit_date AND event_date <= entry_date',
            'outcome_fields_used_by_selector': [],
        },
        'stats': {
            'v103a_base': stats(base),
            'v104b_core': stats(v104b),
            'v105a_raw': stats(v105a_raw),
            'v105a_clean': stats(v105a_clean),
            'v105a_reentry_added': stats(reentry),
            'v105a_rejected': stats(rejected),
        },
        'year_v105a_clean': by_year(v105a_clean),
        'rolling20_v105a_clean': rolling_sl(v105a_clean, 20),
        'rolling50_v105a_clean': rolling_sl(v105a_clean, 50),
        'gate_counts': {
            'base': len(base),
            'v104b': len(v104b),
            'v105a_raw': len(v105a_raw),
            'v105a_clean': len(v105a_clean),
            'reentry': len(reentry),
            'rejected': len(rejected),
            'active_v105a': len(active_v105a),
            'candidate_watch': len(candidate_watch),
        },
        'hard_audit': {
            't1_violations_raw': sum(1 for r in v105a_raw if dkey(r.get('entry_date')) and dkey(r.get('entry_date')) == dkey(r.get('exit_date'))),
            'event_after_entry_raw': sum(1 for r in v105a_raw if dkey(r.get('event_date')) and dkey(r.get('entry_date')) and dkey(r.get('event_date')) > dkey(r.get('entry_date'))),
            'field_missing_v105a_clean': field_missing(v105a_clean, required_fields),
            'field_missing_active_v105a': field_missing(active_v105a, required_fields),
        },
        'failure_buckets_v105a_clean': failure_buckets(v105a_clean),
        'combo_counts_v105a_clean': dict(Counter(r.get('combo_contract_key') for r in v105a_clean)),
        'mtf_permission_counts_v105a_clean': dict(Counter(r.get('mtf_trend_permission') for r in v105a_clean)),
        'next_required': [
            'Implement same selector in the true latest full-market scanner path or dry-run scanner.',
            'Verify scanner-time payload has all selector fields before BUY; no exit/PnL/MFE/MAE fields required.',
            'Only after latest full-market scan passes, route frontend/API to physical current_candidates, not historical trades.',
        ],
    }

    payloads = {
        'v105a_trades.json': enriched_trades,
        'v105a_production_clean.json': v105a_clean,
        'v105a_reentry_added.json': reentry,
        'v105a_rejected.json': rejected,
        'v105a_active_picks.json': active_v105a,
        'v105a_candidate_picks.json': candidate_watch,
        'v105a_symbol_dna.json': dna,
        'v105a_report.json': report,
    }
    for name, payload in payloads.items():
        (OUT_DIR / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
