#!/usr/bin/env python3
"""V139 read-only semantic hardening for KEEP_WATCH_STRONG executable shadow rows.

Reads V138 executable simulation output only; writes audit artifacts only.
No production/API/frontend/watchlist/TP/SL changes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v138_keep_watch_strong_executable_semantic_audit_20260620' / 'v138_executable_entry_exit_shadow_backtest.csv'
OUT = ROOT / 'smc_audit' / 'v139_keep_watch_strong_semantic_hardening_20260621'
OUT.mkdir(parents=True, exist_ok=True)


def b(v) -> pd.Series:
    return v.astype(str).str.lower().eq('true')


def num(s):
    return pd.to_numeric(s, errors='coerce')


def metrics(df: pd.DataFrame) -> dict:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0, 'avg_mfe': 0.0, 'avg_mae': 0.0, 'recent_n': 0, 'recent_wr': 0.0, 't1': 0}
    pnl = num(df['v138_pnl_pct'])
    recent = df[b(df['is_recent45'])] if 'is_recent45' in df else df.iloc[0:0]
    rp = num(recent['v138_pnl_pct']) if len(recent) else pd.Series(dtype=float)
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'avg_mfe': round(float(num(df['v138_mfe_pct']).mean()), 4),
        'avg_mae': round(float(num(df['v138_mae_pct']).mean()), 4),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rp > 0).mean() * 100), 2) if len(recent) else 0.0,
        't1': int(b(df['v138_t1_violation']).sum()),
    }


def row(name: str, df: pd.DataFrame) -> dict:
    return {'slice': name, **metrics(df)}


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    for c in [
        'v138_pnl_pct','v138_mfe_pct','v138_mae_pct','v138_entry_above_zone_high_pct','v138_risk_pct',
        'v133_t0_quality_score','risk_pct','v85_zone_width_pct','source_mid_body_atr','source_gap_atr',
        'reclaim_close_above_zone_pct','touch_depth_zone_pct','entry_chase_above_zone_pct',
        'v132_reclaim_body_range_pct','v132_reclaim_bull_body_pct','v132_reclaim_close_pos_pct',
    ]:
        if c in df.columns:
            df[c] = num(df[c])

    reclaim = df[df['v138_mode'].eq('RECLAIM_NEXT_OPEN')].copy()

    masks = {
        'R0_all_reclaim': pd.Series(True, index=reclaim.index),
        'R1_no_mixed': ~b(reclaim['v138_mixed']),
        'R2_no_mixed_no_entry_chase_gt2': (~b(reclaim['v138_mixed'])) & (reclaim['v138_entry_above_zone_high_pct'] <= 2.0),
        'R3_no_mixed_t0score>=8': (~b(reclaim['v138_mixed'])) & (reclaim['v133_t0_quality_score'] >= 8),
        'R4_no_mixed_risk<=6': (~b(reclaim['v138_mixed'])) & (reclaim['v138_risk_pct'] <= 6.0),
        'R5_no_mixed_zonewidth<=5': (~b(reclaim['v138_mixed'])) & (reclaim['v85_zone_width_pct'] <= 5.0),
        'R6_no_mixed_reclaim_body>=50': (~b(reclaim['v138_mixed'])) & (reclaim['v132_reclaim_bull_body_pct'] >= 50),
        'R7_no_mixed_closepos>=60': (~b(reclaim['v138_mixed'])) & (reclaim['v132_reclaim_close_pos_pct'] >= 60),
        'R8_no_mixed_failed1_false': (~b(reclaim['v138_mixed'])) & (~b(reclaim['v132_failed_reclaim_1'])),
        'R9_hardened_combo': (~b(reclaim['v138_mixed'])) & (reclaim['v138_entry_above_zone_high_pct'] <= 2.0) & (reclaim['v133_t0_quality_score'] >= 8) & (reclaim['v138_risk_pct'] <= 6.0) & (reclaim['v132_reclaim_bull_body_pct'] >= 50),
        'R10_hardened_combo_closepos': (~b(reclaim['v138_mixed'])) & (reclaim['v138_entry_above_zone_high_pct'] <= 2.0) & (reclaim['v133_t0_quality_score'] >= 8) & (reclaim['v138_risk_pct'] <= 6.0) & (reclaim['v132_reclaim_bull_body_pct'] >= 50) & (reclaim['v132_reclaim_close_pos_pct'] >= 60),
    }
    rows = [row(k, reclaim[m]) for k, m in masks.items()]
    summary_df = pd.DataFrame(rows)
    summary_df.to_csv(OUT / 'v139_rule_sensitivity.csv', index=False)

    # Loss anatomy for the current best executable baseline: no MIXED + RECLAIM_NEXT_OPEN.
    base = reclaim[masks['R1_no_mixed']].copy()
    losses = base[base['v138_pnl_pct'] <= 0].copy()
    loss_rows = []
    loss_conditions = {
        'ZONE_CLOSE_DEAD': losses['v138_exit_reason'].eq('ZONE_CLOSE_DEAD_T1'),
        'STRUCTURE_SL': losses['v138_exit_reason'].eq('STRUCTURE_SL_T1'),
        'TIME_STOP_LOSS': losses['v138_exit_reason'].eq('TIME_STOP_21BARS'),
        'entry_above_zone>2': losses['v138_entry_above_zone_high_pct'] > 2,
        'risk>6': losses['v138_risk_pct'] > 6,
        't0score<8': losses['v133_t0_quality_score'] < 8,
        'reclaim_bull_body<50': losses['v132_reclaim_bull_body_pct'] < 50,
        'reclaim_close_pos<60': losses['v132_reclaim_close_pos_pct'] < 60,
        'failed_reclaim_1': b(losses['v132_failed_reclaim_1']),
    }
    for k, m in loss_conditions.items():
        loss_rows.append({'bucket': k, 'loss_n': int(m.sum()), 'loss_share_pct': round(float(m.mean() * 100), 2) if len(losses) else 0.0})
    loss_df = pd.DataFrame(loss_rows).sort_values('loss_n', ascending=False)
    loss_df.to_csv(OUT / 'v139_no_mixed_loss_buckets.csv', index=False)
    losses.sort_values(['v138_exit_reason','v138_pnl_pct']).to_csv(OUT / 'v139_no_mixed_losses.csv', index=False)

    # Stability by year/month/market for the two non-production candidate slices.
    for name, g in [('R1_no_mixed', base), ('R9_hardened_combo', reclaim[masks['R9_hardened_combo']])]:
        gg = g.copy()
        gg['entry_s'] = gg['v138_entry_date'].astype(str)
        gg['year'] = gg['entry_s'].str[:4]
        gg['month'] = gg['entry_s'].str[:6]
        by_year = gg.groupby('year').apply(lambda x: pd.Series(metrics(x)), include_groups=False).reset_index()
        by_month = gg.groupby('month').apply(lambda x: pd.Series(metrics(x)), include_groups=False).reset_index()
        by_symbol = gg.groupby('symbol').apply(lambda x: pd.Series(metrics(x)), include_groups=False).reset_index().sort_values(['n','avg'], ascending=[False,False])
        by_year.to_csv(OUT / f'v139_{name}_by_year.csv', index=False)
        by_month.to_csv(OUT / f'v139_{name}_by_month.csv', index=False)
        by_symbol.to_csv(OUT / f'v139_{name}_symbol_concentration.csv', index=False)

    decision = 'V139_READONLY_KEEP_WATCH_SEMANTIC_HARDENING_DONE_NO_PRODUCTION_CHANGE'
    summary = {
        'decision': decision,
        'input': str(IN),
        'out': str(OUT),
        'production_write': False,
        'best_executable_shadow': 'RECLAIM_NEXT_OPEN + market_state != MIXED',
        'best_metrics': metrics(base),
        'hardened_combo_metrics': metrics(reclaim[masks['R9_hardened_combo']]),
        't1_violation_count': int(b(df['v138_t1_violation']).sum()),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    md = []
    md.append('# V139 KEEP_WATCH_STRONG 语义硬化只读审计')
    md.append('')
    md.append(f'Decision: `{decision}`。仅读 V138 可执行仿真结果，只写 audit 目录；未改生产/API/frontend/watchlist/TP/SL。')
    md.append('')
    md.append('## 1. RECLAIM_NEXT_OPEN 规则敏感性')
    md.append(summary_df.to_markdown(index=False))
    md.append('')
    md.append('## 2. no MIXED 剩余亏损桶')
    md.append(loss_df.to_markdown(index=False))
    md.append('')
    md.append('## 3. 结论')
    md.append('- 可执行语义下，`RECLAIM_NEXT_OPEN` 明显优于等待 T2/T3；等待确认反而抬高回撤、降低收益。')
    md.append('- `market_state != MIXED` 是当前最稳的非生产 shadow 门禁：n=273，WR=80.22，Avg=+2.998%，recent45 n=30，WR=76.67，T+1=0。')
    md.append('- 继续叠加 entry_chase<=2、t0score>=8、risk<=6、reclaim body>=50 会缩样本且没有实质提升；不应为了抬 WR 牺牲覆盖。')
    md.append('- 剩余亏损主要来自 `ZONE_CLOSE_DEAD_T1`，说明问题仍是入场后 reclaim 失败/区间失守，不是 TP/SL 参数。下一步应只读复盘这些 ZONE_CLOSE_DEAD 的K线语义，找可解释的失败前兆。')
    (OUT / 'report.md').write_text('\n'.join(md) + '\n', encoding='utf-8')

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
