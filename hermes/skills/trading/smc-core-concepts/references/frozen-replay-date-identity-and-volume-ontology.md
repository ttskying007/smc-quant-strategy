# Frozen replay identity and volume-ontology gate

## Cache-index pitfall

Rolling K-line caches make bar indices unstable: when a session is appended or history is revised, an old `sweep_idx` / `entry_idx` can refer to a different trading date. A replay that uses persisted indices can silently become a different backtest.

**Rule:** Persist immutable event identity (`symbol` plus event, confirmation, and eligible-entry trading dates). At replay time, map dates back to the current raw-bar array and reject missing or invalid date order. Do not treat a cache-relative index as an event key.

## Required replay checks

1. Generator emits only outcome-blind rows and records all causal dates.
2. Independent raw-bar oracle must reproduce exactly the seed identity set.
3. Frozen T+1 replay resolves entry/event dates dynamically, requires target confirmation before the event, and evaluates exits only from the next session.
4. Independent metric replay must match the trade set and metrics exactly.
5. If provider/source refresh changes the seed set, rerun the full generator → oracle → frozen replay → metric audit chain. Do not reuse a downstream approval artifact.

## Research discipline for a new volume ontology

A genuinely new volume-price ontology may be tested only when it has a different causal story, not merely a changed threshold. Predeclare sequence and support requirements before outcomes; e.g. high-effort spring/reclaim → low-effort test holding the spring → sign-of-strength confirmation → following-session open.

- Support gate: total `n >= 300`, each year `n >= 40`, strict chronology, no outcome fields.
- Promotion-quality gate: T+1=0, independent Oracle/metric match, all-year positive expectancy, and predeclared WR/AvgNet/PF/payoff floors.
- If the single frozen replay fails, close the ontology. Do not search test windows, volume ratios, SL/TP, holding period, or regime variants afterward.

## Proven findings from the V517/V527 program

- The high-relative-volume SSL spring/reclaim followed by next-bar response break passed the fixed replay and independent audit as a **shadow-only** research lineage; no current scanner row means `EMPTY_BOOK`, not a fallback to historical trades.
- A separate Spring → low-volume Test → SOS ontology passed support (8,124 seeds; 2023–26 = 1,571 / 2,500 / 2,451 / 1,602) and the independent Oracle (8,124/8,124) but failed its single frozen strict-T+1 replay: 7,329 closed trades, WR 62.2322%, AvgNet −0.3586%, payoff 0.5270, PF 0.8687; 2023/24/26 AvgNet = −0.8036% / −0.3611% / −1.1295%. Chronology remained clean (T+1 violations=0; target pre-spring=true). It is closed as `V529_FROZEN_REPLAY_FAIL__CLOSE_ONTOLOGY__NO_VARIANTS`; its test-window, volume-ratio, SL/TP, hold and regime parameters are not a research surface.
- A high-volume vs low-volume diagnostic can support an ontology's mechanism, but must never become a post-outcome selector or threshold-tuning license.
