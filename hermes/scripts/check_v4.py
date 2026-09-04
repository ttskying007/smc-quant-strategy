#!/usr/bin/env python3
"""Check V4 optimizer progress"""
import json, os
opt_dir = os.path.expanduser('~/.hermes/smc_opt_v4')
if not os.path.exists(opt_dir):
    print("No smc_opt_v4 directory")
    exit(0)
best_file = os.path.join(opt_dir, 'best_params.json')
if os.path.exists(best_file):
    with open(best_file) as f:
        data = json.load(f)
    print(f"Best Score: {data.get('best_score', 'N/A')}")
    print(f"Best WR_s: {data.get('best_wr_s', 'N/A')}%")
    print(f"Best PF_s: {data.get('best_pf_s', 'N/A')}")
    print(f"Best SR_s: {data.get('best_sr_s', 'N/A')}")
    print(f"Best WR_t: {data.get('best_wr_t', 'N/A')}%")
    print(f"WR>80% ratio: {data.get('best_high_wr_ratio', 0)*100:.1f}%")
    print(f"N strict: {data.get('best_n_strict', 0)}")
    print(f"N total: {data.get('best_n_total', 0)}")
    print()
    print("Best Params:")
    for k, v in sorted(data.get('best_params', {}).items()):
        print(f"  {k}: {v}")

# Iter files
import glob
iters = sorted(glob.glob(os.path.join(opt_dir, 'iter_*.json')))
print(f"\nTotal iterations: {len(iters)}")
if iters:
    last = iters[-1]
    with open(last) as f:
        d = json.load(f)
    print(f"Latest: iter {d.get('iteration')} score={d.get('score')} wr_s={d.get('wr_s')} pf_s={d.get('pf_s')}")