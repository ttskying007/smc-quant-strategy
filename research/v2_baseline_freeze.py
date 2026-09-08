# -*- coding: utf-8 -*-
"""V2 ITERATION 0: Baseline Freeze
冻结: git commit / 数据快照 / Universe / 成本 / Execution 版本 / 时间区间 / 纯净基线指标
含: 事件腿纯净口径逐年/持有桶/退出原因分解(新CSV 1640笔)
输出: handover/baseline_metrics.json —— 后续每轮实验的唯一对照基线
"""
import csv, io, json, os, subprocess, sys, hashlib
from collections import Counter, defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import core.execution as EX
import core.events as EV

ROOT = r"E:\test\smc_project\research"
CSV = os.path.join(ROOT, "combo_v20f_trades.csv")
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS_FROM = "20250701"

# ---- 冻结元信息 ----
git_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r"E:\test\smc_project",
                          capture_output=True, text=True).stdout.strip()
universe_files = [f for f in os.listdir(KT) if f.endswith("_daily_800.json")]
snap_hash = hashlib.md5(",".join(sorted(universe_files)).encode()).hexdigest()[:12]

rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net"] = float(r["net_pnl_pct"])
    r["hold_bars"] = int(r.get("hold_bars") or 0)

def stats(ts):
    if not ts:
        return {"n": 0}
    pn = [t["net"] for t in ts]
    w = [x for x in pn if x > 0]
    return {"n": len(pn), "avg": round(sum(pn)/len(pn), 3), "wr": round(len(w)/len(pn), 3),
            "pf": round(sum(w)/abs(sum(x for x in pn if x <= 0)), 2) if any(x <= 0 for x in pn) and sum(x for x in pn if x <= 0) != 0 else 99}

baseline = {
    "frozen_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
    "git_commit": git_head,
    "universe": {"kline_files": len(universe_files), "snapshot_hash": snap_hash},
    "data": {"trades_csv": os.path.basename(CSV), "event_trades": len(rows)},
    "cost_model": {"fee_pct_roundtrip": 0.20, "slippage": 0.001,
                   "note": "FEE_PCT=0.20%双边, SLIPPAGE=0.001 (core/execution.py)"},
    "execution_version": "core/execution.py simulate/try_fill/try_exit 统一内核 "
                         "(TP1 partial + TP2 + TP3 runner + SL_GAP + 追踪止损 P1-1 + BAD_ENTRY)",
    "events_version": "classify_title 纯净语义 (NEG_HARD/NEG_SOFT/NEG_INERT/PROGRESS_WITH_DELTA), "
                      "2026-09-08 修复注销/激励类污染(剔除444笔)",
    "period": {"start": min(r["entry_date"] for r in rows), "end": max(r["entry_date"] for r in rows),
               "oos_from": OOS_FROM},
    "smc_leg": {"status": "DISABLED (ENABLE_SMC_LEG=False)", 
                "reason": "逐门消融 OOS全负(CI含0); 位移分OOS倒挂; V1迭代1-2证据"},
    "metrics": {},
}

# ---- 逐年 ----
by_year = {}
for y in sorted({r["entry_date"][:4] for r in rows}):
    ys = [t for t in rows if t["entry_date"][:4] == y]
    by_year[y] = {"all": stats(ys), "oos": stats([t for t in ys if t["entry_date"] >= OOS_FROM])}
baseline["metrics"]["by_year"] = by_year

# ---- 全样本 / IS / OOS ----
baseline["metrics"]["overall"] = {"all": stats(rows),
                                   "is": stats([t for t in rows if t["entry_date"] < OOS_FROM]),
                                   "oos": stats([t for t in rows if t["entry_date"] >= OOS_FROM])}

# ---- 持有桶 ----
hb = {}
for name, f in {"1-3d": lambda h: 1 <= h <= 3, "4-6d": lambda h: 4 <= h <= 6,
                "7-9d": lambda h: 7 <= h <= 9, "10-15d": lambda h: 10 <= h <= 15}.items():
    g = [t for t in rows if f(t["hold_bars"])]
    hb[name] = {"all": stats(g), "oos": stats([t for t in g if t["entry_date"] >= OOS_FROM])}
baseline["metrics"]["hold_buckets"] = hb

# ---- 退出原因 ----
er = {}
for reason, g in [(k, [t for t in rows if t.get("reason") == k])
                   for k in ("TP2_RUNNER", "TIME_STOP", "SL_HIT", "BE", "SL_GAP")]:
    er[reason] = stats(g)
baseline["metrics"]["exit_reasons"] = er

# ---- MFE/MAE 汇总 ----
mfes = [float(r.get("mfe_pct") or 0) for r in rows if r.get("mfe_pct")]
maes = [float(r.get("mae_pct") or 0) for r in rows if r.get("mae_pct")]
rrs = [float(r.get("rr_exit") or 0) for r in rows if r.get("rr_exit")]
baseline["metrics"]["mfe_mae"] = {
    "avg_mfe_pct": round(sum(mfes)/len(mfes), 2) if mfes else None,
    "avg_mae_pct": round(sum(maes)/len(maes), 2) if maes else None,
    "avg_rr_exit": round(sum(rrs)/len(rrs), 2) if rrs else None,
    "n": len(mfes),
}

# ---- CONT 延续腿参考(生产并行腿, 供对照) ----
smc_rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
            if r.get("src") == "CONT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in smc_rows:
    r["net"] = float(r["net_pnl_pct"])
smc_oos = [r for r in smc_rows if r["entry_date"] >= OOS_FROM]
baseline["metrics"]["cont_leg_reference"] = {
    "note": "CONT延续腿(生产并行腿, 非SMC); SMC腿已禁用(逐门消融OOS全负)",
    "all": stats(smc_rows), "oos": stats(smc_oos)}

with open(os.path.join(ROOT, "handover", "baseline_metrics.json"), "w", encoding="utf-8") as fh:
    json.dump(baseline, fh, ensure_ascii=False, indent=2, default=str)

print(f"== V2 ITERATION 0 Baseline Freeze 完成 ==")
print(f"git: {git_head[:12]} | universe: {len(universe_files)} files (snap {snap_hash})")
print(f"事件腿纯净: {len(rows)} 笔")
print(f"overall: all={baseline['metrics']['overall']['all']}")
print(f"          is={baseline['metrics']['overall']['is']}")
print(f"         oos={baseline['metrics']['overall']['oos']}")
print(f"持有桶 OOS: " + " | ".join(f"{k}:{v['oos']['avg']}%" for k, v in hb.items()))
print(f"MFE/MAE: avg={baseline['metrics']['mfe_mae']['avg_mfe_pct']}%/{baseline['metrics']['mfe_mae']['avg_mae_pct']}% RR_exit={baseline['metrics']['mfe_mae']['avg_rr_exit']}")
print(f"CONT腿(生产并行,对照): oos={baseline['metrics']['cont_leg_reference']['oos']}")
print("已写 handover/baseline_metrics.json")