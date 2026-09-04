# Research lineage reconciliation and frontier classification

## Trigger

Use this when a frontier report labels a source/strategy as unavailable, closed, or promotable while later artifacts appear to disagree.

## Evidence precedence

1. Follow the active/latest artifact chain declared by the upstream report (`latest` → its mapping/features → frozen replay).
2. Verify that every script reads the same lineage; hard-coded dated paths are non-authoritative if they differ from an upstream latest artifact.
3. Separate **source admission** from **economic usefulness**:
   - `CLOSED_UNAVAILABLE`: coverage, PIT timestamp, raw alignment, or completeness gate failed. Do not claim an economic result.
   - `CLOSED_ECONOMIC`: source admission passed; immutable pre-outcome features and one frozen replay failed their declared usefulness gate. Do not reopen with thresholds, windows, combinations, exits, or subsets.
4. Correct the frontier inventory before deciding what remains untested. A stale diagnostic must not turn an economic failure into a data-availability failure, and it must not reopen a closed ontology.

## Required reconciliation checks

- Fixed identity count and annual coverage.
- PIT rule: source/report date and publication date must be strictly before entry; no same-day use unless release time is independently proved usable.
- Feature materialization count and request errors.
- Frozen replay join count, schema frozen before outcomes, and final gate decision.
- Exact source file path used by every involved script.

## Reporting rule

Record the contradiction, the path-level root cause, the authoritative classification, and whether the correction creates a legal new research action. Do not modify production, watchlist, frontend, or positions during reconciliation.

## Example from a shareholder-PIT audit

A later recovery diagnostic reported 60.55% coverage because it read an obsolete dated mapping. The upstream latest lineage had 4,807/4,832 PIT-ready identities (99.48%), all materialized, then failed its frozen economic feature replay. Correct status: `CLOSED_ECONOMIC`, not `CLOSED_UNAVAILABLE`; no parameter re-search is allowed.