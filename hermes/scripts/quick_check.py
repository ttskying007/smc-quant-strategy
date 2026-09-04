#!/usr/bin/env python3
"""Quick status"""
import json
d=json.load(open('/root/.hermes/smc_opt_v4/iter_0085.json'))
print(f'Latest iter 85: score={d.get("score")} wr_s={d.get("wr_s")} pf_s={d.get("pf_s")} nS={d.get("n_strict")} nT={d.get("n_total")} wr80={d.get("high_wr_ratio")}')
# Show recent best
for i in range(80, 86):
    fn = f'/root/.hermes/smc_opt_v4/iter_{i:04d}.json'
    with open(fn) as f:
        d=json.load(f)
    print(f"  iter {d['iteration']:>3d}: score={d['score']:>5.1f} WR_s={d['wr_s']:>5.1f}% PF_s={d['pf_s']:>5.2f} nS={d['n_strict']} WR80={d.get('high_wr_ratio',0)*100:.0f}%")