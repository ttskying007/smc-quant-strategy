# -*- coding: utf-8 -*-
"""逐笔交易深度分析：重放 SMC 腿每笔，计算 MAE/MFE/买卖价/R倍数，
筛选最好/最差/卖飞/卖早卖晚案例，输出逐笔报告（含 K 线图脚本依赖的 CSV）
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\test\smc_project\wdh")

import wdh_engine as WE
import core.execution as EX

RESEARCH = r"E:\test\smc_project\research"
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

# 读 trades + seeds
trades = list(csv.DictReader(open(os.path.join(r"E:\test\smc_project\wdh", "W1D1D4_trades.csv"), encoding="utf-8-sig")))
seeds = list(csv.DictReader(open(os.path.join(r"E:\test\smc_project\wdh", "W1D1D4_seeds.csv"), encoding="utf-8-sig")))
seed_by_key = {}
for s in seeds:
    seed_by_key[(s["symbol"], s["entry_date"])] = s
# 代码文件映射
code2file = {f.split("_")[0]: os.path.join(KLINE, f) for f in os.listdir(KLINE) if f.endswith("_daily_750.json")}

detail = []
n = 0
for tr in trades:
    sym = tr["symbol"]
    entry_date = tr["entry_date"]
    code = sym.split(".")[0]
    sd = seed_by_key.get((sym, entry_date))
    path = code2file.get(code)
    if not sd or not path or not os.path.exists(path):
        continue
    daily = load_daily(path)
    if not daily:
        continue
    entry_idx = int(sd["entry_idx"])
    if entry_idx >= len(daily):
        continue
    ep = WE.f(sd["entry_price"])
    zone_low = WE.f(sd["zone_low"])
    sweep_low = WE.f(sd.get("sweep_low"))
    sl_base = min(zone_low, sweep_low) if sweep_low else zone_low
    sl = sl_base * WE.SL_BUFFER
    tgt = WE.f(sd.get("weekly_target")) or WE.f(sd.get("target"))
    risk = ep - sl
    if risk <= 0 or tgt <= ep:
        continue
    tgt = max(tgt, ep + 1.5 * risk)  # TP>=1.5R
    r = EX.simulate(daily, entry_idx, ep, sl, tp2=tgt, max_hold=WE.MAX_HOLD)
    if r.get("skipped"):
        continue
    n += 1
    # 信号组合
    sig = []
    if sd.get("w_permission"):
        sig.append(sd["w_permission"])
    if sd.get("sweep_date"):
        sig.append(f"扫损{sd['sweep_date']}")
    if sd.get("ob_date"):
        sig.append(f"OB{sd['ob_date']}")
    if sd.get("touch_date"):
        sig.append(f"触POI{sd['touch_date']}")
    if sd.get("reclaim_date"):
        sig.append(f"收回{sd['reclaim_date']}")
    detail.append({
        "symbol": sym, "entry_date": entry_date, "code": code,
        "net_pnl_pct": float(tr["net_pnl_pct"]), "reason": tr["reason"],
        "hold": int(tr["hold_bars"]), "mfe_r": r["mfe_r"], "mae_r": r["mae_r"],
        "mfe_pct": r["mfe_pct"], "mae_pct": r["mae_pct"],
        "ep": ep, "sl": sl, "tgt": tgt, "risk_pct": (ep - sl) / ep * 100,
        "rr_target": (tgt - ep) / risk if risk > 0 else 0,
        "exit_px": r["exit_price"], "rr_exit": (r["exit_price"] / ep - 1) / (risk / ep) if risk > 0 else 0,
        "signals": "|".join(sig), "file": os.path.basename(path),
    })

# 排序：最好/最差
detail.sort(key=lambda d: d["net_pnl_pct"], reverse=True)
best = detail[:10]
worst = detail[-10:][::-1]
# 卖飞：exit时 rr_exit 远小于 rr_target（TP太远没到，时间止损平仓但 mfe_r 高）
sell_early = [d for d in detail if d["reason"] == "TIME_STOP" and d["mfe_r"] > 1.2]
sell_early.sort(key=lambda d: -d["mfe_r"])
# 卖晚：SL 深度回撤（mae 很深才触发）
sell_late = [d for d in detail if d["reason"] in ("SL_HIT", "SL_GAP") and d["mae_r"] > 1.5]
sell_late.sort(key=lambda d: -d["mae_r"])

def dump_list(lst, title):
    print(f"\n=== {title} ({len(lst)}) ===")
    for d in lst[:8]:
        print(f"  {d['symbol']} {d['entry_date']} pnl={d['net_pnl_pct']:+.2f}% {d['reason']} hold={d['hold']} "
              f"MFE={d['mfe_pct']:+.1f}% MAE={d['mae_pct']:.1f}% 买卖价={d['ep']:.2f}->{d['exit_px']:.2f} R={d['rr_exit']:.2f}")
        print(f"    信号: {d['signals']}")

dump_list(best, "最好10笔")
dump_list(worst, "最差10笔")
dump_list(sell_early, "卖飞(TIME_STOP但MFE高)")
dump_list(sell_late, "卖晚(SL但MAE深)")

# 统计 TP/SL 架构
tp_hit = sum(1 for d in detail if d["reason"] == "TP_STRUCTURAL")
time_stop = sum(1 for d in detail if d["reason"] == "TIME_STOP")
sl_hit = sum(1 for d in detail if d["reason"] in ("SL_HIT", "SL_GAP"))
print(f"\n=== 架构统计 (n={len(detail)}) ===")
print(f"TP触达 {tp_hit} ({tp_hit/len(detail)*100:.1f}%) | 时间止损 {time_stop} ({time_stop/len(detail)*100:.1f}%) | SL {sl_hit} ({sl_hit/len(detail)*100:.1f}%)")
mfe_all = [d["mfe_r"] for d in detail]
mae_all = [d["mae_r"] for d in detail]
print(f"平均MFE(R): {sum(mfe_all)/len(mfe_all):.2f} | 平均MAE(R): {sum(mae_all)/len(mae_all):.2f}")

# 存 CSV 供 K 线图脚本
out_csv = os.path.join(RESEARCH, "handover", "逐笔分析明细.csv")
with open(out_csv, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(detail[0].keys()))
    w.writeheader()
    for d in detail:
        w.writerow(d)
print(f"\n已写 {out_csv} ({len(detail)} 笔)")