# -*- coding: utf-8 -*-
"""r38_sizing.py —— R38 仓位缩放验证: regime 权重自适应 vs 全有全无.
对冻结基线 EVENT 腿, 按入场日上证 regime 给仓位权重, 模拟组合级指标:
  全量:    w=1 全部
  UP-only: w=1(UP) / w=0(其余)
  缩放:    w=1(UP) / 0.5(MIX) / 0.25(DOWN)
  保守:    w=1(UP) / 0.5(MIX) / 0(DOWN)
比较: avg(PnL加权) / PF(加权) / MDD(加权权益) / 逐年稳定性(尤其2026).
纯研究, 不修改生产. """
import csv, io, json, sys, bisect
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

idx = json.load(open(r"E:\test\smc_project\research\_r38_index_sh000001.json", encoding="utf-8"))
idx.sort(key=lambda b: b["t"])
idates = [b["t"] for b in idx]; iclose = [b["c"] for b in idx]
def regime(d8):
    i = bisect.bisect_right(idates, d8) - 1
    if i < 20: return "MIX"
    ma20 = sum(iclose[i-19:i+1])/20; ma10 = sum(iclose[i-9:i+1])/10
    c = iclose[i]
    if c > ma20 and ma10 >= ma20: return "UP"
    if c < ma20 and ma10 <= ma20: return "DOWN"
    return "MIX"

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
def f(x, d=0.0):
    try: return float(x)
    except: return d

def combo_stats(weighted):
    """weighted: [(pnl, w)] → 组合级指标. 权重=仓位占比. """
    if not weighted: return None
    contrib = [p * w for p, w in weighted]
    wins = [x for x in contrib if x > 0]; losses = [x for x in contrib if x <= 0]
    pf = sum(wins)/abs(sum(losses)) if sum(losses) else 99
    wr = 100*len([x for x in contrib if x > 0])/len(contrib)
    eq = []; cum = 0.0; peak = 0.0; mdd = 0.0
    for x in contrib:
        cum += x; peak = max(peak, cum); mdd = min(mdd, cum-peak)
    return dict(n=len(contrib), wr=wr, avg=sum(contrib)/len(contrib), pf=pf,
                mdd=mdd, sum=sum(contrib))

schemes = {
    "全量(w=1)":  {"UP": 1.0, "MIX": 1.0, "DOWN": 1.0},
    "UP-only":    {"UP": 1.0, "MIX": 0.0, "DOWN": 0.0},
    "缩放(1/0.5/0.25)": {"UP": 1.0, "MIX": 0.5, "DOWN": 0.25},
    "保守(1/0.5/0)":    {"UP": 1.0, "MIX": 0.5, "DOWN": 0.0},
}
print("="*92)
print("仓位缩放模拟 (EVENT n=%d, 组合级指标, w=仓位权重)" % len(ev))
print("="*92)
print(f"{'方案':<18}{'n':>6}{'胜率':>8}{'加权平均%':>10}{'PF':>7}{'MDD%':>9}{'PnL合计%':>10}")
res = {}
for name, wmap in schemes.items():
    weighted = [(f(r["net_pnl_pct"]), wmap[regime(r.get("entry_date"))]) for r in ev]
    s = combo_stats(weighted)
    res[name] = s
    print(f"{name:<18}{s['n']:>6}{s['wr']:>7.1f}%{s['avg']:>+9.2f}%{s['pf']:>7.2f}{s['mdd']:>9.1f}%{s['sum']:>+10.0f}%")

print("\n逐年稳定性(缩放 1/0.5/0.25):")
wmap = schemes["缩放(1/0.5/0.25)"]
for y in ("2023", "2024", "2025", "2026"):
    ys = [r for r in ev if str(r.get("entry_date"))[:4] == y]
    if not ys: continue
    weighted = [(f(r["net_pnl_pct"]), wmap[regime(r.get("entry_date"))]) for r in ys]
    s = combo_stats(weighted)
    if s: print(f"  {y}: n={s['n']} 加权avg={s['avg']:+.2f}% PF={s['pf']:.2f} WR={s['wr']:.1f}% PnL={s['sum']:+.0f}%")

print("\n2026 特异性: regime 天数分布 vs 事件供给")
from collections import Counter
rc = Counter(regime(r.get("entry_date")) for r in ev)
print("  全期 EVENT regime 分布:", dict(rc))
yc = Counter(regime(r.get("entry_date")) for r in ev if str(r.get("entry_date"))[:4] == "2026")
print("  2026 EVENT regime 分布:", dict(yc))
