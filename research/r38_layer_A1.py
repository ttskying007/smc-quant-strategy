# -*- coding: utf-8 -*-
"""r38_layer_A1.py —— 假设 A1 验证: 缠论结构分层(3买型 vs 下跌中继型).
在冻结基线 1640 笔 EVENT 上, 按入场日结构分类, 比较 avg/PF/WR/RR.
3买型(缠论): 披露日前 40 根内已形成中枢(横向震荡≥2次) → 披露日 close 突破
  中枢上沿 → 入场日回踩低点不破中枢上沿(3买) 或 破后收回(2买+3买重叠)。
下跌中继型: 未形成中枢 / 未突破 / 突破后回踩破中枢上沿(弱势)。
纯研究分层, 不修改生产。"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
bar_cache = {}
def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []; return bar_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                           "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]

def swing_extrema(bs, lo, hi):
    """返回 [lo,hi) 内摆动高/低点索引列表(相邻3根极值)."""
    highs, lows = [], []
    for j in range(max(1, lo), min(hi, len(bs)-1)):
        if bs[j]["h"] > bs[j-1]["h"] and bs[j]["h"] >= bs[j+1]["h"]:
            highs.append(j)
        if bs[j]["l"] < bs[j-1]["l"] and bs[j]["l"] <= bs[j+1]["l"]:
            lows.append(j)
    return highs, lows

def classify_3buy(bs, disp_idx):
    """缠论风格 3买 判定. 返回 ('3BUY'|'2BUY_OVERLAP'|'WEAK_BREAK'|'NO_BREAK', 中枢上沿).
    简化实现: 40根窗内找中枢区间(两低点夹两高点近似矩形震荡), 披露日突破判定. """
    if disp_idx < 45:
        return ("NO_BREAK", 0.0)
    lo, hi = disp_idx - 40, disp_idx
    highs, lows = swing_extrema(bs, lo, hi)
    if len(highs) < 2 or len(lows) < 2:
        return ("NO_BREAK", 0.0)
    # 中枢上沿 ≈ 区间内两个较低高点的均值(保守), 下沿 ≈ 两个较低低点的均值
    hs = sorted(bs[j]["h"] for j in highs)
    ls = sorted(bs[j]["l"] for j in lows)
    # 排除最近突破段: 取前 80% 的摆动点作中枢(避免把突破后新高算进中枢)
    h_cut = hs[max(0, len(hs)//5): len(hs)*4//5] if len(hs) >= 5 else hs
    l_cut = ls[max(0, len(ls)//5): len(ls)*4//5] if len(ls) >= 5 else ls
    if not h_cut or not l_cut:
        return ("NO_BREAK", 0.0)
    zs_top = sum(h_cut) / len(h_cut)      # 中枢上沿
    zs_bot = sum(l_cut) / len(l_cut)      # 中枢下沿
    if zs_top <= zs_bot or (zs_top - zs_bot) / zs_bot > 0.25:  # 中枢过宽=非横向
        return ("NO_BREAK", zs_top)
    disp_close = bs[disp_idx]["c"]
    if disp_close <= zs_top * 1.005:      # 披露日未明显突破中枢上沿
        return ("NO_BREAK", zs_top)
    # 突破后: 入场日(=披露日+1)低点
    entry_idx = disp_idx + 1
    if entry_idx >= len(bs):
        return ("NO_BREAK", zs_top)
    entry_low = bs[entry_idx]["l"]
    if entry_low >= zs_top * 0.995:       # 回踩不破中枢上沿 = 3买
        return ("3BUY", zs_top)
    # 回踩进中枢但未破下沿 = 2买+3买重叠(力度较大)
    if entry_low >= zs_bot * 0.995:
        return ("2BUY_OVERLAP", zs_top)
    return ("WEAK_BREAK", zs_top)         # 跌破中枢下沿 = 假突破/弱势

def stats(ts):
    if not ts: return None
    pnls = [t["net"] for t in ts]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    pf = sum(wins)/abs(sum(losses)) if sum(losses) else 99
    wr = 100*len(wins)/len(pnls)
    rr = [t["rr"] for t in ts if t["rr"] is not None]
    avg_r = sum(rr)/len(rr) if rr else 0
    return dict(n=len(ts), wr=wr, avg=sum(pnls)/len(pnls), med=sorted(pnls)[len(pnls)//2],
                pf=pf, avg_r=avg_r, pnl_sum=sum(pnls))

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
def f(x, d=0.0):
    try: return float(x)
    except: return d

groups = defaultdict(list)
unclass = 0
for r in ev:
    code = r["symbol"].split(".")[0]
    bs = bars_of(code)
    dates = [b["t"] for b in bs]
    buy_date = r.get("buy_date") or r.get("entry_date")
    if buy_date not in dates:
        unclass += 1; continue
    disp_date = r.get("entry_date")
    if disp_date not in dates:
        unclass += 1; continue
    disp_idx = dates.index(disp_date)
    cls, _ = classify_3buy(bs, disp_idx)
    groups[cls].append({"net": f(r["net_pnl_pct"]), "rr": f(r["rr_exit"], None),
                        "sym": code, "d": buy_date, "reason": r.get("reason","")})

print("="*88)
print("假设 A1: 缠论结构分层 (EVENT 腿 n=%d, 未分类=%d)" % (len(ev), unclass))
print("="*88)
print(f"{'类别':<16}{'n':>6}{'胜率':>8}{'平均%':>9}{'中位%':>8}{'PF':>7}{'期望R':>8}{'PnL合计%':>9}")
order = ["3BUY", "2BUY_OVERLAP", "WEAK_BREAK", "NO_BREAK"]
for k in order:
    s = stats(groups.get(k, []))
    if not s: continue
    print(f"{k:<16}{s['n']:>6}{s['wr']:>7.1f}%{s['avg']:>+8.2f}%{s['med']:>+8.2f}%{s['pf']:>7.2f}{s['avg_r']:>8.2f}{s['pnl_sum']:>+9.2f}%")

# 3买型 vs 非3买型 对比(核心检验)
s3 = stats(groups["3BUY"] + groups["2BUY_OVERLAP"])
snon = stats(groups["WEAK_BREAK"] + groups["NO_BREAK"])
print("\n3买型(3BUY+2BUY重叠): n=%d avg=%+.2f%% PF=%.2f WR=%.1f%% 期望R=%.2f" %
      (s3["n"], s3["avg"], s3["pf"], s3["wr"], s3["avg_r"]))
print("非3买型(WEAK+NO):     n=%d avg=%+.2f%% PF=%.2f WR=%.1f%% 期望R=%.2f" %
      (snon["n"], snon["avg"], snon["pf"], snon["wr"], snon["avg_r"]))

# 分年看 3买占比
print("\n分年 3买型占比与质量:")
for y in ("2023", "2024", "2025", "2026"):
    yy = [r for r in ev if str(r.get("entry_date"))[:4] == y]
    if not yy: continue
    y3 = [r for r in yy if classify_3buy(bars_of(r["symbol"].split(".")[0]),
         [b["t"] for b in bars_of(r["symbol"].split(".")[0])].index(r["entry_date"]))[0]
          in ("3BUY", "2BUY_OVERLAP")]
    pct = 100*len(y3)/len(yy)
    s_y3 = stats([{"net": f(r["net_pnl_pct"]), "rr": f(r["rr_exit"], None)} for r in y3])
    print(f"  {y}: 3买型 {pct:.0f}%({len(y3)}/{len(yy)}) avg={s_y3['avg']:+.2f}% PF={s_y3['pf']:.2f}")
