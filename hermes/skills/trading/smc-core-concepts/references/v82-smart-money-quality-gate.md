# V82 Smart Money Quality Gate Lesson

Session date: 2026-06-12

## Context

After V81 rebuilt candidate generation in the correct context-first order:

```
Environment permission → trend regime → SMC event → POI → touch/reclaim entry → semantic exit
```

V81 still produced a broad false-positive layer:

| Layer | n | WR | avg |
|---|---:|---:|---:|
| V81 all | 47,612 | 53.27% | -0.1160% |

The next step was not FVG/OB relabeling or TP/SL tuning, but Smart Money behavior quality gating.

## V82 quality gate tested

V82 required:

- market state not RECOVERY/ACCUMULATION until true demand validation is rebuilt;
- `pd_zone == DEEP_DISCOUNT`;
- `1.5% < entry-zone_low risk <= 4.0%`;
- `0.5% < POI width <= 3.0%`;
- touch then delayed reclaim, `reclaim_idx - touch_idx >= 2`;
- target RR >= 1.0;
- `zone_low` close to prior structure low: -5% to +5%.

Tests were written for:

- accepting context-first deep-discount delayed reclaim;
- rejecting unproven RECOVERY/ACCUMULATION;
- rejecting shallow discount;
- rejecting same-bar/1-bar reclaim;
- rejecting bad POI width and bad risk bands.

## Result

| Layer | n | WR | avg | POI break | trend damage |
|---|---:|---:|---:|---:|---:|
| V81 all | 47,612 | 53.27% | -0.1160% | 28.05% | 9.84% |
| V82 selected | 265 | 56.23% | +1.4379% | 12.45% | 32.83% |

Year split:

| Year | n | WR | avg |
|---|---:|---:|---:|
| 2023 | 56 | 48.21% | +0.8546% |
| 2024 | 41 | 48.78% | +1.2588% |
| 2025 | 131 | 64.12% | +2.0871% |
| 2026 | 37 | 48.65% | +0.2209% |

## Conclusion

V82 improves POI validity (POI close-break falls from 28.05% to 12.45%) but is not production-ready.

The new root cause is not POI selection anymore. The failure moved downstream: after reclaim, many candidates suffer trend-structure damage. This proves the system still lacks a **post-reclaim smart-money takeover confirmation**.

## Next direction: V83

Do not keep adding static filters. V83 should implement post-reclaim structure takeover:

1. After reclaim, require 1-3 bars to hold above POI or print a higher low.
2. If reclaim is followed immediately by a micro-HL break, reject before simulation.
3. Split continuation and reversal gates; continuation has much better quality than reversal in V82.
4. MIXED should be blocked unless range accumulation is explicitly proven.

Production remains V80. V82 is research-only.
