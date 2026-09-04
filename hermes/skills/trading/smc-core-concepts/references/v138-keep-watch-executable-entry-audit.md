# V138 KEEP_WATCH executable entry audit lesson

Use when KEEP_WATCH / shadow candidates look promising but are not yet production BUY.

## Pattern

1. Start from lifecycle/shadow rows, not production watchlist.
2. Preserve `tradable=false`, `buy_enabled=false`, `trade_action=NO_BUY` until executable semantics pass.
3. Test executable entry modes separately:
   - `RECLAIM_NEXT_OPEN`: reclaim candle close is known; next open is executable.
   - `T2_NEXT_OPEN`: wait for `true_takeover_2`, then next open.
   - `T3_NEXT_OPEN`: wait for strict takeover 3, then next open.
4. Enforce A-share T+1 by forbidding exits on the entry bar/date.
5. Report MFE/MAE, exit reason, chase above zone, market-state split, and recent slice.
6. Do not promote solely because delayed confirmation has stronger labels; verify if it worsens entry price and MAE.

## V138 finding (2026-06-20)

For V137 KEEP_WATCH_STRONG_SHADOW rows, executable audit showed:

| mode | n | WR | AvgPnL | AvgMFE | AvgMAE |
|---|---:|---:|---:|---:|---:|
| RECLAIM_NEXT_OPEN | 408 | 77.70% | +2.3875% | +17.9441% | -5.2687% |
| T2_NEXT_OPEN | 408 | 66.42% | +0.7066% | +15.3908% | -7.3822% |
| T3_NEXT_OPEN | 236 | 68.22% | +0.6087% | +15.0991% | -7.5831% |

`RECLAIM_NEXT_OPEN` was best. Waiting for T2/T3 confirmation increased chase/MAE and reduced PnL. No T+1 violations.

No-MIXED / no-chase subset:

| mode | n | WR | AvgPnL |
|---|---:|---:|---:|
| RECLAIM_NEXT_OPEN | 273 | 80.22% | +2.9981% |
| T2_NEXT_OPEN | 171 | 68.42% | +0.8562% |
| T3_NEXT_OPEN | 79 | 65.82% | +0.9570% |

Conclusion: the correct next research direction is not adding more takeover delay; it is tightening the reclaim-next-open candidate layer and replacing weak exit semantics, because current quality is still below production BUY standard.
