# -*- coding: utf-8 -*-
"""r38_stage_relax.py —— R38 stage 白名单放宽实验(同一 alpha 源内部扩量).

背景: 基线仅接受 stage in (ACCUM, DOWNTREND) 的增持/回购事件。这是"量少"
的直接约束(1640 笔/3年)。两轮外部扩池(技术腿/事件类型)均否决后, 回到
alpha 源内部: 其他 stage(UPTREND/MARKUP/DISTRIB)的事件是否也有正期望?

方法(gen_v20f 同口径, 仅 stage 条件变化):
  对每个增持/回购事件: stage_of + 旧版 adx14>=20 + 入场/SL/TP/simulate 全部同基线
  按 stage 分桶统计 avg/WR/PF/n, 并做 IS/OOS 分段(R38h 纪律)
判据(预注册): 某 stage 桶晋级需 OOS PF>1.5 且 OOS/IS>0.5 且 n>=100
纯研究, 不修改生产。
"""
import csv, io, json, os, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
from core.events import classify_title
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

def adx14(bs, i):
    if i < 30: return None
    plus_dm = minus_dm = tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up = h - bs[k - 1]["h"]; dn = bs[k - 1]["l"] - l
        plus_dm += up if (up > dn and up > 0) else 0
        minus_dm += dn if (dn > up and dn > 0) else 0
        tr_sum += max(h - l, abs(h - pc), abs(l - pc))
    if tr_sum <= 0: return None
    pdi = 100*plus_dm/tr_sum; mdi = 100*minus_dm/tr_sum
    if pdi + mdi == 0: return None
    return 100*abs(pdi - mdi)/(pdi + mdi)

def stage_of(bs, i):
    if i < 91: return None
    w60 = bs[i-60:i]
    ret60 = w60[-1]["c"]/w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i-20:i])/20
    v60 = sum(b["v"] for b in bs[i-60:i])/60
    vt = v20/v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9: return "ACCUM"
    if ret60 > 0.30 and vt > 1.3: return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1: return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"

def is_strong(title):
    is_ev, kind, pol, _a, _p = classify_title(title)
    return bool(is_ev and pol > 0)

recs = []
seen = set()
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for date, code, title in cur.fetchall():
    if not is_strong(title): continue
    code6 = str(code)[:6]
    d = str(date)[:10].replace("-", "")
    if (code6, d) in seen: continue
    seen.add((code6, d))
    bs = bars_of(code6)
    if not bs: continue
    dates = [b["t"] for b in bs]
    if d not in dates: continue
    i = dates.index(d)
    st = stage_of(bs, i)
    if st is None: continue
    adx = adx14(bs, i)
    adx_ok = (adx is not None and adx >= 20)
    entry_idx = i + 1
    if entry_idx + 17 >= len(bs) or entry_idx < 130: continue
    if bs[entry_idx]["t"] < "20230901": continue
    ep_open = bs[entry_idx]["o"]; disc_close = bs[i]["c"]
    if ep_open <= 0: continue
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
    ep = limit if bs[entry_idx]["l"] <= limit else ep_open
    tp1, tp2, tp3 = highs[0], (highs[1] if len(highs) > 1 else highs[0]*1.05), highs[-1]
    _atr = 0.0
    if i >= 15:
        _trs = []
        for _k in range(i-14, i):
            _trs.append(max(bs[_k]["h"]-bs[_k]["l"], abs(bs[_k]["h"]-bs[_k-1]["c"]), abs(bs[_k]["l"]-bs[_k-1]["c"])))
        _atr = sum(_trs)/14 if _trs else 0.0
    sl1 = (lows[0] - 0.5*_atr) if _atr > 0 else lows[0]*0.99
    _tps = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
    if not _tps: continue
    tp1 = _tps[0]; tp2 = _tps[1] if len(_tps) > 1 else tp1*1.05; tp3 = _tps[2] if len(_tps) > 2 else tp2*1.05
    r = _sim(bs, entry_idx, ep, sl1, tp1=tp1, tp2=tp2, tp3=tp3,
             partial_tp1=0.3, stop_to_be=True, max_hold=15, code=code6)
    if r.get("skipped"): continue
    recs.append({"s": code6, "d": d, "stage": st, "adx_ok": adx_ok,
                 "net": round(r.get("net_pnl_pct", 0.0), 4), "reason": r.get("reason", "")})

def stats(ts):
    if not ts: return None
    p = [t["net"] for t in ts]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(ts), "avg": round(sum(p)/len(p), 2), "wr": round(100*len(w)/len(p), 1),
            "pf": round(pf, 2), "sum": round(sum(p), 0)}

print("="*96)
print(f"stage 白名单放宽实验 (增持/回购, {len(recs)} 笔通过分类+入场+几何)")
print("基线口径: stage in (ACCUM,DOWNTREND) + adx>=20")
print("="*96)

# 按 stage 分桶(全部含 adx 条件与不含, 两种视角)
for adx_tag, filt in (("adx>=20(基线条件)", lambda t: t["adx_ok"]), ("不限 adx", lambda t: True)):
    print(f"\n--- {adx_tag} ---")
    print(f"{'stage':<12}{'n':>6}{'avg%':>9}{'胜率':>8}{'PF':>7}{'累计%':>9}{'IS_PF':>8}{'OOS_PF':>8}{'裁定':>10}")
    bys = defaultdict(list)
    for t in recs:
        if filt(t): bys[t["stage"]].append(t)
    for st in ("ACCUM", "DOWNTREND", "UPTREND", "MARKUP", "DISTRIB"):
        ts = bys.get(st, [])
        if not ts: continue
        s = stats(ts)
        is_t = [t for t in ts if t["d"] <= "20250630"]
        oos_t = [t for t in ts if t["d"] > "20250630"]
        si, so = stats(is_t), stats(oos_t)
        sip = si["pf"] if si else 0; sop = so["pf"] if so else 0
        ratio = (sop/sip) if sip else 0
        verdict = "✅晋级" if (so and sop > 1.5 and ratio > 0.5 and s["n"] >= 100) else ("n不足" if s["n"] < 100 else "❌")
        print(f"{st:<12}{s['n']:>6}{s['avg']:>+8.2f}%{s['wr']:>7.1f}%{s['pf']:>7.2f}{s['sum']:>+9.0f}{sip:>8.2f}{sop:>8.2f}{verdict:>10}")

# 全量(所有 stage, adx>=20) vs 基线
print("\n" + "="*96)
base_ts = [t for t in recs if t["stage"] in ("ACCUM","DOWNTREND") and t["adx_ok"]]
all_ts = [t for t in recs if t["adx_ok"]]
sb, sa = stats(base_ts), stats(all_ts)
print(f"基线(stage白名单): n={sb['n']} avg={sb['avg']:+.2f}% 胜率={sb['wr']}% PF={sb['pf']}")
print(f"放宽(全部stage)   : n={sa['n']} avg={sa['avg']:+.2f}% 胜率={sa['wr']}% PF={sa['pf']}")
print(f"增量: +{sa['n']-sb['n']} 笔 ({(sa['n']-sb['n'])/sb['n']*100:.0f}%), PF {sb['pf']}→{sa['pf']}")
print(f"参照: 冻结基线 CSV n=1640 PF3.20 (含 CONT 腿前的 EVENT 口径)")

json.dump(recs, open(os.path.join(HERE, "r38_stage_relax.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"\n→ r38_stage_relax.json ({len(recs)} 笔)")