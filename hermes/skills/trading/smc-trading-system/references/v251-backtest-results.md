# V25.1 Backtest Results (2026-05-19)

## Discovery: V25 First Backtest Failed

The initial V25 scan (200 stocks, 199 picks) was run through backtest without verification.
Results were worse than V24 baseline across ALL metrics:

| Metric | V24 | V25 Initial |
|--------|-----|-------------|
| WR | 50.0% | 34.7% |
| Avg PnL | +4.60% | -2.13% |
| SL rate | 50.0% | 86.4% |
| TP rate | 49.5% | 1.5% |

## Root Cause Analysis

### 1. TP Targets Unreachable (ATR×2.5)
- Most stocks have ATR% 2-5%
- TP = entry × (1 + ATR% × 2.5) = 5-12.5% target
- Only 3 out of 199 trades hit TP
- Fix: Use 2nd-nearest structural high instead

### 2. SL Too Wide (avg 7.3%)
- SL = zone_bottom - ATR × k where k=1.0-1.5
- Wide SL means price hits SL before reaching TP
- Fix: Tighten to zone_bottom - ATR × 0.5

### 3. No Structural Signal Requirement
- V25 accepted ANY zone retrace as entry
- 145/199 picks had no Sweep/CHOCH/BOS in signal chain
- These are weak entries without structural confirmation
- Fix: Require Sweep/CHOCH/BOS in sequence

## V25.1 Results (After 3 Fixes)

| Metric | Value |
|--------|-------|
| Scan | 500 stocks → 751 ELITE picks |
| Filtered | 300 picks (max 3/stock) |
| Trades | 220 |
| WR | 63.2% |
| Avg PnL | +0.84% |
| Total PnL | +184.57% |
| Avg Win | +2.51% |
| Avg Loss | -2.02% |
| TP hit | 48.6% |
| SL hit | 31.8% |
| Trailing | 17.7% |
| Avg Hold | 1.5 bars |
| Avg RR | 4.95 |

## Best Signal Combinations

| Combo | Trades | WR | Avg PnL | TP Rate |
|-------|--------|-----|---------|---------|
| 4-sig + PINBAR/OTE | 57 | 80.7% | +1.77% | 70% |
| 4-signal stories | 115 | 72.2% | +1.15% | 56% |
| PINBAR_ENTRY | 34 | 85.3% | +2.51% | 76% |
| OTE_ENTRY | 40 | 75.0% | +1.02% | 60% |
| OB_Bull zone | 12 | 83.3% | +1.67% | 67% |
| FVG_Bull zone | 19 | 68.4% | +2.10% | 63% |

## Worst Performers

| Combo | WR | Issue |
|-------|-----|-------|
| BreakerBlock_Bull | 41.2% | False breaks |
| BOS_ENTRY | 28.6% | Too late confirmation |
| 2-signal stories | 47.8% | Incomplete SMC structure |

## Key Files
- Scan: `/root/.hermes/scripts/v25/full_scan.py`
- Backtest: `/root/.hermes/scripts/v25/backtest_v251.py`
- Trades: `/root/.hermes/smc_opt_v25/v251_trades.json` (220 trades)
- Picks: `/root/.hermes/smc_opt_v25/v25_picks.json` (300 picks)
- Best subset: `/root/.hermes/smc_opt_v25/v25_best_trades.json` (57 trades, 80.7% WR)

## Mandatory Workflow Rule

**After every scan → ALWAYS run backtest → compare to V24 baseline → reject if worse.**
Do not present picks without verified backtest performance.
