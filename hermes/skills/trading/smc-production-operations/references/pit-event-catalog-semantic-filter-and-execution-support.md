# PIT event catalog: semantic filter and execution-support gate

## Why this reference exists

A complete announcement catalog can create a large raw event count and an outcome-blind seed set that clears the research-support gate, while the **frozen executable trade set** fails the final sample floor. Treat those as different gates.

## Reusable protocol

1. Build a metadata-only, resumable catalog by calendar day. Persist completed/failed days and deduplicate by `(symbol, announcement_id)`.
2. Freeze the title semantics **before** reading OHLC. For an original-plan catalyst, require a title marker that identifies the primary disclosure (for example `草案`) and explicitly exclude summaries, implementation/progress notices, grants/exercises, adjustments, cancellations, legal opinions, and corrections.
3. Deduplicate eligible events by earliest `(symbol, event_date)` before structural reconstruction.
4. Generate outcome-blind causal identities using only event metadata plus OHLC through planned entry.
5. Make an independent raw-data Oracle rebuild the title eligibility and structure independently. Compare canonical `(symbol, planned_entry_date)` identity sets exactly; any missing/extra identity blocks replay.
6. Before outcomes are opened, pre-register execution eligibility. The strategy’s usable sample count is **closed trades**, not raw events or seed count: structural-target availability, invalid structural stops, serial-position rules, and strict T+1 forward-bar availability can reduce it.
7. Run exactly one frozen replay. If either executed total or an executed decision year falls below its prescribed sample floor, that is a gate failure—not permission to loosen structural-target, concurrency, or timing rules.

## Concrete audited example (research-only)

A complete 2023–2025 equity-incentive metadata catalog had 1,970 semantically filtered original-plan events and 1,257 outcome-blind seeds (`2023=307`, `2024=463`, `2025=487`). The independent Oracle matched `1257/1257`, with all causal nodes ordered and no outcome fields.

Under the pre-registered strict-T+1 structural execution contract, 258 seeds lacked a valid unconsumed pre-entry target with RR >= 1.5, leaving 995 executed trades (`2023=169`, `2024=414`, `2025=412`). It also failed economic requirements: WR 31.66%, average net +0.10%, PF 1.03, and 2023 average net -1.85%, although payoff was 2.22 and T+1 violations were zero.

Correct decision: close that exact **PIT equity-incentive-plan → confirmed BSL acceptance → demand-OB retest/reclaim → next open** ontology. Do not convert a raw-event/seed pass into a strategy pass, and do not rescue it with target, stop, hold, calendar, selector, or symbol variants.
