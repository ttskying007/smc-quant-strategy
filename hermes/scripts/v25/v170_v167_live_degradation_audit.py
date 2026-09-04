#!/usr/bin/env python3
"""V170: post-promotion live degradation audit for V167 active candidates.

Read-only. Compares V167 active scanner candidates against /api/live-prices output
and buckets current status by scanner-time fields. No production writes.
"""
from __future__ import annotations

import json
import math
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
OUT = ROOT / 'smc_audit' / 'v170_v167_live_degradation_audit_20260623'
OUT.mkdir(parents=True, exist_ok=True)
PICKS = ROOT / 'smc_opt_v167_exact_scanner_gate' / 'v167_active_picks.json'
REPORT = ROOT / 'smc_opt_v167_exact_scanner_gate' / 'v167_report.json'


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == '' or (isinstance(v, float) and math.isnan(v)):
            return default
        return float(v)
    except Exception:
        return default


def dkey(v: Any) -> str:
    return ''.join(ch for ch in str(v or '') if ch.isdigit())[:8]


def bucket_value(row: dict[str, Any], key: str) -> str:
    if key == 'entry_date':
        return dkey(row.get('entry_date'))
    if key == 'risk_band':
        x = fnum(row.get('risk_pct'))
        return '<=4' if x <= 4 else ('4-6' if x <= 6 else ('6-8' if x <= 8 else '>8'))
    if key == 'entry_chase_band':
        x = fnum(row.get('entry_chase_above_zone_pct'))
        return '<=1' if x <= 1 else ('1-2' if x <= 2 else ('2-3' if x <= 3 else '>3'))
    if key == 'body_band':
        x = fnum(row.get('v132_reclaim_bull_body_pct'))
        return '<=45' if x <= 45 else ('45-55' if x <= 55 else ('55-65' if x <= 65 else '>65'))
    return str(row.get(key) or '')


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    statuses = Counter(r.get('status') for r in rows)
    def pct(k: str) -> float:
        return round(statuses.get(k, 0) / n * 100, 2) if n else 0.0
    return {
        'n': n,
        'status_counts': dict(statuses),
        'sl_hit_pct': pct('SL_HIT'),
        'tp_hit_pct': pct('TP_HIT'),
        'holding_pct': pct('HOLDING'),
        'no_live_last_price_pct': pct('NO_LIVE_LAST_PRICE'),
        'avg_live_pnl_pct': round(sum(fnum(r.get('pnlPct')) for r in rows) / n, 4) if n else 0.0,
        'avg_risk_pct': round(sum(fnum(r.get('risk_pct')) for r in rows) / n, 4) if n else 0.0,
        'avg_entry_chase_pct': round(sum(fnum(r.get('entry_chase_above_zone_pct')) for r in rows) / n, 4) if n else 0.0,
    }


def group(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    g: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[bucket_value(r, key)].append(r)
    out = [{'bucket': k, **summarize(v)} for k, v in sorted(g.items())]
    out.sort(key=lambda x: (-x['sl_hit_pct'], -x['n'], str(x['bucket'])))
    return out


def main() -> None:
    picks = json.loads(PICKS.read_text(encoding='utf-8'))
    live = json.loads(urllib.request.urlopen('http://127.0.0.1:8890/api/live-prices', timeout=40).read().decode())
    live_rows = live.get('picks') or []
    by_symbol = {r.get('symbol'): r for r in live_rows}
    merged = []
    for p in picks:
        row = dict(p)
        row.update(by_symbol.get(p.get('symbol'), {}))
        row['status'] = row.get('status') or 'MISSING_LIVE_ROW'
        row['pnlPct'] = fnum(row.get('pnlPct'))
        merged.append(row)

    sl_rows = [r for r in merged if r.get('status') == 'SL_HIT']
    tp_rows = [r for r in merged if r.get('status') == 'TP_HIT']
    summary = {
        'decision': 'V170_LIVE_DEGRADATION_AUDIT_DONE_READ_ONLY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source_report': str(REPORT),
        'active_pick_count': len(picks),
        'live_total': live.get('total'),
        'live_tradable': live.get('tradableLiveCount'),
        'live_watch': live.get('watchContextCount'),
        'live_data_date': live.get('dataDate'),
        'overall': summarize(merged),
        'by_entry_date': group(merged, 'entry_date'),
        'by_risk_band': group(merged, 'risk_band'),
        'by_entry_chase_band': group(merged, 'entry_chase_band'),
        'by_body_band': group(merged, 'body_band'),
        'sl_hit_rows': [
            {k: r.get(k) for k in ['symbol','entry_date','entryPrice','currentPrice','pnlPct','risk_pct','entry_chase_above_zone_pct','v132_reclaim_bull_body_pct','zone_low','zone_high','status','priceStatus']}
            for r in sl_rows
        ],
        'tp_hit_rows': [
            {k: r.get(k) for k in ['symbol','entry_date','entryPrice','currentPrice','pnlPct','risk_pct','entry_chase_above_zone_pct','v132_reclaim_bull_body_pct','zone_low','zone_high','status','priceStatus']}
            for r in tp_rows
        ],
    }
    # Read-only decision: if live SL cluster is high, next research is not TP/SL tuning;
    # it is ex-ante stale/current-price validity gating before monitor ingestion.
    sl_pct = summary['overall']['sl_hit_pct']
    if sl_pct >= 20:
        summary['next_required'] = 'Build V171 scanner-time/current-price guard: reject or WATCH_ONLY rows already below SL/zone at ingestion; bucket by stale age and risk before changing strategy logic.'
        summary['usability_note'] = 'Historical V167 remains production-usable, but live active set needs ingestion-time validity guard before trading all 33 rows.'
    else:
        summary['next_required'] = 'Continue live-forward monitoring; no immediate ingestion guard required.'
        summary['usability_note'] = 'Live active set is not showing concentrated degradation.'
    (OUT / 'live_rows.json').write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'report.md').write_text('# V170 V167 live degradation audit\n\n```json\n' + json.dumps(summary, ensure_ascii=False, indent=2) + '\n```\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
