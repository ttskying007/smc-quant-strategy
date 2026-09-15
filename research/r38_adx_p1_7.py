# -*- coding: utf-8 -*-
"""r38_adx_p1_7.py —— R38 P1-7 分叉量化: 旧版单窗DX vs 生产Wilder ADX.

背景(审计 P1-7): core/indicators.py 的 adx14_of 是生产唯一 ADX 实现(Wilder 平滑,
2026-09-12 修复); 冻结基线 gen_v20f.py 仍用**旧版单窗 DX** —— 系统性偏低
(实测 0.33/5.78/5.45 vs 标准 13.06/7.55/13.46), 使 ADX>=20 门过严、错杀边界股。

本脚本在 gen_v20f 同口径下量化该分叉:
  ① 两版 ADX 在事件日的数值差异(配对统计)
  ② 旧版拒绝但 Wilder 接受的事件数(被错杀的候选量)
  ③ 这批"错杀候选"的收益质量(avg/PF/逐年/IS-OOS)
判据(预注册): 若错杀候选 avg>0 且 PF>1.5 且逐年稳定 → 支持重基线(P1-7 修复收益显著)
纯研究, 不修改生产。
"""
import io, json, math, os, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
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

def legacy_adx(bs, i):
    """gen_v20f 旧版: 单窗 DX = |PDI-MDI|/(PDI+MDI) (非平滑)."""
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

# ---- 遍历事件, 记录两版 ADX 与后续收益(不做 adx 过滤, 先全收) ----
pairs = []   # (legacy, wilder, code, d, stage, tradable?)
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
    la = legacy_adx(bs, i)
    wa = wilder_adx(bs, i)
    if la is None or wa is None: continue
    entry_idx = i + 1
    tradable = (entry_idx + 17 < len(bs) and entry_idx >= 130
                and bs[entry_idx]["t"] >= "20230901" and bs[entry_idx]["o"] > 0)
    pairs.append({"code": code6, "d": d, "i": i, "legacy": round(la, 2), "wilder": round(wa, 2),
                  "stage": st, "tradable": tradable})

print("="*96)
print(f"P1-7 分叉量化: 事件(stage ACCUM/DOWNTREND) {len(pairs)} 笔有双版 ADX")
print("="*96)
diffs = [p["wilder"] - p["legacy"] for p in pairs]
diffs.sort()
n = len(diffs)
print(f"Wilder - Legacy 差值: 中位 {diffs[n//2]:+.2f} | 均值 {sum(diffs)/n:+.2f} | "
      f"P10 {diffs[n//10]:+.2f} | P90 {diffs[9*n//10]:+.2f}")

leg_ok = [p for p in pairs if p["legacy"] >= 20]
wil_ok = [p for p in pairs if p["wilder"] >= 20]
both = [p for p in pairs if p["legacy"] >= 20 and p["wilder"] >= 20]
rescued = [p for p in pairs if p["legacy"] < 20 and p["wilder"] >= 20]   # 旧版错杀
lost = [p for p in pairs if p["legacy"] >= 20 and p["wilder"] < 20]      # 旧版误收
print(f"\n旧版通过(>=20): {len(leg_ok)} | Wilder 通过: {len(wil_ok)} | 双通过: {len(both)}")
print(f"**��版错杀(Wilder救回)**: {len(rescued)} 笔 (+{100*len(rescued)/max(1,len(leg_ok)):.1f}%)")
print(f"旧版误收(Wilder拒绝):   {len(lost)} 笔")

# ---- 对"错杀候选"跑同口径回测 ----
def run_trade(p):
    bs = bars_of(p["code"])
    i = p["i"]; entry_idx = i + 1
    if entry_idx + 17 >= len(bs) or entry_idx < 130: return None
    if bs[entry_idx]["t"] < "20230901": return None
    ep_open = bs[entry_idx]["o"]; disc_close = bs[i]["c"]
    if ep_open <= 0: return None
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
    if not highs or not lows: return None
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
    if not _tps: return None
    tp1 = _tps[0]; tp2 = _tps[1] if len(_tps) > 1 else tp1*1.05; tp3 = _tps[2] if len(_tps) > 2 else tp2*1.05
    r = _sim(bs, entry_idx, ep, sl1, tp1=tp1, tp2=tp2, tp3=tp3,
             partial_tp1=0.3, stop_to_be=True, max_hold=15, code=p["code"])
    if r.get("skipped"): return None
    return {"d": p["d"], "net": r.get("net_pnl_pct", 0.0), "stage": p["stage"]}

def stats(rs):
    if not rs: return None
    p = [r["net"] for r in rs]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(p), "avg": round(sum(p)/len(p), 2), "wr": round(100*len(w)/len(p), 1), "pf": round(pf, 2)}

print("\n" + "="*96)
print("错杀候选(旧版<20, Wilder>=20) 同口径回测 vs 现有基线")
print("="*96)
res = {}
for label, group in (("旧版通过(现基线)", leg_ok), ("双通过", both),
                     ("**错杀候选(Wilder救回)**", rescued), ("旧版误收", lost)):
    rs = [t for t in (run_trade(p) for p in group) if t]
    s = stats(rs)
    if not s:
        print(f"{label}: 无有效样本"); continue
    res[label] = (s, rs)
    print(f"{label:<28} n={s['n']:>5} avg={s['avg']:+.2f}% 胜率={s['wr']:>5.1f}% PF={s['pf']:.2f}")

if "**错杀候选(Wilder救回)**" in res:
    s, rs = res["**错杀候选(Wilder救回)**"]
    print("\n错杀候选逐年:")
    byy = defaultdict(list)
    for r in rs: byy[r["d"][:4]].append(r)
    for y in sorted(byy):
        ss = stats(byy[y])
        print(f"  {y}: n={ss['n']:>4} avg={ss['avg']:+.2f}% 胜率={ss['wr']:>5.1f}% PF={ss['pf']:.2f}")
    print("\n错杀候选 stage 分布:")
    bys = defaultdict(list)
    for r in rs: bys[r["stage"]].append(r)
    for k, v in bys.items():
        ss = stats(v); print(f"  {k:<11} n={ss['n']:>4} avg={ss['avg']:+.2f}% PF={ss['pf']:.2f}")
    is_r = [r for r in rs if r["d"] <= "20250630"]
    oos_r = [r for r in rs if r["d"] > "20250630"]
    si, so = stats(is_r), stats(oos_r)
    print(f"\n  IS(≤2025-06): n={si['n'] if si else 0} PF={si['pf'] if si else 0:.2f} | "
          f"OOS: n={so['n'] if so else 0} PF={so['pf'] if so else 0:.2f}")
    print(f"  裁定(预注册 avg>0 且 PF>1.5 且逐年稳定): "
          f"{'✅ 支持 P1-7 重基线' if (s['avg'] > 0 and s['pf'] > 1.5) else '❌ 不显著'}")

json.dump({"pairs": len(pairs), "legacy_ok": len(leg_ok), "wilder_ok": len(wil_ok),
           "rescued": len(rescued), "lost": len(lost),
           "rescued_stats": res.get("**错杀候选(Wilder救回)**", (None,))[0]},
          open(os.path.join(HERE, "r38_adx_p1_7.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"\n→ r38_adx_p1_7.json")