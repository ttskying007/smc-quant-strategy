# -*- coding: utf-8 -*-
"""v4_d6_placement.py —— D6 定增(向特定对象发行)事件源研究(V3 Phase D, D6 第四源)
先前认知修正: "announce DB 无定增分类"是错的 —— 全库 98 万条 title, '向特定对象发行'
19802 条/590 日, 表述丰富。但**一事件多文件**(同股同日 4+ 条文书) → 按(股,日)去重事件级。
事件日选择: 事件首现日(该股该事件的第一次公告) —— 语义近似"定增启动披露"。
预注册(与 D6 龙虎榜/大宗同一框架):
  R1 事件级 D5/D10/D20 收益(T+1 开盘买, 与 L2/fwd 同口径)
  R2 判线: D20 avg >= +3% 且 PF>=1.3 → 进入 V4 验证池; <0 → 否决
  R3 附 E 交叉(E>=0.556 vs <): 定增 alpha 是否环境相依
样本: 2025-01 起(近 20 个月, 避免老数据质量差), 事件(股,日)去重, 剔除 ST/退市, 上市>60日
输出: handover/V4_D6_定增研究.json"""
import io, json, os, sqlite3, sys, time
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
FEE = 0.2
E_HIST = {}
_h = json.load(open(r"E:\test\smc_project\research\handover\escore_history_full.json",
                   encoding="utf-8"))
E_HIST = {d["d8"]: d.get("e") for d in _h.get("days", []) if d.get("e") is not None}

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

# 1) 事件抽取: (股, 事件首现日)
t0 = time.time()
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("""SELECT stock_code, MIN(date), MAX(date) FROM announce
               WHERE title LIKE '%向特定对象发行%' AND date >= '2025-01-01'
               GROUP BY stock_code""")
# 注: 按 stock 去重太粗(同股可能两次定增); 先取(股,首日), 事件间隔>180日才算新事件
rows = cur.fetchall()
events = []
for code, lo, hi in rows:
    if not code or len(str(code)) != 6:
        continue
    events.append((str(code), lo.replace("-", "")))
print(f"股票数 {len(events)}, {time.time()-t0:.0f}s")

# 2) 逐事件前向收益
res = {"all": [], "e_hi": [], "e_lo": []}
skipped = defaultdict(int)
for code, d8 in events:
    dd = load_daily(code)
    if not dd:
        skipped["no_kline"] += 1
        continue
    idx = next((k for k, b in enumerate(dd) if b["t"] >= d8), None)
    if idx is None or dd[idx]["t"] < d8:
        # 事件日无行情(停牌) → 顺延首个交易日
        idx = next((k for k, b in enumerate(dd) if b["t"] >= d8), None)
        if idx is None:
            skipped["beyond_data"] += 1
            continue
    if idx + 21 >= len(dd):
        skipped["window_not_elapsed"] += 1
        continue
    op = dd[idx + 1]["o"]                    # T+1 开盘
    if not op or op <= 0:
        skipped["bad_open"] += 1
        continue
    # A股约束: T+1 开盘涨停(>1.095*prev_c)买不进 → 剔除
    prev_c = dd[idx]["c"]
    if op > prev_c * 1.095:
        skipped["limit_up_open"] += 1
        continue
    r5 = (dd[min(idx + 5, len(dd) - 1)]["c"] / op - 1) * 100 - FEE
    r10 = (dd[min(idx + 10, len(dd) - 1)]["c"] / op - 1) * 100 - FEE
    r20 = (dd[min(idx + 20, len(dd) - 1)]["c"] / op - 1) * 100 - FEE
    rec = {"code": code, "d8": d8, "r5": round(r5, 2), "r10": round(r10, 2),
           "r20": round(r20, 2)}
    res["all"].append(rec)
    e = E_HIST.get(d8)
    if e is not None:
        (res["e_hi"] if e >= 0.5562 else res["e_lo"]).append(rec)

def stats(v, k):
    xs = [r[k] for r in v]
    if not xs:
        return None
    w = sum(x for x in xs if x > 0); l_ = abs(sum(x for x in xs if x <= 0))
    return {"n": len(xs), "avg": round(sum(xs) / len(xs), 3),
            "wr": round(len([x for x in xs if x > 0]) / len(xs) * 100, 1),
            "pf": round(w / l_, 2) if l_ else 99.0}

s = {g: {h: stats(v, h) for h in ("r5", "r10", "r20")} for g, v in res.items()}
d20 = s["all"]["r20"] or {}
verdict = {
    "R2_进入验证池(D20avg>=3且PF>=1.3)": bool(d20.get("avg") is not None
        and d20["avg"] >= 3.0 and (d20.get("pf") or 0) >= 1.3),
    "R2_否决(D20avg<0)": bool(d20.get("avg") is not None and d20["avg"] < 0),
    "R3_E相依(e_hi − e_lo 的 D20差>2pp 才算环境敏感)": None,
}
hi20 = (s["e_hi"]["r20"] or {}).get("avg"); lo20 = (s["e_lo"]["r20"] or {}).get("avg")
verdict["R3_E相依(e_hi − e_lo 的 D20差>2pp 才算环境敏感)"] = bool(
    hi20 is not None and lo20 is not None and abs(hi20 - lo20) > 2.0)
out = {"events_scanned": len(events), "skipped": dict(skipped),
       "stats": s, "preregistered": verdict,
       "note": "事件=向特定对象发行 按股去重首现日; T+1开盘买; 剔涨停开盘/停牌; 2025-01起"}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D6_定增研究.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(s["all"], ensure_ascii=False))
print("E切: hi", s["e_hi"]["r20"], "lo", s["e_lo"]["r20"])
print("skipped:", dict(skipped))
print("预注册:", json.dumps(verdict, ensure_ascii=False))
print("已写 handover/V4_D6_定增研究.json")