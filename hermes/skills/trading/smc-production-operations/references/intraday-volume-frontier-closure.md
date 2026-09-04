# 15m price and volume-absorption research frontier closure

## Purpose

Use this reference when a new intraday SMC ontology is proposed after daily OHLCV branches have closed. It defines when a partial-range study may run, how to verify it, and when it must stop.

## Completed evidence: V539–V547

### Price-only chain (V539–V542)

Frozen chain: confirmed 3L/3R SSL sweep → BOS → bullish FVG → first touch/reclaim → next 15m entry.

- Outcome-blind seeds: 58,535
- Independent identity oracle: 58,535/58,535 equal
- One frozen strict-T+1 replay: 41,309 closed, T+1 violations=0
- WR 38.32%, AvgNet -0.2915%, PF 0.8628; 2026 AvgNet -0.6609%
- Status: closed, no variants.

### Volume/displacement/absorption chain (V543–V546)

Frozen new causal dimension: high-participation SSL sweep → high-volume/range BOS and FVG → low-participation first FVG retest reclaim → next 15m entry.

- Outcome-blind seeds: 12,327 across 4,690 symbols
- Independent identity oracle: 12,327/12,327 equal
- One frozen strict-T+1 replay: 8,805 closed, T+1 violations=0
- WR 39.01%, AvgNet -0.3236%, PF 0.8610, payoff 1.3461
- 2025 AvgNet +0.1734%; 2026 AvgNet -0.7589%
- Attribution: 52.25% reached MAE <= -1R; only 37.51% reached +1.5R and 27.70% reached the visible structural target. This is failure of post-entry survival, not a target/stop tuning invitation.
- Status: closed, no variants.

## Independent oracle discipline

1. Implement the causal state machine independently; do not import the seed generator.
2. Run real identity-set fixtures before full-universe work.
3. A qualifying first retest consumes its state even when a serial-position rule rejects the entry. Otherwise a later touch is incorrectly emitted as a second-retest setup.
4. Preserve every generator prerequisite in the oracle; in particular, reference-high updates must retain `high > active_low`.
5. Only `missing_identities=0` and `extra_identities=0` authorizes one frozen replay. An oracle mismatch authorizes no replay and no outcome reading.

## Source and stop boundary

Sina m15 has complete recent source-local coverage but starts in 2025, so it is partial-range research only. Baostock raw MTF is an audited cached subset, not a canonical full universe. Historical tick responses were not date-sensitive and cannot support PIT auction/order-flow research.

Do not retry either closed ontology with threshold, window, RR, stop, target, holding-period, calendar, clock-time, symbol, or ex-post winning-bucket changes. Reopen only with a genuinely new PIT causal data dimension that has same-source, date-sensitive, full-history canonical-universe coverage, then start again from outcome-blind seeds.

Authoritative reconciliation: `/root/.hermes/smc_audit/v547_local_smc_frontier_reconciliation_latest.json`.
