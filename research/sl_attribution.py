# -*- coding: utf-8 -*-
"""止损归因分析（审计方向4测试）：SL_HIT 交易中多少是"结构未真正失效但被扫损"。
数据源: handover/最新回测数据/逐笔交易全明细.json（4783 笔，含 mfe_r/mae_r/rr_exit/reason）
方法:
  ① SL_HIT 全体分布（mfe_r 事后分布）
  ② "被扫损后方向恢复" = SL_HIT 且 mfe_r >= 1.0（止损后本可到 1R+ —— SL 过紧证据）
  ③ 分腿(EVENT/SMC)统计，输出占比与建议
"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC = r"E:\test\smc_project\research\handover\最新回测数据\逐笔交易全明细.json"
d = json.load(open(SRC, encoding="utf-8"))
trades = d.get("trades") or []
print(f"总交易: {len(trades)}")

from collections import Counter
reason_dist = Counter(t.get("reason") for t in trades)
print("离场分布:", dict(reason_dist.most_common(8)))

def attr(leg):
    ts = [t for t in trades if t.get("leg") == leg and t.get("reason") == "SL_HIT"]
    if not ts:
        return None
    n = len(ts)
    # mfe_r: 入场后最大有利偏移(R 倍数)。SL_HIT 后 mfe_r>=1.0 = 止损前/后曾到 1R+（结构未失效，SL 扫损）
    recovered = [t for t in ts if (t.get("mfe_r") or 0) >= 1.0]
    partial = [t for t in ts if 0.3 <= (t.get("mfe_r") or 0) < 1.0]
    never = [t for t in ts if (t.get("mfe_r") or 0) < 0.3]
    avg_mfe = sum(t.get("mfe_r") or 0 for t in ts) / n
    avg_net = sum(t.get("net_pnl_pct") or 0 for t in ts) / n
    return {"n_sl": n, "recovered_ge_1r": len(recovered), "pct_recovered": round(len(recovered) / n * 100, 1),
            "partial_03_1r": len(partial), "never_lt_03r": len(never),
            "avg_mfe_r": round(avg_mfe, 2), "avg_net": round(avg_net, 2)}

out = {}
for leg in ("EVENT", "SMC"):
    a = attr(leg)
    if a:
        out[leg] = a
        print(f"\n== {leg} 腿 SL_HIT 归因 ==")
        print(f"  SL 单数: {a['n_sl']}")
        print(f"  被扫损后方向恢复(MFE≥1R): {a['recovered_ge_1r']} ({a['pct_recovered']}%)  ← SL 过紧证据")
        print(f"  部分恢复(0.3≤MFE<1R): {a['partial_03_1r']}")
        print(f"  从未恢复(MFE<0.3R): {a['never_lt_03r']}  ← 结构真失效，SL 正确")
        print(f"  SL 单平均 MFE_R: {a['avg_mfe_r']} | 平均净收益: {a['avg_net']}%")

# 审计阈值: 反馈说 ">30% 说明 TP/SL 设计是主要亏损来源"
all_sl = [t for t in trades if t.get("reason") == "SL_HIT" and (t.get("mfe_r") or 0) >= 1.0]
n_sl_all = len([t for t in trades if t.get("reason") == "SL_HIT"])
pct_all = round(len(all_sl) / n_sl_all * 100, 1) if n_sl_all else 0
print(f"\n== 全体 ==")
print(f"  SL_HIT: {n_sl_all} | 其中 MFE≥1R(被扫损后恢复): {len(all_sl)} ({pct_all}%)")
print(f"  审计线: >30% 为 SL 设计问题主导 → {'⚠ 超线，SL 过紧是主要亏损来源' if pct_all > 30 else '✅ 未超线，SL 设计非主要亏损来源'}")

out["overall"] = {"n_sl": n_sl_all, "recovered_ge_1r": len(all_sl), "pct": pct_all,
                  "audit_line": 30, "exceed": pct_all > 30}
out["generated_at"] = __import__("time").strftime("%Y-%m-%d %H:%M:%S")
with open(r"E:\test\smc_project\research\handover\止损归因分析.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("已写 handover/止损归因分析.json")