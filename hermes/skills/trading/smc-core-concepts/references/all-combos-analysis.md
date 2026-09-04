# SMC All Combos Analysis (2026-05-14)

## 全量信号组合回测 (586 combo, 30-day window)

ALL combo types are profitable. Earlier theory that STRUCT should not be a start point was disproven by data.

### Chain Type Performance

| Chain | Count | WR | avgPnL | cumPnL |
|-------|-------|-----|--------|--------|
| CHOCH_Bull→FVG_Bull | 99 | 83.8% | +2.57% | +254.2% |
| MSS_Bull→FVG_Bull | 165 | 80.0% | +1.93% | +318.5% |
| BOS_Bull→FVG_Bull | 186 | 78.5% | +1.82% | +339.4% |
| Sweep_SSL→FVG_Bull | 128 | 78.1% | +1.92% | +245.4% |
| Sweep_SSL→OB_Bull | 8 | 100.0% | +4.54% | +36.3% |

Note: EQL→FVG and EQL→OB combos had 0 trades in 30-day window (rare). 
OB_Bull combos are extremely rare (always same-bar as LIQ) but 100% WR when they occur.

### By Start Signal Type

| Start Type | Count | WR | avgPnL |
|------------|-------|-----|--------|
| CHOCH_Bull | 99 | 83.8% | +2.57% |
| MSS_Bull | 165 | 80.0% | +1.93% |
| Sweep_SSL | 136 | 79.4% | +2.07% |
| BOS_Bull | 186 | 78.5% | +1.82% |

### By Gap (bar interval between signals)

| Gap | Count | WR | avgPnL |
|-----|-------|-----|--------|
| gap=1 | 108 | 86.1% | +2.73% |
| gap=2 | 63 | 84.1% | +1.99% |
| gap=3 | 61 | 78.7% | +1.45% |
| gap=4 | 29 | 69.0% | +1.10% |
| gap=5 | 38 | 76.3% | +1.45% |
| gap=6-10 | 177 | 86.4% | +2.92% | ← BEST |
| gap=11+ | 110 | 66.4% | +0.74% |

Key: gap=6-10 is optimal (not gap=1 as previously assumed).
gap=1-2 also strong (84-86% WR).

### V5 Full Backtest (all history, 3369 stocks)

| Tier | Count | WR | avgPnL | cumPnL |
|------|-------|-----|--------|--------|
| L1 OB_Bull | 6090 | 95.3% | +4.09% | +24,888% |
| L2 ALL→FVG | 292 | 59.2% | +0.96% | +279.3% |
| Combined | 6382 | 93.6% | +3.94% | +25,167% |

Market states: Transition 73%, Mean Reversion 27%, Expansion 0% (never in A-share history).

## Critical Bugs Found & Fixed

1. **TP/SL bar-by-bar walk-forward**: Monitor only checked last bar, missing intermediate hits. Fixed: traverse all bars from entry to now.
2. **OB_Bull same-bar as LIQ**: OB cannot participate in sequences (always co-located with EQL/Sweep_SSL). OB is standalone strategy.
3. **liq_bar field missing**: Scan omitted liq_bar/liq_type fields from output dict. Fixed.
4. **Dedup by entry_bar needed**: Multiple LIQ sources pointing to same FVG created duplicate picks.

## Key Findings

- L2 strategy profitable long-term (59.2% WR full history) but in drawdown recently (4% WR 30-day)
- 300-day window confirms profitability (55.2% WR, +0.93% avg)
- Market state gating (V5) correctly handles regime shifts
- V19 find_tps/find_sls + RR≥1 filter essential for SL/TP quality
- 60min confirmation degrades performance (73.7% vs 82.5% baseline)

Data file: `/root/.hermes/smc_opt_v21/all_combos_detail.json`
