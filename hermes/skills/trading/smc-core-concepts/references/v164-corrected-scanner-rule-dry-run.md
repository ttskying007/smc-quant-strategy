# V164 corrected scanner rule dry-run (2026-06-22)

## When to use

Use this note when promoting a historical high-WR lifecycle/backtest rule into the daily full-market scanner, especially after V158–V161 style scanner-time contract audits.

## Durable lesson

A rule that looks clean on a prefiltered historical subset can leak weak scanner-time rows if the scanner implementation does not explicitly require the same semantic preconditions. In this session, old V160 scanner dry-run marked many rows BUY because the scanner application rule did not require TRUE_TAKEOVER_2 or TRUE_TAKEOVER_3_STRICT.

## Corrected scanner rule

```text
(v132_true_takeover_2 OR v132_true_takeover_3_strict)
AND v132_reclaim_bull_body_pct <= 87.1077
```

Implementation artifact:

```bash
python3 /root/.hermes/scripts/v25/v164_corrected_scanner_dry_run.py
```

Read-only output directory:

```text
/root/.hermes/smc_audit/v164_corrected_scanner_dry_run_20260622/
```

## Required dry-run gates before production writes

Do not write production/frontend/watchlist until all pass:

| Gate | Required result |
|---|---:|
| `missing_kline` | 0 |
| required scanner-time fields missing | 0 |
| `outcome_field_leak_rows` | 0 |
| non-TRUE_TAKEOVER BUY rows | 0 |
| body-threshold-fail BUY rows | 0 |
| artifacts explicitly mark `production_write=false` | true |
| artifacts explicitly mark `frontend_write=false` | true |
| artifacts explicitly mark `watchlist_write=false` | true |

## Verified dry-run result from the session

| Scope | Count |
|---|---:|
| scanned symbols | 4655 |
| source rows | 39014 |
| built rows | 39014 |
| recent45 rows | 2348 |
| old V160 BUY recent45 | 1462 |
| V164 corrected BUY recent45 | 333 |
| rejected from old V160 BUY | 1154 |
| latest BUY date | 20260617 |
| latest BUY rows | 2 |

Integrity result:

| Check | Count |
|---|---:|
| non-takeover BUY rows | 0 |
| body-fail BUY rows | 0 |
| outcome leak BUY rows | 0 |

Latest BUY rows were only `688327.SH` and `688787.SH`, both `TRUE_TAKEOVER_3_STRICT`.

## Pitfall to avoid

Do not say a scanner rule is production-ready just because a backtest subset or prefiltered lifecycle table passed. The daily scanner must rebuild every decision field from scanner-time data and then prove that every BUY row satisfies the explicit rule contract. Keep this as dry-run until production-source isolation and frontend/watchlist routing are separately verified.
