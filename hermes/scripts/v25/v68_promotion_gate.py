#!/usr/bin/env python3
"""Promotion gate for V68 directional-classifier candidate."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
REPORT = ROOT / 'smc_opt_v68_directional/v68_report.json'
SEM = ROOT / 'smc_audit/v68_signal_semantic_gate.json'
EDGE = ROOT / 'smc_audit/v68_directional_edge_gate.json'
OUT_JSON = ROOT / 'smc_audit/v68_promotion_gate.json'
OUT_MD = ROOT / 'smc_audit/v68_promotion_gate.md'


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def main() -> None:
    report = load(REPORT, {})
    sem_doc = load(SEM, {})
    sem = sem_doc.get('summary', sem_doc)
    edge = load(EDGE, {})
    metrics = report.get('metrics', {})
    checks = {
        'strict_geometry_semantic_pass': sem.get('strict_pass') is True,
        'direction_architecture_pass': sem.get('architecture_pass') is True,
        'directional_edge_pass': edge.get('directional_edge_pass') is True,
        'effect_pass': report.get('effect_pass') is True,
        'min_trade_count': metrics.get('n_trades', 0) >= report.get('thresholds', {}).get('MIN_TRADES', 30),
        'min_win_rate': metrics.get('wr', 0) >= report.get('thresholds', {}).get('MIN_WR', 70),
        'max_sl_rate': metrics.get('sl_rate', 100) <= report.get('thresholds', {}).get('MAX_SL_RATE', 30),
        'min_avg_pnl': metrics.get('avg_pnl', -999) >= report.get('thresholds', {}).get('MIN_AVG_PNL', 1.0),
    }
    failed = [k for k, v in checks.items() if not v]
    promote = not failed
    out = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'candidate': 'V68_DIRECTION_CLASSIFIER_CANDIDATE',
        'current_production': 'V66_RECENT_REENTRY_RISK_OVERLAY',
        'promote': promote,
        'rollback_to': None if promote else 'V66_RECENT_REENTRY_RISK_OVERLAY',
        'failed_checks': failed,
        'checks': checks,
        'semantic_summary': sem,
        'directional_edge_summary': edge,
        'metrics': metrics,
        'architecture_checks': report.get('architecture_checks', {}),
        'decision': 'PROMOTE_V68' if promote else 'ROLLBACK_KEEP_V66',
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    OUT_MD.write_text('# V68 Promotion Gate\n\n```json\n' + json.dumps(out, ensure_ascii=False, indent=2) + '\n```\n')
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
