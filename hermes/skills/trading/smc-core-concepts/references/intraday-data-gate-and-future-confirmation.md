# Intraday Data Gate & Future-Confirmation Rejection

Use when a daily SMC branch is exhausted and the next proposed edge is a 15/60-minute confirmation, reclaim, takeover, or hold condition.

## Predeclared promotion gate

A candidate must satisfy all of these before shadow/production consideration:

| Dimension | Required check |
|---|---|
| Causality | Each selector is observable no later than `confirm_idx`; `entry_idx >= confirm_idx + 1`. |
| Historical coverage | Full intended SH/SZ universe and analysis range; compare intraday dates to each symbol's own available daily dates. |
| Intraday sessions | Every expected day has exactly four 60m terminal bars: `10:30`, `11:30`, `14:00`, `15:00`. |
| Price convention | Raw and QFQ cannot be mixed. Aggregate QFQ intraday OHLC and compare to the daily QFQ series before zone/touch/SL work. |
| Execution | Entry is the next executable intraday open after confirmation; A-share exits start on the next trading day. |
| Economics | Use the predeclared full-market annual coverage/WR/PnL gate, never a gate selected after outcome mining. |

## Mandatory source sequence

1. **Raw coverage audit first.** Query historical intraday data by calendar-year chunks; providers may silently cap multi-year replies.
2. Compare each symbol's returned dates and slots against that symbol's daily-cache dates; IPOs are not missing history.
3. A limited probe proves provider feasibility only. It never unlocks a full-universe generator. The coverage report must cover the complete target universe (not a sample).
4. **QFQ alignment second.** Aggregate four intraday bars to daily OHLC and retain all date-level deviations. A mismatch blocks price-level POI/reclaim research.
5. Build the lifecycle only after both gates pass: `daily event/fresh POI → 60m touch → reclaim/hold confirmation → next 60m open → T+1 replay`.
6. Independently re-derive all event, POI, touch, reclaim, confirmation, entry, and exit indexes before interpreting returns.

## Future-confirmation pitfall

A label such as `takeover_2`, `takeover_3`, `bull_count_3`, post-reclaim hold, or post-reclaim pullback requires later completed bars. It cannot filter an earlier entry.

Required row-level contract:

```text
source event → POI → touch → reclaim → N completed confirmation bars → next executable open → T+1 exit
```

For every N-bar condition, save `confirm_idx_n = reclaim_idx + N` and reject rows where `entry_idx <= confirm_idx_n`. If a historical branch entered before the confirmation it used, invalidate the entire dependent result family—including OOS splits and high-WR subsets—rather than patching the report with a caveat.

## Session outcome that motivated this gate

A historical takeover branch had 402/402 rows entering two or three bars before its required confirmation fields. Its apparent OOS performance was therefore invalid evidence. This is a reusable audit pattern, not a parameter issue.

## Non-goals

- Do not restart daily scalar filtering, exit-only optimization, or outcome-derived rule mining after this gate fails.
- Do not create a watchlist, frontend payload, trade, or PnL artifact during source/semantic audits.
