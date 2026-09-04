# Persistent-validity W→D→60m SMC research protocol

## Trigger
Use when an outcome-blind multi-timeframe chain is logically correct at each local transition but can remain `ready` after its higher-timeframe permission, daily POI, or executable entry has already become invalid.

## Core lesson
A completed sequence is not sufficient. Every upstream state must remain valid continuously until the next state and until the execution decision. This is a **new causal ontology**, not a post-replay quality filter. Do not reopen the old ontology by adding these rules after inspecting economic outcomes.

## Required lifecycle checks
1. Reset external structure permission at every declared source-segment boundary; a weekly permission cannot cross a data quarantine/segment reset.
2. From daily SSL through entry decision, cancel a chain when a completed weekly close is below its protected low (`W1_INVALIDATED`).
3. From daily event-anchored demand OB through entry, cancel on a completed daily close below the POI low; after daily touch, cancel immediately on a completed 60m close below that low. Do not wait for the later daily close.
4. Allow exactly one daily first touch. After the first later 60m POI touch, a leave-and-re-enter transition before the local SSL reclaim is `REPEATED_D_POI_TOUCH_BEFORE_H2`, not delayed confirmation.
5. The local 60m event-anchored demand OB must overlap the active daily POI by price. A move away from the POI is not evidence of takeover for that POI.
6. Continue checks 1–5 during H3→H4 reclaim/hold. A later local confirmation cannot revive an invalidated upstream state.
7. At the next 60m open, cancel if `open <= max(local SSL raid low, daily POI low)`. This is a real-time order feasibility rule; do not call it an outcome filter.

## Validation sequence
- First emit only state identities, timestamps/zones, and cancellation codes; ban performance and exit fields.
- Recompute the full state machine with an independent primitive/state implementation; require exact identity equality.
- Only then pre-register and execute one strict T+1 replay for the new ontology.
- If that replay fails its fixed gates, close the new ontology. Do not tune lifecycles, windows, stop/target logic, time/year/stock slices, or selectors to rescue it.

## Session evidence
The V676 W→D→60m ontology passed semantic identity checks but its frozen replay exposed a structural lifecycle omission: 744 of 1,579 ready chains had lost an upper-state invariant before entry, including daily-POI invalidations, weekly protected-low invalidations, or an entry open at/below the declared structure stop. The correct response was a separately preregistered V683 persistent-validity ontology, not a variant replay.
