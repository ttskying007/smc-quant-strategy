# -*- coding: utf-8 -*-
"""Setup Engine PAPER 累积台账(B1 SHADOW 后续, 自动化)
每日: run_sequence_v2 扫最近 bar → READY 信号 → 记录(前向纸面):
  entry_limit = poi.mid, sl = poi.low*0.97-1.5ATR, bars_max=15
  既有台账里的信号 → 用 K线推进更新结果(15bar 时间退出/SL/TP3 结构位)
滚动 90 天, 幂等。SHADOW→PAPER 证据链的持续累积器(§94 晋级前置)。
"""
import glob, io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.sequence import run_sequence_v2
from core.entry import fill_in_zone

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
LEDGER = r"E:\test\smc_project\research\handover\setup_engine_paper_ledger.json"
FEE = 0.2
SAMPLE = 10          # 每10只抽1(日常监测口径, 与结构funnel一致)
RECENT = 30

# 1) 更新既有信号结果
led = {"signals": [], "days": 0}
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

# 2) 推进已有未决信号(用最新K线)
n_settled = 0
for sig in led.get("signals", []):
    if sig.get("status") != "OPEN":
        continue
    fp = None
    for suf in ("_SZ", "_SH", "_BJ"):
        p = os.path.join(KL, f"{sig['code']}{suf}_daily_800.json")
        if os.path.exists(p):
            fp = p; break
    if not fp:
        continue
    dd = load_daily(fp)
    n = len(dd)
    i0 = next((k for k, b in enumerate(dd) if b["t"] == sig["date"]), None)
    if i0 is None:
        continue
    # 撮合: 决策点次日起5bar内触 zone_high(STRICT)
    zone = {"zone_low": sig["zone_low"], "zone_high": sig["zone_high"],
            "invalid_price": sig["invalid_price"], "optimal_entry": sig["optimal_entry"]}
    fill = fill_in_zone(dd, i0, zone, max_bars=5, fill_mode="STRICT_LIMIT")
    if fill is None or fill.get("fill_price") is None:
        if fill and fill.get("mode") == "INVALIDATED_BEFORE_FILL":
            sig["status"], sig["ret_pct"] = "INVALIDATED", None
            n_settled += 1
        continue
    fi, fpx = fill["fill_idx"], fill["fill_price"]
    sig["filled_price"], sig["fill_date"] = fpx, dd[fi]["t"]
    atr = 0.02 * fpx
    try:
        from core.structure import atr_of
        a_ = atr_of(dd, fi - 1)
        if a_: atr = a_
    except Exception:
        pass
    slp = sig["invalid_price"] - 1.5 * atr
    # 推进退出
    for k in range(fi + 1, min(n, fi + 16)):
        b = dd[k]
        if b["l"] <= slp:
            sig["status"] = "SL"
            sig["ret_pct"] = round((slp / fpx - 1) * 100 - FEE, 3)
            n_settled += 1
            break
        if k >= min(n - 1, fi + 15):
            sig["status"] = "TIME"
            sig["ret_pct"] = round((b["c"] / fpx - 1) * 100 - FEE, 3)
            n_settled += 1
    if sig.get("status") == "OPEN" and n - 1 > fi + 15:
        sig["status"] = "TIME"
        sig["ret_pct"] = round((dd[min(n - 1, fi + 15)]["c"] / fpx - 1) * 100 - FEE, 3)
        n_settled += 1

# 3) 今日新 READY 信号(最近3根决策点)
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
    for i in range(max(150, n - 3), n):
        if (code, dd[i]["t"]) in seen:
            continue
        m = run_sequence_v2(dd, i, symbol=code)
        s = m.setup()
        if s is None:
            continue
        poi = s["poi"]
        sig = {"code": code, "date": dd[i]["t"], "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "zone_low": poi["low"], "zone_high": poi["high"], "optimal_entry": poi["mid"],
               "invalid_price": poi["low"] * 0.97, "poi_type": poi["type"],
               "sequence": s["sequence"], "status": "OPEN", "ret_pct": None}
        led.setdefault("signals", []).append(sig)
        seen.add((code, dd[i]["t"]))
        n_new += 1

# 4) 汇总
sigs = led.get("signals", [])
closed = [s for s in sigs if s.get("ret_pct") is not None]
avg = round(sum(s["ret_pct"] for s in closed) / len(closed), 3) if closed else None
w = sum(s["ret_pct"] for s in closed if s["ret_pct"] > 0)
l_ = abs(sum(s["ret_pct"] for s in closed if s["ret_pct"] <= 0))
led["summary"] = {"total": len(sigs), "open": len([s for s in sigs if s.get("status") == "OPEN"]),
                  "closed": len(closed), "avg_closed": avg,
                  "pf_closed": round(w / l_, 2) if l_ > 0 else None,
                  "days_accum": led.get("days", 0) + 1, "last_run": today}
json.dump(led, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"新 READY: {n_new}  结算: {n_settled}  台账: total={len(sigs)} closed={len(closed)} "
      f"avg={avg} days={led['summary']['days_accum']}")
print("已写", LEDGER)