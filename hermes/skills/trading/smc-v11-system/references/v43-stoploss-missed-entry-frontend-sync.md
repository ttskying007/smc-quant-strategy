# V43 stop-loss / missed-entry review workflow (2026-05)

Use this reference when debugging SMC versions after the user reports excessive stop-losses, suspicious missed entries, or frontend/backend mismatch.

## Main objective guardrail

Do **not** drift into broad WR/RR optimization. The user’s target is structural correctness:

1. Is the SMC signal definition wrong?
2. Is the entry point wrong or too strict?
3. Is the signal combination/order wrong?
4. Did price never reach the intended entry level?
5. Did frontend render stale or mismatched data?

Keep the work centered on those questions until verified.

## Required review sequence

1. **Freeze active baseline**
   - Capture active version, trade count, WR, SL rate, avg PnL, picks count.
   - Do not switch frontend version before candidate acceptance.

2. **Classify stop losses and missed entries separately**
   - Stop-loss autopsy: group losers by `zone_type`, `source_event`, `conf_type`, `entry_mode`, `market_state`, `exit_reason`.
   - Missed opportunity autopsy: group high-MFE missed structures by reason, especially:
     - `FVG_SETUP_PASSED_NOT_TRADED`
     - `SETUP_PASSED_NOT_TRADED`
     - `NO_RETRACE + FVG_NO_RETRACE`
     - `NO_PREV_SWEEP`

3. **Diagnose setup-passed-but-not-traded paths**
   Attribute each missed setup to a concrete code gate, not a vague label:
   - `ENTRY_OUTSIDE_ZONE_LIMIT`
   - `ENTRY_LIMIT_RETOUCH_FAILED`
   - `ZONE_TOO_WIDE`
   - `MARKET_STATE_FAIL`
   - `FVG_NOT_RANGE`
   - `CONFIRM_TOO_LATE`
   - `QUALITY_FAIL_ON_REPLAY`
   - `START_DATE_FILTERED`

4. **Only then design candidates**
   - FVG repair: handle true setup-passed path leaks and controlled continuation after displacement.
   - NO_RETRACE: require a second-stage filter; never broadly enable no-retrace entries.
   - NO_PREV_SWEEP: test alternative liquidity proxies, but keep them separately labeled from SSL sweep.

5. **Acceptance before promotion**
   A candidate may only become active if it improves the baseline without breaking quality gates. Minimum gates used in this session:
   - trade count must exceed baseline
   - WR must remain high enough for the active system
   - SL rate must not increase materially
   - avg PnL and total PnL must beat baseline
   - capital efficiency (`PnL / 10 holding days`) must not degrade

## Frontend synchronization checklist

Do not claim frontend sync is solved until all of these are verified with live endpoints:

1. `/api/summary` returns the intended active version’s count/WR/avg/signals.
2. `/api/picks` reflects the same active pick file and current entry fields.
3. `/api/kline_full?symbol=<pick>&tf=daily&ver=<active>` returns:
   - non-empty `klines`
   - expected `trade_count`
   - expected `trades` for that symbol
   - expected highlight/marker chain.
4. If data files were regenerated while the server was already running, ensure memory cache invalidation catches file mtime; otherwise restart/prewarm the server.
5. Do **not** add V43 to `ACTIVE_VERSION` selection or frontend version maps until V43 acceptance passes.

## Important pitfall from this session

A local engine edit can overwrite `/root/.hermes/smc_opt_v41/*` while still being experimental. If the candidate is not accepted, preserve or restore the prior baseline before treating frontend numbers as production. Otherwise the frontend may appear synchronized while actually serving experimental V41-shaped data.

## Reporting format for this user

The user asked to “不要偏离主要任务目标”. For this class of task, report in this shape:

- “前端同步是否解决”：已解决 / 未解决 / 部分解决, with endpoint evidence.
- “已确认问题”：only verified findings.
- “方案”：specific code/data path changes, not generic ideas.
- “测试验证方法”：exact gates and endpoints.
- “下一步”：only task-relevant actions; no broad version/metric optimization detours.
