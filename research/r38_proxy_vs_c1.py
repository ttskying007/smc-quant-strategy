# -*- coding: utf-8 -*-
"""r38_proxy_vs_c1.py —— R38 关键对比: 生产 _market_proxy regime 机制 vs C1 指数过滤.
生产 paper_sim 现用 _market_proxy(200只采样20日平均涨跌, 决策日) → _risk_coef
(强市降仓) × _regime_coef(弱市加仓≤2x, 逆向策略弱市信号好)。
我的 C1 用上证20MA → UP才交易(强市才买)。两者方向相反。
验证: 在冻结基线 EVENT 腿上, 按 proxy 分桶(弱/中/强市), 看哪个桶质量高,
判断生产机制与 C1 谁符合数据。纯研究, 不修改生产。"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps  # 复用 _market_proxy(只读, 决策日口径)

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
def f(x, d=0.0):
    try: return float(x)
    except: return d

buckets = defaultdict(list)
n_none = 0
for r in ev:
    code = r["symbol"].split(".")[0]
    d8 = r.get("entry_date") or r.get("buy_date")
    pr = ps._market_proxy(code, d8)
    if pr is None:
        n_none += 1
        continue
    if pr < -0.01: b = "弱市(proxy<-1%)"
    elif pr > 0.02: b = "强市(proxy>2%)"
    else: b = "中性"
    buckets[b].append({"net": f(r["net_pnl_pct"])})

def st(ts):
    if not ts: return None
    pnls = [t["net"] for t in ts]
    w = [x for x in pnls if x>0]; l = [x for x in pnls if x<=0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return dict(n=len(ts), avg=sum(pnls)/len(pnls), wr=100*len(w)/len(pnls), pf=pf)

print("="*80)
print("生产 _market_proxy 分桶 vs C1(上证20MA UP) —— 方向冲突验证")
print("="*80)
print(f"{'桶':<22}{'n':>6}{'胜率':>8}{'平均%':>9}{'PF':>7}")
for k in ("弱市(proxy<-1%)", "中性", "强市(proxy>2%)"):
    s = st(buckets.get(k, []))
    if s: print(f"{k:<22}{s['n']:>6}{s['wr']:>7.1f}%{s['avg']:>+8.2f}%{s['pf']:>7.2f}")
print(f"proxy 缺失: {n_none} 笔")
