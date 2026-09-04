# V29 Root Cause Analysis & High-Quality Optimization

## Diagnosis Methodology

When WR is below target (target ≥85%), do NOT blindly tune parameters.
Run a full 4-stage diagnosis:

### Stage 1: SL Attribution
Query: WHERE is the WR loss coming from?
- Losers by exit_reason: SL_HIT usually dominates (>97% in V28)
- Losers by resonance: CONFLICT vs ALIGNED gap
- Losers by market_state: which states bleed
- Losers by zone_type: OB vs OTE SL rates

### Stage 2: Zone Behavior
Query: Does the zone fail BEFORE the SL?
- Sample 50+ loser trades, load klines
- Check: did close break below zone_low BEFORE SL bar?
- V28 finding: 74% of losers have zone invalidated first

### Stage 3: Feature Comparison
Query: What DIFFERENTIATES winners from losers?
- Compare OB candle characteristics (body_ratio, zone_age, prior_touches)
- Compare entry distance from zone_high
- Compare quality_score, SL distance, hold_bars
- V28 finding: OB candle quality is IDENTICAL between winners/losers
  → Detection accuracy is NOT the problem. Context is.

### Stage 4: Filter Simulation
Query: Which filter combination maximizes WR?
- Simulate N filter scenarios on existing trade data
- Compute WR, PnL, trade_count for each
- Pick the combination that best balances WR and trade volume

## V28 → V29 Key Findings

| Filter | SL Rate | Action |
|--------|---------|--------|
| CONFLICT resonance | 44.0% | Hard skip |
| TREND_DOWN market | 34.8% | Hard skip |
| TRANSITION market | 34.5% | Hard skip |
| PARTIAL resonance | 31.9% | Hard skip |
| ALIGNED resonance | 20.7% | Keep |
| WEAK resonance | 20.4% | Keep |
| Entry >1% from zone_high | ~30% | Tighten to <1% |

## V29 Triple Filter Engine

```python
ALLOWED_RESONANCE = {'ALIGNED', 'WEAK'}      # Skip PARTIAL, CONFLICT
SKIP_MARKET_STATES = {'TREND_DOWN', 'TRANSITION', 'RANGE'}
MAX_ENTRY_DIST_PCT = 1.0   # Max distance from zone_high
```

Expected (simulated): WR=86.0%, 766 trades
Achieved (full scan): WR=85.7%, 757 trades, 383 picks

## Counter-Intuitive Findings

1. **OB×WEAK beats OB×STRONG**: WEAK-grade OBs SL=19.4% vs STRONG 27.7%
2. **Quality score barely differentiates**: winners Q=7.35, losers Q=7.26
3. **SL distance identical**: winners 4.40%, losers 4.43% → not the issue
4. **Hold duration identical**: winners 4.9b, losers 4.8b → not the issue

## K-line Signal Fix Lessons

- V22 BOS/CHOCH/MSS ≠ V27: zero overlap. Use same engine as trades.
- Sweep: bull→wick_low, bear→wick_high. Both must be checked.
- Frontend contract: every trade needs conf_type, zone_type, signal_type, entry_type

## Pick Field Contract for V29

Every pick must have flat: tp1, tp2, tp3, risk_pct, smart_money_cost, price
