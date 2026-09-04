#!/usr/bin/env python3
"""V67 promotion gate.

Promotion requires both strict signal semantics and production-grade effect.
If either fails, production remains V66.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
REPORT = ROOT / 'smc_opt_v67_strict/v67_report.json'
SEM = ROOT / 'smc_audit/v67_signal_semantic_gate.json'
EDGE = ROOT / 'smc_audit/v67_directional_edge_gate.json'
OUT_JSON = ROOT / 'smc_audit/v67_promotion_gate.json'
OUT_MD = ROOT / 'smc_audit/v67_promotion_gate.md'


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def main() -> None:
    report = load(REPORT, {})
    sem = load(SEM, {}).get('summary', {})
    edge = load(EDGE, {})
    metrics = report.get('metrics', {})
    checks = {
        'signal_semantic_strict_pass': sem.get('strict_pass') is True,
        'directional_edge_pass': edge.get('directional_edge_pass') is True,
        'effect_pass': report.get('effect_pass') is True,
        'min_trade_count': metrics.get('n_trades', 0) >= report.get('thresholds', {}).get('MIN_TRADES', 30),
        'min_win_rate': metrics.get('wr', 0) >= report.get('thresholds', {}).get('MIN_WR', 80.0),
        'max_sl_rate': metrics.get('sl_rate', 100) <= report.get('thresholds', {}).get('MAX_SL_RATE', 18.0),
        'min_avg_pnl': metrics.get('avg_pnl', -999) >= report.get('thresholds', {}).get('MIN_AVG_PNL', 2.0),
    }
    failed = [k for k, v in checks.items() if not v]
    promote = not failed
    out = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'candidate': 'V67_STRICT_REGISTRY_CANDIDATE',
        'current_production': 'V66_RECENT_REENTRY_RISK_OVERLAY',
        'promote': promote,
        'rollback_to': None if promote else 'V66_RECENT_REENTRY_RISK_OVERLAY',
        'failed_checks': failed,
        'checks': checks,
        'semantic_summary': sem,
        'directional_edge_summary': edge,
        'metrics': metrics,
        'decision': 'PROMOTE_V67' if promote else 'ROLLBACK_KEEP_V66',
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    md = ['# V67 Promotion Gate\n\n', '```json\n', json.dumps(out, ensure_ascii=False, indent=2), '\n```\n']
    OUT_MD.write_text(''.join(md))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
