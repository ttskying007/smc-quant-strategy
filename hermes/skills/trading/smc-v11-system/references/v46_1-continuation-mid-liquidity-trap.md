# V46.1 continuation mid-liquidity trap notes

Session lesson:
- After a four-dimensional pivot (signal_type × entry_mode × zone_quality × context) on 352 kept trades, the remaining stop-loss concentration was in FVG continuation buckets.
- The 8–12% liquidity-target band was the clearest hard-reject bucket: 55 trades, 72.7% WR, 25.5% SL, 14/34 remaining SLs after LIMIT retouch removal.
- The 5–8% continuation band remained profitable overall but carried elevated SL risk; it was better treated as micro-size (0.12) than hard-rejected.

Practical rule updates:
1. Remove LIMIT_RETOUCH_* as hard reject before touching continuation broadly.
2. Split continuation FVG by liquidity band:
   - 8–12% => hard reject.
   - 5–8% => keep, but micro-size.
   - 12%+ => preserve; only consider soft demotion if context is weak/minor.
3. Recompute final position_size after any soft penalties; do not let size reflect pre-penalty layer.


Validation nuance from the later review cycle:
- If a candidate rule collapses trade count too far or yields `CANDIDATE_FOR_REVIEW`, prefer demotion/micro-sizing over another hard reject unless the bucket is clearly a loss-maker.
- In the V46.1 loop, `FVG continuation + 12+ liquidity + MINOR + weak context` became the next residual drag after the 8–12% mid-liquidity trap; it was a better target for soft demotion than immediate removal.
- Always verify the post-penalty `position_size` distribution after editing `classify_layer`.
