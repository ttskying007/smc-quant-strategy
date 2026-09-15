# -*- coding: utf-8 -*-
"""r38_gen_v20f_wilder.py —— R38 P1-7 重基线分叉: Wilder ADX 版基线.

【关键约束】这是**独立研究分叉**, 绝不修改 gen_v20f.py(冻结线 n=1639±1)。
本脚本 = gen_v20f.py 的逐行复制 + 唯一改动: adx14() 旧版单窗DX → core.indicators.adx14_of
(Wilder 平滑)。用于量化"切到 Wilder 后完整池"的表现(非仅 610 笔错杀候选)。

产出: r38_combo_wilder_trades.csv (同字段), 供对比脚本消费。
审计前置: 若晋级, 需走完整审计(全测试链 + 冻结基线重认定), 不得直接改 gen_v20f.py。
"""
import csv, io, json, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.events import classify_title
from core.indicators import adx14_of as wilder_adx   # ← P1-7 修复: 生产唯一 ADX
from core.execution import simulate as _sim
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
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

def adx14(bs, i):
    """P1-7 修复: 委托 core.indicators.adx14_of(Wilder), 替代旧版单窗DX。"""
    return wilder_adx(bs, i)

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

def weekly_trend_of(bs, i):
    closes = []
    j = i
    while j >= 0 and len(closes) < 20:
        closes.append(bs[j]["c"])
        j -= 5
    closes.reverse()
    if len(closes) < 12:
        return None
    ma10 = sum(closes[-10:]) / 10
    ma_prev = sum(closes[-12:-2]) / 10
    return "up" if ma10 > ma_prev else "down"

ev = []
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
    adx = adx14(bs, i)
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
    avg_v = sum(bs[k]["v"] for k in range(i - 19, i + 1)) / 20 if i >= 19 else 0
    v_ratio = bs[i]["v"] / avg_v if avg_v > 0 else 1.0
    highs = []
    lows = []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(highs) < 2 and bs[j]["h"] > max(bs[k]["h"] for k in range(j - 3, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + 4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j - 3, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + 4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 2 and len(lows) >= 2:
            break
    if not highs or not lows:
        continue
    highs.sort()
    limit = disc_close * 0.99
    ep = limit if bs[entry_idx]["l"] <= limit else ep_open
    tp1, tp2, tp3 = highs[0], (highs[1] if len(highs) > 1 else highs[0] * 1.05), highs[-1]
    _atr = 0
    if i >= 15:
        _trs = []
        for _k in range(i - 14, i):
            _tr = max(bs[_k]["h"] - bs[_k]["l"], abs(bs[_k]["h"] - bs[_k - 1]["c"]), abs(bs[_k]["l"] - bs[_k - 1]["c"]))
            _trs.append(_tr)
        _atr = sum(_trs) / 14 if _trs else 0
    sl1 = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
    _tps = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
    if not _tps:
        continue
    tp1 = _tps[0]
    tp2 = _tps[1] if len(_tps) > 1 else tp1 * 1.05
    tp3 = _tps[2] if len(_tps) > 2 else tp2 * 1.05
    _r = _sim(bs, entry_idx, ep, sl1, tp1=tp1, tp2=tp2, tp3=tp3,
              partial_tp1=0.3, stop_to_be=True, max_hold=15, code=code[:6])
    net = _r.get("net_pnl_pct", 0.0)
    if _r.get("skipped"):
        continue
    _risk = ep - sl1
    _hb = _r.get("hold_bars", 0)
    _sell_i = min(len(bs) - 1, entry_idx + max(1, _hb)) if _hb else entry_idx
    ev.append({
        "symbol": code + (".SH" if code.startswith("6") else ".SZ"), "entry_date": bs[entry_idx]["t"],
        "src": "EVENT",
        "buy_date": bs[entry_idx]["t"], "buy_price": round(ep, 3),
        "sell_date": bs[_sell_i]["t"] if _hb else "",
        "sell_price": round(_r.get("exit_price", 0), 3) if _hb else "",
        "reason": _r.get("reason", ""), "hold_bars": _hb,
        "tp": round(tp2, 3), "sl": round(sl1, 3), "risk_pct": round(_risk / ep * 100, 3) if _risk > 0 else 0,
        "net_pnl_pct": round(net, 4),
        "mfe_pct": _r.get("mfe_pct", 0), "mae_pct": _r.get("mae_pct", 0),
        "mfe_r": _r.get("mfe_r", 0), "mae_r": _r.get("mae_r", 0),
        "rr_exit": round((_r.get("exit_price", ep) / ep - 1) / (_risk / ep), 3) if _risk > 0 else 0,
        "signal_chain": "insider-event", "r20": "", "rank": 0})
conn.close()
print("事件(Wilder ADX):", len(ev))

cont = []
with open(r"E:\test\smc_project\research\cont_v20f_new.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        cont.append({"symbol": r.get("symbol"), "entry_date": r.get("entry_date"),
                     "src": "CONT", "net_pnl_pct": float(r["net_pnl_pct"]), "rank": 3})

seen_c = set()
combo = []
for t in ev + cont:
    k = (str(t["symbol"]), str(t["entry_date"]))
    if k in seen_c:
        continue
    seen_c.add(k)
    combo.append(t)

COMBO_MONTH_CAP = 500
from collections import defaultdict
by_month_combo = defaultdict(list)
for t in combo:
    by_month_combo[str(t["entry_date"])[:6]].append(t)
combo_capped = []
for m, v in sorted(by_month_combo.items()):
    v_sorted = sorted(v, key=lambda t: -(float(t.get("rank") or 0)))
    combo_capped.extend(v_sorted[:COMBO_MONTH_CAP])
combo = combo_capped

out_path = r"E:\test\smc_project\research\r38_combo_wilder_trades.csv"
with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["symbol", "entry_date", "src", "net_pnl_pct", "rank",
                                       "buy_date", "buy_price", "sell_date", "sell_price",
                                       "reason", "hold_bars", "tp", "sl", "risk_pct",
                                       "mfe_pct", "mae_pct", "mfe_r", "mae_r", "rr_exit",
                                       "signal_chain", "r20"])
    w.writeheader()
    for t in combo:
        w.writerow(t)
print(f"v20f-Wilder CSV(月度cap={COMBO_MONTH_CAP}): {len(combo)} 笔 → {out_path}")

import statistics
for y in ("2024", "2025", "2026"):
    ys = [t for t in combo if str(t["entry_date"])[:4] == y]
    if ys:
        ps = [t["net_pnl_pct"] for t in ys]
        print(f"  {y}: n={len(ys)} avg={statistics.mean(ps):+.2f}%")