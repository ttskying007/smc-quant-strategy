# Stop-loss spike triage for SMC systems

Session-derived notes for `smc-v11-system`.

## Triage order
1. Check whether the signal itself is valid and correctly detected.
2. Check whether the entry price is at the intended POI/zone or still inside the setup window.
3. Check whether the combination logic is over- or under-constraining the signal family.
4. Check whether the trade was entered before the actual entry point or after the zone had already been consumed.
5. Only after the above, tune stops or holding logic.

## Common failure buckets
- **Signal-definition defect**: the pattern is detected too early/late, or the wrong structural candle is used.
- **Combination defect**: valid signals are filtered out or merged into an over-strong composite that changes the intended meaning.
- **Entry-point defect**: entry occurs before confirmation, away from zone, or after the price has already moved through the POI.
- **Zone-consumption defect**: the entry arrives after the setup has already been filled/invalidated.
- **Risk-control defect**: stop is reasonable but market context makes the trade structurally fragile.

## Practical review rule
When stop losses rise, do not jump directly to SL/TP tuning. First classify losses by signal correctness, entry correctness, and structural timing. Preserve this order even when aggregated WR/RR looks acceptable.
