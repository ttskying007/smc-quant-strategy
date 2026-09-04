# V27 second audit: 3-year window, signal definition, and frontend sync

Use this reference when SMC backtest/选股/K线图表 shows stale dates, inconsistent trade counts, or suspicious signal correctness after a core signal change.

## Durable lessons

1. **Backtest window must be enforced at K-line load time and frontend cache load time.**
   - Do not trust file `mtime` to select market data caches.
   - Pick cache files by the latest bar date inside the JSON, not by filesystem modification time.
   - Apply the rolling window cutoff before detection/backtest generation, and again when the frontend normalizes `trades`/`picks`.

2. **FVG direction is a definition-level invariant.**
   - Bullish FVG: current bar low is above the high two bars back: `l2 > h0`.
   - Bearish FVG: current bar high is below the low two bars back: `h2 < l0`.
   - Reversed indexing pollutes FVG itself plus BPR, setup explanations, selected-stock reason fields, chart overlays, and backtest distribution.

3. **BPR must not anchor backward.**
   - A BPR zone may only be attached to a structure event at or after the BPR formation index.
   - If no eligible structure event exists, discard that BPR for setup-building.
   - Never fallback to the previous structure event; that creates a future-zone leak into older setups.

4. **Win/loss contract must be recomputed from PnL.**
   - For V27-style outputs, normalize `won = pnl_pct > 0`.
   - Do not rely on stale/legacy `won` fields if output schema evolved.

5. **Cross-surface sync is part of the fix, not a separate UI task.**
   After any signal-definition or scan-output change, verify all surfaces use the same normalized dataset:
   - full scan output
   - `v27_trades.json`
   - `v27_picks.json`
   - metrics/summary JSON
   - frontend cache globals
   - `/api/summary`
   - `/api/kline_full`
   - selected-stock list
   - chart markers/tooltips
   - analysis/replay views

## Audit probes to run after fixes

Minimum expected checks:

```text
pre-window trades = 0
pre-window picks = 0
missing won = 0
won mismatch = 0
BPR backward/future anchor violations = 0
setup order violations = 0
```

For date windows, print both min/max from raw generated files and min/max from frontend API/cache. A successful backend fix is insufficient if the browser server still serves stale cached data.

## Typical code-level fixes

- In the scanner, replace mtime-based cache selection with bar-date-based cache selection.
- Add a rolling `BACKTEST_DAYS = 1095` or equivalent, derived from the newest available market-data date.
- Filter loaded K-lines by cutoff before signal detection.
- In the frontend server, normalize V27 trades/picks on load:
  - filter by the same cutoff
  - fill `won` from `pnl_pct`
  - keep picks synchronized with surviving trades/signals
- Ensure K-line endpoints and summary endpoints read from the same normalized cache.

## Failure pattern this prevents

A file such as `002450_SZ_daily_750.json` can contain bars from `20150819` to `20210528` while having a recent filesystem mtime. If code selects by mtime, old bars enter a supposedly recent backtest and produce 2016-era trades. This must be treated as a cache-selection bug, not as a trading-strategy result.
