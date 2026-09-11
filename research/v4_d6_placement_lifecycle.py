# -*- coding: utf-8 -*-
"""v4_d6_placement_lifecycle.py —— D6 定增生命周期分解(V4, 预注册)
问题: 上轮"股首现日"聚合了不同文书——定增是长流程(预案→问询→批文→发行结果→上市),
不同节点的信息含量不同。分解:
  L1 预案/募集(最早节点, 董事会定案): 不确定性最高
  L2 批文/注册批复(监管放行): 不确定性消除
  L3 发行情况报告书(发行价揭示): 锚定确立
预注册:
  P1 若 L2(批文) D20 优于 L1(预案) >2pp → 监管放行是 alpha 主节点
  P2 若 L3(发行结果) D20 优于 L1 >2pp → 价格锚定是主节点
  P3 若三节点差均 <2pp → alpha 与文书节点无关(事件粗粒度即可, 如实报)
事件定义: 每股每类文书的**首次出现日**(分开统计, 同股可贡献多桶)
输出: handover/V4_D6_定增生命周期.json"""
import io, json, os, sqlite3, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
FEE = 0.2

def load_daily(code):
    for suf in ("_SZ", "_SH", "_BJ"):
        fp = os.path.join(KT, f"{code}{suf}_daily_800.json")
        if os.path.exists(fp):
            try:
                raw = json.load(open(fp, encoding="utf-8"))
                out = [{"t": str(b["t"])[:8], "o": float(b["o"]), "c": float(b["c"])} for b in raw]
                return out if len(out) > 80 else []
            except Exception:
                return []
    return []

CLASSES = [
    ("L1_预案募集", ["募集说明书", "预案"]),
    ("L2_批文", ["同意注册", "注册批复", "批文"]),
    ("L3_发行结果", ["发行情况报告书", "发行结果"]),
]
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("""SELECT stock_code, date, title FROM announce
               WHERE title LIKE '%向特定对象发行%' AND date >= '2025-01-01'""")
rows = cur.fetchall()
# 每股每类首现日
first = {}
for code, d, t in rows:
    if not code or len(str(code)) != 6:
        continue
    t = t or ""
    for label, kws in CLASSES:
        if any(k in t for k in kws):
            k = (str(code), label)
            d8 = str(d).replace("-", "")
            if k not in first or d8 < first[k]:
                first[k] = d8
            break                     # 一条公告只归一类(优先高级节点)
groups = {"L1_预案募集": [], "L2_批文": [], "L3_发行结果": []}
for (code, label), d8 in first.items():
    dd = load_daily(code)
    if not dd:
        continue
    idx = next((k for k, b in enumerate(dd) if b["t"] >= d8), None)
    if idx is None or idx + 21 >= len(dd):
        continue
    op = dd[idx + 1]["o"]
    if not op or op <= 0 or op > dd[idx]["c"] * 1.095:
        continue
    r20 = (dd[min(idx + 20, len(dd) - 1)]["c"] / op - 1) * 100 - FEE
    groups[label].append({"code": code, "d8": d8, "r20": round(r20, 2)})

def stats(v):
    xs = [r["r20"] for r in v]
    if not xs:
        return {"n": 0}
    w = sum(x for x in xs if x > 0); l_ = abs(sum(x for x in xs if x <= 0))
    return {"n": len(xs), "avg": round(sum(xs) / len(xs), 3),
            "wr": round(len([x for x in xs if x > 0]) / len(xs) * 100, 1),
            "pf": round(w / l_, 2) if l_ else 99.0}

s = {g: stats(v) for g, v in groups.items()}
a1 = s["L1_预案募集"].get("avg"); a2 = s["L2_批文"].get("avg"); a3 = s["L3_发行结果"].get("avg")
diff21 = round(a2 - a1, 3) if a1 is not None and a2 is not None else None
diff31 = round(a3 - a1, 3) if a1 is not None and a3 is not None else None
verdict = {
    "P1_批文优于预案>2pp": bool(diff21 is not None and diff21 > 2.0),
    "P2_发行结果优于预案>2pp": bool(diff31 is not None and diff31 > 2.0),
    "P3_节点无关(均<2pp)": None,
}
verdict["P3_节点无关(均<2pp)"] = not (verdict["P1_批文优于预案>2pp"] or verdict["P2_发行结果优于预案>2pp"])
out = {"events": {g: len(v) for g, v in groups.items()},
       "stats": s, "diff_L2_vs_L1": diff21, "diff_L3_vs_L1": diff31,
       "preregistered": verdict,
       "note": "每股每类首现日; 一条公告只归一类(优先高级节点 L3>L2>L1); T+1开盘, 剔涨停"}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D6_定增生命周期.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
for g in groups:
    print(f"  {g}: {s[g]}")
print(f"L2−L1={diff21}  L3−L1={diff31}")
print("预注册:", json.dumps(verdict, ensure_ascii=False))
print("已写 handover/V4_D6_定增生命周期.json")