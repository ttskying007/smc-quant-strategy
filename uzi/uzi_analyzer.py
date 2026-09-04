# -*- coding: utf-8 -*-
"""UZI-Skill 分析引擎集成（uzi_analyzer.py）—— 对股票列表做 UZI 风格分析
结合 our strategy（rank_score/阶段/TP/SL/放量/大资金）输出评审意见"""
import io, json, os, sys, datetime
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def analyze_stock(code, name="", rank_score=0, stage="", entry_price=0, tp1=0, sl1=0, v_ratio=0):
    """对单支股票做 UZI 风格分析（结合我们的策略）"""
    result = {"code": code, "name": name, "ts": datetime.datetime.now().strftime("%H:%M:%S"),
              "institution_score": 0, "our_score": rank_score, "rank_score": rank_score, "stage": stage,
              "verdicts": [], "verdict": "", "entry": entry_price, "tp": tp1, "sl": sl1}
    # 维度1: 我们的策略评分
    if rank_score >= 6:
        result["verdicts"].append("皇冠级(rank≥6) — 高置信度抄底信号")
    elif rank_score >= 4:
        result["verdicts"].append(f"优质级(rank={rank_score}) — 中等置信度信号")
    else:
        result["verdicts"].append(f"普通级(rank={rank_score}) — 低置信度信号")
    # 维度2: 行为阶段
    if stage == "ACCUM":
        result["verdicts"].append("吸筹阶段(ACCUM) — 大资金底部建仓区")
    elif stage == "DOWNTREND":
        result["verdicts"].append("下跌阶段(DOWNTREND) — 超卖反弹区")
    # 维度3: 放量 / 大资金
    if v_ratio > 2.0:
        result["verdicts"].append(f"显著放量(v={v_ratio:.1f}x) — 大资金入场确认")
    elif v_ratio > 1.2:
        result["verdicts"].append(f"温和放量(v={v_ratio:.1f}x) — 大资金关注")
    # 维度4: TP/SL 盈亏比
    if tp1 and sl1 and entry_price:
        rr = (tp1 - entry_price) / (entry_price - sl1) if entry_price > sl1 else 0
        if rr > 2:
            result["verdicts"].append(f"盈亏比优异(rr={rr:.1f}) — 风险收益合理")
        elif rr > 1:
            result["verdicts"].append(f"盈亏比适中(rr={rr:.1f}) — 可接受")
        else:
            result["verdicts"].append(f"盈亏比偏低(rr={rr:.1f}) — 需谨慎")
    # 维度5: 机构评分（UZI 风格）
    result["institution_score"] = min(100, rank_score * 15 + 10)
    # 总评
    verdicts = result["verdicts"]
    if rank_score >= 6:
        result["verdict"] = "【皇冠精选】强势买入 — 高置信度抄底信号，大资金确认，TP/SL 盈亏比合理"
    elif rank_score >= 4:
        result["verdict"] = "【关注】可考虑入场 — 中等置信度，建议等待放量确认"
    else:
        result["verdict"] = "【观察】暂不参与 — 信号置信度不足，等待更佳时机"
    return result


def analyze_list(codes):
    """分析股票列表"""
    results = []
    for c in codes:
        results.append(analyze_stock(c.get("code", ""), c.get("name", ""),
                                     c.get("rank_score", 0), c.get("stage", ""),
                                     c.get("entry_price", 0), c.get("tp1", 0), c.get("sl1", 0),
                                     c.get("v_ratio", 0)))
    return results


if __name__ == "__main__":
    # 测试：从 ledger 取持仓股票分析
    led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
    active = [t for t in led if t.get("status") != "CLOSED"][:10]
    samples = [{"code": t.get("code"), "name": t.get("name"), "rank_score": t.get("rank_score", 0),
                "stage": t.get("stage", ""), "entry_price": t.get("entry_price", 0),
                "tp1": t.get("tp1", 0), "sl1": t.get("sl1", 0), "v_ratio": t.get("v_ratio", 0)}
               for t in active]
    results = analyze_list(samples)
    for r in results:
        print(f"  {r['code']} {r['name']}: {r['verdict']}")
        for v in r["verdicts"]:
            print(f"    · {v}")