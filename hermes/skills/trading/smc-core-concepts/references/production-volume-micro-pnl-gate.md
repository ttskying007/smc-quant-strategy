# SMC Production Promotion: Volume + Micro-PnL Gate

Use this reference when an SMC backtest/version looks high quality but the user challenges yearly trade count or notices many exits around `+0.5%`.

## Durable lesson

A high WR version is not promotable if it relies on synthetic breakeven / micro-profit exits.

In the V152→V156 iteration, V152 initially looked strong:

| Version | n | WR | Avg | micro 0.45–0.55% | synthetic BE | min yearly n |
|---|---:|---:|---:|---:|---:|---:|
| V152 | 127 | 92.91% | 2.9407% | 40 / 127 = 31.50% | 44 | 19 |

User correctly rejected it because:

1. Annual trade count was too low.
2. Many PnLs clustered near `+0.5%`.
3. Those `+0.5%` exits came from BE_SL / lifecycle synthetic exits, not SMC structure targets.

Conclusion: **synthetic BE/micro-profit exits are diagnostic risk controls, not production wins.** They must not inflate WR for promotion.

## Required promotion checks

Before calling any SMC version promotable, add these gates in addition to WR/Avg/T+1:

| Gate | Requirement |
|---|---|
| Multi-year volume | total `n` and per-year `n`; reject low-frequency subsets as production |
| Micro-PnL cluster | count PnL in `[0.45%, 0.55%]`; explain natural vs synthetic |
| Synthetic BE exits | `BE_SL`, `BREAKEVEN`, lifecycle forced micro-profit exits must be `0` for production, or explicitly excluded from WR |
| Year split | every year must pass minimum n and minimum WR |
| Rolling windows | recent 30/60/90 trades must pass sanity WR/Avg |
| Weak months | identify months with `n>=3` and `WR<70` or `Avg<0`; do root-cause audit |
| T+1 | zero same-day exits |

Example V154 candidate gate used after rejecting V152:

```text
n >= 240
min_year_n >= 35
synthetic_be_n == 0
micro_pct <= 1%
WR >= 82%
Avg >= 3.2%
T+1 violations == 0
```

## Repair pattern when micro-PnL is found

Do **not** tune around the 0.5% cluster. First separate real structure exits from synthetic exits.

1. Tag every row:
   - `micro_pnl = 0.45 <= pnl_pct <= 0.55`
   - `synthetic_be = lifecycle_action startswith BE_SL or exit_reason contains BREAKEVEN/BE_SL`
2. Recompute metrics with synthetic BE rows excluded or with original baseline exits restored.
3. Restore volume by adding back structurally justified rows, not by reintroducing BE exits.
4. Compare:
   - baseline all rows
   - high-WR synthetic version
   - no-synthetic repair
   - add-back variants
5. Pick candidate by volume + no-synthetic constraints, not by WR alone.

## V152→V154 example

V152 rejected:

| Version | n | WR | Avg | micro_n | synthetic_BE | year counts |
|---|---:|---:|---:|---:|---:|---|
| V152 | 127 | 92.91% | 2.9407% | 40 | 44 | 25/49/34/19 |

V153 repair:

```text
No BE_SL synthetic exits
Restore PRE_BUY_GAP rows
Drop CANCEL_AFTER_ENTRY_DAY_CLOSE weak bucket
Use original baseline exits only
```

| Version | n | WR | Avg | micro_n | synthetic_BE | year counts |
|---|---:|---:|---:|---:|---:|---|
| V153 | 221 | 83.26% | 3.3327% | 2 | 0 | 61/84/42/34 |

V154 add-back:

```text
ADD_CANCEL_RECLAIM_POS_GE_81_7
```

Reason: among weak `CANCEL_AFTER_ENTRY_DAY_CLOSE` rows, high reclaim close position indicates the candle still recovered toward the upper range; this is a structural recovery subset, not synthetic exit manipulation.

| Version | n | WR | Avg | micro_n | synthetic_BE | year counts |
|---|---:|---:|---:|---:|---:|---|
| V154 | 247 | 82.59% | 3.2709% | 2 | 0 | 63/96/53/35 |

## Stability audit pattern

After a no-synthetic candidate passes overall metrics, run stability audit before production:

1. Yearly metrics.
2. Monthly metrics.
3. Rolling tail 30/60/90/120 trades.
4. Weak-month table.
5. Per-loss root cause for weak months.

V155 found V154 still failed production stability because 2024 was weak:

| Year | n | WR | Avg |
|---|---:|---:|---:|
| 2023 | 63 | 87.30% | 3.4659% |
| 2024 | 96 | 75.00% | 2.4352% |
| 2025 | 53 | 90.57% | 4.3116% |
| 2026 | 35 | 82.86% | 3.6361% |

Release gate failed on `all_year_wr_ge_78`.

## Market breadth caution

V156 tested broad-market breadth gates. They improved WR but cut yearly coverage too much, so they remained research-only.

Do not add generic market breadth as a production gate unless it is reconciled with the user's SMC preference for pure structure logic and preserves yearly volume.

## Reporting to Lei

Use compact tables and explicit decisions:

- `废弃`: if high WR depends on synthetic BE/micro exits.
- `研究候选`: if overall metrics pass but yearly/monthly stability fails.
- `可进入下一轮审计`: if no-synthetic, volume, yearly, rolling gates pass.
- `生产晋级`: only after scanner/API/frontend/watchlist closure also passes.

Never call a version complete just because aggregate WR is high.
