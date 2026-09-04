#!/usr/bin/env python3
"""Semantic hard gate for V67 strict-registry trades."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from strict_smc_registry import FVG_MIN_GAP, BREAK_BUFFER, f, nearest_bearish_candle

ROOT = Path('/root/.hermes')
KLINE_DIR = ROOT / 'kline_cache'
TRADES = ROOT / 'smc_opt_v67_strict/v67_trades.json'
OUT_JSON = ROOT / 'smc_audit/v67_signal_semantic_gate.json'
OUT_MD = ROOT / 'smc_audit/v67_signal_semantic_gate.md'


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def kpath(symbol: str) -> Path:
    stem = symbol.replace('.', '_')
    return KLINE_DIR / f'{stem}_daily_750.json'


def i(x: Any, default: int = -1) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def audit_trade(t: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str(t.get('symbol', ''))
    klines = load(kpath(symbol), [])
    issues: List[str] = []
    zi, ci, si, ei = [i(t.get(k)) for k in ('zone_idx', 'conf_index', 'source_event_idx', 'entry_index')]
    zone_type = str(t.get('zone_type') or '')
    conf_type = str(t.get('conf_type') or '')
    if not klines:
        return {'symbol': symbol, 'entry_date': t.get('entry_date'), 'status': 'FAIL', 'issues': ['MISSING_KLINE']}
    if not (0 <= zi < len(klines) and 0 <= ci < len(klines) and 0 <= ei < len(klines)):
        issues.append('MISSING_REQUIRED_INDEX')
    if zone_type == 'OB_Bull' and 0 <= zi < len(klines) and 0 <= ci < len(klines):
        b = klines[zi]
        if f(b.get('c')) >= f(b.get('o')):
            issues.append('OB_ZONE_NOT_BEARISH_CANDLE')
        expected = nearest_bearish_candle(klines, ci)
        if expected != zi:
            issues.append('OB_NOT_NEAREST_BACKSCAN_CANDLE')
        if not (zi < ci <= ei):
            issues.append('OB_NOT_BEFORE_CONFIRM_ENTRY')
    if zone_type == 'FVG_Bull' and 2 <= zi < len(klines):
        h0 = f(klines[zi - 2].get('h'))
        l2 = f(klines[zi].get('l'))
        if not (h0 > 0 and l2 > h0 * FVG_MIN_GAP):
            issues.append('FVG_THREE_CANDLE_GAP_INVALID')
        if abs(f(t.get('raw_zone_low')) - h0) > max(0.02, h0 * 0.001):
            issues.append('FVG_RAW_LOW_MISMATCH')
        if abs(f(t.get('raw_zone_high')) - l2) > max(0.02, l2 * 0.001):
            issues.append('FVG_RAW_HIGH_MISMATCH')
    if conf_type in ('BOS_Bull', 'CHOCH_Bull') and 0 <= ci < len(klines):
        broken = f(t.get('broken_swing_price'))
        if broken <= 0:
            issues.append('CONF_MISSING_BROKEN_SWING_PRICE')
        elif f(klines[ci].get('c')) <= broken * BREAK_BUFFER:
            issues.append('CONF_CLOSE_DID_NOT_BREAK_SWING_HIGH')
        if si != ci:
            issues.append('SOURCE_EVENT_NOT_CONFIRM_INDEX')
    if 0 <= ci < len(klines) and 0 <= ei < len(klines) and not (ci < ei):
        issues.append('CONF_NOT_BEFORE_ENTRY')
    return {
        'symbol': symbol,
        'entry_date': t.get('entry_date'),
        'zone_type': zone_type,
        'conf_type': conf_type,
        'status': 'PASS' if not issues else 'FAIL',
        'issues': issues,
        'idx': {'zone': zi, 'confirm': ci, 'source': si, 'entry': ei},
    }


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    trades = load(TRADES, [])
    rows = [audit_trade(t) for t in trades]
    bad = [r for r in rows if r['status'] != 'PASS']
    issues = Counter(x for r in bad for x in r.get('issues', []))
    by_zone = Counter((r.get('zone_type'), r['status']) for r in rows)
    summary = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'trade_file': str(TRADES),
        'n_trades': len(rows),
        'pass_count': len(rows) - len(bad),
        'fail_count': len(bad),
        'pass_rate_pct': round((len(rows) - len(bad)) / len(rows) * 100, 3) if rows else 0,
        'strict_pass': len(rows) > 0 and len(bad) == 0,
        'issue_counts': dict(issues),
        'by_zone_status': {str(k): v for k, v in by_zone.items()},
    }
    OUT_JSON.write_text(json.dumps({'summary': summary, 'rows': rows[:1000], 'bad_sample': bad[:200]}, ensure_ascii=False, indent=2))
    OUT_MD.write_text('# V67 Signal Semantic Gate\n\n```json\n' + json.dumps(summary, ensure_ascii=False, indent=2) + '\n```\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
