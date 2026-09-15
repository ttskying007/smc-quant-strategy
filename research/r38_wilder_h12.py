# -*- coding: utf-8 -*-
"""r38_wilder_h12.py —— R38 P1-7+P1-8 合并重基线证据包(审计前置, 不动冻结线).

背景:
- P1-7: 冻结基线 gen_v20f 用 legacy 单窗DX, 生产 paper_sim 用 Wilder
  (R38q 已确认 L314-321 兼容入口委托 core.indicators) → 回测/生产口径分叉。
- P1-8: 冻结基线 max_hold=15, 生产 CFG.MAX_HOLD=12 → 第二处分叉。
  R38m 退出扫描: 生产口径(12) OOS PF4.41/MDD-630 最优(全样本 PF3.11 略低)。

本脚本 = gen_v20f 逐行复制 + 两处改动:
  ① adx14 → core.indicators.adx14_of (Wilder)
  ② 同一次扫描内**同时**用 max_hold=15 与 12 跑 simulate(避免两次全市场扫描)

产出:
  r38_combo_wilder_h15_trades.csv  (仅 Wilder)
  r38_combo_wilder_h12_trades.csv  (Wilder + max_hold=12, = 生产口径)
  控制台对比: 两口径 vs 冻结基线(combo_v20f_trades.csv)

审计约束: 本脚本是**研究分叉**; 若采纳需走完整审计(全测试链+冻结基线重认定),
不得直接修改 gen_v20f.py。
"""
import csv, io, json, os, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.events import classify_title
from core.indicators import adx14_of as wilder_adx
from core.execution import simulate as _sim

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
HERE = r"E:\test\smc_project\research"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
bar_cache = {}
def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []
            return bar_cache[code]
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

def is_strong(title):
    is_ev, kind, pol, _amt, _pct = classify_title(title)
    return bool(is_ev and pol > 0)

def stage_of(bs, i):
    if i < 91:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
    v60 = sum(b["v"] for b in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"

def build_row(bs, i, entry_idx, ep, sl1, tp1, tp2, tp3, code, d8, st, max_hold):
    r = _sim(bs, entry_idx, ep, sl1, tp1=tp1, tp2=tp2, tp3=tp3,
             partial_tp1=0.3, stop_to_be=True, max_hold=max_hold, code=code[:6])
    if r.get("skipped"):
        return None
    risk = ep - sl1
    hb = r.get("hold_bars", 0)
    sell_i = min(len(bs) - 1, entry_idx + max(1, hb)) if hb else entry_idx
    return {
        "symbol": code + (".SH" if code.startswith("6") else ".SZ"), "entry_date": bs[entry_idx]["t"],
        "src": "EVENT", "buy_date": bs[entry_idx]["t"], "buy_price": round(ep, 3),
        "sell_date": bs[sell_i]["t"] if hb else "",
        "sell_price": round(r.get("exit_price", 0), 3) if hb else "",
        "reason": r.get("reason", ""), "hold_bars": hb,
        "tp": round(tp2, 3), "sl": round(sl1, 3),
        "risk_pct": round(risk / ep * 100, 3) if risk > 0 else 0,
        "net_pnl_pct": round(r.get("net_pnl_pct", 0.0), 4),
        "mfe_pct": r.get("mfe_pct", 0), "mae_pct": r.get("mae_pct", 0),
        "mfe_r": r.get("mfe_r", 0), "mae_r": r.get("mae_r", 0),
        "rr_exit": round((r.get("exit_price", ep) / ep - 1) / (risk / ep), 3) if risk > 0 else 0,
        "signal_chain": "insider-event", "r20": "", "rank": 0, "stage": st,
    }

ev15, ev12 = [], []
seen = set()
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for date, code, title in cur.fetchall():
    if not is_strong(title):
        continue
    d = str(date)[:10].replace("-", "")
    if (code, d) in seen:
        continue
    seen.add((code, d))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if d not in dates:
        continue
    i = dates.index(d)
    st = stage_of(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = wilder_adx(bs, i)          # ← P1-7: Wilder(生产口径)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 17 >= len(bs) or entry_idx < 130:
        continue
    if bs[entry_idx]["t"] < "20230901":
        continue
    ep_open = bs[entry_idx]["o"]
    disc_close = bs[i]["c"]
    if ep_open <= 0:
        continue
    highs, lows = [], []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(highs) < 2 and bs[j]["h"] > max(bs[k]["h"] for k in range(j-3, j)) \
           and bs[j]["h"] >= max(bs[k]["h"] for k in range(j+1, j+4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j-3, j)) \
           and bs[j]["l"] <= min(bs[k]["l"] for k in range(j+1, j+4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 2 and len(lows) >= 2:
            break
    if not highs or not lows:
        continue
    highs.sort()
    limit = disc_close * 0.99
    ep = limit if bs[entry_idx]["l"] <= limit else ep_open
    tp1, tp2, tp3 = highs[0], (highs[1] if len(highs) > 1 else highs[0]*1.05), highs[-1]
    _atr = 0.0
    if i >= 15:
        trs = []
        for k in range(i-14, i):
            trs.append(max(bs[k]["h"]-bs[k]["l"], abs(bs[k]["h"]-bs[k-1]["c"]), abs(bs[k]["l"]-bs[k-1]["c"])))
        _atr = sum(trs)/14 if trs else 0.0
    sl1 = (lows[0] - 0.5*_atr) if _atr > 0 else lows[0]*0.99
    tps = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
    if not tps:
        continue
    tp1 = tps[0]
    tp2 = tps[1] if len(tps) > 1 else tp1*1.05
    tp3 = tps[2] if len(tps) > 2 else tp2*1.05
    r15 = build_row(bs, i, entry_idx, ep, sl1, tp1, tp2, tp3, code, d, st, 15)
    r12 = build_row(bs, i, entry_idx, ep, sl1, tp1, tp2, tp3, code, d, st, 12)
    if r15: ev15.append(r15)
    if r12: ev12.append(r12)
conn.close()
print(f"事件腿 Wilder: max_hold=15 → {len(ev15)} 笔 | max_hold=12 → {len(ev12)} 笔")

def write_csv(ev, path):
    cols = ["symbol", "entry_date", "src", "net_pnl_pct", "rank", "buy_date", "buy_price",
            "sell_date", "sell_price", "reason", "hold_bars", "tp", "sl", "risk_pct",
            "mfe_pct", "mae_pct", "mfe_r", "mae_r", "rr_exit", "signal_chain", "r20"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for t in ev:
            w.writerow(t)

def stats(rows):
    p = [r["net_pnl_pct"] for r in rows]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    eq = 0.0; peak = 0.0; mdd = 0.0
    for x in p:
        eq += x; peak = max(peak, eq); mdd = min(mdd, eq-peak)
    sp = sorted(p)
    return dict(n=len(p), wr=100*len(w)/len(p), avg=sum(p)/len(p), med=sp[len(sp)//2],
                pf=pf, mdd=mdd, sum=sum(p))

def yr(rows, y):
    return stats([r for r in rows if r["entry_date"][:4] == y])

def seg(rows, lo, hi):
    return stats([r for r in rows if lo <= r["entry_date"] <= hi])

base = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")))
base = [{"entry_date": r["entry_date"], "net_pnl_pct": float(r["net_pnl_pct"]),
         "rr_exit": float(r.get("rr_exit") or 0), "reason": r.get("reason") or ""} for r in base]

print("\n" + "="*104)
print("P1-7+P1-8 合并重基线证据: 冻结基线 vs Wilder(h=15) vs Wilder(h=12)")
print("="*104)
print(f"{'口径':<24}{'n':>6}{'胜率%':>8}{'平均%':>9}{'中位%':>9}{'PF':>7}{'MDD%':>8}{'累计%':>9}")
for lab, rows in (("冻结基线(legacy DX,h15)", base),
                  ("Wilder(h=15)", ev15),
                  ("Wilder(h=12)生产口径", ev12)):
    s = stats(rows)
    print(f"{lab:<24}{s['n']:>6}{s['wr']:>8.1f}{s['avg']:>+9.2f}{s['med']:>+9.2f}{s['pf']:>7.2f}{s['mdd']:>8.0f}{s['sum']:>+9.0f}")

print("\n逐年 (n / avg% / PF):")
print(f"{'年':<8}{'冻结基线':>22}{'Wilder h15':>22}{'Wilder h12':>22}")
for y in ("2023", "2024", "2025", "2026"):
    cells = []
    for rows in (base, ev15, ev12):
        s = yr(rows, y)
        cells.append(f"{s['n']}/{s['avg']:+.2f}/{s['pf']:.2f}" if s["n"] else "—")
    print(f"{y:<8}{cells[0]:>22}{cells[1]:>22}{cells[2]:>22}")

print("\nIS(≤2025-06) / OOS(>2025-06) PF:")
for lab, rows in (("冻结基线", base), ("Wilder h15", ev15), ("Wilder h12", ev12)):
    si = seg(rows, "00000000", "20250630")
    so = seg(rows, "20250701", "99999999")
    print(f"  {lab:<14} IS PF={si['pf']:.2f} (n={si['n']}) | OOS PF={so['pf']:.2f} (n={so['n']})")

print("\nRR 左尾 (<=-1R):")
for lab, rows in (("冻结基线", base), ("Wilder h15", ev15), ("Wilder h12", ev12)):
    rr = [r.get("rr_exit") or 0 for r in rows]
    print(f"  {lab:<14} {100*sum(1 for x in rr if x <= -1)/len(rr):.1f}%")

p15 = os.path.join(HERE, "r38_combo_wilder_h15_trades.csv")
p12 = os.path.join(HERE, "r38_combo_wilder_h12_trades.csv")
write_csv(ev15, p15)
write_csv(ev12, p12)
print(f"\n→ {p15} ({len(ev15)} 笔)")
print(f"→ {p12} ({len(ev12)} 笔)")
print("\n注: 两 CSV 均为研究分叉证据; 采纳需走完整审计, 不得直接改 gen_v20f.py。")