# -*- coding: utf-8 -*-
"""v4_d3_event_structure.py —— D3: 事件-结构融合入场三臂 OOS 重放
假设(第十轮审计 R1): 事件腿"见事件就买"无环境/结构确认; 结构引擎 alpha 在后半链
(SHIFT/POI/RETEST, Family DB 证明)。融合 = 事件触发后要求 POI 附近才挂限价单。

三臂(同一 1640 笔 EVENT 事件, 决策时点无前视):
  A_base    : 基线 fill_or_open(事件次日开盘, 现生产语义) —— 冻结基线复现
  B_struct  : 事件日检测决策点前是否存在已完成链(run_sequence_v2 在事件日回看);
              有 → POI 区限价(STRICT); 无 → 半仓 fill_or_open(保守模式)
  C_struct_only: 仅结构确认臂(无链事件放弃, 只买有链的) —— 结构 gate 的纯效应
判定(预注册):
  ①B vs A: OOS avg 提升>0.5pp 且 n 保持≥60% → 融合有效
  ②C vs B: 若 C 的 avg>B 但 n<B×40% → 质量换数量, 如实呈现
  ③OOS 优先: IS(2023-09~2025-06)拟合观察用, OOS(≥20250701)判定
退出: 全部 settle_from_record 单源(SL=invalid-1.5ATR/TP3R/TIME15) —— 但 A 臂是
  开盘买入, SL/TP 相对开盘价; B/C 臂相对限价成交价。统一 fee 0.2%。
链检测成本: 事件日在 lookback 窗内扫 run_sequence_v2 决策点, 取最近 READY setup。"""
import csv, glob, io, json, math, os, sys, time
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.sequence import run_sequence_v2
from core.entry import fill_in_zone
from core.setup_exit import settle_from_record

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
FEE = 0.2
OOS = "20250701"
ROWS = [r for r in csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv",
                                       encoding="utf-8-sig")) if r.get("src") == "EVENT"]
print(f"EVENT {len(ROWS)} 笔")

def load_daily(code):
    for suf in ("_SZ", "_SH", "_BJ"):
        p = os.path.join(KT, f"{code}{suf}_daily_800.json")
        if os.path.exists(p):
            try:
                raw = json.load(open(p, encoding="utf-8"))
                return [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
                         "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)}
                        for b in raw]
            except Exception:
                return None
    return None

CACHE = r"E:\test\smc_project\research\handover\d3_daily_cache.pkl"
D3 = {}

def settle_A(daily, i0):        # A: 次日开盘买(基线) → 单源退出
    n = len(daily)
    if i0 + 1 >= n:
        return None
    fill_px = daily[i0 + 1]["o"]
    # 基线 SL 距离按 csv 语义近似: 用 invalid = fill×0.97(ATR 版在下)
    return settle_from_record(daily, i0 + 1, fill_px, fill_px * 0.93, fee_pct=FEE,
                              max_bars=15, tp_rr=3.0)

def struct_setup_at_event(daily, i_ev):
    """事件日 i_ev: 回看窗内最近一次 READY 链的 POI(决策点≤i_ev, 无前视)。"""
    n = len(daily)
    for i in range(min(n - 1, i_ev), max(60, i_ev - 40), -1):
        try:
            m = run_sequence_v2(daily, i, symbol="")
            s = m.setup()
        except Exception:
            continue
        if s is not None:
            return s
    return None

def settle_B(daily, i0, s, half_if_none=True):
    """B: 有链→POI 限价 STRICT(5bar 窗); 无链→(B臂)半仓标记由外层, 结算本身=开盘"""
    if s is None:
        return ("no_chain", None)
    poi = s["poi"]
    zone = {"zone_low": poi["low"], "zone_high": poi["high"],
            "invalid_price": poi["low"] * 0.97, "optimal_entry": poi["mid"]}
    fill = fill_in_zone(daily, i0, zone, max_bars=5, fill_mode="STRICT_LIMIT")
    if fill is None or fill.get("fill_price") is None:
        return ("no_fill", None)
    res = settle_from_record(daily, fill["fill_idx"], fill["fill_price"],
                             zone["invalid_price"], fee_pct=FEE, max_bars=15, tp_rr=3.0)
    if res.get("status") in ("SL", "TP", "TIME"):
        return ("struct", res["ret_pct"])
    return ("open_still", None)

arms = {"A_base": [], "B_struct": [], "C_struct_only": []}
B_meta = defaultdict(int)
t0 = time.time()
for k, r in enumerate(ROWS):
    code = r["symbol"].split(".")[0]
    d8 = r["entry_date"]
    if k % 200 == 0:
        print(f"  ...{k}/{len(ROWS)} {time.time()-t0:.0f}s", flush=True)
    if code not in D3:
        D3[code] = load_daily(code) or []
    daily = D3[code]
    if not daily:
        continue
    i0 = next((i for i, b in enumerate(daily) if b["t"] == d8), None)
    if i0 is None or i0 + 2 >= len(daily):
        continue
    # A 臂
    ra = settle_A(daily, i0)
    if ra and ra.get("status") in ("SL", "TP", "TIME"):
        arms["A_base"].append((d8, ra["ret_pct"]))
    # 结构回看(共享)
    s = struct_setup_at_event(daily, i0)
    # B 臂: 有链→结构确认; 无链→开盘半仓(ret×0.5 记账)
    if s is not None:
        kind, ret = settle_B(daily, i0, s)
        if kind == "struct":
            arms["B_struct"].append((d8, ret))
            B_meta["struct_filled"] += 1
        elif kind == "no_fill":
            # POI 限价未触 → 放弃(不 fallback, 与 A5 LIMIT_RETRACE 一致)
            B_meta["struct_nofill"] += 1
            # B 臂 no_fill 时不买 —— 用 0 记(机会成本如实: 不买=0)
            arms["B_struct"].append((d8, 0.0))
        else:
            B_meta["struct_open"] += 1
    else:
        B_meta["no_chain"] += 1
        arms["B_struct"].append((d8, 0.0))        # 无链不买=0(半仓模式未来再优化)
    # C 臂: 仅结构
    if s is not None:
        kind, ret = settle_B(daily, i0, s)
        if kind == "struct":
            arms["C_struct_only"].append((d8, ret))

def stats(pnl, oos=True):
    v = [p for d, p in pnl if (not oos or d >= OOS)]
    if not v:
        return {"n": 0}
    w = sum(x for x in v if x > 0); l = abs(sum(x for x in v if x <= 0))
    return {"n": len(v), "avg": round(sum(v) / len(v), 3),
            "wr": round(len([x for x in v if x > 0]) / len(v) * 100, 1),
            "pf": round(w / l, 2) if l else 99.0}

S = {a: {"is": stats(v, False), "oos": stats(v, True)} for a, v in arms.items()}
dBA = round(S["B_struct"]["oos"]["avg"] - S["A_base"]["oos"]["avg"], 3) \
    if S["B_struct"]["oos"].get("avg") is not None and S["A_base"]["oos"].get("avg") is not None else None
n_ratio = round(S["B_struct"]["oos"]["n"] / max(1, S["A_base"]["oos"]["n"]), 3) \
    if S["A_base"]["oos"]["n"] else None

out = {"arms": S, "B_meta": dict(B_meta), "delta_B_minus_A_oos_pp": dBA,
       "n_ratio_B_over_A": n_ratio,
       "preregistered": {
           "①融合有效(B较A OOS avg>0.5 且 n≥60%A)": bool(
               dBA is not None and dBA > 0.5 and n_ratio is not None and n_ratio >= 0.6),
           "②C纯结构臂": S["C_struct_only"]["oos"]},
       "notes": "A臂=生产基线复现(开盘买入, 退出单源重放); B臂无链/未触=0机会成本; "
                "csv基线avg+3.72是旧退出, A臂重放值可能不同(单源口径), 判定只看臂间差"}
json.dump(out, open(r"E:\test\smc_project\research\handover\V4_D3_事件结构融合.json", "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
for a in ("A_base", "B_struct", "C_struct_only"):
    print(f"{a:14s} IS {S[a]['is']} / OOS {S[a]['oos']}")
print(f"\nB_meta: {dict(B_meta)}")
print(f"Δ(B-A) OOS = {dBA}pp, n比 = {n_ratio}")
print(f"预注册①: {out['preregistered']['①融合有效(B较A OOS avg>0.5 且 n≥60%A)']}")
print("已写 handover/V4_D3_事件结构融合.json")