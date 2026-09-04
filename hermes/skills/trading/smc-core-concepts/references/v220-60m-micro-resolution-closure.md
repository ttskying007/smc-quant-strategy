# V220 Baostock 60m micro-resolution closure

Date: 2026-06-27

## Trigger
Use when continuing post-V185/V211 research and considering whether the V200 near-frontier 60min execution variant can be made production-safe by reducing micro-profit pollution.

## Artifacts
- Script: `/tmp/v220_60m_micro_resolution.py` (temporary research script, no production writes)
- Output: `/root/.hermes/smc_audit/v220_baostock_60m_micro_resolution_20260627_023951/`
- Cache: `/root/.hermes/smc_audit/baostock_60m_cache_v220/`

## Scope and gates
Source: V175 trades (`/root/.hermes/smc_opt_v175_semantic_split/v175_trades.json`), because V185 lower-WR/loss component is V175-style rows.

Production intraday upgrade gate:
- `n >= 247`
- `min_year_n >= 38`
- `WR >= 84%`
- `AvgPnL >= 6.2%`
- `all_year_WR_min >= 82%`
- `micro_profit_pct <= 1%`
- T+1 violations = 0

All V220 variants are shadow/audit only: `production_write=false`, `frontend_write=false`, `watchlist_write=false`.

## Result
Decision: `V220_INTRADAY_MICRO_RESOLUTION_NO_PRODUCTION_PASS__NO_WRITE`.

Fetch coverage: `247/247` V175 rows from Baostock 60min, T+1 violations `0` for all reported near-frontier variants.

No variant passed all production gates (`pass_count=0`).

## Main frontier findings

High Avg variants fail WR/year stability:
- `rr3.0_h20_sl`: WR `72.47%`, Avg `7.963%`, yearMin `63.16%`, micro `2.43%`.
- `rr3.0_h15_sl`: WR `73.68%`, Avg `7.8933%`, yearMin `63.16%`, micro `2.43%`.

High WR/Avg/year variants fail only micro:
- `rr3.0_h20_lock2p0_trig1p0`: WR `88.26%`, Avg `7.3654%`, yearMin `85.11%`, micro `2.02%`.
- `rr2.2_h20_lock2p0_trig1p0`: WR `88.26%`, Avg `6.3062%`, yearMin `85.11%`, micro `1.62%`.

Micro-safe variants fail yearly stability:
- `rr2.2_h20_lock1p5_trig1p2`: WR `85.43%`, Avg `6.5724%`, yearMin `78.95%`, micro `0.81%`.
- `rr2.2_h20_lock2p0_trig1p2`: WR `85.43%`, Avg `6.5252%`, yearMin `78.95%`, micro `0.81%`.

Closest deficit variants were still not promotable; the bottleneck is a hard tradeoff between BE/lock micro-profit pollution and 2026/year stability.

## Root cause details

For `rr2.2_h20_lock2p0_trig1p0` (near year-pass but micro-fail):
- Metrics: WR `88.26%`, Avg `6.3062%`, yearMin `85.11%`, micro `1.62%`.
- Micro rows (`0<pnl<=1`) were only 4/247:
  - `002368.SZ 20260610` GAP_BE_SL `+0.6435%`
  - `603599.SH 20250423` GAP_BE_SL `+0.5493%`
  - `300696.SZ 20250422` GAP_BE_SL `+0.4845%`
  - `688489.SH 20250410` TIME close `+0.3746%`
- Removing micro by raising/altering lock turns some protected winners into 2026 losers and breaks year stability.

For `rr2.2_h20_lock1p5_trig1p2` (micro-pass but year-fail):
- Metrics: WR `85.43%`, Avg `6.5724%`, yearMin `78.95%`, micro `0.81%`.
- 2026 losses include `688327.SH`, `002401.SZ`, `603638.SH`, `603161.SH`, `000630.SZ`, `300565.SZ`, `000591.SZ`, `300029.SZ`; most are SL/GAP_SL/TIME failures on V175 semantic rows.
- This confirms low-WR rows are not fixed by post-entry 60m micro-lock tuning alone.

## Decision
Close the V175 intraday-exit micro-resolution branch for production. It provides a useful near-frontier but no safe gate pass.

Next research must not continue generic 60min exit-grid tuning. If continuing, the next qualitative direction must use entry-before information:
1. intraday candidate-generation features before entry (not exit replay);
2. sector/market participation before entry;
3. or production stabilization of V185 active/live guard and cron if no new data layer is available.
