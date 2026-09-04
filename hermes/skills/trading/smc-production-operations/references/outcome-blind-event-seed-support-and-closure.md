# Outcome-blind event seed support and closure

Use this after a source-only PIT catalog passes and before any price/outcome Oracle or replay.

## Purpose

A valid source does not authorize economic testing by itself. First test whether a frozen, outcome-blind causal contract produces enough **independent** observations across decision years.

## Required order

1. Verify the source gate and freeze the event-to-state contract before reading outcomes.
2. Generate seeds using only event identity/time plus causal state dates and non-outcome state fields.
3. Audit chronology: every state event must occur after the information became available; entry eligibility must be next-session-or-later.
4. Audit payload schema using an exact outcome-field allow/deny list. Do not flag causal date names such as `entry_eligible_date`, `swing_date`, or `swing_to_sweep_bars` merely by substring; these locate a state and are not a price, return, or exit outcome.
5. Count both:
   - event rows: unique `(symbol, event_date)` identities;
   - independent causal chains: unique `(symbol, swing_date, sweep_date, response_date, entry_eligible_date)`.

Repeated disclosures that map to one same causal chain are correlated evidence, not independent strategy observations. Report multiplicity, repeated groups, and chain-level annual coverage.

## Frozen support gate

Pre-register minimum total support, each complete decision-year support, unique symbols, zero chronology violations, and zero exact outcome fields. Keep the decision-year denominator explicit; do not treat a partial current year as a failed complete-year test.

If any hard support condition fails:

- close the ontology without independent Oracle, replay, scanner, watchlist, or production actions;
- do not lengthen the event window, lower structural/volume requirements, split by regimes, or count repeated disclosures as extra support;
- write a compact closure artifact with raw versus independent-chain counts, annual support, failures, and the only legal reopen condition: a genuinely new independent PIT source.

A source-valid but support-insufficient ontology is a valid negative research result, not an invitation to sample-mine.

## Acceptance evidence

- source gate reference and identity coverage;
- generator declares `outcome_read=false` and no production writes;
- exact field-schema audit passes;
- chronology violations equal zero;
- raw-event and independent-chain support reconcile;
- explicit decision: pass to Oracle once, or close before outcomes.
