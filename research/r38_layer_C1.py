# -*- coding: utf-8 -*-
"""r38_layer_C1.py —— 假设 C1 验证: 指数 regime 过滤.
对冻结基线 EVENT 腿, 按入场日上证指数(000001)状态分桶:
  UP   : 指数 20MA 上行且收盘 > 20MA
  DOWN : 指数 20MA 下行且收盘 < 20MA
  MIX  : 其余(20MA 走平/缠绕)
对比三桶 avg/PF/WR/PnL —— 若 DOWN 桶显著差(4-6月/2023差的主因), 则 regime
过滤对症. 纯研究, 不修改生产. 指数: 腾讯源 sh000001(20211008~20260915 已拉)."""
import csv, io, json, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

idx = json.load(open(r"E:\test\smc_project\research\_r38_index_sh000001.json", encoding="utf-8"))
idx.sort(key=lambda b: b["t"])
idates = [b["t"] for b in idx]
iclose = [b["c"] for b in idx]
# 指数 20MA 与 20日收益率
def idx_state(d8):
    """入场日指数状态: UP/DOWN/MIX. 取 <= d8 的最近指数bar. """
    import bisect
    i = bisect.bisect_right(idates, d8) - 1
    if i < 20:
        return "MIX", 0.0
    ma20 = sum(iclose[i-19:i+1]) / 20
    ma10 = sum(iclose[i-9:i+1]) / 10
    c = iclose[i]
    ret20 = c / iclose[i-20] - 1
    if c > ma20 and ma10 >= ma20:
        return "UP", ret20
    if c < ma20 and ma10 <= ma20:
        return "DOWN", ret20
    return "MIX", ret20

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
def f(x, d=0.0):
    try: return float(x)
    except: return d

buckets = defaultdict(list)
for r in ev:
    d8 = r.get("entry_date") or r.get("buy_date")
    st, ret20 = idx_state(d8)
    buckets[st].append({"net": f(r["net_pnl_pct"]), "ret20": ret20, "d": d8,
                        "rr": f(r["rr_exit"], None), "sym": r["symbol"], "reason": r.get("reason","")})

def stats(ts):
    if not ts: return None
    pnls = [t["net"] for t in ts]
    wins = [x for x in pnls if x > 0]; losses = [x for x in pnls if x <= 0]
    pf = sum(wins)/abs(sum(losses)) if sum(losses) else 99
    wr = 100*len(wins)/len(pnls)
    rrs = [t["rr"] for t in ts if t.get("rr") is not None]
    return dict(n=len(ts), wr=wr, avg=sum(pnls)/len(pnls), med=sorted(pnls)[len(pnls)//2],
                pf=pf, sum=sum(pnls), avg_r=sum(rrs)/len(rrs) if rrs else 0)

print("="*92)
print("假设 C1: 上证指数 regime 分桶 (EVENT n=%d)" % len(ev))
print("="*92)
print(f"{'桶':<6}{'n':>6}{'占比':>7}{'胜率':>8}{'平均%':>9}{'中位%':>8}{'PF':>7}{'期望R':>8}{'PnL合计%':>10}")
for k in ("UP", "MIX", "DOWN"):
    s = stats(buckets.get(k, []))
    if not s: continue
    print(f"{k:<6}{s['n']:>6}{100*s['n']/len(ev):>6.1f}%{s['wr']:>7.1f}%{s['avg']:>+8.2f}%{s['med']:>+8.2f}%{s['pf']:>7.2f}{s['avg_r']:>8.2f}{s['sum']:>+10.2f}%")

# 假设: 过滤 DOWN(或 DOWN+MIX) 的效果
su = stats(buckets["UP"]); sd = stats(buckets["DOWN"]); sm = stats(buckets["MIX"])
_all = [{"net": f(r["net_pnl_pct"]), "rr": f(r["rr_exit"], None)} for r in ev]
all_s = stats(_all)
print("\n对照:")
print(f"  全量:      n={all_s['n']} avg={all_s['avg']:+.2f}% PF={all_s['pf']:.2f} PnL={all_s['sum']:+.0f}%")
print(f"  仅 UP:     n={su['n']} avg={su['avg']:+.2f}% PF={su['pf']:.2f} PnL={su['sum']:+.0f}%")
print(f"  仅 DOWN:   n={sd['n']} avg={sd['avg']:+.2f}% PF={sd['pf']:.2f} PnL={sd['sum']:+.0f}%")
print(f"  UP+DOWN:   n={su['n']+sd['n']} avg={(su['sum']+sd['sum'])/(su['n']+sd['n']):+.2f}%")

# 4-6月是否 = DOWN regime?
print("\n4/5/6月 与 regime 交叉:")
for mm in ("04", "05", "06"):
    ms = [t for t in ev if str(t.get("entry_date"))[4:6] == mm]
    if not ms: continue
    sts = defaultdict(int)
    for t in ms:
        sts[idx_state(t.get("entry_date"))[0]] += 1
    print(f"  {mm}月: n={len(ms)} regime占比 {dict(sts)} avg={sum(f(t['net_pnl_pct']) for t in ms)/len(ms):+.2f}%")

# 46连亏在哪个 regime?
print("\n最长连亏段 regime 构成 (连续<=0 跑):")
seq = [(r.get("entry_date"), f(r["net_pnl_pct"]), idx_state(r.get("entry_date"))[0])
       for r in sorted(ev, key=lambda x: x.get("entry_date"))]
streak = 0; best = 0; best_regimes = {}
cur = {}
for d, p, st in seq:
    if p <= 0:
        streak += 1
        cur[st] = cur.get(st, 0) + 1
        if streak > best:
            best = streak; best_regimes = dict(cur)
    else:
        streak = 0; cur = {}
print(f"  最长连亏 {best} 笔, 期间 regime 分布: {best_regimes}")
