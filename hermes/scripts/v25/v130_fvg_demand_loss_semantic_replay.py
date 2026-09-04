#!/usr/bin/env python3
"""V130 read-only semantic replay for scanner-layer FVG_Demand losses.

Scope: V128 independent scanner shadow rows only. No production writes, no TP/SL tuning.
Questions:
- Are risk_pct > 3 / >5 / >8 losses essentially chase entries?
- Are wide zones invalid/low-quality zones?
- Does entry_chase_above_zone_pct cause buying too high after reclaim?
- Are RECOVERY FVG rows fake recoveries?
- What separates BEAR_RISK/MIXED winners from losers?
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

SRC = Path('/root/.hermes/smc_audit/v128_parallel_scanner_candidate_audit_20260620/v128_parallel_shadow_backtest_all.csv')
RECENT_SRC = Path('/root/.hermes/smc_audit/v128_parallel_scanner_candidate_audit_20260620/v128_parallel_shadow_recent45.csv')
KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_audit/v130_fvg_demand_loss_semantic_replay_20260620')
OUT.mkdir(parents=True, exist_ok=True)


def pct(a: float, b: float) -> float:
    if b in (0, None) or pd.isna(b) or pd.isna(a):
        return float('nan')
    return (a / b - 1.0) * 100.0


def symbol_to_cache(symbol: str) -> Path:
    code, ex = symbol.split('.')
    return KLINE_DIR / f'{code}_{ex}_daily_750.json'


def load_bars(symbol: str):
    p = symbol_to_cache(symbol)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def bar_val(b, k):
    return float(b.get(k, float('nan')))


def enrich_row(row, bars):
    n = len(bars) if bars else 0
    out = {}
    if not bars or n == 0:
        out['kline_missing'] = True
        return out
    out['kline_missing'] = False
    entry = int(row.entry_idx)
    touch = int(row.touch_idx)
    reclaim = int(row.reclaim_idx)
    event = int(row.event_idx)
    zl = float(row.zone_low)
    zh = float(row.zone_high)
    ep = float(row.entry_price)

    def safe_bar(i):
        return bars[i] if 0 <= i < n else None

    tb = safe_bar(touch)
    rb = safe_bar(reclaim)
    eb = safe_bar(entry)
    evb = safe_bar(event)

    pre = bars[max(0, touch): min(n, entry)]
    out['pre_entry_close_below_zone_count'] = sum(1 for b in pre if bar_val(b, 'c') < zl)
    out['pre_entry_low_below_zone_count'] = sum(1 for b in pre if bar_val(b, 'l') < zl)
    out['zone_dead_before_entry'] = out['pre_entry_close_below_zone_count'] > 0
    out['zone_pierced_before_entry'] = out['pre_entry_low_below_zone_count'] > 0

    out['entry_above_zone_high_pct'] = pct(ep, zh)
    out['entry_above_zone_mid_pct'] = pct(ep, (zl + zh) / 2.0)
    out['entry_gap_from_reclaim_close_pct'] = pct(ep, bar_val(rb, 'c')) if rb else float('nan')
    out['reclaim_close_above_event_close_pct'] = pct(bar_val(rb, 'c'), bar_val(evb, 'c')) if rb and evb else float('nan')

    # pre-event trend / recovery sanity: negative pre60 + shallow event/reclaim often fake recovery.
    for win in (10, 20, 60):
        start = event - win
        if start >= 0 and evb:
            out[f'pre{win}_ret_pct'] = pct(bar_val(evb, 'c'), bar_val(bars[start], 'c'))
        else:
            out[f'pre{win}_ret_pct'] = float('nan')

    # post-entry path, not used as gate; diagnostic only.
    for win in (3, 5, 10, 20):
        post = bars[entry:min(n, entry + win + 1)]
        if eb and post:
            max_h = max(bar_val(b, 'h') for b in post)
            min_l = min(bar_val(b, 'l') for b in post)
            out[f'mfe_{win}_pct'] = pct(max_h, ep)
            out[f'mae_{win}_pct'] = pct(min_l, ep)
            out[f'close_ret_{win}_pct'] = pct(bar_val(post[-1], 'c'), ep)
        else:
            out[f'mfe_{win}_pct'] = float('nan')
            out[f'mae_{win}_pct'] = float('nan')
            out[f'close_ret_{win}_pct'] = float('nan')

    return out


def metrics(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return {'n': 0, 'wr': 0, 'avg': 0, 'loss_rate': 0, 'hard_exit_rate': 0}
    hard = df['exit_reason'].astype(str).str.contains('SL|DAMAGE|ZONE_DEAD|STRUCTURE', case=False, regex=True, na=False)
    return {
        'n': int(len(df)),
        'wr': round(float((df['pnl_pct'] > 0).mean() * 100), 2),
        'avg': round(float(df['pnl_pct'].mean()), 4),
        'loss_rate': round(float((df['pnl_pct'] <= 0).mean() * 100), 2),
        'hard_exit_rate': round(float(hard.mean() * 100), 2),
    }


def bucket_table(df: pd.DataFrame, field: str, bins, labels):
    tmp = df.copy()
    tmp['_bucket'] = pd.cut(tmp[field], bins=bins, labels=labels, include_lowest=True, right=True)
    rows = []
    for b, g in tmp.groupby('_bucket', observed=False):
        m = metrics(g)
        m['bucket'] = str(b)
        # diagnostics for losses in this bucket
        loss = g[g.pnl_pct <= 0]
        m['loss_n'] = int(len(loss))
        m['loss_chase_median'] = round(float(loss['entry_chase_above_zone_pct'].median()), 4) if len(loss) else 0
        m['loss_zone_dead_pct'] = round(float(loss['zone_dead_before_entry'].mean() * 100), 2) if len(loss) else 0
        rows.append(m)
    return rows


def compare_wl(df: pd.DataFrame, fields):
    rows = []
    winners = df[df.pnl_pct > 0]
    losers = df[df.pnl_pct <= 0]
    for f in fields:
        rows.append({
            'field': f,
            'winner_median': round(float(winners[f].median()), 4) if len(winners) else 0,
            'loser_median': round(float(losers[f].median()), 4) if len(losers) else 0,
            'winner_mean': round(float(winners[f].mean()), 4) if len(winners) else 0,
            'loser_mean': round(float(losers[f].mean()), 4) if len(losers) else 0,
        })
    return rows


def tag_loss(row) -> str:
    tags = []
    if row.risk_pct > 8:
        tags.append('RISK_GT8')
    elif row.risk_pct > 5:
        tags.append('RISK_GT5')
    elif row.risk_pct > 3:
        tags.append('RISK_GT3')
    if row.entry_chase_above_zone_pct > 8:
        tags.append('CHASE_GT8')
    elif row.entry_chase_above_zone_pct > 5:
        tags.append('CHASE_GT5')
    elif row.entry_chase_above_zone_pct > 3:
        tags.append('CHASE_GT3')
    if row.v85_zone_width_pct > 5:
        tags.append('WIDTH_GT5')
    elif row.v85_zone_width_pct > 3:
        tags.append('WIDTH_GT3')
    if bool(row.zone_dead_before_entry):
        tags.append('ZONE_DEAD_PRE_ENTRY')
    if str(row.market_state) == 'RECOVERY':
        tags.append('RECOVERY')
    if str(row.combo_family) == 'CONTINUATION':
        tags.append('CONTINUATION')
    if row.source_gap_atr < 0.8:
        tags.append('WEAK_GAP')
    if row.source_mid_body_atr < 0.65:
        tags.append('WEAK_MID')
    if row.reclaim_close_above_zone_pct < 0.5:
        tags.append('WEAK_RECLAIM')
    return '|'.join(tags) if tags else 'UNCLASSIFIED'


def md_table(rows, cols):
    if not rows:
        return '(empty)'
    s = '| ' + ' | '.join(cols) + ' |\n'
    s += '| ' + ' | '.join(['---'] * len(cols)) + ' |\n'
    for r in rows:
        s += '| ' + ' | '.join(str(r.get(c, '')) for c in cols) + ' |\n'
    return s


def main():
    df = pd.read_csv(SRC)
    recent_df = pd.read_csv(RECENT_SRC)
    recent_keys = set(
        zip(
            recent_df['symbol'].astype(str),
            recent_df['entry_date'].astype(int),
            recent_df['poi_source'].astype(str),
        )
    )
    fvg = df[(df.poi_source == 'FVG_Demand') & (df.valid_backtest == True)].copy()
    fvg = fvg.sort_values(['entry_date', 'symbol']).reset_index(drop=True)

    enriched = []
    cache = {}
    for row in fvg.itertuples(index=False):
        bars = cache.get(row.symbol)
        if row.symbol not in cache:
            bars = load_bars(row.symbol)
            cache[row.symbol] = bars
        enriched.append(enrich_row(row, bars))
    edf = pd.concat([fvg, pd.DataFrame(enriched)], axis=1)
    edf['is_recent45'] = [
        (str(r.symbol), int(r.entry_date), str(r.poi_source)) in recent_keys
        for r in edf.itertuples(index=False)
    ]
    edf['loss_tag'] = edf.apply(lambda r: tag_loss(r) if r.pnl_pct <= 0 else 'WIN', axis=1)

    all_loss = edf[edf.pnl_pct <= 0].copy()
    recent = edf[edf.is_recent45].copy()
    recent_loss = recent[recent.pnl_pct <= 0].copy()

    summary = {
        'decision': 'V130_FVG_DEMAND_LOSS_SEMANTIC_REPLAY_DONE_NO_PRODUCTION_CHANGE',
        'source': str(SRC),
        'base': metrics(edf),
        'recent45': metrics(recent),
        'loss_count': int(len(all_loss)),
        'recent45_loss_count': int(len(recent_loss)),
        'kline_missing_rows': int(edf['kline_missing'].sum()),
        'risk_buckets': bucket_table(edf, 'risk_pct', [-math.inf, 1, 3, 5, 8, math.inf], ['<=1','1-3','3-5','5-8','>8']),
        'width_buckets': bucket_table(edf, 'v85_zone_width_pct', [-math.inf,1.2,2.2,3,5,math.inf], ['<=1.2','1.2-2.2','2.2-3','3-5','>5']),
        'chase_buckets': bucket_table(edf, 'entry_chase_above_zone_pct', [-math.inf,0,1,3,5,8,math.inf], ['<=0','0-1','1-3','3-5','5-8','>8']),
        'market_state': [],
        'combo_family': [],
        'bear_mixed_wl_compare': compare_wl(edf[edf.market_state.isin(['BEAR_RISK','MIXED'])], [
            'risk_pct','v85_zone_width_pct','entry_chase_above_zone_pct','entry_above_zone_high_pct',
            'source_mid_body_atr','source_gap_atr','reclaim_close_above_zone_pct','touch_to_reclaim_bars',
            'pre20_ret_pct','pre60_ret_pct','mfe_5_pct','mae_5_pct'
        ]),
        'recovery_wl_compare': compare_wl(edf[edf.market_state == 'RECOVERY'], [
            'risk_pct','v85_zone_width_pct','entry_chase_above_zone_pct','entry_above_zone_high_pct',
            'source_mid_body_atr','source_gap_atr','reclaim_close_above_zone_pct','pre20_ret_pct','pre60_ret_pct','mfe_5_pct','mae_5_pct'
        ]),
        'loss_tag_top': [],
    }

    for name, g in edf.groupby('market_state'):
        m = metrics(g); m['market_state'] = name; m['recent45'] = metrics(g[g.is_recent45]); summary['market_state'].append(m)
    for name, g in edf.groupby('combo_family'):
        m = metrics(g); m['combo_family'] = name; m['recent45'] = metrics(g[g.is_recent45]); summary['combo_family'].append(m)

    tag_counts = Counter()
    for tag in all_loss['loss_tag']:
        for part in str(tag).split('|'):
            tag_counts[part] += 1
    summary['loss_tag_top'] = [{'tag': k, 'loss_n': int(v), 'loss_pct': round(v / len(all_loss) * 100, 2)} for k, v in tag_counts.most_common(20)]

    # Detailed loss rows: worst 1000 and all recent losses.
    detail_cols = [
        'symbol','entry_date','market_state','combo_family','pnl_pct','exit_reason','risk_pct','v85_zone_width_pct',
        'entry_chase_above_zone_pct','entry_above_zone_high_pct','entry_gap_from_reclaim_close_pct','zone_dead_before_entry',
        'source_mid_body_atr','source_gap_atr','reclaim_close_above_zone_pct','touch_to_reclaim_bars','pre20_ret_pct','pre60_ret_pct',
        'mfe_5_pct','mae_5_pct','loss_tag','event_date','zone_low','zone_high','entry_price'
    ]
    all_loss.sort_values('pnl_pct').head(1000)[detail_cols].to_csv(OUT / 'worst_1000_fvg_losses_semantic.csv', index=False)
    recent_loss.sort_values('pnl_pct')[detail_cols].to_csv(OUT / 'recent45_fvg_losses_semantic.csv', index=False)
    edf.to_csv(OUT / 'fvg_demand_semantic_enriched_all.csv', index=False)
    pd.DataFrame(summary['bear_mixed_wl_compare']).to_csv(OUT / 'bear_mixed_winner_loser_compare.csv', index=False)
    pd.DataFrame(summary['recovery_wl_compare']).to_csv(OUT / 'recovery_winner_loser_compare.csv', index=False)

    # Focused cross checks for the user questions.
    high_risk_loss = all_loss[all_loss.risk_pct > 3]
    high_chase_loss = all_loss[all_loss.entry_chase_above_zone_pct > 3]
    wide_loss = all_loss[all_loss.v85_zone_width_pct > 3]
    recovery = edf[edf.market_state == 'RECOVERY']
    bear_mixed = edf[edf.market_state.isin(['BEAR_RISK','MIXED'])]
    summary['question_checks'] = {
        'risk_gt3_loss_n': int(len(high_risk_loss)),
        'risk_gt3_loss_chase_gt3_pct': round(float((high_risk_loss.entry_chase_above_zone_pct > 3).mean() * 100), 2) if len(high_risk_loss) else 0,
        'risk_gt3_loss_chase_gt5_pct': round(float((high_risk_loss.entry_chase_above_zone_pct > 5).mean() * 100), 2) if len(high_risk_loss) else 0,
        'risk_gt3_loss_entry_above_zone_high_median': round(float(high_risk_loss.entry_above_zone_high_pct.median()), 4) if len(high_risk_loss) else 0,
        'wide_zone_gt3_loss_n': int(len(wide_loss)),
        'wide_zone_gt3_zone_dead_pct': round(float(wide_loss.zone_dead_before_entry.mean() * 100), 2) if len(wide_loss) else 0,
        'chase_gt3_loss_n': int(len(high_chase_loss)),
        'chase_gt3_loss_mfe5_median': round(float(high_chase_loss.mfe_5_pct.median()), 4) if len(high_chase_loss) else 0,
        'chase_gt3_loss_mae5_median': round(float(high_chase_loss.mae_5_pct.median()), 4) if len(high_chase_loss) else 0,
        'recovery': metrics(recovery),
        'recovery_recent45': metrics(recovery[recovery.is_recent45]),
        'bear_mixed': metrics(bear_mixed),
        'bear_mixed_recent45': metrics(bear_mixed[bear_mixed.is_recent45]),
    }

    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    report = []
    report.append('# V130 FVG_Demand亏损逐笔语义复盘（只读）\n')
    report.append(f"Decision: `{summary['decision']}`\n")
    report.append('## 1. 基础样本\n')
    report.append(md_table([
        {'slice':'FVG_Demand all', **summary['base']},
        {'slice':'FVG_Demand recent45', **summary['recent45']},
    ], ['slice','n','wr','avg','loss_rate','hard_exit_rate']))
    report.append('\n## 2. 风险/宽度/追高桶\n')
    report.append('### risk_pct\n' + md_table(summary['risk_buckets'], ['bucket','n','wr','avg','loss_rate','hard_exit_rate','loss_n','loss_chase_median','loss_zone_dead_pct']))
    report.append('\n### zone_width\n' + md_table(summary['width_buckets'], ['bucket','n','wr','avg','loss_rate','hard_exit_rate','loss_n','loss_chase_median','loss_zone_dead_pct']))
    report.append('\n### entry_chase_above_zone_pct\n' + md_table(summary['chase_buckets'], ['bucket','n','wr','avg','loss_rate','hard_exit_rate','loss_n','loss_chase_median','loss_zone_dead_pct']))
    report.append('\n## 3. market_state / family\n')
    report.append('### market_state\n' + md_table(summary['market_state'], ['market_state','n','wr','avg','loss_rate','hard_exit_rate','recent45']))
    report.append('\n### combo_family\n' + md_table(summary['combo_family'], ['combo_family','n','wr','avg','loss_rate','hard_exit_rate','recent45']))
    report.append('\n## 4. BEAR_RISK/MIXED赢家 vs 输家\n')
    report.append(md_table(summary['bear_mixed_wl_compare'], ['field','winner_median','loser_median','winner_mean','loser_mean']))
    report.append('\n## 5. RECOVERY赢家 vs 输家\n')
    report.append(md_table(summary['recovery_wl_compare'], ['field','winner_median','loser_median','winner_mean','loser_mean']))
    report.append('\n## 6. 亏损标签Top\n')
    report.append(md_table(summary['loss_tag_top'][:15], ['tag','loss_n','loss_pct']))
    report.append('\n## 7. 直接回答\n')
    q = summary['question_checks']
    direct = [
        {'question':'risk_pct>3亏损是否追高', 'answer':f"loss_n={q['risk_gt3_loss_n']}; chase>3占{q['risk_gt3_loss_chase_gt3_pct']}%; chase>5占{q['risk_gt3_loss_chase_gt5_pct']}%; entry高于zone_high中位{q['risk_gt3_loss_entry_above_zone_high_median']}%"},
        {'question':'zone_width大是否无效宽区', 'answer':f"width>3亏损n={q['wide_zone_gt3_loss_n']}; 入场前close跌破zone_low占{q['wide_zone_gt3_zone_dead_pct']}%，宽区本身不是唯一死因，但和高risk/追高叠加"},
        {'question':'entry_chase是否导致买高', 'answer':f"chase>3亏损n={q['chase_gt3_loss_n']}; 亏损行5日MFE中位{q['chase_gt3_loss_mfe5_median']}%，5日MAE中位{q['chase_gt3_loss_mae5_median']}%，说明买高后仍有少量上冲但下行风险更大"},
        {'question':'RECOVERY是否假恢复', 'answer':f"RECOVERY all n={q['recovery']['n']} WR={q['recovery']['wr']} Loss={q['recovery']['loss_rate']}; recent45 n={q['recovery_recent45']['n']} WR={q['recovery_recent45']['wr']} Loss={q['recovery_recent45']['loss_rate']}，是主要污染状态"},
        {'question':'BEAR_RISK/MIXED赢家输家差异', 'answer':f"BEAR_RISK/MIXED all n={q['bear_mixed']['n']} WR={q['bear_mixed']['wr']} Loss={q['bear_mixed']['loss_rate']}; recent45 n={q['bear_mixed_recent45']['n']} WR={q['bear_mixed_recent45']['wr']} Loss={q['bear_mixed_recent45']['loss_rate']}；赢家更依赖低risk/低chase/更强短期MFE，单靠state不够"},
    ]
    report.append(md_table(direct, ['question','answer']))
    report.append('\n## 8. 产物\n')
    report.append('- `summary.json`\n- `fvg_demand_semantic_enriched_all.csv`\n- `worst_1000_fvg_losses_semantic.csv`\n- `recent45_fvg_losses_semantic.csv`\n- `bear_mixed_winner_loser_compare.csv`\n- `recovery_winner_loser_compare.csv`\n')
    report.append('\n## 9. 结论\n')
    report.append('V130 confirms the bottleneck is entry geometry and state semantics, not POI supply quantity. Do not loosen V125 or promote FVG_Demand. Next work should rebuild scanner FVG entry execution: reject/penalize high chase after reclaim, split RECOVERY false-recovery, and replay BEAR_RISK/MIXED losses at candle level before any contract promotion.\n')
    (OUT / 'report.md').write_text('\n'.join(report))
    print(json.dumps({'out': str(OUT), 'decision': summary['decision'], 'base': summary['base'], 'recent45': summary['recent45'], 'question_checks': summary['question_checks']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
