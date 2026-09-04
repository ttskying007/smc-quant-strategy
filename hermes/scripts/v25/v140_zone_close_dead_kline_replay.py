#!/usr/bin/env python3
"""V140 read-only ZONE_CLOSE_DEAD_T1 kline semantic replay.

Continuation of V139. Reads V138 executable shadow output + local kline cache only;
writes audit artifacts only. No production/API/frontend/watchlist/TP/SL changes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v138_keep_watch_strong_executable_semantic_audit_20260620' / 'v138_executable_entry_exit_shadow_backtest.csv'
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_audit' / 'v140_zone_close_dead_kline_replay_20260621'
OUT.mkdir(parents=True, exist_ok=True)


def to_num(s):
    return pd.to_numeric(s, errors='coerce')


def bools(s):
    return s.astype(str).str.lower().eq('true')


def pct(a: float, b: float) -> float:
    if b in (0, None) or pd.isna(a) or pd.isna(b):
        return float('nan')
    return (float(a) / float(b) - 1.0) * 100.0


def cache_path(symbol: str) -> Path:
    code, ex = symbol.split('.')
    return KLINE_DIR / f'{code}_{ex}_daily_750.json'


def load_bars(symbol: str) -> list[dict[str, Any]]:
    p = cache_path(symbol)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return []


def bv(bar: dict[str, Any] | None, k: str) -> float:
    if not bar:
        return float('nan')
    try:
        return float(bar.get(k, float('nan')))
    except Exception:
        return float('nan')


def datev(bar: dict[str, Any] | None) -> str:
    if not bar:
        return ''
    return str(bar.get('t', bar.get('date', '')))


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'loss': 0.0, 'zdead': 0.0, 'recent_n': 0, 'recent_wr': 0.0}
    pnl = to_num(df['v138_pnl_pct'])
    recent = df[bools(df['is_recent45'])] if 'is_recent45' in df else df.iloc[0:0]
    rp = to_num(recent['v138_pnl_pct']) if len(recent) else pd.Series(dtype=float)
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'zdead': round(float(df['v138_exit_reason'].eq('ZONE_CLOSE_DEAD_T1').mean() * 100), 2),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rp > 0).mean() * 100), 2) if len(recent) else 0.0,
    }


def enrich(row: pd.Series, bars: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {'kline_missing': not bool(bars)}
    if not bars:
        return out
    n = len(bars)
    idxs = {}
    for k in ['touch_idx', 'reclaim_idx', 'v138_entry_idx', 'v138_exit_idx', 'entry_idx']:
        try:
            idxs[k] = int(row[k]) if not pd.isna(row[k]) else -1
        except Exception:
            idxs[k] = -1
    touch = idxs['touch_idx']
    reclaim = idxs['reclaim_idx']
    entry = idxs['v138_entry_idx']
    exit_i = idxs['v138_exit_idx']
    zl = float(row['zone_low'])
    zh = float(row['zone_high'])
    ep = float(row['v138_entry_price'])

    def bar(i: int) -> dict[str, Any] | None:
        return bars[i] if 0 <= i < n else None

    tb, rb, eb, xb = bar(touch), bar(reclaim), bar(entry), bar(exit_i)
    pre_touch_start = max(0, touch - 5)
    pre_reclaim = bars[max(0, touch):max(0, reclaim)] if touch >= 0 and reclaim >= 0 else []
    between_reclaim_entry = bars[max(0, reclaim + 1):max(0, entry)] if reclaim >= 0 and entry >= 0 else []
    post_entry_t1 = bar(entry + 1)
    post_entry_t2 = bar(entry + 2)
    pre5 = bars[pre_touch_start:touch] if touch >= 0 else []

    out.update({
        'touch_date_k': datev(tb),
        'reclaim_date_k': datev(rb),
        'entry_date_k': datev(eb),
        'exit_date_k': datev(xb),
        'touch_low_to_zl_pct': pct(bv(tb, 'l'), zl),
        'touch_close_to_zh_pct': pct(bv(tb, 'c'), zh),
        'reclaim_close_to_zh_pct': pct(bv(rb, 'c'), zh),
        'reclaim_low_to_zl_pct': pct(bv(rb, 'l'), zl),
        'entry_open_to_zh_pct': pct(bv(eb, 'o'), zh),
        'entry_close_to_zl_pct': pct(bv(eb, 'c'), zl),
        'entry_low_to_zl_pct': pct(bv(eb, 'l'), zl),
        't1_close_to_zl_pct': pct(bv(post_entry_t1, 'c'), zl),
        't1_low_to_zl_pct': pct(bv(post_entry_t1, 'l'), zl),
        't2_close_to_zl_pct': pct(bv(post_entry_t2, 'c'), zl),
        'touch_to_reclaim_bars_k': reclaim - touch if touch >= 0 and reclaim >= 0 else None,
        'reclaim_to_entry_bars_k': entry - reclaim if reclaim >= 0 and entry >= 0 else None,
        'entry_gap_from_reclaim_close_pct_k': pct(bv(eb, 'o'), bv(rb, 'c')),
        'entry_intraday_fail': bv(eb, 'c') < zl,
        'entry_low_pierce_zl': bv(eb, 'l') < zl,
        't1_close_dead': bv(post_entry_t1, 'c') < zl,
        'pre_reclaim_close_below_zl_count': sum(1 for b in pre_reclaim if bv(b, 'c') < zl),
        'pre_reclaim_low_below_zl_count': sum(1 for b in pre_reclaim if bv(b, 'l') < zl),
        'between_reclaim_entry_close_below_zl_count': sum(1 for b in between_reclaim_entry if bv(b, 'c') < zl),
        'between_reclaim_entry_low_below_zl_count': sum(1 for b in between_reclaim_entry if bv(b, 'l') < zl),
        'pre5_close_trend_pct': pct(bv(tb, 'c'), bv(pre5[0], 'c')) if pre5 else float('nan'),
        'pre5_min_low_to_zl_pct': pct(min((bv(b, 'l') for b in pre5), default=float('nan')), zl) if pre5 else float('nan'),
    })
    # Failure phenotype tags visible before or at executable entry close.
    tags: list[str] = []
    if out['pre_reclaim_close_below_zl_count'] > 0:
        tags.append('ZONE_ALREADY_CLOSED_BELOW_BEFORE_RECLAIM')
    if out['between_reclaim_entry_low_below_zl_count'] > 0:
        tags.append('POST_RECLAIM_PIERCED_BEFORE_ENTRY')
    if out['entry_gap_from_reclaim_close_pct_k'] > 2:
        tags.append('ENTRY_GAP_CHASE_GT2')
    if out['entry_open_to_zh_pct'] > 2:
        tags.append('ENTRY_ABOVE_ZONE_GT2')
    if out['entry_intraday_fail']:
        tags.append('ENTRY_DAY_CLOSE_BACK_BELOW_ZONE')
    if out['entry_low_pierce_zl']:
        tags.append('ENTRY_DAY_LOW_PIERCED_ZONE')
    if float(row.get('v138_risk_pct', float('nan'))) > 6:
        tags.append('RISK_GT6')
    if float(row.get('v132_reclaim_bull_body_pct', float('nan'))) < 50:
        tags.append('WEAK_RECLAIM_BODY_LT50')
    if str(row.get('market_state')) == 'MIXED':
        tags.append('MIXED')
    out['failure_tags'] = '|'.join(tags) if tags else 'NO_OBVIOUS_PRE_ENTRY_TAG'
    return out


def gate_table(df: pd.DataFrame, gates: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for name, mask in gates.items():
        rows.append({'gate': name, **metrics(df[mask])})
    return pd.DataFrame(rows)


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    numeric_cols = ['v138_pnl_pct','v138_entry_idx','v138_exit_idx','touch_idx','reclaim_idx','zone_low','zone_high','v138_entry_price','v138_risk_pct','v138_entry_above_zone_high_pct','v132_reclaim_bull_body_pct','v132_reclaim_close_pos_pct','v85_zone_width_pct']
    for c in numeric_cols:
        if c in df.columns:
            df[c] = to_num(df[c])
    base = df[df['v138_mode'].eq('RECLAIM_NEXT_OPEN') & (~bools(df['v138_mixed']))].copy()
    zdead = base[base['v138_exit_reason'].eq('ZONE_CLOSE_DEAD_T1')].copy()

    cache: dict[str, list[dict[str, Any]]] = {}
    enriched = []
    for _, r in base.iterrows():
        sym = str(r['symbol'])
        if sym not in cache:
            cache[sym] = load_bars(sym)
        enriched.append(enrich(r, cache[sym]))
    edf = pd.concat([base.reset_index(drop=True), pd.DataFrame(enriched)], axis=1)
    edf.to_csv(OUT / 'v140_no_mixed_reclaim_kline_enriched.csv', index=False)
    zedf = edf[edf['v138_exit_reason'].eq('ZONE_CLOSE_DEAD_T1')].copy()
    zedf.to_csv(OUT / 'v140_zone_close_dead_rows_enriched.csv', index=False)

    # Multi-label loss tag counts.
    tag_rows = []
    for tags in zedf['failure_tags'].fillna('').astype(str):
        for t in tags.split('|'):
            if t:
                tag_rows.append(t)
    tag_counts = pd.Series(tag_rows).value_counts().rename_axis('tag').reset_index(name='n')
    tag_counts['share_of_zdead_pct'] = (tag_counts['n'] / max(1, len(zedf)) * 100).round(2)
    tag_counts.to_csv(OUT / 'v140_zone_close_dead_failure_tag_counts.csv', index=False)

    gates = {
        'B0_current_no_mixed': pd.Series(True, index=edf.index),
        'B1_remove_entry_gap_chase_gt2': edf['entry_gap_from_reclaim_close_pct_k'].fillna(0) <= 2,
        'B2_remove_entry_above_zone_gt2': edf['entry_open_to_zh_pct'].fillna(0) <= 2,
        'B3_remove_entry_day_close_fail': ~edf['entry_intraday_fail'].fillna(False).astype(bool),
        'B4_remove_entry_day_low_pierce': ~edf['entry_low_pierce_zl'].fillna(False).astype(bool),
        'B5_remove_post_reclaim_pre_entry_pierce': edf['between_reclaim_entry_low_below_zl_count'].fillna(0) == 0,
        'B6_remove_zone_closed_below_before_reclaim': edf['pre_reclaim_close_below_zl_count'].fillna(0) == 0,
        'B7_risk_le6': edf['v138_risk_pct'] <= 6,
        'B8_reclaim_body_ge50': edf['v132_reclaim_bull_body_pct'] >= 50,
        'B9_pre_entry_semantic_combo': (edf['entry_gap_from_reclaim_close_pct_k'].fillna(0) <= 2) & (edf['entry_open_to_zh_pct'].fillna(0) <= 2) & (~edf['entry_intraday_fail'].fillna(False).astype(bool)) & (edf['between_reclaim_entry_low_below_zl_count'].fillna(0) == 0),
        'B10_combo_plus_body': (edf['entry_gap_from_reclaim_close_pct_k'].fillna(0) <= 2) & (edf['entry_open_to_zh_pct'].fillna(0) <= 2) & (~edf['entry_intraday_fail'].fillna(False).astype(bool)) & (edf['between_reclaim_entry_low_below_zl_count'].fillna(0) == 0) & (edf['v132_reclaim_bull_body_pct'] >= 50),
    }
    gdf = gate_table(edf, gates)
    gdf.to_csv(OUT / 'v140_pre_entry_gate_sensitivity.csv', index=False)

    # Winner/loser medians for interpretable kline fields.
    fields = ['entry_gap_from_reclaim_close_pct_k','entry_open_to_zh_pct','entry_close_to_zl_pct','entry_low_to_zl_pct','t1_close_to_zl_pct','pre_reclaim_close_below_zl_count','between_reclaim_entry_low_below_zl_count','v138_risk_pct','v132_reclaim_bull_body_pct','v132_reclaim_close_pos_pct']
    rows = []
    winners = edf[edf['v138_pnl_pct'] > 0]
    losers = edf[edf['v138_pnl_pct'] <= 0]
    zloss = zedf
    for f in fields:
        rows.append({
            'field': f,
            'winner_median': round(float(winners[f].median()), 4) if f in winners and len(winners) else 0,
            'loser_median': round(float(losers[f].median()), 4) if f in losers and len(losers) else 0,
            'zdead_median': round(float(zloss[f].median()), 4) if f in zloss and len(zloss) else 0,
            'winner_mean': round(float(winners[f].mean()), 4) if f in winners and len(winners) else 0,
            'loser_mean': round(float(losers[f].mean()), 4) if f in losers and len(losers) else 0,
            'zdead_mean': round(float(zloss[f].mean()), 4) if f in zloss and len(zloss) else 0,
        })
    cmpdf = pd.DataFrame(rows)
    cmpdf.to_csv(OUT / 'v140_winner_loser_kline_field_compare.csv', index=False)

    summary = {
        'decision': 'V140_READONLY_ZONE_CLOSE_DEAD_KLINE_REPLAY_DONE_NO_PRODUCTION_CHANGE',
        'input': str(IN),
        'out': str(OUT),
        'production_write': False,
        'base_metrics': metrics(edf),
        'zone_close_dead_n': int(len(zedf)),
        'kline_missing_rows': int(edf['kline_missing'].sum()),
        'top_failure_tags': tag_counts.head(10).to_dict(orient='records'),
        'best_gate_table_head': gdf.to_dict(orient='records'),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    md = []
    md.append('# V140 ZONE_CLOSE_DEAD_T1 K线语义复盘（只读）')
    md.append('')
    md.append(f"Decision: `{summary['decision']}`。读取 V138 executable shadow + 本地K线缓存；只写 audit 目录，未改生产/API/frontend/watchlist/TP/SL。")
    md.append('')
    md.append('## 1. 当前基线')
    md.append(pd.DataFrame([metrics(edf)]).to_markdown(index=False))
    md.append('')
    md.append('## 2. ZONE_CLOSE_DEAD 失败标签')
    md.append(tag_counts.to_markdown(index=False))
    md.append('')
    md.append('## 3. 预入场可见门禁敏感性')
    md.append(gdf.to_markdown(index=False))
    md.append('')
    md.append('## 4. 胜负K线字段对比')
    md.append(cmpdf.to_markdown(index=False))
    md.append('')
    md.append('## 5. 结论')
    md.append('- ZONE_CLOSE_DEAD 不是单一 TP/SL 问题，而是入场当日/次日对 zone 的语义失守。')
    md.append('- 可见前兆要区分两类：追高跳空/站得太高，与入场当日已经跌回 zone 下方。')
    md.append('- 如果某门禁提升 WR 但大幅缩样本或 recent 失真，只能保留为研究门禁，不能接生产。')
    (OUT / 'report.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
