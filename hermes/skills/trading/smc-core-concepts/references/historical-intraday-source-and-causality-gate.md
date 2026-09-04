# Historical Intraday Source & Causality Gate

Use before promoting any daily+intraday SMC entry model or interpreting a high-WR intraday backtest.

## Why this gate exists

A current/recent intraday cache cannot validate a multi-year strategy. A signal can also look excellent if it enters before the bars required to confirm it. Treat both as release blockers, not minor caveats.

## Required order

1. **Define the acceptance gate before data work**
   - Causality: every selector field is visible no later than `confirm_idx`; entry must be strictly later.
   - Coverage: full target universe and every target year; do not replace missing years with a right-edge sample.
   - Execution: actual next-bar open after confirmation; A-share exit must remain T+1.
   - Economics: use fixed sample/annual coverage/WR/PnL thresholds established before rule search.

2. **Audit the source before building a generator**
   - Query intraday history in bounded calendar chunks. Providers may silently cap a multi-year response.
   - Compare every intraday day against the daily source: expected trading dates, four A-share 60m slots (`10:30`, `11:30`, `14:00`, `15:00`), missing dates, and duplicate/partial days.
   - Save only audit artifacts until coverage passes. Do not overwrite production caches or watchlists.

3. **Establish a price-convention contract**
   - Raw and forward-adjusted prices must never be mixed for POI touch, reclaim, SL, or TP.
   - Aggregate the four intraday bars to OHLC per day and compare with the daily source. Isolate symbols/dates exceeding a predefined deviation threshold.
   - QFQ-aligned research may reproduce an existing QFQ daily model, but it is not proof of raw executable-price correctness. Add a separate raw-vs-QFQ structure-differential audit before production promotion.

4. **Build the intraday lifecycle only after source pass**
   - `daily event / fresh POI → 60m first touch → 60m reclaim/hold confirmation → next 60m open entry → T+1 exit replay`.
   - Never use the close/high/low of the entry bar to establish its own confirmation.
   - Materialize `event_idx`, `zone_idx`, `touch_idx`, `reclaim_idx`, `confirm_idx`, and `entry_idx`; reject `entry_idx <= confirm_idx`.

5. **Independently re-derive the lifecycle**
   - Recompute confirmation from raw bars in a separate audit.
   - Report counts where an entry precedes any required 1/2/3-bar takeover condition.
   - If a historical row was entered before a required later confirmation, invalidate that whole result family; OOS metrics do not repair future-data contamination.

## Provider findings to re-test, not assume

- Tencent 60m requests can return only a short recent window even when a large bar count or historic date range is requested. Always inspect first/last timestamps and actual bar count.
- Baostock `frequency='60'` can supply historic SH/SZ data, but multi-year requests may cap/truncate; use calendar-year chunks and validate each response. Validate actual coverage before using it as a source.
- Baostock raw (`adjustflag=3`) and QFQ (`adjustflag=2`) have different roles: raw for eventual executable-price validation, QFQ only for alignment with an existing QFQ daily stack.

## Legacy-model review pitfall

Some older intraday models wait for an intraday confirmation but enter at the next daily open. This may be conservative in latency but is not the requested next-60m execution contract and must not be reused as validation of a true intraday entry model.

## Minimal evidence bundle

- Full-universe per-symbol coverage rows, including expected vs actual dates and slots.
- QFQ daily/intraday aggregate alignment rows and threshold failures.
- Raw-vs-QFQ event/POI ordering differential.
- Per-trade lifecycle index chain and T+1 audit.
- Fixed-gate chronological OOS results; no outcome-derived feature selection.
