# V420–V425 local pure-structure direction audit

Use when continuing post-V419 research without external data.

## Direction 1: EQL spring → SOS → LPS

Frozen semantic story: two confirmed 3L/3R equal lows → later spring sweep/reclaim → later break above pre-spring range high → fresh spring-wick demand retest/reclaim/hold → next-session open.

- V420 full market: 4,903 symbols, 1,572 semantic candidates, 170 takeover-confirmed.
- V421 frozen structural replay: n=169, WR=55.62%, AvgPnL=-0.8013%, PF=0.5783, payoff=0.4614, planned RR=0.7203, T+1=0.
- Conclusion: liquidity-pool spring semantics are valid but too sparse and economically negative. Do not threshold-mine this branch.

## Direction 2: failed close-through → breaker → LPS

Frozen semantic story: confirmed swing low → bearish close-through → close recovery above broken level → break above breakdown-candle high → breaker-body retest/reclaim/hold → next-session open.

- V422 full market: 4,903 symbols, 66,714 semantic candidates, 26,377 takeover-confirmed.
- V423 micro-target replay exposed an execution-contract defect: nearest micro swing gives WR=61.58% but AvgPnL=-0.8558%, payoff=0.369, planned RR=0.4388. Do not use nearest micro swing as structural BSL.
- V424 corrected structure hierarchy: SL below breaker body low, TP at confirmed 10L/10R macro swing. n=26,199, WR=50.80%, AvgPnL=-0.4846%, PF=0.8282, payoff=0.8021, planned RR=1.8937. Only 2025 was positive; 2023/24/26 remained negative.
- Conclusion: correcting SL/target hierarchy improves payoff and average PnL but does not produce stable positive expectancy. Close generic failed-breakdown breaker as a production branch; do not tune windows or thresholds.

## Integrity

V425 independently verified complete chronology, source seeds without outcome fields, exact next-session-open entries, and zero T+1 violations for V420–V424. Economic failures are valid, not replay corruption.

Artifacts: `v420_eql_spring_sos_lps_latest.json`, `v421_eql_spring_frozen_structural_replay_latest.json`, `v422_failed_breakdown_breaker_latest.json`, `v423_failed_breakdown_frozen_replay_latest.json`, `v424_failed_breakdown_hierarchical_replay_latest.json`, `v425_new_direction_integrity_latest.json`.
