# -*- coding: utf-8 -*-
"""r38_exit_sweep.py —— R38 退出参数扫描(收敛判断后的最后一类杠杆).

背景: R38 已测试 10+ 信号层假设(技术腿/事件扩池/stage/rank/C1) 全部否决,
收敛判断指向"剩余空间在仓位管理与执行"。退出结构正是执行层核心, 且审计
P1-8 已标注分叉: 冻结基线 max_hold=15 vs 生产 CFG.MAX_HOLD=12。

本脚本在 gen_v20f 同口径下扫描退出参数(入场/SL/TP 不变, 仅退出规则变化):
  A 基线        max_hold=15, partial=0.3, stop_to_be=True
  B 生产口径    max_hold=12 (同 A 其余)
  C 短持有      max_hold=10
  D 长持有      max_hold=20
  E 无部分止盈  partial_tp1=0.0
  F 重部分止盈  partial_tp1=0.5
  G 不保本      stop_to_be=False

判据(预注册): 变体晋级需 ①PF 不低于基线 ②MDD 不劣于基线×1.1 ③IS/OOS 双段一致
纯研究, 不修改生产。
"""
import io, json, os, sqlite3, sys
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

def adx14(bs, i):
    if i < 30: return None
    pd = md = ts = 0.0
    for k in range(i-14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k-1]["c"]
        up = h - bs[k-1]["h"]; dn = bs[k-1]["l"] - l
        pd += up if (up > dn and up > 0) else 0
        md += dn if (dn > up and dn > 0) else 0
        ts += max(h-l, abs(h-pc), abs(l-pc))
    if ts <= 0: return None
    pdi = 100*pd/ts; mdi = 100*md/ts
    if pdi+mdi == 0: return None
    return 100*abs(pdi-mdi)/(pdi+mdi)

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

# ---- 收集候选(入场/几何条件与基线同) ----
cands = []
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
    if st not in ("ACCUM", "DOWNTREND"): continue
    adx = adx14(bs, i)
    if adx is None or adx < 20: continue
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
    cands.append({"code": code6, "d": d, "i": entry_idx, "ep": ep, "sl": sl1,
                  "tp1": tp1, "tp2": tp2, "tp3": tp3})
print(f"候选(基线口径过滤后): {len(cands)}")

CONFIGS = {
    "A 基线(15/0.3/保本)":   dict(max_hold=15, partial_tp1=0.3, stop_to_be=True),
    "B 生产口径(12)":        dict(max_hold=12, partial_tp1=0.3, stop_to_be=True),
    "C 短持有(10)":          dict(max_hold=10, partial_tp1=0.3, stop_to_be=True),
    "D 长持有(20)":          dict(max_hold=20, partial_tp1=0.3, stop_to_be=True),
    "E 无部分止盈":          dict(max_hold=15, partial_tp1=0.0, stop_to_be=True),
    "F 重部分止盈(0.5)":     dict(max_hold=15, partial_tp1=0.5, stop_to_be=True),
    "G 不保本":              dict(max_hold=15, partial_tp1=0.3, stop_to_be=False),
}
results = {}
for name, cfg in CONFIGS.items():
    recs = []
    for c in cands:
        bs = bars_of(c["code"])
        r = _sim(bs, c["i"], c["ep"], c["sl"], tp1=c["tp1"], tp2=c["tp2"], tp3=c["tp3"],
                 partial_tp1=cfg["partial_tp1"], stop_to_be=cfg["stop_to_be"],
                 max_hold=cfg["max_hold"], code=c["code"])
        if r.get("skipped"): continue
        recs.append({"d": c["d"], "net": r.get("net_pnl_pct", 0.0), "reason": r.get("reason", "")})
    results[name] = recs

def stats(rs):
    if not rs: return None
    p = [r["net"] for r in rs]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    eq = 0.0; peak = 0.0; mdd = 0.0
    for x in p:
        eq += x; peak = max(peak, eq); mdd = min(mdd, eq-peak)
    return {"n": len(p), "avg": round(sum(p)/len(p), 2), "wr": round(100*len(w)/len(p), 1),
            "pf": round(pf, 2), "mdd": round(mdd, 0), "sum": round(sum(p), 0)}

print("\n" + "="*100)
print("退出参数扫描 (入场/SL/TP 不变, 仅退出规则变化)")
print("="*100)
print(f"{'配置':<22}{'n':>6}{'avg%':>9}{'胜率':>8}{'PF':>7}{'MDD%':>9}{'累计%':>9}{'IS_PF':>8}{'OOS_PF':>8}")
rows = []
for name in CONFIGS:
    rs = results[name]; s = stats(rs)
    is_r = [r for r in rs if r["d"] <= "20250630"]
    oos_r = [r for r in rs if r["d"] > "20250630"]
    si, so = stats(is_r), stats(oos_r)
    sip = si["pf"] if si else 0; sop = so["pf"] if so else 0
    print(f"{name:<22}{s['n']:>6}{s['avg']:>+8.2f}%{s['wr']:>7.1f}%{s['pf']:>7.2f}{s['mdd']:>9.0f}{s['sum']:>+9.0f}{sip:>8.2f}{sop:>8.2f}")
    rows.append((name, s, sip, sop))

base = rows[0][1]
print("\n裁定 (预注册: PF>=基线 且 MDD 不劣于基线×1.1 且 IS/OOS 一致):")
for name, s, sip, sop in rows:
    if name.startswith("A "): continue
    ok_pf = s["pf"] >= base["pf"]
    ok_mdd = s["mdd"] >= base["mdd"] * 1.1
    ok_seg = sip >= base["pf"]*0.9 and sop >= base["pf"]*0.9
    verdict = "✅晋级" if (ok_pf and ok_mdd and ok_seg) else "❌"
    print(f"  {name:<22} PF{'↑' if ok_pf else '↓'}({s['pf']:.2f}) MDD{'↑' if ok_mdd else '↓'}({s['mdd']:.0f}) "
          f"IS/OOS({sip:.2f}/{sop:.2f}) → {verdict}")

print("\n出场原因构成(A 基线 vs B 生产口径):")
for nm in ("A 基线(15/0.3/保本)", "B 生产口径(12)"):
    by = defaultdict(int)
    for r in results[nm]: by[r["reason"] or "?"] += 1
    tot = sum(by.values())
    print(f"  {nm}: " + " ".join(f"{k}={v}({100*v/tot:.0f}%)" for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:5]))

json.dump({k: stats(v) for k, v in results.items()},
          open(os.path.join(HERE, "r38_exit_sweep.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"\n→ r38_exit_sweep.json")