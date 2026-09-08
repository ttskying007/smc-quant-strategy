# -*- coding: utf-8 -*-
"""V1 迭代2: SMC 阶段漏斗 + Displacement 语义分排序信息 A/B
单趟全市场(4662股): ①输出阶段漏斗(研究腿, 补齐V1迭代1的SMC侧)
②按位移分桶分档输出 IS/OOS avg/WR/PF —— 检验语义分是否有排序信息
   (若高分桶 OOS 稳定优于低分桶 → 打分可作为 admission 连续门槛, 而非布尔门)
"""
import sys, os, json, io, time
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import wdh_engine as W

OOS = "20250701"
files = sorted(p for p in os.listdir(W.KLINE) if p.endswith("_daily_800.json"))
t0 = time.time()
funnel = {"universe_files": len(files)}
buckets = {}   # bucket -> list of trades
seeds_n = 0
trades_all = []
stage_keys = ("bars_scanned", "w1_pass", "sweep_found", "bos_found", "disp_pass", "entry_found", "seeds")
stage_tot = {k: 0 for k in stage_keys}
for p in files:
    daily = W.bars_for(os.path.join(W.KLINE, p))
    if len(daily) < 300:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    _seeds = W.build_seeds(sym, daily, None)
    for k in stage_keys:
        stage_tot[k] += W.STAGE_STATS.get(k, 0)
    for sd in _seeds:
        seeds_n += 1
        tr = W.replay(sd, daily)
        if tr and tr.get("net_pnl_pct") is not None:
            tr["entry_date"] = sd["entry_date"]
            bkt = sd.get("disp_bucket", "N/A")
            buckets.setdefault(bkt, []).append(tr)
            trades_all.append(tr)
funnel["stage"] = stage_tot

print(f"DONE: files={len(files)} seeds={seeds_n} trades={len(trades_all)} ({time.time()-t0:.0f}s)")

def _stats(ts, oos):
    sel = [t for t in ts if (t["entry_date"] >= OOS) == oos]
    if not sel:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    pn = [t["net_pnl_pct"] for t in sel]
    w = [x for x in pn if x > 0]
    return {"n": len(pn), "avg": round(sum(pn)/len(pn), 3), "wr": round(len(w)/len(pn), 3),
            "pf": round(sum(w)/abs(sum(x for x in pn if x <= 0)), 2) if any(x <= 0 for x in pn) and sum(x for x in pn if x <= 0) != 0 else 99}

out = {"asof": time.strftime("%Y-%m-%d %H:%M:%S"), "oos_from": OOS,
       "funnel": funnel, "seeds": seeds_n, "trades": len(trades_all), "buckets": {}}
print("\n== SMC 研究腿阶段漏斗 ==")
prev = 0
for k in ("bars_scanned", "w1_pass", "sweep_found", "sweep_vol_pass", "bos_found", "disp_pass", "entry_found", "seeds"):
    v = stage_tot[k]
    keep = (v / prev) if prev else None
    print(f"  {k:16s}: {v:6d}  (上阶段留存率 {keep:.1%})" if keep else f"  {k:16s}: {v:6d}")
    prev = v

print("\n== Displacement 语义分分桶（IS/OOS）==")
for bkt in sorted(buckets):
    bs = buckets[bkt]
    out["buckets"][bkt] = {"IS": _stats(bs, False), "OOS": _stats(bs, True), "n_all": len(bs)}
    print(f"  {bkt:10s}: all={len(bs):4d} IS={_stats(bs, False)} OOS={_stats(bs, True)}")

with open(r"E:\test\smc_project\research\handover\V1迭代2_位移分与漏斗.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("\n已写 handover/V1迭代2_位移分与漏斗.json")