# V351–V357 Canonical Continuation Lifecycle Closure

Use when a continuation audit reports huge numbers of semantic BOS/OB candidates or takeover rows.

## Root defects proved by V351/V352 audit

A semantic primitive audit is not a candidate lifecycle audit. V351/V356 proved the daily primitives were causal and matched an independent oracle, but V352 treated every `BOS × backward-OB` attachment as a separate lifecycle.

On the full source set:

- semantic BOS/OB rows: 205,049
- physical OB zones: 123,365
- duplicate repeated-BOS rows: 81,684
- V352 takeover rows: 75,007, including duplicated reuse of the same post-zone touch/reclaim/takeover sequence
- 146,487 / 205,049 raw rows had a wick touch *before* their associated BOS; those zones were already mitigated, not fresh pullback candidates.

Do not use raw semantic-row counts or raw takeover counts as candidate supply, backtest sample size, or production signal counts.

## Canonical continuation contract

For a bullish continuation candidate:

1. Define physical zone key: `(symbol, ob_idx, zone_low, zone_high)`.
2. Keep only the **earliest** associated bullish BOS for that zone. Later BOS events cannot create another first retest of the same order block.
3. Inspect strictly between `ob_idx + 1` and `event_idx - 1`:
   - any close `< zone_low` → `PRE_EVENT_INVALIDATED`, exclude;
   - otherwise any wick low `<= zone_high` → `PRE_EVENT_MITIGATED`, exclude;
   - otherwise → `FRESH_AT_BOS`.
4. Only fresh zones enter the lifecycle after BOS:
   `first wick touch → close reclaim above zone_high → following hold above zone`.
5. A post-BOS close `< zone_low` cancels the lifecycle. A right-edge incomplete observation is `WAIT_*`, never expiry/failure.
6. Lifecycle output must remain non-tradable and contain no entry, exit, PnL, TP, SL, RR, or outcome fields until a separate source-safe execution/backtest study is designed.

## Full-universe V357 result (2026-07-11)

Artifact: `/root/.hermes/smc_audit/v357_canonical_continuation_lifecycle_latest.json`

| Stage | Count |
|---|---:|
| raw semantic seeds | 205,049 |
| physical OB zones | 123,365 |
| duplicate BOS rows suppressed | 81,684 |
| pre-event mitigated | 68,502 |
| pre-event invalidated | 1,699 |
| fresh canonical zones | 53,164 |
| post-BOS takeover confirmed | 20,213 |
| post-BOS invalidated | 27,998 |

Checks passed: one row per physical fresh zone, no duplicate event keys, all rows fresh at BOS, all rows non-tradable, and zero temporal-order failures.

## Interpretation boundary

This proves only that the **candidate lifecycle definition** is causal and no longer duplicates a spent zone. It does **not** establish profitability, a production threshold, an entry rule, or a live watchlist.

Never turn the 20,213 takeovers into trades without a separate source-safe full-history execution study. The current local 60-minute cache remains insufficient for a 2023–2026 MTF promotion audit.

## V365–V366 future-confirmation trap (2026-07-11)

A chronological V333 daily-rule search initially found one apparent two-fold OOS survivor: `V164 + bull3>=3 + zone>=2 + DEMAND_OB/OB+FVG` (without needing the non-point-in-time industry snapshot). **It is rejected, not a research candidate.**

V366 proved every one of its 402 rows was entered before the confirmation data used by the selection rule:

- `v132_true_takeover_2`: 402/402 rows depend on two post-reclaim bars, while `entry_idx - v132_entry_after_confirm_idx_2 = -2` for every row.
- `v132_bull_count_3>=3`: 402/402 rows depend on three post-reclaim bars, while `entry_idx - v132_entry_after_confirm_idx_3 = -3` for every row.

`v132_fvg_reclaim_takeover_shadow_backtest.py:108-149` materializes those forward bars; its own correct delayed model enters only at `v132_entry_after_confirm_idx_n` (lines 175-180). Therefore any V164/V132 rule that applies `true_takeover_2`, `true_takeover_3_strict`, `bull_count_3`, hold_2/3, or post-pullback_2/3 to an earlier `entry_idx` is future-data contaminated, even if temporal OOS metrics are high.

**Closure rule:** do not mine or promote V164/V132 pre-entry rules until the entry is rebuilt at the corresponding confirmation-next-open and all metrics are recomputed from scratch. Do not treat old V333/V365 metrics as evidence.
