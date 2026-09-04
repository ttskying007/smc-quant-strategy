# PIT institutional-survey source qualification

## When to use

Use when evaluating institutional-investor survey / investor-relations disclosures as a genuinely new, event-first information dimension before joining any OHLCV or opening outcomes.

## Source-first sequence

1. Pre-register the source years, date field, canonical event identity, completeness gates, and same-day execution prohibition.
2. Probe both aggregate and detail reports without market data. Treat report-specific columns as separate schemas.
3. Read the provider's own current frontend configuration to identify canonical filters; preserve the URL and a content hash as source-contract evidence.
4. Fetch all declared date partitions and assert, independently by partition:
   - every page committed;
   - received rows equal the provider count;
   - every `NOTICE_DATE` belongs to the requested partition;
   - publication/event identity fields are complete;
   - no price, return, trade, stop, or target fields were read or emitted.
5. Only after the source gate passes may one event-first ontology be preregistered and generated.

## Eastmoney schema pitfall

Eastmoney's institutional-survey reports have different semantics:

- `RPT_ORG_SURVEYNEW` is an aggregate/recent report and may expose only a rolling recent interval. A large row count does not prove complete historical years; explicitly test each declared year and record the minimum/maximum `NOTICE_DATE`.
- `RPT_ORG_SURVEY` is the historical detail report. Without the provider's canonical filters it expands events into participant/detail rows and can inflate the apparent denominator by an order of magnitude.
- At the time of qualification, the provider frontend used `NUMBERNEW="1"` and `IS_SOURCE="1"` to select canonical event/source rows. Re-read the live frontend configuration rather than assuming these fields or values are permanent.
- A column valid in the detail report (for example a document URL) may be invalid in the aggregate report. Qualify each report with its own declared column list.

The canonical event identity should normally include `SECUCODE + NOTICE_DATE + URL` when URL is available. Participant or organization counts are diagnostic fields, not post-outcome selectors.

## Eastmoney datacenter transport contract (measured, 2026-08)

`https://datacenter-web.eastmoney.com/api/data/v1/get` with `reportName=RPT_ORG_SURVEY`:

- **page_size=50 only.** 100/500 return `服务器繁忙` regardless of concurrency.
- **Concurrency ≤4 workers** with a per-thread persistent `requests.Session` (keep-alive). 16 workers rate-limit into systematic failures.
- **6 retries, exponential backoff capped ~12s** per page; a page that exhausts retries stays missing — never convert a failed page into a zero-row success or reuse a partial participant-denominator checkpoint.
- Expected canonical denominators (with `NUMBERNEW/IS_SOURCE` filter): 2023=26,272 rows (526 pages), 2024=25,374 (508), 2025=24,566 (492); 1,526 pages total.
- **Per-thread keep-alive sessions roughly double throughput vs fresh urllib connections** (urllib ~211 pages/600s → requests.Session ~1238 pages/63min with failures; resume is idempotent).
- A full 1,526-page build exceeds any foreground 600s terminal window. Run it as a **background process with `notify_on_complete=true` and a long timeout**, or in chunked resume runs; the resumable sqlite checkpoint makes this safe. Never sit in a foreground wait for the whole build.
- `progress.json` should carry per-partition committed pages/rows/remaining plus the failure list; verify `complete` and failure count from the controller's final report, not from a log tail.

## Large historical pagination

Never hold a full multi-thousand-page build only in memory.

- Commit each page atomically into an isolated SQLite/checkpoint namespace.
- Store provider count/page-count witnesses with every committed page.
- Resume only missing pages after interruption.
- When the source contract changes (report, filter, partition, identity), use a new namespace; never mix old pages into the repaired denominator.
- Probe page-size and concurrency behavior before the full build. Prefer a persistent HTTP session per worker and conservative concurrency.
- A page request that exhausts retries stays missing; it is not converted into a zero-row success. Re-run the controller until the declared denominator is complete or close the source.

## Research versus production

A complete source-local catalog can authorize one no-write, outcome-blind research ontology. It does not automatically authorize production. Production still requires independent publication-time/official-document validation where applicable, current-universe coverage, exact identity Oracle parity, one frozen strict-T+1 replay, and a current scanner that materializes the same decision-time contract.

If only a rolling fragment or incomplete set of years is available, label it diagnostic/partial-history explicitly. Do not silently redefine a preregistered multi-year source gate after seeing the coverage result.