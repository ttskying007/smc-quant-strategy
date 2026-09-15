# -*- coding: utf-8 -*-
"""r38_combo_gates.py —— R38 组合闸验证: UP-regime × rank 门槛.
在冻结基线 EVENT 腿上, 叠加 C1(上证20MA UP) + rank 门槛(≥1/≥2/≥3/≥4),
比较 avg/PF/WR/n —— 找"质量最优 × 量可接受"的平衡点.
纯研究, 不修改生产. """
import csv, io, json, sys, bisect
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

idx = json.load(open(r"E:\test\smc_project\research\_r38_index_sh000001.json", encoding="utf-8"))
idx.sort(key=lambda b: b["t"])
idates = [b["t"] for b in idx]; iclose = [b["c"] for b in idx]
def is_up(d8):
    i = bisect.bisect_right(idates, d8) - 1
    if i < 20: return True
    ma20 = sum(iclose[i-19:i+1])/20; ma10 = sum(iclose[i-9:i+1])/10
    return iclose[i] > ma20 and ma10 >= ma20

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
def f(x, d=0.0):
    try: return float(x)
    except: return d

def stats(ts):
    if not ts: return None
    pnls = [t["net"] for t in ts]
    wins = [x for x in pnls if x > 0]; losses = [x for x in pnls if x <= 0]
    pf = sum(wins)/abs(sum(losses)) if sum(losses) else 99
    wr = 100*len(wins)/len(pnls)
    return dict(n=len(ts), wr=wr, avg=sum(pnls)/len(pnls), pf=pf, sum=sum(pnls))

print("="*96)
print("组合闸: UP-regime × rank 门槛 (EVENT 腿 n=1640)")
print("="*96)
print(f"{'组合':<24}{'n':>6}{'占比':>7}{'胜率':>8}{'平均%':>9}{'PF':>7}{'PnL合计%':>10}")
combos = [
    ("全量", lambda r: True),
    ("UP only", lambda r: is_up(r.get("entry_date"))),
    ("UP × rank>=2", lambda r: is_up(r.get("entry_date")) and int(r.get("rank") or 0) >= 2),
    ("UP × rank>=3", lambda r: is_up(r.get("entry_date")) and int(r.get("rank") or 0) >= 3),
    ("UP × rank>=4", lambda r: is_up(r.get("entry_date")) and int(r.get("rank") or 0) >= 4),
    ("全量 × rank>=3", lambda r: int(r.get("rank") or 0) >= 3),
    ("全量 × rank>=4", lambda r: int(r.get("rank") or 0) >= 4),
]
for name, pred in combos:
    ts = [{"net": f(r["net_pnl_pct"])} for r in ev if pred(r)]
    s = stats(ts)
    if not s: continue
    print(f"{name:<24}{s['n']:>6}{100*s['n']/len(ev):>6.1f}%{s['wr']:>7.1f}%{s['avg']:>+8.2f}%{s['pf']:>7.2f}{s['sum']:>+10.0f}%")

# 逐年稳定性: UP×rank>=3
print("\nUP×rank>=3 逐年:")
for y in ("2024", "2025", "2026"):
    ts = [{"net": f(r["net_pnl_pct"])} for r in ev
          if str(r.get("entry_date"))[:4] == y and is_up(r.get("entry_date"))
          and int(r.get("rank") or 0) >= 3]
    s = stats(ts)
    if s: print(f"  {y}: n={s['n']} avg={s['avg']:+.2f}% PF={s['pf']:.2f} WR={s['wr']:.1f}%")
