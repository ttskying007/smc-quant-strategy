# -*- coding: utf-8 -*-
"""r38_proxy_weight_verify.py —— R38 验证生产 _market_proxy 仓位加权机制.
生产逻辑: _risk_coef = 1.0; if proxy>0.02: max(0.3, 1-(proxy-0.02)/0.04)(强市降仓);
_regime_coef = 1.0; if WEAK_MARKET_WEIGHT and proxy: clip(1-k×proxy, 0.3, 2.0)(弱市加仓);
final position × _risk_coef × _regime_coef.
在冻结基线 EVENT 腿上重放该权重(proxy 决策日口径), 比较 组合加权指标 vs 等权.
这验证生产机制是否已是最优, 以及 C1 是否应被废弃. 纯研究. """
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
def f(x, d=0.0):
    try: return float(x)
    except: return d

def prod_weight(pr):
    # 复现生产 _risk_coef × _regime_coef (WEAK_MARKET_K=2.0, W_MIN=0.3, W_MAX=2.0)
    rc = 1.0
    if pr is not None and pr > 0.02:
        rc = max(0.3, 1.0 - (pr - 0.02) / 0.04)
    gc = 1.0
    if pr is not None:
        gc = max(0.3, min(2.0, 1.0 - 2.0 * pr))
    return rc * gc

weighted = []
n_weak = 0; n_strong = 0
for r in ev:
    code = r["symbol"].split(".")[0]
    d8 = r.get("entry_date") or r.get("buy_date")
    pr = ps._market_proxy(code, d8)
    w = prod_weight(pr) if pr is not None else 1.0
    if pr is not None and pr < -0.01: n_weak += 1
    if pr is not None and pr > 0.02: n_strong += 1
    weighted.append((f(r["net_pnl_pct"]), w))

def combo(weighted):
    contrib = [p*w for p, w in weighted]
    wins = [x for x in contrib if x>0]; losses = [x for x in contrib if x<=0]
    pf = sum(wins)/abs(sum(losses)) if sum(losses) else 99
    eq=[]; cum=0.0; peak=0.0; mdd=0.0
    for x in contrib:
        cum+=x; peak=max(peak,cum); mdd=min(mdd,cum-peak)
    return dict(avg=sum(contrib)/len(contrib), pf=pf, mdd=mdd, sum=sum(contrib))

equal = [(p, 1.0) for p, _ in weighted]
we = combo(equal); wp = combo(weighted)
print("="*78)
print("生产 _market_proxy 仓位加权 vs 等权 (EVENT n=%d, 弱市%d 强市%d)" %
      (len(ev), n_weak, n_strong))
print("="*78)
print(f"{'方案':<18}{'加权平均%':>10}{'PF':>7}{'MDD%':>9}{'PnL合计%':>10}")
print(f"{'等权(w=1)':<18}{we['avg']:>+9.2f}%{we['pf']:>7.2f}{we['mdd']:>9.1f}%{we['sum']:>+10.0f}%")
print(f"{'生产proxy加权':<18}{wp['avg']:>+9.2f}%{wp['pf']:>7.2f}{wp['mdd']:>9.1f}%{wp['sum']:>+10.0f}%")
print(f"\nΔ: avg {wp['avg']-we['avg']:+.2f}pp | PF {wp['pf']-we['pf']:+.2f} | MDD {wp['mdd']-we['mdd']:+.1f}pp | PnL {wp['sum']-we['sum']:+.0f}pp")