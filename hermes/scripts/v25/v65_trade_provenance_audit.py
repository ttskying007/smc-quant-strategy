#!/usr/bin/env python3
"""V65 trade provenance audit.

Audits existing candidate trades (V65 if present, otherwise V49) against the V65
signal snapshot. This makes gaps explicit before V65 engine exists.
"""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path('/root/.hermes')
SNAPSHOT = ROOT / 'smc_opt_v50_signal' / 'v50_signal_snapshot.json'
V65_TRADES = ROOT / 'smc_opt_v65' / 'v65_trades.json'
V49_TRADES = ROOT / 'smc_opt_v49_exit_optimized' / 'v49_trades.json'
OUT_JSON = ROOT / 'smc_audit' / 'v65_trade_provenance_audit.json'
OUT_MD = ROOT / 'smc_audit' / 'v65_trade_provenance_audit.md'
REQUIRED_IDX = ['source_event_idx', 'zone_idx', 'conf_index', 'entry_index', 'exit_index']


def _i(x: Any, default: int = -1) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _trade_file() -> Path:
    return V65_TRADES if V65_TRADES.exists() else V49_TRADES


def _families_for_key(key: str, trade: Dict[str, Any]) -> List[str]:
    # V65 engine writes explicit execution/confirmation overlay ids into trades.
    # Prefer exact ids over nearest raw-family matching; raw snapshot remains useful for zone/source.
    if key == 'source_event_idx':
        return ['structure', 'sweep']
    if key == 'zone_idx':
        z = str(trade.get('zone_type', '')).lower()
        if 'fvg' in z:
            return ['fvg']
        if 'ob' in z:
            return ['ob']
        return ['ob', 'fvg', 'bpr', 'ote', 'lv']
    if key == 'conf_index':
        return ['confirm', 'entry', 'sweep', 'structure', 'ob', 'fvg']
    if key == 'entry_index':
        return ['entry']
    if key == 'exit_index':
        return ['exit']
    return []


def _nearest_signal(signals: List[Dict[str, Any]], idx: int, families: List[str]) -> Dict[str, Any] | None:
    if idx < 0:
        return None
    cands = [s for s in signals if (not families or s.get('family') in families)]
    if not cands:
        return None
    return min(cands, key=lambda s: abs(_i(s.get('idx')) - idx))


def _check_idx(trade: Dict[str, Any], signals: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    idx = _i(trade.get(key))
    id_field = {'source_event_idx': 'source_event_id', 'zone_idx': 'zone_id', 'conf_index': 'conf_id', 'entry_index': 'entry_id', 'exit_index': 'exit_id'}.get(key)
    explicit_id = trade.get(id_field) if id_field else None
    if idx < 0:
        return {'expected_idx': idx, 'matched': False, 'bar_diff': None, 'issue': f'MISSING_{key.upper()}'}
    if explicit_id and (':confirm:' in explicit_id or ':entry:' in explicit_id or ':exit:' in explicit_id):
        return {'expected_idx': idx, 'matched': True, 'bar_diff': 0, 'explicit_id': explicit_id, 'issue': ''}
    families = _families_for_key(key, trade)
    sig = _nearest_signal(signals, idx, families)
    if not sig:
        # Entry/exit are execution markers and may not exist in raw signal snapshot before V65 engine.
        return {'expected_idx': idx, 'matched': key in ('entry_index', 'exit_index'), 'bar_diff': 0 if key in ('entry_index', 'exit_index') else None, 'issue': '' if key in ('entry_index', 'exit_index') else f'NO_SIGNAL_FAMILY_{key.upper()}'}
    diff = abs(_i(sig.get('idx')) - idx)
    matched = diff == 0
    return {
        'expected_idx': idx,
        'matched': matched,
        'bar_diff': diff,
        'nearest_signal_id': sig.get('signal_id'),
        'nearest_family': sig.get('family'),
        'nearest_type': sig.get('type'),
        'nearest_idx': sig.get('idx'),
        'issue': '' if matched else f'BAR_DIFF_{key.upper()}_{diff}',
    }


def audit_trade(trade: Dict[str, Any], signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    checks = {k: _check_idx(trade, signals, k) for k in REQUIRED_IDX}
    issues = []
    for k, c in checks.items():
        if c.get('issue'):
            issues.append(c['issue'])
    seq = [_i(trade.get(k)) for k in REQUIRED_IDX]
    labels = list(REQUIRED_IDX)
    for a, b, la, lb in zip(seq, seq[1:], labels, labels[1:]):
        if a >= 0 and b >= 0 and a > b:
            issues.append(f'TIME_ORDER_{la}_GT_{lb}')
    entry_price = _f(trade.get('entry_price'))
    sl = _f(trade.get('sl'))
    risk_pct = _f(trade.get('risk_pct'))
    if entry_price > 0 and sl > 0 and risk_pct <= 0:
        issues.append('MISSING_RISK_PCT')
    status = 'PASS' if not issues else 'FAIL'
    return {
        'symbol': trade.get('symbol'),
        'entry_date': trade.get('entry_date'),
        'exit_date': trade.get('exit_date'),
        'zone_type': trade.get('zone_type'),
        'conf_type': trade.get('conf_type'),
        'checks': checks,
        'status': status,
        'issues': issues,
    }


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    snapshot = _load(SNAPSHOT, {})
    trade_path = _trade_file()
    trades = _load(trade_path, [])
    rows = []
    issue_counts = Counter()
    for t in trades:
        r = audit_trade(t, snapshot.get(t.get('symbol', ''), []))
        rows.append(r)
        issue_counts.update(r['issues'])
    fatal = [r for r in rows if r['status'] != 'PASS']
    summary = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'trade_file': str(trade_path),
        'snapshot_file': str(SNAPSHOT),
        'n_trades': len(trades),
        'pass_count': len(rows) - len(fatal),
        'fatal_count': len(fatal),
        'issue_counts': dict(issue_counts),
        'note': 'Before V65 engine, V49 trades may lack source_event_idx/zone_idx/conf_index. This audit exposes required fixes.'
    }
    out = {'summary': summary, 'rows': rows}
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    md = ['# V65 Trade Provenance Audit\n\n', '```json\n', json.dumps(summary, ensure_ascii=False, indent=2), '\n```\n\n']
    for r in fatal[:50]:
        md.append(f"- {r['symbol']} {r['entry_date']} status={r['status']} issues={','.join(r['issues'])}\n")
    OUT_MD.write_text(''.join(md))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
