---
name: smc-autonomous-closed-loop
description: Daily autonomous SMC strategy analysis, repair, audit, frontend sync, and promotion workflow. Use when maintaining SMC versions after V65 or when cron runs the daily 00:00 closed-loop job.
version: 1.0.0
---

# SMC Autonomous Closed Loop

## Goal
Run the complete SMC improvement loop without waiting for step-by-step user prompts. Daily scan rows discovered during this loop are not production picks by default: unvalidated sequences must stay `VALIDATION_ONLY` until the same production gate/full-market mechanism audit passes (see `references/daily-scan-production-gate-and-log-timing.md`).

1. Regenerate the active engine output.
2. Run full audits.
3. Inspect failures and regressions.
4. Diagnose by family/zone/confirmation/BQ/trend/exit/90D MFE.
5. Implement the next surgical version only when evidence supports it.
6. Sync frontend active version and rerun support.
7. Verify APIs and pages.
8. Save daily report.

## Daily 00:00 execution

Primary script:

```bash
cd /root/.hermes/scripts/v25
python3 smc_daily_closed_loop.py
```

Hermes cron job should be created with a script path relative to `~/.hermes/scripts/`:

```bash
hermes cron create '0 0 * * *' \
  'Run SMC autonomous closed loop from script output; if release gate fails or metrics regress, diagnose and implement next minimal Vxx repair, audit, sync frontend/rerun support, verify APIs, no user prompts.' \
  --name 'SMC Autonomous Closed Loop V65+' \
  --deliver local \
  --skill smc-autonomous-closed-loop \
  --skill smc-v11-system \
  --script 'v25/smc_daily_closed_loop.py' \
  --workdir '/root/.hermes/scripts'
```

Expected output directory:

```text
/root/.hermes/smc_daily_closed_loop/
```

See `references/daily-rerun-resonance.md` for the rerun API, resonance fallback, and cron path pitfalls discovered during V65 sync.

See `references/daily-closed-loop-timeout-and-v88-report-paths.md` for the V88/V90/V98/V99 operational lesson: a 120s wrapper timeout can be a false failure because daily ops alone can exceed 12 minutes; inspect `smc_monitor/ops_logs/YYYYMMDD.json` and current V88/V99 artifact paths before changing strategy code or creating a next Vxx.

See `references/daily-closed-loop-wrapper-timeout-and-shadow-selectors.md` for the V99/V100/V101 shadow-selector workflow: before treating a timeout as failure, check for still-running children, inspect ops/latest artifacts, rerun with a long timeout, optionally skip V98 only for verification if V98 is the known long pole, and verify real production gates plus API smoke.

See `references/daily-cron-timeout-verification-report-2026-06-19.md` for the V66/V88/V90/V102 operational pattern: a 120s cron timeout can still complete through `smc_daily_ops.py`; do not rerun while the child is alive, then verify `ops_latest.json`, release/completeness gates, and 8890 API smoke before producing the final concise cron report.

See `references/daily-closed-loop-compaction-recovery-and-manual-report.md` for the recovery pattern when context compaction or wrapper timeout leaves no dated closed-loop report: wait for child SMC processes, inspect `ops_logs/YYYYMMDD.json`, regenerate only the cheap active production contract if needed, run API smoke, and synthesize a report that explicitly includes the daily completeness gate.

See `references/cron-compaction-and-missing-report-recovery-2026-06-25.md` for the cron-specific variant: when daily ops completed but the dated closed-loop report is still missing, run the real `smc_daily_closed_loop.py` once as a Hermes-tracked background process, wait/poll, verify final artifacts/smoke/no residual processes, and do not use `--help` as a harmless probe because this wrapper ignores argv and executes the job.

See `references/daily-closed-loop-rerun-active-version-and-refresh-drift.md` for the follow-up safeguard: a real wrapper rerun can regenerate the missing dated report but also overwrite `ops_latest.json` with a second provider-refresh false failure; snapshot/read the first successful ops log, audit actual kline cache using both `date` and `t` bar keys, and do not restart the frontend blindly when the live API serves a newer version than the wrapper's on-disk `ACTIVE_VERSION` detection.

See `references/daily-closed-loop-secondary-refresh-false-failure-2026-06-28.md` for a concrete V185 cron recovery: the first daily ops pass refreshed 4637 latest-date cache files, the report was missing, the real wrapper regenerated it, and a second provider refresh overwrote `ops_latest.json` with `ok=0`; the correct conclusion came from cache audit + API/reselect smoke, not from the final refresh counter alone.

See `references/daily-closed-loop-orphan-wrapper-recovery-2026-06-29.md` for the follow-up cron/compaction recovery pattern: wait out orphan `smc_daily_ops.py`, rerun the real wrapper only if the dated report remains missing, verify actual cache coverage despite secondary refresh `ok=0`, smoke live-guard parity plus `POST /api/reselect {"version":"V185"}`, and confirm no residual child processes before reporting success.

See `references/daily-closed-loop-v185-wrapper-timeout-recovery-2026-06-30.md` for the V185 variant where the orphan daily ops completed, `v185_daily_rematerialize_latest.json` passed, but the dated closed-loop report was missing until the real wrapper was run once. It also records the parity checks across `/api/summary`, `/api/picks`, `/api/resonance`, `/api/live-prices`, `/api/kline_full?...ver=V185`, and `POST /api/reselect {"version":"V185"}`, plus the caveat that `/api/autopsy/closed-loop` may return `{}` because it loads a 90D review artifact rather than the daily report.

See `references/daily-completeness-gate-refresh-truthfulness.md` for the completeness-gate truthfulness rule: distinguish stale/inconsistent refresh counters from genuine under-refresh. If `ok`, latest cache count, and failed ratio genuinely miss thresholds, do not patch around the gate or claim closed-loop completion; report data completeness as failed even if daily ops and shadow selectors exited 0.

See `references/v175-semantic-split-reselect-verification.md` for the V175 semantic/label-only promotion pattern: after changing labels or display semantics, verify top-level APIs, nested DNA/contract fields, `/api/resonance` non-empty signal text, K-line/backtest pages, and `POST /api/reselect {"version":"V175"}` so manual rerun does not silently fall back to an older engine.

See `references/v175-live-guard-picks-sync.md` for the V175 frontend parity lesson: `/api/picks` must apply the same current-price live guard as `/api/live-prices` so stale/recent scanner candidates do not appear buyable after TP hit, SL hit, or >threshold entry drift. Semantic/label-only reports should also expose preserved metrics at top level, not only nested provenance fields.

See `references/v185-cron-timeout-reselect-sync-2026-06-27.md` for the V185 cron recovery and frontend/API sync lesson: a 120s wrapper timeout can still complete once the real wrapper is allowed to run longer; verify dated closed-loop report and V185 artifacts, then smoke `POST /api/reselect {"version":"V185"}`. If reselect fails with `当前版本暂不支持重跑` while summary/report already serve V185, this is an allowed minimal `_api_reselect` field-sync bug: add V185 to `engine_map`, default preference, tuple lists, and report path handling before declaring口径一致.

See `references/v185-picks-live-guard-sl-tp-parity-2026-07-02.md` for the V185 picks/live-prices parity lesson: after missing-report recovery, compare per-symbol `live_guard_status` between `/api/picks` and `/api/live-prices`. If they disagree only because `/api/picks` lacks the same fallback SL/TP derivation (`risk_pct`/`sl_initial_pct`, `tp_tiers`) used by `/api/live-prices`, it is an allowed minimal frontend/API field-sync fix; patch the guard helper, restart 8890, and re-smoke symbol/status parity plus reselect.

See `references/v185-full-wrapper-timeout-and-parity-2026-07-03.md` for the V185 full-wrapper recovery pattern: a 600s foreground call can still time out while the real wrapper is healthy; run it as a Hermes-tracked background process, wait for the final JSON line, then verify fresh dated report, ops logs, rematerialized V185 artifacts, cache coverage, reselect, API smoke, and `/api/picks` vs `/api/live-prices` live-guard parity before reporting success.

See `references/v185-refresh-timeout-rematerialize-pass-2026-07-04.md` for the V185 variant where the wrapper exits `ok=true`/`pass=true` but the embedded `smc_daily_ops.py` has `returncode=1` because `refresh_daily_750.py` hit its 900s subprocess timeout. If V185 rematerialization, gate booleans, actual cache coverage, API smoke, reselect, and `/api/picks` vs `/api/live-prices["picks"]` parity all pass, report success with an explicit refresh-timeout caveat and do not mutate production artifacts or strategy code.

See `references/v185-closed-loop-long-wrapper-full-parity-2026-07-05.md` for the V185 long-wrapper success pattern: keep polling the Hermes-tracked background process until the final JSON appears, then verify fresh dated report, V185 production artifacts, ops/completeness, API reselect, picks/live-prices live-guard parity, resonance context, cache coverage, and no residual child processes before reporting success. If `v185_trades.json` has an older source-material mtime while report/active/picks and all gates are fresh, report it as a caveat rather than mutating strategy or production artifacts.

See `references/v185-successful-rerun-artifact-paths-2026-07-11.md` for the successful full-rerun verification map: V185 artifacts are under `smc_opt_v185_combined_production_candidate`, cache coverage must read either `date` or `t`, and an empty `/api/picks`/`/api/live-prices` pair is valid parity when V185 has zero active production candidates. `/api/autopsy/closed-loop` returning `{}` is only a 90-day-artifact caveat, not a contradiction of the dated daily report.

See `references/v177-executable-exit-replay-boundary.md` for the V177 execution-layer boundary: generic BE/trailing/lock-profit/partial-profit grids on V175 failed to improve production or research gates. Do not overclaim higher WR when AvgPnL falls or micro/BE pollution rises; next work should classify TIME rows by day-by-day R path and use 60min only for genuinely executable intraday tests.

See `references/v178-v179-time-exit-boundary.md` for the follow-up TIME-row boundary: V178 found the main TIME problem is `MID_MFE_0P5_1P2R_GIVEBACK` / `NEAR_TP_OR_LARGE_GIVEBACK`, but V179 proved Tencent 60min only covers recent rows (9/65). Do not claim production/research improvement without historical intraday coverage for 2023-2025; keep `TIME_WINNER_HELD_OK` untouched.

See `references/v167-live-degradation-audit-materiality.md` for the V167 post-close live-degradation audit rule: `live_tradable != active_pick_count` is material and must be reported, but it is not automatically a price-degradation event. Distinguish tradability/context mismatch from actual SL/TP deterioration, and keep the audit read-only unless loss evidence appears.

## Required workflow for each version

### 1. Generate
Run active engine:

```bash
python3 /root/.hermes/scripts/v25/vXX_engine.py
```

### 2. Audit
Run all available scripts:

```bash
python3 vXX_quality_metrics.py
python3 vXX_trade_provenance_audit.py
python3 vXX_signal_sequence_audit.py
python3 vXX_sample_bias_audit.py
python3 vXX_closed_loop_90d_review.py
python3 vXX_t1_audit.py   # if present; A股T+1强制审计
python3 vXX_release_gate.py
```

### 3. Diagnose
Never use aggregate WR alone. Break down by:

- `v59_setup_family`: PRIMARY_SETUP / CONTINUATION_SETUP / REENTRY_SETUP
- `zone_type`: OB_Bull / FVG_Bull / BPR / LV
- `conf_type`: BOS_Bull / CHOCH_Bull / MSS_Bull
- `breakout_quality_score` buckets
- `trend_ctx.score`, `near_high_pct`, `range_atr`
- `body_ratio`, `volume_ratio`
- `exit_reason`: SL_HIT, GAP_SL_HIT, STRUCT_CONFIRM_BREAK, TIMEOUT
- 90D closed-loop issues: SOLD_EARLY_NEXT_90D, SOLD_EARLY_BY_STRUCTURE_STOP, LOW_90D_MFE_CAPTURE, BAD_EXIT_LOST_BUT_90D_RECOVERED

### 4. Fix rules

- If PRIMARY hurts WR: demote to watch-only; do not tune it endlessly.
- If continuation is noisy: split OB vs FVG; OB continuation has been strongest; FVG needs MSS/BOS/trend/BQ gates.
- If reentry is noisy: require FVG + BOS + trend_score >= 4 + BQ >= 55; reject OB/LV reentry unless future evidence changes.
- If GAP_SL is rare, do not overfit to gap filters.
- If SL_HIT dominates and later recovers, fix entry/fake-break gates, not exit delay.
- If SOLD_EARLY dominates, first classify original runner vs new continuation/reentry setup; avoid blindly holding original trade.

### 5. Frontend sync checklist
When promoting VXX:

- `ACTIVE_VERSION`
- `ACTIVE_TRADE_FILE`
- `ACTIVE_PICK_FILE`
- `VXX_DIR`
- `get_version_trades`
- `get_version_picks`
- `_active_version_paths`
- version dropdown
- `_api_reselect` `engine_map` — must include the active version or manual rerun fails with `当前版本暂不支持重跑`
- `_api_reselect` version tuple lists
- history/picks paths
- `/api/resonance` signal fallback — must not depend only on `ctx_seq`; fallback to family/zone/conf and reject literal `None`/`null`
- closed-loop loader should read `/root/.hermes/smc_audit/vXX_closed_loop_90d_review.json`

### 6. Verification
Run:

```bash
python3 -m py_compile /root/.hermes/scripts/smc_unified.py /root/.hermes/scripts/v25/vXX_*.py
```

Restart frontend:

```bash
ss -ltnp 'sport = :8890' | sed -n '2p' | grep -o 'pid=[0-9]*' | cut -d= -f2 | xargs -r kill || true
cd /root/.hermes/scripts && python3 smc_unified.py
```

Verify:

```text
/api/summary
/api/autopsy/closed-loop
/api/picks
/backtest
/api/kline_full?symbol=300349.SZ&tf=daily&ver=VXX
/api/resonance
POST /api/reselect
```

## Session-specific operational lessons

See `references/operational-lessons-2026-05-28.md` for durable lessons from the V65 operational pass.

See `references/v66-t1-kline-sync-and-reentry-review.md` for the V66 follow-up lessons covering:

- A-share T+1 as a hard release-gate constraint; same-day buy/sell exits are forbidden.
- Version-specific `vXX_t1_audit.py` plus `t1_no_same_day_exit` in `vXX_release_gate.py`.
- Backtest list, K-line chart markers, K-line lower trade records, closed-loop review, and picks/API must be cross-checked from the same trade keys.
- If a backtest row is missing from K-line markers, first check whether `entry_date`/`exit_date` exist in the loaded K-line window (`daily_300` vs longer cache); out-of-window dates need a longer K-line window, not fake trade edits.
- Low-WR windows must be decomposed by family/zone/confirmation/BQ/near-high/range/entry/exit/T+1/market regime and then reviewed trade by trade.
- V66 REENTRY overlay pattern: reject weak REENTRY (`BQ < 60`) and exact-high expanded-range REENTRY (`near_high_pct == 0` and `range_atr >= 4.4`).
- SMC push/report output must use phone-readable Markdown tables with clear Chinese field names.

## Morning holdings + picks push

Daily morning push script:

```bash
cd /root/.hermes/scripts/v25
python3 smc_morning_push.py
```

If the morning push cron times out, follow `references/morning-push-timeout-recovery.md`: check for still-running `smc_daily_ops.py` / closed-loop children before rerunning, then build a recovery report from `ops_latest.json`, `/api/monitor/state`, `/api/picks`, and `/api/live-prices` instead of repeatedly launching the same blocking script. See `references/morning-push-recovery-2026-06-24.md` for a concrete example where the first `ops_latest.json` was stale, the background child updated it after finishing, and the final report had to be rebuilt from the fresh artifact.

If the parent `smc_morning_push.py` exits but an orphaned `smc_daily_ops.py` continues under PID 1, do not report failure or launch duplicates. Wait for the orphan child, verify the refreshed `ops_latest.json`, run API smoke, and report executable live-guard statuses from `/api/live-prices` rather than only summary pick counts. See `references/morning-push-orphaned-daily-ops-recovery-2026-06-24.md`.

If `smc_morning_push.py` still appears running after fresh `ops_logs/YYYYMMDD.json`, `ops_latest.json`, and `*_morning_push.md` have already been written, treat it as an artifact-complete residual-process recovery: verify ops stage return codes, read the report, smoke `/api/summary`, `/api/picks`, `/api/live-prices`, `/api/monitor/state`, verify `POST /api/reselect {"version":"V185"}`, compare `/api/picks` vs `/api/live-prices` live-guard parity, then clear the residual process and verify no children remain. See `references/morning-push-artifact-complete-residual-process-2026-07-03.md`.

Hermes cron job:

```text
Job ID: 87ffb87dad0b
Name: SMC Morning Holdings Picks Push
Schedule: 30 8 * * 1-5
Script: v25/smc_morning_push.py
Workdir: /root/.hermes/scripts
Targets in prompt: weixin:o9cq802Ky3FS2FoTpvNMxGz8wJhM@im.wechat and qqbot:E732A0D614E0B39F693CE0D89CEBB720
```

Push content must include:

- OPEN monitored positions: **all deduplicated holdings**, not a sampled/truncated table; buy date, symbol, name, cost, current price, pnl, SL, TP, status, signal type.
- Daily active picks: pick date, symbol, name, cost, SL, TP, status, signal type, BQ score.
- Existing holdings should be explicitly marked `[已持仓]`; new candidates `[新选股]`.
- De-duplicate open positions by `(symbol, pick/entry date, entry price, sl)` before pushing.
- If recovering from cron timeout, count `/api/picks` rows by scope/state separately from production/tradable rows; `33 WATCH_ONLY` is not the same as `/api/picks total 0`.

Known pitfall: Weixin iLink may return `rate limited`; QQ push can still succeed. Retry Weixin later or via the next scheduled job.

## Current production baseline

As of V66:

- WR 90.51%
- 137 trades
- avg_pnl 20.649%
- avg_realized_r 5.016
- avg_90d_capture 0.412
- 2026-01-01..2026-05-28 window: 14 trades, WR 92.86%, avg_pnl 13.162%
- T+1 violations: 0
- release gate passed

V66 sustainable rules:

- Direct continuation trading only for OB_Bull continuation.
- FVG continuation is watch-only unless future evidence creates a stricter profitable subset.
- REENTRY must pass FVG + BOS + strong trend logic inherited from V63 and additionally range_atr <= 5 and body_ratio >= 0.3.
- V66 overlay: reject REENTRY with `breakout_quality_score < 60`.
- V66 overlay: reject REENTRY with `near_high_pct == 0` and `range_atr >= 4.4` because this exact-high expanded-range subset caused the 2026 low-WR cluster.
- A-share T+1 is a hard gate: any same-day entry/exit fails release.

## Pitfalls

- **Tencent K线刷新二次突发限流/空响应：**同一时段连续跑两次 `refresh_daily_750.py --workers 20` 可能出现第一次 `ok≈4640`、第二次全量 `Expecting value: line 1 column 1` / `ok=0` 的假失败。遇到 cron/compaction recovery 时先审计 `/root/.hermes/kline_cache/*_daily_750.json` 的实际最新日期覆盖数；缓存行可能使用 `t` 而不是 `date` 字段，审计脚本必须同时支持两者；若缓存已覆盖 ≥4500 只最新交易日，可把第二次刷新计数视为供应商临时限流/计数漂移，但仍要如实报告 caveat，不要重复狂刷或绕过生产门禁。
- **闭环报告版本与在线前端版本可能漂移：**`smc_daily_closed_loop.py` 从 on-disk `smc_unified.py` 的 `ACTIVE_VERSION` 推断报告版本；在线 8890 进程可能已经服务更新版本（如 V175）。在这种漂移存在时不要为了“同步”而盲目 kill/restart 8890，否则可能把在线前端降级到旧版本。先用 `/api/summary`、`/api/picks`、`/api/resonance`、`POST /api/reselect` 验证在线状态，并把“dated report version”和“live API version”分开报告。
- Do not report success before rerun support is added to `_api_reselect` and verified by POST `/api/reselect`.
- Do not allow resonance signal cell to show `None`; fallback to family/zone/conf and verify `/api/resonance` has zero empty/None `ctxSeq` values.
- Do not verify `/api/live-prices` only. `/api/picks` must carry the same live/current-price guard result (`BUY` vs `WATCH_ONLY`, guard reason, current-entry gap), otherwise the selection page can still present old scanner candidates as buyable.
- Do not trust an old frontend process; verify `ss -ltnp 'sport = :8890'` after restart.
- Do not optimize only WR by shrinking to tiny samples; release gate sample_not_too_narrow must pass.
- Do not create Hermes cron jobs with absolute `--script` paths; use paths relative to `~/.hermes/scripts/`.
- **V139 KEEP_WATCH executable shadow lesson:** after V138 creates executable rows, evaluate entry modes (`RECLAIM_NEXT_OPEN`, `T2_NEXT_OPEN`, `T3_NEXT_OPEN`) before composing new gates. In the V139 pass, `RECLAIM_NEXT_OPEN + market_state != MIXED` was the best non-production shadow slice (273 rows, WR 80.22%, Avg +2.998%, recent45 30 rows, T+1=0); further hardening collapsed coverage without improving average PnL. Remaining losses were mostly `ZONE_CLOSE_DEAD_T1`, so next work should be K-line semantic replay of reclaim failure, not TP/SL tuning. See `references/v139-keep-watch-executable-shadow-hardening.md`.
- **V152/V153/V164 promotion-demotion lesson:** do not let high headline WR preserve a promoted route when synthetic breakeven or micro-profit clustering is present. V152 was demoted despite WR 92.91% because 34.65% rows were synthetic BE and 31.50% were +0.5% micro profits. V153 was historically cleaner (221 trades, WR 83.26%, avg +3.3327%, T+1=0) but was still not production-ready because its exact selector depended on `v143_lifecycle_status`, which is absent at scanner time. V164 corrected scanner dry-run reduced recent45 BUY rows from 1462 to 333 with zero non-takeover/body-fail/outcome-leak rows, but remained research-only because dry-run integrity is not full production promotion. See `references/v152-demotion-v153-v164-scanner-contract.md`.
- **Do not stop at field completeness or WR/RR metrics — always audit the strategy-layer entry logic** (`daily_scan.py`). V66 case: all 137 trades have correct fields, WR=90.51%, but `entry_idx = c.bar+1` means 100% of trades have zero retrace wait, 0/137 have sweep precondition, 0/137 have computed market_state. V67 full-market audit (90551 trades) reveals true WR=41%. See `references/v66-strategy-layer-breakout-vs-smc-retrace.md`.
- When user says "SL problem" or "信号不准", do NOT just audit field contracts or aggregate metrics. Trace the **signal detection → strategy entry → monitor execution** pipeline end-to-end. Check: entry_idx vs conf_idx, sweep precondition, market_state, SL buffer vs zone_low, and signal combination richness. These are architecture issues, not parameter tuning issues.
