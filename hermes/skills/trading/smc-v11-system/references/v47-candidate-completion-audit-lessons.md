# V47 Candidate Completion Audit Lessons

Date: 2026-05-26
Scope: SMC V47 candidate execution after V46.1 provenance/sync repair.

## Core workflow lesson

When the user asks whether previously planned SMC work is "done", do not answer from implementation presence alone. Build or run an explicit completion audit that checks:

1. production/current output metrics,
2. candidate output metrics,
3. frontend API contract state,
4. signal-specific audit outputs,
5. remaining architectural gaps.

Use status labels that distinguish:

- `COMPLETE`: active production/current output passes;
- `COMPLETE_CANDIDATE`: isolated candidate output passes but is not yet safe to publish;
- `PARTIAL`: audit exists but does not close the full loop;
- `NOT_COMPLETE`: no passing output or known architectural gap remains.

This avoids falsely declaring completion when a candidate improved one failure mode but degraded production requirements.

## V47 candidate evidence pattern

A safe V47-style candidate should be generated separately from production outputs first. In this session the candidate path was:

```text
/root/.hermes/scripts/v25/v47_candidate_engine.py
/root/.hermes/smc_opt_v47_candidate/
```

It replayed V46.1 base setups with:

- zone-mid/deeper executable entry,
- structural raw-zone / sweep SL,
- TP1/TP2 partials plus liquidity/structure runner,
- source_signal / wave_turn / gap provenance preserved.

Do not publish such a candidate just because some micro-metrics improve. Compare against production acceptance gates.

Example comparison from the session:

| Metric | V46.1 production | V47 candidate | Meaning |
|---|---:|---:|---|
| trades | 415 | 2570 | recall expanded too much |
| WR | 84.1% | 65.18% | not publishable |
| SL rate | 15.66% | 34.47% | not publishable |
| avg pnl | 6.508% | 3.826% | weaker single-trade quality |
| avg entry zone pos | 0.99 | 0.583 | entry location improved |
| fake SL rate | 12.05% | 8.02% | SL quality improved |
| sold early rate | 85.78% | 49.03% | runner improved |

Conclusion pattern:

```text
Candidate proves direction, but cannot replace production until WR/SL quality gates recover.
Next step: apply entry/SL/runner only to the existing high-quality kept set, or restore equivalent V46.1 layer gates.
```

## Completion audit script pattern

A reusable audit script should report each open task with status + evidence fields, not prose only. It should write JSON under `smc_audit/`, e.g.:

```text
/root/.hermes/scripts/v25/audit_v47_unfinished_completion.py
/root/.hermes/smc_audit/v47_unfinished_completion_audit.json
```

Expected checks for this class of work:

- entry productionization: `avg_entry_zone_pos` current and candidate;
- structural SL: structural rule coverage and fake-SL delta;
- runner/liquidity exit: sold-early rate and MFE capture;
- Pine-like FVG: dedicated FVG audit exists and has zero failure counts;
- wave structure: BOS/CHOCH/MSS have wave-layer labels, not just LuxAlgo currentLevel labels;
- rebuild: new output directory exists and has report/trades/picks.

## Pine-like FVG audit lesson

Generic signal audit may miss FVG if it reads the wrong family bucket. Add a dedicated FVG audit that checks each FVG trade against K-line facts:

- gap bounds exist (`gap_low/gap_high` or raw zone bounds),
- a Pine-like bullish FVG exists near the zone index (`low[i] > high[i-2]`),
- stored bounds match the K-line gap within tolerance,
- price touched the gap before/at entry,
- optionally flag whether gap fully filled before/at entry.

Example output shape:

```json
{
  "v46": {"n_fvg": 262, "failure_counts": {}},
  "v47": {"n_fvg": 1616, "failure_counts": {}}
}
```

## Wave-structure audit lesson

Do not conflate OB wave-turn sync with full structure sync. OB can have `wave_turn_label` while BOS/CHOCH/MSS remain LuxAlgo currentLevel events without wave labels.

Audit separately:

- frontend `signals_list` families `bos/choch/mss`,
- number with `wave_turn_label`, `wave_ref_idx`, or wave-derived pivot rule,
- trade-level `struct_event` wave fields.

If `wave_labeled == 0`, mark wave-structure unification `NOT_COMPLETE` even when OB labels are complete.

## Production publishing rule

Keep frontend on the current production version if the candidate fails any quality gate, even if candidate fixes a specific issue.

For this SMC workflow, candidate publish gates should include at least:

```text
WR >= 80%
SL rate <= 18%
avg_entry_zone_pos < 0.75
sold_early_rate < 55%
fake_sl_rate < 8%
```

If WR/SL fail, report `COMPLETE_CANDIDATE`, not `COMPLETE`, and do not switch frontend outputs.
