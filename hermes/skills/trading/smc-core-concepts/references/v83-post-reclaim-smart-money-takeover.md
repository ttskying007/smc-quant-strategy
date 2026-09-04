# V83 Post-Reclaim Smart Money Takeover Lesson

Session date: 2026-06-12

## Context

V81 rebuilt candidate generation in the correct context-first order, and V82 added POI/risk/discount/reclaim quality gates. V82 reduced POI close-breaks but still failed production because many candidates suffered trend-structure damage after reclaim.

The root cause moved downstream: **touch + reclaim is not enough evidence that smart money has taken control**. A candidate needs a post-reclaim takeover confirmation before entry.

## V83 implementation

Added `v83_post_reclaim_takeover_gate.py` with tests in `test_v83_post_reclaim_takeover_gate.py`.

Behavior tested:

1. Accept when price holds above POI after reclaim, then move entry to next open after takeover confirmation.
2. Accept when price prints a higher low after reclaim without closing below POI.
3. Reject immediate POI close break after reclaim.
4. Reject micro-HL break after reclaim.
5. Reject if there is no next open after takeover confirmation.

Implementation rule:

```
Environment → trend → event → POI → touch/reclaim → post-reclaim takeover → next-open entry → semantic exit
```

## Full scan result

Applied V83 to V82 selected candidates (`v82_selected_candidates.json`).

| Layer | n | WR | avg | POI break | trend damage | TP rate |
|---|---:|---:|---:|---:|---:|---:|
| V82 source | 265 | 56.23% | +1.4379% | 12.45% | 32.83% | 53.58% |
| V83 selected | 224 | 58.93% | +1.2029% | 10.27% | 30.80% | 57.14% |

Year split:

| Year | n | WR | avg | trend damage |
|---|---:|---:|---:|---:|
| 2023 | 41 | 43.90% | -0.1841% | 41.46% |
| 2024 | 38 | 60.53% | +1.2693% | 31.58% |
| 2025 | 115 | 65.22% | +2.0117% | 23.48% |
| 2026 | 30 | 53.33% | -0.0862% | 43.33% |

## Key mechanism finding

V83 proves post-reclaim takeover helps, but it is still not production-ready.

Important bucket split:

| Takeover type | n | WR | avg | trend damage | TP rate |
|---|---:|---:|---:|---:|---:|
| HOLD_ABOVE_POI | 161 | 64.60% | +1.4079% | 22.98% | 65.84% |
| POST_RECLAIM_HIGHER_LOW | 63 | 44.44% | +0.6788% | 50.79% | 34.92% |

Conclusion: **holding above POI is a real smart-money takeover signal; a weak higher-low after reclaim is still contaminated and should not be treated as equal quality.**

Story split:

| Story | n | WR | avg | trend damage | TP rate |
|---|---:|---:|---:|---:|---:|
| UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM | 50 | 74.00% | +2.6581% | 22.00% | 70.00% |
| DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM | 174 | 54.60% | +0.7847% | 33.33% | 53.45% |

Conclusion: continuation + hold-above-POI is the first genuinely strong smart-money behavior bucket. Reversal remains too noisy.

## Best research bucket

`UP_CONTINUATION + HOLD_ABOVE_POI + zone_width<=2%`:

| n | WR | avg | POI break | trend damage | TP rate |
|---:|---:|---:|---:|---:|---:|
| 25 | 92.00% | +3.2593% | 0.00% | 4.00% | 88.00% |

Not production because coverage is too small and year distribution is concentrated in 2025.

## Current conclusion

V83 is a correct next step but not complete:

- It confirms the user’s diagnosis that the core issue is smart-money tracking, not FVG/OB labels or TP/SL.
- It adds the missing post-reclaim takeover layer.
- It identifies the first strong bucket: `BULL_CONTINUATION + BOS pullback + HOLD_ABOVE_POI`.
- It proves `POST_RECLAIM_HIGHER_LOW` is not strong enough as currently defined.
- It still fails 2023/2026 due to high trend-damage after entry.

## Next direction

V84 should split the generator before POI creation, not just post-filter V83:

1. Continuation path: focus on `BULL_CONTINUATION + BOS + HOLD_ABOVE_POI`, expand coverage.
2. Reversal path: rebuild SSL sweep → CHOCH rules; current reversal path is too noisy.
3. Remove or downgrade weak `POST_RECLAIM_HIGHER_LOW` unless it later also holds above POI.
4. Add pre-entry market-state durability check after takeover; 2023/2026 failures still show environment deterioration after reclaim.
