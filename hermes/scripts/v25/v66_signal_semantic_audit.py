#!/usr/bin/env python3
"""V66 signal semantic audit.

This verifies bar-level SMC invariants for traded V66 signals. It is stricter than
provenance: provenance matches ids/indices; this checks candle geometry and causal
semantics for OB/FVG/BOS/CHOCH/MSS.
"""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v66' / 'v66_trades.json'
OUT_JSON = ROOT / 'smc_audit' / 'v66_signal_semantic_audit.json'
OUT_MD = ROOT / 'smc_audit' / 'v66_signal_semantic_audit.md'
KLINE_DIR = ROOT / 'kline_cache'


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def i(x: Any, default: int = -1) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def kpath(symbol: str) -> Path:
    stem = symbol.replace('.', '_')
    p = KLINE_DIR / f'{stem}_daily_750.json'
    return p if p.exists() else KLINE_DIR / f'{stem}_daily_300.json'


def swing_high(klines: List[Dict[str, Any]], idx: int, left: int = 3, right: int = 3) -> bool:
    if idx - left < 0 or idx + right >= len(klines):
        return False
    high = f(klines[idx].get('h'))
    return high > 0 and all(j == idx or f(klines[j].get('h')) < high for j in range(idx - left, idx + right + 1))


def swing_low(klines: List[Dict[str, Any]], idx: int, left: int = 3, right: int = 3) -> bool:
    if idx - left < 0 or idx + right >= len(klines):
        return False
    low = f(klines[idx].get('l'))
    return low > 0 and all(j == idx or f(klines[j].get('l')) > low for j in range(idx - left, idx + right + 1))


def latest_confirmed_swing_high_before(klines: List[Dict[str, Any]], idx: int) -> Dict[str, Any] | None:
    for j in range(idx - 3, 5, -1):
        if j + 3 <= idx and swing_high(klines, j):
            return {'idx': j, 'price': f(klines[j].get('h')), 'confirm_idx': j + 3}
    return None


def latest_confirmed_swing_low_before(klines: List[Dict[str, Any]], idx: int) -> Dict[str, Any] | None:
    for j in range(idx - 3, 5, -1):
        if j + 3 <= idx and swing_low(klines, j):
            return {'idx': j, 'price': f(klines[j].get('l')), 'confirm_idx': j + 3}
    return None


def nearest_opposite_candle_before(klines: List[Dict[str, Any]], event_idx: int, direction: str, max_back: int = 15) -> int:
    for j in range(event_idx - 1, max(-1, event_idx - max_back - 1), -1):
        op, cl = f(klines[j].get('o')), f(klines[j].get('c'))
        if direction == 'bull' and cl < op:
            return j
        if direction == 'bear' and cl > op:
            return j
    return -1


def audit_trade(t: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str(t.get('symbol') or '')
    klines = load(kpath(symbol), [])
    issues: List[str] = []
    evidence: Dict[str, Any] = {}
    if not klines:
        return {'symbol': symbol, 'entry_date': t.get('entry_date'), 'status': 'FAIL', 'issues': ['MISSING_KLINE']}
    si, zi, ci, ei = [i(t.get(k)) for k in ('source_event_idx', 'zone_idx', 'conf_index', 'entry_index')]
    zone_type = str(t.get('zone_type') or '')
    conf_type = str(t.get('conf_type') or '')

    if zone_type == 'OB_Bull':
        if not (0 <= zi < len(klines)):
            issues.append('OB_MISSING_ZONE_IDX')
        else:
            op, cl = f(klines[zi].get('o')), f(klines[zi].get('c'))
            if cl >= op:
                issues.append('OB_ZONE_NOT_LAST_BEARISH_CANDLE')
            anchor_idx = si if si >= 0 else ci
            expected = nearest_opposite_candle_before(klines, anchor_idx, 'bull') if anchor_idx >= 0 else -1
            evidence['ob_expected_nearest_bearish_idx'] = expected
            if expected >= 0 and abs(expected - zi) > 2:
                issues.append('OB_NOT_NEAREST_BACKSCAN_CANDLE')
            if anchor_idx >= 0 and not (zi < anchor_idx <= ci if ci >= 0 else zi < anchor_idx):
                issues.append('OB_NOT_BEFORE_STRUCTURE_EVENT')

    if zone_type == 'FVG_Bull':
        if not (2 <= zi < len(klines)):
            issues.append('FVG_MISSING_GEOMETRY_IDX')
        else:
            h0 = f(klines[zi - 2].get('h'))
            l2 = f(klines[zi].get('l'))
            evidence['fvg_gap_low'] = h0
            evidence['fvg_gap_high'] = l2
            if not (h0 > 0 and l2 > h0 * 1.0005):
                issues.append('FVG_THREE_CANDLE_GAP_INVALID')

    if conf_type in ('BOS_Bull', 'CHOCH_Bull', 'MSS_Bull'):
        if not (0 <= ci < len(klines)):
            issues.append('CONF_MISSING_INDEX')
        else:
            sw = latest_confirmed_swing_high_before(klines, ci)
            evidence['latest_confirmed_high_before_conf'] = sw
            close = f(klines[ci].get('c'))
            if not sw:
                issues.append('CONF_NO_CONFIRMED_SWING_HIGH_BEFORE')
            elif close <= sw['price'] * 1.001:
                issues.append('CONF_CLOSE_DID_NOT_BREAK_SWING_HIGH')
            if conf_type == 'CHOCH_Bull':
                prev_low = latest_confirmed_swing_low_before(klines, ci)
                evidence['latest_confirmed_low_before_conf'] = prev_low
                if not prev_low:
                    issues.append('CHOCH_NO_PRIOR_SWING_LOW_CONTEXT')
            if conf_type == 'MSS_Bull':
                found_ssl = False
                for j in range(max(0, ci - 20), ci + 1):
                    swl = latest_confirmed_swing_low_before(klines, j)
                    if swl and f(klines[j].get('l')) < swl['price'] * 0.997 and f(klines[j].get('c')) > swl['price'] * 0.999:
                        found_ssl = True
                        break
                if not found_ssl:
                    issues.append('MSS_NO_RECENT_SSL_SWEEP')

    if 0 <= zi < len(klines) and 0 <= ci < len(klines) and zi > ci:
        issues.append('ZONE_AFTER_CONFIRM')
    if 0 <= ci < len(klines) and 0 <= ei < len(klines) and ci > ei:
        issues.append('CONF_AFTER_ENTRY')

    return {
        'symbol': symbol,
        'entry_date': t.get('entry_date'),
        'zone_type': zone_type,
        'conf_type': conf_type,
        'family': t.get('v59_setup_family'),
        'idx': {'source': si, 'zone': zi, 'confirm': ci, 'entry': ei},
        'status': 'PASS' if not issues else 'FAIL',
        'issues': issues,
        'evidence': evidence,
    }


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    trades = load(TRADES, [])
    rows = [audit_trade(t) for t in trades]
    bad = [r for r in rows if r['status'] != 'PASS']
    issue_counts = Counter(x for r in bad for x in r.get('issues', []))
    by_zone = Counter((r.get('zone_type'), r['status']) for r in rows)
    summary = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'n_trades': len(rows),
        'pass_count': len(rows) - len(bad),
        'fail_count': len(bad),
        'pass_rate_pct': round((len(rows) - len(bad)) / len(rows) * 100, 2) if rows else 0,
        'issue_counts': dict(issue_counts),
        'by_zone_status': {str(k): v for k, v in by_zone.items()},
        'strict_pass': len(bad) == 0,
        'note': 'Strict invariant audit; failures indicate semantic items requiring replay, not necessarily all production-fatal without visual review.',
    }
    OUT_JSON.write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=2))
    md = ['# V66 Signal Semantic Audit\n\n', '```json\n', json.dumps(summary, ensure_ascii=False, indent=2), '\n```\n\n']
    for r in bad[:80]:
        md.append(f"- {r.get('symbol')} {r.get('entry_date')} {r.get('zone_type')}->{r.get('conf_type')} issues={','.join(r.get('issues') or [])}\n")
    OUT_MD.write_text(''.join(md))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
