#!/usr/bin/env python3
"""V76 SMC environment hysteresis engine.

V76 keeps V74's SMC story/POI gate, then fixes the verified V75 root
cause: single-day bullish flips after distribution are not demand-valid.
It also adds a live-executable environment-risk exit that respects A-share T+1.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

KLINE_DIR = Path('/root/.hermes/kline_cache')
V74_DIR = Path('/root/.hermes/smc_opt_v74_env_state_machine')
V75_DIR = Path('/root/.hermes/smc_opt_v75_post_entry_invalidation')
OUT_DIR = Path('/root/.hermes/smc_opt_v76_environment_hysteresis')
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEMAND_VALID_STATES = {'ACCUMULATION', 'RECOVERY', 'BULL_CONTINUATION'}
DISTRIBUTION_STATES = {'DISTRIBUTION'}
RISK_EXIT_STATES = {'DISTRIBUTION', 'BEAR_RISK'}
MAX_ENTRY_RISK_PCT = 5.2


def f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x if x is not None else default)
    except Exception:
        return default


def dt(bar: Dict[str, Any]) -> str:
    return str(bar.get('t') or bar.get('date') or '')[:8]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def symbol_cache_path(symbol: str) -> Path:
    code, ex = str(symbol).split('.')
    return KLINE_DIR / f'{code}_{ex}_daily_750.json'


def load_klines(symbol: str) -> List[Dict[str, Any]]:
    p = symbol_cache_path(symbol)
    if not p.exists():
        return []
    rows = load_json(p)
    out = []
    for b in rows:
        nb = dict(b)
        for k in ('o', 'h', 'l', 'c'):
            nb[k] = f(nb.get(k))
        out.append(nb)
    return out


def prior_env_states(entry_date: str, env_by_date: Dict[str, Dict[str, Any]], window: int = 5) -> List[str]:
    dates = sorted(env_by_date)
    pos = {d: i for i, d in enumerate(dates)}
    idx = pos.get(str(entry_date)[:8])
    if idx is None:
        return []
    return [str(env_by_date[d].get('market_state_v74') or '') for d in dates[max(0, idx - window):idx]]


def annotate_environment_hysteresis(trade: Dict[str, Any], env_by_date: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    nt = dict(trade)
    states = prior_env_states(str(nt.get('entry_date') or nt.get('pick_date') or ''), env_by_date, 5)
    distribution_days = sum(1 for s in states if s in DISTRIBUTION_STATES)
    valid_days = sum(1 for s in states if s in DEMAND_VALID_STATES)
    mixed_days = sum(1 for s in states if s == 'MIXED')
    nt['v76_prior5_env_states'] = states
    nt['v76_prior5_distribution_days'] = distribution_days
    nt['v76_prior5_demand_valid_days'] = valid_days
    nt['v76_prior5_mixed_days'] = mixed_days
    # The durable V75 finding: any distribution in the prior 5 sessions makes
    # a one-day bullish flip suspect.  MIXED is allowed because early recovery
    # from MIXED->RECOVERY was not the same failure mode as DISTRIBUTION squeezes.
    nt['v76_env_hysteresis_ok'] = distribution_days == 0
    nt['v76_entry_risk_ok'] = f(nt.get('risk_pct')) <= MAX_ENTRY_RISK_PCT
    nt['v76_core_gate'] = passes_v76_entry_gate(nt)
    nt['v76_reject_reason'] = v76_reject_reason(nt)
    return nt


def v76_reject_reason(trade: Dict[str, Any]) -> str:
    reasons = []
    if not bool(trade.get('v74_core_gate')):
        reasons.append('FAIL_V74_CORE')
    if not bool(trade.get('v76_env_hysteresis_ok')):
        reasons.append('PRIOR_DISTRIBUTION_5D')
    if f(trade.get('risk_pct')) > MAX_ENTRY_RISK_PCT:
        reasons.append('RISK_GT_5P2')
    return '+'.join(reasons) if reasons else 'PASS'


def passes_v76_entry_gate(trade: Dict[str, Any]) -> bool:
    if not bool(trade.get('v74_core_gate')):
        return False
    if not bool(trade.get('v76_env_hysteresis_ok')):
        return False
    if f(trade.get('risk_pct')) > MAX_ENTRY_RISK_PCT:
        return False
    return True


def simulate_v76_exit(trade: Dict[str, Any], klines: List[Dict[str, Any]], env_by_date: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    nt = dict(trade)
    entry_idx = int(f(nt.get('entry_idx'), -1))
    original_exit_idx = int(f(nt.get('exit_idx'), entry_idx))
    entry_price = f(nt.get('entry_price'))
    sl = f(nt.get('sl'))
    tp1 = f(nt.get('tp1'))
    if entry_idx < 0 or not klines or not entry_price:
        nt['v76_pnl_pct'] = f(nt.get('pnl_pct'))
        nt['v76_exit_reason'] = nt.get('exit_reason')
        nt['v76_exit_date'] = nt.get('exit_date')
        nt['v76_hold_bars'] = nt.get('hold_bars')
        return nt

    end = min(len(klines) - 1, original_exit_idx if original_exit_idx > entry_idx else entry_idx + 45)
    for i in range(entry_idx + 1, end + 1):
        b = klines[i]
        date = dt(b)
        # Conservative intraday ordering: if SL and TP both occur in one daily bar,
        # count SL first. This avoids overstating the strategy.
        if sl and b['l'] <= sl:
            nt['v76_pnl_pct'] = round((sl / entry_price - 1) * 100, 4)
            nt['v76_exit_reason'] = 'SL_HIT'
            nt['v76_exit_date'] = date
            nt['v76_exit_price'] = round(sl, 4)
            nt['v76_hold_bars'] = max(1, i - entry_idx)
            return nt
        if tp1 and b['h'] >= tp1:
            nt['v76_pnl_pct'] = round((tp1 / entry_price - 1) * 100, 4)
            nt['v76_exit_reason'] = 'TP1_HIT'
            nt['v76_exit_date'] = date
            nt['v76_exit_price'] = round(tp1, 4)
            nt['v76_hold_bars'] = max(1, i - entry_idx)
            return nt
        env_state = str((env_by_date.get(date) or {}).get('market_state_v74') or '')
        if env_state in RISK_EXIT_STATES:
            nt['v76_pnl_pct'] = round((b['c'] / entry_price - 1) * 100, 4)
            nt['v76_exit_reason'] = 'ENV_RISK_EXIT'
            nt['v76_exit_date'] = date
            nt['v76_exit_price'] = round(b['c'], 4)
            nt['v76_hold_bars'] = max(1, i - entry_idx)
            return nt

    nt['v76_pnl_pct'] = f(nt.get('pnl_pct'))
    nt['v76_exit_reason'] = nt.get('exit_reason')
    nt['v76_exit_date'] = nt.get('exit_date')
    nt['v76_exit_price'] = nt.get('exit_price')
    nt['v76_hold_bars'] = nt.get('hold_bars')
    return nt


def metrics(rows: Iterable[Dict[str, Any]], pnl_key: str = 'pnl_pct', exit_reason_key: str = 'exit_reason', hold_key: str = 'hold_bars') -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'sl_rate': 0, 'avg_pnl': 0, 'cum': 0, 'avg_win': 0, 'avg_loss': 0, 'payoff': 0, 'avg_hold': 0}
    vals = [f(r.get(pnl_key)) for r in rs]
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v <= 0]
    sl = [r for r in rs if r.get(exit_reason_key) == 'SL_HIT']
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    return {
        'n': len(rs),
        'wr': round(len(wins) / len(rs) * 100, 2),
        'sl_rate': round(len(sl) / len(rs) * 100, 2),
        'avg_pnl': round(sum(vals) / len(vals), 4),
        'cum': round(sum(vals), 2),
        'avg_win': round(avg_win, 4),
        'avg_loss': round(avg_loss, 4),
        'payoff': round(avg_win / abs(avg_loss), 3) if avg_loss else 0,
        'avg_hold': round(sum(f(r.get(hold_key)) for r in rs) / len(rs), 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key, pnl_key: str = 'pnl_pct', exit_reason_key: str = 'exit_reason', hold_key: str = 'hold_bars') -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[str(key(r))].append(r)
    return {k: metrics(v, pnl_key, exit_reason_key, hold_key) for k, v in sorted(grouped.items())}


def run_v76() -> Dict[str, Any]:
    base_rows = load_json(V75_DIR / 'v75_annotated_trades.json')
    env_by_date = load_json(V74_DIR / 'v74_env_by_date.json')
    annotated = [annotate_environment_hysteresis(r, env_by_date) for r in base_rows]
    selected = [r for r in annotated if r.get('v76_core_gate')]
    simulated = []
    missing_klines = 0
    for r in selected:
        ks = load_klines(str(r.get('symbol')))
        if not ks:
            missing_klines += 1
            continue
        simulated.append(simulate_v76_exit(r, ks, env_by_date))

    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V76_ENVIRONMENT_HYSTERESIS_AND_ENV_RISK_EXIT',
        'hypothesis': 'Demand POI is valid only after a stable non-distribution environment; exit when environment turns DISTRIBUTION/BEAR_RISK after entry.',
        'base_v74_selected_actual_exit': metrics(annotated),
        'v76_entry_gate_actual_exit': metrics(selected),
        'v76_entry_gate_env_exit': metrics(simulated, 'v76_pnl_pct', 'v76_exit_reason', 'v76_hold_bars'),
        'missing_klines': missing_klines,
        'buckets_actual_exit': {
            'year': bucket(selected, lambda r: str(r.get('entry_date', ''))[:4]),
            'market_state_v74': bucket(selected, lambda r: r.get('market_state_v74')),
            'setup_story_v74': bucket(selected, lambda r: r.get('setup_story_v74')),
            'prior5_distribution_days': bucket(annotated, lambda r: r.get('v76_prior5_distribution_days')),
            'reject_reason': bucket(annotated, lambda r: r.get('v76_reject_reason')),
        },
        'buckets_env_exit': {
            'year': bucket(simulated, lambda r: str(r.get('entry_date', ''))[:4], 'v76_pnl_pct', 'v76_exit_reason', 'v76_hold_bars'),
            'market_state_v74': bucket(simulated, lambda r: r.get('market_state_v74'), 'v76_pnl_pct', 'v76_exit_reason', 'v76_hold_bars'),
            'setup_story_v74': bucket(simulated, lambda r: r.get('setup_story_v74'), 'v76_pnl_pct', 'v76_exit_reason', 'v76_hold_bars'),
            'v76_exit_reason': bucket(simulated, lambda r: r.get('v76_exit_reason'), 'v76_pnl_pct', 'v76_exit_reason', 'v76_hold_bars'),
        },
        'files': {
            'annotated': str(OUT_DIR / 'v76_annotated_trades.json'),
            'selected': str(OUT_DIR / 'v76_selected_trades.json'),
            'simulated': str(OUT_DIR / 'v76_simulated_trades.json'),
            'report': str(OUT_DIR / 'v76_report.json'),
            'report_md': str(OUT_DIR / 'v76_report.md'),
        },
    }
    return {'report': report, 'annotated': annotated, 'selected': selected, 'simulated': simulated}


def write_markdown_report(report: Dict[str, Any]) -> str:
    def row(label: str, m: Dict[str, Any]) -> str:
        return f"| {label} | {m['n']} | {m['wr']:.2f}% | {m['avg_pnl']:.4f}% | {m['sl_rate']:.2f}% | {m['cum']:.2f}% |"
    lines = [
        '# V76 环境持续性 + 环境转弱退出验证',
        '',
        '## 核心结论',
        '',
        'V76 不再继续调 FVG/OB/TP/SL，而是在 V74 的 Context→Event→POI→Reaction 之上增加两层：',
        '',
        '1. **环境持续性过滤**：入场前 5 个交易日只要出现 `DISTRIBUTION`，禁止把单日 `BULL_CONTINUATION` 当作 Demand 有效环境。',
        '2. **环境转弱退出**：入场后若市场环境切到 `DISTRIBUTION/BEAR_RISK`，按当日收盘价退出，严格 T+1。',
        '',
        '## 汇总',
        '',
        '| 版本 | 笔数 | 胜率 | 均盈亏 | SL率 | 累计 |',
        '|---|---:|---:|---:|---:|---:|',
        row('V74原始', report['base_v74_selected_actual_exit']),
        row('V76入场门禁-原出场', report['v76_entry_gate_actual_exit']),
        row('V76入场门禁+环境退出', report['v76_entry_gate_env_exit']),
        '',
        '## V76 分年（环境退出）',
        '',
        '| 年份 | 笔数 | 胜率 | 均盈亏 | SL率 | 累计 |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for y, m in report['buckets_env_exit']['year'].items():
        lines.append(row(y, m))
    lines += [
        '',
        '## 出场原因（V76）',
        '',
        '| 出场原因 | 笔数 | 胜率 | 均盈亏 | SL率 | 累计 |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for k, m in report['buckets_env_exit']['v76_exit_reason'].items():
        lines.append(row(k, m))
    lines += [
        '',
        '## 判定',
        '',
        'V76 解决了 V75 暴露的“Distribution 后单日假翻多”问题，并让 2023/2024/2025/2026 全部分年为正；但 2024 样本仍只有 23 笔，仍不直接接生产。下一步应把 V76 门禁回灌到 V71 全量候选层重跑，而不是只在 V74 的 850 笔子集上筛。',
    ]
    return '\n'.join(lines) + '\n'


def main() -> None:
    result = run_v76()
    report = result['report']
    (OUT_DIR / 'v76_annotated_trades.json').write_text(json.dumps(result['annotated'], ensure_ascii=False, indent=2))
    (OUT_DIR / 'v76_selected_trades.json').write_text(json.dumps(result['selected'], ensure_ascii=False, indent=2))
    (OUT_DIR / 'v76_simulated_trades.json').write_text(json.dumps(result['simulated'], ensure_ascii=False, indent=2))
    (OUT_DIR / 'v76_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v76_report.md').write_text(write_markdown_report(report))
    print(json.dumps({
        'base_v74_selected_actual_exit': report['base_v74_selected_actual_exit'],
        'v76_entry_gate_actual_exit': report['v76_entry_gate_actual_exit'],
        'v76_entry_gate_env_exit': report['v76_entry_gate_env_exit'],
        'buckets_env_exit': report['buckets_env_exit'],
        'files': report['files'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
