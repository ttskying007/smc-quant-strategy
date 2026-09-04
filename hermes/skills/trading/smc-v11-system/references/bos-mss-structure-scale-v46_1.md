# V46.1 BOS/MSS structure-scale audit lesson

## Trigger
Use this when the user says SMC BOS/MSS/CHOCH signals are too few, late, or visually misaligned with Pine/TradingView.

## Durable lesson
Do not treat a clean structure invariant audit (`bad_events = 0`) as proof that BOS/MSS is visually correct. It only proves emitted events obey the current implementation's rules. If the implementation used the wrong Pine parameters, the audit can pass while still missing most TradingView signals.

## Pine parameters observed from the session screenshots
- Smart Money Concepts 2026:
  - Market Structure `Swing Length = 5`
  - Show BOS = enabled
  - Show CHOCH = enabled
  - Show MSS = enabled, labelled `MSS (Early Warning)`
  - OB Swing Detection Length = 7
  - OB Lookback = 10
  - OB Displacement Multiplier = 1.5
  - FVG ATR Multiplier = 0.5
  - EQH/EQL Pivot Length = 4
  - EQH/EQL ATR Length = 200
  - EQH/EQL Threshold = 0.1
- LuxAlgo SMC screenshot:
  - Internal Order Blocks = 5
  - Swing Order Blocks = 5
  - Order Block Filter = ATR
  - Mitigation = High/Low

## Root causes found
1. `smc_core_luxalgo_v34.detect_all_signals_lux_v34()` used `swing_len=20` by default while the provided SMC2026 Pine settings used `Swing Length = 5`. This alone suppressed BOS/CHOCH/MSS density.
2. `structure = swing_structure + only internal_structure where is_mss` hides most internal BOS/CHOCH from the final signal layer. Keep raw layers separately visible when auditing signal correctness.
3. MSS was implemented as strict `CHOCH + recent same-direction sweep + displacement`, but the Pine label says `MSS (Early Warning)`. Future work should distinguish:
   - `MSS_EARLY`: structure-shift warning after relevant sweep/context, lower strictness, displayed on charts.
   - `MSS_CONFIRMED`: stricter trade-quality gate with displacement/body evidence, used for reversal entry quality.
4. `bootstrap_cutoff = size * 2` can delay early pivot/structure visibility. If early chart mismatch appears, test this separately; do not bundle it with swing-length changes.

## Verification pattern
Before and after any BOS/MSS fix, run a structure-density + invariant audit:

```bash
cd /root/.hermes/scripts/v25
python3 v46_1_structure_audit.py
```

Compare at least:
- total structure events
- BOS bull/bear counts
- CHOCH bull/bear counts
- MSS bull/bear counts
- `bad_events`, `bad_rate`, `issue_counts`

In the session where this lesson was captured, changing default `swing_len` from 20 to 5 increased sampled average structure density approximately:
- `swing_structure`: 10.96 → 36.33 per symbol
- MSS: 1.45 → 7.49 per symbol

Full audit after the swing-length fix emitted 201,501 events with `bad_events = 0`, confirming the increased density still obeyed close-cross/pivot-order invariants.

## Guardrail
Do not optimize WR/RR first when the user reports BOS/MSS inaccuracy. First align Pine parameters and visual signal definitions, then re-run full backtest/selection/frontend sync. Signal correctness is the primary objective for this class of task.
