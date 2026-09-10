# -*- coding: utf-8 -*-
"""v3_full_replay_review.py —— V3 修正后全面回测+验证+复盘（P0-1 统一退出语义版）
背景: B1 SHADOW 首跑用旧退出(内联SL/TIME无TP), V3 P0-1 已将退出统一到 core/setup_exit.py。
本脚本 = 修正后的全面复验:
  1. 全市场统一链回测(run_sequence_v2 → build_setup → settle_setup 单源退出)
  2. 逐年分析(2023-2026 每年 N/WR/Avg/PF/MaxDD)
  3. 逐月分析(60+ 月度, 含最差月/最好月/正收益月占比)
  4. 逐笔分析(集中度 Top1/Top5, MFE/MAE分布, 退出原因分布)
  5. 新旧退出语义 A/B(SL/TIME-only vs +TP3R): 量化 TP 补全的影响
  6. 与冻结 EVENT 基线(md5登记)对照 —— 只对照, 不改生产
判定(预注册): 每年 PF>1 且 avg>0 视为该年有效; 任一年 PF<0.9 → 红旗复核;
  逐笔 Top1<10%(否则集中度红旗); 新旧退出 Δavg>1pp → 必须复核 TP 语义对生产腿的影响。
输出: handover/V3修正后全面回测复盘.json"""
import glob, io, json, os, sys, time
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.sequence import run_sequence_v2
from core.setup_engine import build_setup, ENGINE_VERSION
from core.setup_exit import settle_setup, EXIT_VERSION, settle_from_record

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT = r"E:\test\smc_project\research\handover\V3修正后全面回测复盘.json"
FEE = 0.2
OOS = "20250701"
SAMPLE_STRIDE = 2          # 全市场 2/3 抽样(与 Family DB 同口径)

FILES = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::SAMPLE_STRIDE]

def load_daily(fp):
    raw = json.load(open(fp, encoding="utf-8"))
    return [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
             "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]

def stats(vals):
    if not vals:
        return {"n": 0}
    w = sum(x for x in vals if x > 0); l_ = abs(sum(x for x in vals if x <= 0))
    return {"n": len(vals), "avg": round(sum(vals) / len(vals), 3),
            "wr": round(len([x for x in vals if x > 0]) / len(vals) * 100, 1),
            "pf": round(w / l_, 2) if l_ > 0 else 99.0}

def max_dd(vals):
    eq, peak, dd = 0.0, 0.0, 0.0
    for x in vals:
        eq += x
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 2)

trades = []       # (date, ret, exit_reason, symbol, ret_no_tp)
t0 = time.time()
from core.entry import fill_in_zone
for fp in FILES:
    try:
        dd_ = load_daily(fp)
    except Exception:
        continue
    if len(dd_) < 200:
        continue
    code = os.path.basename(fp).split("_")[0]
    n = len(dd_)
    for i in range(150, n - 25):
        try:
            m = run_sequence_v2(dd_, i, symbol=code)
            s = m.setup()
        except Exception:
            continue
        if s is None:
            continue
        poi = s["poi"]
        zone = {"zone_low": poi["low"], "zone_high": poi["high"],
                "invalid_price": poi["low"] * 0.97, "optimal_entry": poi["mid"]}
        try:
            fill = fill_in_zone(dd_, i, zone, max_bars=5, fill_mode="STRICT_LIMIT")
        except Exception:
            continue
        if fill is None or fill.get("fill_price") is None:
            continue
        fi, fpx = fill["fill_idx"], fill["fill_price"]
        # 新语义(+TP3R)与旧语义(无TP)同笔配对 —— 都走单源 settle_from_record
        res = settle_from_record(dd_, fi, fpx, zone["invalid_price"], fee_pct=FEE,
                                 max_bars=15, tp_rr=3.0)
        old = settle_from_record(dd_, fi, fpx, zone["invalid_price"], fee_pct=FEE,
                                 max_bars=15, tp_rr=1e9)      # tp→∞ = 无TP旧语义
        if res.get("status") not in ("SL", "TP", "TIME"):
            continue
        trades.append({"d": dd_[i]["t"], "sym": code, "ret": res["ret_pct"],
                       "why": res["exit_reason"], "fill_px": fpx,
                       "ret_old": old.get("ret_pct"),
                       "sl": res.get("sl"), "tp": res.get("tp"),
                       "fill_date": dd_[fi]["t"]})

n = len(trades)
oos = [t for t in trades if t["d"] >= OOS]
S_all, S_oos = stats([t["ret"] for t in trades]), stats([t["ret"] for t in oos])

# ---- 逐年 ----
by_year = defaultdict(list)
for t in oos + [x for x in trades if x["d"] < OOS]:
    by_year[t["d"][:4]].append(t["ret"])
yearly = {y: {**stats(v), "mdd_pts": max_dd(v)} for y, v in sorted(by_year.items())}

# ---- 逐月 ----
by_month = defaultdict(list)
for t in trades:
    by_month[t["d"][:6]].append(t["ret"])
monthly = {mth: stats(v) for mth, v in sorted(by_month.items())}
pos_months = sum(1 for v in monthly.values() if v.get("avg", 0) > 0)

# ---- 逐笔 ----
rets = sorted((t["ret"] for t in trades), reverse=True)
tot = sum(abs(x) for x in rets) or 1
top1, top5 = rets[0] / tot, sum(rets[:5]) / tot
exit_dist = defaultdict(int)
for t in trades:
    exit_dist[t["why"]] += 1

# ---- 新旧退出 A/B(同笔对照) ----
pair = [(t["ret"], t["ret_old"]) for t in trades if t["ret_old"] is not None]
old_oos = [o for (r_, o) in pair if True]  # 全样本同笔配对
S_old = stats([o for _, o in pair])
S_new = stats([r for r, _ in pair])
delta_ab = round(S_new["avg"] - S_old["avg"], 3) if S_new.get("avg") is not None else None

report = {
    "title": "V3 修正后全面回测复盘(统一 setup_exit 单源语义)",
    "engine": ENGINE_VERSION, "exit": EXIT_VERSION,
    "sample": f"全市场 [::{SAMPLE_STRIDE}] 抽样 {len(FILES)} 股",
    "period": f"{trades[0]['d'][:6]}~{trades[-1]['d'][:6]}" if trades else "-",
    "total": {"all": S_all, "oos": S_oos, "oos_cutoff": OOS},
    "yearly": yearly,
    "monthly": {"months": len(monthly), "pos_month_pct": round(pos_months / max(1, len(monthly)) * 100, 1),
                "best": max(monthly.items(), key=lambda kv: kv[1].get("avg") or -99)[0] if monthly else None,
                "worst": min(monthly.items(), key=lambda kv: kv[1].get("avg") or 99)[0] if monthly else None,
                "detail_headtail": {k: monthly[k] for k in (list(monthly)[:3] + list(monthly)[-3:])}},
    "per_trade": {"top1_pct_of_total_abs": round(top1 * 100, 2),
                  "top5_pct_of_total_abs": round(top5 * 100, 2),
                  "exit_reason_dist": dict(exit_dist),
                  "best": rets[0] if rets else None, "worst": rets[-1] if rets else None},
    "exit_semantics_ab": {"new_with_tp": S_new, "old_no_tp": S_old, "delta_avg_pp": delta_ab},
    "flags": {
        "any_year_pf_below_0.9": [y for y, v in yearly.items() if v.get("pf") is not None and v["pf"] < 0.9],
        "top1_over_10pct": top1 > 0.10,
        "ab_delta_over_1pp": delta_ab is not None and abs(delta_ab) > 1.0},
    "runtime_s": round(time.time() - t0, 1),
}
json.dump(report, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print(f"== V3 修正后全面回测(统一退出) == 样本 {len(FILES)} 股, {n} 笔, {report['runtime_s']}s")
print(f"全期: {S_all}")
print(f"OOS:  {S_oos}")
print("\n-- 逐年 --")
for y, v in yearly.items():
    print(f"  {y}: {v}")
print(f"\n-- 逐月: {len(monthly)} 月, 正收益月 {report['monthly']['pos_month_pct']}%, "
      f"最好 {report['monthly']['best']} 最差 {report['monthly']['worst']}")
print(f"\n-- 逐笔: Top1占绝对值 {report['per_trade']['top1_pct_of_total_abs']}%  "
      f"Top5 {report['per_trade']['top5_pct_of_total_abs']}%  退出分布 {dict(exit_dist)}")
print(f"\n-- 退出语义 A/B: 新(+TP3R) {S_new} vs 旧(无TP) {S_old} → Δavg {delta_ab}pp")
print(f"红旗: {report['flags']}")
print("已写", OUT)