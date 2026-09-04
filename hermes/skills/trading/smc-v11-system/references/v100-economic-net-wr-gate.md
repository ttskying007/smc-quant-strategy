# V100 Economic Net-WR Gate Audit

## Trigger
Use when a high gross WR branch is suspected to be inflated by sub-cost protective stops, especially V99/V100 style exits.

## Procedure
1. Recompute the upstream economic autopsy from code, not from a stale JSON artifact:
   - `cd /root/.hermes/scripts/v25 && python3 v99_economic_autopsy.py`
2. Recompute the candidate gate:
   - `python3 v100_economic_net_wr_gate.py`
3. Compare row-level PnL/exit consistency between the upstream autopsy simulation and candidate output before trusting aggregate WR.
4. Production gate for V100-style economic exits:
   - A/B candidate pool `n >= 100`
   - `net_wr_ge_0_8 >= 90%`
   - `small_win_0_to_0_8 == 0`
   - `t1_violations == 0`
   - If any gate fails, export `v100_active_picks.json` as `[]` and keep the branch research-only.

## 2026-07-07 Finding
After recomputing from code, the previously cited high `hybrid4_2r_6_3r` matrix was stale/inconsistent. Current verified metrics:

| Pool | n | net WR >=0.8 | small wins | loss % | avg PnL | PF |
|---|---:|---:|---:|---:|---:|---:|
| A/B | 113 | 78.76% | 0 | 21.24% | 2.5638% | 16.7631 |
| A | 60 | 73.33% | 0 | 26.67% | 2.3038% | 12.6005 |
| B | 53 | 84.91% | 0 | 15.09% | 2.8582% | 24.4368 |
| ABC | 855 | 72.40% | 0 | 27.60% | 2.6726% | 11.4169 |

Decision: V100 economic exit fixes the small-win pollution but fails the 90% economic net-WR production gate. Do not promote; current production remains V185.

## Pitfalls
- Do not trust old `v99_economic_autopsy.json` after upstream scripts or source artifacts change. Always rerun it.
- Reason-label differences (`PROTECT_STOP` vs `V100_ECONOMIC_PROTECT_STOP`) are harmless only if PnL and row keys match exactly.
- Never export active picks from a rejected research branch, even if its raw scanner has current candidates.
