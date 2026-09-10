# -*- coding: utf-8 -*-
"""v4_d6_blocktrade_research.py —— D6 剩余源验证: 大宗折价族(研究侧)
审计设计(D6 冻结): 大宗折价率>8% → 同一管线 → PAPER 30 日 → rank 单调且月均≥10 笔才保留。
龙虎榜族已否决(预注册#23)。本脚本验大宗折价族(同探索框架):
  ① 族定义: A股(EQA) + 折价 DISCOUNT_RATIO ≤ −8%(即成交价低于收盘 8%) 且 买方=机构专用
  ② 频率: 月度 n(数据窗 2026h2)
  ③ 前向: D1/D5/D10/D20(东财内置) + 剔除一字板
  ④ 排序: 折价深度分位 × D5 单调性
预注册(探索, 生产判定属 PAPER 30 日):
  E1 月均≥10; E2 D5 中位>0; E3 分位单调比≥0.75
输出: handover/V4_D6_大宗折价研究.json"""
import glob, io, json, os, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC = [r"E:\test\smc_project\hermes\blocktrade_cache\blocktrade_2026h2.json",
       r"E:\root\.hermes\blocktrade_cache\blocktrade_2026h2.json"]
rows = []
for p in SRC:
    if os.path.exists(p):
        try:
            lst = json.load(open(p, encoding="utf-8"))
            if isinstance(lst, list):
                rows = lst
                break
        except Exception:
            continue
print(f"大宗记录: {len(rows)}")

# ① 族定义
def in_family(r):
    if r.get("SECURITY_TYPE") != "EQA":
        return False
    disc = r.get("DISCOUNT_RATIO")
    if disc is None or disc > -0.08:          # 折价至少 8%
        return False
    if "机构" not in str(r.get("BUYER_NAME") or ""):
        return False
    # 可交易: 剔一字板(当日已涨停买不进 → 看次日, 数据只有当日涨幅; 近似剔除 ≥9.9)
    ch = r.get("CHANGE_RATE") or 0
    code = str(r.get("SECURITY_CODE") or "")
    cap = 19.9 if (len(code) == 6 and code[0] in "36") else 9.9
    if ch >= cap:
        return False
    return True

fam_rows = [r for r in rows if in_family(r)]
print(f"折价8%+机构买: {len(fam_rows)}")

# ② 月度频率
bym = defaultdict(list)
for r in fam_rows:
    d8 = str(r.get("TRADE_DATE") or "")[:10].replace("-", "")
    bym[d8[:6]].append(r)
monthly = {m: len(v) for m, v in sorted(bym.items())}
print(f"月度: {monthly}")

# ③ 前向收益
def med(v):
    v = sorted(x for x in v if x is not None)
    return round(v[len(v) // 2], 2) if v else None
def avg(v):
    v = [x for x in v if x is not None]
    return round(sum(v) / len(v), 2) if v else None
fwd = {}
for name, key in (("D1", "CHANGE_RATE_1DAYS"), ("D5", "CHANGE_RATE_5DAYS"),
                  ("D10", "CHANGE_RATE_10DAYS"), ("D20", "CHANGE_RATE_20DAYS")):
    vals = [r.get(key) for r in fam_rows]
    vv = [x for x in vals if x is not None]
    wr = round(len([x for x in vv if x > 0]) / len(vv) * 100, 1) if vv else None
    fwd[name] = {"avg": avg(vals), "med": med(vals), "wr": wr, "n": len(vv)}
print(f"前向: {fwd}")

# ④ 折价深度分位 × D5
qu = []
for r in fam_rows:
    disc = r.get("DISCOUNT_RATIO")
    d5 = r.get("CHANGE_RATE_5DAYS")
    if disc is not None and d5 is not None:
        qu.append((disc, d5))          # disc 为负, 越负折越深
qu.sort()
if len(qu) >= 50:
    k = len(qu) // 5
    qtab = []
    for i in range(5):
        seg = qu[i * k:(i + 1) * k] if i < 4 else qu[4 * k:]
        qtab.append({"q": i + 1, "n": len(seg),
                     "disc_range": [round(seg[0][0] * 100, 1), round(seg[-1][0] * 100, 1)] if seg else None,
                     "avg_d5": round(sum(x[1] for x in seg) / len(seg), 2) if seg else None})
    means = [q["avg_d5"] for q in qtab if q["avg_d5"] is not None]
    n_up = sum(1 for a, b in zip(means, means[1:]) if b > a)
    mono = round(n_up / max(1, len(means) - 1), 2)
else:
    qtab, mono = None, None
print(f"折价深度五分位(D5): {qtab}")

months_n = list(monthly.values())
avg_month = round(sum(months_n) / len(months_n), 1) if months_n else 0
f5 = fwd.get("D5", {})
verdict = {"E1_月均≥10": avg_month >= 10,
           "E2_D5中位>0": (f5.get("med") or 0) > 0,
           "E3_分位单调": bool(mono is not None and mono >= 0.75),
           "explore_only": True,
           "note": "探索性验证; 生产采用与否由 PAPER 30 日决定(审计 D6 设计)"}
out = {"source": "blocktrade 东财大宗", "total": len(rows), "family_n": len(fam_rows),
       "monthly": monthly, "avg_per_month": avg_month,
       "forward": fwd, "quintile_discount_depth": qtab, "mono_ratio": mono,
       "preregistered_explore": verdict,
       "caveat": "数据仅 2026h2 截面(~100日), 月频统计力弱; CHANGE_RATE_xDAYS 为东财口径"}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D6_大宗折价研究.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_D6_大宗折价研究.json")