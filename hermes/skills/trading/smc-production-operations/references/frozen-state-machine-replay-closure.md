# Frozen state-machine replay: completeness and closure protocol

Use after a result-blind SMC state machine passes semantic validation and a single strict A-share T+1 replay is authorized.

## Before opening outcomes

Freeze every execution term, not only entry/stop/target: source seed identity, fee, structural stop anchor/buffer, structural target definition, planned-RR threshold, T+1 exit start, gap fills, same-bar collision order, time stop, and serial-position behavior. A missing execution term makes a reported net-performance result non-reproducible.

## If a preliminary run is contract-incomplete

1. Quarantine its report and trade file; never compare or report its metrics.
2. Correct **only** the omitted pre-frozen term.
3. Preserve the exact seed source, semantic identity, entry, stop, target, and every other contract term.
4. Execute one contract-complete replay, then independently reproduce every trade from raw bars.

## Required independent checks

- source seed count and yearly support count;
- no selector or outcome-field inclusion rule;
- pre-entry right-confirmed, unconsumed target identity and planned RR;
- structural stop anchor;
- gap, collision, time-stop, fee, and serial-position outcomes;
- zero same-day A-share exits;
- zero duplicate `symbol + entry_time` executed identities;
- recomputed rows and metrics equal the replay output.

## Interpretation and closure

Semantic correctness and economic edge are separate conclusions. A valid sequence—confirmed SSL → sweep/reclaim → CHOCH → displacement → causal POI → pristine touch → reclaim → hold → next-bar entry—can fail economically under strict execution. If the one frozen replay fails its preregistered support, annual stability, WR, average-net, PF, or payoff gate, close that ontology/source scope with **NO_VARIANTS_NO_PRODUCTION**. Do not post-hoc search timing, stop, target, hold, calendar, year, OB/FVG, selector, or execution variants.
