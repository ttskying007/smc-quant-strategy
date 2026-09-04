# Scanner universe completeness vs causal funnel filtering

## Trigger

Use whenever the user asks “扫描是不是被过滤掉一部分了 / 算不算完整的全市场扫描” or when a current scanner shows a funnel that drops thousands of symbols before any setup. Do NOT answer from aggregate numbers alone — prove completeness per file.

## Core distinction

Two different kinds of “filtering” must never be conflated:

1. **Universe / data-availability filtering** — symbols missing from the scan input, or present but with no bar on the committed market date. This is a data-plane fact and must be enumerated and categorized.
2. **Causal signal filtering** — symbols that HAVE fresh data but fail a defined stage of the signal chain (no confirmed swing, no SSL breach, no reclaim, volume rank below top-quintile, no response break). This is the strategy contract, not a bug and not a universe cut.

A scan is “full market” when its input universe is the complete canonical cache (`files_seen == total cached files`) and every stage in the funnel has a documented causal rule matching the frozen research contract.

## Proof procedure (all per-file, no aggregates)

1. **Input universe.** Confirm the scanner iterates the full cache glob (`*_daily_750.json`) and record `files_seen` vs total files. Verify the refresh gate values from the committed epoch manifest: request coverage (≥90%) and current-date coverage (≥99%).
2. **Enumerate stale files.** List every file whose last bar ≠ committed market date. For each, record its last-bar date. Categorize: long suspension (weeks/months) vs delisted (years stale). Suspended/delisted symbols have no tradable bar on the day — excluding them is correct, and counting them as “missed” would be wrong.
3. **Enumerate fresh-without-structure.** For each fresh file that produced no diagnostic row (or stopped at an early stage), check bar count and first-bar date:
   - new listings with < swing window + lookback bars (e.g. ~26+ bars) cannot form a confirmed swing — structural exclusion, not data loss;
   - old files with full history but no row mean the nearest prior low is consumed (mitigated) or lacks right confirmation — signal definition working as intended.
4. **Reconcile funnel arithmetic.** Every stage count must equal the sum of the next-stage counts plus the rows stopped at that stage with `furthest_stage` labels. If the scanner persists partial rows, use them for this; a funnel that does not add up is a real defect.
5. **Show the causal chain, not just the top count.** E.g. full market → fresh-on-date → confirmed-unmitigated SSL → SSL breach ≥0.3% → sweep reclaim → volume top-quintile → response break → full setup. Each arrow has a fixed parameter from the frozen contract.
6. **Verify scanner-time boundary.** Scanners that only emit when `response_date == committed market_date` (anti-lookahead) will NOT re-emit a setup from an earlier date if the cron missed that day. That is a deliberate trade-off — state it, don't hide it. Zero full setups on a given day is a legitimate market outcome; verify the few rows nearest the final stage (e.g. high-volume reclaims) individually and show why they failed the last condition.

## Funnel arithmetic reconciliation recipe

The scanner's `diagnostic_funnel` object usually exposes only the cumulative stage counts (fresh → confirmed_swing → ssl_breach → sweep_reclaim → high_volume → response_break → full). The "stopped at each stage" counts that make the funnel provably additive are recovered by classifying the persisted partial rows:

```python
from collections import Counter
c = Counter(r['furthest_stage'] for r in rows)          # stopped-at-stage counts
```

Then reconcile every arrow: each stage count must equal its stopped-at count plus the next stage count, and the last stage's count must equal its stopped-at count (0 remaining). Do this in code and report the additions — a funnel that does not add up is a real defect. With `furthest_stage` values named `CONFIRMED_SWING_LOW`, `SSL_BREACH`, `SWEEP_RECLAIM`, `HIGH_VOLUME_SWEEP_RECLAIM`, the 20260803 example reconciles as:

```text
4886 fresh = 4852 stopped at CONFIRMED_SWING_LOW + 34 reached SSL_BREACH
34        = 4 stopped at SSL_BREACH + 30 reached SWEEP_RECLAIM (≠ funnel 14 — see pitfall)
funnel ssl_breach 18 = 4 stopped + 14 sweep_reclaim ✓
funnel sweep_reclaim 14 = 11 stopped + 3 high_volume ✓
funnel high_volume 3 = 3 stopped + 0 response_break ✓
```

**Pitfall — label arithmetic vs funnel counts diverge.** `furthest_stage` labels mark where a row *stopped*, so the label-derived intermediate sums (34, 30) include rows that passed the stage and stopped later; they must NOT equal the funnel's stage counts. Only the funnel counts themselves reconcile arithmetically (`18 = 4 + 14`, `14 = 11 + 3`). Present the funnel counts as the proof, and use the label Counter only to recover the stopped-at numbers that explain them.

## Verify the final-stage rows individually

For the rows nearest the final stage (e.g. the high-volume reclaims), print each one's `sweep_high`, `response_close`, and `next_required`, and show why each failed the last condition. 20260803:

```text
002569.SZ  sweep_high 12.87  response_close 12.60  next RESPONSE_CLOSE_BREAKS_SWEEP_HIGH (miss 2.1%)
300955.SZ  sweep_high 32.48  response_close 29.40  (miss 9.5%)
603309.SH  sweep_high 11.49  response_close 11.34  (miss 1.3%)
```

## Concrete evidence pattern (V521, 20260803)

```text
files_seen 4905 == total cache files
fresh on committed date 4886 (99.61% — refresh gate ≥99%)
stale 19: all suspended/delisted (last bars 20210528…20260731)
fresh without confirmed swing low 16:
  7 new listings (71–273 bars, listed 2025-10..2026-04)
  9 full-history (750 bars) with consumed/no-right-confirmation low
funnel: 4886 → 4870 confirmed SSL → 18 SSL breach (4 no reclaim + 11 low-vol + 3 high-vol)
        → 14 reclaim → 3 high-volume → 0 response break → 0 full setup
3 high-volume rows (002569/300955/603309): response close < sweep high, individually verified
```

Conclusion pattern: “不是被过滤掉 — 19 只是停牌/退市，16 只是结构上无信号可产生，漏斗各级都是信号定义。全市场扫描=输入宇宙完整 + 过滤全是因果过滤。”

## User expectation

Lei's question “这样是不是被过滤掉一部分了” is a completeness challenge: answer with per-symbol enumeration (last-bar dates, bar counts, stage labels), a funnel that reconciles arithmetically, and the concrete rows that stopped at the final stage — never with a bare funnel table.
