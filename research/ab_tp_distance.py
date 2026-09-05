# -*- coding: utf-8 -*-
"""SMC 腿 TP 距离改造 A/B 对比：当前(结构目标) vs TP>=1.5R vs TP>=2R
验证提升 R 倍数对 payoff/PF/期望的影响（审计 F11 深化）
"""
import io, os, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\test\smc_project\wdh")

import wdh_engine as WE
import core.execution as EX

KLINE = r"E:\test\smc_project\hermes\kline_cache"

def load_daily(path):
    raw = json.load(open(path, encoding="utf-8"))
    bs = []
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                       "c": float(r["c"]), "v": float(r["v"])})
    bs.sort(key=lambda b: b["t"])
    return bs

def simulate_with_tp(seed, daily, tp_mode):
    """tp_mode: 'struct'(当前) / 'min15' / 'min20'"""
    entry_idx = int(seed["entry_idx"])
    if entry_idx >= len(daily) - 1:
        return None
    ep = WE.f(seed["entry_price"])
    zone_low = WE.f(seed["zone_low"])
    sweep_low = WE.f(seed.get("sweep_low"))
    sl_base = min(zone_low, sweep_low) if sweep_low else zone_low
    sl = sl_base * WE.SL_BUFFER
    tgt = WE.f(seed.get("weekly_target")) or WE.f(seed.get("target"))
    risk = ep - sl
    if risk <= 0 or tgt <= ep:
        return None
    if tp_mode == "struct":
        tp = tgt
    elif tp_mode == "min15":
        tp = max(tgt, ep + 1.5 * risk)
    else:
        tp = max(tgt, ep + 2.0 * risk)
    r = EX.simulate(daily, entry_idx, ep, sl, tp2=tp, max_hold=WE.MAX_HOLD)
    if r.get("skipped"):
        return None
    rr = (tp - ep) / risk if risk > 0 else 0
    return {"net": r["net_pnl_pct"], "reason": r["reason"], "rr": rr}

def run(mode, limit_files=1500):
    files = sorted(f for f in os.listdir(KLINE) if f.endswith("_daily_750.json"))[:limit_files]
    rows = []
    n = 0
    for p in files:
        n += 1
        daily = load_daily(os.path.join(KLINE, p))
        if len(daily) < 300:
            continue
        sym = p.replace("_daily_750.json", "").replace("_", ".", 1)
        seeds = WE.build_seeds(sym, daily)
        for sd in seeds:
            tr = simulate_with_tp(sd, daily, mode)
            if tr:
                rows.append(tr)
        if n % 500 == 0:
            print(f"  {mode} {n} files, rows {len(rows)}", flush=True)
    pn = [r["net"] for r in rows if r["net"] is not None]
    if not pn:
        return {"mode": mode, "n": 0}
    n_ = len(pn)
    mean = sum(pn) / n_
    wins = [x for x in pn if x > 0]
    losses = [x for x in pn if x <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses else 99.0
    avg_win = sum(wins) / max(1, len(wins))
    avg_loss = abs(sum(losses)) / max(1, len(losses))
    payoff = avg_win / avg_loss if avg_loss else 99.0
    rrs = [r["rr"] for r in rows]
    return {"mode": mode, "n": n_, "avg": mean, "win": len(wins) / n_, "pf": pf,
            "payoff": payoff, "avg_rr": sum(rrs) / len(rrs) if rrs else 0,
            "reason": {r: sum(1 for x in rows if x["reason"] == r) for r in set(x["reason"] for x in rows)}}

if __name__ == "__main__":
    results = []
    for m in ("struct", "min15", "min20"):
        r = run(m)
        results.append(r)
        print(f"\n[{m}] n={r.get('n')} avg={r.get('avg',0):+.2f}% wr={r.get('win',0)*100:.1f}% "
              f"PF={r.get('pf',0):.2f} payoff={r.get('payoff',0):.2f} avgR={r.get('avg_rr',0):.2f}")
        print(f"    reason: {r.get('reason')}", flush=True)
    print("\n=== 对比结论 ===")
    for r in results:
        print(f"  {r['mode']}: n={r['n']} avg={r['avg']:+.2f}% PF={r['pf']:.2f} payoff={r['payoff']:.2f} avgR={r['avg_rr']:.2f}")
