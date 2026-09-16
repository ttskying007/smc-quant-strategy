# -*- coding: utf-8 -*-
"""r38_rank_prod.py —— 生产口径重算 rank + 重做门槛搜索(路径①) + 分位数门槛(路径③).

背景(R38w): 回测 rank(7特征) 与生产 paper_sim rank_score(L814-851) 不等价 ——
生产多 2 项增持强度特征(占比>=1% / 金额>=1亿 各 +1)。故 R38v 的"rank>=4"
不能直接搬到生产。本脚本执行推荐路径①+③:

  ① 用**生产特征集**对历史事件重算 rank_prod
  ② 在生产口径上重做门槛搜索(IS/OOS)
  ③ 用**分位数**门槛(规避分布漂移)并做 IS/OOS

生产 rank_score 特征(paper_sim L814-851):
  (2 if ACCUM else 1)
  +1 if v_ratio > 1.2
  +1 if v_ratio >= 2.0
  +1 if etype(方案/首次/计划)
  +1 if 6 <= stage_span <= 15
  +1 if adx_span > 15
  +1 if weekly_trend == "down"
  +1 if v_ratio >= 1.5 and v2_ratio >= 1.5
  +1 if insider_pct >= 1.0          ← 回测无
  +1 if insider_amount_wan >= 10000 ← 回测无

数据: combo_v20f_trades.csv(新基线 EVENT) + kline + announce DB + paper_sim 辅助函数
纯研究, 不修改生产。
"""
import csv, io, json, os, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = r"E:\test\smc_project\research"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
sys.path.insert(0, HERE)
from core.events import classify_title
from core.indicators import adx14_of as wilder_adx    # 生产口径 ADX
try:
    from paper_sim import _parse_insider_magnitude
    HAVE_MAG = True
except Exception as e:
    print("WARN 无法导入 _parse_insider_magnitude: %s" % e)
    HAVE_MAG = False

IS_END = "20250630"

def f(x, d=0.0):
    try: return float(x)
    except: return d

code2file = {fn.split("_")[0]: os.path.join(KT, fn) for fn in os.listdir(KT) if fn.endswith("_daily_800.json")}
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

def stage_of(bs, i):
    if i < 91: return None
    w60 = bs[i-60:i]
    if len(w60) < 2: return None
    ret60 = w60[-1]["c"]/w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i-20:i])/20
    v60 = sum(b["v"] for b in bs[i-60:i])/60
    vt = v20/v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9: return "ACCUM"
    if ret60 > 0.30 and vt > 1.3: return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1: return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"

def weekly_trend_of(bs, i):
    closes = []; j = i
    while j >= 0 and len(closes) < 20:
        closes.append(bs[j]["c"]); j -= 5
    closes.reverse()
    if len(closes) < 12: return None
    return "up" if sum(closes[-10:])/10 > sum(closes[-12:-2])/10 else "down"

# 标题索引(取 announce DB 中该股该日的标题)
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
title_idx = {}
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for date, code, title in cur.fetchall():
    d = str(date)[:10].replace("-", "")
    title_idx[(str(code)[:6], d)] = title

rows = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
print("新基线 EVENT: %d 笔" % len(ev))

recs = []
n_hit = 0
for r in ev:
    sym = str(r.get("symbol") or "").split(".")[0]
    d8 = str(r.get("entry_date") or "").replace("-", "")
    bs = bars_of(sym)
    if not bs: continue
    dates = [b["t"] for b in bs]
    if d8 not in dates: continue
    ei = dates.index(d8)
    i = ei - 1
    if i < 95: continue
    st = stage_of(bs, i)
    if st is None: continue
    title = title_idx.get((sym, d8), "")
    avg_v = sum(b["v"] for b in bs[i-19:i+1])/20 if i >= 19 else 0
    v_ratio = bs[i]["v"]/avg_v if avg_v > 0 else 1.0
    v2_ratio = bs[i-1]["v"]/avg_v if (avg_v > 0 and i >= 1) else 0
    stage_span = 0
    for j in range(i, max(0, i-60), -1):
        if stage_of(bs, j) == st: stage_span += 1
        else: break
    adx_span = 0
    for j in range(i, max(0, i-40), -1):
        if (wilder_adx(bs, j) or 0) >= 20: adx_span += 1
        else: break
    wt = weekly_trend_of(bs, i)
    etype = 1 if ("方案" in str(title) or "首次" in str(title) or "计划" in str(title)) else 0
    # ── 生产口径 rank_score ──
    rs = (2 if st == "ACCUM" else 1)
    rs += (1 if v_ratio > 1.2 else 0) + (1 if v_ratio >= 2.0 else 0)
    rs += (1 if 6 <= stage_span <= 15 else 0) + (1 if adx_span > 15 else 0)
    rs += 1 if wt == "down" else 0
    rs += 1 if (v_ratio >= 1.5 and v2_ratio >= 1.5) else 0
    rs += etype
    _pct = _amt = None
    if HAVE_MAG and title:
        try:
            _amt, _shr, _pct, _mh = _parse_insider_magnitude(title)
        except Exception:
            pass
    if _pct is not None and _pct >= 1.0: rs += 1
    if _amt is not None and _amt >= 10000: rs += 1
    n_hit += 1
    recs.append({"net": f(r["net_pnl_pct"]), "rank_prod": rs,
                 "rank_bt": int(f(r.get("rank"))), "d": d8})

print("重算命中: %d / %d" % (n_hit, len(ev)))

def stats(ts):
    if not ts: return None
    p = [t["net"] for t in ts]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(p), "avg": round(sum(p)/len(p), 2),
            "wr": round(100*len(w)/len(p), 1), "pf": round(pf, 2)}

print("\n" + "="*96)
print("① 分布对比: 回测 rank vs 生产 rank_prod")
print("="*96)
for lab, key in (("回测 rank", "rank_bt"), ("生产 rank_prod", "rank_prod")):
    d = defaultdict(int)
    for t in recs: d[t[key]] += 1
    mx = max(d) if d else 0
    print("  %-16s 范围 1-%d | 分布 %s" % (lab, mx, dict(sorted(d.items()))))
shift = sum(t["rank_prod"] - t["rank_bt"] for t in recs) / len(recs)
print("  平均位移: %+.2f 分 (生产 - 回测)" % shift)

print("\n" + "="*96)
print("② 生产口径门槛搜索(IS/OOS)")
print("="*96)
print("%-18s %6s %9s %7s | %6s %9s %7s" % ("方案", "IS_n", "IS_avg%", "IS_PF", "OOS_n", "OOS_avg%", "OOS_PF"))
base_is = stats([t for t in recs if t["d"] <= IS_END])
base_oos = stats([t for t in recs if t["d"] > IS_END])
print("%-18s %6d %+8.2f%% %7.2f | %6d %+8.2f%% %7.2f"
      % ("等权(基准)", base_is["n"], base_is["avg"], base_is["pf"],
         base_oos["n"], base_oos["avg"], base_oos["pf"]))
for g in (2, 3, 4, 5, 6):
    si = stats([t for t in recs if t["d"] <= IS_END and t["rank_prod"] >= g])
    so = stats([t for t in recs if t["d"] > IS_END and t["rank_prod"] >= g])
    if si and so:
        keep = len([t for t in recs if t["rank_prod"] >= g])
        ok = "✅" if (so["pf"] > 1.5 and so["pf"]/si["pf"] > 0.5 and so["pf"] >= base_oos["pf"]) else "  "
        print("%-18s %6d %+8.2f%% %7.2f | %6d %+8.2f%% %7.2f 保留%d(%.0f%%) %s"
              % ("rank_prod>=%d" % g, si["n"], si["avg"], si["pf"],
                 so["n"], so["avg"], so["pf"], keep, 100*keep/len(recs), ok))

print("\n" + "="*96)
print("③ 分位数门槛(规避分布漂移, IS/OOS)")
print("="*96)
# 在 IS 上定分位切点, 应用到 OOS(严格无前视)
is_recs = sorted([t for t in recs if t["d"] <= IS_END], key=lambda t: t["rank_prod"])
for q in (0.0, 0.25, 0.5, 0.75):
    if not is_recs: continue
    cut = is_recs[int(len(is_recs)*q)]["rank_prod"]
    si = stats([t for t in recs if t["d"] <= IS_END and t["rank_prod"] >= cut])
    so = stats([t for t in recs if t["d"] > IS_END and t["rank_prod"] >= cut])
    if si and so:
        keep = len([t for t in recs if t["rank_prod"] >= cut])
        print("  q=%.2f (切点 rank_prod>=%d, IS 内): IS n=%d PF=%.2f | OOS n=%d PF=%.2f | 保留 %.0f%%"
              % (q, cut, si["n"], si["pf"], so["n"], so["pf"], 100*keep/len(recs)))

print("\n注: 若生产口径下的最优点与回测口径不同, 说明 R38v 的 rank>=4 确属回测特有;")
print("    应以本脚本的生产口径结果为准接线。")