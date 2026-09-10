# -*- coding: utf-8 -*-
"""v4_d6_lhb_research.py —— D6 事件源扩展研究侧验证: 龙虎榜机构净买族
审计设计(D6 冻结): 龙虎榜机构净买 → 同一 classify 管线 → 各自 PAPER 30 日观察 →
rank 单调且月均≥10 笔才保留。

本脚本 = 研究侧第一步(数据探索 + 筛选规则制定):
  ① 全 lhb_cache(2026-06~) 统计: 机构买入信号(EXPLAIN 含 '机构')的频率/月度分布
  ② 定义候选族: EXPLAIN 匹配 "N家机构买入"(净机构买方) —— 排除 '机构卖出'
  ③ 前向收益验证: 用内置 D1/D5/D10/D20 字段(东财已算, 与我们事件腿 fwd5/fwd10 同口径
     可比) + 剔除一字板(CHANGE_RATE>=9.9 买不进)
  ④ rank 单调性: 按 BILLBOARD_NET_AMT/FREE_MARKET_CAP 分位看 D5 单调?
预注册(探索性, 不做生产判定 —— 生产判定属 PAPER 30 日):
  E1 月均 n≥10 → 频率可行; E2 D5 中位>0 → 方向; E3 分位单调(ρ>0.2) → 排序价值
输出: handover/V4_D6_龙虎榜研究.json"""
import glob, io, json, os, re, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LHB = r"E:\root\.hermes\lhb_cache"
OOS = "20250701"
rows_all = []
for fp in sorted(glob.glob(os.path.join(LHB, "*.json"))):
    try:
        lst = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if isinstance(lst, list):
        rows_all.extend(lst)
print(f"龙虎榜记录: {len(rows_all)} (文件 {len(glob.glob(os.path.join(LHB, '*.json')))})")

# ① 机构买入族定义
def is_inst_buy(r):
    ex = str(r.get("EXPLAIN") or "")
    return bool(re.search(r"机构买入", ex)) and "机构卖出" not in ex

inst = [r for r in rows_all if is_inst_buy(r)]
# 剔除一字板(T+1 买不进): 当日涨幅>=9.9(主板) 或>=19.9(创业/科创)
def tradable(r):
    ch = r.get("CHANGE_RATE") or 0
    code = str(r.get("SECURITY_CODE") or "")
    cap = 19.9 if (len(code) == 6 and code[0] in "36") else 9.9
    return ch < cap
inst_t = [r for r in inst if tradable(r)]
print(f"机构买入: {len(inst)} → 可交易(剔一字板): {len(inst_t)}")

# ② 月度频率
bym = defaultdict(list)
for r in inst_t:
    d8 = str(r.get("TRADE_DATE") or "")[:10].replace("-", "")
    bym[d8[:6]].append(r)
monthly = {m: len(v) for m, v in sorted(bym.items())}
print(f"月度: {monthly}")

# ③ 前向收益(东财内置字段, 决策时点后)
def med(v):
    v = sorted(x for x in v if x is not None)
    return round(v[len(v) // 2], 2) if v else None
def avg(v):
    v = [x for x in v if x is not None]
    return round(sum(v) / len(v), 2) if v else None

fwd = {}
for name, key in (("D1", "D1_CLOSE_ADJCHRATE"), ("D5", "D5_CLOSE_ADJCHRATE"),
                  ("D10", "D10_CLOSE_ADJCHRATE"), ("D20", "D20_CLOSE_ADJCHRATE")):
    vals = [r.get(key) for r in inst_t]
    pos = [x for x in vals if x is not None]
    wr = round(len([x for x in pos if x > 0]) / len(pos) * 100, 1) if pos else None
    fwd[name] = {"avg": avg(vals), "med": med(vals), "wr": wr, "n": len(pos)}
print(f"前向收益: {fwd}")

# ④ 分位单调性(净买强度 = NET/流通市值)
import math
qu = []
for r in inst_t:
    fmc = r.get("FREE_MARKET_CAP")
    net = r.get("BILLBOARD_NET_AMT")
    d5 = r.get("D5_CLOSE_ADJCHRATE")
    if fmc and net is not None and d5 is not None and fmc > 0:
        qu.append((net / fmc * 100, d5))
qu.sort()
if len(qu) >= 50:
    k = len(qu) // 5
    qtab = []
    for i in range(5):
        seg = qu[i * k:(i + 1) * k] if i < 4 else qu[4 * k:]
        qtab.append({"q": i + 1, "n": len(seg),
                     "avg_d5": round(sum(x[1] for x in seg) / len(seg), 2) if seg else None})
    # Spearman 简易(quintile 均值 vs 序)
    means = [q["avg_d5"] for q in qtab if q["avg_d5"] is not None]
    n_up = sum(1 for a, b in zip(means, means[1:]) if b > a)
    rho_mono = round(n_up / max(1, len(means) - 1), 2)
else:
    qtab, rho_mono = None, None
print(f"净买强度五分位(D5): {qtab}")

months_n = list(monthly.values())
avg_month = round(sum(months_n) / len(months_n), 1) if months_n else 0
f5 = fwd.get("D5", {})
verdict = {
    "E1_月均≥10": avg_month >= 10,
    "E2_D5中位>0": (f5.get("med") or 0) > 0,
    "E3_分位单调": bool(rho_mono is not None and rho_mono >= 0.75),
    "explore_only": True,
    "note": "探索性验证, 生产采用与否由 PAPER 30 日决定(审计 D6 设计)"
}
out = {"source": "lhb_cache 东财龙虎榜", "total_records": len(rows_all),
       "inst_buy": len(inst), "tradable": len(inst_t),
       "monthly": monthly, "avg_per_month": avg_month,
       "forward": fwd, "quintile_net_strength": qtab, "mono_ratio": rho_mono,
       "preregistered_explore": verdict,
       "caveat": "数据仅 2026-06 起(3个月), 统计力弱; D1-D30 为东财口径(与本组 fwd5/fwd10 近似可比)"}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D6_龙虎榜研究.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_D6_龙虎榜研究.json")