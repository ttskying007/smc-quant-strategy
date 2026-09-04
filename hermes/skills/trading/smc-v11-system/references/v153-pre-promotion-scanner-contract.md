# V153 pre-promotion scanner-time contract lesson

Session lesson from V153/V164 audit: a historical backtest gate can pass while the production scanner contract still fails. Do **not** promote a version to frontend/API just because historical rows are clean.

## Context

V152 had strong-looking WR but was invalidated by synthetic BE / micro-profit pollution. V153 repaired the historical contract:

- 221 trades
- WR 83.26%
- avg +3.3327%
- synthetic BE = 0
- micro_pct = 0.9%
- T+1 violations = 0
- min yearly sample = 34

However, V164 proved V153 was **not promotion-ready**.

## Required promotion gate

Before writing `vXXX_trades.json`, `vXXX_picks.json`, `vXXX_report.json`, or changing `_promoted_contract_dir()` / frontend routing, require all four gates:

1. Historical contract passes: fields complete, T+1 zero, no synthetic BE, release gate true.
2. Losing rows are reviewed individually / by bucket; losses must be natural hard/time exits, not hidden pseudo-exit pollution.
3. Excluded/rejected bucket root-cause audit is complete; exclusion must be justified by materially worse WR/avg/hard-exit profile.
4. **Scanner-time exact selector passes**: the production/dry-run scanner must contain every field needed to reproduce the exact historical selector without outcome/post-entry leakage.

If any gate fails, the version remains a historical diagnostic/research candidate only.

## Specific V153 pitfall

V153 selection was defined as baseline rows excluding:

```text
v143_lifecycle_status == CANCEL_AFTER_ENTRY_DAY_CLOSE
```

The scanner dry-run recent45 payload had 2633 rows, all with:

```text
v143_lifecycle_status missing
```

Therefore exact V153 selection cannot be reproduced at scanner time. V153 is historically clean but **not live-scanner usable** until either:

- a delayed lifecycle scanner contract can observe and emit `v143_lifecycle_status` before BUY, or
- a non-outcome proxy rule is rebuilt and dry-run integrity passes.

## Reusable audit artifact pattern

Create a pre-promotion audit script that writes only `smc_audit/...`, never production/frontend/watchlist. It should produce:

- `summary.json` with explicit `decision`, `gates`, and `next_required`
- loss bucket metrics
- ranked losing rows
- excluded/rejected bucket metrics
- scanner-time contract audit with required missing fields and outcome-leak count

Example decision labels:

```text
V153_PROMOTION_READY
V153_NOT_PROMOTION_READY__SCANNER_CONTRACT_FAILS
```

## Concrete V164 outcome

V164 result:

```text
historical_contract_pass = true
losing_bucket_explained = true
excluded_cancel_justified = true
scanner_time_exact_v153_pass = false
final_pass = false
```

So the correct action was to **not** write V153 production artifacts and **not** alter frontend promoted routing.
