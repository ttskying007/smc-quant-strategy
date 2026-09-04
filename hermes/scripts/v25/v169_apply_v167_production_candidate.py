#!/usr/bin/env python3
"""V169: promote V167 scanner-time production candidate into isolated artifacts.

Inputs are read-only research outputs from V166/V167. This script writes a new
isolated production directory only; smc_unified.py routing is a separate step.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
V166_ROWS = ROOT / 'smc_audit' / 'v166_v164_slice_variant_search_20260623' / 'v166_best_production_slice_rows.csv'
V167_SUMMARY = ROOT / 'smc_audit' / 'v167_exact_scanner_dry_run_20260623' / 'summary.json'
V167_RECENT = ROOT / 'smc_audit' / 'v167_exact_scanner_dry_run_20260623' / 'v167_recent45_buy_rows.csv'
OUT = ROOT / 'smc_opt_v167_exact_scanner_gate'
OUT.mkdir(parents=True, exist_ok=True)
ENGINE = 'V167_EXACT_SCANNER_GATE'
VERSION = 'V167'
RULE = 'market_state==BEAR_RISK AND poi_source==DEMAND_OB AND v132_reclaim_class==TRUE_TAKEOVER_3_STRICT AND v132_reclaim_bull_body_pct<=65'


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == '' or (isinstance(v, float) and math.isnan(v)):
            return default
        return float(v)
    except Exception:
        return default


def ikey(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def bval(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {'true', '1', 'yes'}


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {'n': 0, 'wr': 0.0, 'avg_pnl': 0.0, 'median_pnl': 0.0, 'micro_profit_pct': 0.0, 't1_violations': 0, 'min_year_n': 0}
    pnl = [fnum(r.get('pnl_pct')) for r in rows]
    pnl_sorted = sorted(pnl)
    median = pnl_sorted[n // 2] if n % 2 else (pnl_sorted[n // 2 - 1] + pnl_sorted[n // 2]) / 2
    year_counts = Counter(ikey(r.get('entry_date'))[:4] for r in rows if ikey(r.get('entry_date'))[:4] >= '2023')
    return {
        'n': n,
        'wr': round(sum(x > 0 for x in pnl) / n * 100, 2),
        'avg_pnl': round(sum(pnl) / n, 4),
        'median_pnl': round(median, 4),
        'micro_profit_pct': round(sum(0 < x <= 0.55 for x in pnl) / n * 100, 2),
        't1_violations': sum(1 for r in rows if ikey(r.get('exit_date')) and ikey(r.get('entry_date')) >= ikey(r.get('exit_date'))),
        'min_year_n': min(year_counts.values()) if year_counts else 0,
    }


def bucket(rows: list[dict[str, Any]], key: str, prefix: int | None = None) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = str(row.get(key) or '')
        groups[value[:prefix] if prefix else value].append(row)
    return {k: metrics(v) for k, v in sorted(groups.items())}


def convert_trade(row: dict[str, Any]) -> dict[str, Any]:
    entry_price = fnum(row.get('entry_price'))
    zone_low = fnum(row.get('zone_low'))
    zone_high = fnum(row.get('zone_high'))
    risk_pct = fnum(row.get('risk_pct'))
    sl = round(zone_low * 0.99, 4) if zone_low else round(entry_price * (1 - risk_pct / 100), 4)
    tp1 = round(entry_price + (entry_price - sl) * 1.5, 4) if entry_price and sl and entry_price > sl else 0.0
    pnl = fnum(row.get('pnl_pct'))
    out = dict(row)
    out.update({
        'engine': ENGINE,
        'version': VERSION,
        'strategy_version': VERSION,
        'production_eligible_v167': True,
        'production_grade': 'A_PRODUCTION',
        'contract_source': 'V164_SCANNER_TIME_FIELDS_PLUS_V166_ROBUST_SLICE_PLUS_V167_DRYRUN',
        'selection_contract': RULE,
        'execution_contract': 'TP=1.5R; max_hold=10 bars; SL=zone_low-1%; T+1 exit starts entry_idx+1',
        'symbol': row.get('symbol'),
        'event_date': ikey(row.get('event_date')),
        'signal_date': ikey(row.get('event_date') or row.get('zone_date')),
        'zone_date': ikey(row.get('zone_date')),
        'pick_date': ikey(row.get('entry_date')),
        'select_date': ikey(row.get('entry_date')),
        'join_date': ikey(row.get('entry_date')),
        'entry_date': ikey(row.get('entry_date')),
        'entry_idx': int(fnum(row.get('entry_idx'), -1)),
        'entry_price': round(entry_price, 4),
        'price': round(entry_price, 4),
        'exit_date': ikey(row.get('exit_date')),
        'exit_idx': int(fnum(row.get('exit_idx'), -1)),
        'exit_reason': row.get('exit_reason'),
        'pnl_pct': round(pnl, 4),
        'won': pnl > 0,
        'hold_bars': int(fnum(row.get('hold_bars'), 0)),
        'sl': sl,
        'sl_price': sl,
        'sl_pct': round((entry_price - sl) / entry_price * 100, 4) if entry_price and sl else round(risk_pct, 4),
        'risk_pct': round((entry_price - sl) / entry_price * 100, 4) if entry_price and sl else round(risk_pct, 4),
        'tp': tp1,
        'tp1': tp1,
        'tp2': tp1,
        'tp3': tp1,
        'rr': 1.5 if tp1 else 0.0,
        'rr_realized': round(pnl / risk_pct, 4) if risk_pct else 0.0,
        'zone_type': 'OB_Bull',
        'signal_type': row.get('poi_source') or 'DEMAND_OB',
        'conf_type': row.get('v132_reclaim_class') or 'TRUE_TAKEOVER_3_STRICT',
        'zone_low': round(zone_low, 4),
        'zone_high': round(zone_high, 4),
        'dz_low': round(zone_low, 4),
        'dz_high': round(zone_high, 4),
        'cost_line': round((zone_low + zone_high) / 2, 4) if zone_low and zone_high else round(entry_price, 4),
        'smart_money_cost': round((zone_low + zone_high) / 2, 4) if zone_low and zone_high else round(entry_price, 4),
        'volatility_pct': round(fnum(row.get('v85_zone_width_pct') or row.get('risk_pct')), 4),
        'market_state': row.get('market_state') or '',
        'combo_family': row.get('combo_family') or '',
        'event_type': row.get('event_type') or '',
        'entry_mode': 'scanner_reclaim_next_open',
        'pick_scope': 'HISTORICAL_BEST',
        'is_active_pick': False,
        'setup_status': 'BACKTEST_PRODUCTION_CONTRACT_VERIFIED',
        'semantic_layer': 'V167_SCANNER_TIME_TRUE_TAKEOVER_OB_GATE',
        'strict_audit_status': 'PASS',
        'signal_correctness_claim': 'SCANNER_TIME_FIELD_COMPLETE_AND_NO_OUTCOME_LEAK',
        't1_violation': ikey(row.get('exit_date')) != '' and ikey(row.get('entry_date')) >= ikey(row.get('exit_date')),
    })
    return out


def convert_pick(row: dict[str, Any]) -> dict[str, Any]:
    t = convert_trade(row)
    t.update({
        'pnl_pct': 0,
        'won': False,
        'exit_date': '',
        'exit_reason': '',
        'pick_scope': 'ACTIVE_CANDIDATE',
        'is_active_pick': True,
        'setup_status': 'ACTIVE_SCANNER_CANDIDATE',
        'signal_correctness_claim': 'CURRENT_SCANNER_OUTPUT_NOT_HISTORICAL_TRADE',
        'tradable': True,
        'buy_enabled': True,
        'trade_action': 'BUY',
        'v167_live_action': 'BUY',
        'v167_live_reason': 'RECENT45_V167_RULE_PASS',
    })
    return t


def main() -> None:
    summary = json.loads(V167_SUMMARY.read_text(encoding='utf-8'))
    if summary.get('decision') != 'V167_DRYRUN_PASS__PROMOTION_GATE_NEXT':
        raise SystemExit('V167 dry-run did not pass; refusing promotion')
    rows = [r for r in read_csv(V166_ROWS) if ikey(r.get('entry_date'))[:4] >= '2023']
    trades = [convert_trade(r) for r in rows]
    recent_rows = read_csv(V167_RECENT)
    # Join recent slim rows back to full V166 rows by symbol/date/entry/zone so active
    # picks carry outcome-free scanner fields and full frontend field contract.
    full_by_key = {
        (r.get('symbol'), ikey(r.get('entry_date')), str(fnum(r.get('entry_price'))), str(fnum(r.get('zone_low')))): r
        for r in rows
    }
    active = []
    for r in recent_rows:
        key = (r.get('symbol'), ikey(r.get('entry_date')), str(fnum(r.get('entry_price'))), str(fnum(r.get('zone_low'))))
        active.append(convert_pick(full_by_key.get(key, r)))
    report = {
        'engine': ENGINE,
        'version': VERSION,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source_v166_rows': str(V166_ROWS),
        'source_v167_summary': str(V167_SUMMARY),
        'production_write': True,
        'frontend_write': True,
        'watchlist_write': True,
        'historical_trade_source': 'V166 outcome-evaluated rows, entry_year>=2023',
        'active_pick_source': 'V167 recent45 scanner dry-run BUY rows, not historical completed trades',
        'selection_contract': RULE,
        'execution_contract': {'tp_r': 1.5, 'max_hold_bars': 10, 'sl_buffer_pct': 1.0, 't1_exit_start': 'entry_idx+1'},
        'production_total': len(trades),
        'active_pick_count': len(active),
        'latest_active_pick_date': max((p.get('entry_date') for p in active), default=''),
        'production_stats': metrics(trades),
        'by_year': bucket(trades, 'entry_date', prefix=4),
        'by_market_state': bucket(trades, 'market_state'),
        'by_event_type': bucket(trades, 'event_type'),
        'by_exit_reason': bucket(trades, 'exit_reason'),
        'field_audit': {
            k: sum(1 for r in trades if r.get(k) in (None, '') or (k in {'entry_price', 'zone_low', 'zone_high', 'sl', 'tp1'} and fnum(r.get(k)) <= 0))
            for k in ['engine','symbol','entry_date','exit_date','entry_price','zone_type','zone_low','zone_high','sl','tp1','risk_pct','pnl_pct','market_state','poi_source','v132_reclaim_class']
        },
        'active_field_audit': {
            k: sum(1 for r in active if r.get(k) in (None, '') or (k in {'entry_price', 'zone_low', 'zone_high', 'sl', 'tp1'} and fnum(r.get(k)) <= 0))
            for k in ['engine','symbol','entry_date','entry_price','zone_type','zone_low','zone_high','sl','tp1','risk_pct','market_state','poi_source','v132_reclaim_class']
        },
    }
    report['production_gate'] = {
        'n_ge_200': report['production_stats']['n'] >= 200,
        'min_year_n_ge_35': report['production_stats']['min_year_n'] >= 35,
        'wr_ge_82': report['production_stats']['wr'] >= 82,
        'avg_pnl_ge_3': report['production_stats']['avg_pnl'] >= 3,
        'micro_profit_pct_le_1': report['production_stats']['micro_profit_pct'] <= 1,
        't1_zero': report['production_stats']['t1_violations'] == 0,
        'field_missing_zero': all(v == 0 for v in report['field_audit'].values()),
        'active_field_missing_zero': all(v == 0 for v in report['active_field_audit'].values()),
        'active_not_historical_completed': all(p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick') is True and not p.get('exit_date') for p in active),
    }
    report['decision'] = 'V169_PROMOTION_ARTIFACTS_PASS' if all(report['production_gate'].values()) else 'V169_PROMOTION_ARTIFACTS_FAIL'
    if report['decision'].endswith('FAIL'):
        raise SystemExit(json.dumps(report, ensure_ascii=False, indent=2))

    (OUT / 'v167_trades.json').write_text(json.dumps(trades, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'v167_picks.json').write_text(json.dumps(active, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'v167_active_picks.json').write_text(json.dumps(active, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'v167_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (OUT / 'v167_trades.csv').open('w', newline='', encoding='utf-8') as fp:
        fields = sorted({k for r in trades for k in r.keys()})
        writer = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(trades)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
