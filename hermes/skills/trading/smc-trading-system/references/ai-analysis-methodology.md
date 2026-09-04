# SMC AI Signal Quality Analysis Methodology

## Purpose
Systematic method to evaluate SMC signal quality across multiple dimensions using backtest data.

## Core Discovery (2026-05-15)
SMC context (liquidity sweep, structure break, swing point, FVG proximity) is the **#1 predictor of signal quality**.
The more SMC context confirmations a signal has, the higher its win rate:

```
Context Count  →  Win Rate
  ctx_0 (孤立)    42.3%  ← untradeable
  ctx_1          64.3%
  ctx_2          79.4%
  ctx_3          87.3%
  ctx_4          92.0%  ← best
```

This was discovered by sampling 1000 trades from V9 backtest and checking each signal for:
1. LIQ Sweep (Sweep_SSL/BSL) within 10 bars before signal
2. STRUCT break (CHOCH/BOS) within 15 bars before signal  
3. At swing point (signal bar within 2 bars of a swing high/low)
4. FVG nearby (within 5 bars)

## Analysis Dimensions

### 1. Signal Quality per Type
Run across all backtest trades, group by signal type:
- Win rate, avg PnL, avg SL, avg hold, TP hit rate
- Win/loss ratio (avgWin/avgLoss)
- Entry source breakdown (daily vs 60min)

### 2. Entry Timing Analysis
Classify entries:
- **Perfect**: PnL > 5% AND hold <= 3 bars (entry→profit fast)
- **Early**: PnL < -2% OR (PnL > 5% AND hold > 5 bars) — long drawdown
- **Late**: entry_bar close > signal zone midpoint — missed the best price

### 3. Exit Timing Analysis  
- **Too early**: Won but PnL < 3% — trailing activated too soon
- **Too late**: Lost — SL too wide or trailing not active
- **Good**: TP hit

### 4. SMC Context Analysis (most important)
For a sample of trades, load actual OHLCV data and check:
- Is there a liquidity sweep before the signal?
- Is there a structure break (CHOCH/BOS) before?
- Is the signal at a real swing point?
- Is there an FVG nearby?

Calculate WR for each context count level.

## Usage
```bash
cd /root/.hermes/scripts/v11
python3 ai_analysis_engine.py  # runs full analysis, saves to smc_opt_v9/analysis/
```

## Key Findings That Drive Decisions

1. **60min entries REDUCE quality**: OB_Bull daily entry WR=99.4% vs 60min entry WR=59.7%.
   - 60min noise corrupts the signal structure
   - 60min should only be used as supplementary confirmation, NOT primary entry

2. **FVG_Bull is unreliable without context**: Without SMC context, FVG WR=38.5%.
   Must require LIQ sweep or CHOCH before FVG entry.

3. **Sweep_SSL + OB_Bull is the best combo**: WR=97.5% when Sweep precedes OB.

4. **Isolated signals are untradeable**: ctx_0 WR=42.3% — never enter without context.

5. **TP is reachable on daily**: 22-42% TP hit rate on daily timeframe (was 0% on 60min V477).

## Engine Files
- `/root/.hermes/scripts/v11/ai_analysis_engine.py` — standalone analysis runner
- `/root/.hermes/smc_opt_v9/analysis/ai_analysis_report.json` — latest report
