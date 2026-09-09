# -*- coding: utf-8 -*-
"""事件腿 SL 收紧实验(归因驱动): LOSS_SL_TOO_WIDE 占 50.4% 亏损贡献。
单一假设: 事件腿 SL 离场过远(>3×ATR), 收紧到结构位(前低/ATR缓冲)可压缩亏损贡献而不伤赢家。

方法(逐笔重放, 无前视):
  基线 = CSV 原始 net(生产 SL 语义)
  实验臂 = 对每笔重放: entry 次日开盘买, SL=max(结构位=披露日前5根最低低×(1-0.5×ATR%), 原SL的0.6),
           TP/时间退出与生产同语义(TP1/TP2/TP3/15根/SL_GAP)
  对照统计: 亏损单 SL 距离分布 + 收紧后 WR/avg/PF + 赢家是否被误伤(被提前打掉的盈利单重放)
简化重放注意: CSV 无逐笔 SL 事件序列, 重放用 K 线近似 —— 结果是方向性证据非生产结论。
"""
import csv, glob, io, json, os, sys
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20
HOLD = 15

rows = [r for r in csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]

kl_cache = {}
def load_daily(code):
    if code in kl_cache:
        return kl_cache[code]
    fp = None
    for suffix in ("_SZ", "_SH", "_BJ", ""):
        p = KL + os.sep + code + suffix + "_daily_800.json"
        if os.path.exists(p):
            fp = p
            break
    if fp is None:
        kl_cache[code] = None
        return None
    raw = json.load(open(fp, encoding="utf-8"))
    daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    kl_cache[code] = daily
    return daily

def sim(daily, i_entry, sl_pct, use_struct_sl):
    """重放: i_entry=入场bar(次日开盘买), sl_pct=SL距入场%数; use_struct_sl=True 用结构位。"""
    if i_entry + 1 >= len(daily) or i_entry + HOLD + 1 >= len(daily):
        return None
    px = daily[i_entry + 1]["o"]
    if px <= 0:
        return None
    # ATR% (入场点)
    trs = []
    for k in range(max(1, i_entry - 13), i_entry + 1):
        trs.append(max(daily[k]["h"] - daily[k]["l"],
                       abs(daily[k]["h"] - daily[k-1]["c"]),
                       abs(daily[k]["l"] - daily[k-1]["c"])))
    atr_abs = sum(trs) / len(trs) if trs else px * 0.025
    if use_struct_sl:
        struct_low = min(b["l"] for b in daily[max(0, i_entry-4):i_entry+1])
        sl_px = min(struct_low * (1 - 0.005), px * (1 - sl_pct/100))  # 结构位与原SL取更近
        sl_pct_eff = (px - sl_px) / px * 100
    else:
        sl_pct_eff = sl_pct
    sl_px_eff = px * (1 - sl_pct_eff/100)
    for k in range(i_entry + 1, min(len(daily), i_entry + HOLD + 1)):
        b = daily[k]
        if b["l"] <= sl_px_eff:  # SL优先(保守)
            return -(sl_pct_eff) - FEE, "SL"
    sell = daily[min(len(daily)-1, i_entry + HOLD)]["c"]
    return (sell / px - 1) * 100 - FEE, "TIME"

# 对照: CSV原值 vs 重放基线(原SL%) vs 结构位收紧臂
import collections
arm_base, arm_tight = [], []
sl_dists = []
for r in rows:
    code = r["symbol"].split(".")[0]
    daily = load_daily(code)
    if not daily:
        continue
    d8 = r["entry_date"]
    tidx = {b["t"]: k for k, b in enumerate(daily)}
    # CSV buy_date=买入bar的开盘日 → i_buy是该bar; 决策bar=前一根
    i_buy = tidx.get(r.get("buy_date") or d8)
    if i_buy is None or i_buy < 15:
        continue
    i_entry = i_buy - 1  # 决策bar(收盘后发单)
    ep = float(r.get("buy_price") or 0)
    slp = float(r.get("sl") or 0)
    if ep <= 0 or slp <= 0:
        continue
    sl_pct = (ep - slp) / ep * 100
    sl_dists.append(sl_pct)
    p_base, _ = sim(daily, i_entry, sl_pct, use_struct_sl=False)
    p_tight, _ = sim(daily, i_entry, sl_pct, use_struct_sl=True)
    if p_base is None or p_tight is None:
        continue
    arm_base.append((code, d8, p_base))
    arm_tight.append((code, d8, p_tight))

sl_dists.sort()
print(f"重放对: {len(arm_base)} | SL距离分布: p25={sl_dists[len(sl_dists)//4]:.2f}% p50={sl_dists[len(sl_dists)//2]:.2f}% p75={sl_dists[3*len(sl_dists)//4]:.2f}% >7.5%(3ATR)占比={sum(1 for x in sl_dists if x>7.5)/len(sl_dists)*100:.1f}%")

def stats(arm, oos):
    sel = [p for c, d, p in arm if (d >= OOS) == oos]
    if not sel:
        return {"n": 0}
    w = [x for x in sel if x > 0]
    l_ = [x for x in sel if x <= 0]
    return {"n": len(sel), "avg": round(sum(sel)/len(sel), 3), "wr": round(len(w)/len(sel), 3),
            "pf": round(sum(w)/abs(sum(l_)), 2) if l_ else 99}

print("\n== SL收紧 A/B(逐笔重放) ==")
for name, arm in (("基线(原SL)", arm_base), ("结构位收紧", arm_tight)):
    print(f"  {name}: IS={stats(arm, False)} OOS={stats(arm, True)}")

# 误伤分析: 原CSV盈利单在收紧臂变成SL被打
csv_net = {(r["symbol"], r["entry_date"]): float(r["net_pnl_pct"]) for r in rows}
hurt = [(c, d, pb, pt) for (c, d, pb), (c2, d2, pt) in zip(arm_base, arm_tight)
        if csv_net.get((c + ".SH", d)) is None and False]
base_pos_tight_neg = sum(1 for (c, d, pb), (c2, d2, pt) in zip(arm_base, arm_tight) if pb > 3 and pt < 0)
base_pos = sum(1 for (c, d, pb) in arm_base if pb > 3)
print(f"\n赢家误伤: 大赢家(基线>+3%) {base_pos} 笔中 {base_pos_tight_neg} 笔被收紧SL提前打掉 ({base_pos_tight_neg/max(1,base_pos)*100:.0f}%)")

json.dump({"sl_dist_percentiles": {"p25": round(sl_dists[len(sl_dists)//4],2), "p50": round(sl_dists[len(sl_dists)//2],2),
                                     "p75": round(sl_dists[3*len(sl_dists)//4],2)},
           "base_oos": stats(arm_base, True), "tight_oos": stats(arm_tight, True),
           "base_is": stats(arm_base, False), "tight_is": stats(arm_tight, False),
           "winners_hurt": base_pos_tight_neg, "winners_big": base_pos},
          open(r"E:\test\smc_project\research\handover\事件腿SL收紧实验.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/事件腿SL收紧实验.json")