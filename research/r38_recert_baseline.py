# -*- coding: utf-8 -*-
"""r38_recert_baseline.py —— R38 冻结基线重认定(审计步骤③).

旧认证记录(handover/baseline_metrics.json)认证的是 legacy 基线
(combo_v20f_trades.csv, event_trades=1639, max_hold=15, legacy DX)。
R38r 合并重基线后 canonical 名下的数据已变为 Wilder+h12(n=1861/EVENT 1527),
故必须重发认证记录, 否则任何"基线已认证"的引用都会指向错误数据。

本脚本:
  ① 从当前 canonical combo_v20f_trades.csv 重新计算全部认证指标
     (结构/键名与旧记录保持一致, 便于消费方无缝切换)
  ② 写入 handover/baseline_metrics.json, 并附 rebaseline 元数据
  ③ 旧记录已归档 handover/archive/baseline_metrics_legacy_dx_h15.json

口径(与 gen_v20f2_wilder_h12.py 一致):
  ADX = core.indicators.adx14_of (Wilder) | max_hold = CFG.MAX_HOLD (12)
  fee 0.2% 双边 | slippage 0.001
"""
import csv, io, json, os, subprocess, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
CSV = os.path.join(HERE, "combo_v20f_trades.csv")
OUT = os.path.join(HERE, "handover", "baseline_metrics.json")
ARCH = os.path.join(HERE, "handover", "archive", "baseline_metrics_legacy_dx_h15.json")

sys.path.insert(0, HERE)
import config as CFG

rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
cont = [r for r in rows if r.get("src") == "CONT"]

def f(x, d=0.0):
    try: return float(x)
    except: return d

def agg(rs):
    if not rs: return None
    p = [f(r["net_pnl_pct"]) for r in rs]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p)/len(p), 3),
            "wr": round(len(w)/len(p), 3), "pf": round(pf, 2)}

OOS_FROM = "20250701"
def by_year(rs):
    out = {}
    for y in ("2023", "2024", "2025", "2026"):
        ys = [r for r in rs if str(r.get("entry_date"))[:4] == y]
        if not ys: continue
        oos = [r for r in ys if str(r.get("entry_date")) >= OOS_FROM]
        out[y] = {"all": agg(ys), "oos": agg(oos) if oos else {"n": 0}}
    return out

dates = sorted(str(r.get("entry_date")) for r in ev)

# hold buckets
HB = [("1-3d", 1, 3), ("4-6d", 4, 6), ("7-9d", 7, 9), ("10-15d", 10, 15)]
hb = {}
for name, lo, hi in HB:
    rs = [r for r in ev if lo <= int(f(r.get("hold_bars"))) <= hi]
    oos = [r for r in rs if str(r.get("entry_date")) >= OOS_FROM]
    hb[name] = {"all": agg(rs), "oos": agg(oos) if oos else {"n": 0}}

# exit reasons
ex = defaultdict(list)
for r in ev:
    ex[r.get("reason") or "?"].append(r)
exits = {}
for k, rs in sorted(ex.items(), key=lambda kv: -len(kv[1])):
    a = agg(rs)
    if a: exits[k] = a

# mfe/mae
mfe = [f(r.get("mfe_pct")) for r in ev]
mae = [f(r.get("mae_pct")) for r in ev]
rr = [f(r.get("rr_exit")) for r in ev]

is_rs = [r for r in ev if str(r.get("entry_date")) < OOS_FROM]
oos_rs = [r for r in ev if str(r.get("entry_date")) >= OOS_FROM]

try:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r"E:\test\smc_project",
                            capture_output=True, text=True, timeout=20).stdout.strip()
except Exception:
    commit = ""

import datetime
rec = {
    "frozen_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "git_commit": commit,
    "rebaseline": {
        "round": "R38r/R38s",
        "approved_by": "user (2026-09-16)",
        "change": "P1-7 ADX legacy 单窗DX → core.indicators.adx14_of(Wilder); "
                  "P1-8 max_hold 15 → CFG.MAX_HOLD(12)",
        "nature": "让回测追上生产 —— 生产 paper_sim 早已用 Wilder + MAX_HOLD=12; 生产行为零变化",
        "supersedes": "handover/archive/baseline_metrics_legacy_dx_h15.json "
                      "(n=1639, avg3.722, pf3.44)",
        "evidence": ["r38_combo_wilder_h15_trades.csv", "r38_combo_wilder_h12_trades.csv",
                     "r38_rebaseline_verify.py", "r38_delta20_diag.py"],
    },
    "universe": {"kline_files": len([x for x in os.listdir(r"E:\test\smc_project\hermes\kline_cache_tencent") if x.endswith("_daily_800.json")])},
    "data": {"trades_csv": "combo_v20f_trades.csv",
             "event_trades": len(ev), "cont_trades": len(cont), "combo_trades": len(rows)},
    "cost_model": {"fee_pct_roundtrip": round(CFG.FEE_PCT, 2) if hasattr(CFG, "FEE_PCT") else 0.2,
                   "slippage": CFG.SLIPPAGE,
                   "note": "FEE_PCT 双边, SLIPPAGE (core/execution.py)"},
    "execution_version": "core/execution.py simulate/try_fill/try_exit 统一内核 "
                         "(TP1 partial + TP2 + TP3 runner + SL_GAP + 追踪止损 + BAD_ENTRY); "
                         "max_hold = CFG.MAX_HOLD = %d" % CFG.MAX_HOLD,
    "events_version": "classify_title 纯净语义 (NEG_HARD/NEG_SOFT/NEG_INERT/PROGRESS_WITH_DELTA)",
    "period": {"start": dates[0] if dates else "", "end": dates[-1] if dates else "",
               "oos_from": OOS_FROM},
    "smc_leg": {"status": "DISABLED (ENABLE_SMC_LEG=False)",
                "reason": "逐门消融 OOS全负(CI含0); 位移分OOS倒挂"},
    "metrics": {
        "by_year": by_year(ev),
        "overall": {"all": agg(ev), "is": agg(is_rs), "oos": agg(oos_rs)},
        "hold_buckets": hb,
        "exit_reasons": exits,
        "mfe_mae": {"avg_mfe_pct": round(sum(mfe)/len(mfe), 2),
                    "avg_mae_pct": round(sum(mae)/len(mae), 2),
                    "avg_rr_exit": round(sum(rr)/len(rr), 3), "n": len(ev)},
        "cont_leg_reference": {
            "note": "CONT延续腿(生产并行腿, 非SMC); SMC腿已禁用",
            "all": agg(cont),
            "oos": agg([r for r in cont if str(r.get("entry_date")) >= OOS_FROM]),
        },
        "combo_overall": {"all": agg(rows),
                          "is": agg([r for r in rows if str(r.get("entry_date")) < OOS_FROM]),
                          "oos": agg([r for r in rows if str(r.get("entry_date")) >= OOS_FROM])},
    },
}
json.dump(rec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("=" * 88)
print("冻结基线重认定完成 (审计步骤③)")
print("=" * 88)
o = rec["metrics"]["overall"]
print("  EVENT  n=%d avg=%.3f wr=%.3f pf=%.2f" % (o["all"]["n"], o["all"]["avg"], o["all"]["wr"], o["all"]["pf"]))
print("  IS     n=%d avg=%.3f pf=%.2f" % (o["is"]["n"], o["is"]["avg"], o["is"]["pf"]))
print("  OOS    n=%d avg=%.3f pf=%.2f" % (o["oos"]["n"], o["oos"]["avg"], o["oos"]["pf"]))
c = rec["metrics"]["combo_overall"]["all"]
print("  COMBO  n=%d avg=%.3f wr=%.3f pf=%.2f" % (c["n"], c["avg"], c["wr"], c["pf"]))
print("\n  逐年:")
for y, v in rec["metrics"]["by_year"].items():
    a = v["all"]; oo = v.get("oos") or {}
    print("    %s: n=%d avg=%+.2f pf=%.2f | oos n=%s pf=%s"
          % (y, a["n"], a["avg"], a["pf"], oo.get("n", 0),
             ("%.2f" % oo["pf"]) if oo.get("pf") else "-"))
print("\n  归档旧认证: %s" % os.path.basename(ARCH))
print("  → %s" % OUT)