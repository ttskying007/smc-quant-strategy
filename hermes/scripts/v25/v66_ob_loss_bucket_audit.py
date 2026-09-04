#!/usr/bin/env python3
"""V66 OB loss-bucket replay audit.

Focuses on losing OB_Bull trades and classifies root causes with bar-level evidence.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v66' / 'v66_trades.json'
OUT_JSON = ROOT / 'smc_audit' / 'v66_ob_loss_bucket_audit.json'
OUT_MD = ROOT / 'smc_audit' / 'v66_ob_loss_bucket_audit.md'
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
    if p.exists():
        return p
    return KLINE_DIR / f'{stem}_daily_300.json'


def pct(a: float, b: float) -> float:
    return (a - b) / b * 100 if b else 0.0


def date_of(klines: List[Dict[str, Any]], idx: int) -> str:
    if 0 <= idx < len(klines):
        return str(klines[idx].get('t') or klines[idx].get('date') or '')[:8]
    return ''


def replay_trade(t: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str(t.get('symbol') or '')
    klines = load(kpath(symbol), [])
    zi, ri, ci, ei, xi = [i(t.get(k)) for k in ('zone_idx', 'retrace_index', 'conf_index', 'entry_index', 'exit_index')]
    entry = f(t.get('entry_price'))
    sl = f(t.get('sl'))
    zone_low = f(t.get('raw_zone_low') or t.get('zone_low') or t.get('dz_low'))
    zone_high = f(t.get('raw_zone_high') or t.get('zone_high') or t.get('dz_high'))
    if not zone_low and 0 <= zi < len(klines):
        zone_low = f(klines[zi].get('l'))
        zone_high = f(klines[zi].get('h'))
    issues: List[str] = []
    evidence: Dict[str, Any] = {}
    if not klines or ei < 0:
        return {'symbol': symbol, 'entry_date': t.get('entry_date'), 'fatal': 'MISSING_KLINE_OR_ENTRY'}

    if 0 <= zi < len(klines):
        zb = klines[zi]
        evidence['zone_bar'] = {'idx': zi, 'date': date_of(klines, zi), 'o': f(zb.get('o')), 'h': f(zb.get('h')), 'l': f(zb.get('l')), 'c': f(zb.get('c'))}
        if not (f(zb.get('c')) < f(zb.get('o'))):
            issues.append('OB_ZONE_NOT_BEARISH_CANDLE')
    else:
        issues.append('MISSING_ZONE_IDX')

    if zone_low and entry:
        evidence['entry_vs_zone_low_pct'] = round(pct(entry, zone_low), 3)
        if entry > zone_high > 0:
            issues.append('ENTRY_ABOVE_ZONE_HIGH')
        if entry > zone_low * 1.08:
            issues.append('ENTRY_TOO_FAR_FROM_OB_LOW')
    if sl and zone_low:
        evidence['sl_below_zone_low_pct'] = round(pct(zone_low, sl), 3)
        if sl >= zone_low:
            issues.append('SL_NOT_BELOW_ZONE_LOW')

    pre_entry_breaks = []
    for idx in range(max(0, zi + 1), min(ei, len(klines))):
        if zone_low and f(klines[idx].get('c')) < zone_low:
            pre_entry_breaks.append({'idx': idx, 'date': date_of(klines, idx), 'close': f(klines[idx].get('c'))})
    if pre_entry_breaks:
        issues.append('ZONE_CLOSED_BELOW_BEFORE_ENTRY')
        evidence['pre_entry_breaks'] = pre_entry_breaks[:5]

    exit_bar = klines[xi] if 0 <= xi < len(klines) else {}
    if exit_bar:
        evidence['exit_bar'] = {'idx': xi, 'date': date_of(klines, xi), 'o': f(exit_bar.get('o')), 'h': f(exit_bar.get('h')), 'l': f(exit_bar.get('l')), 'c': f(exit_bar.get('c'))}
        if sl and f(exit_bar.get('o')) < sl:
            issues.append('GAP_THROUGH_SL')
        elif sl and f(exit_bar.get('l')) <= sl:
            issues.append('INTRADAY_SL_TOUCH')

    root = 'NORMAL_SL_AFTER_VALID_ENTRY'
    priority = ['ZONE_CLOSED_BELOW_BEFORE_ENTRY', 'ENTRY_TOO_FAR_FROM_OB_LOW', 'ENTRY_ABOVE_ZONE_HIGH', 'GAP_THROUGH_SL', 'OB_ZONE_NOT_BEARISH_CANDLE', 'SL_NOT_BELOW_ZONE_LOW', 'INTRADAY_SL_TOUCH']
    for p in priority:
        if p in issues:
            root = p
            break

    return {
        'symbol': symbol,
        'entry_date': t.get('entry_date'),
        'exit_date': t.get('exit_date'),
        'zone_type': t.get('zone_type'),
        'conf_type': t.get('conf_type'),
        'family': t.get('v59_setup_family'),
        'pnl_pct': f(t.get('pnl_pct')),
        'realized_r': f(t.get('realized_r')),
        'exit_reason': t.get('exit_reason'),
        'idx': {'source': i(t.get('source_event_idx')), 'zone': zi, 'retrace': ri, 'confirm': ci, 'entry': ei, 'exit': xi},
        'prices': {'entry': entry, 'sl': sl, 'zone_low': zone_low, 'zone_high': zone_high},
        'issues': issues,
        'root_cause': root,
        'evidence': evidence,
    }


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    trades = load(TRADES, [])
    ob_losses = [t for t in trades if t.get('zone_type') == 'OB_Bull' and f(t.get('pnl_pct')) <= 0]
    rows = [replay_trade(t) for t in ob_losses]
    root_counts = Counter(r.get('root_cause') or r.get('fatal') for r in rows)
    by_conf = defaultdict(lambda: {'n': 0, 'avg_pnl': 0.0, 'roots': Counter()})
    for r in rows:
        key = r.get('conf_type') or 'UNKNOWN'
        by_conf[key]['n'] += 1
        by_conf[key]['avg_pnl'] += f(r.get('pnl_pct'))
        by_conf[key]['roots'][r.get('root_cause') or r.get('fatal')] += 1
    by_conf_out = {k: {'n': v['n'], 'avg_pnl': round(v['avg_pnl'] / v['n'], 3) if v['n'] else 0, 'roots': dict(v['roots'])} for k, v in by_conf.items()}
    summary = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'trade_file': str(TRADES),
        'ob_loss_count': len(rows),
        'root_counts': dict(root_counts),
        'by_conf': by_conf_out,
        'pass': len(rows) > 0,
    }
    OUT_JSON.write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=2))
    md = ['# V66 OB Loss Bucket Audit\n\n', '```json\n', json.dumps(summary, ensure_ascii=False, indent=2), '\n```\n\n']
    for r in rows:
        md.append(f"- {r.get('symbol')} {r.get('entry_date')} {r.get('conf_type')} pnl={r.get('pnl_pct')} root={r.get('root_cause')} issues={','.join(r.get('issues') or [])}\n")
    OUT_MD.write_text(''.join(md))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
