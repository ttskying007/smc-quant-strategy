# -*- coding: utf-8 -*-
"""r38_exit_diag.py —— 出场结构逐笔诊断(针对"盈亏比差"痛点).

背景: 目标三大痛点为「选股量少 / 选股不准 / 盈亏比差」。R38 循环已充分勘探
筛选层(扩池/stage/rank)与仓位层(加权/门槛), 但**退出层结构**只做过参数扫描
(§97.x "退出参数: 现有结构局部最优"), 未做逐笔诊断。

基线出场构成(新基线 EVENT n=1527):
  TIME_STOP   n= 793 (51.9%) avg=+6.32% wr=79.6%
  TP2_RUNNER  n= 241 (15.8%) avg=+8.86% wr=98.8%
  SL_HIT      n= 232 (15.2%) avg=-5.08% wr= 0.0%
  SL_GAP      n= 132 ( 8.6%) avg=-2.49% wr=15.2%
  BE          n= 129 ( 8.4%) avg=+0.88% wr=83.7%
→ 止损盘合计 364 笔(23.8%), 是亏损的全部来源。

本脚本(纯 CSV, 廉价)诊断:
  ① CSV 列清单与可用字段
  ② SL 距离分布(相对入场价) —— 是否过紧/过宽
  ③ SL 距离 × 结果 交叉(找最优区间)
  ④ RR 分布与实现率
  ⑤ 出场类型 × rank 交叉(低 rank 是否更易被止损)
  ⑥ 持仓天数 × 出场类型

判据(预注册): 若某 SL 距离区间同时改善 avg 与 PF, 且跨 IS/OOS 成立, 才进入
下一阶段(K 线级"被打掉后是否反弹"检验)。本轮只做诊断, 不做结论。
纯研究, 不修改生产。
"""
import csv
import io
import os
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
IS_END = "20250630"
PATH = os.path.join(HERE, "combo_v20f_trades.csv")


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


rows = list(csv.DictReader(open(PATH, encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]

print("=" * 100)
print("① CSV 字段清单(判断可用维度)")
print("=" * 100)
print("总行数 %d | EVENT %d | 列数 %d" % (len(rows), len(ev), len(rows[0]) if rows else 0))
print("列名: %s" % ", ".join(sorted(rows[0].keys())))
print("\n非空率(对 EVENT):")
for c in sorted(rows[0].keys()):
    n = sum(1 for r in ev if r.get(c) not in (None, "", "None"))
    if n:
        print("  %-22s %4d / %d (%.1f%%)" % (c, n, len(ev), 100 * n / len(ev)))


def stats(rs, key="net_pnl_pct"):
    if not rs:
        return None
    p = [f(r[key]) for r in rs]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


# ── ② SL 距离分布(需 sl_price + entry_price) ──
print("\n" + "=" * 100)
print("② SL 距离分布(入场价 -> 止损价)")
print("=" * 100)
has_sl = all(c in rows[0] for c in ("sl_price", "entry_price"))
if not has_sl:
    print("  缺 sl_price/entry_price 字段 —— 尝试从其他列推断")
    cand = [c for c in rows[0] if "sl" in c.lower() or "entry" in c.lower()
            or "price" in c.lower() or "dist" in c.lower()]
    print("  候选列: %s" % (cand or "(无)"))
else:
    dist = []
    for r in ev:
        ep = f(r.get("entry_price"))
        sl = f(r.get("sl_price"))
        if ep > 0 and sl > 0 and sl < ep:
            dist.append((abs(ep - sl) / ep * 100, r))
    if dist:
        vals = sorted(d for d, _ in dist)
        n = len(vals)
        print("  可算笔数 %d / %d" % (n, len(ev)))
        print("  SL 距离(%%): min=%.2f  p10=%.2f  p25=%.2f  中位=%.2f  p75=%.2f  p90=%.2f  max=%.2f"
              % (vals[0], vals[int(n * .1)], vals[int(n * .25)], vals[n // 2],
                 vals[int(n * .75)], vals[int(n * .9)], vals[-1]))
        print("\n  按 SL 距离分桶:")
        BINS = [(0, 2), (2, 3), (3, 4), (4, 5), (5, 7), (7, 10), (10, 999)]
        print("  %-12s %6s %10s %8s %8s %10s" % ("距离区间", "n", "avg%", "wr", "PF", "止损占比"))
        for lo, hi in BINS:
            sub = [r for d, r in dist if lo <= d < hi]
            s = stats(sub)
            if not s:
                continue
            sl_n = sum(1 for r in sub if (r.get("reason") or "").startswith("SL"))
            print("  %-12s %6d %+9.2f%% %7.1f%% %8.2f %9.1f%%"
                  % ("[%g,%g)" % (lo, hi), s["n"], s["avg"], s["wr"], s["pf"],
                     100 * sl_n / s["n"]))

# ── ③ 出场类型 × rank ──
print("\n" + "=" * 100)
print("③ 出场类型 × rank(低 rank 是否更易被止损)")
print("=" * 100)
RANKS = sorted({int(f(r.get("rank"))) for r in ev if r.get("rank")})
print("%-6s %6s %10s %10s %10s %10s %8s" % ("rank", "n", "SL占比", "SL_HIT", "GAP", "TIME", "avg%"))
for rk in RANKS:
    sub = [r for r in ev if int(f(r.get("rank"))) == rk]
    if not sub:
        continue
    s = stats(sub)
    sl = sum(1 for r in sub if (r.get("reason") or "") == "SL_HIT")
    gp = sum(1 for r in sub if (r.get("reason") or "") == "SL_GAP")
    tm = sum(1 for r in sub if (r.get("reason") or "") == "TIME_STOP")
    print("%-6d %6d %9.1f%% %9.1f%% %9.1f%% %9.1f%% %+7.2f%%"
          % (rk, s["n"], 100 * (sl + gp) / s["n"], 100 * sl / s["n"],
             100 * gp / s["n"], 100 * tm / s["n"], s["avg"]))

# ── ④ RR 分布与实现率 ──
print("\n" + "=" * 100)
print("④ RR 分布与实现率(rr_exit)")
print("=" * 100)
rr = [f(r.get("rr_exit")) for r in ev if r.get("rr_exit") not in (None, "", "None")]
if rr:
    rr.sort()
    n = len(rr)
    print("  可算 %d 笔 | min=%.2f p25=%.2f 中位=%.2f p75=%.2f max=%.2f"
          % (n, rr[0], rr[int(n * .25)], rr[n // 2], rr[int(n * .75)], rr[-1]))
    print("  <=-1R %.1f%% | -1~0R %.1f%% | 0~1R %.1f%% | >=1R %.1f%% | >=2R %.1f%%"
          % (100 * sum(1 for x in rr if x <= -1) / n,
             100 * sum(1 for x in rr if -1 < x <= 0) / n,
             100 * sum(1 for x in rr if 0 < x < 1) / n,
             100 * sum(1 for x in rr if x >= 1) / n,
             100 * sum(1 for x in rr if x >= 2) / n))
    # 按 RR 分桶看收益
    print("\n  RR 分桶:")
    for lo, hi in [(-99, -1), (-1, 0), (0, 1), (1, 2), (2, 3), (3, 99)]:
        sub = [r for r in ev if r.get("rr_exit") not in (None, "", "None")
               and lo <= f(r.get("rr_exit")) < hi]
        s = stats(sub)
        if s:
            print("    [%g,%g) n=%4d avg=%+.2f%% PF=%.2f" % (lo, hi, s["n"], s["avg"], s["pf"]))

# ── ⑤ 持仓天数 × 出场类型 ──
print("\n" + "=" * 100)
print("⑤ 持仓天数 × 出场类型")
print("=" * 100)
for c in ("hold_days", "days", "exit_date"):
    if c in rows[0]:
        print("  发现字段: %s" % c)
if "exit_date" in rows[0] and "entry_date" in rows[0]:
    import datetime as dt

    def d2(s):
        s = str(s).replace("-", "")[:8]
        try:
            return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except Exception:
            return None

    spans = defaultdict(list)
    for r in ev:
        a, b = d2(r.get("entry_date")), d2(r.get("exit_date"))
        if a and b:
            spans[r.get("reason") or "?"].append((b - a).days)
    print("  %-14s %6s %10s %10s" % ("出场类型", "n", "中位天数", "均值天数"))
    for k, v in sorted(spans.items(), key=lambda kv: -len(kv[1])):
        v.sort()
        print("  %-14s %6d %10d %10.1f" % (k, len(v), v[len(v) // 2], sum(v) / len(v)))
else:
    print("  缺 entry_date/exit_date 之一, 跳过")

# ── ⑥ IS/OOS 分段确认止损盘规模 ──
print("\n" + "=" * 100)
print("⑥ 止损盘 IS/OOS 分段")
print("=" * 100)
for lab, lo, hi in (("IS", "0", IS_END), ("OOS", IS_END + "1", "99999999")):
    sub = [r for r in ev if lo <= str(r.get("entry_date")) <= hi]
    sl = [r for r in sub if (r.get("reason") or "").startswith("SL")]
    s_all, s_sl = stats(sub), stats(sl)
    if s_all and s_sl:
        print("  %-4s 全 %d 笔 avg=%+.2f%% PF=%.2f | 止损盘 %d 笔(%.1f%%) avg=%+.2f%%"
              % (lab, s_all["n"], s_all["avg"], s_all["pf"],
                 s_sl["n"], 100 * s_sl["n"] / s_all["n"], s_sl["avg"]))

print("\n" + "=" * 100)
print("注: 本脚本仅诊断。任何退出结构改动须经 K 线级检验(被打掉后是否反弹)")
print("    + 全链路重放 + IS/OOS, 才可进入候选。")
print("=" * 100)