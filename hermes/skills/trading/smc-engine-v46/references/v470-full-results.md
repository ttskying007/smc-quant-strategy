# V470 Full 4552 Results

## Summary (Baseline: displacement_mult=1.3, MIN_RR=8.0)

| Metric | Value |
|--------|-------|
| Data | 60min |
| Stocks | 452/4552 (9.9%) |
| Trades | 1056 |
| WR | 57.7% |
| RR | 6.37x |
| PF | 11.45 |
| P&L/笔 | +2.52% |
| Avg Hold | 2.8 bars |
| POI Activated | 880 (83.3%) |

## Direction
All trades are bull-only (ENABLE_BEAR=False).

## Entry Types
| Type | Count | % |
|------|-------|---|
| OB_Rev | 998 | 94.5% |
| Sweep→OB | 58 | 5.5% |

## SL Types
| Type | Count | % |
|------|-------|---|
| adaptive (ATR) | 716 | 67.8% |
| swing_low | 262 | 24.8% |
| ob_lower | 78 | 7.4% |

## TP Types
| Type | Count | % |
|------|-------|---|
| swing_high | 947 | 89.7% |
| choch | 109 | 10.3% |

## Exit Methods
100% trailing exit (0 TP hits).

## Comparison vs V468

| Metric | V468 | V470 (baseline) | Delta |
|--------|------|-----------------|-------|
| Stocks | 561 | 452 | -19.4% |
| Trades | 1318 | 1056 | -19.9% |
| WR | 58.0% | 57.7% | -0.5% |
| RR | 5.64x | **6.37x** | **+12.9%** |
| P&L/笔 | +2.42% | +2.52% | +4.1% |
| Time | 87s | 67s | -23% |

## Key Insight
The 12.9% RR improvement comes from the OB displacement filter. By requiring displacement > 1.3x preceding bar range, lower-quality OBs (where the impulse move is small relative to the OB bar) are filtered out.

## Parameter Tuning (A+B+C) — FINAL RESULTS

Applied 4 changes simultaneously (user request: "all"):

### A) displacement_mult 1.3 -> 1.0 (signals_vPine.py)
Lower detection threshold to allow more OBs through.

### B) Entry displacement filter >= 0.5 (v470_engine.py)
Second-tier filter at entry level, captures marginal OBs that pass 1.0 detection-level.

### C1) MIN_PROJECTED_RR 8.0 -> 6.0
### C2) PROGRESSIVE_BE tighter: [(3,0),(6,0.3),(10,0.5),(16,1.0)]

### Premium/Discount Filter FAILED (removed same session)
Added: skip bull OB if entry_bar close > midpoint of OB zone.
Result: 17/4552 stocks (vs 452 baseline) filter too aggressive for 60min.
Root cause: Price doesn't retrace deep enough into OB zones. Zone lower entry via _calc_entry_price_at_zone is already optimal.
Lesson: Do not add close-based premium checks on 60min entry. Entry_at_zone already handles discount pricing correctly.

### Final Results (A+B+C)

| Metric | Baseline | A+B+C | Delta | V468 |
|--------|:--------:|:-----:|:-----:|:----:|
| Stocks | 452 | 180 | -60% | 561 |
| Trades | 1056 | 394 | -63% | 1318 |
| WR | 57.7% | **67.8%** | **+10.1pp** | 58.0% |
| RR | 6.37x | **6.90x** | **+8.3%** | 5.64x |
| P&L/笔 | +2.52% | **+3.36%** | **+33%** | +2.42% |
| Avg Hold | 2.8b | 3.1b | +0.3b | 2.4b |

### Top Stocks (sorted by RR)

| Symbol | Trades | WR | RR | P&L |
|--------|:-----:|:--:|:--:|:---:|
| 002436.SZ | 2 | 100% | 25.59x | +9.26% |
| 002756.SZ | 3 | 100% | 23.85x | +11.16% |
| 600730.SH | 2 | 100% | 20.42x | +8.52% |
| 002466.SZ | 2 | 100% | 20.41x | +8.99% |
| 603808.SH | 2 | 100% | 18.14x | +5.31% |

### Key Takeaways
1. WR+10.1pp, RR+8.3%, P&L+33% — all three metrics improved
2. Coverage dropped 60% (452 to 180 stocks) — quality over quantity tradeoff
3. 5 entry filters stacked (sequence + resonance + reversal OB + displacement >= 0.5 + trend alignment) — each one reduces count
4. A+B+C combination dominates baseline on every quality metric
5. Tradeoff: only 4% of stocks (180/4552) produce trades vs 10% (452/4552) baseline
6. Premium/discount zone filter is destructive on 60min entry — _calc_entry_price_at_zone is already optimal

## Files
- /root/.hermes/smc_opt_v470/v470_full_trades.json (baseline 1056 trades, then A+B+C 394)
- /root/.hermes/smc_opt_v470/v470_full_stocks.json (baseline 452, A+B+C 180)
- /root/.hermes/smc_opt_v470/v470_summary.json
- /root/.hermes/smc_opt_v470/list_top.py helper script
