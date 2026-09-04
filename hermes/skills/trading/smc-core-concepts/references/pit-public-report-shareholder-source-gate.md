# PIT Public-Report Shareholder Snapshot Gate

Use this before treating Top-10 shareholder data as a historical stock signal.

## The valid join

A structured shareholder snapshot has a **report period**, not necessarily the date at which it became knowable. Join it to a public filing record:

`symbol + report_end -> public announcement metadata -> next eligible decision date`

Minimum fields:

- `report_end`
- public `notice_date` (and publication time when the source supplies it)
- announcement/artifact identifier
- holder rows and their report period

For a decision on `entry_date`, require both:

- `report_end < entry_date`
- `notice_date < entry_date`

This strict rule intentionally forbids same-day use. It is conservative around after-close and weekend filings; it prevents accidental same-day information leakage without needing to infer intraday availability.

## Feasibility comes before outcome replay

Freeze identities first (for example, `symbol, entry_date` from a fixed replay), then inspect source availability without reading outcome columns. A source may advance only if all of these pass:

| Gate | Minimum |
|---|---:|
| total PIT-mapped identities | >=95% |
| PIT-mapped identities in every calendar year | >=95% |
| structured holder snapshot non-empty | required |
| report period and public notice both before entry | 100% |
| outcome/PnL/exit fields used in source construction | 0 |
| production/frontend/watchlist writes | 0 |

Only after this gate passes may a separate frozen-outcome replay test predeclared shareholder features. Do not tune thresholds during the availability phase.

## Public endpoint collection pitfall

Public announcement endpoints can intermittently return HTML or non-JSON anti-bot pages. Never interpret a parse failure as an issuer with no filing.

Collection contract:

1. Validate that the response is JSON before parsing it.
2. Retry transient non-JSON/HTTP failures with bounded backoff.
3. Reduce concurrency when a burst causes anti-bot pages.
4. Count unresolved requests separately as `REQUEST_FAILED`, not `NO_PRIOR_PUBLIC_REPORT`.
5. Declare coverage only after failed requests are retried or explicitly accounted for.

This distinguishes a true lack of point-in-time history from a collector artifact.

## Evidence artifacts

Persist a no-write report and a mapping table containing at least:

`symbol, entry_date, report_end, notice_date, publication_time, announcement_id, mapping_status, row_count`.

The mapping is evidence of source-time eligibility only. It does not establish a shareholder signal edge or authorize production promotion.
