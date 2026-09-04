# PIT announcement payload: source-to-semantic-frontier protocol

## Use when
A timestamped announcement title archive has sufficient event coverage but the causal fact of interest (for example forecast direction, a turnaround state, a disclosed amount, or a term) exists only in the document body.

## Durable procedure

1. **Keep title metadata and payload semantics separate.** A title proves occurrence and timestamp; it does not prove an omitted body field. Never infer the missing field from wording in the title.
2. **Run a deterministic source-only payload pilot.** Hash-sort immutable announcement IDs and sample a fixed count per year. For each row require HTTP success, `payload.art_code == announcement_id`, payload publication time equal to metadata publication time, and a nonempty body. Do not read OHLCV, seeds, trades, outcomes, PnL, targets, or stops.
3. **Build from the canonical metadata denominator.** Store each raw body atomically in a provider-isolated, year-partitioned cache with ID, both timestamps, transport type, body hash, and source identity. Retry transient transport failures before classifying an item as unavailable.
4. **Recover an empty inline body only from the same immutable announcement.** If its payload provides an official attachment URL, fetch and extract that attachment while retaining the same `announcement_id` and publication timestamp. This is a transport fallback, not a cross-source data fill. Record it distinctly from inline body transport.
5. **Require full coverage before semantics.** Persist unresolved identity/timestamp/empty-body failures separately. A complete local file count is insufficient: audit the original metadata denominator, per-year coverage, raw identity, timestamp parity, and nonempty content. Do not start a semantic catalog until this gate passes.
6. **Pre-register one exact semantic object.** Define the body section, allowed exact phrases, exclusions, canonical duplicate policy, support gate, and no-variant rule. Broad text search is an inventory only, not a semantic event.
7. **Use two independent source-only extractors.** Compare raw announcement IDs before canonicalization. A bounded-section parser and an independently written regex/parser must have exact identity parity. Any mismatch closes the object before market data is read.
8. **Separate close vs. new-field decisions.** If an exact semantic object fails support, close that object; do not widen its phrases, add quick reports, change years, or merge related wording. A different source-body field may be explored only through a fresh pre-registration proving it is an independent causal fact.

## Promotion boundary

A source and semantic pass only authorize a separately pre-registered causal ontology. The next required sequence remains:

`outcome-blind seed → independent causal oracle → one frozen strict-T+1 replay → independent metrics → scanner-time reconstruction → production/UI isolation audit`.

No payload catalog, semantic support count, or successful parser may write a production candidate or override `EMPTY_BOOK`.

## Evidence pattern from the earnings-payload case

A full 2023–2025 archive contained 8,849 timestamped earnings documents. The body source passed identity/time/coverage audit only after distinguishing inline text from same-announcement official-PDF attachment transport. A narrow explicit-positive forecast object then failed support and was closed. A separately pre-registered, bounded-section current forecast loss-to-profit turnaround object passed dual-parser identity parity and support. A later independently preregistered `PIT turnaround → post-disclosure structural acceptance → fresh OB → pristine touch → later reclaim → hold` ontology nevertheless produced only 3 outcome-blind valid chains from 1,672 canonical events (0/0/3 across 2023/2024/2025), missing its frozen 300-total, 50-per-year, and 150-symbol support gate. It was closed before Oracle or replay. This demonstrates why source qualification, field semantics, seed support, and economic strategy eligibility must remain separate gates.
