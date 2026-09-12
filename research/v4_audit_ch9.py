# -*- coding: utf-8 -*-
"""v4_audit_ch9.py —— 审计 §9 亏损归因六类框架的事件腿落档(预注册 #42)
审计要求每笔亏损归因到: 方向错误/结构错误/位置错误/成交错误/退出错误/市场状态错误。
台账可用字段: reason(退出)/E 档(市场状态)/entry_date/pnl/hold_bars/rank/v_ratio。
本实验做**可用数据的可归因映射**(不是补字段, 而是回答: 现有台账能归因几类?)
预注册:
  C1 亏损笔按 reason 分解: SL_HIT+SL_GAP=结构失效类; BE+TIME(负)=时间退出类 → 覆盖率
  C2 亏损按 E 档分解: low 档亏损占比(市场状态错误类的可归因代理)
  C3 交叉表: E 档 × 亏损 reason → 最大亏损桶(可归因到'市场状态×退出'联合)
  C4 审计六类中现有台账无法归因的清单(如实报缺口, Phase E 补字段)"""
import csv, io, json, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv",
                                encoding="utf-8-sig", errors="replace")))
E = {d["d8"]: d.get("e") for d in json.load(open(
    r"E:\test\smc_project\research\handover\escore_history_full.json", encoding="utf-8")
).get("days", []) if d.get("e") is not None}
def band(e):
    return None if e is None else ("low" if e <= 0.4559 else "mid" if e <= 0.5562 else "high")

ev = []
for r in rows:
    if r.get("src") != "EVENT" or not r.get("net_pnl_pct"):
        continue
    d8 = str(r["entry_date"])[:10].replace("-", "")
    ev.append({"pnl": float(r["net_pnl_pct"]), "reason": str(r.get("reason") or ""),
               "band": band(E.get(d8)), "d8": d8})
losses = [t for t in ev if t["pnl"] <= 0]
n_l = len(losses)

# C1: reason 分解
by_reason = defaultdict(lambda: [0, 0.0])
for t in losses:
    by_reason[t["reason"][:14]][0] += 1
    by_reason[t["reason"][:14]][1] += t["pnl"]
print(f"亏损笔 n={n_l}/{len(ev)} = {n_l/len(ev)*100:.1f}%")
print("\nC1 亏损按退出 reason:")
struct_fail = time_neg = be = 0
for k, (c, s) in sorted(by_reason.items(), key=lambda kv: -kv[1][0]):
    print(f"  {k}: n={c} avg={s/c:.2f}")
    if "SL" in k:
        struct_fail += c
    elif "TIME" in k:
        time_neg += c
    elif "BE" in k:
        be += c
cov1 = (struct_fail + time_neg + be) / n_l * 100
print(f"  → 可归因: 结构失效(SL) {struct_fail} + 时间退出负 {time_neg} + 保本 {be} = {cov1:.0f}% 亏损笔")

# C2: E 档分解(市场状态类)
by_band = defaultdict(list)
for t in losses:
    if t["band"]:
        by_band[t["band"]].append(t["pnl"])
print("\nC2 亏损按 E 档(市场状态):")
for b in ("low", "mid", "high"):
    v = by_band.get(b, [])
    if v:
        print(f"  {b}: n={len(v)} 亏损贡献 {sum(v):.0f}pt avg={sum(v)/len(v):.2f}")

# C3: 交叉表
cross = defaultdict(lambda: [0, 0.0])
for t in losses:
    if t["band"]:
        cross[(t["band"], t["reason"].split("_")[0])][0] += 1
        cross[(t["band"], t["reason"].split("_")[0])][1] += t["pnl"]
big = sorted(cross.items(), key=lambda kv: kv[1][0], reverse=True)[:4]
print("\nC3 最大亏损桶(E×退出):")
for (b, rk), (c, s) in big:
    print(f"  {b}×{rk}: n={c} 贡献 {s:.0f}pt")

# C4: 缺口清单
verdict = {
    "C1_退出reason可归因率": round(cov1, 0),
    "C2_E档可归因(市场状态)": {b: len(v) for b, v in by_band.items()},
    "C3_最大亏损桶": [f"{b}×{rk} n={c} {s:.0f}pt" for (b, rk), (c, s) in big],
    "C4_无法归因类(需 Phase E 补字段)": {
        "方向错误": "需高周期方向字段(个股 r20/指数 beta) — 台账 rank 部分代理",
        "结构错误": "需 sweep/MSS 质量 字段 — 无",
        "位置错误": "需 entry 距 POI 距离 字段 — G5 proxy 部分代理(§16)",
        "成交错误": "需滑点/延迟记录 — v0 台账 filled vs 开盘 dev 2.41%(§41)代理",
        "退出错误": "reason 已可归因(SL/TIME/BE/TP2)",
        "市场状态": "E 档已可归因(强单调 §56)",
    },
    "归因覆盖": f"退出类 {cov1:.0f}% + 市场状态类(E)全量 → 审计六类中 2 类全量可归因, 3 类代理, 1 类(结构质量)缺口",
}
print("\n预注册:", json.dumps({k: v for k, v in verdict.items() if k != "C4_无法归因类(需 Phase E 补字段)"},
                               ensure_ascii=False)[:400])
json.dump(verdict, open(r"E:\test\smc_project\research\handover\V4_亏损归因六类.json", "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_亏损归因六类.json")