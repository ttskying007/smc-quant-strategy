# V502–V505 Weekly SSL → CHOCH → Demand OB transfer closure

Use when continuing pure-structure research after weekly rejection-block, BOS-demand, FVG-demand, and breaker transfers are closed.

## Frozen ontology

`confirmed weekly 2L/2R SSL → later weekly wick raid >=0.3% and close-back → within 12 completed weeks close >=0.3% above the most recent pre-raid confirmed weekly swing high (bull CHOCH) → nearest post-raid bearish weekly candle within 6 weeks as demand OB → first post-CHOCH daily touch → later reclaim → later hold → next-session open`.

This is distinct from weekly rejection-block because it requires a later weekly CHOCH, and distinct from generic weekly BOS-demand because it requires prior SSL manipulation and restricts the OB source to the post-raid displacement leg.

## Verified evidence

- Full universe: 4,897 symbols.
- Outcome-blind semantic seeds: 7,415; 2023/24/25/26 support 390/2,643/3,030/1,351.
- Independent raw-bar oracle: 7,415/7,415 pass; zero mismatch; zero outcome headers.
- Frozen execution: next open; SL=weekly raid low×0.99; nearest higher confirmed weekly swing high visible by hold as target; time30; fee0.2%; serial; gap-aware; conservative SL on collision; strict T+1; one replay.
- Closed trades: 6,843; 123 overlaps suppressed; T+1=0; duplicate entry=0.
- Aggregate: gross WR 72.0444%, net>=0.8 WR 58.0009%, AvgNet -0.0485%, AvgWin +4.2331%, AvgLoss -10.1574%, payoff 0.4168, PF 0.9840, SL 19.0998%.
- 2023: n=384, WR 58.5938%, AvgNet -2.2485%, payoff 0.3823, PF 0.5296.
- 2024: n=2,531, WR 65.4682%, AvgNet -0.2469%, payoff 0.5154, PF 0.9373.
- 2025: n=2,937, WR 79.2646%, AvgNet +0.5411%, payoff 0.3749, PF 1.2588.
- 2026: n=991, WR 72.6539%, AvgNet -0.4368%, payoff 0.3709, PF 0.8421.
- V505 independently recomputed every aggregate/year metric exactly; serial overlap, chronology and T+1 failures are zero.

## Decision

Close this ontology. Weekly CHOCH materially raises headline WR but does not solve loss asymmetry: average loss is 2.4× average win, aggregate PF is below 1, and 2023/2024/2026 expectancy is negative. The edge is again dominated by 2025. Do not reopen through raid threshold, CHOCH window, OB lookback, SL, TP, hold, year, or regime variants.

## Implementation pitfall

Forbidden outcome-header audits must use exact field names. Substring checks for `sl` falsely flag legitimate `weekly_ssl_*` semantic fields, just as substring stop classification can falsely flag `BSL_*` targets.

Artifacts: `v502_weekly_ssl_choch_demand_transfer_latest.json`, `v503_weekly_ssl_choch_demand_oracle_latest.json`, `v504_weekly_ssl_choch_demand_frozen_t1_replay_latest.json`, `v505_weekly_ssl_choch_demand_metric_audit_latest.json`.
