#!/usr/bin/env python3
"""V180: consolidate completed SMC research, define usability gates, and choose next direction.

Read-only consolidation. Writes audit artifacts only.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
OUT = AUD / f"v180_research_direction_closure_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
OUT.mkdir(parents=True, exist_ok=True)

FILES = {
    'V167 production base': AUD / 'v167_exact_scanner_dry_run_20260623' / 'summary.json',
    'V172 high-quality gate': ROOT / 'smc_opt_v172_v167_high_quality_gate' / 'v172_report.json',
    'V173 scalar frontier': AUD / 'v173_v172_next_quality_frontier_20260623' / 'summary.json',
    'V174 semantic audit': AUD / 'v174_v172_wave_structure_hierarchy_20260623' / 'summary.json',
    'V175 semantic split/frontend': AUD / 'v175_frontend_endpoint_smoke_20260623' / 'summary.json',
    'V176 loss frontier': AUD / 'v176_v175_loss_frontier_20260623' / 'summary.json',
    'V177 executable exit replay': sorted(AUD.glob('v177_v175_executable_exit_replay_*/summary.json'))[-1],
    'V178 TIME path attribution': sorted(AUD.glob('v178_v175_time_path_attribution_*/summary.json'))[-1],
    'V179 60min TIME probe': sorted(AUD.glob('v179_v175_time_60min_probe_*/summary.json'))[-1],
}

GATES = {
    'production_upgrade_usable': {
        'n_min': 200,
        'min_year_n_min': 35,
        'wr_min': 84.0,
        'avg_pnl_min': 6.2,
        'all_year_wr_min': 82.0,
        'micro_profit_max': 1.0,
        't1_violations': 0,
        'no_outcome_leak': True,
        'frontend_contract_pass': True,
    },
    'research_overlay_usable': {
        'n_min': 150,
        'min_year_n_min': 25,
        'wr_min': 85.0,
        'avg_pnl_min': 6.0,
        'all_year_wr_min': 83.0,
        'micro_profit_max': 1.0,
        't1_violations': 0,
        'no_outcome_leak': True,
    },
    'unusable': [
        'any T+1 violation',
        'any scanner/active-pick outcome leakage',
        'higher WR produced by cutting AvgPnL or increasing micro/BE pollution',
        'coverage below gate',
        'classical SSL/CHOCH claim not proven by semantic audit',
        '60min-only execution claim with <80% historical coverage',
    ],
}


def load(p: Path) -> dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        return {'_error': str(e), '_path': str(p)}


def pick_metric(d: dict[str, Any], *paths: str, default: Any = None) -> Any:
    for path in paths:
        cur: Any = d
        ok = True
        for part in path.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            return cur
    return default

items = {name: load(path) for name, path in FILES.items()}

completed = []
completed.append({
    'area': '生产基线',
    'status': 'DONE',
    'evidence': 'V175 已完成语义拆分+前端/API冒烟，/api/summary=/api/picks=/api/live-prices/browser smoke 全通过。',
    'artifact': str(FILES['V175 semantic split/frontend']),
})
completed.append({
    'area': '语义真实性',
    'status': 'DONE',
    'evidence': 'V174 证明经典 SSL sweep->CHOCH 只占少数；V175 改名为 DEMAND_OB_TRUE_TAKEOVER_RECLAIM，避免过度声称。',
    'artifact': str(FILES['V174 semantic audit']),
})
completed.append({
    'area': '标量过滤/质量边界',
    'status': 'DONE',
    'evidence': 'V173 找到研究叠加但无生产升级；继续加 scanner-time scalar gate 触及覆盖天花板。',
    'artifact': str(FILES['V173 scalar frontier']),
})
completed.append({
    'area': '亏损归因',
    'status': 'DONE',
    'evidence': 'V176 将剩余亏损分为 SL_DIRECT_ZONE_FAIL、TIME_PARTIAL_FOLLOW_THROUGH_FAIL、TIME_GAVE_BACK_AFTER_NEAR_TP 等，未发现可晋级规则。',
    'artifact': str(FILES['V176 loss frontier']),
})
completed.append({
    'area': '执行层退出',
    'status': 'DONE / BLOCKED',
    'evidence': 'V177 generic BE/partial/trailing 全部降低 AvgPnL 或鲁棒性；V179 60min 覆盖仅 9/65=13.85%，不能做历史生产判断。',
    'artifact': str(FILES['V177 executable exit replay']) + ' ; ' + str(FILES['V179 60min TIME probe']),
})

not_done = [
    {
        'area': '新信号供给层 / 候选生成器重建',
        'why_not_done': 'V173 已证明继续在 V172 上加标量门禁不能形成生产升级；尚未从 V167/V175 之外重建新的非同源结构生成器。',
        'next_test': 'V181: demand takeover 之外的 supply-side expansion：从 V167 全量候选中按结构生命周期重分桶，寻找能补足 n>=200 且 avg>=6.2 的第二子引擎。',
    },
    {
        'area': '历史 60min 可执行退出验证',
        'why_not_done': '腾讯 60min API 只覆盖 2025-12 后，2023-2025 的 TIME 行无数据。',
        'next_test': '除非补齐历史分钟数据，否则不得继续声称 60min exit 改进；可只用于未来 shadow live。',
    },
    {
        'area': '当前 production 与新研究并行 shadow',
        'why_not_done': 'V175 已生产闭环，下一步研究必须隔离，不得污染 /api/picks。',
        'next_test': '所有新候选只写 smc_audit / smc_opt_v181_shadow，不写前端/watchlist。',
    },
]

# Compact status table from actual summaries.
v175_api = items['V175 semantic split/frontend'].get('endpoints', {})
v177_best = items['V177 executable exit replay'].get('best_variant', {})
v178 = items['V178 TIME path attribution']
v179 = items['V179 60min TIME probe']
v173 = items['V173 scalar frontier']

scoreboard = [
    {
        'version': 'V175 production baseline',
        'n': pick_metric(v175_api, '/api/summary.total_trades'),
        'wr': pick_metric(v175_api, '/api/summary.win_rate'),
        'avg': pick_metric(v175_api, '/api/summary.avg_pnl'),
        'decision': 'CURRENT_PRODUCTION_USABLE',
        'reason': 'frontend/API contract pass; no active-pick historical pollution',
    },
    {
        'version': 'V173 best research overlay',
        'n': pick_metric(v173, 'best_research.n'),
        'wr': pick_metric(v173, 'best_research.wr'),
        'avg': pick_metric(v173, 'best_research.avg'),
        'decision': 'RESEARCH_ONLY_USABLE_NOT_PRODUCTION',
        'reason': 'n/min_year below production upgrade; usable only as overlay label',
    },
    {
        'version': 'V177 best exit replay',
        'n': v177_best.get('n'),
        'wr': v177_best.get('wr'),
        'avg': v177_best.get('avg'),
        'decision': items['V177 executable exit replay'].get('decision'),
        'reason': 'best is base replay; all generic exit variants reduce AvgPnL / robustness',
    },
    {
        'version': 'V178 TIME daily attribution',
        'n': v178.get('time_rows'),
        'wr': None,
        'avg': None,
        'decision': v178.get('decision'),
        'reason': f"TIME not homogeneous: {v178.get('path_class_counts')}; attribution only, not scanner rule",
    },
    {
        'version': 'V179 60min TIME probe',
        'n': v179.get('time_rows'),
        'wr': None,
        'avg': None,
        'decision': v179.get('decision'),
        'reason': f"coverage {v179.get('covered_rows')}/{v179.get('time_rows')}={v179.get('coverage_rate')}%; historical production claim blocked",
    },
]

next_direction = {
    'decision': 'STOP_EXIT_LAYER_AND_SCALAR_FILTERS__NEXT_REBUILD_SIGNAL_SUPPLY_LAYER',
    'why': [
        'V177 proved generic execution exits do not improve V175 without cutting winners.',
        'V179 blocks historical 60min execution research due insufficient coverage.',
        'V173/V176 show scalar filters/loss frontiers have no production-grade upgrade left.',
        'Only remaining path with chance for qualitative change is a second non-overlapping signal generator that increases high-quality supply while preserving V175 semantic contract isolation.',
    ],
    'v181_predefined_result': {
        'usable_production': 'combined non-leaking engine n>=260, min_year_n>=40, WR>=84%, AvgPnL>=6.2%, all_year_WR_min>=82%, micro<=1%, T+1=0, frontend/watchlist untouched until dry-run passes',
        'usable_research': 'new child engine n>=120, min_year_n>=20, WR>=86%, AvgPnL>=6.5%, all_year_WR_min>=83%, T+1=0, non-overlap with V175>=60%',
        'unusable': 'any outcome leak, T+1 violation, n below gate, AvgPnL lower via winner truncation, or simply relabeling V175/V172 rows as new signals',
    },
    'next_concrete_script': '/root/.hermes/scripts/v25/v181_signal_supply_expansion_probe.py',
}

report = {
    'decision': next_direction['decision'],
    'generated_at': datetime.now().isoformat(timespec='seconds'),
    'production_write': False,
    'frontend_write': False,
    'watchlist_write': False,
    'gates': GATES,
    'scoreboard': scoreboard,
    'completed': completed,
    'not_done': not_done,
    'next_direction': next_direction,
    'artifact_dir': str(OUT),
}

(OUT / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

lines = ['# V180 SMC研究闭环与下一方向', '', f"Decision: **{report['decision']}**", '', '## 可用/不可用预定结果', '', '|级别|硬门槛|', '|---|---|']
lines.append(f"|生产升级可用|{next_direction['v181_predefined_result']['usable_production']}|")
lines.append(f"|研究可用|{next_direction['v181_predefined_result']['usable_research']}|")
lines.append(f"|不可用|{next_direction['v181_predefined_result']['unusable']}|")
lines += ['', '## 已完成研究', '', '|方向|状态|证据|', '|---|---|---|']
for x in completed:
    lines.append(f"|{x['area']}|{x['status']}|{x['evidence']}|")
lines += ['', '## 未完成/不能继续的方向', '', '|方向|原因|下一处理|', '|---|---|---|']
for x in not_done:
    lines.append(f"|{x['area']}|{x['why_not_done']}|{x['next_test']}|")
lines += ['', '## 核心结论', '退出层和标量门禁已经到边界；下一步只做信号供给层重建，且必须与V175隔离。', '', f"Artifacts: `{OUT}`"]
(OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

print(json.dumps({
    'decision': report['decision'],
    'summary': str(OUT / 'summary.json'),
    'report': str(OUT / 'report.md'),
    'next_script': next_direction['next_concrete_script'],
    'scoreboard': scoreboard,
}, ensure_ascii=False, indent=2))
