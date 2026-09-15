# -*- coding: utf-8 -*-
"""r38_event_newtype_test.py —— R38 新事件类型前瞻收益测试(是否值得新增分类规则).

R38i 发现: 股权激励/业绩预告/中标合同/定增 全部 pol=0(无分类规则),
但供给充足(2797/7282/2151/1083)。本脚本用缓存 K 线做**低成本**前瞻收益
测试(不跑完整 simulate), 判断哪类值得投入做新规则:

  业绩预增(正向)  vs 业绩预减(负向)  —— 分开测, 避免正负抵消
  股权激励(授予)  vs 员工持股
  中标合同 / 重大重组

方法: 公告日 T+1 开盘买入, 持有 10/20 日收盘卖出, 记录 avg/WR/PF。
判据: 若某类 avg>+2% 且 WR>55% 且逐年稳定 → 晋级为下一轮正式候选。
纯研究, 不修改生产。
"""
import io, json, os, re, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
HERE = r"E:\test\smc_project\research"
code2file = {f.split("_")[0]: f for f in os.listdir(KT) if f.endswith("_daily_800.json")}
_bars = {}
def bars_of(code):
    if code not in _bars:
        fn = code2file.get(code)
        if not fn:
            _bars[code] = []
            return _bars[code]
        raw = json.load(open(os.path.join(KT, fn), encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("c") and r.get("h") and r.get("l"):
                bs.append({"t": t, "o": float(r["o"]), "c": float(r["c"]),
                           "h": float(r["h"]), "l": float(r["l"])})
        bs.sort(key=lambda b: b["t"])
        _bars[code] = bs
    return _bars[code]

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

# 分类: (名称, WHERE 片段)
GROUPS = [
    ("业绩预增", "title LIKE '%业绩预增%' OR title LIKE '%业绩预告%预增%'"),
    ("业绩预减", "title LIKE '%业绩预减%' OR title LIKE '%业绩预告%预减%' OR title LIKE '%业绩预亏%'"),
    ("股权激励授予", "title LIKE '%股权激励%' AND (title LIKE '%授予%' OR title LIKE '%首次授予%')"),
    ("员工持股计划", "title LIKE '%员工持股计划%' AND (title LIKE '%草案%' OR title LIKE '%完成%')"),
    ("中标合同", "title LIKE '%中标%' OR title LIKE '%签订合同%'"),
    ("重大重组", "title LIKE '%重大资产重组%' AND title LIKE '%预案%'"),
]

def stats(rets):
    if not rets: return None
    w = [x for x in rets if x > 0]; l = [x for x in rets if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(rets), "avg": sum(rets)/len(rets), "wr": 100*len(w)/len(rets), "pf": pf}

print("="*96)
print("新事件类型前瞻收益测试(T+1开盘买入, 持有10/20日)")
print("事件腿参照: n=1640 avg+3.51% PF3.20 (含SL/TP结构, 非纯持有)")
print("="*96)
print(f"{'类型':<14}{'公告数':>7}{'可回测':>7}{'10日均值':>9}{'10日WR':>8}{'10日PF':>8}{'20日均值':>10}{'20日PF':>8}")
results = {}
for name, where in GROUPS:
    cur.execute(f"SELECT date, stock_code, title FROM announce WHERE date >= '2023-09-01' AND ({where})")
    rows = cur.fetchall()
    r10, r20 = [], []
    for d8, code, title in rows:
        code6 = str(code)[:6]
        bs = bars_of(code6)
        if not bs: continue
        d = str(d8).replace("-", "")[:8]
        idx = next((i for i, b in enumerate(bs) if b["t"] == d), None)
        if idx is None or idx + 21 >= len(bs): continue
        ep = bs[idx + 1]["o"]
        if ep <= 0: continue
        r10.append((bs[idx + 11]["c"]/ep - 1)*100)
        r20.append((bs[idx + 21]["c"]/ep - 1)*100)
    s10, s20 = stats(r10), stats(r20)
    results[name] = {"s10": s10, "s20": s20}
    if s10 and s20:
        print(f"{name:<14}{len(rows):>7}{s10['n']:>7}{s10['avg']:>+8.2f}%{s10['wr']:>7.1f}%{s10['pf']:>8.2f}{s20['avg']:>+9.2f}%{s20['pf']:>8.2f}")
    else:
        print(f"{name:<14}{len(rows):>7}   无有效样本")

print("\n" + "="*96)
print("判定:")
for name, r in results.items():
    s = r["s20"] or r["s10"]
    if not s: continue
    tag = "✅ 候选" if (s["avg"] > 2.0 and s["wr"] > 55) else ("⚠ 中性" if s["avg"] > 0 else "❌ 负期望")
    print(f"  {name:<14} 20日 avg={s['avg']:+.2f}% WR={s['wr']:.1f}% PF={s['pf']:.2f}  {tag}")
print("\n注: 此为纯持有测试(无SL/TP), 仅用于筛选方向; 晋级项需在冻结基线口径下重测+OOS。")
json.dump(results, open(os.path.join(HERE, "r38_event_newtype_test.json"), "w", encoding="utf-8"), ensure_ascii=False)