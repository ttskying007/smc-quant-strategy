# V153/V164 pre-promotion scanner contract lesson

A production candidate is not usable just because historical backtest rows pass. Promotion requires a scanner-time exact selector gate.

## Durable rule

Before writing production artifacts or routing frontend/API to a new SMC version, require all four gates:

1. Historical rows pass: fields complete, T+1 zero, no synthetic BE/micro-profit pollution.
2. Losing rows are reviewed; losses are natural hard/time exits, not hidden pseudo-exit artifacts.
3. Excluded/rejected bucket is audited and its exclusion is justified by materially worse WR/avg/hard-exit profile.
4. Scanner-time exact selector passes: dry-run/live scanner payload contains every field needed to reproduce the historical selector without outcome/post-entry leakage.

If scanner-time exact selector fails, the version remains historical diagnostic/research only.

## V153 example

V153 historical metrics were clean enough as a candidate:

- 221 trades
- WR 83.26%
- avg +3.3327%
- synthetic BE 0
- micro_pct 0.9%
- T+1 violations 0

But V164 blocked promotion because V153 selected rows by excluding:

```text
v143_lifecycle_status == CANCEL_AFTER_ENTRY_DAY_CLOSE
```

The scanner dry-run recent45 payload had 2633 rows with `v143_lifecycle_status` missing. Therefore exact V153 selection could not be reproduced at scanner time.

Correct action: do **not** write `v153_trades.json`, `v153_picks.json`, `v153_report.json`, and do **not** change promoted frontend routing until either a delayed lifecycle scanner emits the needed status before BUY, or a non-outcome proxy selector is rebuilt and dry-run integrity passes.

## Recommended audit outputs

A pre-promotion audit should write only `smc_audit/...` and include:

- `summary.json` with explicit `decision`, `gates`, and `next_required`
- loss bucket metrics + ranked losing rows
- excluded/rejected bucket metrics
- scanner-time contract audit with missing required fields and outcome-leak counts
