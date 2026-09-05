# -*- coding: utf-8 -*-
"""逐笔 K 线标注图：标买入点/TP/SL/实际卖出点/信号组合（SMC 腿案例）"""
import io, json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import datetime as _dt
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT_DIR = r"E:\test\smc_project\research\handover\kline_charts"
os.makedirs(OUT_DIR, exist_ok=True)

# 案例：symbol, entry_date, 标注文本
CASES = [
    {"symbol": "920006.BJ", "entry_date": "20241016", "tag": "best_+57_TP"},
    {"symbol": "300561.SZ", "entry_date": "20240703", "tag": "worst_-34_SL"},
    {"symbol": "300717.SZ", "entry_date": "20240611", "tag": "early_exit_MFE7.8R"},
]

KLINE = r"E:\test\smc_project\hermes\kline_cache"
code2file = {f.split("_")[0]: os.path.join(KLINE, f) for f in os.listdir(KLINE) if f.endswith("_daily_750.json")}

def load_daily(path):
    raw = json.load(open(path, encoding="utf-8"))
    bs = []
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    bs.sort(key=lambda b: b["t"])
    return bs

# 读 seeds 拿锚点
import csv
seeds = list(csv.DictReader(open(r"E:\test\smc_project\wdh\W1D1D4_seeds.csv", encoding="utf-8-sig")))
seed_by_key = {(s["symbol"], s["entry_date"]): s for s in seeds}

def parse_date(t):
    return _dt.datetime.strptime(str(t)[:8], "%Y%m%d")

for c in CASES:
    sym, edate, tag = c["symbol"], c["entry_date"], c["tag"]
    code = sym.split(".")[0]
    path = code2file.get(code)
    if not path or not os.path.exists(path):
        print(f"skip {sym}: no kline")
        continue
    daily = load_daily(path)
    sd = seed_by_key.get((sym, edate))
    if not sd:
        print(f"skip {sym}: no seed")
        continue
    entry_idx = int(sd["entry_idx"])
    ep = float(sd["entry_price"])
    zone_low = float(sd["zone_low"])
    sweep_low = float(sd.get("sweep_low") or 0)
    sl_base = min(zone_low, sweep_low) if sweep_low else zone_low
    sl = sl_base * 0.99
    tgt = float(sd.get("weekly_target") or sd.get("target") or 0)
    risk = ep - sl
    tgt = max(tgt, ep + 1.5 * risk)
    # 时间窗口：entry 前 15 根 到 后 hold+5 根
    start = max(0, entry_idx - 15)
    end = min(len(daily), entry_idx + 20)
    win = daily[start:end]
    dates = [parse_date(b["t"]) for b in win]
    # 找实际卖出（重放）
    import sys as _sys
    _sys.path.insert(0, r"E:\test\smc_project\research")
    import core.execution as EX
    r = EX.simulate(daily, entry_idx, ep, sl, tp2=tgt, max_hold=12)
    exit_idx = None
    if not r.get("skipped"):
        # 定位卖出日
        for k in range(entry_idx + 1, min(len(daily), entry_idx + 13)):
            bb = daily[k]
            if r["reason"] in ("SL_GAP",) and bb["o"] < sl:
                exit_idx = k; break
            if r["reason"] == "SL_HIT" and (bb["l"] <= sl or (bb["h"] >= tgt and bb["l"] <= sl)):
                exit_idx = k; break
            if r["reason"] == "TP_STRUCTURAL" and bb["h"] >= tgt:
                exit_idx = k; break
            if r["reason"] == "TIME_STOP" and (k - entry_idx) >= 12:
                exit_idx = k; break
    # 画图（英文标注，兼容 DejaVu 字体）
    fig, ax = plt.subplots(figsize=(14, 6))
    for i, b in enumerate(win):
        x = dates[i]
        color = "#f85149" if b["c"] >= b["o"] else "#3fb950"
        ax.plot([x, x], [b["l"], b["h"]], color=color, lw= 0.8)
        ax.plot([x, x], [b["o"], b["c"]], color=color, lw= 3.0)
    ax.axhline(ep, color="#f0883e", lw=1.2, ls="--", label="BUY %.2f" % ep)
    ax.axhline(sl, color="#f85149", lw=1.2, ls="--", label="SL %.2f" % sl)
    ax.axhline(tgt, color="#3fb950", lw=1.2, ls="--", label="TP %.2f (%.2fR)" % (tgt, (tgt - ep) / risk if risk > 0 else 0))
    # 标注买卖点
    ep_idx = entry_idx - start
    if 0 <= ep_idx < len(dates):
        ax.annotate("BUY %.2f\n%s" % (ep, edate), xy=(dates[ep_idx], ep), xytext=(dates[ep_idx], ep * 0.95),
                    arrowprops=dict(arrowstyle="->", color="#f0883e"), fontsize=9, color="#f0883e")
    if exit_idx is not None:
        ex_i = exit_idx - start
        if 0 <= ex_i < len(dates):
            ax.annotate("SELL %s @%.2f" % (r["reason"], r["exit_price"]), xy=(dates[ex_i], r["exit_price"]),
                        xytext=(dates[ex_i], r["exit_price"] * 0.9),
                        arrowprops=dict(arrowstyle="->", color="#58a6ff"), fontsize=9, color="#58a6ff")
    # 信号时间标注（英文）
    sig_map = {"SWEEP": sd.get("sweep_date"), "OB": sd.get("ob_date"), "POI": sd.get("touch_date"), "RECLAIM": sd.get("reclaim_date")}
    for label, dt8 in sig_map.items():
        if not dt8:
            continue
        for i, b in enumerate(win):
            if b["t"] == str(dt8)[:8]:
                ax.annotate(label, xy=(dates[i], daily[start + i]["h"] * 1.01),
                            fontsize=8, color="#d29922", rotation=45, ha="center")
                break
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_title("%s %s | %s | %s pnl=%s%%" % (sym, edate, tag, r["reason"], r.get("net_pnl_pct") if r.get("net_pnl_pct") is not None else "skip"))
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "%s_%s.png" % (sym, edate))
    plt.savefig(out, dpi=120)
    plt.close()
    print("saved %s" % out)
