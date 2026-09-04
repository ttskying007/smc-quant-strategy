# Multi-lane PIT source qualification and resumable raw builds

## Trigger

Use after the local price-only/SMC ontology inventory is terminal but the user requests continued research. Continuous work must not become a disguised sweep of prior windows, timeframes, exits, thresholds, or selected universes.

## Core rule

A legal new branch needs an **independent causal information dimension**. Examples are point-in-time capital positioning, date-sensitive cross-border holdings, historical order flow, or PIT constituent-flow data. A different M15/M60/daily expression of an existing OHLCV story is not new.

## Pre-register before reading outcomes

1. Define the source contract: provider, requested date, received date, symbol universe, whether the feature has a public/as-of timestamp, and the earliest permitted decision time.
2. State outcome-blind identity fields (`symbol`, event, confirmation, entry date).
3. Freeze quality gates before outcome access. A robust production gate should require adequate total and annual support, positive annual economics, zero T+1 violations, and independent identity reconciliation.
4. Explicitly prohibit reuse of historical trades/PnL/exit fields in seed generation.

## Multi-lane qualification pattern

Maintain a small set of genuinely orthogonal lanes rather than serially mutating a failed one:

- **Stock-level financing / securities lending**: prior-session financing balance, financing purchase, and lending changes can test whether capital participates in a structurally valid SMC response.
- **Stock Connect holdings**: require per-stock history and prior public availability, not merely a current holdings endpoint.
- **Historical tick/order flow**: must be date-sensitive, carry actual volume, and align to same-source daily OHLCV before interpreting it as absorption.
- **ETF constituent flow**: aggregate ETF shares are insufficient; require historical constituent weights plus publication/effective timestamps.
- **Exchange/institutional disclosure events**: only a source semantically non-overlapping with a closed disclosure branch is new.

A successful three-date pilot only proves a candidate source can be built. It does **not** authorize a replay, a full-market claim, or production.

## Raw source build pattern

For a pilot-ready source, build raw data before creating any strategy:

1. Derive the requested date denominator independently from a dated daily master; never count only already-built partitions.
2. Store one provider and one venue in separate namespaces and partitions, for example `raw/<provider>/<venue>/<yyyymmdd>.json.gz`.
3. Persist the requested/received date, source, provider timestamp, original feature semantics, and a statement that usage is restricted to a later completed session.
4. Write each partition to a temporary file and atomically rename it.
5. Compute missing work from valid committed partitions; a corrupt or incomplete partition remains missing.
6. Serialize writers with a file lock; a scheduled retry must safely exit while a prior batch is running.
7. Use a watchdog that stays silent during normal progress and emits only a failure or final-completion event. This avoids repeatedly notifying the user while preserving a durable controller.
8. When complete, run a source coverage/PIT timing audit before producing an outcome-blind seed. Missing exchange, asset-class, listing-history, or publication-time coverage must fail closed.

## Example: official Chinese exchange margin detail

A practical source probe can validate several separated historical dates on both exchanges:

- SSE endpoint: `query.sse.com.cn/marketdata/tradedata/queryMargin.do`, `tabType=mxtype`, `detailsDate=YYYYMMDD`, requiring rows whose `opDate` equals the requested date and which contain a security code.
- SZSE endpoint: `www.szse.cn/api/report/ShowReport`, `SHOWTYPE=xlsx`, `CATALOGID=1837_xxpl`, `txtDate=YYYY-MM-DD`, requiring a parsable workbook with stock code, financing-buy, and financing-balance columns.

This is only a source pilot. Margin statistics are end-of-session data, so any later SMC ontology must use the previous completed exchange session only; it must never use same-date margin values to decide that date's entry.

## Promotion boundary

After source coverage and PIT timing pass, the mandatory order remains:

`outcome-blind generator → independent identity oracle → one frozen strict-T+1 replay → independent metric audit → scanner-time exact reconstruction → production/UI isolation audit`.

If the frozen replay fails, close the ontology. Do not convert its source field into a threshold search or a state/year subset.
