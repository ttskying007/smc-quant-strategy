# -*- coding: utf-8 -*-
"""r38_rank_chain.py —— rank 门槛的 paper_sim 全链路审计(接线前最后一步).

背景: R38x 在生产口���上确定 rank_prod>=3 为最优(OOS PF4.52), 但那是**对已选出的
1527 笔**重算 rank 后过滤 —— 属"CSV 离线验证"。真正的接线审计必须在**完整选择链**
上重放, 因为:
  ① rank 门槛改变候选集 → 改变月度 cap=500 的挤出行为(按 rank 排序取前500)
  ② CONT 腿 rank 硬编码=3 → 不同门槛对组合的影响不同(>=4 会整腿剔除)
  ③ 需确认从 announce DB 直接重算 rank 与 CSV 记录一致(无中间口径漂移)

本脚本 = gen_v20f2_wilder_h12 的完整选择链 + rank 门槛扫描:
  事件过滤 classify_title → stage(ACCUM/DOWNTREND) → adx14_of(Wilder)>=20
  → rank_score(生产9特征, paper_sim L814-851 口径) → 入场(limit=close*0.99)
  → 退出(core.execution.simulate, max_hold=CFG.MAX_HOLD, partial 0.3, BE)
  然后对门槛 G in {0,2,3,4} 各自: 过滤 → 月度cap500 → 组合级 + IS/OOS

CONT 腿: 从 cont_v20f_new.csv 读入(rank=3), 按各门槛处理(>=4 时整腿剔除, 显式标注)。
纯研究, 不修改生产。
"""
import csv, io, json, os, sqlite3, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
from core.events import classify_title
from core.indicators import adx14_of as wilder_adx
from core.execution import simulate as _sim
import config as CFG
try:
    from paper_sim import _parse_insider_magnitude
    HAVE_MAG = True
except Exception as _e:
    print("WARN 无法导入 _parse_insider_magnitude: %s" % _e)
    HAVE_MAG = False
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
HERE = r"E:\test\smc_project\research"
IS_END = "20250630"

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
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

def is_strong(title):
    is_ev, kind, pol, _a, _p = classify_title(title)
    return bool(is_ev and pol > 0)

# ── 收集全部候选(生产完整链, 先不设 rank 门槛) ──
cands = []
seen = set()
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for date, code, title in cur.fetchall():
    if not is_strong(title):
        continue
    sym = str(code)[:6]
    d = str(date)[:10].replace("-", "")
    if (sym, d) in seen: continue
    seen.add((sym, d))
    bs = bars_of(sym)
    if not bs: continue
    dates = [b["t"] for b in bs]
    if d not in dates: continue
    i = dates.index(d)
    st = stage_of(bs, i)
    if st not in ("ACCUM", "DOWNTREND"): continue
    adx = wilder_adx(bs, i)
    if adx is None or adx < 20: continue
    ei = i + 1
    if ei + 17 >= len(bs) or ei < 130: continue
    if bs[ei]["t"] < "20230901": continue
    ep_open = bs[ei]["o"]; disc_close = bs[i]["c"]
    if ep_open <= 0: continue
    # ── rank_score: paper_sim L814-851 口径 ──
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
    rs = (2 if st == "ACCUM" else 1)
    rs += (1 if v_ratio > 1.2 else 0) + (1 if v_ratio >= 2.0 else 0)
    rs += (1 if ("方案" in str(title) or "首次" in str(title) or "计划" in str(title)) else 0)
    rs += (1 if 6 <= stage_span <= 15 else 0) + (1 if adx_span > 15 else 0)
    rs += 1 if wt == "down" else 0
    rs += 1 if (v_ratio >= 1.5 and v2_ratio >= 1.5) else 0
    if HAVE_MAG:
        try:
            _amt, _shr, _pct, _mh = _parse_insider_magnitude(title)
            if _pct is not None and _pct >= 1.0: rs += 1
            if _amt is not None and _amt >= 10000: rs += 1
        except Exception:
            pass
    # ── 入场 + 退出(同 gen_v20f2) ──
    highs, lows = [], []
    for j in range(i-1, max(0, i-60), -1):
        if j < 3 or j+3 >= i: continue
        if len(highs) < 2 and bs[j]["h"] > max(bs[k]["h"] for k in range(j-3, j)) \
           and bs[j]["h"] >= max(bs[k]["h"] for k in range(j+1, j+4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j-3, j)) \
           and bs[j]["l"] <= min(bs[k]["l"] for k in range(j+1, j+4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 2 and len(lows) >= 2: break
    if not highs or not lows: continue
    highs.sort()
    limit = disc_close*0.99
    ep = limit if bs[ei]["l"] <= limit else ep_open
    tp1, tp2, tp3 = highs[0], (highs[1] if len(highs) > 1 else highs[0]*1.05), highs[-1]
    _atr = 0.0
    if i >= 15:
        trs = [max(bs[k]["h"]-bs[k]["l"], abs(bs[k]["h"]-bs[k-1]["c"]), abs(bs[k]["l"]-bs[k-1]["c"]))
               for k in range(i-14, i)]
        _atr = sum(trs)/14 if trs else 0.0
    sl1 = (lows[0] - 0.5*_atr) if _atr > 0 else lows[0]*0.99
    tps = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
    if not tps: continue
    tp1 = tps[0]; tp2 = tps[1] if len(tps) > 1 else tp1*1.05; tp3 = tps[2] if len(tps) > 2 else tp2*1.05
    if ep <= sl1: continue
    r = _sim(bs, ei, ep, sl1, tp1=tp1, tp2=tp2, tp3=tp3,
             partial_tp1=0.3, stop_to_be=True, max_hold=CFG.MAX_HOLD, code=sym)
    if r.get("skipped"): continue
    cands.append({"s": sym, "d": bs[ei]["t"], "net": r.get("net_pnl_pct", 0.0),
                  "rank": rs, "stage": st})
conn.close()
print("完整链候选(无 rank 门槛): %d 笔" % len(cands))

# CONT 腿(rank=3, 与 gen_v20f 一致)
cont = []
with open(os.path.join(HERE, "cont_v20f_new.csv"), encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        cont.append({"s": row.get("symbol"), "d": str(row.get("entry_date")),
                     "net": float(row["net_pnl_pct"]), "rank": 3, "stage": "CONT"})
print("CONT 腿: %d 笔" % len(cont))

def combo_stats(trades):
    if not trades: return None
    p = [t["net"] for t in trades]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(p), "avg": round(sum(p)/len(p), 3),
            "wr": round(100*len(w)/len(p), 1), "pf": round(pf, 2),
            "sum": round(sum(p), 0)}

def build(gate, gate_cont=True):
    """门槛 → 过滤 → 去重 → 月度 cap=500(按 rank 降序)

    gate_cont=False: 门槛**只作用于 EVENT 腿**, CONT 腿(rank 恒=3)始终保留 ——
    用于分离"EVENT 质量提升"与"CONT 被顺带剔除"两个效应。"""
    pool = [t for t in cands if t["rank"] >= gate]
    pool = pool + [t for t in cont if (t["rank"] >= gate if gate_cont else True)]
    seen = set(); dedup = []
    for t in pool:
        k = (str(t["s"]), str(t["d"]))
        if k in seen: continue
        seen.add(k); dedup.append(t)
    bym = defaultdict(list)
    for t in dedup: bym[str(t["d"])[:6]].append(t)
    out = []
    for m, v in sorted(bym.items()):
        out.extend(sorted(v, key=lambda t: -t["rank"])[:500])
    return out

print("\n" + "=" * 104)
print("rank 门槛全链路审计 (完整选择链重放; CONT 腿 rank=3)")
print("=" * 104)
print("%-22s %6s %9s %7s %6s %9s %7s %8s" % ("方案", "IS_n", "IS_avg%", "IS_PF", "OOS_n", "OOS_avg%", "OOS_PF", "全n"))
for gc in (True, False):
    tag = "门槛作用于两腿(CONT 可能被剔除)" if gc else "门槛只作用于 EVENT(CONT 保留)"
    print("\n--- %s ---" % tag)
    print("%-22s %6s %9s %7s %6s %9s %7s %8s" % ("方案", "IS_n", "IS_avg%", "IS_PF", "OOS_n", "OOS_avg%", "OOS_PF", "全n"))
    base_oos = None
    for g in (0, 2, 3, 4):
        tr = build(g, gc)
        isr = [t for t in tr if str(t["d"]) <= IS_END]
        oosr = [t for t in tr if str(t["d"]) > IS_END]
        si, so = combo_stats(isr), combo_stats(oosr)
        if g == 0: base_oos = so
        if si and so:
            ok = "✅" if (so["pf"] > 1.5 and so["pf"]/si["pf"] > 0.5 and so["pf"] >= base_oos["pf"]) else "  "
            print("%-22s %6d %+8.2f%% %7.2f %6d %+8.2f%% %7.2f %8d %s"
                  % ("rank_prod>=%d" % g, si["n"], si["avg"], si["pf"],
                     so["n"], so["avg"], so["pf"], len(tr), ok))

print("\n分腿(全样本):")
for g in (0, 2, 3, 4):
    ev_n = len([t for t in build(g) if t["stage"] != "CONT"])
    co_n = len([t for t in build(g) if t["stage"] == "CONT"])
    print("  rank_prod>=%d: EVENT %4d + CONT %3d" % (g, ev_n, co_n))

print("\n逐年(rank_prod>=3 vs 基线):")
for y in ("2024", "2025", "2026"):
    a = combo_stats([t for t in build(0) if str(t["d"])[:4] == y])
    b = combo_stats([t for t in build(3) if str(t["d"])[:4] == y])
    if a and b:
        print("  %s: 基线 n=%3d %+.2f%%/PF%.2f | >=3 n=%3d %+.2f%%/PF%.2f"
              % (y, a["n"], a["avg"], a["pf"], b["n"], b["avg"], b["pf"]))

json.dump({"cands": len(cands),
           "gates_both": {str(g): combo_stats(build(g, True)) for g in (0, 2, 3, 4)},
           "gates_event_only": {str(g): combo_stats(build(g, False)) for g in (0, 2, 3, 4)}},
          open(os.path.join(HERE, "r38_rank_chain.json"), "w", encoding="utf-8"), ensure_ascii=False)
# 缓存候选(供后续廉价变体分析, 免重跑全市场)
json.dump(cands, open(os.path.join(HERE, "r38_rank_chain_cands.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("\n→ r38_rank_chain.json (+ r38_rank_chain_cands.json 缓存 %d 笔)" % len(cands))