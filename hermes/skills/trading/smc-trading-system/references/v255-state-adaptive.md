# V25.5 Market State Adaptive Parameters — Detailed Findings

## Backtest Results (2026-05-19)

| Version | Trades | WR | Avg PnL | Total PnL | Key Change |
|---------|--------|-----|---------|-----------|------------|
| V25.1 | 220 | 63.2% | +0.84% | +184% | Sweep/CHOCH filter + structural TP |
| V25.5 (with RANGE) | 297 | 57.6% | +0.84% | +250% | State-adaptive but RANGE dragging down |
| V25.5 (no RANGE) | 195 | 64.6% | +1.47% | +286% | Skip RANGE entirely |
| V25.5 (final, 500 scan) | 300 | 67.7% | +1.68% | +505% | RANGE filtered in scan + more picks |

## Market State Detection Logic

```
compute_adx(klines, 14, entry_idx)  → Wilder's ADX
compute_atr(klines, 14, entry_idx)  → ATR and ATR%
ma20 = sum(closes[-20:])/20
ma_slope = (closes[-1]-closes[-5])/closes[-5]*100
pct_from_ma = (current-ma20)/ma20*100

Classification priority:
1. ATR% > 5% → HIGH_VOL (widest SL 0.8x ATR, shortest hold 20bar)
2. ATR% < 1.5% + ADX < 20 → LOW_VOL (tightest SL 0.3x ATR, longest hold 90bar)
3. ADX < 20 → RANGE (wider SL 0.7x ATR, closer TP 1.3x ATR, 30bar hold)
   ⚠️ RANGE must be SKIPPED — backtest shows 44% WR, -0.35% avgP
4. pct_from_ma > 1% + ma_slope > 0.5 → TREND_UP (tight SL 0.4x ATR, wide TP 2.0x, 60bar hold)
5. pct_from_ma < -1% + ma_slope < -0.5 → TREND_DOWN (same as TREND_UP)
```

## Why RANGE Must Be Skipped

V25.5 initial backtest included RANGE with adjusted parameters (wider SL):
- RANGE: 102 trades, WR=44.1%, avgP=-0.35%
- Even with wider SL (0.7x ATR), whipsaws in ranging markets kill performance
- The wider SL reduces SL hit rate but average loss is still negative
- Skip RANGE entirely → WR 57.6%→64.6%, avgP +0.84%→+1.47%

Rule: `if state == 'RANGE': continue` in both scan and backtest.

## Adaptive Parameters per State

```python
STATE_PARAMS = {
    'TREND_UP': {
        'sl_atr_mult': 0.4,      # Tight — trend is friend
        'tp_atr_mult': 2.0,      # Wide — let winners run
        'max_hold': 60,
        'trail_activate_r': 0.8, # Early trail in trends
        'trail_buffer_atr': 0.3,
    },
    'HIGH_VOL': {
        'sl_atr_mult': 0.8,      # Wider — avoid getting shaken out
        'tp_atr_mult': 1.5,
        'max_hold': 20,          # Short — volatility means fast moves
        'trail_activate_r': 1.2, # Late trail in volatility
        'trail_buffer_atr': 0.6, # Wider trail buffer
    },
    'LOW_VOL': {
        'sl_atr_mult': 0.3,      # Tightest — small ranges
        'tp_atr_mult': 1.5,
        'max_hold': 90,          # Long — slow grind
        'trail_activate_r': 0.7,
        'trail_buffer_atr': 0.2,
    },
}
```

## Key Insight: HIGH_VOL is the Star Performer

Counterintuitively, HIGH_VOL stocks perform best:
- WR=68.3%, avgP=+2.35%
- The wider SL (0.8x ATR) prevents premature stops
- Structural TP targets are more likely to be hit in volatile moves
- Short hold (20bar) prevents overstaying

## Best State × Confirmation Combos

| Combo | Trades | WR | Avg PnL |
|-------|--------|-----|---------|
| TREND_DOWN + PINBAR_ENTRY | 16 | 81.2% | +1.72% |
| TREND_DOWN + OTE_ENTRY | 20 | 80.0% | +1.66% |
| TREND_UP + CHOCH_ENTRY | 19 | 78.9% | +5.45% |
| HIGH_VOL + PINBAR_ENTRY | 9 | 77.8% | +6.14% |
| HIGH_VOL + OTE_ENTRY | 10 | 80.0% | +3.00% |
| TREND_UP + OTE_ENTRY | 11 | 18.2% | -4.19% ← AVOID! |

Surprising: TREND_UP + OTE_ENTRY is terrible (18.2% WR). OTE entries work in DOWN trends and HIGH_VOL, but not in UP trends — in strong uptrends, pullbacks to OTE don't happen, price keeps running.

## Implementation Files

- `/root/.hermes/scripts/v25/state_backtest.py` — State detection + adaptive backtest
- `/root/.hermes/scripts/v25/full_scan.py` — Integrated RANGE filter + adaptive SL
- `/root/.hermes/smc_opt_v25/v255_trades.json` — 300 state-adaptive trades
