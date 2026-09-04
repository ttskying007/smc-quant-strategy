# -*- coding: utf-8 -*-
"""生成 v20e 回测 CSV：事件腿（rank_score 6特征 + 回踩买点 ×0.99 + 分层 TP/SL）+ 延续腿（固定10日）
新 rank_score 特征（阶段跨度/ADX跨度/周线/放量分级/连续放量）的生产回测"""
import csv, io, json, os, sqlite3, sys
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
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


def adx14(bs, i):
    if i < 30:
        return None
    plus_dm = minus_dm = tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up = h - bs[k - 1]["h"]
        dn = bs[k - 1]["l"] - l
        plus_dm += up if (up > dn and up > 0) else 0
        minus_dm += dn if (dn > up and dn > 0) else 0
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_sum += tr
    if tr_sum <= 0:
        return None
    pdi = 100 * plus_dm / tr_sum
    mdi = 100 * minus_dm / tr_sum
    if pdi + mdi == 0:
        return None
    return 100 * abs(pdi - mdi) / (pdi + mdi)


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
    # FIX(2026-08-22): 无泄漏 —— v_ratio 用 T 日量（披露日收盘可得，决策时点），v2_ratio 用 T-1 量
    v_ratio = bs[i]["v"] / avg_v if avg_v > 0 else 1.0
    v2_ratio = bs[i - 1]["v"] / avg_v if (avg_v > 0 and i >= 1) else 0
    stage_span = 0
    for j in range(i, max(0, i - 60), -1):
        if stage_of(bs, j) == st:
            stage_span += 1
        else:
            break
    adx_span = 0
    for j in range(i, max(0, i - 40), -1):
        if (adx14(bs, j) or 0) >= 20:
            adx_span += 1
        else:
            break
    wt = weekly_trend_of(bs, i)
    # FIX(2026-08-22): rank_score 特征对齐（7↔7 与 paper_sim 一致）—— 加事件类型 +1
    _etype = 1 if ("方案" in str(title) or "首次" in str(title) or "计划" in str(title)) else 0
    rs = (2 if st == "ACCUM" else 1)
    rs += (1 if v_ratio > 1.2 else 0) + (1 if v_ratio >= 2.0 else 0)
    rs += (1 if 6 <= stage_span <= 15 else 0) + (1 if adx_span > 15 else 0)
    rs += 1 if wt == "down" else 0
    rs += 1 if (v_ratio >= 1.5 and v2_ratio >= 1.5) else 0
    rs += _etype
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
    # retrace entry (回踩买点 ×0.99)
    limit = disc_close * 0.99
    ep = limit if bs[entry_idx]["l"] <= limit else ep_open
    # tiered TP/SL exit
    tp1, tp2, tp3 = highs[0], (highs[1] if len(highs) > 1 else highs[0] * 1.05), highs[-1]
    # FIX(2026-08-22) P2: SL = sweep low − 0.5×ATR（A股可执行，P1 已落地模拟器）
    _atr = 0
    if i >= 15:
        _trs = []
        for _k in range(i - 14, i):
            _tr = max(bs[_k]["h"] - bs[_k]["l"], abs(bs[_k]["h"] - bs[_k - 1]["c"]), abs(bs[_k]["l"] - bs[_k - 1]["c"]))
            _trs.append(_tr)
        _atr = sum(_trs) / 14 if _trs else 0
    sl1 = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
    # P2: TP 单调去重（确保 tp1<tp2<tp3 且都 > ep）
    _tps = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
    if not _tps:
        continue
    tp1 = _tps[0]
    tp2 = _tps[1] if len(_tps) > 1 else tp1 * 1.05
    tp3 = _tps[2] if len(_tps) > 2 else tp2 * 1.05
    remaining = 1.0
    net = 0.0
    be = False
    for k in range(entry_idx + 1, min(len(bs), entry_idx + 16)):
        bb = bs[k]
        stop = ep if be else sl1
        if bb["l"] <= stop:
            net += remaining * (stop / ep - 1) * 100
            remaining = 0
            break
        if not be and bb["h"] >= tp1:
            net += 0.3 * (tp1 / ep - 1) * 100
            remaining = 0.7
            be = True
        elif be and bb["h"] >= tp2:
            net += remaining * (tp2 / ep - 1) * 100
            remaining = 0
            break
        elif be and bb["h"] >= tp3:
            net += remaining * (tp3 / ep - 1) * 100
            remaining = 0
            break
    if remaining > 0:
        last = bs[min(len(bs), entry_idx + 15) - 1]["c"]
        net += remaining * (last / ep - 1) * 100
    ev.append({"symbol": code + (".SH" if code.startswith("6") else ".SZ"), "entry_date": bs[entry_idx]["t"],
               "src": "EVENT", "net_pnl_pct": round(net - 0.20, 4), "rank": rs})
conn.close()
print("事件(v20e):", len(ev))

# continuation (P2-1: VWAP10% + 支撑新鲜度≤5, from cont_v20f_new.csv)
cont = []
with open(r"E:\test\smc_project\research\cont_v20f_new.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        cont.append({"symbol": r.get("symbol"), "entry_date": r.get("entry_date"),
                     "src": "CONT", "net_pnl_pct": float(r["net_pnl_pct"]), "rank": 3})

# dedup
seen_c = set()
combo = []
for t in ev + cont:
    k = (str(t["symbol"]), str(t["entry_date"]))
    if k in seen_c:
        continue
    seen_c.add(k)
    combo.append(t)

out_path = r"E:\test\smc_project\research\combo_v20f_trades.csv"
with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["symbol", "entry_date", "src", "net_pnl_pct", "rank"])
    w.writeheader()
    for t in combo:
        w.writerow(t)
print(f"v20f CSV(无泄漏): {len(combo)} 笔 → {out_path}")

# quick stats
import statistics
# FIX(2026-09-04, 审计 P2 幸存者偏差): 回测仅覆盖当前缓存中有 K 线的股票（退市/长期停牌股被排除），
# 存在正向幸存者偏差。此处提供"剔除极端尾部(net<=-50%，疑似退市/暴跌)"对照，量化偏差影响。
for y in ("2024", "2025", "2026"):
    ys = [t for t in combo if str(t["entry_date"])[:4] == y]
    if ys:
        pnls = [t["net_pnl_pct"] for t in ys]
        wins = [x for x in pnls if x > 0]
        pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
        # 剔除尾部对照
        pnls_c = [x for x in pnls if x > -50.0]
        wins_c = [x for x in pnls_c if x > 0]
        pf_c = sum(wins_c) / abs(sum(x for x in pnls_c if x <= 0)) if any(x <= 0 for x in pnls_c) else 99
        n_tail = len(pnls) - len(pnls_c)
        print(f"  {y}: n={len(ys)} avg={sum(pnls)/len(pnls):+.2f}% PF={pf:.2f} | 剔除尾部后 n={len(pnls_c)} avg={sum(pnls_c)/len(pnls_c):+.2f}% PF={pf_c:.2f} (剔除{n_tail}笔 net<=-50%)")
print("注: 回测存在正向幸存者偏差（仅覆盖现存股票），剔除尾部对照供参考。")
