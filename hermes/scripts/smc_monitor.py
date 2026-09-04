#!/usr/bin/env python3
"""
SMC Optimization Monitor — Progress Dashboard
"""
import json, glob, os, sys
from datetime import datetime

opt_dir = os.path.expanduser('~/.hermes/smc_opt')

def main():
    # Check process
    import subprocess
    r = subprocess.run(['pgrep', '-f', 'smc_optimizer_v2'], capture_output=True, text=True, timeout=5)
    pids = [p.strip() for p in r.stdout.strip().split('\n') if p.strip()]
    
    print(f"SMC Optimizer: {'RUNNING PID=' + ', '.join(pids) if pids else 'NOT RUNNING'}")
    print()
    
    # Load best
    bp_file = os.path.join(opt_dir, 'best_params.json')
    if os.path.exists(bp_file):
        with open(bp_file) as f:
            best = json.load(f)
        print(f"BEST SCORE: {best.get('best_score', 0)}")
        bs = best.get('best_stats', {})
        print(f"  Avg Sharpe:   {bs.get('avg_sharpe', '?'):>8}")
        print(f"  Median WR:    {bs.get('median_wr', '?'):>8}%")
        print(f"  High WR>=33%: {bs.get('high_wr_ratio', '?'):>8}%")
        print(f"  SR>0 stocks:  {bs.get('pos_sharpe_ratio', '?'):>8}%")
        print(f"  Valid stocks: {bs.get('n_valid', '?'):>8}")
        bp = best.get('best_params', {})
        print(f"  Best params:")
        for k, v in bp.items():
            print(f"    {k}: {v}")
    print()
    
    # Iteration timeline
    iters = sorted(glob.glob(os.path.join(opt_dir, 'iterations', 'iter_*.json')))
    if not iters:
        print("No iterations found")
        return
    
    # Clean old v1 iterations (score < 1.0)
    v1_iters = [f for f in iters if 'iter_0' in os.path.basename(f) and '_01' <= os.path.basename(f)[5:9] <= '_05']
    v2_iters = [f for f in iters if f not in v1_iters]
    
    print(f"Iterations: {len(v2_iters)} (v2 engine) + {len(v1_iters)} (v1 legacy)")
    print()
    
    # Last 20 v2 iterations
    recent = v2_iters[-20:] if len(v2_iters) >= 20 else v2_iters
    if recent:
        print(f"{'Iter':>6} {'Score':>7} {'AvgSR':>7} {'MdWR':>6} {'HSWR':>6} {'SR>0%':>6} {'n':>4}")
        print(f"{'-'*50}")
        for f in recent:
            try:
                with open(f) as fp:
                    r = json.load(fp)
                s = r.get('score', 0)
                st = r.get('stats', {})
                fn = os.path.basename(f).replace('iter_', '').replace('.json', '')
                print(f"  {fn:>4} {s:>7.1f} {st.get('avg_sharpe','?'):>7} {st.get('median_wr','?'):>5}% "
                      f"{st.get('high_wr_ratio','?'):>5}% {st.get('pos_sharpe_ratio','?'):>5}% "
                      f"{st.get('n_valid','?'):>4}")
            except:
                pass
    
    print()
    
    # Performance over time
    scores = []
    for f in v2_iters[-50:]:
        try:
            with open(f) as fp:
                r = json.load(fp)
            scores.append(r.get('score', 0))
        except:
            scores.append(0)
    
    if scores:
        print(f"Recent performance:")
        print(f"  Last 5 avg: {sum(scores[-5:])/5:.1f}")
        print(f"  Last 10 avg: {sum(scores[-10:])/10:.1f}" if len(scores) >= 10 else "")
        print(f"  Best in window: {max(scores):.1f}")
    
    # Guard proxy
    print()
    pr = subprocess.run(['pgrep', '-f', 'proxy_guardian'], capture_output=True, text=True, timeout=5)
    proxy_pids = [p.strip() for p in pr.stdout.strip().split('\n') if p.strip()]
    print(f"Proxy Guardian: {'RUNNING PID=' + ', '.join(proxy_pids) if proxy_pids else 'NOT RUNNING'}")


if __name__ == '__main__':
    main()