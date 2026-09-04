# V84 Smart Money Path Split Lesson

Session date: 2026-06-12

## Context

The user clarified the core issue: replacing FVG with OB or anchoring OB to the sweep origin still does not solve the problem. The real root cause is that the system does not truly track smart-money behavior through ordered stages:

```
Environment → trend regime → SMC event → POI location → touch/reclaim → takeover → entry → semantic exit
```

V84 therefore did not tune TP/SL or relabel zones. It split V83 candidates by explicit smart-money paths.

## Implementation

Files:

- `/root/.hermes/scripts/v25/v84_smart_money_path_split_gate.py`
- `/root/.hermes/scripts/v25/test_v84_smart_money_path_split_gate.py`
- `/root/.hermes/scripts/v25/v84_apply_smart_money_path_split.py`

Tests passed for:

1. continuation + HOLD_ABOVE_POI + post-takeover demand-valid environment;
2. rejecting POST_RECLAIM_HIGHER_LOW as weak smart-money control;
3. rejecting environment deterioration after takeover;
4. reversal requiring SSL sweep + CHOCH + HOLD_ABOVE_POI;
5. rejecting weak sweep pierce;
6. rejecting MIXED reversal if post-takeover environment stays MIXED.

## Result

Applied to V83 selected candidates (224 rows):

| Layer | n | WR | avg | POI break | trend damage | TP rate |
|---|---:|---:|---:|---:|---:|---:|
| V83 source | 224 | 58.93% | +1.2029% | 10.27% | 30.80% | 57.14% |
| V84 selected | 45 | 71.11% | +1.9058% | 4.44% | 17.78% | 75.56% |

Path split:

| Path | n | WR | avg | trend damage | TP rate |
|---|---:|---:|---:|---:|---:|
| CONTINUATION_HOLD_ABOVE_POI | 35 | 77.14% | +2.1859% | 14.29% | 80.00% |
| REVERSAL_SSL_CHOCH_HOLD_ABOVE_POI | 10 | 50.00% | +0.9255% | 30.00% | 60.00% |

## Key mechanism findings

1. `HOLD_ABOVE_POI` is the strongest current proxy for smart-money takeover.
2. `POST_RECLAIM_HIGHER_LOW` is not equivalent to takeover; it has high trend-damage contamination and must be downgraded unless it later also holds above POI.
3. Continuation (`UP_CONTINUATION + BOS pullback + HOLD_ABOVE_POI`) is the main viable path.
4. Reversal (`SSL sweep + CHOCH`) remains too noisy. Sweep pierce depth alone does not fix it; deeper pierce often reduces quality/coverage.
5. MIXED should not be globally blocked: `post_MIXED + narrow POI (zone_width<=1.5%)` produced 23 rows / 82.61% WR / +2.0535% avg, suggesting a real `MIXED_ACCUMULATION` substate.

## Production status

V84 is research-only. It improves mechanism quality but does not meet production coverage:

| Year | n | WR | avg |
|---|---:|---:|---:|
| 2023 | 1 | 0.00% | -2.7194% |
| 2024 | 2 | 50.00% | +2.5195% |
| 2025 | 39 | 76.92% | +2.3640% |
| 2026 | 3 | 33.33% | -2.9178% |

Production remains V80.

## Next direction: V85

Do not keep filtering V83/V84 small samples. Rebuild the generator/environment layer:

1. Split MIXED into `MIXED_ACCUMULATION` and `MIXED_DISTRIBUTION`.
2. Expand continuation path at generation time, not after filtering: broaden BOS pullback search while retaining HOLD_ABOVE_POI takeover.
3. Rebuild reversal path using post-sweep range reclaim + CHOCH hold + subsequent HH/HL, not just sweep pierce.
4. Keep production gates: total ≥500, each year ≥50, each year WR ≥65%, T+1 0 violations, field audit 0 missing.
