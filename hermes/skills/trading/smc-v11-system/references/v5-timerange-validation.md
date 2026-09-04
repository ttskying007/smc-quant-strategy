# V5 Timerange Backtest Results (2026-05-14)

## V5 Scanner (Final Matrix)

- **L1 OB_Bull**: Always enabled, independent. WR=93-98% (proven)
- **L2 ALL→ZONE**: Only in MeanReversion market state. ALL_START = LIQ(Sweep_SSL/EQL) + STRUCT(CHOCH_Bull/BOS_Bull/MSS_Bull) → ZONE(OB_Bull优先, FVG_Bull回退)
- **RR≥1 filter**: tpd/sld >= 1.0
- **Dedup by entry_bar**: (symbol, entry_bar) key, keep highest score
- **OB priority**: ZONE matching sorts OB_Bull first, then FVG_Bull

## Timerange Backtest (3088 bullish stocks)

| Period | Stocks | Trades | WR | PnLavg | PnLsum | PF | TP% | SL% | Hold |
|--------|--------|--------|-----|--------|--------|-----|------|-----|------|
| 2024-2025 | 2952 | 6577 | 91.2% | +3.81% | +25069% | 18.2 | 91.2% | 8.8% | 3.6b |
| 2026 | 1020 | 1178 | 93.7% | +3.96% | +4664% | 25.9 | 93.6% | 6.1% | 2.3b |
| Before22/2022-2023 | 0 | 0 | - | - | - | - | - | - | - |

Note: Before22 and 2022-2023 have 0 trades because 300-bar kline cache doesn't extend that far back.

## L1 vs L2 Breakdown

| Period | L1 OB_Bull | | L2 COMBO | |
|--------|-----------|----------|----------|----------|
| | Trades | WR/avg | Trades | WR/avg |
| 2024-2025 | 6055 | 93.6%/+4.00% | 522 | 63.6%/+1.58% |
| 2026 | 997 | 98.0%/+4.33% | 181 | 70.2%/+1.91% |

**Conclusion**: L1 OB_Bull is the dominant profit generator. L2 COMBOs add marginal value.

## L2 Signal Type Ranking

| Signal | Trades | WR | PnLavg | CumPnL |
|--------|--------|-----|--------|--------|
| BOS_Bull→FVG_Bull | 215 | 69.3% | +2.07% | +445.5% |
| CHOCH_Bull→FVG_Bull | 104 | 68.3% | +2.03% | +211.6% |
| EQL→FVG_Bull | 94 | 64.9% | +1.54% | +144.9% |
| Sweep_SSL→FVG_Bull | 237 | 62.4% | +1.28% | +303.8% |
| MSS_Bull→FVG_Bull | 53 | 56.6% | +1.19% | +63.1% |

## Market State Validation

| State | 2024-2025 WR | 2026 WR | L2 Active? |
|-------|-------------|---------|------------|
| mean_reversion | 87.7% | 85.4% | YES (L2 drags WR down) |
| transition | 94.0% | 98.0% | NO (pure L1) |
| expansion | 94.1% | 100.0% | NO (rare) |

Market state gating is CORRECT: L2 only activates in mean_reversion where baseline is lower. Transition/expansion states (high WR) keep pure L1.

## Script Reference

- Scanner: `/root/.hermes/scripts/v11/scan_LD_v5.py` (V5 market-state-driven, 87 picks)
- Timerange: `/root/.hermes/scripts/v11/backtest_timerange_v5.py`
- Results: `/root/.hermes/smc_opt_v21/backtest_timerange_v5.json`
- Picks: `/root/.hermes/smc_opt_v21/LD_picks_v5.json`

## Pitfall: find_tps/find_sls requires swings_dict

These functions in v19_backtest_engine.py access `swings_dict.get('highs', [])`. Passing `None` causes AttributeError. Always pass the swings_dict from `detect_all_signals_v20()`.
