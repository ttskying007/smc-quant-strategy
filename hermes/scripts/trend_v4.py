#!/usr/bin/env python3
"""Show V4 optimizer trends"""
import json, glob, os
opt = os.path.expanduser('~/.hermes/smc_opt_v4')
files = sorted(glob.glob(os.path.join(opt, 'iter_*.json')))
print(f'Total iterations: {len(files)}')
for f in files[-20:]:
    with open(f) as j:
        d = json.load(j)
    print(f"  iter {d.get('iteration',0):>3d}: score={d.get('score',0):>5.1f} WR_s={d.get('wr_s',0):>5.1f}% PF_s={d.get('pf_s',0):>5.2f} SR_s={d.get('sr_s',0):>5.3f} nS={d.get('n_strict',0)}")
best = os.path.join(opt, 'best_params.json')
if os.path.exists(best):
    with open(best) as j:
        d = json.load(j)
    print(f"\nBEST: score={d.get('best_score')} WR_s={d.get('best_wr_s')}% PF_s={d.get('best_pf_s')} SR_s={d.get('best_sr_s')} WR_t={d.get('best_wr_t')}%")