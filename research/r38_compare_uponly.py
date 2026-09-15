# -*- coding: utf-8 -*-
"""r38_compare_uponly.py —— R38 C1 验证: UP-only vs 全量 完整回测对比.
输入: combo_v20f_trades.csv(冻结基线) vs r38_combo_uponly_trades.csv(研究分叉).
产出: 逐年/逐月/RR分布/回撤对比 —— 若 UP-only 在 avg/PF/回撤/4-6月 全面改善
则 C1 晋级正式改进候选(仍需审计流程). 纯研究. """
import csv, io, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

def load(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))
def f(x, d=0.0):
    try: return float(x)
    except: return d

base = load(r"E:\test\smc_project\research\combo_v20f_trades.csv")
up = load(r"E:\test\smc_project\research\r38_combo_uponly_trades.csv")
print(f"全量: {len(base)} 笔 (EVENT {sum(1 for r in base if r['src']=='EVENT')} + CONT {sum(1 for r in base if r['src']=='CONT')})")
print(f"UP-only: {len(up)} 笔 (EVENT {sum(1 for r in up if r['src']=='EVENT')} + CONT {sum(1 for r in up if r['src']=='CONT')})")
print(f"过滤率: {100*(1-len(up)/len(base)):.1f}%\n")

def mat(rows, tag):
    pnls = [f(r["net_pnl_pct"]) for r in rows]
    wins = [x for x in pnls if x > 0]; losses = [x for x in pnls if x <= 0]
    pf = sum(wins)/abs(sum(losses)) if sum(losses) else 99
    wr = 100*len(wins)/len(pnls)
    eq = []; cum = 0.0; peak = 0.0; mdd = 0.0
    for x in pnls:
        cum += x; peak = max(peak, cum); mdd = min(mdd, cum-peak)
    rrs = [f(r["rr_exit"], None) for r in rows if r.get("rr_exit")]
    avg_r = sum(x for x in rrs if x is not None)/len(rrs) if rrs else 0
    return dict(n=len(rows), wr=wr, avg=sum(pnls)/len(pnls), med=sorted(pnls)[len(pnls)//2],
                pf=pf, mdd=mdd, avg_r=avg_r, sum=sum(pnls))

mb = mat(base, "base"); mu = mat(up, "up")
print("="*78)
print(f"{'版本':<10}{'n':>6}{'胜率':>8}{'平均%':>9}{'中位%':>8}{'PF':>7}{'期望R':>8}{'MDD%':>9}{'PnL合计%':>10}")
print(f"{'全量':<10}{mb['n']:>6}{mb['wr']:>7.1f}%{mb['avg']:>+8.2f}%{mb['med']:>+8.2f}%{mb['pf']:>7.2f}{mb['avg_r']:>8.2f}{mb['mdd']:>9.1f}%{mb['sum']:>+10.0f}%")
print(f"{'UP-only':<10}{mu['n']:>6}{mu['wr']:>7.1f}%{mu['avg']:>+8.2f}%{mu['med']:>+8.2f}%{mu['pf']:>7.2f}{mu['avg_r']:>8.2f}{mu['mdd']:>9.1f}%{mu['sum']:>+10.0f}%")
print(f"\nΔ: avg {mu['avg']-mb['avg']:+.2f}pp | PF {mu['pf']-mb['pf']:+.2f} | WR {mu['wr']-mb['wr']:+.1f}pp | MDD {mu['mdd']-mb['mdd']:+.1f}pp | 期望R {mu['avg_r']-mb['avg_r']:+.2f}")

print("\n" + "="*78)
print("逐年对比 (全量 vs UP-only):")
print(f"{'年份':<6}{'n_全':>7}{'avg_全':>9}{'PF_全':>7}  | {'n_UP':>7}{'avg_UP':>9}{'PF_UP':>7}")
for y in sorted({r['entry_date'][:4] for r in base}):
    def _row(rows):
        ys = [r for r in rows if r['entry_date'][:4] == y]
        if not ys: return None
        pnls = [f(r['net_pnl_pct']) for r in ys]
        w = [x for x in pnls if x>0]; l = [x for x in pnls if x<=0]
        pf = sum(w)/abs(sum(l)) if sum(l) else 99
        return len(ys), sum(pnls)/len(pnls), pf
    rb, ru = _row(base), _row(up)
    if not rb: continue
    print(f"{y:<6}{rb[0]:>7}{rb[1]:>+8.2f}%{rb[2]:>7.2f}  | {ru[0]:>7}{ru[1]:>+8.2f}%{ru[2]:>7.2f}")

print("\n" + "="*78)
print("4/5/6月(历史弱势月)对比:")
for mm in ("04","05","06"):
    def _m(rows):
        ms = [r for r in rows if r['entry_date'][4:6]==mm]
        if not ms: return None
        pnls=[f(r['net_pnl_pct']) for r in ms]
        return len(ms), sum(pnls)/len(pnls)
    rb, ru = _m(base), _m(up)
    print(f"  {mm}月: 全量 n={rb[0] if rb else 0} avg={rb[1]:+.2f}% | UP n={ru[0] if ru else 0} avg={ru[1]:+.2f}%" if rb else f"  {mm}月: 无")

print("\n" + "="*78)
print("RR 分布对比 (<=-1R 左尾占比):")
def rr_dist(rows):
    rrs = [f(r['rr_exit'], None) for r in rows if r.get('rr_exit')]
    le1 = 100*sum(1 for x in rrs if x <= -1)/len(rrs) if rrs else 0
    g1 = 100*sum(1 for x in rrs if 1 <= x < 2)/len(rrs) if rrs else 0
    g3 = 100*sum(1 for x in rrs if x >= 3)/len(rrs) if rrs else 0
    return le1, g1, g3
lb = rr_dist(base); lu = rr_dist(up)
print(f"  全量:   <=-1R {lb[0]:.1f}% | 1~2R {lb[1]:.1f}% | >=3R {lb[2]:.1f}%")
print(f"  UP-only: <=-1R {lu[0]:.1f}% | 1~2R {lu[1]:.1f}% | >=3R {lu[2]:.1f}%")
