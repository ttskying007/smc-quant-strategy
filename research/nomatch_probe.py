# -*- coding: utf-8 -*-
"""NO_MATCH 类(155笔)成因排查: DB缺公告 or 日期漂移 or 覆盖缺口。
方法: 对 NO_MATCH 交易查 ①该股在DB的全部公告(任意窗口) ②entry前后±10天公告分布
③样本具体案例(代码/日期/最近公告) → 判定成因。"""
import csv, io, json, sqlite3, sys
from collections import defaultdict, Counter
from datetime import date as _d
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import core.events as EV

DB = r"E:\test\smc_project\announce\smc_announce.db"
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"

rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]

conn = sqlite3.connect(DB)
cur = conn.cursor()
ann_by_code = defaultdict(list)
cur.execute("SELECT stock_code, date, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for code, d, t in cur.fetchall():
    ann_by_code[str(code)].append((str(d)[:10].replace("-", ""), str(t)))
conn.close()
for c in ann_by_code:
    ann_by_code[c].sort(key=lambda x: x[0], reverse=True)

no_match, causes = [], Counter()
samples = []
for r in rows:
    e = _d(int(r["entry_date"][:4]), int(r["entry_date"][4:6]), int(r["entry_date"][6:8]))
    code = r["symbol"].split(".")[0]
    has_real, has_inert = False, False
    for d8, t in ann_by_code.get(code, [])[:24]:
        dd = _d(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))
        gap = (e - dd).days
        if gap > 7:
            break
        if 0 <= gap <= 7:
            if EV.classify_title(t)[0]:
                has_real = True
            else:
                has_inert = True
    if has_real or has_inert:
        continue
    no_match.append(r)
    # 成因: 该股是否有任何公告(更早日期) / 完全无公告
    all_ann = ann_by_code.get(code, [])
    any_positive = any(EV.classify_title(t)[0] for _, t in all_ann)
    if not all_ann:
        causes["DB无该股任何回购/增持公告"] += 1
    elif any_positive:
        # 有真公告但不在窗口 → 日期漂移/窗口外
        near = min(abs((e - _d(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))).days) for d8, _ in all_ann)
        causes[f"真公告在窗口外(最近{near}天)"] += 1
        if len(samples) < 8:
            samples.append((code, r["entry_date"], f"最近公告距{near}天"))
    else:
        causes["该股公告全被新语义拒(如B股/可转债)"] += 1

print(f"NO_MATCH: {len(no_match)} 笔")
print("成因分布:")
for c, n in causes.most_common():
    print(f"  {c}: {n}")
print("\n样例:")
for s in samples:
    print(f"  {s}")
# 年份分布: NO_MATCH是否集中在早期(DB覆盖起点前后)?
yr = Counter(r["entry_date"][:4] for r in no_match)
print("\n年份分布:", dict(sorted(yr.items())))
all_yr = Counter(r["entry_date"][:4] for r in rows)
print("全样本年份:", dict(sorted(all_yr.items())))