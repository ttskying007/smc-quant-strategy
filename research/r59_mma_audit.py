# -*- coding: utf-8 -*-
"""R59: 逐年/逐月/逐笔结构审计 (on combo_v21_trades.csv — 纯审查, 不调参)
审计问题: (a) 年度 regime 迁移是否稳; (b) 月度 structure/regime 是否稳; (c) per-leg
  损失归因与结构列的承接关系(为 E4'' 预注册提供事实). 读 v21 CSV, 不写生产。"""
import csv, io, os, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from collections import Counter, defaultdict
import statistics

ROOT = r"E:\test\smc_project"
rows = list(csv.DictReader(open(os.path.join(ROOT, "research", "combo_v21_trades.csv"), encoding="utf-8-sig")))
ev  = [r for r in rows if r["src"] == "EVENT"]
print(f"EVENT legs: {len(ev)}  |  total v21: {len(rows)}")

def f(x):
    try: return float(x)
    except Exception: return None

def yr(r):  return r["entry_date"][:4]
def mo(r):  return r["entry_date"][:6]

# ---- 年度 ---- (趋势/供给/SL合规分布)
print("\n=== 年度: regime + 结构分布 ===")
for y in sorted(set(yr(r) for r in ev)):
    ys = [r for r in ev if yr(r)==y]; pn=[f(r["net_pnl_pct"]) for r in ys if f(r["net_pnl_pct"]) is not None]
    w=[x for x in pn if x>0]; l=[x for x in pn if x<=0]
    pf = sum(w)/abs(sum(l)) if l else 99
    trends = Counter(r["trend_state"] for r in ys); zones = Counter(r["zone_90d"] for r in ys)
    sl_ok = sum(1 for r in ys if r["sl_below_structure"]=="1")
    print(f"  {y}: n={len(pn)} avg={sum(pn)/len(pn):+.2f}% PF={pf:.2f} WR={len(w)/len(pn)*100:.0f}% "
          f"trend(down/up)={trends.get('down',0)}/{trends.get('up',0)} "
          f"zone(p/d/e)={zones.get('premium',0)}/{zones.get('discount',0)}/{zones.get('equilibrium',0)} "
          f"sl_below_struct={sl_ok}/{len(ys)}={sl_ok/len(ys)*100:.0f}%")

# ---- 月度 (regime + cap binding) ----
print("\n=== 月度: 过去12月 regime(2024-09…2026-09) ===")
months = sorted(set(mo(r) for r in ev if r["entry_date"] >= "202409"))
recent = [m for m in months if m >= "202509"]
show = months[-12:] if len(months)>12 else months
for m in show:
    ms = [r for r in ev if mo(r)==m]; pn=[f(r["net_pnl_pct"]) for r in ms if f(r["net_pnl_pct"]) is not None]
    if not ms: continue
    w=[x for x in pn if x>0]; l=[x for x in pn if x<=0]
    pf = sum(w)/abs(sum(l)) if l else 99
    print(f"  {m}: n={len(pn)} avg={sum(pn)/len(pn):+.2f}% PF={pf:.2f} WR={len(w)/len(pn)*100:.0f}% "
          f"trend={'↓' if Counter(r['trend_state'] for r in ms).get('down',0)>len(ms)/2 else '↑'} "
          f"zone={'D' if Counter(r['zone_90d'] for r in ms).get('discount',0)>len(ms)/2 else 'P'} "
          f"cap{'*' if len(ms)>=500 else ''}")
capped = [m for m in show if Counter(mo(r) for r in ev).get(m,0) >= 500]
print(f"  month-cap(500) binding: {capped if capped else '无 — 未触发阈值'}")

# ---- 逐笔: 损失腿结构承接 ---- (为R13/E4''预注册)
print("\n=== 逐笔: 损亏腿的结构承接(负 pnl n=...) ===")
loss = [r for r in ev if (f(r["net_pnl_pct"]) or 0) < 0]
gain = [r for r in ev if (f(r["net_pnl_pct"]) or 0) > 0]
print(f"  EVENT 盈利 {len(gain)} 浮亏 {len(loss)}")
print("  亏损腿结构分布(负 vs 全):\n    sl_below_struct   trend     zone       supply_avg")
for label, pool in ("亏", loss), ("全", ev):
    sb = sum(1 for r in pool if r["sl_below_structure"]=="1")
    ts = Counter(r["trend_state"] for r in pool)
    zs = Counter(r["zone_90d"] for r in pool)
    sl = [f(r["supply_layers"]) for r in pool if f(r["supply_layers"]) is not None]
    print(f"    {label:<3} {sb:>4}/{len(pool)}  down/up={ts.get('down',0)}/{ts.get('up',0)} "
          f"D/P/E={zs.get('discount',0)}/{zs.get('premium',0)}/{zs.get('equilibrium',0)} "
          f"avg_layers={sum(sl)/len(sl):.2f}")
# sample 5 worst
worst = sorted(loss, key=lambda r: f(r["net_pnl_pct"]))[:5]
print("\n  5 笔worst (pnl / trend / last_event / supply / zone / entry)")
for r in worst:
    print(f"    {f(r['net_pnl_pct']):+.2f}%  {r['trend_state']:4s} {r['last_event_kind']:<6s} "
          f"sup={r['supply_layers']} {r['zone_90d']:10s} {r['entry_date']} {r['symbol']}")

# ---- last_event_kind 盈利性对照 ----
print("\n=== last_event_kind 盈利性(盈利率 WR / 均pnL) ===")
ec = defaultdict(list)
for r in ev:
    ec[r["last_event_kind"] or "-"].append(f(r["net_pnl_pct"]))
for k in sorted(ec, key=lambda x: sum(ec[x])/len(ec[x]), reverse=True):
    v=ec[k]; pn=[x for x in v if x is not None]
    if not pn: continue
    print(f"  {k:<6s}: n={len(pn)} avg={sum(pn)/len(pn):+.2f}% WR={len([x for x in pn if x>0])/len(pn)*100:.0f}%")
