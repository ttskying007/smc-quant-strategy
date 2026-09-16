# -*- coding: utf-8 -*-
"""r38_stage_rescan.py —— 新基线口径下重算 stage (解决 ACCUM×2 不可判定) + 月度弱势归因.

问题(R38t): 上一轮 ACCUM×2 复核用 r38_stage_relax.json 做 join, 命中仅 5.6%
(86/1527) —— 根因是 stage_relax 的候选集来自 legacy adx 过滤, 与新基线
(Wilder adx) 事件集重叠极小 → ACCUM×2 不可判定。

本脚本**直接对新基线的 1527 笔 EVENT 重算 stage**(stage_of 只用 ret60+量比,
与 ADX 无关): 信号日 i = entry_date 在 bars 中的索引 - 1。

同时归因 4/5/6 月弱势(跨口径稳定, R38t 确认):
  ① 这些月的逐年分布(是否集中在 2023 小样本)
  ② 这些月的 rank / stage 构成
  ③ 与强势月(2/7/9)对照

产出: 真 stage 分桶 + ACCUM×2 判定 + 月度归因。
纯研究, 不修改生产。
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = r"E:\test\smc_project\research"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
sys.path.insert(0, HERE)

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
    """与 gen_v20f/gen_v20f2 完全一致 (仅 ret60 + 量比, 不含 ADX)。"""
    if i < 91: return None
    w60 = bs[i-60:i]
    if len(w60) < 2: return None
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i-20:i]) / 20
    v60 = sum(b["v"] for b in bs[i-60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9: return "ACCUM"
    if ret60 > 0.30 and vt > 1.3: return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1: return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"

rows = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
print("新基线 EVENT: %d 笔" % len(ev))

recs = []
n_stage = 0
for r in ev:
    sym = str(r.get("symbol") or "").split(".")[0]
    d8 = str(r.get("entry_date") or "").replace("-", "")
    bs = bars_of(sym)
    st = None
    if bs:
        dates = [b["t"] for b in bs]
        if d8 in dates:
            ei = dates.index(d8)
            i = ei - 1                      # 信号日 = 入场日 - 1
            if i >= 0:
                st = stage_of(bs, i)
    if st: n_stage += 1
    try: rk = int(float(r.get("rank") or 0))
    except: rk = 0
    recs.append({"net": f(r["net_pnl_pct"]), "stage": st or "(未算出)", "rank": rk,
                 "d": d8, "reason": r.get("reason") or "?"})
print("stage 命中: %d / %d (%.1f%%)" % (n_stage, len(recs), 100*n_stage/len(recs)))

def combo(ws):
    if not ws: return None
    c = [n*w for n, w in ws]
    wins = [x for x in c if x > 0]; loss = [x for x in c if x <= 0]
    pf = sum(wins)/abs(sum(loss)) if sum(loss) else 99
    eq = 0.0; peak = 0.0; mdd = 0.0
    for x in c:
        eq += x; peak = max(peak, eq); mdd = min(mdd, eq-peak)
    tw = sum(w for _, w in ws)
    return {"n": len(c), "exp": round(tw, 0), "avg_exp": round(sum(c)/tw, 2) if tw else 0,
            "pf": round(pf, 2), "mdd": round(mdd, 0), "sum": round(sum(c), 0)}

print("\n" + "="*92)
print("① stage 真实分桶(新基线口径, 与 gen_v20f2 同函数)")
print("="*92)
bys = defaultdict(list)
for t in recs: bys[t["stage"]].append(t["net"])
print("%-12s %6s %10s %8s %8s" % ("stage", "n", "avg%", "wr", "PF"))
for k, ps in sorted(bys.items(), key=lambda kv: -len(kv[1])):
    w = [x for x in ps if x > 0]
    l = [x for x in ps if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    print("%-12s %6d %+9.2f%% %7.1f%% %8.2f" % (k, len(ps), sum(ps)/len(ps), 100*len(w)/len(ps), pf))

print("\n② ACCUM×2 判定(真实 stage)")
wsA = [(t["net"], 1.0) for t in recs]
wsB = [(t["net"], 2.0 if t["stage"] == "ACCUM" else 1.0) for t in recs]
A, B = combo(wsA), combo(wsB)
print("  A 等权    : 敞口=%.0f 每单位=%+.2f%% PF=%.2f MDD=%.0f" % (A["exp"], A["avg_exp"], A["pf"], A["mdd"]))
print("  B ACCUM×2 : 敞口=%.0f 每单位=%+.2f%% PF=%.2f MDD=%.0f" % (B["exp"], B["avg_exp"], B["pf"], B["mdd"]))
n_acc = sum(1 for t in recs if t["stage"] == "ACCUM")
print("  ACCUM 笔数=%d (%.1f%%)" % (n_acc, 100*n_acc/len(recs)))
if B["avg_exp"] > A["avg_exp"] and B["pf"] >= A["pf"]:
    print("  → ✅ ACCUM×2 仍成立 (+%.2fpp / PF %+.2f)" % (B["avg_exp"]-A["avg_exp"], B["pf"]-A["pf"]))
elif n_acc >= 100:
    print("  → ⚠ ACCUM×2 效果改变 (n=%d 足够, 结论需修正)" % n_acc)
else:
    print("  → ⚠ 样本不足(n=%d), 仍不可判定" % n_acc)

print("\n③ 4/5/6 月弱势归因(跨口径稳定, R38t 确认)")
for mm, lab in (("04", "4月"), ("05", "5月"), ("06", "6月"),
                ("02", "2月(强)"), ("07", "7月(强)"), ("09", "9月(强)")):
    ms = [t for t in recs if t["d"][4:6] == mm]
    if not ms: continue
    ps = [t["net"] for t in ms]
    w = [x for x in ps if x > 0]; l = [x for x in ps if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    byy = defaultdict(int)
    for t in ms: byy[t["d"][:4]] += 1
    rk = defaultdict(int)
    for t in ms: rk[t["rank"]] += 1
    stg = defaultdict(int)
    for t in ms: stg[t["stage"]] += 1
    top_st = sorted(stg.items(), key=lambda kv: -kv[1])[:2]
    print("  %s n=%3d avg=%+.2f%% PF=%.2f | 年%s | rank%s | stage%s"
          % (lab, len(ms), sum(ps)/len(ps), pf,
             dict(sorted(byy.items())),
             dict(sorted(rk.items())),
             dict(top_st)))

print("\n④ 4/5/6 月逐年明细(排除小样本干扰)")
for mm, lab in (("04", "4月"), ("05", "5月"), ("06", "6月")):
    for y in ("2023", "2024", "2025", "2026"):
        ys = [t for t in recs if t["d"][4:6] == mm and t["d"][:4] == y]
        if not ys: continue
        ps = [t["net"] for t in ys]
        w = [x for x in ps if x > 0]
        print("    %s %s: n=%2d avg=%+.2f%% wr=%.0f%%" % (y, lab, len(ps), sum(ps)/len(ps), 100*len(w)/len(ps)))

json.dump({"stage_hit": n_stage, "n": len(recs),
           "accum_n": n_acc, "A": A, "B": B},
          open(os.path.join(HERE, "r38_stage_rescan.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("\n→ r38_stage_rescan.json")