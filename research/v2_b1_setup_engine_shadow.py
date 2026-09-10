# -*- coding: utf-8 -*-
"""F6/B1: 统一 Setup Engine SHADOW 首跑(第三轮深审 B1)
假设(单一): 生产链的 R20/Stage/FVG 硬门对新引擎 READY 候选的过滤, 会挡掉
  结构链完整但"早期"(尚在 Discount/未 UPTREND)的候选 —— 即深审 §58 战略冲突。
方法: 新引擎完整链(run_sequence_v2)扫 OOS 全市场抽样 → 每个 READY 决策点:
  a) 记录旧生产门(R20<15 拒 / Stage∉{UPTREND,MARKUP} 拒 / 近12bar FVG 无 拒)的通过率
  b) 两条子臂回测: 全 READY vs 仅旧门通过 READY, 同 B3 退出(结构SL宽+15bar时间退出)
  c) 对比 avg/pf —— 判定旧门是"漏杀"还是"误杀"
判定线(预注册): 全 READY OOS avg > 旧门通过 READY OOS avg + 1.0pp → 旧门误杀早期候选;
  反之旧门通过更好 → 旧门仍是有效准入; 差 < 1pp → 中性。
只读实验: 不动生产/registry。"""
import glob, io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.sequence import run_sequence_v2
from core.entry import fill_in_zone

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20

def stage_of(daily, i):
    """旧生产 Stage 门(简化重实现: 60日收益分位) —— UPTREND/MARKUP=强趋势。"""
    w = daily[max(0, i - 60):i + 1]
    if len(w) < 60:
        return "NA"
    r60 = w[-1]["c"] / w[0]["c"] - 1
    return "UPTREND" if r60 > 0.25 else ("MARKUP" if r60 > 0.10 else "OTHER")

def r20_of(daily, i):
    w = daily[max(0, i - 20):i + 1]
    return (w[-1]["c"] / w[0]["c"] - 1) * 100 if len(w) >= 20 else 0.0

def fvg_fresh(daily, i, bars=12):
    """旧生产门: 近12bar内存在 FVG。"""
    from core.fvg_ob import fvg_at
    return any(fvg_at(daily, k) for k in range(max(0, i - bars), i + 1))

files = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::5][:800]
arm_all, arm_gate = [], []     # (date, ret)
gate_stats = {"ready": 0, "pass_r20": 0, "pass_stage": 0, "pass_fvg": 0, "pass_all": 0}
t0 = time.time()

for fp in files:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if len(raw) < 200:
        continue
    code = os.path.basename(fp).split("_")[0]
    daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    n = len(daily)
    for i in range(150, n - 20):
        if daily[i]["t"] < OOS:
            continue
        m = run_sequence_v2(daily, i, symbol=code)
        if m.setup() is None:
            continue
        gate_stats["ready"] += 1
        # 旧生产三门
        ok_r20 = r20_of(daily, i) < 15.0
        ok_stage = stage_of(daily, i) in ("UPTREND", "MARKUP")
        ok_fvg = fvg_fresh(daily, i)
        if ok_r20: gate_stats["pass_r20"] += 1
        if ok_stage: gate_stats["pass_stage"] += 1
        if ok_fvg: gate_stats["pass_fvg"] += 1
        passes_all = ok_r20 and ok_stage and ok_fvg
        if passes_all:
            gate_stats["pass_all"] += 1
        # 回测(两条臂共用退出): entry=retest bar 次日, SL=invalid-1.5ATR宽, 15bar时间退出
        setup = m.setup()
        poi = setup["poi"]
        zone = {"zone_low": poi["low"], "zone_high": poi["high"], "invalid_price": poi["low"] * 0.97,
                "optimal_entry": poi["mid"]}
        fill = fill_in_zone(daily, i, zone, max_bars=5, fill_mode="STRICT_LIMIT")
        if fill is None or fill.get("fill_price") is None:
            continue
        fi = fill["fill_idx"]
        atr = 0.02 * fill["fill_price"]
        try:
            from core.structure import atr_of
            a_ = atr_of(daily, fi - 1)
            if a_: atr = a_
        except Exception:
            pass
        fill_px = fill["fill_price"]
        sl = zone["invalid_price"] - 1.5 * atr
        ret = None
        for k in range(fi + 1, min(n, fi + 16)):
            b = daily[k]
            if b["l"] <= sl:
                ret = (sl / fill_px - 1) * 100 - FEE
                break
            if k == min(n - 1, fi + 15):
                ret = (b["c"] / fill_px - 1) * 100 - FEE
        if ret is None:
            continue
        arm_all.append((daily[i]["t"], ret))
        if passes_all:
            arm_gate.append((daily[i]["t"], ret))

def stats(pnl):
    oos = [p for d, p in pnl if d >= OOS]
    if not oos:
        return {"n": 0}
    w = sum(x for x in oos if x > 0); l_ = abs(sum(x for x in oos if x <= 0))
    return {"n": len(oos), "avg": round(sum(oos) / len(oos), 3),
            "pf": round(w / l_, 2) if l_ > 0 else 99.0}

s_all, s_gate = stats(arm_all), stats(arm_gate)
delta = round(s_all.get("avg", 0) - s_gate.get("avg", 0), 3) if s_all.get("avg") is not None and s_gate.get("avg") is not None else None
verdict = ("旧门误杀早期候选(全READY显著更优)" if delta is not None and delta > 1.0
           else ("旧门仍有效(门内更优)" if delta is not None and delta < -1.0 else "中性/样本不足"))

out = {"gate_pass_rates": {k: round(v / gate_stats["ready"], 3) for k, v in gate_stats.items() if k != "ready"},
       "ready_total": gate_stats["ready"],
       "arm_all_READY": s_all, "arm_旧门通过": s_gate, "delta_avg_pp": delta,
       "verdict": verdict, "runtime_s": round(time.time() - t0)}
print("READY 总数:", gate_stats["ready"])
print("门通过率:", out["gate_pass_rates"])
print("全 READY臂:", s_all)
print("旧门通过臂:", s_gate)
print(f"Δavg = {delta}pp → {verdict}")
json.dump(out, open(r"E:\test\smc_project\research\handover\B1_统一SetupEngine_SHADOW.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/B1_统一SetupEngine_SHADOW.json")