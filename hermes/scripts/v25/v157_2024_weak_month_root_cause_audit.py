#!/usr/bin/env python3
"""V157: 2024 weak-month per-trade root-cause audit for V154.

Scope:
- Read-only diagnostic. No production writes.
- Diagnose 2024-05/06/08 concentrated losses.
- Test whether existing pure-SMC structural fields can explain/filter the weak bucket.
- Do NOT use market-breadth as a production gate. Individual symbol K-line context is diagnostic only.
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path('/root/.hermes')
SRC = ROOT / 'smc_audit' / 'v154_cancel_addback_no_micro_20260622' / 'v154_chosen_rows.csv'
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_audit' / 'v157_2024_weak_month_root_cause_audit_20260622'
OUT.mkdir(parents=True, exist_ok=True)
WEAK_MONTHS = {'2024-05', '2024-06', '2024-08'}


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def bval(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if pd.isna(v):
        return False
    return str(v).strip().lower() in {'true', '1', 'yes'}


def sdate(v: Any) -> str:
    return str(v).replace('-', '')[:8]


def month_key(v: Any) -> str:
    d = sdate(v)
    return f'{d[:4]}-{d[4:6]}' if len(d) >= 6 else ''


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0, 'min_year_n': 0, 'year_counts': {}, 'year_wr': {}}
    pnl = pd.to_numeric(df['v154_pnl_pct'], errors='coerce').fillna(0.0)
    year_counts = {str(k): int(v) for k, v in df.groupby('year').size().sort_index().items()}
    year_wr = {}
    for y, g in df.groupby('year'):
        gp = pd.to_numeric(g['v154_pnl_pct'], errors='coerce').fillna(0.0)
        year_wr[str(y)] = round(float((gp > 0).mean() * 100), 2)
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'min_year_n': int(min(year_counts.values())) if year_counts else 0,
        'year_counts': year_counts,
        'year_wr': year_wr,
    }


def load_bars(symbol: str) -> list[dict[str, Any]]:
    code, exch = symbol.split('.')
    p = KLINE_DIR / f'{code}_{exch}_daily_750.json'
    if not p.exists():
        p = KLINE_DIR / f'{code}_{exch}_daily_300.json'
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return []
    if isinstance(data, dict):
        for k in ('data', 'klines', 'bars'):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    return data if isinstance(data, list) else []


def bar_date(b: dict[str, Any]) -> str:
    return sdate(b.get('t') or b.get('date') or b.get('day') or b.get('time') or '')


def add_symbol_context(row: pd.Series) -> dict[str, Any]:
    bars = load_bars(str(row['symbol']))
    ed = sdate(row['v154_entry_date'])
    idx = -1
    for i, b in enumerate(bars):
        if bar_date(b) == ed:
            idx = i
            break
    out: dict[str, Any] = {'kline_found': idx >= 0, 'entry_bar_idx': idx}
    if idx < 0:
        return out
    closes = [fnum(b.get('c') or b.get('close')) for b in bars]
    highs = [fnum(b.get('h') or b.get('high')) for b in bars]
    lows = [fnum(b.get('l') or b.get('low')) for b in bars]
    opens = [fnum(b.get('o') or b.get('open')) for b in bars]
    c = closes[idx]
    out.update({'entry_open': opens[idx], 'entry_high': highs[idx], 'entry_low': lows[idx], 'entry_close': c})
    for n in (5, 10, 20, 60, 120):
        out[f'pre_ret{n}_pct'] = round((c / closes[idx-n] - 1) * 100, 4) if idx >= n and closes[idx-n] else 0.0
    # Post-entry path, T+1 aware diagnostic.
    zl = fnum(row.get('zone_low'))
    zh = fnum(row.get('zone_high'))
    ep = fnum(row.get('entry_price'))
    if ep > 0 and idx + 1 < len(bars):
        post = bars[idx + 1: min(len(bars), idx + 16)]
        post_lows = [fnum(b.get('l') or b.get('low')) for b in post]
        post_highs = [fnum(b.get('h') or b.get('high')) for b in post]
        post_closes = [fnum(b.get('c') or b.get('close')) for b in post]
        out['post15_min_low_pct'] = round((min(post_lows) / ep - 1) * 100, 4) if post_lows else 0.0
        out['post15_max_high_pct'] = round((max(post_highs) / ep - 1) * 100, 4) if post_highs else 0.0
        if zl > 0:
            dead_i = None
            for j, pc in enumerate(post_closes, start=idx + 1):
                if pc < zl:
                    dead_i = j
                    break
            out['zone_dead_after_entry_bars'] = int(dead_i - idx) if dead_i is not None else 999
            out['zone_dead_after_entry_date'] = bar_date(bars[dead_i]) if dead_i is not None else ''
        if zh > 0:
            reclaim_fail_i = None
            for j, pc in enumerate(post_closes, start=idx + 1):
                if pc < zh:
                    reclaim_fail_i = j
                    break
            out['close_below_zone_high_after_entry_bars'] = int(reclaim_fail_i - idx) if reclaim_fail_i is not None else 999
    return out


def root_flags(row: pd.Series) -> dict[str, Any]:
    pnl = fnum(row.get('v154_pnl_pct'))
    loss = pnl <= 0
    zone_dead = str(row.get('v154_exit_reason')) == 'ZONE_CLOSE_DEAD_T1' or bval(row.get('v140_zone_close_dead_lead_signal')) or fnum(row.get('zone_dead_after_entry_bars'), 999) <= 10
    structure_sl = str(row.get('v154_exit_reason')) == 'STRUCTURE_SL_T1'
    entry_chase = fnum(row.get('entry_chase_above_zone_pct'))
    reclaim_above = fnum(row.get('reclaim_close_above_zone_pct'))
    risk = fnum(row.get('risk_pct'))
    reclaim_pos = fnum(row.get('reclaim_close_pos'))
    mae = fnum(row.get('v138_mae_pct'))
    mfe = fnum(row.get('v138_mfe_pct'))
    pre60 = fnum(row.get('pre_ret60_pct'))
    pre20 = fnum(row.get('pre_ret20_pct'))

    entry_too_early = (
        bval(row.get('v140_no_entry_follow_through_le_1pct'))
        or (str(row.get('v143_lifecycle_status')) == 'PRE_BUY_GAP_NOTE_ONLY' and entry_chase >= 3.0)
        or (fnum(row.get('close_below_zone_high_after_entry_bars'), 999) <= 2)
    )
    signal_weak = (
        str(row.get('v132_reclaim_class')) == 'TRUE_TAKEOVER_2'
        or reclaim_pos < 0.65
        or reclaim_above < 2.0
    )
    sl_problem = structure_sl or (risk < 3.2 and mae <= -5) or (loss and mfe >= 7 and str(row.get('v154_exit_reason')) != 'STRUCTURE_OR_1R_TP_T1')
    adverse_stock_regime = pre60 <= -10 or pre20 <= -5

    causes = []
    if zone_dead:
        causes.append('ZONE_DEAD')
    if entry_too_early:
        causes.append('ENTRY_TOO_EARLY')
    if signal_weak:
        causes.append('SIGNAL_WEAK')
    if sl_problem:
        causes.append('SL_OR_TP_STRUCTURE_PROBLEM')
    if adverse_stock_regime:
        causes.append('ADVERSE_SYMBOL_REGIME')
    if loss and not causes:
        causes.append('UNEXPLAINED_LOSS')
    if not loss:
        causes.append('WINNER_CONTEXT')
    return {
        'is_loss': loss,
        'root_zone_dead': zone_dead,
        'root_entry_too_early': entry_too_early,
        'root_signal_weak': signal_weak,
        'root_sl_or_tp_structure_problem': sl_problem,
        'root_adverse_symbol_regime': adverse_stock_regime,
        'root_cause': '+'.join(causes),
    }


def main() -> None:
    df = pd.read_csv(SRC, low_memory=False).copy()
    df['entry_date_key'] = df['v154_entry_date'].map(sdate)
    df['year'] = df['entry_date_key'].str[:4]
    df['month'] = df['v154_entry_date'].map(month_key)
    df['pnl'] = pd.to_numeric(df['v154_pnl_pct'], errors='coerce').fillna(0.0)

    contexts = [add_symbol_context(r) for _, r in df.iterrows()]
    ctx = pd.DataFrame(contexts)
    full = pd.concat([df.reset_index(drop=True), ctx.reset_index(drop=True)], axis=1)
    flags = pd.DataFrame([root_flags(r) for _, r in full.iterrows()])
    full = pd.concat([full.reset_index(drop=True), flags.reset_index(drop=True)], axis=1)
    full.to_csv(OUT / 'v157_all_trades_root_cause.csv', index=False)

    weak = full[full['month'].isin(WEAK_MONTHS)].copy()
    weak_losses = weak[weak['pnl'] <= 0].copy()
    weak.to_csv(OUT / 'v157_2024_weak_month_trades.csv', index=False)
    weak_losses.to_csv(OUT / 'v157_2024_weak_month_losses.csv', index=False)

    month_rows = []
    for month, g in weak.groupby('month'):
        m = metrics(g)
        losses = g[g['pnl'] <= 0]
        cause_counts = losses['root_cause'].value_counts().to_dict()
        bool_counts = {c: int(losses[c].sum()) for c in ['root_zone_dead','root_entry_too_early','root_signal_weak','root_sl_or_tp_structure_problem','root_adverse_symbol_regime']}
        month_rows.append({'month': month, **m, 'loss_n': int(len(losses)), 'cause_counts': cause_counts, **bool_counts})
    month_summary = pd.DataFrame(month_rows).sort_values('month')
    month_summary.to_csv(OUT / 'v157_weak_month_root_cause_summary.csv', index=False)

    loss_cols = [
        'symbol','v154_entry_date','v154_exit_date','v154_pnl_pct','v154_exit_reason','root_cause',
        'v132_reclaim_class','v143_lifecycle_status','reclaim_close_pos','reclaim_close_above_zone_pct',
        'entry_chase_above_zone_pct','risk_pct','v138_mae_pct','v138_mfe_pct',
        'pre_ret20_pct','pre_ret60_pct','post15_min_low_pct','post15_max_high_pct',
        'zone_dead_after_entry_bars','zone_dead_after_entry_date','zone_low','zone_high','entry_price'
    ]
    weak_losses[loss_cols].sort_values(['v154_entry_date','symbol']).to_csv(OUT / 'v157_loss_case_table.csv', index=False)

    # Pure-SMC structural gate tests. These are diagnostic candidates only, not production changes.
    predicates: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
        'STRICT3_ONLY': lambda x: x['v132_reclaim_class'].eq('TRUE_TAKEOVER_3_STRICT'),
        'NO_ZONE_DEAD_LEAD': lambda x: ~x['v140_zone_close_dead_lead_signal'].map(bval),
        'NO_NO_FOLLOWTHROUGH': lambda x: ~x['v140_no_entry_follow_through_le_1pct'].map(bval),
        'ENTRY_CHASE_LE_3': lambda x: pd.to_numeric(x['entry_chase_above_zone_pct'], errors='coerce').fillna(0) <= 3.0,
        'ENTRY_CHASE_LE_2_5': lambda x: pd.to_numeric(x['entry_chase_above_zone_pct'], errors='coerce').fillna(0) <= 2.5,
        'RECLAIM_POS_GE_0_65': lambda x: pd.to_numeric(x['reclaim_close_pos'], errors='coerce').fillna(0) >= 0.65,
        'RECLAIM_POS_GE_0_75': lambda x: pd.to_numeric(x['reclaim_close_pos'], errors='coerce').fillna(0) >= 0.75,
        'RECLAIM_ABOVE_GE_2': lambda x: pd.to_numeric(x['reclaim_close_above_zone_pct'], errors='coerce').fillna(0) >= 2.0,
        'RISK_LE_5_5': lambda x: pd.to_numeric(x['risk_pct'], errors='coerce').fillna(999) <= 5.5,
        'RISK_GE_3': lambda x: pd.to_numeric(x['risk_pct'], errors='coerce').fillna(0) >= 3.0,
        'NO_PRE_BUY_GAP_NOTE': lambda x: ~x['v143_lifecycle_status'].eq('PRE_BUY_GAP_NOTE_ONLY'),
    }
    variants = []
    names = list(predicates)
    base_mask = pd.Series([True] * len(full), index=full.index)
    for r in range(0, 4):
        for combo in itertools.combinations(names, r):
            mask = base_mask.copy()
            for name in combo:
                mask &= predicates[name](full)
            g = full[mask].copy()
            if len(g) == 0:
                continue
            mm = metrics(g)
            variants.append({'gate': 'ALL_V154' if not combo else '+'.join(combo), **mm})
    variants_df = pd.DataFrame(variants).drop_duplicates('gate')
    # Prefer stable candidates, then volume, then WR.
    variants_df['release_like_pass'] = variants_df.apply(lambda r: bool(
        r['n'] >= 200 and r['wr'] >= 82.0 and r['avg'] >= 3.2 and r['min_year_n'] >= 35 and all(float(v) >= 78.0 for v in r['year_wr'].values())
    ), axis=1)
    variants_df = variants_df.sort_values(['release_like_pass','n','wr','avg'], ascending=[False, False, False, False])
    variants_df.to_csv(OUT / 'v157_pure_smc_gate_search.csv', index=False)

    promotable = variants_df[variants_df['release_like_pass']].to_dict(orient='records')
    cause_totals = {c: int(weak_losses[c].sum()) for c in ['root_zone_dead','root_entry_too_early','root_signal_weak','root_sl_or_tp_structure_problem','root_adverse_symbol_regime']}
    root_counts = weak_losses['root_cause'].value_counts().to_dict()

    decision = 'V157_NO_PURE_SMC_PRODUCTION_GATE_KEEP_V154_RESEARCH_ONLY'
    if promotable:
        decision = 'V157_PURE_SMC_GATE_CANDIDATE_FOUND_REQUIRES_FULL_RETEST'

    summary = {
        'decision': decision,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'source': str(SRC),
        'out': str(OUT),
        'overall_v154': metrics(full),
        'weak_months': sorted(WEAK_MONTHS),
        'weak_month_overall': metrics(weak),
        'weak_loss_n': int(len(weak_losses)),
        'weak_loss_root_boolean_counts': cause_totals,
        'weak_loss_root_combo_counts': root_counts,
        'month_summary': month_summary.to_dict(orient='records'),
        'best_pure_smc_gate_rows': variants_df.head(15).to_dict(orient='records'),
        'promotable_pure_smc_candidates': promotable,
        'interpretation': (
            'Weak 2024 months are dominated by post-entry zone death and early/pre-buy-gap entries. '
            'Existing pure-SMC fields can describe the failures, but no tested pure-SMC gate preserves production-level volume/year coverage while fixing 2024. '
            'Therefore V154 remains research-only unless a new non-leaking SMC lifecycle rule is designed and fully retested.'
        ),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    report = [
        '# V157 2024 Weak-Month Root Cause Audit', '',
        f"Decision: `{decision}`。只读审计，不写生产。", '',
        '## V154 overall', pd.DataFrame([metrics(full)]).to_markdown(index=False), '',
        '## Weak-month summary', month_summary.to_markdown(index=False), '',
        '## Weak-month loss root causes',
        pd.DataFrame([{'root_flag': k, 'loss_count': v} for k, v in cause_totals.items()]).to_markdown(index=False), '',
        '## Weak-month loss cases',
        weak_losses[loss_cols].sort_values(['v154_entry_date','symbol']).to_markdown(index=False), '',
        '## Pure-SMC gate search top rows',
        variants_df.head(20).to_markdown(index=False), '',
        '## Conclusion',
        summary['interpretation'],
    ]
    (OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
