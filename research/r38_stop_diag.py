# -*- coding: utf-8 -*-
"""r38_stop_diag.py —— 止损有效性 + 扫损检验(直击"盈亏比差"痛点).

字段语义(已抽样确认):
  buy_price/sl/tp   入场价/止损价/目标价
  risk_pct          SL 距离 %(买价->SL), 中位 11.88%, p75 27.52%  <-- 极宽
  mae_r / mfe_r     最大不利/有利偏移(R 计); 负=不利方向, 正=有利方向
  hold_bars         持仓 K 线数
  rr_exit           退出 R 倍数
  reason            TIME_STOP/TP2_RUNNER/SL_HIT/SL_GAP/BE

核心问题(逐笔):
  ① 止损距离分布 —— 是否"名义止损"(太宽以致很少触发)?
  ② **扫损检验**: SL_HIT 的 232 笔在被打掉前 mfe_r 多大?
     若 mfe_r 普遍高 → 曾浮盈后被扫 → 止损位置/结构问题(SMC 流动性扫荡)
     若 mfe_r 普遍低 → 一入场就错 → 是**择时/选股**问题, 不是止损问题
  ③ MFE 未兑现分析: 所有交易的最大浮盈 vs 最终收益(盈亏比差的直接量化)
  ④ 止损距离 × 结果 交叉(找最优区间)
  ⑤ 持仓 K 线 × 出场类型

判据(预注册): 若 SL_HIT 的 mfe_r 中位 < 0.5R → 止损不是主要问题(属择时);
            若 > 1.0R → 存在系统性扫损, 止损位置值得重设计。
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


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


ev = [r for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"),
                                    encoding="utf-8-sig")) if r.get("src") == "EVENT"]


def stats(rs, key="net_pnl_pct"):
    if not rs:
        return None
    p = [f(r[key]) for r in rs]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


def med(v):
    if not v:
        return 0.0
    v = sorted(v)
    return v[len(v) // 2]


print("=" * 100)
print("① 止损距离(risk_pct)分布 —— 是否名义止损")
print("=" * 100)
rp = [f(r.get("risk_pct")) for r in ev if f(r.get("risk_pct")) > 0]
print("  n=%d | min=%.2f p10=%.2f p25=%.2f 中位=%.2f p75=%.2f p90=%.2f max=%.2f"
      % (len(rp), min(rp), sorted(rp)[int(len(rp) * .1)], sorted(rp)[int(len(rp) * .25)],
         med(rp), sorted(rp)[int(len(rp) * .75)], sorted(rp)[int(len(rp) * .9)], max(rp)))
print("\n  按止损距离分桶(看哪段最优):")
print("  %-12s %6s %10s %8s %8s %10s %10s" % ("距离%", "n", "avg%", "wr", "PF", "实际触发SL", "TIME占比"))
for lo, hi in [(0, 3), (3, 6), (6, 10), (10, 15), (15, 25), (25, 40), (40, 999)]:
    sub = [r for r in ev if lo <= f(r.get("risk_pct")) < hi]
    s = stats(sub)
    if not s:
        continue
    sl_n = sum(1 for r in sub if (r.get("reason") or "").startswith("SL"))
    tm_n = sum(1 for r in sub if (r.get("reason") or "") == "TIME_STOP")
    print("  %-12s %6d %+9.2f%% %7.1f%% %8.2f %9.1f%% %9.1f%%"
          % ("[%g,%g)" % (lo, hi), s["n"], s["avg"], s["wr"], s["pf"],
             100 * sl_n / s["n"], 100 * tm_n / s["n"]))

print("\n" + "=" * 100)
print("② 扫损检验(SL_HIT 被打掉前的最大浮盈 mfe_r)")
print("=" * 100)
sl_hit = [r for r in ev if (r.get("reason") or "") == "SL_HIT"]
sl_gap = [r for r in ev if (r.get("reason") or "") == "SL_GAP"]
print("  SL_HIT n=%d | SL_GAP n=%d" % (len(sl_hit), len(sl_gap)))
for lab, grp in (("SL_HIT", sl_hit), ("SL_GAP", sl_gap)):
    if not grp:
        continue
    mfe = [f(r.get("mfe_r")) for r in grp]
    mae = [abs(f(r.get("mae_r"))) for r in grp]
    print("  %s: mfe_r 中位=%.3f 均值=%.3f | mae_r 中位=%.3f | hold_bars 中位=%d"
          % (lab, med(mfe), sum(mfe) / len(mfe), med(mae),
             med([f(r.get("hold_bars")) for r in grp])))
    # 关键分档: 曾浮盈多少才被打掉
    print("     mfe_r 分档(曾浮盈多少):")
    for lo, hi in [(-99, 0), (0, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 99)]:
        n = sum(1 for x in mfe if lo <= x < hi)
        if n:
            print("       [%g,%g) %4d (%.1f%%)" % (lo, hi, n, 100 * n / len(mfe)))
    # 曾浮盈 >0.5R 的比例(扫损嫌疑)
    susp = sum(1 for x in mfe if x > 0.5)
    print("     **曾浮盈 >0.5R 后被打掉: %d / %d = %.1f%%**"
          % (susp, len(mfe), 100 * susp / len(mfe)))

print("\n" + "=" * 100)
print("③ MFE 未兑现分析 —— 盈亏比差的直接量化")
print("=" * 100)
all_mfe = [(f(r.get("mfe_r")), f(r.get("rr_exit")), r) for r in ev]
mfe_vals = [x[0] for x in all_mfe]
rr_vals = [x[1] for x in all_mfe]
print("  全体 mfe_r: 中位=%.2f 均值=%.2f | rr_exit: 中位=%.2f 均值=%.2f"
      % (med(mfe_vals), sum(mfe_vals) / len(mfe_vals), med(rr_vals), sum(rr_vals) / len(rr_vals)))
print("  **未兑现率(每笔) = (mfe_r - rr_exit)**:")
unc = [a - b for a, b in zip(mfe_vals, rr_vals)]
print("    中位=%.2f 均值=%.2f  (正=曾有浮盈未拿到)" % (med(unc), sum(unc) / len(unc)))
print("\n  高浮盈但收益平庸的交易(>2R 浮盈):")
for lo, hi in [(2, 3), (3, 5), (5, 99)]:
    sub = [x[2] for x in all_mfe if lo <= x[0] < hi]
    s = stats(sub)
    if s:
        rr_m = med([f(r.get("rr_exit")) for r in sub])
        print("    mfe_r [%g,%g): n=%4d 最终 avg=%+.2f%% PF=%.2f | 兑现 rr 中位=%.2f (浮盈中位=%.2f)"
              % (lo, hi, s["n"], s["avg"], s["pf"], rr_m, med([f(r.get("mfe_r")) for r in sub])))

print("\n" + "=" * 100)
print("④ 持仓 K 线 × 出场类型")
print("=" * 100)
print("  %-14s %6s %12s %12s %10s" % ("出场类型", "n", "hold中位", "hold均值", "avg%"))
by = defaultdict(list)
for r in ev:
    by[r.get("reason") or "?"].append(r)
for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    hb = [f(x.get("hold_bars")) for x in v]
    s = stats(v)
    print("  %-14s %6d %12d %12.1f %+9.2f%%" % (k, s["n"], med(hb), sum(hb) / len(hb), s["avg"]))

print("\n" + "=" * 100)
print("⑤ 按 hold_bars 分档(是否过早/过晚)")
print("=" * 100)
print("  %-10s %6s %10s %8s %8s %10s" % ("持仓K线", "n", "avg%", "wr", "PF", "SL占比"))
for lo, hi in [(0, 2), (2, 4), (4, 6), (6, 9), (9, 12), (12, 99)]:
    sub = [r for r in ev if lo <= f(r.get("hold_bars")) < hi]
    s = stats(sub)
    if not s:
        continue
    sl_n = sum(1 for r in sub if (r.get("reason") or "").startswith("SL"))
    print("  %-10s %6d %+9.2f%% %7.1f%% %8.2f %9.1f%%"
          % ("[%g,%g)" % (lo, hi), s["n"], s["avg"], s["wr"], s["pf"], 100 * sl_n / s["n"]))

print("\n" + "=" * 100)
print("裁定")
print("=" * 100)
if sl_hit:
    m = med([f(r.get("mfe_r")) for r in sl_hit])
    susp = 100 * sum(1 for r in sl_hit if f(r.get("mfe_r")) > 0.5) / len(sl_hit)
    print("  SL_HIT 的 mfe_r 中位 = %.3f | 曾浮盈>0.5R 后被打掉 = %.1f%%" % (m, susp))
    if m < 0.5:
        print("  → **止损不是主要问题**: 被止损的交易大多一入场就错(mfe_r 低)")
        print("     属**择时/选股**问题, 非止损位置问题 → 退出层改动收益有限")
    else:
        print("  → **存在系统性扫损**: 止损位置值得重设计(SMC 流动性扫荡视角)")
print("  未兑现率中位 = %.2fR (每笔曾有浮盈但未拿到)" % med([a - b for a, b in zip(mfe_vals, rr_vals)]))