# Phase2 SMC Semantic Root-Cause Audit

Use this reference when Phase2 / L→D / POI-retrace SMC systems show winrate that is too low despite apparently correct event order. The key lesson is to debug SMC semantics, not tune thresholds.

## Core Finding

A low winrate can come from mixing different SMC POI semantics into one entry model:

```text
SSL/EQL sweep -> bullish displacement/CHOCH -> POI -> entry
```

is not one system. It must branch by POI type:

| POI | Correct role | Common bug |
|---|---|---|
| FVG Demand | Displacement/imbalance continuation; often strongest before full fill | Treating FVG like OB and waiting for deep retrace/reclaim |
| OB Demand | Structural retest area; can use retrace/reclaim/wick rejection | Selecting merely the last down candle before displacement |
| Pinbar | Entry confirmation inside an existing PD Array | Treating as independent zone or forcing it onto FVG continuation |

## Session-Proven Diagnostic Pattern

Run a semantic ablation before production wiring:

1. Keep signal sequence fixed: `SSL_SWEEP -> BULL_DISPLACEMENT -> DEMAND_POI`.
2. Split POI buckets: `FVG_Demand`, `OB_Demand`, `OB_FVG_Demand`.
3. Compare entry semantics:
   - `FVG immediate`: enter next bar after displacement if FVG remains unfilled.
   - `FVG reclaim`: wait for touch/reclaim of the FVG.
   - `inside_zone`: require entry close inside/near zone.
   - `BSL target`: require structural liquidity target RR.
4. Bucket by mechanism, not just WR:
   - `wait_bin`: 0-2 bars vs 3-6 vs 7-12.
   - `pre_touch_bin`: 0/1/2+ prior touches.
   - `invalid_pre`: close below zone before entry.
   - `fill_bin`: shallow/deep/overfill.
   - `pinbar`: no confirm / weak green / strict pinbar.
   - `pierce_atr`, `disp_atr`, structure context, target RR.

## Durable Lessons

### 1. FVG and OB must not share one retrace entry rule

If FVG reclaim underperforms immediate entry, the bug is semantic:

```text
FVG filled/reclaimed may mean the imbalance has been mitigated, not that support is stronger.
```

For A-share daily Phase2, test FVG as continuation first:

```text
SSL/EQL Sweep -> Bullish Displacement/CHOCH -> Unmitigated FVG -> immediate / 0-2 bar entry
```

OB should be a separate system:

```text
SSL Sweep -> CHOCH/BOS -> structural last-down OB -> unmitigated retest -> wick rejection/reclaim
```

### 2. OB_Demand negative expectancy means OB identification is wrong, not that OB is useless

Reject/rewrite OB if it is just:

```python
last down candle before displacement
```

A tradable OB needs at minimum:

- Located near a structural low / manipulation leg, not trend middle.
- Created or validated by CHOCH/BOS displacement.
- Not already mitigated before entry.
- Ideally overlaps or aligns with FVG, OTE/discount, SSL context, or higher-TF demand.
- Has separate quality grading; weak OB must not be pooled with structural OB.

### 3. Time decay is a first-class SMC gate

For FVG continuation setups, waiting too long after displacement can destroy edge. Bucket `entry_idx - confirm_bar`:

| Wait | Interpretation |
|---|---|
| 0-2 bars | Fresh imbalance; usually best candidate zone |
| 3-6 bars | Momentum may have decayed; verify before allowing |
| 7-12 bars | Often stale; reject unless another structure event refreshes setup |

### 4. Mitigation count matters

Unmitigated PD Arrays are stronger. Track touches between zone creation and entry:

```text
0 touches > 1 touch > 2+ touches
```

Two or more prior touches/fills often indicate a consumed zone. Do not let repeated mitigations enter the same bucket as first-touch setups.

### 5. Pinbar is not a universal confirmation

If strict pinbar performs worse than weak bullish close, do not tighten pinbar parameters blindly. It may mean the POI context is wrong. Use pinbar mainly for OB/PD Array retests, not as mandatory confirmation for FVG continuation.

## Required Report Format for Lei

Use compact tables and state the mechanism-level cause plainly:

1. Which SMC component is missing/wrong.
2. Evidence table by mechanism bucket.
3. Which branch is rejected or split out.
4. Which full-market audit is still running / complete.
5. Do not claim production completion until scan/API/K-line/live/frontend are synced and verified.

## Minimal Candidate Rewrite Direction

Before touching production, build a candidate that explicitly separates:

```text
FVG_Continuation:
  SSL/EQL pool sweep
  -> bullish displacement / CHOCH
  -> true unmitigated FVG
  -> immediate or <=2 bar entry
  -> TP to structural BSL/EQH or RR fallback

OB_Retest:
  SSL sweep
  -> CHOCH/BOS
  -> structural OB, not merely last down candle
  -> first retest only
  -> wick rejection/reclaim confirmation
```

The acceptance gate is not aggregate WR alone. It must show that rejected buckets map to SMC logic: stale FVG, mitigated FVG, weak/false OB, missing structure, or poor target.