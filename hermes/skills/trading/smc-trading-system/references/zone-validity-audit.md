# Zone Validity Audit Methodology

## Core Discovery (2026-05-15)

Full A-share scan (4,905 stocks) of Demand Zones (OB_Bull, confidence≥0.7) revealed:

| Zone Status | Count | % | Meaning |
|-------------|-------|---|---------|
| ❌ Breached | 617 | 79% | Close dropped below zone_low×0.98 — zone FAILED as support |
| ⏳ Expired | 90 | 11% | >60 bars old, never tested — stale |
| ✅ Valid | 77 | 10% | Unbreached, <60 bars, tested at least once |

## Zone Audit Checklist

For each Demand Zone (OB_Bull), check:

1. **Zone Age**: `current_bar - zone_bar` — reject if >80 bars (stale)
2. **Rally Confirmation**: zone must show price rallying away after formation (proves it's real support)
3. **Test History**: has price returned to the zone? How many times?
4. **Breach Status**: did close ever drop below `zone_low × 0.98`?
5. **CHOCH Presence**: is there a CHOCH_Bull after zone formation? (confirms trend reversal)
6. **Trigger History**: was this zone already used in backtest? What was the result?

## Zone Classification

### ✅ Unbreached (valid)
- Price never closed below zone_low × 0.98
- CHOCH_Bull exists after zone formation
- Rally confirmed
- **Backtest**: 429 trades, WR=96.3%, Avg PnL=+10.18%

### 🔄 PO3 (breached then reversed — theoretically valid)
- Zone breached, but CHOCH_Bull appears after breach
- Represents: Accumulation → Manipulation (sweep below) → Distribution (rally back)
- **Backtest**: only 10 valid cases in 4,905 A-shares — TOO RARE
- WR=50.0%, Avg PnL=+3.66% (insufficient sample)

### ❌ Breached-Invalid (dead zone)
- Zone breached, NO CHOCH_Bull reversal after breach
- Trend continued downward — zone is no longer support
- **617 out of 784 zones (79%)** — the most common case

### ⏳ Expired (stale)
- Zone >60 bars old, never tested
- Market has moved on, zone relevance decayed

## PO3 Pattern Verification

User's hypothesis (correct in theory): "击穿后如果反转了, 也可以作为入场, 说明这里产生了流动性扫除和PO3"

Verification result: PO3 is real but extremely rare in A-shares. Only 10 valid PO3 entries found across 4,905 stocks. The pattern exists but is not a reliable standalone strategy.

## Scanner Evolution

| Scanner Version | Logic | Count | Issue |
|----------------|-------|-------|-------|
| V1 | All OB_Bull signals | 4,517 | Includes years-old signals |
| V2 | 60-bar recent signals | 1,791 | Still includes downtrend fake signals |
| V3 | 5-bar recent + MA20 filter | 180 | Wrong: signal trigger ≠ entry timing |
| V4 | Zone retrace + MA20/60d-high | 123 | User rejected MA filters as non-SMC |
| V5 | Pure SMC: Zone + CHOCH + retrace | 784 | 79% breached zones included |
| **V6** | **Pure SMC + zone validity audit** | **77 valid** | ★ Correct: only unbreached zones |

## Key Insight

The OB_Bull signal fires when the zone FORMS. The trading opportunity is when price RETRACES to the zone later. Monitoring should track retracement proximity, not signal trigger recency.
