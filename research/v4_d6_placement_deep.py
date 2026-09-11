# -*- coding: utf-8 -*-
"""v4_d6_placement_deep.py —— D6 定增边缘候选的深层分解(V4 延伸, 预注册)
上轮: 定增 D20 +2.19/PF1.56(边缘), E 相依显著(hi +4.03 vs lo +1.27)。
未解: 定增 alpha 的来源结构 —— 两个候选机理:
  H1 发行价锚定: 定增价(通常为市价 8 折)构成硬支撑(破发=大股东亏, 护盘动机)
  H2 阶段效应: 披露日股价处于低位(超跌) → 均值回归
可分变量(决策时点可得):
  ① 披露日距 60 日高点回撤深度(低位组=回撤>20% vs 高位组)
  ② 事件前 20 日动能(涨过 vs 跌过)
预注册:
  X1 低位组(回撤>20%) D20 显著优于高位组(差>2pp) → H2 阶段效应主导
  X2 前期跌(20日 ret<0) D20 优于 前期涨 → 同 H2
  X3 双否 → alpha 来自发行价锚定(H1)或纯事件效应(不可分解, 如实报)
输出: handover/V4_D6_定增机理.json"""
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
                out = [{"t": str(b["t"])[:8], "o": float(b["o"]), "h": float(b["h"]),
                        "l": float(b["l"]), "c": float(b["c"])} for b in raw]
                return out if len(out) > 80 else []
            except Exception:
                return []
    return []

t0 = time.time()
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("""SELECT stock_code, MIN(date) FROM announce
               WHERE title LIKE '%向特定对象发行%' AND date >= '2025-01-01'
               GROUP BY stock_code""")
events = [(str(c), d.replace("-", "")) for c, d in cur.fetchall() if c and len(str(c)) == 6]
print(f"事件 {len(events)}, {time.time()-t0:.0f}s")

recs = []
for code, d8 in events:
    dd = load_daily(code)
    if not dd:
        continue
    idx = next((k for k, b in enumerate(dd) if b["t"] >= d8), None)
    if idx is None or idx + 21 >= len(dd) or idx < 60:
        continue
    op = dd[idx + 1]["o"]
    prev_c = dd[idx]["c"]
    if not op or op <= 0 or op > prev_c * 1.095:
        continue
    # 特征(决策时点): 60日高回撤 / 前20日动能
    hi60 = max(b["h"] for b in dd[idx - 59:idx + 1])
    drawdown = (dd[idx]["c"] / hi60 - 1) * 100
    mom20 = (dd[idx]["c"] / dd[idx - 20]["c"] - 1) * 100
    r20 = (dd[min(idx + 20, len(dd) - 1)]["c"] / op - 1) * 100 - FEE
    recs.append({"code": code, "d8": d8, "dd": round(drawdown, 1),
                 "mom": round(mom20, 1), "r20": round(r20, 2)})

def stats(v):
    if not v:
        return {"n": 0}
    xs = [r["r20"] for r in v]
    w = sum(x for x in xs if x > 0); l_ = abs(sum(x for x in xs if x <= 0))
    return {"n": len(xs), "avg": round(sum(xs) / len(xs), 3),
            "wr": round(len([x for x in xs if x > 0]) / len(xs) * 100, 1),
            "pf": round(w / l_, 2) if l_ else 99.0}

low_dd = [r for r in recs if r["dd"] <= -20]
high_dd = [r for r in recs if r["dd"] > -20]
down_mom = [r for r in recs if r["mom"] < 0]
up_mom = [r for r in recs if r["mom"] >= 0]
s_low, s_high = stats(low_dd), stats(high_dd)
s_dn, s_up = stats(down_mom), stats(up_mom)
diff_dd = round(s_low["avg"] - s_high["avg"], 3) if s_low.get("avg") is not None and s_high.get("avg") is not None else None
diff_mom = round(s_dn["avg"] - s_up["avg"], 3) if s_dn.get("avg") is not None and s_up.get("avg") is not None else None
verdict = {
    "X1_低位组(DD>20%)优于高位(差>2pp)": bool(diff_dd is not None and diff_dd > 2.0),
    "X2_前期跌优于前期涨(差>2pp)": bool(diff_mom is not None and diff_mom > 2.0),
    "X3_双否→发行价锚定或纯事件": None,
}
verdict["X3_双否→发行价锚定或纯事件"] = not (verdict["X1_低位组(DD>20%)优于高位(差>2pp)"]
                                             or verdict["X2_前期跌优于前期涨(差>2pp)"])
out = {"n_total": len(recs),
       "低位组(回撤>20%)": s_low, "高位组": s_high, "diff_pp": diff_dd,
       "前期跌20日": s_dn, "前期涨20日": s_up, "diff_mom_pp": diff_mom,
       "preregistered": verdict,
       "note": "与上轮同事件集(2025-01起, 股首现日, T+1开盘, 剔涨停开盘)"}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D6_定增机理.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"低位(n={s_low['n']}): {s_low}")
print(f"高位(n={s_high['n']}): {s_high}  差={diff_dd}")
print(f"前跌(n={s_dn['n']}): {s_dn}")
print(f"前涨(n={s_up['n']}): {s_up}  差={diff_mom}")
print("预注册:", json.dumps(verdict, ensure_ascii=False))
print("已写 handover/V4_D6_定增机理.json")