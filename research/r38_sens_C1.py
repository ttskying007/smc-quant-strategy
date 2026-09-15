# -*- coding: utf-8 -*-
"""r38_sens_C1.py —— R38 C1 敏感性检验: regime 定义(MA窗口/指数选择)稳健性.
对冻结基线 EVENT 腿逐笔, 用不同 regime 定义分桶, 比较 UP 桶质量:
  MA窗口: 10/20/30
  指数: 000001(上证) vs 000300(沪深300)
判据: UP 桶 avg/PF 是否稳定 > 全量; 若某参数组合失效则 C1 需更严格论证.
纯研究, 不修改生产. """
import csv, io, json, sys, bisect
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

def load_idx(path, tkey="t", ckey="c"):
    d = json.load(open(path, encoding="utf-8"))
    d.sort(key=lambda b: b[tkey])
    return [b[tkey] for b in d], [b[ckey] for b in d]

# 上证指数(已拉) 与 沪深300(ETF缓存, 覆盖2024-04~2026-05; 用于交叉验证后半段)
idx1_d, idx1_c = load_idx(r"E:\test\smc_project\research\_r38_index_sh000001.json")
idx3_d, idx3_c = load_idx(r"E:\test\smc_project\hermes\kline_cache_etf\000300_SH_day.json", tkey="date")

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
def f(x, d=0.0):
    try: return float(x)
    except: return d

def regime(d8, dates, closes, ma_n):
    i = bisect.bisect_right(dates, d8) - 1
    if i < ma_n:
        return None  # 数据不足
    ma = sum(closes[i-ma_n+1:i+1]) / ma_n
    ma_prev = sum(closes[i-ma_n:i]) / ma_n
    c = closes[i]
    if c > ma and ma >= ma_prev:
        return "UP"
    if c < ma and ma <= ma_prev:
        return "DOWN"
    return "MIX"

def stats(ts):
    if not ts: return None
    pnls = [t["net"] for t in ts]
    wins = [x for x in pnls if x > 0]; losses = [x for x in pnls if x <= 0]
    pf = sum(wins)/abs(sum(losses)) if sum(losses) else 99
    wr = 100*len(wins)/len(pnls)
    return dict(n=len(ts), wr=wr, avg=sum(pnls)/len(pnls), pf=pf, sum=sum(pnls))

all_ev = [{"net": f(r["net_pnl_pct"])} for r in ev]
sa = stats(all_ev)
print("="*92)
print("C1 敏感性: 全量 EVENT 基线 n=%d avg=%+.2f%% PF=%.2f" % (sa["n"], sa["avg"], sa["pf"]))
print("="*92)
print(f"{'指数':<10}{'MA':>4}{'UP占比':>8}{'UP_n':>7}{'UP胜率':>8}{'UP平均%':>9}{'UP_PF':>8}{'UP_PnL%':>9}")

for idx_name, dates, closes in (("000001", idx1_d, idx1_c), ("000300", idx3_d, idx3_c)):
    for ma_n in (10, 20, 30):
        up = []
        for r in ev:
            st = regime(r.get("entry_date"), dates, closes, ma_n)
            if st == "UP":
                up.append({"net": f(r["net_pnl_pct"])})
        su = stats(up)
        if not su: continue
        pct = 100*su["n"]/len(ev)
        print(f"{idx_name:<10}{ma_n:>4}{pct:>7.1f}%{su['n']:>7}{su['wr']:>7.1f}%{su['avg']:>+8.2f}%{su['pf']:>8.2f}{su['sum']:>+9.0f}%")

# 000300 只覆盖 2024-04~2026-05 —— 单独标注后半段交叉
print("\n000300 覆盖 2024-04~2026-05(后半段交叉验证):")
post = [r for r in ev if "20240401" <= r.get("entry_date") <= "20260508"]
sp_all = stats([{"net": f(r["net_pnl_pct"])} for r in post])
print(f"  后半段全量 n={sp_all['n']} avg={sp_all['avg']:+.2f}% PF={sp_all['pf']:.2f}")
for ma_n in (20,):
    up2 = [{"net": f(r["net_pnl_pct"])} for r in post
           if regime(r.get("entry_date"), idx3_d, idx3_c, ma_n) == "UP"]
    su2 = stats(up2)
    print(f"  后半段 000300 UP(MA{ma_n}): n={su2['n']} avg={su2['avg']:+.2f}% PF={su2['pf']:.2f} WR={su2['wr']:.1f}%")
