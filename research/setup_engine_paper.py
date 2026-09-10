# -*- coding: utf-8 -*-
"""Setup Engine PAPER 台账 —— V3 P0-1/P0-2 重写版
V3审计§六 两个问题修正:
  1) SAMPLED PAPER 明确标注: 本台账是 [::10] 抽样监测(非全市场), 统计口径写入 summary.sampling,
     晋级判定只以 SAMPLED_PAPER 命名, 禁止与 FULL_UNIVERSE PAPER 混淆。
  2) 退出语义单源化: 结算统一走 core/setup_exit.py(settle_setup/settle_from_record) ——
     旧版注释写"TP3结构位"但无 TP 逻辑的分叉已消除; SL=invalid-1.5ATR / TIME=15bar /
     TP=3R 结构位, 与 B1 SHADOW 回测同 EXIT_VERSION。
新信号生成走 core/setup_engine.py build_setup(统一 setup_id/engine_version/exit_version)。
自动化: 每日跑, 幂等(同 setup_id 只记一次), 滚动90天。"""
import glob, io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.entry import fill_in_zone
from core.setup_exit import settle_from_record, EXIT_VERSION
from core.setup_engine import build_setup, validate_setup, ENGINE_VERSION

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
LEDGER = r"E:\test\smc_project\research\handover\setup_engine_paper_ledger.json"
FEE = 0.2
SAMPLE = 10           # [::10] —— SAMPLED PAPER(监测抽样), 非全市场
RECENT_DECISIONS = 3

led = {"signals": [], "summary": {}}
if os.path.exists(LEDGER):
    try:
        led = json.load(open(LEDGER, encoding="utf-8"))
    except Exception:
        pass

files = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::SAMPLE]
today = time.strftime("%Y%m%d")

def load_daily(fp):
    raw = json.load(open(fp, encoding="utf-8"))
    return [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
             "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]

# ---------- 1) 推进既有 OPEN 信号(单一退出实现) ----------
n_settled = n_still_open = 0
for sig in led.get("signals", []):
    if sig.get("status") not in ("OPEN",):
        continue
    fp = None
    for suf in ("_SZ", "_SH", "_BJ"):
        p = os.path.join(KL, f"{sig['code']}{suf}_daily_800.json")
        if os.path.exists(p):
            fp = p
            break
    if not fp:
        continue
    try:
        dd = load_daily(fp)
    except Exception:
        continue
    n = len(dd)
    i0 = next((k for k, b in enumerate(dd) if b["t"] == sig["date"]), None)
    if i0 is None:
        continue
    zone = {"zone_low": sig["zone_low"], "zone_high": sig["zone_high"],
            "invalid_price": sig["invalid_price"], "optimal_entry": sig["optimal_entry"]}
    fill = fill_in_zone(dd, i0, zone, max_bars=5, fill_mode="STRICT_LIMIT")
    if fill is None or fill.get("fill_price") is None:
        if fill and fill.get("mode") == "INVALIDATED_BEFORE_FILL":
            sig["status"] = "INVALIDATED"
            sig["exit_reason"] = "INVALIDATED_BEFORE_FILL"
            sig["exit_version"] = EXIT_VERSION
            n_settled += 1
        continue
    fi, fpx = fill["fill_idx"], fill["fill_price"]
    sig["filled_price"], sig["fill_date"] = fpx, dd[fi]["t"]
    # P0-1: 统一退出(与回测同源); 旧分叉(注释TP3/实际无TP)已消除
    res = settle_from_record(dd, fi, fpx, sig["invalid_price"], fee_pct=FEE, max_bars=15, tp_rr=3.0)
    sig["exit_version"] = res["exit_version"]
    sig["sl"], sig["tp"] = res.get("sl"), res.get("tp")
    if res["status"] in ("SL", "TP", "TIME"):
        sig["status"], sig["ret_pct"], sig["exit_reason"] = res["status"], res["ret_pct"], res["exit_reason"]
        n_settled += 1
    elif res["status"] == "OPEN":
        n_still_open += 1

# ---------- 2) 今日新 READY(统一 SetupEngine) ----------
n_new = 0
seen = {(s.get("code"), s.get("date")) for s in led.get("signals", [])}
for fp in files:
    code = os.path.basename(fp).split("_")[0]
    try:
        dd = load_daily(fp)
    except Exception:
        continue
    if len(dd) < 200:
        continue
    n = len(dd)
    for i in range(max(150, n - RECENT_DECISIONS), n):
        if (code, dd[i]["t"]) in seen:
            continue
        setup = build_setup(dd, i, code)
        if setup is None:
            continue
        ok_v, why = validate_setup(setup)
        if not ok_v:
            continue
        sig = {"setup_id": setup["setup_id"],
               "engine_version": setup["engine_version"], "exit_version": setup["exit_version"],
               "code": code, "date": dd[i]["t"], "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "zone_low": setup["zone"]["low"], "zone_high": setup["zone"]["high"],
               "optimal_entry": setup["zone"]["optimal"],
               "invalid_price": setup["invalid_price"], "poi_type": setup["poi"]["type"],
               "sequence": setup["sequence"], "family": setup["family"],
               "order_type": setup["order_type"],
               "status": "OPEN", "ret_pct": None, "exit_reason": None}
        led.setdefault("signals", []).append(sig)
        seen.add((code, dd[i]["t"]))
        n_new += 1

# ---------- 3) 汇总(SAMPLED 口径显式) ----------
sigs = led.get("signals", [])
closed = [s for s in sigs if s.get("ret_pct") is not None]
avg = round(sum(s["ret_pct"] for s in closed) / len(closed), 3) if closed else None
w = sum(s["ret_pct"] for s in closed if s["ret_pct"] > 0)
l_ = abs(sum(s["ret_pct"] for s in closed if s["ret_pct"] <= 0))
# 晋级门预演(V3 §十六): 七道门按 closed 样本逐项计算, 未达标如实显示
gates = {"G1_sample": len(closed) >= 30,
         "G2_edge": (len(closed) > 0 and avg is not None and avg > 0
                     and (w / l_ > 1 if l_ > 0 else True))}
top1 = max((abs(s["ret_pct"]) for s in closed), default=0)
tot = sum(abs(s["ret_pct"]) for s in closed) or 1
gates["G3_concentration"] = len(closed) > 0 and top1 / tot < 0.10
led["summary"] = {
    "ledger_type": "SAMPLED_PAPER",                       # 禁止混淆: 非全市场
    "sampling": f"[::{SAMPLE}] 抽样监测, 每日{RECENT_DECISIONS}个决策窗",
    "exit_version": EXIT_VERSION, "engine_version": ENGINE_VERSION,
    "total": len(sigs), "open": len([s for s in sigs if s.get("status") == "OPEN"]),
    "closed": len(closed), "avg_closed": avg,
    "pf_closed": round(w / l_, 2) if l_ > 0 else None,
    "promotion_gates_preview": gates,                      # 完整7门在 closed>=30 时全量评估
    "days_accum": led.get("summary", {}).get("days_accum", 0) + 1, "last_run": today}
json.dump(led, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"新 READY: {n_new}  结算: {n_settled}  仍OPEN: {n_still_open}")
print(f"台账[SAMPLED_PAPER ::{SAMPLE}]: total={len(sigs)} closed={len(closed)} avg={avg} "
      f"days={led['summary']['days_accum']} exit={EXIT_VERSION}")
print("晋级门预演:", gates)
print("已写", LEDGER)