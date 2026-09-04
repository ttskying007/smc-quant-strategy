#!/usr/bin/env python3
"""SMC V4 — 最终报告"""
import json, os

opt = os.path.expanduser('~/.hermes/smc_opt_v4')
best = os.path.join(opt, 'best_params.json')

with open(best) as f:
    d = json.load(f)

print('=' * 70)
print('  SMC V4 全自动迭代 — 最终验证报告')
print('=' * 70)
print(f'\n🏆 目标验证:')
print(f'   目标1: WR > 80%  -> {"✅ " + str(d.get("best_wr_s","N/A")) + "%" if d.get("best_wr_s",0) >= 80 else "❌ " + str(d.get("best_wr_s","N/A"))}')
print(f'   目标2: PF > 5.0  -> {"✅ " + str(d.get("best_pf_s","N/A")) if d.get("best_pf_s",0) >= 5.0 else "❌ " + str(d.get("best_pf_s","N/A"))}')
print(f'   目标3: WR>80%比例 -> {d.get("best_high_wr_ratio",0)*100:.1f}%')
print(f'\n📊 绩效指标:')
print(f'   Score:     {d.get("best_score")}')
print(f'   WR_s:      {d.get("best_wr_s")}%')
print(f'   PF_s:      {d.get("best_pf_s")}')
print(f'   SR_s:      {d.get("best_sr_s")}')
print(f'   WR_t:      {d.get("best_wr_t")}%')
print(f'   N_strict:  {d.get("best_n_strict")}')
print(f'   N_total:   {d.get("best_n_total")}')
print(f'\n⚙️ 最佳参数:')
params = d.get('best_params', {})
for k, v in sorted(params.items()):
    print(f'   {k:>25s}: {v:>8.4f}')

# Save canonical
with open(os.path.join(opt, 'canonical_params.json'), 'w') as f:
    json.dump(params, f, indent=2)
print(f'\n✅ 参数已持久化到 canonical_params.json')

# Summary
iters = [f for f in os.listdir(opt) if f.startswith('iter_')]
print(f'\n📈 总迭代: {len(iters)} / 200 轮')
print(f'{"=" * 70}')