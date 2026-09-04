#!/usr/bin/env python3
"""V171: repair V167 frontend field contract and live-candidate guard.

- Enrich V167 historical trades and active candidates with V101-style MTF/DNA/combo fields.
- Produce monthly backtest statistics and per-trade replay diagnostics.
- Convert stale/degraded active candidates to WATCH_ONLY when current cached price is
  no longer close to the scanner entry or has already hit TP/SL.
- Writes only inside the isolated V167 production directory, with timestamp backups.
"""
from __future__ import annotations

import csv
import json
import math
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
OUT = ROOT / 'smc_opt_v167_exact_scanner_gate'
KLINE = ROOT / 'kline_cache'
HISTORY = OUT / 'history'
HISTORY.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, str(ROOT / 'scripts' / 'v25'))
from v101_mtf_dna_combo_contract import build_dna, enrich_row  # type: ignore

PRICE_GAP_BUY_PCT = 1.5
VERSION = 'V167'
ENGINE = 'V167_EXACT_SCANNER_GATE'
REQUIRED_CONTRACT_FIELDS = [
    'engine','symbol','pick_date','join_date','zone_type','zone_low','zone_high','cost_line',
    'volatility_pct','signal_type','conf_type','signal_price','dna_preferred_behavior',
    'combo_contract_key','weekly_trend_state','daily_structure_state','m60_state',
]


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == '' or (isinstance(v, float) and math.isnan(v)):
            return default
        return float(v)
    except Exception:
        return default


def dkey(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields and not isinstance(r.get(k), (dict, list)):
                fields.append(k)
    with path.open('w', newline='', encoding='utf-8') as fp:
        w = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)


def backup(path: Path, stamp: str) -> None:
    if path.exists():
        target = HISTORY / f'{path.stem}_{stamp}{path.suffix}'
        if not target.exists():
            shutil.copy2(path, target)


def sym_key(symbol: str) -> str:
    return str(symbol or '').replace('.', '_')


def last_cached_bar(symbol: str) -> dict[str, Any]:
    key = sym_key(symbol)
    for n in (750, 300):
        path = KLINE / f'{key}_daily_{n}.json'
        rows = load_json(path, []) if path.exists() else []
        if isinstance(rows, list) and rows:
            b = rows[-1]
            prev = rows[-2] if len(rows) > 1 else {}
            return {
                'date': dkey(b.get('t') or b.get('date') or b.get('day')),
                'close': fnum(b.get('c')),
                'high': fnum(b.get('h')),
                'low': fnum(b.get('l')),
                'prev_close': fnum(prev.get('c')),
            }
    return {'date': '', 'close': 0.0, 'high': 0.0, 'low': 0.0, 'prev_close': 0.0}


def normalize_core(row: dict[str, Any]) -> dict[str, Any]:
    r = dict(row)
    r['version'] = VERSION
    r['strategy_version'] = VERSION
    r['engine'] = ENGINE
    if not r.get('signal_price'):
        r['signal_price'] = r.get('price') or r.get('entry_price') or r.get('zone_high') or r.get('zone_low')
    if not r.get('select_date'):
        r['select_date'] = dkey(r.get('pick_date') or r.get('entry_date') or r.get('signal_date'))
    if not r.get('pick_date'):
        r['pick_date'] = dkey(r.get('select_date') or r.get('entry_date') or r.get('signal_date'))
    if not r.get('join_date'):
        r['join_date'] = dkey(r.get('entry_date') or r.get('pick_date'))
    if not r.get('zone_type'):
        r['zone_type'] = 'OB_Bull' if r.get('poi_source') == 'DEMAND_OB' else (r.get('signal_type') or 'UNKNOWN')
    if not r.get('signal_type'):
        r['signal_type'] = r.get('poi_source') or r.get('zone_type')
    if not r.get('conf_type'):
        r['conf_type'] = r.get('v132_reclaim_class') or r.get('event_type') or 'UNKNOWN'
    if not r.get('cost_line'):
        zl, zh = fnum(r.get('zone_low')), fnum(r.get('zone_high'))
        r['cost_line'] = round((zl + zh) / 2, 4) if zl and zh else fnum(r.get('entry_price'))
    if not r.get('volatility_pct'):
        r['volatility_pct'] = fnum(r.get('v85_zone_width_pct') or r.get('risk_pct'))
    return r


def enrich_rows(rows: list[dict[str, Any]], dna: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        x = normalize_core(r)
        try:
            x = enrich_row(x, dna)
        except Exception as e:
            x['enrich_error'] = str(e)
        # Flatten critical aliases for frontend contract.
        for prefix, state_key in (('weekly', 'weekly_state'), ('daily', 'daily_state'), ('m60', 'm60_state')):
            state = x.get(state_key) if isinstance(x.get(state_key), dict) else {}
            x[f'{prefix}_trend_state'] = x.get(f'{prefix}_trend_state') or state.get('trend_state') or 'UNKNOWN'
            x[f'{prefix}_structure_state'] = x.get(f'{prefix}_structure_state') or state.get('structure_state') or 'UNKNOWN'
        x['daily_structure_state'] = x.get('daily_structure_state') or x.get('daily_structure_state') or 'UNKNOWN'
        x['m60_state'] = x.get('m60_state') if isinstance(x.get('m60_state'), dict) else {'trend_state': x.get('m60_trend_state') or 'UNKNOWN', 'structure_state': x.get('m60_structure_state') or 'UNKNOWN'}
        x['dna_preferred_behavior'] = x.get('dna_preferred_behavior') or 'UNKNOWN'
        x['combo_contract_key'] = x.get('combo_contract_key') or 'UNKNOWN'
        out.append(x)
    return out


def field_missing(rows: list[dict[str, Any]]) -> dict[str, int]:
    miss = {}
    for k in REQUIRED_CONTRACT_FIELDS:
        c = 0
        for r in rows:
            v = r.get(k)
            if v is None or v == '' or (k in {'zone_low','zone_high','signal_price'} and fnum(v) <= 0):
                c += 1
        miss[k] = c
    return miss


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {'n': 0, 'wr': 0.0, 'avg_pnl': 0.0, 'median_pnl': 0.0, 'tp_rate': 0.0, 'sl_rate': 0.0, 'time_rate': 0.0}
    pnl = [fnum(r.get('pnl_pct')) for r in rows]
    pnl_sorted = sorted(pnl)
    med = pnl_sorted[n//2] if n % 2 else (pnl_sorted[n//2-1] + pnl_sorted[n//2]) / 2
    exits = Counter(str(r.get('exit_reason') or '').upper() for r in rows)
    return {
        'n': n,
        'wr': round(sum(x > 0 for x in pnl) / n * 100, 2),
        'avg_pnl': round(sum(pnl) / n, 4),
        'median_pnl': round(med, 4),
        'total_pnl': round(sum(pnl), 4),
        'avg_hold_bars': round(sum(fnum(r.get('hold_bars')) for r in rows) / n, 2),
        'tp_rate': round(exits.get('TP', 0) / n * 100, 2),
        'sl_rate': round((exits.get('SL', 0) + exits.get('GAP_SL', 0)) / n * 100, 2),
        'time_rate': round(exits.get('TIME', 0) / n * 100, 2),
    }


def monthly_stats(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in trades:
        m = dkey(t.get('entry_date'))[:6]
        if m:
            groups[m].append(t)
    out = []
    for m, rows in sorted(groups.items()):
        out.append({'month': m, **metrics(rows)})
    return out


def replay_rows(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for t in trades:
        entry = fnum(t.get('entry_price'))
        sl = fnum(t.get('sl') or t.get('sl_price'))
        tp = fnum(t.get('tp1') or t.get('tp'))
        risk = (entry - sl) / entry * 100 if entry and sl else fnum(t.get('risk_pct'))
        pnl = fnum(t.get('pnl_pct'))
        issues = []
        if dkey(t.get('entry_date')) >= dkey(t.get('exit_date')) and dkey(t.get('exit_date')):
            issues.append('T1_VIOLATION')
        if risk > 8:
            issues.append('RISK_GT_8')
        if str(t.get('exit_reason')).upper() in {'SL', 'GAP_SL'}:
            issues.append('LOSS_EXIT')
        if str(t.get('exit_reason')).upper() == 'TIME' and pnl > 0:
            issues.append('TIME_PROFIT_EXIT')
        if str(t.get('exit_reason')).upper() == 'TIME' and pnl <= 0:
            issues.append('TIME_LOSS_EXIT')
        rr_realized = pnl / risk if risk else 0
        rows.append({
            'symbol': t.get('symbol'), 'entry_date': dkey(t.get('entry_date')), 'exit_date': dkey(t.get('exit_date')),
            'signal_type': t.get('signal_type'), 'conf_type': t.get('conf_type'), 'event_date': dkey(t.get('event_date')),
            'entry_price': round(entry, 4), 'signal_price': round(fnum(t.get('signal_price')), 4),
            'zone_low': t.get('zone_low'), 'zone_high': t.get('zone_high'), 'sl': round(sl, 4), 'tp1': round(tp, 4),
            'risk_pct': round(risk, 4), 'pnl_pct': round(pnl, 4), 'rr_realized': round(rr_realized, 4),
            'exit_reason': t.get('exit_reason'), 'hold_bars': t.get('hold_bars'),
            'mae_pct': fnum(t.get('mae_pct')), 'mfe_pct': fnum(t.get('mfe_pct')),
            'replay_issue_count': len(issues), 'replay_issues': '|'.join(issues) or 'OK',
            'dna_preferred_behavior': t.get('dna_preferred_behavior'), 'combo_contract_key': t.get('combo_contract_key'),
            'weekly_trend_state': t.get('weekly_trend_state'), 'daily_structure_state': t.get('daily_structure_state'),
            'm60_trend_state': t.get('m60_trend_state'),
        })
    rows.sort(key=lambda r: (r['replay_issue_count'], -abs(r['pnl_pct'])), reverse=True)
    return rows


def guard_active_picks(picks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    guarded = []
    counts = Counter()
    for p in picks:
        x = dict(p)
        bar = last_cached_bar(str(x.get('symbol') or ''))
        entry = fnum(x.get('entry_price') or x.get('price'))
        sl = fnum(x.get('sl') or x.get('sl_price'))
        tp = fnum(x.get('tp1') or x.get('tp'))
        cur = fnum(bar.get('close'))
        gap = (cur - entry) / entry * 100 if cur and entry else 0.0
        status = 'BUY_VALID'
        reason = 'CURRENT_PRICE_WITHIN_ENTRY_GAP_AND_NOT_TP_SL'
        if not cur:
            status, reason = 'WATCH_ONLY_NO_PRICE', 'NO_CACHED_OR_LIVE_PRICE'
        elif sl and cur <= sl:
            status, reason = 'WATCH_ONLY_SL_ALREADY_HIT', 'CURRENT_PRICE_BELOW_OR_EQUAL_SL'
        elif tp and cur >= tp:
            status, reason = 'WATCH_ONLY_TP_ALREADY_HIT', 'CURRENT_PRICE_ABOVE_OR_EQUAL_TP'
        elif abs(gap) > PRICE_GAP_BUY_PCT:
            status = 'WATCH_ONLY_PRICE_NOT_NEAR_ENTRY'
            reason = 'CHASED_UP_TOO_FAR_FROM_ENTRY' if gap > 0 else 'DROPPED_TOO_FAR_FROM_ENTRY'
        x['last_price'] = round(cur, 4)
        x['last_price_date'] = bar.get('date')
        x['live_guard_price_gap_pct'] = round(gap, 4)
        x['live_guard_status'] = status
        x['live_guard_reason'] = reason
        x['live_guard_threshold_pct'] = PRICE_GAP_BUY_PCT
        if status == 'BUY_VALID':
            x['pick_scope'] = 'ACTIVE_CANDIDATE'
            x['is_active_pick'] = True
            x['tradable'] = True
            x['buy_enabled'] = True
            x['trade_action'] = 'BUY'
            x['v167_live_action'] = 'BUY'
        else:
            x['pick_scope'] = 'WATCH_ONLY'
            x['is_active_pick'] = False
            x['tradable'] = False
            x['buy_enabled'] = False
            x['trade_action'] = 'WATCH_ONLY'
            x['v167_live_action'] = 'WATCH_ONLY'
            x['watch_reason'] = reason
        counts[status] += 1
        guarded.append(x)
    return guarded, {
        'threshold_pct': PRICE_GAP_BUY_PCT,
        'counts': dict(counts),
        'buy_valid_count': counts.get('BUY_VALID', 0),
        'watch_only_count': len(guarded) - counts.get('BUY_VALID', 0),
        'latest_price_date': max((str(p.get('last_price_date') or '') for p in guarded), default=''),
    }


def main() -> None:
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    paths = [OUT/'v167_trades.json', OUT/'v167_picks.json', OUT/'v167_active_picks.json', OUT/'v167_report.json']
    for p in paths:
        backup(p, stamp)

    raw_trades = load_json(OUT / 'v167_trades.json', [])
    raw_picks = load_json(OUT / 'v167_active_picks.json', [])
    if not isinstance(raw_trades, list) or not raw_trades:
        raise SystemExit('missing v167_trades.json')
    if not isinstance(raw_picks, list):
        raw_picks = []

    seed = [normalize_core(r) for r in raw_trades]
    dna = build_dna(seed)
    trades = enrich_rows(seed, dna)
    picks_enriched = enrich_rows([normalize_core(r) for r in raw_picks], dna)
    guarded_picks, live_guard = guard_active_picks(picks_enriched)

    months = monthly_stats(trades)
    replay = replay_rows(trades)
    field_audit = field_missing(trades)
    active_field_audit = field_missing(guarded_picks)
    report = load_json(OUT / 'v167_report.json', {}) if (OUT / 'v167_report.json').exists() else {}
    report.update({
        'version': VERSION,
        'engine': ENGINE,
        'v171_contract_repair_generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_total': len(trades),
        'active_pick_count_before_live_guard': len(raw_picks),
        'active_pick_count': live_guard['buy_valid_count'],
        'watch_only_count': live_guard['watch_only_count'],
        'live_guard': live_guard,
        'production_stats': metrics(trades),
        'by_month': {r['month']: {k: v for k, v in r.items() if k != 'month'} for r in months},
        'field_audit': field_audit,
        'active_field_audit': active_field_audit,
        'field_contract_gate': all(v == 0 for v in field_audit.values()) and all(v == 0 for v in active_field_audit.values()),
        'monthly_report_file': str(OUT / 'v167_monthly_stats.csv'),
        'trade_replay_file': str(OUT / 'v167_trade_replay_analysis.csv'),
        'live_guard_file': str(OUT / 'v167_live_guard_report.json'),
    })

    write_json(OUT / 'v167_symbol_dna.json', dna)
    write_json(OUT / 'v167_trades.json', trades)
    write_json(OUT / 'v167_picks.json', guarded_picks)
    write_json(OUT / 'v167_active_picks.json', guarded_picks)
    write_json(OUT / 'v167_report.json', report)
    write_json(OUT / 'v167_monthly_stats.json', months)
    write_csv(OUT / 'v167_monthly_stats.csv', months)
    write_json(OUT / 'v167_trade_replay_analysis.json', replay)
    write_csv(OUT / 'v167_trade_replay_analysis.csv', replay)
    write_json(OUT / 'v167_live_guard_report.json', {'live_guard': live_guard, 'rows': guarded_picks})

    md_lines = [
        '# V167 V171 前端合同 + 实时买入守门报告', '',
        f'- 生成时间: {report["v171_contract_repair_generated_at"]}',
        f'- 历史回测: {len(trades)} 笔, WR={report["production_stats"]["wr"]}%, AvgPnL={report["production_stats"]["avg_pnl"]}%',
        f'- 实时候选: 原始 {len(raw_picks)} -> 可买 {live_guard["buy_valid_count"]} / 观察 {live_guard["watch_only_count"]}',
        f'- 实时价格守门: ±{PRICE_GAP_BUY_PCT}% 入场价，且未触发 SL/TP',
        f'- 字段合同: {"PASS" if report["field_contract_gate"] else "FAIL"}', '',
        '## 实时守门分布', '',
        '|状态|数量|', '|---|---:|',
    ]
    for k, v in sorted(live_guard['counts'].items()):
        md_lines.append(f'|{k}|{v}|')
    md_lines += ['', '## 逐月统计', '', '|月份|笔数|WR|均盈|累计PnL|SL率|TP率|TIME率|', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in months:
        md_lines.append(f"|{r['month']}|{r['n']}|{r['wr']}%|{r['avg_pnl']}%|{r['total_pnl']}%|{r['sl_rate']}%|{r['tp_rate']}%|{r['time_rate']}%|")
    (OUT / 'v167_frontend_contract_live_guard_report.md').write_text('\n'.join(md_lines) + '\n', encoding='utf-8')

    print(json.dumps({
        'decision': 'V171_V167_FRONTEND_CONTRACT_AND_LIVE_GUARD_DONE',
        'field_contract_gate': report['field_contract_gate'],
        'production_total': len(trades),
        'monthly_rows': len(months),
        'replay_rows': len(replay),
        'live_guard': live_guard,
        'field_audit': field_audit,
        'active_field_audit': active_field_audit,
        'report': str(OUT / 'v167_frontend_contract_live_guard_report.md'),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
