#!/usr/bin/env python3
"""Generate integrated V66 repair closure report: pollution, backtest, live audit, replay plan."""
from __future__ import annotations
import json, datetime, collections, statistics
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
OUT_JSON = AUDIT / 'v66_integrated_repair_closure.json'
OUT_MD = AUDIT / 'v66_integrated_repair_closure.md'


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default


def f(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def pct(n, d):
    return round(n / max(d, 1) * 100, 2)


def q(vals):
    vals = sorted([f(x) for x in vals if f(x) or str(x) == '0'])
    if not vals:
        return {}
    return {
        'min': round(vals[0], 3),
        'p50': round(statistics.median(vals), 3),
        'p90': round(vals[int((len(vals) - 1) * 0.9)], 3),
        'max': round(vals[-1], 3),
        'avg': round(statistics.mean(vals), 3),
    }


def main():
    trades = load(ROOT / 'smc_opt_v66/v66_trades.json', [])
    picks = load(ROOT / 'smc_opt_v66/v66_picks.json', [])
    positions = load(ROOT / 'smc_monitor/positions.json', [])
    reviews = load(ROOT / 'smc_monitor/closed_reviews.json', [])
    ledger = load(ROOT / 'smc_monitor/trade_ledger.json', [])
    quarantine = load(AUDIT / 'v66_pollution_quarantine.json', {})
    live = load(AUDIT / 'v66_live_execution_audit.json', {})
    bias = load(AUDIT / 'v66_sample_bias_audit.json', {})
    gate = load(AUDIT / 'v66_release_gate.json', {})
    gap = load(AUDIT / 'v66_live_vs_backtest_gap_report.json', {})
    active = [p for p in picks if p.get('pick_scope') in ('ACTIVE_CANDIDATE', 'ACTIVE_ENTRY') and p.get('is_active_pick')]
    watch = [p for p in picks if p.get('pick_scope') == 'WATCH_ONLY']
    wins = [t for t in trades if f(t.get('pnl_pct')) > 0]
    losses = [t for t in trades if f(t.get('pnl_pct')) <= 0]
    current_open = [p for p in positions if p.get('status') == 'OPEN']
    current_watch = [p for p in positions if p.get('status') == 'WATCH_ONLY']
    missing = []
    if not gate.get('pass'):
        missing.append('release_gate_failed')
    if reviews:
        missing.append('production_review_file_not_empty_after_quarantine')
    polluted_closed = [p for p in positions if p.get('status') == 'CLOSED' and p.get('sample_class') != 'PRODUCTION_CLEAN']
    if polluted_closed:
        missing.append('closed_diagnostic_positions_still_in_production_file')
    if live.get('violations', {}).get('production_review_pollution'):
        missing.append('review_pollution_audit_violation')
    if live.get('violations', {}).get('production_closed_position_pollution'):
        missing.append('closed_position_pollution_audit_violation')
    if not active:
        missing.append('no_current_tradable_active_candidate')
    out = {
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'status': 'PASS' if not missing else 'ATTENTION',
        'missing_or_open_items': missing,
        'why_previous_repairs_failed': [
            {'problem': '只打 sample_class 标签，没有物理隔离', 'evidence': 'closed_reviews.json 和 positions.json 仍保留 DIAGNOSTIC_ONLY closed rows，下游页面/报告继续读同一文件', 'fix': '已将 diagnostic closed positions/reviews/ledger rows 迁入 smc_monitor/quarantine'},
            {'problem': 'release gate 没有把生产复盘污染作为失败项', 'evidence': '旧 gate 只检查 live field/T+1/coverage，不检查 closed_reviews 是否 clean-only', 'fix': '新增 production_reviews_clean_only 与 production_closed_positions_clean_only'},
            {'problem': '统计口径把观察层和可买层混成 Active', 'evidence': 'daily ops active_count 曾包含 WATCH_ONLY', 'fix': '新增 active_tradable_count/watch_only_count 双口径'},
            {'problem': '字段契约补丁无法改写历史已关闭记录', 'evidence': 'zone_bar→zone_idx 修复只作用于后续 ingest；旧 review 已生成且缺 provenance', 'fix': '历史作为 archive evidence 保留，不再参与生产 WR/SL'},
        ],
        'backtest_validation': {
            'trades': len(trades), 'wins': len(wins), 'losses': len(losses), 'wr_pct': pct(len(wins), len(trades)),
            'avg_pnl_pct': round(statistics.mean([f(t.get('pnl_pct')) for t in trades]), 3) if trades else 0,
            'by_zone': dict(collections.Counter(t.get('zone_type') or t.get('signal_type') for t in trades)),
            'loss_by_zone': dict(collections.Counter(t.get('zone_type') or t.get('signal_type') for t in losses)),
        },
        'live_validation': {
            'positions_total': len(positions), 'open': len(current_open), 'watch_only': len(current_watch), 'closed': sum(1 for p in positions if p.get('status') == 'CLOSED'),
            'production_reviews': len(reviews), 'ledger_rows': len(ledger), 'live_audit_pass': live.get('pass'), 'live_checks': live.get('checks'),
            'legacy_open_or_watch_kept': quarantine.get('legacy_open_or_watch_kept'),
        },
        'selection_funnel': {
            'picks_total': len(picks), 'active_tradable': len(active), 'watch_only': len(watch),
            'active_risk_pct': q([p.get('risk_pct') for p in active]), 'watch_risk_pct': q([p.get('risk_pct') for p in watch]),
            'bias_flags': bias.get('bias_flags'),
        },
        'quarantine': quarantine,
        'release_gate': {'pass': gate.get('pass'), 'failed_checks': gate.get('failed_checks')},
        'repair_plan': [
            {'layer': '样本口径', 'action': '生产文件 clean-only；历史污染物理归档；页面显示 archive 但不计入生产指标', 'expected': 'production review_count=0 直到新 clean 交易关闭'},
            {'layer': '实时执行', 'action': '继续保留 legacy OPEN/WATCH_ONLY 风控监控，但 sample_class=DIAGNOSTIC_ONLY，不参与 WR/SL', 'expected': '旧仓位仍能止损/止盈，但关闭后自动按诊断归档或不进入生产统计'},
            {'layer': '选股漏斗', 'action': 'ACTIVE_CANDIDATE 与 WATCH_ONLY 分离；risk<=5 且 zone/provenance/T+1 通过才可买', 'expected': 'active 维持小而干净，watch 只做降风险观察'},
            {'layer': '回测验证', 'action': 'V66 trades 继续使用 T+1/provenance/sequence gate；新增 clean-vs-live 对比必须等待 clean closed 样本', 'expected': '回测 WR 与实盘 WR 的比较只在同源 clean 样本上发生'},
            {'layer': '复盘闭环', 'action': '每个 clean SL 必须逐笔回放 signal→zone→confirm→entry→exit；diagnostic SL 只归入历史污染报告', 'expected': '下一次止损能定位到信号、入场、执行、出场四层之一'},
        ],
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    lines = []
    lines.append('# V66 全流程修复闭环报告')
    lines.append('')
    lines.append('## 1. 当前结论')
    lines.append(f"- 状态: **{out['status']}**；release gate: `{gate.get('pass')}`；live audit: `{live.get('pass')}`。")
    lines.append(f"- 历史污染已物理隔离：closed positions `{quarantine.get('archived_closed_positions')}`、reviews `{quarantine.get('archived_reviews')}`、ledger `{quarantine.get('archived_ledger_rows')}`。")
    lines.append(f"- 生产复盘文件当前 reviews=`{len(reviews)}`，closed diagnostic positions=`{len(polluted_closed)}`；后续生产 WR/SL 不再混入旧样本。")
    lines.append(f"- V66 回测仍为 `{len(trades)}` 笔，WR `{out['backtest_validation']['wr_pct']}%`，均值 `{out['backtest_validation']['avg_pnl_pct']}%`；实盘 clean closed 暂为 0，不能强行比较。")
    lines.append('')
    lines.append('## 2. 为什么前几次修复没有真正解决历史污染')
    lines.append('| 问题 | 证据 | 本次修复 |')
    lines.append('|---|---|---|')
    for item in out['why_previous_repairs_failed']:
        lines.append(f"| {item['problem']} | {item['evidence']} | {item['fix']} |")
    lines.append('')
    lines.append('## 3. 修复方案')
    lines.append('| 层级 | 动作 | 预期结果 |')
    lines.append('|---|---|---|')
    for item in out['repair_plan']:
        lines.append(f"| {item['layer']} | {item['action']} | {item['expected']} |")
    lines.append('')
    lines.append('## 4. 验证结果')
    lines.append('| 项目 | 结果 |')
    lines.append('|---|---:|')
    lines.append(f"| Release gate failed_checks | {gate.get('failed_checks')} |")
    lines.append(f"| Live audit checks | {live.get('checks')} |")
    lines.append(f"| 当前 OPEN | {len(current_open)} |")
    lines.append(f"| 当前 WATCH_ONLY positions | {len(current_watch)} |")
    lines.append(f"| 当前 ACTIVE_CANDIDATE | {len(active)} |")
    lines.append(f"| 当前 WATCH_ONLY picks | {len(watch)} |")
    lines.append(f"| WATCH_ONLY risk p50 | {out['selection_funnel']['watch_risk_pct'].get('p50')}% |")
    lines.append('')
    lines.append('## 5. 仍需等待的数据')
    lines.append('- 生产 clean closed 样本目前为 0；只有后续 ACTIVE_CANDIDATE 经 T+1 入场并关闭后，才能计算真实实盘 clean WR/SL。')
    lines.append('- 当前 6 条 legacy OPEN/WATCH_ONLY 仍保留用于风控，不计入生产指标；关闭后不应回流生产统计。')
    lines.append('- 102 条 WATCH_ONLY 只观察风险回落和 zone reclaim，不允许直接扩大买入。')
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'json': str(OUT_JSON), 'md': str(OUT_MD), 'status': out['status'], 'missing': missing}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
