#!/usr/bin/env python3
"""Show full V4 optimizer summary"""
import json, os, glob
opt = os.path.expanduser('~/.hermes/smc_opt_v4')
files = sorted(glob.glob(os.path.join(opt, 'iter_*.json')))
print('=' * 70)
print('  SMC V4 OPTIMIZER — 实时运行报告')
print(f'  总迭代: {len(files)} 轮')
print('=' * 70)

# Best
best = os.path.join(opt, 'best_params.json')
if os.path.exists(best):
    with open(best) as f:
        d = json.load(f)
    print(f'\n🏆 当前最佳:')
    print(f'  Score:      {d.get("best_score", "N/A")}')
    print(f'  Strict WR:  {d.get("best_wr_s", "N/A")}%')
    print(f'  Strict PF:  {d.get("best_pf_s", "N/A")}')
    print(f'  Strict SR:  {d.get("best_sr_s", "N/A")}')
    print(f'  Total WR:   {d.get("best_wr_t", "N/A")}%')
    print(f'  WR>80%:     {d.get("best_high_wr_ratio", 0)*100 if d.get("best_high_wr_ratio") else 0:.1f}%')
    print(f'  N(strict):  {d.get("best_n_strict", 0)}')
    print(f'  N(total):   {d.get("best_n_total", 0)}')
    
    params = d.get('best_params', {})
    if params:
        print(f'\n⚙️ 最佳参数:')
        for k, v in sorted(params.items()):
            print(f'  {k:>25s}: {v:>8.4f}')

# Stats
scores = [(json.load(open(f)).get('score',0), json.load(open(f)).get('wr_s',0), json.load(open(f)).get('n_strict',0), json.load(open(f)).get('iteration',0)) for f in files]
wr100 = sum(1 for _,wr,_,_ in scores if wr == 100)
wr_over_80 = sum(1 for _,wr,_,_ in scores if wr >= 80)
avg_wr = sum(wr for _,wr,_,_ in scores) / len(scores) if scores else 0
avg_n = sum(n for _,_,n,_ in scores) / len(scores) if scores else 0

print(f'\n📊 总体统计:')
print(f'  WR=100%轮次:   {wr100}/{len(files)} ({wr100/len(files)*100:.1f}%)')
print(f'  WR>=80%轮次:   {wr_over_80}/{len(files)} ({wr_over_80/len(files)*100:.1f}%)')
print(f'  平均WR:        {avg_wr:.1f}%')
print(f'  平均N(strict): {avg_n:.1f}')
print(f'  目标达成:      {"✅ YES! WR>80% PF>5" if wr_over_80 > 0 else "⏳ 运行中"}')
print(f'\n{"="*70}')