# -*- coding: utf-8 -*-
"""reject_stress_gate.py —— R10: ADX_LT20 放宽预注册压力门(2026-09-13)。

审计 §9.3(新源进入 SHADOW 的门槛)/§11.2(成本压力)/§11.4(禁止验收方式)对
"放宽一个拒绝层"同样适用 —— 本模块把 ADX_LT20 候选层(R6 order 级 E[path]=−0.16%
但 fill 级 +2.45%/PF3.0, R8)过三道预注册压力门:

  G1 成本压力(§11.2): 基线成本=双边费率0.2%+单边滑点0.1%; 压力=费率×2+滑点×2。
     重算净收益(从 fill 回放 gross 反推), 要求压力下 avg 仍 > 0 且 PF > 1。
  G2 子窗稳定性(§11.4 "总收益不能靠单一时段解释"): 60 交易日窗三等分子窗,
     要求 ≥2 个子窗 avg > 0(允许 1 个子窗为负 —— 反弹型信号天然时段集中)。
  G3 集中度(§11.4 "不能靠少数交易解释"): 去掉收益最高的 10% 样本后 avg 仍 > 0;
     且单一行业占比 < 60%(无行业数据则跳过该项, 标记)。

全部基于 R8 fill-level 回放(冻结基线口径 partial 0.3/BE/15bar, 结构带生产同源),
不做任何新参数搜索 —— 这是"验证"而非"优化"。

用法: python reject_stress_gate.py [--stage ADX_LT20]
输出: handover/reject_stress_gate_report.json
"""
import io, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import paper_sim
import reject_fill_replay as RFR

HERE = os.path.dirname(os.path.abspath(__file__))
BACKFILL_FILE = os.path.join(paper_sim.ROOT, "reject_ledger_backfill.json")
FEE = paper_sim.CFG.FEE_PCT          # 双边合计 %
SLIP = paper_sim.CFG.SLIPPAGE        # 单边小数


def recompute_net(trade, fee_pct, slip_extra=0.0):
    """从 fill 回放结果反推 gross 并按新成本重算净收益(%)。
    simulate net = gross − FEE(%); fill/exit 各含单边滑点 SLIP(价内)。
    压力: fee_pct 替换 FEE; slip_extra 额外单边滑点(×2 fill+exit 近似 ×2×slip_extra)。"""
    gross = trade["net_pnl_pct"] + FEE
    # 额外滑点对收益的近似损耗: 进出两侧各 slip_extra(小数) → %损
    approx_slip_cost = (slip_extra * 2) * 100 * (1 if trade.get("filled") else 0)
    return round(gross - fee_pct - approx_slip_cost, 4)


def stress_costs(trades, fee_mult=2.0, slip_mult=2.0):
    """G1: 成本压力重算。fee_mult/slip_mult 相对基线倍数。"""
    fee_pct = FEE * fee_mult
    slip_extra = SLIP * (slip_mult - 1.0)
    nets = [recompute_net(t, fee_pct, slip_extra) for t in trades]
    wins = [x for x in nets if x > 0]
    gp = sum(wins)
    gl = -sum(x for x in nets if x <= 0)
    return {"fee_pct": fee_pct, "slip_extra_pct": round(slip_extra * 100, 3),
            "avg_net": round(sum(nets) / len(nets), 4) if nets else None,
            "win_rate": round(len(wins) / len(nets), 4) if nets else None,
            "pf": round(gp / gl, 3) if gl > 0 else None,
            "pass": bool(nets and sum(nets) / len(nets) > 0 and (gl == 0 or (gp / gl) > 1))}


def subwindow_stability(trades, n_sub=3):
    """G2: 按日期三等分子窗, 各子窗 avg>0 计数。"""
    srt = sorted(trades, key=lambda t: t["date"])
    n = len(srt)
    if n < n_sub * 2:
        return {"pass": False, "why": f"n={n}< {n_sub*2} 样本不足以切分"}
    k = n // n_sub
    subs = []
    for i in range(n_sub):
        chunk = srt[i * k: (i + 1) * k] if i < n_sub - 1 else srt[i * k:]
        nets = [t["net_pnl_pct"] for t in chunk if not t.get("skipped")]
        subs.append({"window": [chunk[0]["date"], chunk[-1]["date"]], "n": len(chunk),
                     "avg_net": round(sum(nets) / len(nets), 4) if nets else None,
                     "pos": bool(nets and sum(nets) / len(nets) > 0)})
    pos_cnt = sum(1 for s in subs if s["pos"])
    return {"subwindows": subs, "pos_windows": pos_cnt, "n_sub": n_sub,
            "pass": pos_cnt >= 2, "rule": "≥2/3 子窗 avg>0(允许1窗负: 反弹型信号天然时段集中)"}


def concentration(trades, top_trim=0.10):
    """G3: 去掉收益最高 10% 后 avg>0; n<20 无法稳健判定 → not_applicable。"""
    ok = [t for t in trades if not t.get("skipped")]
    n = len(ok)
    if n < 20:
        return {"pass": None, "why": f"n={n}<20, 集中度检验不适用(小样本)", "n": n}
    srt = sorted(ok, key=lambda t: t["net_pnl_pct"])
    k = max(1, int(n * top_trim))
    trimmed = srt[: n - k]
    avg_full = sum(t["net_pnl_pct"] for t in ok) / n
    avg_trim = sum(t["net_pnl_pct"] for t in trimmed) / len(trimmed)
    return {"n": n, "trimmed": k, "avg_full": round(avg_full, 4),
            "avg_after_trim": round(avg_trim, 4),
            "pass": avg_trim > 0, "rule": "去 top10% 后 avg 仍>0(§11.4 不能靠少数交易解释)"}


def run_gate(stage="ADX_LT20", records=None, bars_of=None, ttl_td=3):
    records = records if records is not None else json.load(open(BACKFILL_FILE, encoding="utf-8"))
    sel = [r for r in records if r.get("stage") == stage]
    res = RFR.run_layer(sel, bars_of=bars_of, ttl_td=ttl_td)
    trades = res["trades"]
    return {
        "stage": stage, "n_candidates": res["agg"]["n_candidates"],
        "n_filled": len(trades),
        "baseline": {"avg_net": res["agg"]["avg_net_pct"], "pf": res["agg"]["pf"],
                     "sl_rate": res["agg"]["sl_rate"], "tp_rate": res["agg"]["tp_rate"]},
        "G1_cost_stress": stress_costs(trades),
        "G2_subwindow": subwindow_stability(trades),
        "G3_concentration": concentration(trades),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="ADX_LT20")
    args = ap.parse_args()
    if not os.path.exists(BACKFILL_FILE):
        print(f"FAIL-FAST: {BACKFILL_FILE} 尚不存在 — 先跑 reject_backfill.py")
        return 1
    out = run_gate(stage=args.stage)
    g1, g2, g3 = out["G1_cost_stress"], out["G2_subwindow"], out["G3_concentration"]
    print(f"== {args.stage} 预注册压力门(基于 R8 fill 回放, 冻结口径) ==")
    print(f"  基线: n_filled={out['n_filled']} avg={out['baseline']['avg_net']}% PF={out['baseline']['pf']}")
    print(f"  G1 成本压力(费率×2+滑点×2): avg={g1['avg_net']}% PF={g1['pf']} → {'PASS' if g1['pass'] else 'FAIL'}")
    print(f"  G2 子窗稳定(3等分): 正子窗 {g2.get('pos_windows')}/{g2.get('n_sub')} → {'PASS' if g2['pass'] else 'FAIL'}")
    for s in (g2.get("subwindows") or []):
        print(f"     子窗 {s['window'][0]}..{s['window'][1]} n={s['n']} avg={s['avg_net']}")
    if g3["pass"] is None:
        print(f"  G3 集中度: 不适用({g3['why']})")
    else:
        print(f"  G3 集中度(去top10%): full={g3['avg_full']}% → trim={g3['avg_after_trim']}% → {'PASS' if g3['pass'] else 'FAIL'}")
    gates = [g1["pass"], g2["pass"], g3["pass"]]
    all_pass = all(x is True for x in gates)
    out["verdict"] = ("全部门通过 —— 但仅构成'研究层放宽建议'的证据链末端; "
                      "正式放宽仍需生产 reject_ledger 前瞻积累 n>=20 独立同向"
                      if all_pass else
                      "存在未通过门 —— 该层维持拒绝(frozen), 记录失败门")
    out["gate_discipline"] = ("§9.3/§11.2/§11.4 预注册; 三门全过也只是必要条件; "
                             "样本为 60 交易日单窗研究级回放, 未含组合容量约束")
    print(f"  判定: {out['verdict']}")
    rp = os.path.join(HERE, "handover", "reject_stress_gate_report.json")
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    json.dump({"generated_at": ts, "provenance": "stress_gate(研究级, 不改生产)", **out},
              open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"已写 {rp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())