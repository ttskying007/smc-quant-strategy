# Partial-history parent-child MTF research: V562–V565

## Durable correction

When the user’s goal is strategy research, do **not** replace the work with a data-completeness audit or declare the overall research frontier closed merely because the available same-source history is only one or two years. Keep production claims constrained, but use the coherent available range for no-write research.

## Required contract

For a partial-history exploration, predeclare both layers:

- **Research support:** normally total unique identities >=1,000 and >=300 per available calendar year.
- **Strategy gate:** total n>=1,000; each available year>=300; WR>=55%; AvgNet>=+0.50%; PF>=1.15; payoff>=0.70; each available year AvgNet>0; T+1 violations=0.

Then run: outcome-blind seeds -> independent raw-bar identity oracle -> one frozen strict-T+1 replay -> recompute metrics from per-trade rows.

## Parent-child MTF examples

### V562: support failure without opening outcomes

Frozen chain: `ex-stock industry confirmed daily BOS -> constituent confirmed M15 SSL sweep/reclaim/confirmed-LH CHOCH -> D+1 daily open`.

It produced only 6 seeds (3 in 2025, 3 in 2026), so it failed support before any outcomes were read. Correct action: close this exact ontology; do not loosen its swing/CHOCH conditions to force a replay.

### V563–V565: adequate supply but economic failure

A distinct intraday child semantic was defined instead of relaxing V562:

`ex-stock industry confirmed daily BOS on D -> constituent completed 09:30–10:00 opening range -> morning sweep below opening SSL and close-back -> morning close above opening BSL -> D+1 daily open`.

- Outcome-blind V563 supply: 3,436 unique identities (2025 2,164; 2026 1,272).
- Independent V564 raw oracle: 3,436 expected / 3,436 reconstructed; missing=0, extra=0.
- V565 frozen execution: D+1 daily open; stop=opening raid low*0.995; nearest unconsumed entry-visible daily 3L/3R high with RR>=1.5; exits earliest D+2; conservative stop-first; 20 sessions; fee 0.20%.
- V565 replay: n=2,126; WR=29.1157%; AvgNet=+0.3210%; PF=1.1519; payoff=2.8045; annual AvgNet positive; T+1 violations=0.

It passed support, PF, payoff, annual-positive, and T+1 checks, but failed WR and AvgNet gates. Therefore close this ontology without tuning its morning window, stop, target, RR, holding period, year selection, or symbol subset.

## Mechanism lesson

Causal correctness and adequate opportunity density are necessary but insufficient. A same-day intraday opening acceptance can be real while still failing to survive overnight T+1 execution. High payoff/PF alone must not mask a low win rate. The next experiment must introduce a different causal explanation for overnight persistence, not an outcome-driven V563 variant.
