# V43 continuation / stoploss triage notes

Session takeaway:
- Replaying the strict no-retrace branch (`B_NO_RETRACE_STRICT`) produced 15 trades with WR 73.3% and SL 20.0%, so this branch is not a safe general repair.
- The failure pattern is consistent with over-aggressive chase-style entry under the label “no retrace” rather than a clean signal problem.
- A single alternative-liquidity proxy branch (`C_ALT_LIQ`) produced 1 trade, 100% WR, 0% SL, +15.98% PnL. It should be treated as an isolated extension only, not as a replacement for the official sweep path.
- FVG repair under the strict setup path produced no incremental trades beyond the frozen V41 path.
- Broader FVG continuation relaxations were rejected because they failed the acceptance gate (WR/SL/total PnL worse than the frozen baseline).

Decision rule reinforced:
1. Keep the official validated path unchanged until a candidate beats the frozen baseline.
2. Reject broad no-retrace loosenings that raise trade count but damage WR/SL.
3. If an alternative-liquidity proxy is accepted, keep it explicitly isolated and labeled as a separate branch.
4. Use entry-distance-to-zone-high, market state, and positive replay PnL as minimum filters before considering the proxy branch.
