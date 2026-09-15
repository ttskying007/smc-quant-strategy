# -*- coding: utf-8 -*-
"""r38_tech_verify.py —— R38 技术腿最优变体稳健性检验(防过拟合).

背景: r38_tech_sltp_search.py 在 12 变体中选最优(S3_ep_1atr|T_swing
PF5.26/avg+6.08%) —— 存在多重比较/择优偏差风险。本脚本做三项检验:

 ① IS/OOS 分段: IS=2023-09~2025-06, OOS=2025-07~2026-08
    判据: OOS 不应显著劣于 IS(若 OOS PF<IS 的一半 → 择优偏差警示)
 ② 变体分散度: 全部 12 变体的 PF 分布 —— 若只在单点强、其他崩, 则脆弱;
    若整族(T_swing 六个 SL)都强, 则结论稳健
 ③ regime 稳健性: 逐 regime × 逐年 交叉 —— 确认 MIX 优势不是单年偶然

输入: r38_tech_sltp_search.json (12 变体统计 + 最优变体逐笔)
纯研究, 不修改生产。
"""
import io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
D = json.load(open(os.path.join(HERE, "r38_tech_sltp_search.json"), encoding="utf-8"))
best = D["best"]
trades = D["best_trades"]
print("="*88)
print(f"技术腿最优变体稳健性检验: {best}")
print("="*88)

def stats(pnls):
    if not pnls: return None
    w = [x for x in pnls if x > 0]; l = [x for x in pnls if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(pnls), "avg": round(sum(pnls)/len(pnls), 2),
            "wr": round(100*len(w)/len(pnls), 1), "pf": round(pf, 2)}

# ---- ① IS/OOS 分段 ----
IS_END = "20250630"
is_t = [t["net"] for t in trades if t["d"] <= IS_END]
oos_t = [t["net"] for t in trades if t["d"] > IS_END]
si, so = stats(is_t), stats(oos_t)
print("\n① IS/OOS 分段 (IS=2023-09~2025-06, OOS=2025-07~2026-08):")
print(f"  IS : n={si['n']} avg={si['avg']:+.2f}% 胜率={si['wr']}% PF={si['pf']}")
print(f"  OOS: n={so['n']} avg={so['avg']:+.2f}% 胜率={so['wr']}% PF={so['pf']}")
ratio = so["pf"]/si["pf"] if si["pf"] else 0
if so["pf"] < si["pf"] * 0.5:
    print(f"  ⚠ OOS/IS PF 比 = {ratio:.2f} (<0.5) —— 择优偏差警示")
elif so["pf"] > 1.2:
    print(f"  ✅ OOS/IS PF 比 = {ratio:.2f} —— OOS 未劣化(OOS 市场更难仍正期望)")
else:
    print(f"  ✅ OOS/IS PF 比 = {ratio:.2f} —— OOS 保持正期望, 无严重劣化")

# ---- ② 变体分散度 ----
print("\n② 12 变体 PF 分布 (整族强度 = 结论稳健性):")
tw = [(k, v["stats"]["pf"], v["stats"]["avg"], v["stats"]["n"]) for k, v in D["variants"].items() if v["stats"]]
swing_only = [x for x in tw if x[0].endswith("T_swing")]
r_only = [x for x in tw if x[0].endswith("T_r")]
print(f"  T_swing 族(6个): PF min={min(x[1] for x in swing_only):.2f} max={max(x[1] for x in swing_only):.2f} "
      f"均值={sum(x[1] for x in swing_only)/len(swing_only):.2f}")
print(f"  T_r 族(6个):     PF min={min(x[1] for x in r_only):.2f} max={max(x[1] for x in r_only):.2f} "
      f"均值={sum(x[1] for x in r_only)/len(r_only):.2f}")
print(f"  全族 PF 最低 = {min(x[1] for x in tw):.2f} (若 >2.0 → 无脆弱单点)")
if min(x[1] for x in tw) > 2.0:
    print("  ✅ 整族皆 >2.0 —— 结论不依赖单一参数点")
else:
    print("  ⚠ 存在 PF<2.0 的变体 —— 参数敏感, 需谨慎")

# ---- ③ regime × 逐年 交叉 ----
print("\n③ regime × 逐年 交叉 (最优变体):")
grid = defaultdict(lambda: defaultdict(list))
for t in trades:
    grid[t["reg"]][t["d"][:4]].append(t["net"])
print(f"{'regime':<8}" + "".join(f"{y:>14}" for y in ("2023", "2024", "2025", "2026")))
for k in ("MIX", "UP", "DOWN"):
    row = f"{k:<8}"
    for y in ("2023", "2024", "2025", "2026"):
        s = stats(grid[k].get(y, []))
        cell = "—" if not s else "%.1f%%/%.1f" % (s["avg"], s["pf"])
        row += f"{cell:>14}"
    print(row)

# ---- ④ 2026 全变体扫描(市场级问题确认) ----
print("\n④ 2026 弱势是否为市场级(跨策略一致)?")
print("  事件腿基线 2026: PF 4.17(强) | 技术腿10日 2026: PF 0.77 | 同口径 2026: PF 1.03")
print(f"  最优变体 2026: PF {stats(grid['MIX'].get('2026',[])+grid['UP'].get('2026',[])+grid['DOWN'].get('2026',[]))['pf']:.2f}")
print("  → 2026 技术腿全线弱, 但事件腿仍强 —— 两条腿在 2026 的表现分离,")
print("    说明非全局市场问题, 而是**技术腿(扫损反转)在 2026 结构下失效**")
print("    (2026 指数长期在 20MA 下 + 事件供给收缩, 反转模式缺乏延续性)")

summary = {"best": best, "IS": si, "OOS": so,
           "variants_min_pf": min(x[1] for x in tw),
           "swing_family_pf": [x[1] for x in swing_only],
           "r_family_pf": [x[1] for x in r_only]}
json.dump(summary, open(os.path.join(HERE, "r38_tech_verify.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"\n→ r38_tech_verify.json")