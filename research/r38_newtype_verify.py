# -*- coding: utf-8 -*-
"""r38_newtype_verify.py —— R38 新事件类型稳健性检验(R38h 纪律: 先 OOS 再结论).

r38_event_newtype_test 筛出 3 个候选(业绩预增 20日+5.15%/PF3.02、
股权激励授予 +3.43%/2.05、业绩预减 +3.08%/1.91)。但技术腿教训表明
全样本 PF 可能全是单年产物 —— 本脚本对候选做强制检验:

 ① 去重: 同一 (code, 公告日) 只计一次(避免预告修正公告重复计数)
 ② IS/OOS 分段(与技术腿同口径: IS≤2025-06-30, OOS>2025-06-30)
 ③ 逐年
 ④ 月度分布(业绩预告有强季节性, 检验是否集中在个别月)
 ⑤ 覆盖率(公告数 vs 可回测数, 检验样本选择偏差)

判据(预注册): 晋级需 OOS PF > 1.5 且 OOS/IS PF 比 > 0.5 且 逐年无负数年。
纯研究, 不修改生产。
"""
import io, json, os, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
HERE = r"E:\test\smc_project\research"
code2file = {f.split("_")[0]: f for f in os.listdir(KT) if f.endswith("_daily_800.json")}
_bars = {}
def bars_of(code):
    if code not in _bars:
        fn = code2file.get(code)
        if not fn:
            _bars[code] = []
            return _bars[code]
        raw = json.load(open(os.path.join(KT, fn), encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "c": float(r["c"])})
        bs.sort(key=lambda b: b["t"])
        _bars[code] = bs
    return _bars[code]

def stats(rets):
    if not rets: return None
    w = [x for x in rets if x > 0]; l = [x for x in rets if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(rets), "avg": sum(rets)/len(rets), "wr": 100*len(w)/len(rets), "pf": pf}

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
GROUPS = [
    ("业绩预增", "title LIKE '%业绩预增%'"),
    ("业绩预减", "title LIKE '%业绩预减%' OR title LIKE '%业绩预亏%'"),
    ("股权激励授予", "title LIKE '%股权激励%' AND title LIKE '%授予%'"),
]
IS_END = "20250630"
HOLD = 20

for name, where in GROUPS:
    cur.execute(f"SELECT date, stock_code FROM announce WHERE date >= '2023-09-01' AND ({where})")
    rows = cur.fetchall()
    seen = set(); recs = []; miss = 0
    for d8, code in rows:
        code6 = str(code)[:6]
        d = str(d8).replace("-", "")[:8]
        if (code6, d) in seen:      # 去重
            continue
        seen.add((code6, d))
        bs = bars_of(code6)
        if not bs:
            miss += 1
            continue
        idx = next((i for i, b in enumerate(bs) if b["t"] == d), None)
        if idx is None or idx + HOLD + 1 >= len(bs):
            continue
        ep = bs[idx + 1]["o"]
        if ep <= 0: continue
        recs.append({"d": d, "ret": (bs[idx + 1 + HOLD]["c"]/ep - 1)*100})
    if not recs:
        print(f"\n{name}: 无样本"); continue
    allr = [r["ret"] for r in recs]
    is_r = [r["ret"] for r in recs if r["d"] <= IS_END]
    oos_r = [r["ret"] for r in recs if r["d"] > IS_END]
    print("="*88)
    print(f"{name}  (公告 {len(rows)} 条, 去重后 {len(seen)}, 可回测 {len(recs)}, K线缺失 {miss})")
    print(f"  覆盖: 去重后缺失率 {100*miss/max(1,len(seen)):.1f}% —— 高缺失=样本选择偏差风险")
    sa, si, so = stats(allr), stats(is_r), stats(oos_r)
    print(f"  全样本: n={sa['n']} avg={sa['avg']:+.2f}% WR={sa['wr']:.1f}% PF={sa['pf']:.2f}")
    print(f"  IS    : n={si['n'] if si else 0} avg={si['avg']:+.2f}% WR={si['wr']:.1f}% PF={si['pf']:.2f}" if si else "  IS: 无")
    print(f"  OOS   : n={so['n'] if so else 0} avg={so['avg']:+.2f}% WR={so['wr']:.1f}% PF={so['pf']:.2f}" if so else "  OOS: 无")
    if si and so:
        ratio = so["pf"]/si["pf"] if si["pf"] else 0
        verdict = "✅ 晋级候选" if (so["pf"] > 1.5 and ratio > 0.5) else "❌ 否决(OOS 不过线)"
        print(f"  OOS/IS PF 比 = {ratio:.2f}  → {verdict}")
    byy = defaultdict(list)
    for r in recs: byy[r["d"][:4]].append(r["ret"])
    print("  逐年: " + " | ".join(
        f"{y}: n={len(ps)} {sum(ps)/len(ps):+.2f}%" for y, ps in sorted(byy.items())))
    bym = defaultdict(list)
    for r in recs: bym[r["d"][4:6]].append(r["ret"])
    top = sorted(bym.items(), key=lambda kv: -len(kv[1]))[:4]
    print("  月集中度: " + " | ".join(f"{m}月 n={len(ps)} {sum(ps)/len(ps):+.1f}%" for m, ps in top))