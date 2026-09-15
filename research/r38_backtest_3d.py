# -*- coding: utf-8 -*-
"""r38_backtest_3d.py —— R38 全量回测三维复盘(逐年/逐月/逐笔).
输入: combo_v20f_trades.csv(基线, n=1640 EVENT + CONT capped 1974).
产出: ①逐年矩阵 ②逐月热区 ③RR/盈亏分布 ④亏损簇(连续亏损/大亏单)
     ⑤触发出场分解 ⑥选股稀疏度(月笔数/空窗). 不修改生产。"""
import csv, io, sys
from collections import defaultdict, Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
print(f"EVENT 腿笔数: {len(ev)}  全量(含CONT): {len(rows)}\n")

def f(x, d=0.0):
    try: return float(x)
    except: return d

# ==== ① 逐年矩阵 ====
print("="*92)
print("① 逐年矩阵 (EVENT 腿)")
print("="*92)
print(f"{'年份':<6}{'n':>6}{'胜率':>8}{'平均%':>9}{'中位%':>8}{'PF':>7}{'期望R':>8}{'盈亏比':>8}{'maxDD%':>8}{'maxWin':>8}{'maxLoss':>8}")
for y in sorted({r['entry_date'][:4] for r in ev}):
    ys = [r for r in ev if r['entry_date'][:4] == y]
    pnls = [f(r['net_pnl_pct']) for r in ys]
    rr = [f(r['rr_exit']) for r in ys]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    pf = sum(wins)/abs(sum(losses)) if sum(losses) else 99
    # 最大回撤(逐笔权益)
    eq = []; cum = 0.0; peak = 0.0; mdd = 0.0
    for x in pnls:
        cum += x; peak = max(peak, cum); mdd = min(mdd, cum-peak)
    wr = 100*len(wins)/len(ys)
    avg_r = sum(rr)/len(rr) if rr else 0
    pl = (sum(wins)/len(wins))/(abs(sum(losses))/len(losses)) if losses and wins else 0
    print(f"{y:<6}{len(ys):>6}{wr:>7.1f}%{sum(pnls)/len(pnls):>+8.2f}%{sorted(pnls)[len(pnls)//2]:>+8.2f}%{pf:>7.2f}{avg_r:>8.2f}{pl:>8.2f}{mdd:>8.2f}%{max(pnls):>+8.2f}%{min(pnls):>+8.2f}%")

# ==== ② 逐月热区 ====
print("\n" + "="*92)
print("② 逐月笔数 / 平均% / PF (2023-2026)")
print("="*92)
by_m = defaultdict(list)
for r in ev: by_m[r['entry_date'][:6]].append(f(r['net_pnl_pct']))
months = sorted(by_m)
# 按月序(1-12)聚合跨年, 找季节性
season = defaultdict(list)
for m, ps in by_m.items(): season[int(m[4:6])].extend(ps)
print("月序季节效应(2023-2026聚合):")
print(f"{'月':>4}{'n':>6}{'平均%':>9}{'PF':>7}{'胜率':>8}")
for mm in range(1,13):
    ps = season.get(mm, [])
    if not ps: continue
    w = [x for x in ps if x>0]; l = [x for x in ps if x<=0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    print(f"{mm:>4}{len(ps):>6}{sum(ps)/len(ps):>+8.2f}%{pf:>7.2f}{100*len(w)/len(ps):>7.1f}%")

# ==== ③ RR / 盈亏分布 ====
print("\n" + "="*92)
print("③ RR(exit-R)分布 / 盈亏分布 (EVENT 腿)")
print("="*92)
rr = [f(r['rr_exit']) for r in ev]
rrb = defaultdict(int)
for x in rr:
    if x <= -1: rrb["<=-1R"] += 1
    elif x < 0: rrb["-1~0"] += 1
    elif x == 0: rrb["0"] += 1
    elif x < 1: rrb["0~1"] += 1
    elif x < 2: rrb["1~2"] += 1
    elif x < 3: rrb["2~3"] += 1
    else: rrb[">=3"] += 1
print("RR 分布:  " + "  ".join(f"{k}:{v}({100*v/len(rr):.1f}%)" for k,v in sorted(rrb.items())))
# 期望是否被 1~2 笔大赢主导
pnls = sorted((f(r['net_pnl_pct']) for r in ev), reverse=True)
top = sum(pnls[:20]); total = sum(pnls)
print(f"Top20 盈利占比: {100*top/total:.1f}% (若>50% = 收益集中少数大赢)")

# ==== ④ 亏损簇 / 连续亏损 ====
print("\n" + "="*92)
print("④ 亏损簇(连续亏损跑) / 大亏单明细")
print("="*92)
seq = [(r['entry_date'], f(r['net_pnl_pct'])) for r in sorted(ev, key=lambda x:x['entry_date'])]
streak = 0; best_streak = 0; cur_start = ""; runs = []
for d, p in seq:
    if p <= 0:
        if streak == 0: cur_start = d
        streak += 1
        if streak > best_streak: best_streak = streak
    else:
        if streak >= 3: runs.append((cur_start, streak))
        streak = 0
if streak >= 3: runs.append((cur_start, streak))
print(f"最长连续亏损: {best_streak} 笔")
print(f"连续>=3笔亏损跑: {len(runs)} 段")
bigloss = sorted([r for r in ev if f(r['net_pnl_pct']) <= -5], key=lambda x:f(x['net_pnl_pct']))
print(f"亏损>=5%的单: {len(bigloss)} 笔")
for r in bigloss[:8]:
    print(f"  {r['symbol']} {r['entry_date']} {r['reason']:<14} net={f(r['net_pnl_pct']):+.1f}% hold={r['hold_bars']} mae={f(r['mae_pct']):+.1f}%")

# ==== ⑤ 触发出场分解 ====
print("\n" + "="*92)
print("⑤ 出场触发分解 (EVENT 腿)")
print("="*92)
byr = defaultdict(list)
for r in ev: byr[r.get('reason','')].append(f(r['net_pnl_pct']))
for k, ps in sorted(byr.items(), key=lambda kv:-len(kv[1])):
    w = [x for x in ps if x>0]; l=[x for x in ps if x<=0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    print(f"  {k:<18} n={len(ps):>5} 平均{sum(ps)/len(ps):>+6.2f}% 胜率{100*len(w)/len(ps):>5.1f}% PF={pf:>5.2f}")

# ==== ⑥ 选股稀疏度 ====
print("\n" + "="*92)
print("⑥ 选股稀疏度(月笔数 / 空窗)")
print("="*92)
mcounts = sorted(((m, len(v)) for m,v in by_m.items()))
print(f"月笔数:  " + " ".join(f"{m[-2:]}:{c}" for m,c in mcounts))
low = [m for m,c in mcounts if c < 10]
print(f"月笔数<10的月份: {len(low)} 个 {low if low else ''}")
# 相邻两信号间隔(笔间稀疏度)
dates = sorted(r['entry_date'] for r in ev)
gaps = []
for a,b in zip(dates, dates[1:]):
    import datetime as dt
    da = dt.date(int(a[:4]),int(a[4:6]),int(a[6:8])); db = dt.date(int(b[:4]),int(b[4:6]),int(b[6:8]))
    gaps.append((db-da).days)
import statistics
print(f"信号间间隔(交易日近似): 中位{statistics.median(gaps)}天 平均{statistics.mean(gaps):.1f}天 最大{max(gaps)}天")
print(f"间隔>=30天(信号枯竭)的次数: {sum(1 for g in gaps if g>=30)}")