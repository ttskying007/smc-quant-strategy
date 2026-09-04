# SMC Production Closure Audit Pattern

Use this reference when a future SMC task asks whether a repair is truly solved end-to-end, especially for historical pollution, daily completeness, signal correctness, combinations, retraces, and TP/SL design.

## Separate Three Truth Levels

1. **Tool-proven solved** — production files and gates prove the issue is gone.
2. **Empirically behaving well** — backtest/live metrics look good but do not prove definitions.
3. **Not yet proven** — needs a new audit, usually semantic signal or retrace-rank validation.

Never use WR alone as proof of signal correctness.

## Historical Pollution Closure

Label-only repairs are insufficient. If old closed positions, closed reviews, or ledger events remain in hot production files, downstream pages and reports can keep reading them.

A complete repair requires:

- Physical quarantine of historical closed/review/ledger pollution.
- Production files checked directly: no non-clean `CLOSED` rows, no diagnostic reviews.
- Release gate checks for both `production_reviews_clean_only` and `production_closed_positions_clean_only`.
- Legacy `OPEN` / `WATCH_ONLY` rows may remain visible for risk monitoring but must not enter production WR/SL metrics.

## Daily Full-Market Completeness

Daily refresh must validate:

- K-line refresh success count.
- expected universe count.
- missing symbol count.
- latest market date / stale date.
- tradable count separated from WATCH_ONLY count.

Do not report WATCH_ONLY rows as active production picks.

## Signal Correctness Boundary

Sequence and provenance audits prove time order and traceability:

`source_event_idx → zone_idx → retrace_index → conf_index → entry_index → exit_index`

They do **not** prove Pine/LuxAlgo semantic correctness. Add semantic re-derivation audits for:

- OB: scan backward from the confirmed structure/break point to nearest opposite candle.
- FVG: verify three-candle gap geometry and mitigation state.
- BOS/CHOCH: verify swing break and confirmation/de-dup rules.
- Sweep: verify wick sweep of liquidity and cooldown.

## Multi-Retrace Audit

For questions about first/second/multiple retraces, materialize `retrace_rank` and report per-rank WR, avg PnL, SL rate, gap SL rate, and invalidation-before-entry rate.

Do not infer later retrace quality from aggregate strategy WR.

## Methodology Reporting For Lei

Reports should be compact but explicit:

- what is proven solved
- what is only empirically good
- what remains unproven
- exact files/gates/metrics used as evidence
- next automatic audit needed

Avoid long theoretical explanations unless they are tied to a gate, file, or measurable failure mode.

## API Closure Is Not Strategy Closure

When a repair removes historical pollution from `/api/picks`, `/api/live-prices`, current watchlists, or frontend routing, report that as **production/API closure only** unless a fresh strategy loop was also rerun.

Production/API closure requires direct endpoint/file proof:
- current picks do not contain completed-trade fields such as `exit_date`, `net_pnl_pct`, stale `exit_reason`, or realized `hold_bars`;
- WATCH_ONLY rows are explicitly non-tradable context (`isTradableLive=false`, `tradable=false`, `WATCH_ONLY_CONTEXT`) and do not compute live PnL/SL/TP state;
- active tradable count, WATCH_ONLY count, and raw file count are separately reported;
- daily completeness and release gates pass for freshness, T+1, provenance, and pollution checks.

### Full Sync API/Frontend Verification Bundle

When closing a production/API/frontend sync repair, run a direct endpoint bundle and persist the result under `~/.hermes/smc_audit/`:
- `/api/summary`: HTTP 200 and `last_kline_date` equals the latest market date.
- `/api/picks/contract`: `tradable_active_pick_count`, `watch_only_count`, `raw_pick_file_count` reported separately.
- `/api/picks`: row count and scope counts match the contract; all current non-trading rows are `WATCH_ONLY`; completed-trade pollution count is zero for `exit_date`, `net_pnl_pct`, `hold_bars` and camelCase aliases.
- `/api/live-prices`: `tradableLiveCount=0` when no active tradable picks; `watchContextCount` equals displayed watch context rows; WATCH_ONLY rows have `status=WATCH_ONLY_CONTEXT`, `tradable=false`, `isTradableLive=false`, and `pnlPct=0`.
- Browser smoke for `/`, `/monitor`, `/live`: labels must say “可交易X / 观察Y” or “真实持仓X / 观察上下文Y”; console JS errors must be zero.

If an endpoint disconnects or the service restarts during verification, first check service liveness (`ss -ltnp` + process), then retry with a small deterministic Python/urllib probe that records per-endpoint HTTP status, counts, and bad rows. Capture the retry pattern and final proof, not the transient failure, and do not declare closure until endpoints and browser smoke both pass.

Do **not** use those operational gates to claim strategy promotion. Strategy closure still requires a current full-market multi-year backtest plus monthly, per-trade, combo, interval, entry-position, SL/TP, and semantic-signal audits.

### POI Lifecycle Start / Mitigation Pitfall (V415–V416)

A causal sequence can still be semantically false if its POI lifecycle starts before the POI exists or ignores a prior mitigation.

For every candidate, enforce `lifecycle_start_idx = max(event_idx, poi_idx)` and inspect only bars strictly after it for the claimed first `touch → reclaim → hold` lifecycle.

- **Backward-anchored OB:** if a wick enters the OB between `poi_idx+1` and `event_idx-1`, it is already mitigated and cannot be labelled the *post-confirmation first retest*. A close below `zone_low` in that interval invalidates it.
- **FVG:** the third candle that establishes the gap is its creation bar, not a post-creation retest. If `event_idx < poi_idx`, starting from `event_idx+1` creates a source-bar touch artifact.
- Do not replay, promote, or compare economics until these states are physically materialized and pre-mitigated/source-bar rows are excluded from the strict story.

V415 evidence (4655-symbol V409 audit): literal eligibility fell to R1 `452/1406`, R2 `466/1477`, C1 `53165/123364`; all outputs remained non-tradable and outcome-free. V416 materializes the corrected candidate definitions only; it makes no economic claim.

### Reclaim-confirmed Entry Pitfall

If a system claims `touch → reclaim → entry`, audit `reclaim_idx → entry_idx` explicitly. If most rows have `entry_idx < reclaim_idx`, the model is a touch/anticipation-entry model, not reclaim-confirmed SMC entry, regardless of headline WR/RR. The next strategy version must enforce `entry_idx > reclaim_idx`, rerun full-market backtest, then re-audit monthly stability and per-trade behavior.

For detailed SMC system workflow, see `smc-v11-system/references/production-api-vs-strategy-backtest-closure.md`.

For strict `touch -> reclaim -> entry` rebuilds, see `references/v104-strict-reclaim-entry-audit.md`. Key pitfall: if the next open after reclaim gaps back below `zone_high`, it is not an executable reclaim-confirmed entry; skip it and wait for a fresh reclaim. Semantic repair can pass while release promotion still fails on WR/monthly stability, so report those as separate truth levels.

### V132/V339 Future-confirmation Trap

A field whose name ends in `_1`, `_2`, or `_3` can encode bars observed *after* reclaim. It must never be used to select a trade at the older `entry_idx`.

Concrete 2026-07 audit: V339 reported `n=634`, WR `94.95%`, average PnL `+8.2%` after conservative same-bar handling, but its selector required `v132_bull_count_3`, `v132_reclaim_bull_body_pct`, and `v132_post_zone_pullback_depth_pct_3`. All 634 selected rows had `entry_idx - v132_entry_after_confirm_idx_3 = -3`: entry occurred three bars before the required three-bar confirmation. Same-bar exit conservatism cannot repair pre-entry selector leakage.

Required audit for any V132-derived rule: materialize `entry_idx`, every required `v132_entry_after_confirm_idx_n`, and prove `entry_idx >= confirmation_idx` (normally enter at the following open). If any row fails, invalidate all reported performance, do not use it for shadow promotion, and rebuild/replay from the legal entry index.

### Shadow Lifecycle UI/API Dry-run Pattern

When a lifecycle/shadow contract has no proven entry edge, it may be mapped into UI/API payloads only if the payload is explicitly non-tradable:
- every row must export `shadow_only=true`, `tradable=false`, `buy_enabled=false`, `trade_action=NO_BUY`;
- status labels such as `KEEP_WATCH`, `CANCEL`, and `IGNORE` are display/lifecycle states, not BUY signals;
- failed-reclaim rows must not be reinterpreted as buy signals (`failed_reclaim_is_buy_signal=false`);
- no realized outcome fields may leak into the dry-run payload;
- latest-per-symbol payloads must be deduplicated by symbol/source key;
- production endpoints/watchlists must be snapshotted and remain unchanged.

A valid dry-run proof should persist `summary.json`, payload JSONs, and `report.md` under `~/.hermes/smc_audit/`, with row counts, status counts, zero tradable/buy-enabled counts, zero missing required fields, zero outcome leaks, and an explicit production snapshot. This proves UI/API plumbing only; it does not promote KEEP_WATCH/CANCEL to BUY and does not prove an entry edge.

For the next research-only refinement after dry-run plumbing, see `references/v137-keep-watch-shadow-refinement.md`. Key lesson: split KEEP_WATCH into strong/weak shadow tiers only after loser taxonomy and bucket scans, keep all payload rows `NO_BUY`, and move next to executable entry/exit reconstruction rather than further threshold tuning.
