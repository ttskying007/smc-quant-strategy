# Causal Replay and Intraday Data Contract

Use this reference whenever a backtest or SMC research branch appears to produce strong results from reclaim, takeover, hold, persistence, or multi-bar confirmation rules.

## 1. Non-negotiable causality rule

A feature may gate an entry only if it is fully observable **before** the decision/fill point.

Required order:

```text
source event → POI creation → first touch → reclaim / N-bar confirmation → next executable open → T+1 exit eligibility
```

If a label needs `N` completed bars after reclaim, the earliest allowed entry is the **next bar after confirmation**, never the historical reclaim bar or an earlier entry index.

### Mandatory row-level test

Materialize and audit these fields for every candidate:

| Field | Required relation |
|---|---|
| `event_idx` | `< zone_idx` or event-specific causal relation explicitly defined |
| `touch_idx` | `>= zone_idx` |
| `reclaim_idx` | `>= touch_idx` |
| `confirm_idx_n` | `= reclaim_idx + n` for an N-bar post-reclaim label |
| `entry_idx` | `> confirm_idx_n` |
| `exit_idx` | `> entry_idx` and on a later A-share trading date |

A negative `entry_idx - confirm_idx_n` is future-data contamination. Do not repair it with a disclaimer: invalidate every result that depends on the label.

## 2. V366 contamination pattern

The historical V132/V164-style takeover branch used features such as `takeover_2/3`, `bull_count_3`, hold, and pullback states that inspect the two or three bars after reclaim, while the historical rows had an earlier `entry_idx`.

The audit found 402/402 candidate rows entered two to three bars before their required confirmation. The apparent OOS performance was therefore invalid. This is the canonical example of why aggregate WR, OOS splits, or a successful source-field name cannot establish causality.

**Rule:** once this defect is found, downstream subsets, OOS reports, and parameter searches that use the contaminated field are research-invalid until regenerated from a causal entry index.

## 3. Historical intraday data contract

Do not build an MTF strategy from a provider sample, partial local cache, or an API that silently caps bars.

Before generator work, run two no-write gates over the full eligible universe and intended historical span:

### Gate A — raw 60min coverage

- Compare each local daily trading date to raw (`adjustflag=3`) 60min bars.
- Require exactly four A-share slots: `10:30`, `11:30`, `14:00`, `15:00`.
- Query intraday history in calendar-year chunks: providers may silently cap long multi-year requests.
- Treat provider errors, request timeouts, missing dates, duplicate/extra dates, and wrong slot counts as failures.
- Serial provider access is acceptable when concurrent sessions are unstable; a complete reliable audit is preferable to a fast partial one.

### Gate B — qfq price alignment

- Aggregate qfq (`adjustflag=2`) 60min OHLC by day and compare against the daily qfq series used by the backtest.
- For each day: open=first, high=max, low=min, close=last.
- Require a fixed, disclosed max OHLC deviation tolerance; retain failure rows and provider metadata.
- Do not claim price-level POI/reclaim compatibility until this passes.

## 4. Promotion sequence after both data gates pass

1. Build only a no-write candidate/lifecycle dataset.
2. Generate `daily POI → 60min touch → 60min reclaim/hold → next 60min open` entries with all timestamps retained.
3. Apply structural SL and pre-known liquidity targets; enforce T+1 in the replay.
4. Run the full-market multi-year replay against predeclared economic gates.
5. Independently re-derive the raw SMC objects and compare candidate coordinates/causality.
6. Perform row-level loss and execution audits before any watchlist, frontend, or production write.

## 5. Closure rule

If the new generator cannot pass causality, coverage, execution, and economic gates, declare the branch closed. Do not restart daily scalar filtering, exit-only optimization, or OOS mining unless there is genuinely new data or new scanner-time information.
