# Strict Daily Causal Combination Closure

Use when researching an A-share daily SMC narrative such as `sweep → CHOCH/BOS → POI → retest/reclaim/hold`.

## Fixed research contract

1. **Generate candidates without outcomes.** Candidate rows must contain no PnL, exit, TP/SL, mark, MAE/MFE, or winner fields.
2. **Lifecycle begins strictly after the last prerequisite bar**: `start_idx = max(event_idx, poi_idx)`; scan starts at `start_idx + 1`.
3. **Demand OB freshness**: a wick touch before the structure event means it is not the claimed first post-event retest; a pre-event close below `zone_low` invalidates it.
4. **FVG freshness**: its creation/source bar cannot count as a post-creation retest.
5. **Entry diagnostic is fixed**: only `TAKEOVER_CONFIRMED → next session open`; exclude entry session from fixed 5/10/20-session marks. Do not search TP, SL, exits, windows, or thresholds.
6. **Audit independently before using economics**: reconstruct chronology from raw bars and verify every replay entry equals the following raw session open; enforce T+1=0.

## Minimum gates

### Candidate supply gate
Before opening any outcome/mark field:

- total `TAKEOVER_CONFIRMED >= 300`
- each calendar year has `>= 40` takeover rows

If this fails, close the semantic branch as **insufficient supply**. Do not relax pool tolerance, event spacing, lifecycle duration, or POI freshness to manufacture support.

### Frozen annual quality gate
For each year and each predeclared diagnostic horizon:

- `n >= 40`
- positive mark rate `>= 50%`
- average mark `>= 0%`
- zone invalidation `<= 30%`
- T+1 violations `= 0`

A production promotion needs a separate full economic gate; this diagnostic gate only decides whether a causal narrative has stable basic quality.

## Semantic pitfalls

- A stored `strict_lifecycle_start_idx` may correctly equal the final prerequisite bar. The first eligible lifecycle bar is **one bar later**; do not flag this as a future leak.
- Several valid events can share the same `symbol + combo + takeover_date`. Preserve multiplicity or use an internal event identity; do not collapse them into a dict keyed only by visible dates.
- An `outcome_fields_present=false` field is a safety marker, not an outcome field.
- A legacy result that contains exits/PnL or lacks strict lifecycle reconstruction cannot close a new semantic branch.

## Evidence from the strict daily closure

After lifecycle correction and independent chronology/T+1 verification, the three canonical daily narratives (`SSL→CHOCH→Demand OB`, `SSL→CHOCH→Bull FVG`, and `BOS→Demand OB`) all failed their fixed annual quality gate. A fourth, more literal liquidity-pool narrative (`two confirmed equal lows→SSL sweep→CHOCH→fresh Demand OB`) produced only 11 confirmed takeovers across 4,655 symbols, failing the supply gate before outcomes were opened.

**Do not restart these daily combinations by parameter tuning.** A new direction must add a genuinely different information class or a separately specified semantic primitive with its own predeclared supply and quality gates.
