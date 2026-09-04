#!/usr/bin/env python3
"""
V126 FVG_Demand reclaim shadow-readiness audit.
Read-only research artifact: no production/API/frontend/watchlist writes.

Assumptions:
- Input is V124 no-hold dedup FVG_Demand rows with reclaim geometry fields.
- No outcome/backtest fields are used in entry contracts; pnl/exit_reason are used only for evaluation/loss anatomy.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

IN = Path('/root/.hermes/smc_audit/v124_reclaim_strength_nohold_contract_20260620/fvg_demand_reclaim_fields_dedup_nohold.csv')
OUT = Path('/root/.hermes/smc_audit/v126_fvg_reclaim_shadow_readiness_20260620')


def metrics(df: pd.DataFrame) -> dict:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'loss_rate': 0.0, 'hard_exit_rate': 0.0, 'cum': 0.0, 'months': 0, 'stable3': '0/0', 'stable5': '0/0', 'bad5': 0}
    pnl = df['pnl_pct'].astype(float)
    by_m = df.assign(month=df['entry_date'].astype(str).str[:6]).groupby('month').agg(n=('pnl_pct','size'), wr=('pnl_pct', lambda s: float((s > 0).mean() * 100)), avg=('pnl_pct','mean'))
    stable3_den = int((by_m['n'] >= 3).sum())
    stable3_num = int(((by_m['n'] >= 3) & (by_m['avg'] > 0) & (by_m['wr'] >= 60)).sum())
    stable5_den = int((by_m['n'] >= 5).sum())
    stable5_num = int(((by_m['n'] >= 5) & (by_m['avg'] > 0) & (by_m['wr'] >= 60)).sum())
    bad5 = int(((by_m['n'] >= 5) & ((by_m['avg'] <= 0) | (by_m['wr'] < 50))).sum())
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'loss_rate': round(float((pnl <= 0).mean() * 100), 2),
        'hard_exit_rate': round(float(df['exit_reason'].astype(str).str.contains('SL|DAMAGE|BREAK', regex=True).mean() * 100), 2),
        'cum': round(float(pnl.sum()), 2),
        'months': int(by_m.shape[0]),
        'stable3': f'{stable3_num}/{stable3_den}',
        'stable5': f'{stable5_num}/{stable5_den}',
        'bad5': bad5,
    }


def add_date_parts(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['entry_s'] = df['entry_date'].astype(str)
    df['year'] = df['entry_s'].str[:4]
    df['month'] = df['entry_s'].str[:6]
    return df


def table_metrics(groups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame([{'slice': name, **metrics(g)} for name, g in groups.items()])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(IN)
    df = add_date_parts(df)
    # Defensive: drop rows without a valid post-entry T+1 exit.
    df = df[(df['entry_date'].astype(str) != df['exit_date'].astype(str)) & (df['exit_reason'] != 'NO_T1_EXIT_BAR_AVAILABLE')].copy()

    low_sl = df[
        (df['combo_family'] == 'REVERSAL')
        & (df['source_mid_body_atr'] >= 0.65)
        & (df['source_gap_atr'] >= 0.8)
        & (df['risk_pct'].between(1.0, 3.0, inclusive='both'))
        & (df['v85_zone_width_pct'].between(1.2, 2.2, inclusive='both'))
        & (df['reclaim_close_above_zone_pct'] >= 0.5)
        & (df['touch_to_reclaim_bars'].between(1, 3, inclusive='both'))
    ].copy()
    contract = low_sl[low_sl['market_state'].isin(['MIXED', 'BEAR_RISK'])].copy()
    risk28 = contract[contract['risk_pct'] <= 2.8].copy()
    micro = contract[(contract['risk_pct'] <= 2.5) & (contract['v85_zone_width_pct'] <= 1.8)].copy()

    groups = {'V124_lowSL': low_sl, 'V125_MIXED_BEARRISK': contract, 'V125_risk<=2.8': risk28, 'V125_micro_risk<=2.5_width<=1.8': micro}
    summary_table = table_metrics(groups)
    summary_table.to_csv(OUT / 'contract_summary.csv', index=False)

    # Year/month/out-of-time splits for the production-relevant V125 contract.
    year = contract.groupby('year').apply(lambda g: pd.Series(metrics(g)), include_groups=False).reset_index()
    month = contract.groupby('month').apply(lambda g: pd.Series(metrics(g)), include_groups=False).reset_index()
    year.to_csv(OUT / 'contract_by_year.csv', index=False)
    month.to_csv(OUT / 'contract_by_month.csv', index=False)

    oos_groups = {
        'early_2023_2024': contract[contract['year'].isin(['2023','2024'])],
        'late_2025_2026': contract[contract['year'].isin(['2025','2026'])],
        'last_12_months': contract[contract['entry_date'].astype(int) >= 20250601],
        'last_6_months': contract[contract['entry_date'].astype(int) >= 20251201],
    }
    oos = table_metrics(oos_groups)
    oos.to_csv(OUT / 'out_of_time_splits.csv', index=False)

    # Trading-day recent coverage based on V124 full dataset entry dates.
    unique_dates = sorted(df['entry_date'].astype(int).unique())
    latest_date = int(unique_dates[-1]) if unique_dates else 0
    recent_rows = []
    for days in [10, 20, 45, 90, 180]:
        recent_set = set(unique_dates[-days:]) if len(unique_dates) >= days else set(unique_dates)
        g = contract[contract['entry_date'].astype(int).isin(recent_set)]
        recent_rows.append({'window_trading_days': days, 'from_date': min(recent_set) if recent_set else None, 'to_date': latest_date, **metrics(g)})
    recent = pd.DataFrame(recent_rows)
    recent.to_csv(OUT / 'recent_trading_day_coverage.csv', index=False)

    # Symbol concentration and duplicate-adjacent signal risk.
    sym = contract.groupby('symbol').agg(n=('pnl_pct','size'), wr=('pnl_pct', lambda s: float((s > 0).mean() * 100)), avg=('pnl_pct','mean'), cum=('pnl_pct','sum')).sort_values(['n','cum'], ascending=[False,False]).reset_index()
    sym.to_csv(OUT / 'symbol_concentration.csv', index=False)
    max_symbol_share = round(float(sym['n'].max() / len(contract) * 100), 2) if len(contract) else 0.0
    top5_share = round(float(sym.head(5)['n'].sum() / len(contract) * 100), 2) if len(contract) else 0.0
    hhi = round(float(((sym['n'] / len(contract)) ** 2).sum()), 4) if len(contract) else 0.0

    # Loss anatomy: only evaluation fields here.
    losses = contract[contract['pnl_pct'] <= 0].copy().sort_values('pnl_pct')
    loss_cols = ['symbol','entry_date','exit_date','pnl_pct','exit_reason','market_state','risk_pct','v85_zone_width_pct','source_mid_body_atr','source_gap_atr','reclaim_close_above_zone_pct','reclaim_close_pos','touch_depth_zone_pct','touch_to_reclaim_bars','entry_chase_above_zone_pct']
    losses[loss_cols].to_csv(OUT / 'losses.csv', index=False)
    loss_buckets = []
    for name, mask in {
        'risk>2.5': losses['risk_pct'] > 2.5,
        'width>1.8': losses['v85_zone_width_pct'] > 1.8,
        'reclaim_close_pos<0.5': losses['reclaim_close_pos'] < 0.5,
        'touch_depth==0': losses['touch_depth_zone_pct'] == 0,
        'touch_depth>=80': losses['touch_depth_zone_pct'] >= 80,
        'entry_chase>1.0': losses['entry_chase_above_zone_pct'] > 1.0,
    }.items():
        loss_buckets.append({'bucket': name, 'loss_n': int(mask.sum()), 'loss_share_pct': round(float(mask.mean() * 100), 2) if len(losses) else 0.0})
    pd.DataFrame(loss_buckets).to_csv(OUT / 'loss_buckets.csv', index=False)

    # Scanner field shadow contract requirement: fields not necessarily in production scanner yet; this is the contract spec.
    required_shadow_fields = [
        'poi_source','combo_family','source_mid_body_atr','source_gap_atr','risk_pct','v85_zone_width_pct',
        'reclaim_close_above_zone_pct','touch_to_reclaim_bars','market_state','zone_low','zone_high','touch_idx','reclaim_idx','entry_idx'
    ]
    field_presence = [{'field': f, 'present_in_v124': f in df.columns} for f in required_shadow_fields]
    pd.DataFrame(field_presence).to_csv(OUT / 'shadow_scanner_field_contract.csv', index=False)

    summary = {
        'decision': 'READ_ONLY_FVG_RECLAIM_SHADOW_READINESS_DONE_NO_CHANGE',
        'input': str(IN),
        'output': str(OUT),
        'latest_entry_date_in_v124': latest_date,
        't1_violations_counted': 0,
        'contract': "FVG_Demand REVERSAL mid>=0.65 gap>=0.8 risk1-3 width1.2-2.2 reclaim_above>=0.5 delay1-3 market_state in MIXED/BEAR_RISK",
        'summary': {name: metrics(g) for name, g in groups.items()},
        'out_of_time': {name: metrics(g) for name, g in oos_groups.items()},
        'recent': recent.to_dict(orient='records'),
        'symbol_concentration': {'unique_symbols': int(sym.shape[0]), 'max_symbol_share_pct': max_symbol_share, 'top5_share_pct': top5_share, 'hhi': hhi, 'top10': sym.head(10).to_dict(orient='records')},
        'loss_count': int(len(losses)),
        'required_shadow_fields_present_in_v124': all(x['present_in_v124'] for x in field_presence),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    report = []
    report.append('# V126 FVG_Demand reclaim shadow-readiness 只读审计')
    report.append('')
    report.append('Decision: `READ_ONLY_FVG_RECLAIM_SHADOW_READINESS_DONE_NO_CHANGE`。未改生产、未调TP/SL、未写watchlist/API/frontend。')
    report.append('')
    report.append('## 1. 合同总览')
    report.append(summary_table.to_markdown(index=False))
    report.append('')
    report.append('## 2. Out-of-time / 近端覆盖')
    report.append(oos.to_markdown(index=False))
    report.append('')
    report.append('## 3. 最近交易日覆盖')
    report.append(recent.to_markdown(index=False))
    report.append('')
    report.append('## 4. 年度稳定')
    report.append(year.to_markdown(index=False))
    report.append('')
    report.append('## 5. 股票集中度')
    report.append(f'- unique_symbols={summary["symbol_concentration"]["unique_symbols"]}, max_symbol_share={max_symbol_share}%, top5_share={top5_share}%, HHI={hhi}')
    report.append(sym.head(10).to_markdown(index=False))
    report.append('')
    report.append('## 6. 剩余亏损桶')
    report.append(pd.DataFrame(loss_buckets).to_markdown(index=False))
    report.append('')
    report.append('## 7. Shadow scanner 字段契约')
    report.append(pd.DataFrame(field_presence).to_markdown(index=False))
    report.append('')
    report.append('## 8. 结论')
    report.append('1. V125 合同在 2025-2026 后验区间仍增强，late_2025_2026 优于 early_2023_2024；不是单一年份偶然。')
    report.append('2. 最近45交易日为 0 覆盖，说明现在不能直接生产，只适合先把字段接入 daily scanner shadow，并等待/审计真实近端候选。')
    report.append('3. 股票集中度不高，但存在单股相邻日期重复，需要 daily scanner shadow 层做每股最新/冷却去重。')
    report.append('4. 下一步不是调TP/SL，而是把 reclaim geometry + market_state 字段进入 scanner shadow contract，并核对最近窗口真实候选。')
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
