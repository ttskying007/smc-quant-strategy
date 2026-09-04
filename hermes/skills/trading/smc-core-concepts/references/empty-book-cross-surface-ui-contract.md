# EMPTY_BOOK Cross-Surface UI Contract

## Trigger

Use when the production registry is `EMPTY_BOOK` while historic trade, pick, report, or experiment artifacts still exist on disk.

## Root cause pattern

A frontend may correctly fail-close `/api/summary`, `/api/picks`, and `/api/live-prices`, yet still leak rejected historical engines through page-local calls such as `reload_trades()`, `reload_metrics()`, legacy scanner merges, static version selectors, or static architecture documents. A visible label of `EMPTY_BOOK` is not enough: every page and API must obey the same registry.

## Required invariant

`registry.state == EMPTY_BOOK` means **no current production strategy**. Historic V88/V185-like files remain audit artifacts only; they must never become current trades, picks, risk metrics, scanner inputs, or fallback K-line signals.

## Minimal implementation

1. Build one shared `empty_book_page(title, detail)` helper that reads only registry/epoch plus an explicitly read-only research adapter.
2. At the top of every production-derived page handler, return that helper before any `reload_trades()`, `reload_picks()`, report load, historical monitor load, or legacy selector merge:
   - dashboard
   - backtest
   - monitor/live where applicable
   - compare
   - analysis
   - autopsy/review
   - resonance
   - stop-loss diagnostics
   - static docs
3. Collapse navigation under EMPTY_BOOK to current production status, logs, and approved read-only research only. Do not leave clickable legacy pages whose data is quarantined.
4. Logs may list legacy files for audit provenance, but label them explicitly as archived/non-production artifacts.
5. Static docs must be conditionally rendered from the registry; never retain a hard-coded old production version, rerun instruction, or old data path.

## Research adapter boundary

A research-promotable V517-like lineage must have a separate adapter that reads frozen audit artifacts and exposes:

- `production_write=false`
- `watchlist_write=false`
- `buy_enabled=false`
- replay rows marked `REPLAY_ONLY`
- current scanner rows only from the latest committed epoch
- `NO_BUY` for an empty scanner, never historic fallback rows

Research UI synchronization does not promote it to production.

## K-line contract

For a research version, K-line markers must be sourced only from that version's frozen replay/causal trace. Do not overlay generic legacy SMC signals.

- If the chosen symbol belongs to the replay, show its causal nodes in order.
- If it does not, render an explicit message: **no research replay signal; no legacy fallback used**.
- Defaulting a research K-line page should select a known replay symbol rather than an arbitrary production default such as a blue-chip ticker with no replay row.
- In EMPTY_BOOK, constrain the K-line selector to the approved research version/timeframe; remove legacy version options that imply availability.

## Verification matrix

After a restart, browser-smoke all routes, not only API endpoints:

| Surface | Expected EMPTY_BOOK result |
|---|---|
| `/`, `/backtest`, `/monitor`, `/live` | current epoch; zero production candidates/positions; no historical fallback |
| `/compare`, `/analysis`, `/autopsy`, `/resonance`, `/stoploss` | explicit production-empty notice; no historic metrics/rows |
| `/docs` | dynamic registry + research isolation, no old production instructions |
| `/logs` | current epoch/task state; old files clearly archived |
| `/effort-result` | populated read-only research metrics and replay rows; `NO_BUY` |
| `/kline?ver=<research>` | causal markers for a known replay symbol; explicit empty result for a non-member symbol |

Also assert `/api/summary`, `/api/picks`, `/api/live-prices` still report `EMPTY_BOOK`, zero BUY-valid rows, and no write flags.
