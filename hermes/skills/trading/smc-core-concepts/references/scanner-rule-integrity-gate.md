# Scanner Rule Integrity Gate

Use this when promoting an SMC backtest rule into a daily scanner / dry-run / production selector.

## Trigger

A historical backtest rule looks clean, but the real scanner produces too many BUY rows or lets weak reclaim classes into current candidates.

## Core lesson

Do not assume the historical chosen-row source contains the same class distribution as the live scanner stream. A backtest subset may already be pre-filtered, hiding a missing rule precondition.

Example failure pattern:

```text
Historical backtest rows: all TRUE_TAKEOVER_2 / TRUE_TAKEOVER_3_STRICT
Scanner rows: include FAILED_RECLAIM_*, RECOVERY_SEPARATE, UNCLEAR_RECLAIM
Buggy application rule: (strict3 OR chase <= threshold) AND body <= threshold
Missing precondition: TRUE_TAKEOVER_2 OR TRUE_TAKEOVER_3_STRICT
```

This allows non-takeover reclaim classes to leak into BUY in the scanner even though historical metrics looked valid.

## Required audit before promotion

1. Rebuild rule fields from the real scanner candidate stream, not historical chosen trades.
2. Count class distribution before and after the selector:
   - `v132_reclaim_class`
   - `v132_true_takeover_2`
   - `v132_true_takeover_3_strict`
3. Assert every BUY row satisfies the semantic precondition explicitly.
4. Assert scanner-time fields are complete and contain no outcome fields:
   - no `pnl`, `exit_*`, `won`, `mae`, `mfe`, `hold_bars`, backtest-version outcome prefixes.
5. Compare old BUY count vs corrected BUY count; large drops are expected if leakage existed.
6. Keep the first pass as dry-run only. Do not write production/frontend/watchlist until the corrected dry-run passes.

## Corrected rule shape for takeover scanner gates

```text
(v132_true_takeover_2 OR v132_true_takeover_3_strict)
AND body/exhaustion cap passes
```

For the V164 audit, the concrete body cap was:

```text
(v132_true_takeover_2 OR v132_true_takeover_3_strict)
AND v132_reclaim_bull_body_pct <= 87.1077
```

## Verification output to preserve

Produce a compact report with:

- source scanner rows
- built scanner-time rows
- recent-window rows
- old rule BUY rows
- corrected rule BUY rows
- rows rejected from old BUY by corrected rule
- latest pass date and latest BUY rows
- missing kline count
- missing field count
- outcome leakage count
- non-takeover BUY count
- body-fail BUY count

Promotion is blocked if any corrected BUY row is non-takeover, body-fail, missing required fields, or contains outcome leakage.
