# V430–V437 production reset and Target-First DOL

Use when continuing the post-V185 causal production program.

## Production truth

- Daily refresh is fail-closed in `refresh_daily_750.py` and `smc_daily_ops.py`.
- Latest verified refresh: 4,905 requested, 4,903 successful, latest-date coverage 99.65%.
- V432 rejected V185 as a production baseline: all 247 V175 entries precede takeover confirmation, all 87 child rows use post-reclaim evidence and lack required provenance. `v185_daily_rematerialize.py` physically empties active/picks and exits 2.
- V365 is not a survivor/challenger. V366 showed every historical candidate entered before legal confirmation; V367 causal rebuild had zero survivors. V433 keeps it only as a no-buy negative control.
- Supply-Failure Breaker passed semantic generation and an independent oracle but failed the one frozen replay (2023 AvgPnL -0.4471%; 2023–24 epoch AvgPnL -0.0443%). Close the ontology; no window/SL/TP/hold variants.

## Target-First DOL frozen contract

Artifact: `v437_target_first_dol_latest.json`.

Sequence:

1. A 3L/3R swing high is confirmed and remains unconsumed.
2. It is selected before the later bullish BOS as the nearest visible BSL/DOL above event close.
3. The bullish BOS anchors a backward nearest bearish-candle demand POI.
4. DOL must remain unconsumed while price touches the POI, later reclaims it, and later holds above it.
5. Entry eligibility is the next session only; an entry gap through DOL or below POI invalidates the setup.
6. All V437 rows are non-tradable and contain no outcomes.

Full-market V437 result: 4,903 symbols, 173,590 lifecycle rows, 36,050 raw takeovers, 28,335 unique takeovers; yearly support 2023=2,052, 2024=8,819, 2025=13,119, 2026=4,338; semantic-order failures=0.

Important chronology lesson: a backward-scanned POI candle is physically before its anchoring BOS but only becomes semantically usable at the BOS. Validate `dol_confirm_idx < event_idx`, `poi_idx < event_idx`, then `event < touch < reclaim < hold < eligible`; do not require DOL confirmation to precede the historical POI candle.

## V438–V439 closure (2026-07-14)

V438 independently re-derived all semantics without importing V27/V437. It scanned 4,903 symbols and matched the complete V437 unique identity set exactly: source=28,335, oracle=28,335, mismatch=0, chronology failures=0, duplicate identities=0. The independent semantic gate passed.

V439 then ran the only allowed frozen replay: next-open entry after takeover, SL=`zone_low*0.99`, the preselected unconsumed DOL as the immutable target, max hold 30, strict T+1, gap-aware, conservative same-bar collision. Search count was exactly 1. Result: 27,937 closed rows, WR=47.1525%, AvgPnL=+0.9308%, median=-2.6883%, SL=49.7512%, T+1 violations=0. It failed the fixed promotion gate because 2023 was WR=34.2593%/Avg=-1.2315%, 2026 was WR=38.2898%/Avg=-0.9012%, and both chronological epochs had WR<50%.

Decision: `TARGET_FIRST_DOL_ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY_NO_VARIANTS`. Do not run target/window/SL/hold variants. Production remains `EMPTY_BOOK_FAIL_CLOSED`.

## V440–V443 Protected-Swing Transfer and program closure (2026-07-14)

The final predeclared ontology changed the causal identity to a two-BOS protected-boundary migration: first bull BOS establishes an old protected low; a later higher confirmed low forms while the old boundary holds; a later bull BOS transfers protection; then a transfer-leg demand POI must touch, reclaim, and hold before next-open eligibility.

V440 scanned 4,903 symbols and produced 19,128 unique takeovers with support in every 2023–2026 year and zero chronology failures. V441 independently re-derived the complete identity set without importing V27/V440: source=19,128, oracle=19,128, mismatch=0, chronology failures=0.

V442 ran exactly one frozen replay: next-open entry, SL=`new_protected_low*0.99`, nearest unconsumed confirmed BSL visible by takeover as target, max hold 30, strict T+1. Aggregate was n=18,360 / WR=57.2331% / AvgPnL=+0.6622%, but 2023 was WR=43.2710% / Avg=-2.6203%, 2024 Avg=-0.4945%, and the 2023–2024 epoch Avg=-0.8474%. It failed the fixed annual/epoch promotion gate with T+1=0. Close this ontology with no variants.

V443 records final state: V185 rejected research history, V365 rejected negative control, all three distinct pure-structure ontologies closed after independent semantics and one frozen replay, API picks/live picks empty, no new BUY events, and production remains `EMPTY_BOOK_FAIL_CLOSED`. Artifact: `/root/.hermes/smc_audit/v443_causal_production_rebuild_program_closure_latest.json`.
