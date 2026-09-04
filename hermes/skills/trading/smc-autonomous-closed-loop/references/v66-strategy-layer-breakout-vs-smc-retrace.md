# V66 Strategy Layer Gap: Breakthrough System ≠ SMC Retrace System (2026-06-10)

## Critical Finding

V59 engine (`smc_core_pine_like.py`) signal detection is correctly aligned with Pine Script.
But the **strategy layer** (`daily_scan.py`) uses signals as a **breakthrough trading system**, not an SMC retrace-to-POI entry system.

## Evidence (137 V66 Trades)

| Check | Result | SMC Theory |
|-------|--------|------------|
| entry_idx vs conf_idx | 137/137 entry at conf_bar+1 | Should wait for retrace to POI |
| Sweep precondition | 0/137 have sweep | Should require liquidity sweep → structure break |
| market_state | 137/137 = "?" (never computed) | Need trend/reversal/range state machine |
| Entry position | 91 (66%) above zone_high | Should be inside zone at 25-50% position |
| SL vs zone_low | 45 SL = zone_low (no buffer) | SL should be zone_low - ATR*0.5 |
| Signal combos | Only 5 (OB/FVG + BOS/CHOCH/MSS) | Missing triple-confluence and sweep+zone |

## Code Locations

```python
# daily_scan.py:216-218 — No retrace wait
entry_idx = c.bar + 1              # Enter on next bar after confirmation
if entry_idx != latest_idx:        # Only trade latest bar
    continue
entry_price = klines[entry_idx].get('o')  # Enter at open price

# daily_scan.py:183-196 — No market state
def _pass_daily_gate(zone_type, conf_type, score, trend_ctx, body_ratio):
    if zone_type == 'OB_Bull' and conf_type in ('BOS_Bull', 'CHOCH_Bull'):
        return True, [], 'CONTINUATION_SETUP'
    # Never checks market state

# compute_sltp() (inline in daily_scan.py) — SL at zone_low
v25_sl_price = raw_zone_low  # No buffer
```

## V67 Validation: Full Market WR = 41%

V67_STRICT with 90551 trades shows WR=41.15% — actual SMC signal accuracy level.
V66's WR=90% comes from V64(269)→V65(143)→V66(137) over-filtering, not signal quality.

## V65/V66 Are Post-hoc Filters, Not Architecture Fixes

V65 = loss-review gate on V64 results (47% reject)
V66 = REENTRY risk overlay on V65 (5% reject)
Neither fixes `entry_idx = c.bar+1`.

## Fix Path

### Phase 0 (Quick Fix)
- SL buffer: `v25_sl_price = raw_zone_low * 0.99` (min 1% buffer)
- Reject chase: `if entry_price > zone_high * 1.008: continue`

### Phase 1 (Strategy Rebuild)
- New `smc_retrace_entry.py`: wait for price retrace to zone + rejection candle
- New sweep precondition: require sweep event before structure break
- New `smc_market_state.py`: state machine (TREND_UP/DOWN/RANGING/BREAKOUT)
- Multi-timeframe alignment (weekly trend filter)

### Phase 2 (Production)
- 500+ stock full backtest
- Monitor layer adaptation
- Frontend quality marking

## Audit Checklist (Add to any V66+ review)

1. entry_idx vs conf_idx relationship (is retrace waited?)
2. Entry price vs zone boundary (inside? above?)
3. Does a sweep event precede the trade?
4. Is market_state computed?
5. SL position relative to zone_low buffer
6. Signal combination richness (single vs multi-signal confluence)
