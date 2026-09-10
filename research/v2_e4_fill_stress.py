# -*- coding: utf-8 -*-
"""E4 Fill 压力测试(第三轮深审): 事件腿 1640 笔 × 三成交模型 × 滑点网格
模型(严格→宽):
  STRICT_LIMIT: retrace 价(披露日收盘×0.99)必须被触及才成交(fill@limit), 未触=放弃;
               T+1 开盘 fallback=无(严格)。注: 事件腿生产语义是 retrace-or-open —— 本臂
               只保留触价部分, 衡量"纯限价单"下的样本与收益。
  LIMIT_OR_OPEN(生产现状): 触价成交@limit, 否则 T+1 开盘成交(带滑点)。
  MARKET_OPEN: 一律 T+1 开盘成交(带滑点)。
滑点: 0.05% / 0.10% / 0.20% / 0.30%。
判定: 若仅在宽松模型+低滑点下 avg>0 且 STRICT 大幅衰减 → 执行幻觉警报。
重放用 gen_v20f 同源数据(K线), exit 语义固定 15 日收盘-费(单一变量=成交模型)。"""
import csv, glob, io, json, os, sys
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20

rows = [r for r in csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]

kl_cache = {}
def load_daily(code):
    if code in kl_cache:
        return kl_cache[code]
    fp = None
    for suffix in ("_SZ", "_SH", "_BJ"):
        p = KL + os.sep + code + suffix + "_daily_800.json"
        if os.path.exists(p):
            fp = p; break
    daily = None
    if fp:
        raw = json.load(open(fp, encoding="utf-8"))
        daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
                  "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    kl_cache[code] = daily
    return daily

MODELS = ("STRICT_LIMIT", "LIMIT_OR_OPEN", "MARKET_OPEN")
SLIPS = (0.05, 0.10, 0.20, 0.30)
results = {}
for model in MODELS:
    for slip in SLIPS:
        fills, pnl = 0, []
        for r in rows:
            code = r["symbol"].split(".")[0]
            daily = load_daily(code)
            if not daily:
                continue
            tidx = {b["t"]: k for k, b in enumerate(daily)}
            i_buy = tidx.get(r.get("buy_date") or r["entry_date"])
            if i_buy is None or i_buy + 16 >= len(daily):
                continue
            b_prev = daily[i_buy - 1]
            limit_px = round(b_prev["c"] * 0.99, 3)
            b = daily[i_buy]
            if model == "STRICT_LIMIT":
                if b["l"] > limit_px:   # 未触价 → 放弃
                    continue
                fill_px = limit_px * (1 + slip / 100)
                fills += 1
            elif model == "LIMIT_OR_OPEN":
                if b["l"] <= limit_px:
                    fill_px = limit_px * (1 + slip / 100)
                else:
                    fill_px = b["o"] * (1 + slip / 100)
                fills += 1
            else:  # MARKET_OPEN
                fill_px = b["o"] * (1 + slip / 100)
                fills += 1
            sell = daily[min(len(daily) - 1, i_buy + 15)]["c"]
            pnl.append((r["entry_date"], (sell / fill_px - 1) * 100 - FEE))
        oos = [p for d, p in pnl if d >= OOS]
        al = [p for d, p in pnl]
        w = [x for x in oos if x > 0]; l_ = [x for x in oos if x <= 0]
        results[f"{model}@{slip}"] = {
            "n": fills, "fill_rate": round(fills / len(rows), 3),
            "all_avg": round(sum(al) / len(al), 3) if al else None,
            "oos_n": len(oos), "oos_avg": round(sum(oos) / len(oos), 3) if oos else None,
            "oos_pf": round(sum(w) / abs(sum(l_)), 2) if l_ and sum(l_) != 0 else 99}
        v = results[f"{model}@{slip}"]
        print(f"  {model:14s}@{slip:.2f}%: fill={v['fill_rate']:.0%} n={v['n']:4d} OOS avg={v['oos_avg']} PF={v['oos_pf']}")

# 执行幻觉判定: STRICT vs MARKET 的 OOS avg 差 + 全部模型 OOS>0
strict_best = results["STRICT_LIMIT@0.05"]["oos_avg"]
market_worst = results["MARKET_OPEN@0.3"]["oos_avg"]
all_positive = all(results[f"{m}@{s}"]["oos_avg"] is not None and results[f"{m}@{s}"]["oos_avg"] > 0
                   for m in MODELS for s in SLIPS)
verdict = {"strict_minus_market30": round(strict_best - market_worst, 3),
           "all_models_oos_positive": all_positive,
           "execution_illusion_risk": (not all_positive) or (strict_best - market_worst > 1.5)}
out = {"results": results, "verdict": verdict}
print(f"\n== E4 判定 ==")
print(f"  全模型 OOS>0: {all_positive}")
print(f"  STRICT@0.05 - MARKET@0.30 = {strict_best - market_worst:.3f}pp")
print(f"  → 执行幻觉风险: {verdict['execution_illusion_risk']}")

json.dump(out, open(r"E:\test\smc_project\research\handover\E4_Fill压力测试.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/E4_Fill压力测试.json")