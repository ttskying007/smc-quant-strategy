#!/usr/bin/env python3
"""V78 full-candidate lifecycle audit.

Runs the explicit SMC lifecycle decomposition over the full V71/V73 candidate
layer (9,931 trades), not the V74 850-trade subset:
1) trend regime,
2) lifecycle event,
3) POI location,
4) entry location,
5) exit semantics.

This is diagnostic first: it measures which combinations actually track smart
money before any production promotion.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from v74_environment_state_machine import add_env_slopes, classify_market_env
from v78_smc_lifecycle_state_machine import (
    classify_exit_semantics,
    classify_trend_regime,
    detect_smc_lifecycle_event,
    evaluate_entry_location,
    f,
    locate_demand_poi,
)

ROOT = Path('/root/.hermes')
KLINE_DIR = ROOT / 'kline_cache'
V73_DIR = ROOT / 'smc_opt_v73_structural_env'
OUT_DIR = ROOT / 'smc_opt_v78_full_lifecycle_audit'
OUT_DIR.mkdir(parents=True, exist_ok=True)


def sym_to_cache(symbol: str) -> Path:
    code, ex = symbol.split('.')
    return KLINE_DIR / f'{code}_{ex}_daily_300.json'


def load_klines(symbol: str) -> List[Dict[str, Any]]:
    p = sym_to_cache(symbol)
    if not p.exists():
        p = Path(str(p).replace('_daily_300.json', '_daily_750.json'))
    if not p.exists():
        return []
    rows = json.loads(p.read_text())
    return rows if isinstance(rows, list) else []


def date_of(bar: Dict[str, Any]) -> str:
    return str(bar.get('t') or bar.get('date') or '')[:8]


def find_idx_by_date(ks: List[Dict[str, Any]], date: str) -> int:
    d = str(date or '')[:8]
    for i, b in enumerate(ks):
        if date_of(b) == d:
            return i
    return -1


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    xs = list(rows)
    if not xs:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'sl_rate': 0, 'cum': 0, 'avg_win': 0, 'avg_loss': 0, 'payoff': 0}
    wins = [r for r in xs if f(r.get('pnl_pct')) > 0]
    losses = [r for r in xs if f(r.get('pnl_pct')) <= 0]
    sl = [r for r in xs if r.get('exit_reason') == 'SL_HIT']
    avg_win = sum(f(r.get('pnl_pct')) for r in wins) / len(wins) if wins else 0
    avg_loss = sum(f(r.get('pnl_pct')) for r in losses) / len(losses) if losses else 0
    return {
        'n': len(xs),
        'wr': round(len(wins) / len(xs) * 100, 2),
        'avg_pnl': round(sum(f(r.get('pnl_pct')) for r in xs) / len(xs), 4),
        'sl_rate': round(len(sl) / len(xs) * 100, 2),
        'cum': round(sum(f(r.get('pnl_pct')) for r in xs), 2),
        'avg_win': round(avg_win, 4),
        'avg_loss': round(avg_loss, 4),
        'payoff': round(avg_win / abs(avg_loss), 3) if avg_loss else 0,
    }


def bucket(rows: Iterable[Dict[str, Any]], key) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(groups.items())}


def prior_env_window(env: Dict[str, Dict[str, Any]], entry_date: str, n: int = 10) -> List[str]:
    dates = sorted(env)
    d = str(entry_date or '')[:8]
    try:
        idx = dates.index(d)
    except ValueError:
        return []
    return [env[dt].get('market_state_v74') or classify_market_env(env[dt]) for dt in dates[max(0, idx - n):idx]]


def annotate_trade(trade: Dict[str, Any], env: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(trade)
    symbol = str(trade.get('symbol') or '')
    ks = load_klines(symbol)
    entry_idx = int(trade.get('entry_idx') or -1)
    confirm_idx = int(trade.get('confirm_bar') or -1)
    if not ks or entry_idx < 0:
        out.update({'lifecycle_audit_status': 'MISSING_KLINE_OR_ENTRY'})
        return out
    if entry_idx >= len(ks):
        fixed = find_idx_by_date(ks, str(trade.get('entry_date') or ''))
        entry_idx = fixed if fixed >= 0 else entry_idx
    if entry_idx < 0 or entry_idx >= len(ks):
        out.update({'lifecycle_audit_status': 'ENTRY_INDEX_OUT_OF_RANGE'})
        return out
    if confirm_idx < 0 or confirm_idx >= len(ks):
        confirm_idx = find_idx_by_date(ks, str(trade.get('confirm_date') or ''))
    if confirm_idx < 0 or confirm_idx >= len(ks):
        confirm_idx = max(0, entry_idx - 1)

    trend = classify_trend_regime(ks, max(0, confirm_idx - 1))
    event = detect_smc_lifecycle_event(ks, confirm_idx, trend)
    poi = locate_demand_poi(ks, event)
    entry = evaluate_entry_location(ks, poi, int(event.get('event_idx') or confirm_idx) + 1, entry_idx)
    exit_sem = classify_exit_semantics(ks, poi, entry_idx + 1, int(trade.get('exit_idx') or len(ks) - 1)) if poi.get('valid') else {'exit_signal': 'NO_VALID_POI'}

    entry_date = str(trade.get('entry_date') or '')[:8]
    er = env.get(entry_date, {})
    prior10 = prior_env_window(env, entry_date, 10)
    prior5 = prior10[-5:]
    demand_states = {'ACCUMULATION', 'RECOVERY', 'BULL_CONTINUATION'}

    out.update({
        'lc_trend_regime': trend.get('regime'),
        'lc_trend_reason': trend.get('reason'),
        'lc_event_type': event.get('event_type'),
        'lc_event_idx': event.get('event_idx'),
        'lc_poi_type': poi.get('poi_type'),
        'lc_poi_zone_low': poi.get('zone_low'),
        'lc_poi_zone_high': poi.get('zone_high'),
        'lc_poi_zone_idx': poi.get('zone_idx'),
        'lc_entry_valid': entry.get('entry_valid'),
        'lc_entry_type': entry.get('entry_type'),
        'lc_entry_story': entry.get('entry_story'),
        'lc_zone_broken_before_entry': entry.get('zone_broken_before_entry'),
        'lc_exit_signal': exit_sem.get('exit_signal'),
        'lc_exit_idx': exit_sem.get('exit_idx'),
        'market_state_v74': er.get('market_state_v74', trade.get('market_state_v74')),
        'lc_prior5_distribution_days': sum(1 for x in prior5 if x == 'DISTRIBUTION'),
        'lc_prior10_distribution_days': sum(1 for x in prior10 if x == 'DISTRIBUTION'),
        'lc_prior10_demand_days': sum(1 for x in prior10 if x in demand_states),
        'lc_bull_breadth': f(er.get('bull_breadth', trade.get('market_bull_breadth'))),
        'lifecycle_audit_status': 'OK',
    })

    out['lc_core_valid'] = bool(
        entry.get('entry_valid')
        and out['market_state_v74'] in demand_states
        and out['lc_prior5_distribution_days'] == 0
        and out['lc_prior10_distribution_days'] <= 3
        and out['lc_prior10_demand_days'] >= 3
        and f(out.get('risk_pct')) <= 5.5
        and f(out.get('lc_bull_breadth')) <= 0.50
        and exit_sem.get('exit_signal') not in {'EXIT_POI_CLOSE_BREAK', 'EXIT_TREND_HL_BREAK'}
    )
    return out


def main() -> None:
    trades = json.loads((V73_DIR / 'v73_annotated_trades.json').read_text())
    env = add_env_slopes(json.loads((V73_DIR / 'v73_env_by_date.json').read_text()))
    annotated: List[Dict[str, Any]] = []
    for i, t in enumerate(trades, 1):
        annotated.append(annotate_trade(t, env))
        if i % 1000 == 0:
            print(f'annotated {i}/{len(trades)}')

    ok = [r for r in annotated if r.get('lifecycle_audit_status') == 'OK']
    selected = [r for r in ok if r.get('lc_core_valid')]
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V78_FULL_CANDIDATE_LIFECYCLE_AUDIT',
        'input': {'full_candidate_trades': len(trades), 'ok': len(ok), 'selected': len(selected)},
        'base': metrics(ok),
        'lc_core_valid': metrics(selected),
        'buckets': {
            'base_year': bucket(ok, lambda r: str(r.get('entry_date', ''))[:4]),
            'selected_year': bucket(selected, lambda r: str(r.get('entry_date', ''))[:4]),
            'trend_regime': bucket(ok, lambda r: r.get('lc_trend_regime')),
            'event_type': bucket(ok, lambda r: r.get('lc_event_type')),
            'entry_story': bucket(ok, lambda r: r.get('lc_entry_story')),
            'entry_valid': bucket(ok, lambda r: r.get('lc_entry_valid')),
            'exit_signal': bucket(ok, lambda r: r.get('lc_exit_signal')),
            'selected_story': bucket(selected, lambda r: r.get('lc_entry_story')),
            'selected_exit_signal': bucket(selected, lambda r: r.get('lc_exit_signal')),
            'selected_market_state': bucket(selected, lambda r: r.get('market_state_v74')),
        },
        'reject_counts': dict(Counter(
            'PASS' if r.get('lc_core_valid') else '+'.join(x for x in [
                'BAD_ENTRY' if not r.get('lc_entry_valid') else '',
                'BAD_ENV' if r.get('market_state_v74') not in {'ACCUMULATION', 'RECOVERY', 'BULL_CONTINUATION'} else '',
                'PRIOR5_DIST' if f(r.get('lc_prior5_distribution_days')) > 0 else '',
                'PRIOR10_DIST' if f(r.get('lc_prior10_distribution_days')) > 3 else '',
                'NO_DEMAND_HISTORY' if f(r.get('lc_prior10_demand_days')) < 3 else '',
                'RISK_WIDE' if f(r.get('risk_pct')) > 5.5 else '',
                'BREADTH_HIGH' if f(r.get('lc_bull_breadth')) > 0.50 else '',
                'POI_CLOSE_BREAK' if r.get('lc_exit_signal') == 'EXIT_POI_CLOSE_BREAK' else '',
                'TREND_HL_BREAK' if r.get('lc_exit_signal') == 'EXIT_TREND_HL_BREAK' else '',
            ] if x) or 'OTHER'
            for r in ok
        )),
        'files': {
            'annotated': str(OUT_DIR / 'v78_full_lifecycle_annotated.json'),
            'selected': str(OUT_DIR / 'v78_full_lifecycle_selected.json'),
            'report': str(OUT_DIR / 'v78_full_lifecycle_report.json'),
            'markdown': str(OUT_DIR / 'v78_full_lifecycle_report.md'),
        },
    }
    (OUT_DIR / 'v78_full_lifecycle_annotated.json').write_text(json.dumps(annotated, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v78_full_lifecycle_selected.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v78_full_lifecycle_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    md = [
        '# V78 全量候选生命周期审计', '',
        '## 核心结果', '',
        '|层级|笔数|WR|均盈亏|SL率|累计|',
        '|---|---:|---:|---:|---:|---:|',
        f"|V71/V73全量候选|{report['base']['n']}|{report['base']['wr']}%|{report['base']['avg_pnl']}%|{report['base']['sl_rate']}%|{report['base']['cum']}|",
        f"|生命周期核心有效|{report['lc_core_valid']['n']}|{report['lc_core_valid']['wr']}%|{report['lc_core_valid']['avg_pnl']}%|{report['lc_core_valid']['sl_rate']}%|{report['lc_core_valid']['cum']}|",
        '', '## 生命周期核心有效-分年', '',
        '|年份|笔数|WR|均盈亏|SL率|累计|', '|---|---:|---:|---:|---:|---:|',
    ]
    for y, m in report['buckets']['selected_year'].items():
        md.append(f"|{y}|{m['n']}|{m['wr']}%|{m['avg_pnl']}%|{m['sl_rate']}%|{m['cum']}|")
    md += ['', '## 结论', '', '这是全量候选层的生命周期审计，不是V74子集筛选。若分年覆盖或稳定性不足，下一步修生命周期状态机，而不是继续调TP/SL。']
    (OUT_DIR / 'v78_full_lifecycle_report.md').write_text('\n'.join(md))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
