# V54–V62 continuation/reentry/full-market gating lessons

## Trigger
Use this reference when iterating the SMC full-market engine after V53, especially when the user asks about:
- 结构止损卖早 / 90D MFE 捕获不足
- continuation / reentry setup recognition
- PRIMARY_SETUP 降级或剔除
- 假突破 / 失败回踩二次门禁
- 前端 active version / rerun route not supporting the current version

## Durable lessons

### 1. Do not fix SOLD_EARLY by globally delaying structure exits
V61 tested broad runner extension after V60 structure exits. It looked intuitive because V60 had many `SOLD_EARLY_BY_STRUCTURE_STOP`, but full validation showed it reduced system quality:
- V60 baseline: 4450 trades, WR 65.69%, avgPnL 11.696%, avgR 2.833, avg90dCapture 0.276.
- V61 exit-layer repair: 4318 trades, WR 64.36%, avgPnL 11.582%, avgR 2.811, avg90dCapture 0.262.

Conclusion: delayed exit is only locally useful for a small REENTRY subset; as a general fix it turns valid structure failure into worse holds. For future versions, only extend exits after bucket-level A/B proof; default should be pre-entry false-break filtering.

### 2. PRIMARY_SETUP is not a main production source after full-market scaling
V59/V60 proved that direct PRIMARY setups drag the full-market system:
- V60 PRIMARY_SETUP: 788 trades, WR 54.57%, avgPnL 8.08%.
- V60 CONTINUATION_SETUP: 2335 trades, WR 68.95%, avgPnL 13.014%.
- V60 REENTRY_SETUP: 1327 trades, WR 66.54%, avgPnL 11.524%.

V62 demoted PRIMARY_SETUP to watch-only. Treat PRIMARY as candidate context unless a future version proves an extremely narrow, audited subgroup.

### 3. False-break / failed-retest gate is the right next layer for win-rate improvement
V62 improved over V60 by rejecting noise before entry rather than extending exits:
- V62 source: V60 trades.
- Rules: PRIMARY watch-only; CONTINUATION excludes `LiquidityVoid_Bull`, requires BQ>=50, no fast return to range, retest holds raw zone, no 1–3 bar reclaim; REENTRY same but BQ>=55.
- Result: 1408 trades, WR 68.18%, avgPnL 12.089%, avgR 3.036, avg90dCapture 0.297.

Main rejected buckets: `PRIMARY_WATCH_ONLY_V62`, `LV_FALSE_BREAK_RISK`, `*_FAST_RETURN_TO_RANGE`, low BQ, reclaim. This is a durable diagnostic sequence for future win-rate work.

### 4. Continuation and reentry need different thresholds
In V62, continuation passed 70% WR while reentry lagged:
- CONTINUATION_SETUP: 854 trades, WR 70.26%, avgPnL 13.124%.
- REENTRY_SETUP: 554 trades, WR 64.98%, avgPnL 10.492%.

Do not use one threshold for both. Future win-rate improvement should focus on REENTRY: require stronger post-exit confirmation, cooldown, new BOS/CHOCH/MSS after exit, trend_score>=4, and/or higher BQ.

### 5. Every promoted version must update rerun/version plumbing
When adding V61/V62-style versions, update all version dispatch paths, not only output files:
- `ACTIVE_VERSION`
- `ACTIVE_TRADE_FILE` / `ACTIVE_PICK_FILE`
- version directory constants (`V61_DIR`, `V62_DIR`, ...)
- `get_version_trades(version)`
- `get_version_picks(version)`
- `_active_version_paths(version)` for rerun support
- frontend version selector
- `/api/kline_full?ver=...`, `/api/summary`, `/api/picks`, `/api/autopsy/closed-loop`, `/backtest`

Failure mode observed: frontend displayed `失败: 当前版本暂不支持重跑，ACTIVE_VERSION=V61`. Fix by registering the current active version in `_active_version_paths` and any rerun mapping.

## Verification checklist
For V60+ versions, do not report completion until all are run:
1. Full engine run on 4905-symbol/V50 signal snapshot-derived source.
2. Quality metrics: no small wins <2%, no win RR<2, no loss inside 1% noise, no hold >90.
3. Provenance audit: fatal_count = 0.
4. Signal sequence audit: violation_count = 0.
5. Sample-bias audit: no bias flags.
6. Closed-loop 90D review: compare WR, avgPnL, avgR, avg90dCapture and issue counts vs prior production.
7. Release gate pass.
8. Frontend sync: summary, picks, backtest, kline, autopsy, and rerun route support current ACTIVE_VERSION.

## Pitfall
Do not claim a new version is better just because release gate passes. V61 passed release gate but was inferior to V60. Compare against prior production across WR, avgPnL, avgR, avg90dCapture, trade count, and issue counts before promoting.
