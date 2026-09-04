# Production API Closure vs Strategy Backtest Closure

Use this reference when an SMC session fixes frontend/API/current-pick pollution and the user asks whether the whole strategy loop is done.

## Core Lesson

Do not confuse **production display/API correctness** with **strategy correctness**.

A repair can be fully complete for current production routing while the trading model still fails semantic or backtest promotion gates.

## What Counts as Production/API Closure

Production/API closure is proven by direct hot-path evidence:

- `/api/picks` rows come from the latest full-market scanner or real monitor state, not historical completed trades.
- `/api/picks` has no completed-outcome pollution: no `exit_date`, `net_pnl_pct`, stale `exit_reason`, or realized `hold_bars` on current candidates.
- `/api/live-prices` separates tradable live rows from observation context rows.
- WATCH_ONLY rows use context status such as `WATCH_ONLY_CONTEXT`, `isTradableLive=false`, `tradable=false`, and do not compute live PnL/SL/TP state.
- Contract endpoint separates `tradable_active_pick_count`, `watch_only_count`, and raw pick file count.
- Daily completeness and release gates pass for freshness, T+1, field contract, provenance, and pollution checks.

If these pass, say production/API routing is closed — not that the strategy is promoted.

## What Does NOT Count as Strategy Closure

The following are insufficient for strategy promotion:

- Old V100/V102/V103-style backtest artifacts generated before API/routing repairs.
- High aggregate WR/RR when sequence semantics are not clean.
- Release gate pass alone; release gate proves checked operational contracts, not Pine/LuxAlgo signal correctness.
- Current daily scanner returning zero tradable active candidates; there is no new candidate cohort to backtest.

## Mandatory Strategy Closure Checks

Before saying the strategy itself is done, rerun the strategy loop after the latest semantic changes and report:

1. Full-market, multi-year backtest from the current generator, not historical representative trades.
2. Monthly table: trades, WR, avg net, SL rate, anomaly months, low-sample months.
3. Per-trade audit trail: `sweep_idx/event_idx/touch_idx/reclaim_idx/entry_idx/exit_idx` and dates.
4. Sequence gates: `entry_before_sweep=0`, `entry_before_event=0`, `entry_before_touch=0`, `entry_before_reclaim=0`, same-day exit/buy violations = 0.
5. Combo split: reversal and continuation evaluated separately; do not let continuation inherit reversal SMC justification.
6. Interval analysis: sweep→event, event→touch, touch→reclaim, reclaim→entry, touch→entry.
7. Entry quality: entry must be after the required confirmation (`entry_idx > reclaim_idx` for reclaim-confirmed systems) unless the system explicitly labels itself as touch-entry and validates that separately.
8. SL/TP correctness: structure-based SL and liquidity/BSL/EQH target semantics rechecked after any entry change.

## Pitfall: Reclaim Semantics

If a model claims "touch → reclaim → entry" but audit shows `entry_idx < reclaim_idx`, the model is not reclaim-confirmed. It is a touch/anticipation entry model and must not be reported as strict SMC reaction-confirmed entry.

For example, if most trades have `reclaim_to_entry` negative, the headline WR/RR is not valid evidence for a reclaim-confirmed production system. The next version must enforce `entry_idx > reclaim_idx`, rerun full-market backtest, then re-audit monthly and per-trade behavior.

## Reporting Pattern for Lei

Use a compact table with three sections:

- **Solved**: operational/API closure backed by endpoint/file/gate counts.
- **Not solved**: strategy/backtest/semantic closure gaps backed by failing counts.
- **Next closure loop**: exact generator/version to rebuild, gates to add, and pass criteria.

Never say "done" if only the production API layer is done.