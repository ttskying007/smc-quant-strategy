# -*- coding: utf-8 -*-
"""事件过滤 A/B 验证（第六轮审计研究项）：PROGRESS_WITH_DELTA（进展/完成类含金额增量公告）
   是否值得从"一刀切拒绝"放开为"候选"。

设计：
  A 组（现行生产口径）= NEG_WORDS 全否（进展/完成类全拒绝）            → 基线
  B 组（研究候选）     = A + PROGRESS_WITH_DELTA（软否+回购/增持+金额/比例增量）
  其余链路完全一致（阶段/ADX/回踩×0.99/分层TP/SL-0.5ATR/15根持有/0.20费），
  复制 gen_v20f.py 的 EVENT 腿语义（无泄漏：特征只用披露日及以前数据）。

验收线（预注册，不看结果再定）：
  B−A 增量笔数 n_delta ≥ 30（样本足够）
  且 OOS(2025-07-01后) B 组增量 avg_net > +1.0%（增量交易为正贡献）
  且 IS 与 OOS 方向一致（非过拟合窗口）
  → 三条全过才建议放开；任一不过 → 维持拒绝（证据记录）。
"""
import io, json, os, sqlite3, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.events import classify_title, classify_title_detailed

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS_FROM = "20250701"

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
bar_cache = {}

def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        raw = json.load(open(p, encoding="utf-8")) if p else []
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                           "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def adx14(bs, i):
    if i < 30:
        return None
    plus_dm = minus_dm = tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up, dn = h - bs[k - 1]["h"], bs[k - 1]["l"] - l
        plus_dm += up if (up > dn and up > 0) else 0
        minus_dm += dn if (dn > up and dn > 0) else 0
        tr_sum += max(h - l, abs(h - pc), abs(l - pc))
    if tr_sum <= 0:
        return None
    pdi, mdi = 100 * plus_dm / tr_sum, 100 * minus_dm / tr_sum
    return 100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else None


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


def run_leg(mode):
    """mode='A' 全否基线 | 'B' A+PROGRESS_WITH_DELTA。返回交易列表。"""
    trades, seen = [], set()
    cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
    for date, code, title in cur.fetchall():
        _is_ev, kind, pol, amt, pct = classify_title(title)
        layer = classify_title_detailed(title)[5]
        if not _is_ev or pol < 0:
            if mode == "A":
                continue  # 基线：软否/硬否全拒
            if mode == "B" and layer != "PROGRESS_WITH_DELTA":
                continue  # B：只额外纳入含增量的进展类
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
        highs, lows = [], []
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
            _trs = [max(bs[k]["h"] - bs[k]["l"], abs(bs[k]["h"] - bs[k - 1]["c"]), abs(bs[k]["l"] - bs[k - 1]["c"]))
                    for k in range(i - 14, i)]
            _atr = sum(_trs) / 14
        sl1 = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
        _tps = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
        if not _tps:
            continue
        tp1 = _tps[0]
        tp2 = _tps[1] if len(_tps) > 1 else tp1 * 1.05
        tp3 = _tps[2] if len(_tps) > 2 else tp2 * 1.05
        remaining, net, be = 1.0, 0.0, False
        for k in range(entry_idx + 1, min(len(bs), entry_idx + 16)):
            bb = bs[k]
            stop = ep if be else sl1
            if bb["l"] <= stop:
                net += remaining * (stop / ep - 1) * 100
                remaining = 0
                break
            if not be and bb["h"] >= tp1:
                net += 0.3 * (tp1 / ep - 1) * 100
                remaining, be = 0.7, True
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
        trades.append({"code": code, "entry_date": bs[entry_idx]["t"], "layer": layer,
                       "net": round(net - 0.20, 4)})
    return trades


def stats(ts):
    if not ts:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    pnls = [t["net"] for t in ts]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    return {"n": len(ts), "avg": round(sum(pnls) / len(pnls), 3),
            "wr": round(len(wins) / len(pnls), 3),
            "pf": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else 99.0}


def split(ts, oos_from=OOS_FROM):
    return [t for t in ts if t["entry_date"] < oos_from], [t for t in ts if t["entry_date"] >= oos_from]


A = run_leg("A")
B = run_leg("B")
print(f"A 组（基线，进展/完成全拒）: {len(A)} 笔")
print(f"B 组（A+含增量进展类）:      {len(B)} 笔")

a_set = {(t["code"], t["entry_date"]) for t in A}
delta = [t for t in B if (t["code"], t["entry_date"]) not in a_set]
print(f"增量（B−A，放开后新增）:    {len(delta)} 笔  layer分布:",
      {l: sum(1 for t in delta if t['layer'] == l) for l in {t['layer'] for t in delta}})

print("\n== A 组基线 ==")
A_is, A_oos = split(A)
print(f"  全部: {stats(A)}")
print(f"  IS(<{OOS_FROM}): {stats(A_is)}")
print(f"  OOS(>={OOS_FROM}): {stats(A_oos)}")

print("\n== B 组 ==")
B_is, B_oos = split(B)
print(f"  全部: {stats(B)}")
print(f"  IS: {stats(B_is)}  |  OOS: {stats(B_oos)}")

print("\n== 增量交易（B−A）单独 ==")
D_is, D_oos = split(delta)
print(f"  全部: {stats(delta)}")
print(f"  IS: {stats(D_is)}")
print(f"  OOS: {stats(D_oos)}")

# 预注册验收
n_delta = len(delta)
d_oos = stats(D_oos)
d_is = stats(D_is)
c1 = n_delta >= 30
c2 = d_oos.get("avg", 0) > 1.0
c3 = (d_is.get("avg", 0) > 0) == (d_oos.get("avg", 0) > 0)
print("\n== 预注册验收（三条全过才建议放开）==")
print(f"  ① 增量样本 n≥30: {n_delta} → {'✅' if c1 else '❌'}")
print(f"  ② OOS avg>+1.0%: {d_oos.get('avg')}% → {'✅' if c2 else '❌'}")
print(f"  ③ IS/OOS 方向一致: IS={d_is.get('avg')}% OOS={d_oos.get('avg')}% → {'✅' if c3 else '❌'}")
verdict = "PASS → 建议放开 PROGRESS_WITH_DELTA" if (c1 and c2 and c3) else "FAIL → 维持拒绝（证据记录）"
print(f"\n结论: {verdict}")

# 落盘
out = {"generated_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
       "oos_from": OOS_FROM,
       "A_baseline": {"all": stats(A), "is": stats(A_is), "oos": stats(A_oos)},
       "B_with_delta": {"all": stats(B), "is": stats(B_is), "oos": stats(B_oos)},
       "delta_only": {"all": stats(delta), "is": stats(D_is), "oos": stats(D_oos),
                      "n": n_delta, "layer_dist": {l: sum(1 for t in delta if t['layer'] == l)
                                                   for l in {t['layer'] for t in delta}}},
       "criteria": {"n_ge_30": c1, "oos_avg_gt_1pct": c2, "is_oos_consistent": c3},
       "verdict": verdict}
os.makedirs(r"E:\test\smc_project\research\handover", exist_ok=True)
with open(r"E:\test\smc_project\research\handover\事件过滤AB验证.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("已写 handover/事件过滤AB验证.json")
conn.close()