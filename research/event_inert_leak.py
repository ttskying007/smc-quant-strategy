# -*- coding: utf-8 -*-
"""P2 事件标注集发现: 注销/激励类标题泄漏量化 + 分类器修复 A/B
发现: "回购注销限制性股票/减资/激励/期权/员工持股"类公告(股本管理,非市场回购)
被 classify_title 判为 EVENT 进入候选池 —— 语义污染。
本脚本: ① 量化泄漏(候选+交易) ② 修复(注销类触发硬否) ③ A/B 回测(全样本+OOS)
"""
import csv, io, json, re, sqlite3, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import core.events as EV

DB = r"E:\test\smc_project\announce\smc_announce.db"
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
OOS = "20250701"
# 股本管理类语义标记(非市场回购/增持): 注销/减资/限制性股票/激励/期权/员工持股/质押/解除质押
INERT_MARKS = ("注销", "减资", "限制性股票", "激励", "期权", "员工持股", "质押")

def is_inert_title(t):
    s = str(t or "")
    return any(m in s for m in INERT_MARKS)

# ① 泄漏量化: 全DB中 EVENT 判定但属注销/激励类
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT stock_code, date, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
leak = []
total_ev = 0
for code, d, title in cur.fetchall():
    is_ev, kind, pol, amt, pct = EV.classify_title(title)
    if is_ev:
        total_ev += 1
        if is_inert_title(title):
            leak.append((code, str(d)[:10].replace("-", ""), title))
conn.close()
print(f"① EVENT 判定标题总数: {total_ev}, 其中注销/激励类(语义污染): {len(leak)} ({len(leak)/max(total_ev,1):.1%})")

# ② 交易污染: 匹配 combo_v20f_trades(信号日=披露日, entry=次日)
rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net"] = float(r["net_pnl_pct"])
# 泄漏集按 (code, date) 索引
leak_keys = {(c, d) for c, d, _ in leak}
polluted = []
clean = []
for r in rows:
    # 交易 signal_date = entry_date 前一交易日附近; 用逐笔的 buy_date=entry 匹配披露日(前1天)
    key_found = False
    # 披露日 = entry 前最近公告日: 直接查 (code, entry_date-3..entry_date)
    for dd in (r["entry_date"],):
        # 近似: 泄漏日与entry差1-2天
        try:
            from datetime import date as _d, timedelta as _td
            e = _d(int(dd[:4]), int(dd[4:6]), int(dd[6:8]))
        except Exception:
            continue
        for off in range(0, 4):
            k = (r["symbol"].split(".")[0], (e - _td(days=off)).strftime("%Y-%m-%d"))
            if k in leak_keys:
                key_found = True
                break
        if key_found:
            break
    (polluted if key_found else clean).append(r)
print(f"② 事件腿交易: {len(rows)}, 匹配到注销/激励类披露: {len(polluted)} ({len(polluted)/len(rows):.1%})")

def _stats(ts, oos=False):
    sel = [t for t in ts if (t["entry_date"] >= OOS) == oos]
    if not sel:
        return {"n": 0}
    pn = [t["net"] for t in sel]
    w = [x for x in pn if x > 0]
    return {"n": len(pn), "avg": round(sum(pn)/len(pn), 3), "wr": round(len(w)/len(pn), 3),
            "pf": round(sum(w)/abs(sum(x for x in pn if x <= 0)), 2) if any(x <= 0 for x in pn) and sum(x for x in pn if x <= 0) != 0 else 99}

print("\n③ A/B: 保留污染 vs 剔除污染")
ab = {"baseline_all": _stats(rows), "baseline_oos": _stats(rows, True),
      "clean_all": _stats(clean), "clean_oos": _stats(clean, True),
      "polluted_all": _stats(polluted), "polluted_oos": _stats(polluted, True)}
for k, v in ab.items():
    print(f"  {k:14s}: {v}")

out = {"leak_titles": len(leak), "total_event_titles": total_ev,
       "leak_ratio": round(len(leak)/max(total_ev, 1), 4),
       "trades_total": len(rows), "trades_polluted": len(polluted),
       "polluted_ratio": round(len(polluted)/max(len(rows), 1), 4),
       "ab": ab,
       "sample_leak_titles": [t for _, _, t in leak[:8]]}
with open(r"E:\test\smc_project\research\handover\事件分类注销泄漏量化.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
print("\n已写 handover/事件分类注销泄漏量化.json")