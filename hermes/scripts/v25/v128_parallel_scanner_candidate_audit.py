#!/usr/bin/env python3
"""V128 parallel scanner candidate shadow audit.

Reads V90 scanner's standalone V128 shadow candidates and runs a full
post-entry semantic backtest for audit only. No production writes.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from v81_contextual_smc_generator import next_exit_semantic
from v90_daily_full_market_scanner import date_key, num

ROOT = Path('/root/.hermes')
SCANNER_OUT = ROOT / 'smc_opt_v90_daily_full_market_scanner'
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_audit' / 'v128_parallel_scanner_candidate_audit_20260620'
OUT.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"


def bar_date(b: Dict[str, Any]) -> str:
    return date_key(b.get('t') or b.get('date'))


def fbar(b: Dict[str, Any], key: str) -> float:
    return num(b.get(key))


def simulate(row: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    entry_idx = int(num(row.get('entry_idx'), -1))
    entry = num(row.get('entry_price'))
    out = dict(row)
    if entry_idx < 0 or entry_idx >= len(ks) or entry <= 0:
        out.update({'valid_backtest': False, 'invalid_reason': 'BAD_ENTRY_IDX_OR_PRICE'})
        return out
    horizon = ks[entry_idx:min(len(ks), entry_idx + 21)]
    poi = {
        'zone_low': row.get('zone_low'),
        'zone_high': row.get('zone_high'),
        'prior_structure_low': row.get('zone_low'),
        'liquidity_target': '',
    }
    if len(horizon) <= 1:
        b = ks[entry_idx]
        exit_idx, exit_date, exit_price, reason = entry_idx, bar_date(b), fbar(b, 'c'), 'NO_T1_EXIT_BAR_AVAILABLE'
    else:
        ex = next_exit_semantic(horizon, poi, 1)
        if ex.get('exit_idx') is None:
            local = len(horizon) - 1
            b = horizon[local]
            exit_idx, exit_date, exit_price, reason = entry_idx + local, bar_date(b), fbar(b, 'c'), 'TIME_STOP_NO_SEMANTIC_EXIT'
        else:
            exit_idx = entry_idx + int(ex.get('exit_idx'))
            exit_date, exit_price, reason = date_key(ex.get('exit_date')), num(ex.get('exit_price')), ex.get('exit_signal')
    if date_key(exit_date) == date_key(row.get('entry_date')) and exit_idx + 1 < len(ks):
        exit_idx += 1
        b = ks[exit_idx]
        exit_date, exit_price, reason = bar_date(b), fbar(b, 'c'), f'{reason}_T1_SHIFTED'
    out.update({
        'exit_idx': exit_idx,
        'exit_date': date_key(exit_date),
        'exit_price': round(exit_price, 6),
        'exit_reason': reason,
        'pnl_pct': round((exit_price / entry - 1) * 100, 4),
        'hold_bars': max(0, exit_idx - entry_idx),
        'valid_backtest': reason != 'NO_T1_EXIT_BAR_AVAILABLE',
        'invalid_reason': 'NO_T1_EXIT_BAR_AVAILABLE' if reason == 'NO_T1_EXIT_BAR_AVAILABLE' else '',
    })
    return out


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rs = list(rows)
    n = len(rs)
    if not n:
        return {'n': 0, 'wr': 0, 'avg': 0, 'loss_rate': 0, 'hard_exit_rate': 0, 'cum': 0}
    vals = [num(r.get('pnl_pct')) for r in rs]
    hard = [r for r in rs if 'BREAK' in str(r.get('exit_reason')) or 'DAMAGE' in str(r.get('exit_reason')) or 'SL' in str(r.get('exit_reason'))]
    return {
        'n': n,
        'wr': round(sum(x > 0 for x in vals) / n * 100, 2),
        'avg': round(sum(vals) / n, 4),
        'loss_rate': round(sum(x <= 0 for x in vals) / n * 100, 2),
        'hard_exit_rate': round(len(hard) / n * 100, 2),
        'cum': round(sum(vals), 4),
    }


def bucket(rows: Iterable[Dict[str, Any]], keyfn) -> Dict[str, Dict[str, Any]]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(keyfn(r))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fields = sorted({k for r in rows for k in r.keys()}) if rows else []
    with path.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        if fields:
            w.writeheader(); w.writerows(rows)


def main() -> None:
    scanner_report = load_json(SCANNER_OUT / 'v90_daily_scan_report.json')
    production_rows = load_json(SCANNER_OUT / 'v90_all_contract_candidates.json')
    production_recent = load_json(SCANNER_OUT / 'v90_active_picks.json')
    shadow_rows = load_json(SCANNER_OUT / 'v128_parallel_shadow_candidates.json')
    shadow_recent = load_json(SCANNER_OUT / 'v128_parallel_shadow_recent45.json')

    tested: List[Dict[str, Any]] = []
    missing_kline = 0
    for r in shadow_rows:
        path = kline_path(str(r.get('symbol')))
        if not path.exists():
            missing_kline += 1
            continue
        tested.append(simulate(r, load_json(path)))
    valid = [r for r in tested if r.get('valid_backtest')]
    invalid = [r for r in tested if not r.get('valid_backtest')]
    recent_valid = [r for r in valid if 0 <= num(r.get('bars_since_entry'), 9999) <= 45]
    v125 = [r for r in valid if r.get('v125_contract_shadow_pass')]
    v125_recent = [r for r in recent_valid if r.get('v125_contract_shadow_pass')]
    t1 = [r for r in valid if date_key(r.get('entry_date')) == date_key(r.get('exit_date'))]
    key_counts = Counter((r.get('symbol'), date_key(r.get('entry_date')), r.get('poi_source')) for r in shadow_rows)
    dup_after_dedupe = sum(1 for c in key_counts.values() if c > 1)
    non_fvg_contract = [r for r in valid if r.get('v125_contract_shadow_pass') and r.get('poi_source') != 'FVG_Demand']

    losses = sorted([r for r in valid if num(r.get('pnl_pct')) <= 0], key=lambda r: num(r.get('pnl_pct')))[:300]
    v125_losses = sorted([r for r in v125 if num(r.get('pnl_pct')) <= 0], key=lambda r: num(r.get('pnl_pct')))

    summary = {
        'decision': 'V128_PARALLEL_SCANNER_SHADOW_DONE_NO_PRODUCTION_DECISION_CHANGE',
        'run_at': datetime.now().isoformat(timespec='seconds'),
        'scanner_report_v128_parallel': scanner_report.get('v128_parallel_shadow'),
        'production_identity': {
            'all_contract_candidates': len(production_rows),
            'recent_picks': len(production_recent),
            'unchanged_expected': True,
        },
        'shadow_rows': len(shadow_rows),
        'shadow_recent45_rows': len(shadow_recent),
        'missing_kline': missing_kline,
        'valid_backtest_rows': len(valid),
        'invalid_rows': len(invalid),
        'invalid_reasons': dict(Counter(str(r.get('invalid_reason')) for r in invalid)),
        'dedupe_key': 'symbol+entry_date+poi_source',
        'duplicate_keys_after_dedupe': dup_after_dedupe,
        't1_violations': len(t1),
        'non_fvg_contract_pass_violations': len(non_fvg_contract),
        'overall': metrics(valid),
        'recent45': metrics(recent_valid),
        'v125_contract': metrics(v125),
        'v125_contract_recent45': metrics(v125_recent),
        'by_source': bucket(valid, lambda r: r.get('poi_source')),
        'by_source_recent45': bucket(recent_valid, lambda r: r.get('poi_source')),
        'by_month': bucket(valid, lambda r: date_key(r.get('entry_date'))[:6]),
        'by_year': bucket(valid, lambda r: date_key(r.get('entry_date'))[:4]),
        'v125_by_month': bucket(v125, lambda r: date_key(r.get('entry_date'))[:6]),
        'v125_by_year': bucket(v125, lambda r: date_key(r.get('entry_date'))[:4]),
        'loss_by_source': bucket([r for r in valid if num(r.get('pnl_pct')) <= 0], lambda r: r.get('poi_source')),
        'loss_by_exit_reason': bucket([r for r in valid if num(r.get('pnl_pct')) <= 0], lambda r: r.get('exit_reason')),
        'top_losses_count': len(losses),
        'v125_losses_count': len(v125_losses),
        'no_hard_reject': True,
        'no_api_frontend_watchlist_write': True,
    }

    write_csv(OUT / 'v128_parallel_shadow_backtest_all.csv', valid)
    write_csv(OUT / 'v128_parallel_shadow_recent45.csv', recent_valid)
    write_csv(OUT / 'v128_v125_contract_pass.csv', v125)
    write_csv(OUT / 'v128_top_losses.csv', losses)
    write_csv(OUT / 'v128_v125_losses.csv', v125_losses)
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = []
    lines.append('# V128 Parallel Scanner Candidate Shadow Audit')
    lines.append('')
    lines.append('Decision: `V128_PARALLEL_SCANNER_SHADOW_DONE_NO_PRODUCTION_DECISION_CHANGE`。只写 shadow 文件，不改生产 picks/API/frontend/watchlist，不 hard reject。')
    lines.append('')
    lines.append('## 1. Scanner shadow 输出')
    v128 = scanner_report.get('v128_parallel_shadow', {})
    lines.append('|检查|结果|')
    lines.append('|---|---:|')
    for k in ['raw_rows_before_dedupe','dedup_rows','recent45_rows','v125_contract_pass_all','v125_contract_pass_recent45','t1_entry_guard_violations']:
        lines.append(f'|{k}|{v128.get(k)}|')
    lines.append('')
    lines.append('## 2. 全量语义回测')
    lines.append('|切片|n|WR|Avg|Loss|HardExit|Cum|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for name, m in [('ALL', summary['overall']), ('recent45', summary['recent45']), ('V125_contract', summary['v125_contract']), ('V125_recent45', summary['v125_contract_recent45'])]:
        lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['cum']}|")
    lines.append('')
    lines.append('## 3. 按 source')
    lines.append('|source|n|WR|Avg|Loss|HardExit|Cum|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for src, m in summary['by_source'].items():
        lines.append(f"|{src}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['cum']}|")
    lines.append('')
    lines.append('## 4. 按年')
    lines.append('|year|n|WR|Avg|Loss|HardExit|Cum|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for y, m in summary['by_year'].items():
        lines.append(f"|{y}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['cum']}|")
    lines.append('')
    lines.append('## 5. V125合同逐月')
    lines.append('|month|n|WR|Avg|Loss|HardExit|Cum|')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for mth, m in summary['v125_by_month'].items():
        lines.append(f"|{mth}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss_rate']}|{m['hard_exit_rate']}|{m['cum']}|")
    lines.append('')
    lines.append('## 6. 结论')
    lines.append(f"1. `DEMAND_OB / FVG_Demand / OB+FVG` 已作为独立 scanner shadow candidate 输出；dedupe={summary['dedupe_key']}，重复键={dup_after_dedupe}。")
    lines.append(f"2. T+1 违规={len(t1)}；V125合同仅 shadow 命中，不 hard reject；recent45 V125命中={len(v125_recent)}。")
    lines.append('3. 逐笔明细、亏损明细、逐月/逐年数据已落盘为CSV。')
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(json.dumps({'out': str(OUT), 'summary': summary}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
