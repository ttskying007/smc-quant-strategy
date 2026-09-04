# V25 Field Migration Guide

When migrating the SMC frontend (smc_unified.py) from V19/V24 to V25 state_backtest data,
comprehensive field name updates are required across all pages.

## Complete Field Mapping

| V19/V24 Field | V25 Field | Pages Affected |
|--------------|-----------|----------------|
| `regime` | `market_state` | Dashboard, Backtest, Analysis, Autopsy |
| `ctx_score` / `context_score` | `zone_type` | Dashboard, Analysis, Autopsy |
| `sl_initial` | `sl_pct` | Backtest (avg SL), Analysis |
| `sl` (in exit Counter) | `SL_hit` | Analysis (止损计数) |
| `engine` | NOT PRESENT | Dashboard (replaced by market_state grouping) |
| `autopsy_*` / `v19_*` | NOT PRESENT | Autopsy (must be completely rewritten) |
| `tp_tiers` (string/descriptive) | `tp_price`, `tp_pct` | Multiple |
| `gap_up` / `gap_down` exit | `TP_hit` / `SL_hit` / `trailing` | Backtest exit_names |

## Page-by-Page Fix Summary

### Dashboard (build_dashboard)
- Per-engine breakdown: `t.get('engine')` → `t.get('market_state')` grouping
- Context analysis: `t.get('context_score')` → `t.get('zone_type')`
- Picks table: `p.get('engine')` → `p.get('zone_type')`, `p.get('ctx_score')` → `p.get('v253_quality')`
- Title: "V19选股" → "V25选股"

### Backtest (build_backtest)
- Exit names: add 'SL_hit', 'TP_hit', 'TP1', 'TP2'
- avg_sl: `t.get('sl_initial')` → `t.get('sl_pct')`
- Trade regime display: `t.get('regime')` → `t.get('market_state')`
- Title: "V24 回测" → "V25 回测"

### Analysis (build_analysis)
- Context stats: `t.get('ctx_score')` → `t.get('zone_type')`
- Exit counter: `exits.get('sl')` → `exits.get('SL_hit')`
- SL threshold: `sl_pct > 3` → `sl_pct > 30` (V25 has 41% SL rate)
- Regime analysis: `t.get('regime')=='HIGH_VOLATILITY'` → state loop over `market_state`
- Per-state params: `t.get('sl_initial')` → `t.get('sl_pct')`, use `rr` field
- Title: "V19 引擎" → "V25 引擎"

### Autopsy (build_autopsy)
- Complete rewrite: old code checked for `autopsy_overall`/`v19_overall` fields
- New: native V25 analysis with zone_type, conf_type, market_state breakdowns
- Auto-fix: SL_hit > 40% → HIGH, WR < 60% → HIGH, avg_pnl < 1% → MED
- Title: "V24 交易统计" → "V25 逐笔交易复盘诊断"

## RR Calculation Fix

Old: `rr = avg_pnl / avg_sl` (wrong — divides mean PnL by mean SL percentage)
New: `rr = avg_win / abs(avg_loss)` (correct — ratio of average winner to average loser)

For V25.5: 4.01 / 3.17 = 1.26x

## Autopsy Page Datapoints

Old autopsy showed:
- 引擎: ? (engine field missing)
- 主市态: ? (regime field missing)
- 诊断待建 (no V18/V19 data)
- Verdicts: empty

New autopsy shows:
- Zone分布: BPR 159笔/69.8%, FVG_Bull 66笔/72.7%, IFVG 42笔/57.1%
- 入场确认: CHOCH_ENTRY, ZONE_RETRACE, OTE_ENTRY, etc.
- 市场状态: TREND_DOWN, TREND_UP, HIGH_VOL (all from market_state)
- 出场方式: TP_hit 114, SL_hit 124, trailing 55, timeout 7
- 最差10笔交易 with real PnL/exit_reason/zone/hold_bars
- 自动诊断: auto-fix based on actual SL rate, WR, avg PnL
