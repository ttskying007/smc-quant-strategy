# -*- coding: utf-8 -*-
"""r38_tech_regime_sizing.py —— R38 技术腿 regime 仓位系数设计验证.

背景: R38e 发现技术腿(扫损反转)在 MIX 震荡 regime 最强(PF7.13), UP 趋势市
几乎无 edge(PF1.04), DOWN 弱(PF1.27)。事件腿恰好相反(UP 最强)。

设计(与生产 _risk_coef×_regime_coef 同构, 但按"信号×环境适配"而非单一市场强弱):
  技术腿仓位权重 w_tech:
    MIX  → 1.0 (满仓, 扫损反转的黄金环境)
    UP   → 0.3 (减仓, 趋势市扫损常续跌)
    DOWN → 0.3 (减仓, 但非零 —— DOWN 桶仍 PF1.27 正期望)

对比方案:
  A 等权(w=1)              : 现状
  B 设计值(1.0/0.3/0.3)    : 本方案
  C 激进(1.0/0.2/0)        : 只做 MIX
  D 反向(0.3/1.0/1.0)      : 反证(若 D 最优则适配假设错)

判据: 组合加权 avg / PF / MDD / 累计PnL 与 逐年稳定性。
输入: r38_tech_sltp_cache.json (同口径逐笔, 含 reg 字段)
纯研究, 不修改生产。
"""
import io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
CACHE = os.path.join(HERE, "r38_tech_sltp_cache.json")
if not os.path.exists(CACHE):
    print(f"缺缓存 {CACHE} —— 先运行 r38_tech_sltp.py"); sys.exit(1)
trades = json.load(open(CACHE, encoding="utf-8"))
print(f"技术腿同口径逐笔: n={len(trades)}")

SCHEMES = {
    "A 等权(1/1/1)":        {"MIX": 1.0, "UP": 1.0, "DOWN": 1.0},
    "B 设计(1.0/0.3/0.3)":  {"MIX": 1.0, "UP": 0.3, "DOWN": 0.3},
    "C 激进(1.0/0.2/0)":    {"MIX": 1.0, "UP": 0.2, "DOWN": 0.0},
    "D 反向(0.3/1.0/1.0)":  {"MIX": 0.3, "UP": 1.0, "DOWN": 1.0},
}

def combo(ws):
    """ws: [(net, w)] → 组合级指标(仓位加权, 权重=风险敞口占比)."""
    if not ws: return None
    contrib = [n*w for n, w in ws]
    wins = [x for x in contrib if x > 0]; loss = [x for x in contrib if x <= 0]
    pf = sum(wins)/abs(sum(loss)) if sum(loss) else 99
    eq = 0.0; peak = 0.0; mdd = 0.0
    for x in contrib:
        eq += x; peak = max(peak, eq); mdd = min(mdd, eq-peak)
    # 平均按"每单位敞口"归一(避免权重总量差异误导)
    tw = sum(w for _, w in ws)
    return {"n": len(contrib), "avg_exp": round(sum(contrib)/tw, 2) if tw else 0,
            "avg_raw": round(sum(contrib)/len(contrib), 2),
            "wr": round(100*len(wins)/len(contrib), 1), "pf": round(pf, 2),
            "mdd": round(mdd, 0), "sum": round(sum(contrib), 0), "exposure": round(tw, 0)}

print("="*96)
print("技术腿 regime 仓位系数 (输入=同口径SL/TP逐笔, 权重=风险敞口)")
print("="*96)
print(f"{'方案':<22}{'敞口':>7}{'每单位收益%':>11}{'原始均值%':>10}{'胜率':>7}{'PF':>7}{'MDD%':>9}{'累计%':>9}")
res = {}
for name, wmap in SCHEMES.items():
    ws = [(t["net"], wmap.get(t["reg"], 1.0)) for t in trades]
    s = combo(ws); res[name] = s
    print(f"{name:<22}{s['exposure']:>7.0f}{s['avg_exp']:>+10.2f}%{s['avg_raw']:>+9.2f}%{s['wr']:>6.1f}%{s['pf']:>7.2f}{s['mdd']:>9.0f}{s['sum']:>+9.0f}")

print("\n逐年 (方案B 设计值):")
byy = defaultdict(list)
for t in trades: byy[t["d"][:4]].append((t["net"], SCHEMES["B 设计(1.0/0.3/0.3)"].get(t["reg"], 1.0)))
for y in ("2023", "2024", "2025", "2026"):
    s = combo(byy.get(y, []))
    if s: print(f"  {y}: 敞口={s['exposure']:.0f} 每单位={s['avg_exp']:+.2f}% 胜率={s['wr']:.1f}% PF={s['pf']:.2f} 累计={s['sum']:+.0f}%")

print("\nregime 桶明细(同口径):")
byr = defaultdict(list)
for t in trades: byr[t["reg"]].append(t["net"])
for k in ("MIX", "UP", "DOWN"):
    ps = byr.get(k, [])
    if not ps: continue
    w = [x for x in ps if x > 0]; l = [x for x in ps if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    print(f"  {k}: n={len(ps)} avg={sum(ps)/len(ps):+.2f}% 胜率={100*len(w)/len(ps):.1f}% PF={pf:.2f}")

print("\n裁定:")
best = max(res.items(), key=lambda kv: kv[1]["avg_exp"])
print(f"  每单位收益最优 = {best[0]} ({best[1]['avg_exp']:+.2f}%)")
d = res["D 反向(0.3/1.0/1.0)"]
b = res["B 设计(1.0/0.3/0.3)"]
if d["avg_exp"] > b["avg_exp"]:
    print("  ⚠ D(反向) 优于 B —— 信号×环境适配假设在技术腿上不成立, 设计需否定")
else:
    print(f"  ✅ B(设计) 优于 D(反向) {b['avg_exp']-d['avg_exp']:+.2f}pp —— 适配假设成立")