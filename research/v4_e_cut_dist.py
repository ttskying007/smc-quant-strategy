# -*- coding: utf-8 -*-
"""v4_e_cut_dist.py —— E 档位切点的样本结构审计(预注册 #36)
背景: 锁定切点 q33=0.4559 / q67=0.5562(全历史窗口), 但 E 历史只有 60 天(n=60)。
预注册:
  C1 若 60 天样本的 q33/q67 与锁定值差 <0.03 → 切点稳定(60 天已够代表性)
  C2 若差 ≥0.03 → 切点漂移警示(需扩窗, 但切点仍锁定不重算——只记录)
  C3 E 分布的时间稳定性: 前后 30 天的分布对比(KS 检验近似: 分位差)
另: 检查 60 天内 E 的档位占比 vs 档位系数的设计占比。"""
import json, sys, io, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

h = json.load(open(r"E:\test\smc_project\research\handover\escore_history.json", encoding="utf-8"))
days = [d for d in h["days"] if d.get("e") is not None]
es = [d["e"] for d in days]
es_sorted = sorted(es)
n = len(es)
q33_now = es_sorted[int(0.33 * n)]
q67_now = es_sorted[int(0.67 * n)]
print(f"n={n}")
print(f"60天窗口: q33={round(q33_now,4)} q67={round(q67_now,4)}")
print(f"锁定切点: q33=0.4559 q67=0.5562")
d33 = round(q33_now - 0.4559, 4)
d67 = round(q67_now - 0.5562, 4)
print(f"差: Δq33={d33} Δq67={d67}")
# C1/C2
c1 = abs(d33) < 0.03 and abs(d67) < 0.03
print(f"C1(切点稳定,差<0.03): {c1}")
# C3: 前后30天分布
h1 = es[:30]; h2 = es[30:]
def qs(v):
    s = sorted(v)
    return [s[len(s)//4], s[len(s)//2], s[int(0.75*len(s))]]
q1, q2 = qs(h1), qs(h2)
print(f"\nC3 时间稳定性: 前30天 Q1/Q2/Q3 = {[round(x,3) for x in q1]}")
print(f"            后30天 Q1/Q2/Q3 = {[round(x,3) for x in q2]}")
shift = [round(q2[i]-q1[i],3) for i in range(3)]
print(f"            分位差 = {shift} ({'稳定' if max(abs(x) for x in shift)<0.15 else '漂移'})")
# 档位占比(用锁定切点)
from collections import Counter
b = Counter("low" if e <= 0.4559 else "mid" if e <= 0.5562 else "high" for e in es)
tot = sum(b.values())
print(f"\n档位占比(60天): " + ", ".join(f"{k}={v/tot*100:.0f}%" for k, v in sorted(b.items())))
verdict = {"C1_切点稳定": c1, "C2_漂移警示": not c1, "Δq33": d33, "Δq67": d67,
           "C3_分位差": shift, "C3_稳定": max(abs(x) for x in shift) < 0.15,
           "档位占比": {k: round(v/tot*100) for k, v in sorted(b.items())}}
print("\n预注册:", json.dumps(verdict, ensure_ascii=False))
json.dump(verdict, open(r"E:\test\smc_project\research\handover\V4_E切点结构审计.json", "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_E切点结构审计.json")