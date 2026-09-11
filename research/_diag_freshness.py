# -*- coding: utf-8 -*-
"""_diag_freshness.py —— 数据新鲜度诊断: 各缓存目录的末bar日期分布 + selection时间戳"""
import glob, io, json, os, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
dist = Counter()
n = 0
for fp in glob.glob(os.path.join(KT, "*_daily_800.json")):
    try:
        raw = json.load(open(fp, encoding="utf-8"))
        if raw:
            dist[str(raw[-1].get("t"))[:8]] += 1
            n += 1
    except Exception:
        pass
print(f"tencent日线 {n} 文件, 末bar分布(前10):")
for d8, c in dist.most_common(10):
    print(f"  {d8}: {c} ({round(c / n * 100, 1)}%)")
cov = sum(c for d8, c in dist.items() if d8 >= "20260910")
print(f"覆盖率(末bar>=20260910): {cov}/{n} = {round(cov/n*100,1)}%")

# selection_result 时间戳
srp = r"E:\test\smc_project\research\selection_result.json"
if os.path.exists(srp):
    sr = json.load(open(srp, encoding="utf-8"))
    keys = [k for k in sr.keys() if "time" in k.lower() or "date" in k.lower() or "at" in k.lower()]
    print(f"\nselection_result.json: generated_at={sr.get('generated_at')} 其他时间字段: {keys}")
# paper_ledger / escore_history 最后记录
for name, p in (("escore_history", r"E:\test\smc_project\research\handover\escore_history.json"),
               ("paper_ledger", r"E:\test\smc_project\research\handover\setup_engine_paper_ledger.json")):
    if os.path.exists(p):
        j = json.load(open(p, encoding="utf-8"))
        if name == "escore_history":
            ds = j.get("days", [])
            print(f"escore_history: {len(ds)} 日, 最后 {ds[-1]['d8'] if ds else '-'} "
                  f"E={ds[-1].get('e') if ds else '-'} recorded={ds[-1].get('recorded_at') if ds else '-'}")
        else:
            s = j.get("summary", {})
            print(f"paper_ledger: last_run={s.get('last_run')} days={s.get('days_accum')} closed={s.get('closed')}")