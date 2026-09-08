# -*- coding: utf-8 -*-
"""纯净集口径精确化: 三分类(真事件/仅污染/无匹配) + 窗口敏感性。
上次两脚本口径差: 1434(拒绝=任一污染) vs 1158(保留=至少一真事件)。
差集 = 窗口内"无任何公告"的交易(披露可能距entry 4-7天: PENDING过期+周末)。
本脚本: 窗口 0-7 天三分类 + 0-3/0-5/0-7 敏感性 + 各类 IS/OOS。"""
import csv, io, json, sqlite3, sys
from collections import defaultdict
from datetime import date as _d
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import core.events as EV

DB = r"E:\test\smc_project\announce\smc_announce.db"
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
OOS = "20250701"

rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net"] = float(r["net_pnl_pct"])

conn = sqlite3.connect(DB)
cur = conn.cursor()
ann_by_code = defaultdict(list)
cur.execute("SELECT stock_code, date, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for code, d, t in cur.fetchall():
    ann_by_code[str(code)].append((str(d)[:10].replace("-", ""), str(t)))
conn.close()
for c in ann_by_code:
    ann_by_code[c].sort(key=lambda x: x[0], reverse=True)

def classify_trade(r, window):
    e = _d(int(r["entry_date"][:4]), int(r["entry_date"][4:6]), int(r["entry_date"][6:8]))
    code = r["symbol"].split(".")[0]
    has_real, has_inert_only = False, False
    # FIX: 遍历全部公告(不截断[:24]——多公告股票2026年新公告会占满前24条, 2023年真公告漏检)
    for d8, t in ann_by_code.get(code, []):
        dd = _d(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))
        gap = (e - dd).days
        if gap > window:
            break  # 降序列表: 更早的公告不再看
        if 0 <= gap <= window:
            if EV.classify_title(t)[0]:
                has_real = True
            else:
                has_inert_only = True
    if has_real:
        return "CLEAN"
    if has_inert_only:
        return "POLLUTED"
    return "NO_MATCH"

def _stats(ts, oos=False):
    sel = [t for t in ts if (t["entry_date"] >= OOS) == oos]
    if not sel:
        return {"n": 0}
    pn = [t["net"] for t in sel]
    w = [x for x in pn if x > 0]
    return {"n": len(pn), "avg": round(sum(pn)/len(pn), 3), "wr": round(len(w)/len(pn), 3),
            "pf": round(sum(w)/abs(sum(x for x in pn if x <= 0)), 2) if any(x <= 0 for x in pn) and sum(x for x in pn if x <= 0) != 0 else 99}

out = {"windows": {}}
for win in (3, 5, 7):
    cats = {"CLEAN": [], "POLLUTED": [], "NO_MATCH": []}
    for r in rows:
        cats[classify_trade(r, win)].append(r)
    res = {k: {"n": len(v), "all": _stats(v), "OOS": _stats(v, True)} for k, v in cats.items()}
    out["windows"][win] = res
    print(f"\n== 窗口 {win} 天 ==")
    for k, v in res.items():
        print(f"  {k:10s}: n={v['n']:4d} all={v['all']} OOS={v['OOS']}")

# 推荐口径: 7天窗口(覆盖PENDING 3交易日+周末), CLEAN=至少一条真事件公告
rec = out["windows"][7]
print("\n== 推荐纯净口径(7天窗口) ==")
print(f"  CLEAN: {rec['CLEAN']['n']} ({rec['CLEAN']['n']/len(rows):.1%}) OOS={rec['CLEAN']['OOS']}")
print(f"  POLLUTED: {rec['POLLUTED']['n']} OOS={rec['POLLUTED']['OOS']}")
print(f"  NO_MATCH: {rec['NO_MATCH']['n']} OOS={rec['NO_MATCH']['OOS']} (披露距entry>7天或DB缺)")

json.dump(out, open(r"E:\test\smc_project\research\handover\纯净集口径精确化.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("\n已写 handover/纯净集口径精确化.json")