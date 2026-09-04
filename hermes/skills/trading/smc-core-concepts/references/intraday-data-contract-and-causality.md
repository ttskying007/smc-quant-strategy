# Intraday Data Contract and Causality Closure

Use when an SMC research direction requires 15m/60m refinement after daily-signal research has plateaued.

## 1. Do not treat an intraday API response as usable history

Before building signals, entries, or PnL, run a full-universe data contract:

- Define the eligible daily universe and date range.
- For every expected daily date, require all four A-share 60m slots: `10:30`, `11:30`, `14:00`, `15:00`.
- Fetch capped providers in calendar-year chunks; a single multi-year Baostock query silently truncates near 1,500 bars.
- Separate source/session errors from actual missing bars. Baostock sessions can return `10001001 用户未登录` mid-run; retry the *same chunk* after re-login before declaring coverage failure.
- Persist only audit artifacts until source coverage passes. Never create strategy/production/watchlist output from partial intraday history.

A valid source pass requires 100% eligible-symbol/date coverage, no unexpected slots, no silent truncation, and explicit per-year coverage.

## 2. Price convention is a mandatory contract

A daily POI and intraday touch cannot be mixed across raw and adjusted prices.

- Existing Tencent `qfq` daily cache is not directly compatible with Baostock raw (`adjustflag=3`) intraday bars.
- The raw-to-qfq multiplier varies through time around corporate actions; a single per-symbol scaling factor is invalid.
- Baostock `adjustflag=2` aggregated intraday OHLC empirically aligns with Tencent qfq daily OHLC closely enough for a **qfq-aligned research layer**.
- Raw intraday (`adjustflag=3`) belongs in a separate **raw execution-validation layer**, together with raw daily bars and corporate-action discontinuity handling.

Required preflight: aggregate 60m OHLC by day and compare with the daily POI source on early/mid/recent dates across varied symbols. Isolate rows whose convention or daily aggregation does not align.

## 3. QFQ is not automatically a production-causality proof

QFQ may be useful for compatibility with the existing daily research system, but corporate-action adjustments can alter historical structure boundaries. A production claim requires a raw-vs-qfq structural differential audit:

- Re-derive event/POI ordering in both representations.
- Flag events whose existence, order, or zone geometry changes across the adjustment boundary.
- Do not promote those rows until the raw executable model independently validates them.

## 4. Entry-time causality is non-negotiable

For a proposed sequence:

`daily fresh POI → intraday first touch → intraday reclaim/hold → entry`

- `entry_idx` must be strictly after every confirmation bar used by the selector.
- Execute only at the next tradable-bar open after confirmation.
- Never use post-entry `takeover_2`, `takeover_3`, `bull_count_3`, hold, pullback, MFE/MAE, or outcome fields as entry gates.
- For A shares, apply T+1 exits and conservative same-bar SL/TP ordering.

## 5. Critical historical pitfall: apparent OOS can still leak

A historical V132/V164-style reclaim study had every apparent survivor enter two to three bars **before** its required takeover confirmation. The issue survived a superficial OOS split because the leakage was in feature timing, not train/test membership.

Therefore a chronological OOS result is insufficient. It must be preceded by a row-level check:

`event_idx → zone_idx → touch_idx → reclaim_idx → confirm_idx → entry_idx → exit_idx`

and report counts for every negative or zero-invalid delta.

## Promotion sequence

1. Full-universe intraday source coverage pass.
2. Daily/intraday price-convention alignment pass.
3. Raw-vs-qfq structural differential audit.
4. Causal next-open MTF replay with T+1.
5. Fixed economic gate + chronological OOS + independent semantic re-derivation.
6. Only then shadow watchlist/front-end integration.
