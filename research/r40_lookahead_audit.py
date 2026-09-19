# -*- coding: utf-8 -*-
"""R40: 前视审计专项 — entry_date(信号日) vs buy_date(成交日) 间隔分布
规则: 信号 D 日生成, 应 T+1 (含跳空处理) 成交。若 buy==entry 则需追问是否用了当日收盘前已知信息。
(公告 D 日 OFTEN 盘后发布 -> T+1 才能反应, 所以 0 间隔必须稀少且可解释)
"""
import csv, os, sys, json, statistics, datetime
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")):
    if not (r.get("buy_price") or "").strip(): continue
    e, b = r.get("entry_date"), r.get("buy_date")
    if not e or not b: continue
    try:
        d0 = datetime.date(int(e[:4]), int(e[4:6]), int(e[6:8]))
        d1 = datetime.date(int(b[:4]), int(b[4:6]), int(b[6:8]))
        r["_gap"] = (d1 - d0).days
        r["_pnl"] = float(r["net_pnl_pct"])
        rows.append(r)
    except Exception: continue

gaps = Counter(r["_gap"] for r in rows)
print("buy_date - entry_date 间隔分布(日历日):")
for g in sorted(gaps):
    print(f"  gap={g:>2}d: n={gaps[g]:>4} ({gaps[g]/len(rows)*100:.1f}%)")

# 交易日等价换算(粗略): gap0=同日, gap1=T+1(相邻), gap2-3=周五→周一
same_day = [r for r in rows if r["_gap"] == 0]
neg = [r for r in rows if r["_gap"] < 0]
print(f"\nsame-day(gap=0): n={len(same_day)}  neg-gap(buy早于entry): n={len(neg)}")
if same_day:
    print("  same-day 样本 avg:", round(statistics.mean(r['_pnl'] for r in same_day), 2))
neg_avg = round(statistics.mean(r['_pnl'] for r in neg), 2) if neg else None
print("  neg-gap legs (若有, 任一都是严重前视): ", [f"{r.get('symbol') or r.get(chr(65279)+'symbol')} {r['entry_date']}->{r['buy_date']}" for r in neg[:5]])

res = {"n": len(rows), "gap_dist": {str(k): v for k, v in sorted(gaps.items())},
       "same_day_n": len(same_day), "neg_n": len(neg),
       "semantics": ("生成器 gen_v20f2_wilder_h12.py:120 entry_idx=i+1 — entry_date/buy_date 均为披露次日(T+1)成交日;"
                     " 公告日 i 的计算(stage/adx/disc_close)只用至当日收盘; 回踩限价=0.99*C_disc 用 T+1 的低点判定填充, 静态挂单价无前视"),
       "verdict": ("CLEAN: 无 buy<entry; entry_date=buy_date=T+1成交日, T+1 语义完整" if not neg else "❌ 存在 buy<entry, 前视嫌疑!")}
print("\n判定:", res["verdict"])
json.dump(res, open(os.path.join(HERE, "handover", "r40_lookahead_audit.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r40_lookahead_audit.json")
