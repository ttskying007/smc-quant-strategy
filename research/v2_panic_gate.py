# -*- coding: utf-8 -*-
"""PANIC 降仓闸门 WF 稳定性验证(真值 Regime 六态)
发现: 事件腿在 PANIC 态 WR 39.3%/avg +0.78%(all), OOS n=8 avg+0.27% —— 唯一危险态。
假设: PANIC 态降仓(×0.5)或空仓可提升风险调整收益。
方法: 用 core/regime.py 真值, 对事件腿 1640 笔做:
  A臂 = 基线(全时段同仓位)
  B臂 = PANIC 空仓
  C臂 = PANIC 半仓
  D臂 = PANIC+SIDEWAYS 空仓(两弱态都停)
+ WF 稳定性: 8 个滚动窗内逐窗比较 A vs B(净风险调整收益), 若 B 在大多数窗占优且 OOS 成立 → 晋级候选。
预注册线: B臂 OOS riskadj > A臂 且 WF >=5/8 窗占优, 否则仅研究保留。
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.regime import market_regime

OOS = "20250701"
rows = [r for r in csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net"] = float(r["net_pnl_pct"])
    r["risk_pct"] = float(r.get("risk_pct") or 0)

# regime 缓存(真值, 决策时点可得)
rg_cache = {}
for r in rows:
    d8 = r["entry_date"]
    if d8 not in rg_cache:
        rg = market_regime(d8)
        rg_cache[d8] = rg["regime"] if rg else "UNKNOWN"
    r["regime"] = rg_cache[d8]

print("Regime 覆盖:", {k: v for k, v in defaultdict(int, {k: sum(1 for x in rows if x['regime'] == k) for k in {x['regime'] for x in rows}}).items()})

def arm_net(trs, mode):
    """计算该臂的风险调整净收益(riskadj): Σ net/risk_pct —— 跳过的算 0 仓贡献 0。
    mode: 'A' 全做 | 'B' PANIC不做 | 'C' PANIC半仓 | 'D' PANIC+SIDEWAYS不做"""
    tot = 0.0
    for t in trs:
        if t["risk_pct"] <= 0:
            continue
        w = 1.0
        if mode == "B" and t["regime"] == "PANIC":
            continue
        if mode == "C" and t["regime"] == "PANIC":
            w = 0.5
        if mode == "D" and t["regime"] in ("PANIC", "SIDEWAYS"):
            continue
        tot += w * t["net"] / t["risk_pct"]
    return tot

def arm_stats(trs, mode, oos):
    sel = [t for t in trs if (t["entry_date"] >= OOS) == oos]
    if not sel:
        return {"n": 0}
    nets = []
    for t in sel:
        if mode == "B" and t["regime"] == "PANIC":
            continue
        if mode == "D" and t["regime"] in ("PANIC", "SIDEWAYS"):
            continue
        w = 0.5 if (mode == "C" and t["regime"] == "PANIC") else 1.0
        nets.append(w * t["net"])
    if not nets:
        return {"n": 0}
    w_ = [x for x in nets if x > 0]
    l_ = [x for x in nets if x <= 0]
    return {"n": len(nets), "avg": round(sum(nets)/len(nets), 3), "wr": round(len(w_)/len(nets), 3),
            "pf": round(sum(w_)/abs(sum(l_)), 2) if l_ and sum(l_) != 0 else 99}

# ---- 全样本 A/B/C/D ----
out = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S")}
for mode in ("A", "B", "C", "D"):
    o = {"IS": arm_stats(rows, mode, False), "OOS": arm_stats(rows, mode, True),
         "riskadj_all": round(arm_net(rows, mode), 3)}
    out[mode] = o
    print(f"\n== {mode} 臂 ==")
    print(f"  IS={o['IS']} OOS={o['OOS']} riskadj={o['riskadj_all']}")

# ---- WF 稳定性: 8 滚动窗(12m 训练→3m 测试), 每窗比较 A vs B 的 OOS 期风险调整收益 ----
def shift_ym(m, n):
    y, mm = int(m[:4]), int(m[4:6])
    t_ = y * 12 + mm - 1 + n
    return f"{t_//12:04d}{t_%12+1:02d}"

by_month = defaultdict(list)
for t in rows:
    by_month[t["entry_date"][:6]].append(t)
months = sorted(by_month)

wf = []
cur_m = months[0]
while True:
    tr_end = shift_ym(cur_m, 12)
    te_start, te_end = tr_end, shift_ym(tr_end, 3)
    if te_start > months[-1]:
        break
    te_tr = [t for m in months if te_start <= m < te_end for t in by_month[m]]
    if len(te_tr) >= 4:
        a_ = arm_net(te_tr, "A")
        b_ = arm_net(te_tr, "B")
        d_ = arm_net(te_tr, "D")
        wf.append({"test": f"{te_start}~{te_end}", "n": len(te_tr), "A_riskadj": round(a_, 2),
                   "B_riskadj": round(b_, 2), "D_riskadj": round(d_, 2),
                   "B_beats_A": b_ > a_, "D_beats_A": d_ > a_})
    cur_m = shift_ym(cur_m, 3)

b_wins = sum(1 for w in wf if w["B_beats_A"])
d_wins = sum(1 for w in wf if w["D_beats_A"])
for w in wf:
    print(f"  {w['test']}: n={w['n']:3d} A={w['A_riskadj']:8.2f} B={w['B_riskadj']:8.2f} D={w['D_riskadj']:8.2f} B>A:{w['B_beats_A']} D>A:{w['D_beats_A']}")

verdict = {
    "wf_windows": len(wf), "B_beats_A_windows": b_wins, "D_beats_A_windows": d_wins,
    "B_oos_riskadj": out["B"]["riskadj_all"], "A_oos_riskadj": out["A"]["riskadj_all"],
    "B_oos_beats_A": out["B"]["OOS"].get("avg", -99) > out["A"]["OOS"].get("avg", -99),
    "B_oos_pf": out["B"]["OOS"].get("pf"), "A_oos_pf": out["A"]["OOS"].get("pf"),
}
# 预注册: WF >= 5/8 且 OOS 双升
verdict["promote_B"] = (b_wins >= len(wf) - 3) and verdict["B_oos_beats_A"]
verdict["promote_D"] = (d_wins >= len(wf) - 3) and out["D"]["OOS"].get("avg", -99) > out["A"]["OOS"].get("avg", -99)
out["verdict"] = verdict
print(f"\n== 预注册判定 ==")
print(f"  WF: B>A {b_wins}/{len(wf)} 窗 | D>A {d_wins}/{len(wf)} 窗")
print(f"  OOS: B avg={out['B']['OOS']['avg']} vs A {out['A']['OOS']['avg']} | PF {out['B']['OOS']['pf']} vs {out['A']['OOS']['pf']}")
print(f"  → PANIC空仓晋级: {verdict['promote_B']} | PANIC+SIDEWAYS空仓晋级: {verdict['promote_D']}")

json.dump(out, open(r"E:\test\smc_project\research\handover\PANIC闸门WF稳定性.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/PANIC闸门WF稳定性.json")