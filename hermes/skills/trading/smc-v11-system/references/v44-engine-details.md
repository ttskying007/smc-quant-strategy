# SMC Engine V44 — Detailed Reference

> Originally `smc-engine-v44` standalone skill. Absorbed into `smc-v11-system`.
> V44 is covered in the umbrella's version comparison table; this file preserves the engine-specific details.

## Key Innovations

1. **Retest Entry**: Price retests signal zone before entry (32.9% of trades)
2. **Quality-Grade Differentiated Trailing**: S/A→loose, B/C→tight
3. **Bull-Bear Balance**: Bear share increased from 6.4% to 36.9%
4. **Structural TP + ATR Floor**: At least 1.5% distance swing points
5. **5-Level Signal Quality**: S/A/B/C/D

## Architecture

```
backtest_stock_v44(ohlcv, sym)
├── detect_market_phase(ohlcv) → Wyckoff phase
├── calc_stock_params(ohlcv) → per-stock ATR/SL params
├── detect_all_signals_v11(ohlcv, params) → all SMC signals
├── detect_retest_entries(all_signals, ohlcv, params) → retest entry points
└── iterate signals → evaluate_signal_entry_v44(...)
    ├── retest entry → _evaluate_retest_entry(...)
    └── direct entry → calc_structural_sl_v44 + calc_structural_tp_v44 + calc_trailing_v44
```

Key File: `/root/.hermes/scripts/v11/v44_engine.py`

## V44 vs V43 Full Comparison (4800 stocks)

| Metric | V44(4800) | V43(4800) |
|--------|-----------|-----------|
| WR | 79.9% | 91.8% |
| RR | 3.97x | 9.54x |
| PF | 8 | 135 |
| P&L | +0.53% | +4.09% |
| Bear share | 36.9% | 6.4% |
| Avg hold bars | 1.0 | ~1.5 |
| Tradable | 4776/4800 | 4111/4800 |
| Total trades | 236,556 | 38,810 |

## Key Parameters

### ENTRY_PARAMS (by quality grade)
- S: sl_mult=0.15, tp_mult=4.0, hold_max=60
- A: sl_mult=0.20, tp_mult=3.0, hold_max=40
- B: sl_mult=0.25, tp_mult=2.5, hold_max=30
- C: sl_mult=0.30, tp_mult=2.0, hold_max=20
- D: None (no trade)

### TRAILING_PROFILES
```
bull_loose:  [(6.0,3.0), (3.0,1.5), (1.5,0.3), (1.0,0.1), (0.5,0.0)]
bull_tight:  [(3.0,1.0), (1.5,0.5), (0.7,0.2), (0.4,0.05), (0.2,0.0)]
bear_loose:  [(6.0,3.0), (3.0,1.5), (1.5,0.3), (1.0,0.1), (0.35,0.0)]
bear_tight:  [(3.0,1.0), (1.5,0.5), (0.7,0.2), (0.35,0.0)]
```

Profile selection:
- S/A grade → always loose
- B/C + has TP → loose
- B/C + no TP → tight
- D grade → tight

### RETEST_PARAMS
- max_retest_bars: 15
- retest_tolerance_pct: 0.3
- confirm_bars: 2
- min_retest_volume_pct: 0.8

## Critical Bugs Fixed

### Bug 1: Bull SL Exit Always Marked Win
- Symptom: Bull WR=100%, Bear WR=2.0%
- Root cause: `calc_trailing_v44` bull SL exit hardcoded `return j, round(...), True`
- Fix: Dynamic `exit_price > entry_price` check

### Bug 2: Bear TP Pre-Exit Factor Error
- Symptom: Bear TP rarely triggered
- Root cause: Condition `extreme <= tp_price * 0.98` — multiplier wrong for bear direction
- Fix: Changed to `extreme <= tp_price` (exact TP exit) or `<= tp_price * 1.02`

### Bug 3: RetestEntry Dataclass Subscript Access
- Symptom: `TypeError: 'RetestEntry' object is not subscriptable`
- Root cause: RetestEntry is dataclass (attribute access `re.entry_idx`) but code used dict subscript `re['entry_idx']`
- Fix: Global replace `re[...]` → `re.xxx`

### Bug 4: find_swing_high/low References best as dict
- Symptom: `TypeError: list indices must be integers or slices, not dict`
- Root cause: best is `{'idx': i, 'price': x}` but code used `ohlcv[best]['h']`
- Fix: Changed to `ohlcv[best['idx']]['h']`

### Bug 5: 200-Stock Sample Bias
- Observation: 200-stock test RR=4.85x, full 4800 RR=3.97x
- Root cause: 000-prefix stocks not representative of full market distribution
- Lesson: Always validate with full 4800

## Core Constraints

### A-Share Daily 1-Bar Exit
- Full 4800 avg hold = 1.0 bars (84.5% of trades exit ≤3 bars)
- Structural constraint of A-share daily gap — cannot be changed
- All exit mechanisms must complete within 1-2 bars, limiting RR ceiling

### Trailing vs TP Hit Tradeoff
- TP hit: WR=100%, RR=7.26x (8.9% of trades)
- Trailing: WR=77.9%, RR=3.65x (91.1% of trades)
- Raising TP hit rate is the key path to higher RR
- Method: Increase TP distance (ATR 3.0x→6.0x), skip near swings for far swings

## Debug Commands

```bash
# 200-stock test (30 seconds)
cd /root/.hermes/scripts/v11 && python3 v44_backtest_test.py

# 10-stock smoke test (2 seconds)
cd /root/.hermes/scripts/v11 && python3 v44_smoke.py

# Full 4800 (~17 minutes)
cd /root/.hermes/scripts/v11 && python3 v44_full_scan.py
```
