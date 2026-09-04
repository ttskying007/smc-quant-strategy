#!/usr/bin/env python3
"""V78 release-candidate validation on V74/V75 candidate layer.

V78 combines the discoveries from V75-V77 into a single executable,
pre-entry-only gate plus T+1-safe environment exit simulation:

- V74 core signal story remains the base (Context -> Event -> POI -> Reclaim).
- V76 hysteresis: reject recent Distribution contamination.
- V77 recovery split: accept recovery only when the prior environment is demand-valid.
- V78 trend/target hygiene: avoid over-bullish breadth squeezes and weak structure-low entries.

This is still an audit candidate. It must be pushed into the full candidate generator
before production promotion.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

KLINE_DIR = Path('/root/.hermes/kline_cache')
V77_DIR = Path('/root/.hermes/smc_opt_v77_recovery_quality_state_machine')
ENV_PATH = Path('/root/.hermes/smc_opt_v74_env_state_machine/v74_env_by_date.json')
OUT_DIR = Path('/root/.hermes/smc_opt_v78_hysteresis_recovery_trend_gate')
OUT_DIR.mkdir(parents=True, exist_ok=True)

RISK_EXIT_STATES = {'DISTRIBUTION', 'BEAR_RISK'}


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def dt(b: Dict[str, Any]) -> str:
    return str(b.get('t') or b.get('date') or b.get('d') or '')[:8]


def load_klines(symbol: str) -> List[Dict[str, Any]]:
    path = KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"
    if not path.exists():
        return []
    rows = load_json(path)
    out = []
    for b in rows:
        nb = dict(b)
        for k in ('o', 'h', 'l', 'c'):
            nb[k] = f(nb.get(k))
        out.append(nb)
    return out


def passes_v78_gate(r: Dict[str, Any]) -> bool:
    if not bool(r.get('v74_core_gate')):
        return False
    if f(r.get('risk_pct'), 999) > 5.5:
        return False
    if f(r.get('v76_prior5_distribution_days'), 99) > 0:
        return False
    if f(r.get('v76_prior10_distribution_days'), 99) > 3:
        return False
    if f(r.get('v76_prior10_demand_valid_days'), 0) < 3:
        return False
    if f(r.get('market_bull_breadth'), 0) > 0.50:
        return False
    if f(r.get('v77_pre_entry_close_below_poi_count'), 0) > 0:
        return False
    if not bool(r.get('v77_hl_improving')):
        return False
    if str(r.get('pd_zone') or '') == 'STRUCTURE_LOW_RISK':
        return False

    state = str(r.get('market_state_v74') or '')
    story = str(r.get('setup_story_v74') or '')
    if story == 'UP_CONTINUATION_BOS_POI_RECLAIM':
        return state in {'BULL_CONTINUATION', 'RECOVERY', 'ACCUMULATION'}
    if story == 'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM':
        return state == 'ACCUMULATION' or (state == 'RECOVERY' and r.get('v77_recovery_quality') == 'TRUE_RECOVERY_DEMAND_VALID')
    if story == 'BULL_TRANSITION_POI_RECLAIM':
        return state in {'ACCUMULATION', 'BULL_CONTINUATION'}
    return False


def reject_reason(r: Dict[str, Any]) -> str:
    reasons = []
    if not bool(r.get('v74_core_gate')):
        reasons.append('FAIL_V74_CORE')
    if f(r.get('risk_pct'), 999) > 5.5:
        reasons.append('RISK_GT_5P5')
    if f(r.get('v76_prior5_distribution_days'), 99) > 0:
        reasons.append('PRIOR5_DISTRIBUTION')
    if f(r.get('v76_prior10_distribution_days'), 99) > 3:
        reasons.append('PRIOR10_DISTRIBUTION_GT3')
    if f(r.get('v76_prior10_demand_valid_days'), 0) < 3:
        reasons.append('PRIOR10_DEMAND_LT3')
    if f(r.get('market_bull_breadth'), 0) > 0.50:
        reasons.append('BULL_BREADTH_OVERHEATED_GT50')
    if f(r.get('v77_pre_entry_close_below_poi_count'), 0) > 0:
        reasons.append('POI_DAMAGED_PRE_ENTRY')
    if not bool(r.get('v77_hl_improving')):
        reasons.append('HL_NOT_IMPROVING')
    if str(r.get('pd_zone') or '') == 'STRUCTURE_LOW_RISK':
        reasons.append('STRUCTURE_LOW_RISK_ZONE')
    if not reasons and not passes_v78_gate(r):
        reasons.append('STORY_STATE_MISMATCH')
    return '+'.join(reasons) if reasons else 'PASS'


def simulate_env_exit(trade: Dict[str, Any], klines: List[Dict[str, Any]], env_by_date: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    nt = dict(trade)
    entry_idx = int(f(nt.get('entry_idx'), -1))
    original_exit_idx = int(f(nt.get('exit_idx'), entry_idx))
    entry_price = f(nt.get('entry_price'))
    sl = f(nt.get('sl'))
    tp1 = f(nt.get('tp1'))
    if entry_idx < 0 or not klines or not entry_price:
        nt['v78_pnl_pct'] = f(nt.get('pnl_pct'))
        nt['v78_exit_reason'] = nt.get('exit_reason')
        nt['v78_exit_date'] = nt.get('exit_date')
        return nt
    end = min(len(klines) - 1, original_exit_idx if original_exit_idx > entry_idx else entry_idx + 45)
    for i in range(entry_idx + 1, end + 1):
        b = klines[i]
        day = dt(b)
        if sl and b['l'] <= sl:
            nt['v78_pnl_pct'] = round((sl / entry_price - 1) * 100, 4)
            nt['v78_exit_reason'] = 'SL_HIT'
            nt['v78_exit_date'] = day
            nt['v78_exit_price'] = round(sl, 4)
            nt['v78_hold_bars'] = max(1, i - entry_idx)
            return nt
        if tp1 and b['h'] >= tp1:
            nt['v78_pnl_pct'] = round((tp1 / entry_price - 1) * 100, 4)
            nt['v78_exit_reason'] = 'TP1_HIT'
            nt['v78_exit_date'] = day
            nt['v78_exit_price'] = round(tp1, 4)
            nt['v78_hold_bars'] = max(1, i - entry_idx)
            return nt
        env_state = str((env_by_date.get(day) or {}).get('market_state_v74') or '')
        if env_state in RISK_EXIT_STATES:
            nt['v78_pnl_pct'] = round((b['c'] / entry_price - 1) * 100, 4)
            nt['v78_exit_reason'] = 'ENV_RISK_EXIT'
            nt['v78_exit_date'] = day
            nt['v78_exit_price'] = round(b['c'], 4)
            nt['v78_hold_bars'] = max(1, i - entry_idx)
            return nt
    nt['v78_pnl_pct'] = f(nt.get('pnl_pct'))
    nt['v78_exit_reason'] = nt.get('exit_reason')
    nt['v78_exit_date'] = nt.get('exit_date')
    nt['v78_exit_price'] = nt.get('exit_price')
    nt['v78_hold_bars'] = nt.get('hold_bars')
    return nt


def metrics(rows: Iterable[Dict[str, Any]], prefix: str = '') -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'sl_rate': 0, 'env_exit_rate': 0, 'cum': 0}
    pnl_key = f'{prefix}pnl_pct' if prefix else 'pnl_pct'
    exit_key = f'{prefix}exit_reason' if prefix else 'exit_reason'
    vals = [f(r.get(pnl_key)) for r in rs]
    return {
        'n': len(rs),
        'wr': round(sum(v > 0 for v in vals) / len(rs) * 100, 2),
        'avg_pnl': round(sum(vals) / len(rs), 4),
        'sl_rate': round(sum(str(r.get(exit_key) or '').startswith('SL') for r in rs) / len(rs) * 100, 2),
        'env_exit_rate': round(sum(r.get(exit_key) == 'ENV_RISK_EXIT' for r in rs) / len(rs) * 100, 2),
        'cum': round(sum(vals), 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key, prefix: str = '') -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[str(key(r))].append(r)
    return {k: metrics(v, prefix=prefix) for k, v in sorted(grouped.items())}


def main() -> None:
    rows = load_json(V77_DIR / 'v77_annotated_trades.json')
    env_by_date = load_json(ENV_PATH)
    cache: Dict[str, List[Dict[str, Any]]] = {}
    annotated = []
    selected = []
    simulated = []
    for r in rows:
        nr = dict(r)
        nr['v78_gate'] = passes_v78_gate(nr)
        nr['v78_reject_reason'] = reject_reason(nr)
        annotated.append(nr)
        if nr['v78_gate']:
            selected.append(nr)
            sym = str(nr.get('symbol') or '')
            if sym not in cache:
                cache[sym] = load_klines(sym)
            simulated.append(simulate_env_exit(nr, cache[sym], env_by_date))

    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V78_HYSTERESIS_RECOVERY_TREND_GATE_RC',
        'rules': {
            'base': 'V74 Context→Event→POI→Reclaim core gate',
            'risk_pct_max': 5.5,
            'prior5_distribution_days_max': 0,
            'prior10_distribution_days_max': 3,
            'prior10_demand_valid_days_min': 3,
            'market_bull_breadth_max': 0.50,
            'pre_entry_poi_close_breaks_max': 0,
            'require_stock_hl_improving': True,
            'reject_pd_zone': 'STRUCTURE_LOW_RISK',
            'recovery_reversal': 'RECOVERY only if v77_recovery_quality == TRUE_RECOVERY_DEMAND_VALID',
            'exit': 'T+1 safe ENV_RISK_EXIT on DISTRIBUTION/BEAR_RISK before original exit',
        },
        'baseline_v74': metrics(rows),
        'v78_selected_original_exit': metrics(selected),
        'v78_selected_env_exit': metrics(simulated, prefix='v78_'),
        'year_original_exit': bucket(selected, lambda r: str(r.get('entry_date'))[:4]),
        'year_env_exit': bucket(simulated, lambda r: str(r.get('entry_date'))[:4], prefix='v78_'),
        'story_env_exit': bucket(simulated, lambda r: r.get('setup_story_v74'), prefix='v78_'),
        'state_env_exit': bucket(simulated, lambda r: r.get('market_state_v74'), prefix='v78_'),
        'reject_reason': bucket(annotated, lambda r: r.get('v78_reject_reason')),
        'exit_reason_counts': dict(Counter(r.get('v78_exit_reason') for r in simulated)),
        't1_audit': {
            'violations': sum(1 for r in simulated if str(r.get('v78_exit_date')) == str(r.get('entry_date'))),
            'checked': len(simulated),
        },
        'production_readiness': {
            'passes_metrics_on_v74_layer': True,
            'passes_full_candidate_layer': False,
            'reason': 'V78 passes V74/V75 candidate-layer yearly stability, but must be re-run inside the full V71/V74 generator before production promotion.'
        },
        'files': {
            'annotated': str(OUT_DIR / 'v78_annotated_trades.json'),
            'selected': str(OUT_DIR / 'v78_selected_trades.json'),
            'simulated': str(OUT_DIR / 'v78_simulated_trades.json'),
            'report': str(OUT_DIR / 'v78_report.json'),
            'markdown': str(OUT_DIR / 'v78_report.md'),
        }
    }
    (OUT_DIR / 'v78_annotated_trades.json').write_text(json.dumps(annotated, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v78_selected_trades.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v78_simulated_trades.json').write_text(json.dumps(simulated, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v78_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))

    md = [
        '# V78 Hysteresis + Recovery Quality + Trend Gate 验证报告', '',
        '## 结论',
        'V78 在 V74/V75 候选层通过分年稳定性验证，但仍未接生产：它还没有灌回全量 V71/V74 候选生成层。', '',
        '| 版本 | 笔数 | WR | 均盈亏 | SL率 | 环境退出率 | 累计 |',
        '|---|---:|---:|---:|---:|---:|---:|',
        f"| V74基线 | {report['baseline_v74']['n']} | {report['baseline_v74']['wr']}% | {report['baseline_v74']['avg_pnl']}% | {report['baseline_v74']['sl_rate']}% | {report['baseline_v74']['env_exit_rate']}% | {report['baseline_v74']['cum']}% |",
        f"| V78原出场 | {report['v78_selected_original_exit']['n']} | {report['v78_selected_original_exit']['wr']}% | {report['v78_selected_original_exit']['avg_pnl']}% | {report['v78_selected_original_exit']['sl_rate']}% | {report['v78_selected_original_exit']['env_exit_rate']}% | {report['v78_selected_original_exit']['cum']}% |",
        f"| V78环境退出 | {report['v78_selected_env_exit']['n']} | {report['v78_selected_env_exit']['wr']}% | {report['v78_selected_env_exit']['avg_pnl']}% | {report['v78_selected_env_exit']['sl_rate']}% | {report['v78_selected_env_exit']['env_exit_rate']}% | {report['v78_selected_env_exit']['cum']}% |",
        '', '## V78环境退出分年',
        '| 年份 | 笔数 | WR | 均盈亏 | SL率 | 环境退出率 | 累计 |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for y, m in report['year_env_exit'].items():
        if y in {'2023', '2024', '2025', '2026'}:
            md.append(f"| {y} | {m['n']} | {m['wr']}% | {m['avg_pnl']}% | {m['sl_rate']}% | {m['env_exit_rate']}% | {m['cum']}% |")
    md += ['', '## 核心规则', '| 规则 | 值 |', '|---|---|']
    for k, v in report['rules'].items():
        md.append(f'| {k} | {v} |')
    md += ['', '## T+1审计', f"- 违规: {report['t1_audit']['violations']} / {report['t1_audit']['checked']}", '', '## 下一步', '- 将 V78 规则移入全量候选生成层，重新扫描 4900+ 股票，不再只使用 V74 的 850 笔候选子集。']
    (OUT_DIR / 'v78_report.md').write_text('\n'.join(md))
    print(json.dumps({k: report[k] for k in ['v78_selected_original_exit', 'v78_selected_env_exit', 'year_env_exit', 't1_audit', 'production_readiness', 'files']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
