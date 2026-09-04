# V107C TRADEABLE_REGIME Re-derivation Lesson

Use this reference when continuing SMC strategy-body research after strict `touch -> reclaim -> next-open entry` systems fail production stability, especially when the user asks for market-state / signal-semantic re-derivation rather than TP/SL tuning.

## Durable lesson

V107 proved the market-state layer is the right direction, but V107/V107B initially used `*_daily_300.json` for full-market breadth. That under-covered 2023/2024 and produced distorted BEAR_STRESS/MIXED_CHOP attribution. V107C corrected the regime layer by using `*_daily_750.json` plus winsorized/median market breadth.

## Correct V107C data-source pattern

- Use raw strict-reclaim trades as the signal substrate, not historical active-pick artifacts.
- Use `kline_cache/*_daily_750.json` for full-market market-state breadth.
- For each `entry_date`, compute only ex-ante universe stats at or before that date:
  - `up20_pct`, `up60_pct`
  - `ret20_pos_pct`, `ret60_pos_pct`
  - winsorized average `ret20/ret60`
  - median `ret20/ret60`
- Avoid `*_daily_300.json` for multi-year regime attribution; it may truncate early-year market state.
- Keep structural TP/SL unchanged while testing market-state validity. If the result fails, do not tune TP/SL to force promotion.

## V107C gate result

Full substrate: V104 strict reclaim, 487 trades, structural TP/SL unchanged.

| Regime | n | WR | SL | Avg | Median | Months | Stable3 | Judgement |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| BULL_EXPANSION | 147 | 72.11% | 25.85% | 2.5167% | 5.5687% | 11 | 4 | Direction works, not production-stable |
| BULL_RECOVERY | 96 | 46.88% | 52.08% | -0.4741% | -3.9072% | 14 | 2 | Not tradable |
| MIXED_CHOP | 25 | 52.00% | 40.00% | -0.0278% | 3.8339% | 7 | 2 | Not a special tradable state |
| NO_TRADE_BEAR_STRESS | 101 | 48.51% | 49.51% | -0.4382% | -1.4586% | 17 | 4 | Hard skip |
| REPAIRABLE_RANGE | 118 | 44.92% | 51.69% | -0.6155% | -4.1806% | 17 | 4 | Not tradable |

Production gate remains failed because no rule simultaneously satisfied sufficient sample size, WR/SL, and monthly stability.

## BULL_EXPANSION internal findings

| Split | n | WR | SL | Avg | Months | Stable3 | Lesson |
|---|---:|---:|---:|---:|---:|---:|---|
| BULL_EXPANSION_BASE | 147 | 72.11% | 25.85% | 2.5167% | 11 | 4 | Market-state layer is useful but not enough |
| TREND_UP_only | 60 | 86.67% | 13.33% | 4.2802% | 8 | 3 | High-quality but too small |
| retrace_20_40 | 52 | 82.69% | 15.38% | 3.9291% | 11 | 4 | Best semantic zone, still not enough |
| TREND_UP_retrace_20_40 | 19 | 94.74% | 5.26% | 5.3834% | 6 | 3 | Too small; research only |
| CONTINUATION_retrace_20_40 | 40 | 82.50% | 17.50% | 3.7740% | 10 | 4 | Research candidate only |

Primary remaining failure mode inside BULL_EXPANSION:
- `RANGE_TRANSITION`: n=87, WR 62.07%, SL 34.48% — false/immature structure inside otherwise bullish breadth.
- `event_to_entry 5-8`: n=36, WR 55.56%, SL 41.67% — too-early confirmation / unstable timing bucket.

## MIXED_CHOP correction

V107B suggested MIXED_CHOP 16 trades had 93.75% WR. After V107C fixed breadth with `daily_750`, MIXED_CHOP became 25 trades with WR 52% and SL 40%. Treat the earlier high-WR result as sample/data-source artifact, not a production hypothesis.

## BEAR_STRESS hard-skip evidence

2023/2024 NO_TRADE_BEAR_STRESS after V107C:
- n=75
- WR=44.0%
- SL=53.33%
- Avg=-1.0167%
- market breadth averages: up20=26.37%, up60=25.64%, median_ret20=-6.555%, median_ret60=-6.9424%

This is a market-state failure, not an exit-parameter failure. Do not try to rescue it with TP/SL tuning.

## Next-step direction

Do not connect V107 artifacts to production. Keep production on the current clean scanner/watchlist path unless a fresh full-market strategy gate passes.

Next research class should be V108-style signal semantics inside BULL_EXPANSION:
1. Split `TREND_UP` vs `RANGE_TRANSITION` and explain the structure difference.
2. Identify why `RANGE_TRANSITION` produces pseudo-structure despite bullish breadth.
3. Re-audit `event_to_entry 5-8` timing for early/weak reclaim confirmations.
4. Preserve structural TP/SL while testing the semantic gate.
5. Only consider production routing if the fresh full-market gate passes with adequate n and monthly stability.
