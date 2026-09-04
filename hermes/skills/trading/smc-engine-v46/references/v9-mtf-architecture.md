# V9 Multi-Timeframe Engine Architecture

## Data Flow
```
Daily K-lines (300 bars, ~15 months)
  → detect_all_signals_v20() → OB_Bull, FVG_Bull, CHOCH_Bull, BOS_Bull, Sweep_SSL
  → Weekly MA20 trend filter (bullish only)
  → 60min K-lines (where available, 500 bars)
  → Find 60min entry within daily zone (retrace check)
  → SL: entry * (1 - max(3%, min(8%, ATR * 2.0)))
  → TP: forward swing_high (daily, min 5%)
  → Trailing: +5% activate, trail_dist = ATR * 0.8
  → T+1: skip same-day exit
  → Output: v9_mtf_full.json
```

## Signal Selection Rationale
- **OB_Bull (WR=85.3%)**: Primary signal. Order block at structural reversal. Proven.
- **Sweep_SSL (WR=70.6%)**: Liquidity sweep before reversal. Good second signal.
- **CHOCH_Bull (WR=59.4%)**: Structure break. Use with OB confirmation.
- **FVG_Bull (WR=49.6%)**: Fair value gap. Daily fills too often — limit to 60min.
- **BOS_Bull (WR=41.9%)**: Break of structure. NOT standalone — context only.

## Key Parameters
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| SL_MIN | 3% | Floor for low-ATR stocks |
| SL_MAX | 8% | Ceiling for high-ATR stocks |
| SL_ATR_MUL | 2.0 | SL ≈ 2× daily ATR |
| TRAIL_ACT | 5% | Activate trailing after 5% gain |
| TRAIL_DIST_MUL | 0.8 | Trail distance ≈ 0.8× ATR |
| TP_MIN | 5% | Minimum TP target |
| MAX_WAIT_DAILY | 3 | Max bars to wait for daily retrace |
| MAX_60MIN_RETRACE | 12 | Max 60min bars for zone entry |
| WEEKLY_FILTER_PCT | 2% | Price must be > MA20 by 2% |

## Known Limitations
1. 60min data only 6-7 months (Tencent ifzq API cap)
2. No market regime detection (bull/bear/range same parameters)
3. No position sizing (all trades equal weight)
4. No volume confirmation on entry/exit
5. FVG_Bull underperforms on daily — needs unfilled-gap filter
