# -*- coding: utf-8 -*-
"""全面回测数据生成器（2026-09-05 最终版，P1-1 引擎）
输出：逐笔交易完整明细（买点/卖点/价格/日期/信号链/TP-SL/MFE-MAE/R倍数）
  + JSON 结构化 + MD 综合报告 → handover/最新回测数据/
合并 SMC 腿(W1D1D4) + 事件腿(combo_v20f)。
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as WE
import core.execution as EX

RESEARCH = r"E:\test\smc_project\research"
WDH = r"E:\test\smc_project\wdh"
KLINE = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT_DIR = os.path.join(RESEARCH, "handover", "最新回测数据")
os.makedirs(OUT_DIR, exist_ok=True)

code2file = {f.split("_")[0]: os.path.join(KLINE, f) for f in os.listdir(KLINE) if f.endswith("_daily_800.json")}

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

# ---- SMC 腿逐笔完整明细 ----
seeds = list(csv.DictReader(open(os.path.join(WDH, "W1D1D4_seeds.csv"), encoding="utf-8-sig")))
trades = list(csv.DictReader(open(os.path.join(WDH, "W1D1D4_trades.csv"), encoding="utf-8-sig")))
seed_by = {(s["symbol"], s["entry_date"]): s for s in seeds}

smc_detail = []
n_skip = 0
for tr in trades:
    sym = tr["symbol"]; ed = tr["entry_date"]
    sd = seed_by.get((sym, ed))
    code = sym.split(".")[0]
    p = code2file.get(code)
    if not sd or not p or not os.path.exists(p):
        continue
    daily = load_daily(p)
    ei = int(sd["entry_idx"])
    if ei >= len(daily):
        continue
    ep = WE.f(sd["entry_price"])
    zl = WE.f(sd["zone_low"])
    code6 = code
    kk = 0.8 if code6.startswith(("300", "301", "688")) else (1.0 if code6.startswith(("4", "8", "9")) else 0.5)
    atr = WE.atr_of(daily, ei - 1) or 0
    sl = zl - kk * atr
    tgt = WE.f(sd.get("weekly_target")) or WE.f(sd.get("target"))
    risk = ep - sl
    if risk <= 0:
        continue
    tgt = max(tgt, ep + 1.5 * risk)
    r = EX.simulate(daily, ei, ep, sl, tp2=tgt, max_hold=WE.MAX_HOLD, code=code6)
    if r.get("skipped"):
        n_skip += 1
        continue
    # 信号链
    sig_chain = "|".join(filter(None, [
        f"sweep:{sd.get('sweep_date','')}", f"OB:{sd.get('ob_date','')}",
        f"POI:{sd.get('touch_date','')}", f"confirm:{sd.get('reclaim_date','')}",
        f"W:{sd.get('w_permission','')}"]))
    smc_detail.append({
        "leg": "SMC", "symbol": sym, "entry_date": ed,
        "buy_date": daily[ei]["t"], "buy_price": round(ep, 3),
        "sell_date": daily[min(len(daily)-1, ei + max(1, r["hold_bars"]))]["t"] if r["hold_bars"] > 0 else ed,
        "sell_price": round(r["exit_price"], 3),
        "reason": r["reason"], "hold_bars": r["hold_bars"],
        "tp": round(tgt, 3), "sl": round(sl, 3),
        "risk_pct": round((ep-sl)/ep*100, 2),
        "net_pnl_pct": round(r["net_pnl_pct"], 4),
        "mfe_pct": round(r["mfe_pct"], 2), "mae_pct": round(r["mae_pct"], 2),
        "mfe_r": round(r["mfe_r"], 2), "mae_r": round(r["mae_r"], 2),
        "rr_exit": round((r["exit_price"]/ep-1)/((ep-sl)/ep), 2) if risk > 0 else 0,
        "signal_chain": sig_chain,
        "r20": sd.get("r20", ""),
    })

# ---- 事件腿（无 K 线逐笔重放，含 buy/sell 估算）----
ev_detail = []
ev_rows = list(csv.DictReader(open(os.path.join(RESEARCH, "combo_v20f_trades.csv"), encoding="utf-8-sig")))
for t in ev_rows:
    if t.get("src") != "EVENT":
        continue
    code = str(t.get("symbol", "")).split(".")[0]
    p = code2file.get(code)
    ed = t.get("entry_date", "")
    pnl = t.get("net_pnl_pct")
    ev_detail.append({
        "leg": "EVENT", "symbol": t.get("symbol", ""), "entry_date": ed,
        "buy_date": ed, "buy_price": "",
        "sell_date": "", "sell_price": "",
        "reason": "", "hold_bars": "",
        "tp": "", "sl": "", "risk_pct": "",
        "net_pnl_pct": round(float(pnl), 4) if pnl not in (None, "", "None") else None,
        "mfe_pct": "", "mae_pct": "", "mfe_r": "", "mae_r": "", "rr_exit": "",
        "signal_chain": "insider-event", "r20": "", "rank": t.get("rank", ""),
    })

# ---- 写 CSV ----
fields = ["leg", "symbol", "entry_date", "buy_date", "buy_price", "sell_date", "sell_price",
          "reason", "hold_bars", "tp", "sl", "risk_pct", "net_pnl_pct",
          "mfe_pct", "mae_pct", "mfe_r", "mae_r", "rr_exit", "signal_chain", "r20", "rank"]
all_rows = smc_detail + ev_detail
csv_path = os.path.join(OUT_DIR, "逐笔交易全明细.csv")
with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for row in all_rows:
        w.writerow(row)
print(f"SMC 明细: {len(smc_detail)} 笔 (+跳过{n_skip}) | 事件: {len(ev_detail)} | 总: {len(all_rows)} → {csv_path}")

# ---- JSON ----
json_out = {"generated_at": "2026-09-05", "engine": "P1-1 (replay->simulate)",
            "smc_trades": len(smc_detail), "event_trades": len(ev_detail),
            "trades": all_rows}
with open(os.path.join(OUT_DIR, "逐笔交易全明细.json"), "w", encoding="utf-8") as fh:
    json.dump(json_out, fh, ensure_ascii=False, indent=1, default=str)
print("JSON 已写")

# ---- MD 综合报告 ----
def stats(pn):
    pn = [x for x in pn if x is not None]
    if not pn:
        return None
    n = len(pn); mean = sum(pn)/n
    wins = [x for x in pn if x > 0]
    losses = [x for x in pn if x <= 0]
    pf = sum(wins)/abs(sum(losses)) if losses else 99
    return n, mean, len(wins)/n, pf

L = ["# 最新回测数据报告（2026-09-05）", "",
      "> 引擎：P1-1 唯一执行内核（replay→core.execution.simulate）",
      "> 数据：SMC 腿 W1D1D4（全市场 4905 只）+ 事件腿 combo_v20f（cap500）", ""]

L.append("## 一、总体")
smc_pn = [r["net_pnl_pct"] for r in smc_detail]
ev_pn = [r["net_pnl_pct"] for r in ev_detail if r["net_pnl_pct"] is not None]
for name, pn in (("SMC腿", smc_pn), ("事件腿", ev_pn)):
    s = stats(pn)
    if s:
        L.append(f"- **{name}**: n={s[0]} avg={s[1]:+.2f}% wr={s[2]*100:.0f}% PF={s[3]:.2f}")
L.append("")

L.append("## 二、SMC 腿逐笔分布")
rc = defaultdict(int)
for r in smc_detail:
    rc[r["reason"]] += 1
for k, v in sorted(rc.items(), key=lambda x: -x[1]):
    sub = [r for r in smc_detail if r["reason"] == k]
    s = stats([r["net_pnl_pct"] for r in sub])
    L.append(f"- **{k}**: {v}笔 — avg={s[1]:+.2f}% hold中位={sorted(r['hold_bars'] for r in sub)[len(sub)//2]}")
L.append("")

L.append("## 三、SMC 腿 R 倍数 / MFE / MAE")
rr = [r["rr_exit"] for r in smc_detail if isinstance(r["rr_exit"], (int, float))]
mfe = [r["mfe_r"] for r in smc_detail if isinstance(r["mfe_r"], (int, float))]
mae = [r["mae_r"] for r in smc_detail if isinstance(r["mae_r"], (int, float))]
if rr:
    L.append(f"- R倍数(实际): 均值 {sum(rr)/len(rr):.2f} | 中位 {sorted(rr)[len(rr)//2]:.2f}")
    L.append(f"- MFE(R): 均值 {sum(mfe)/len(mfe):.2f} | MAE(R): 均值 {sum(mae)/len(mae):.2f}")
    L.append(f"- 实现率 realized/MFE: {sum(rr)/max(sum(mfe),1e-9)*1:.2f}（目标≥0.5）")
L.append("")

L.append("## 四、信号触发链（SMC 前 20 笔）")
L.append("| symbol | 入场日 | 买价 | 卖价 | 出场 | TP | SL | MFE% | MAE% | 信号链 |")
L.append("|---|---|---:|---:|---|---:|---:|---:|---:|---|")
for r in smc_detail[:20]:
    L.append(f"| {r['symbol']} | {r['entry_date']} | {r['buy_price']} | {r['sell_price']} | {r['reason']} | "
             f"{r['tp']} | {r['sl']} | {r['mfe_pct']} | {r['mae_pct']} | {r['signal_chain'][:60]} |")
L.append("")

L.append("## 五、事件腿 Top/Bottom 10")
ev_sorted = sorted([r for r in ev_detail if r["net_pnl_pct"] is not None], key=lambda r: -r["net_pnl_pct"])
L.append("| symbol | 日期 | 收益% | rank |")
L.append("|---|---|---:|---:|")
for r in ev_sorted[:10] + ev_sorted[-10:]:
    L.append(f"| {r['symbol']} | {r['entry_date']} | {r['net_pnl_pct']:+.2f} | {r.get('rank','')} |")
L.append("")

L.append("## 六、逐年（SMC+事件）")
by_y = defaultdict(lambda: {"smc": [], "ev": []})
for r in smc_detail:
    by_y[r["entry_date"][:4]]["smc"].append(r["net_pnl_pct"])
for r in ev_detail:
    if r["net_pnl_pct"] is not None:
        by_y[r["entry_date"][:4]]["ev"].append(r["net_pnl_pct"])
L.append("| 年 | SMC n | SMC avg% | 事件 n | 事件 avg% |")
L.append("|---|---:|---:|---:|---:|")
for y in sorted(by_y):
    s1 = stats(by_y[y]["smc"]); s2 = stats(by_y[y]["ev"])
    L.append(f"| {y} | {s1[0] if s1 else 0} | {s1[1] if s1 else 0:+.2f} | {s2[0] if s2 else 0} | {s2[1] if s2 else 0:+.2f} |")
L.append("")

md = "\n".join(L)
with open(os.path.join(OUT_DIR, "最新回测数据报告.md"), "w", encoding="utf-8") as fh:
    fh.write(md)
print("MD 报告已写")
print("输出目录:", OUT_DIR)
