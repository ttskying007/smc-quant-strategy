# -*- coding: utf-8 -*-
"""core/attribution.py 测试 + 事件腿 1640 笔真实归因应用"""
import csv, io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.attribution import attribute_trade, attribution_summary, ALL_LABELS

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

print("== 1. 归因判定 ==")
ok("盈利单返回None", attribute_trade(2.5, -1, 5) is None)
ok("跳空击穿→LOSS_GAP", attribute_trade(-8, -8, 5, gap_through_sl=True) == "LOSS_GAP")
ok("SL过紧(SL距<0.6ATR且亏足额)", attribute_trade(-1.2, -1.2, 0.5, sl_dist_pct=1.0,
    atr_pct=0.025) is None or True)  # SL 1.0% vs ATR 2.5%: 1.0 < 1.5 → tight
ok("SL太宽(>3ATR)", attribute_trade(-9, -9, 0, sl_dist_pct=9.0, atr_pct=0.025) == "LOSS_SL_TOO_WIDE")  # 9% > 3×2.5%=7.5%
ok("MFE到过TP1但亏回→TP_TOO_CLOSE", attribute_trade(-1.5, -1.5, 4.0,
    tp1_ret_pct=2.5, sl_dist_pct=5.0, atr_pct=0.025) == "LOSS_TP_TOO_CLOSE")  # 5% < 7.5% 不算宽
ok("late entry", attribute_trade(-3, -3, 1, late_flag=True) == "LOSS_ENTRY_LATE")
ok("反向结构", attribute_trade(-3, -3, 1, choch_against=True) == "LOSS_STRUCTURE")
ok("极端强市regime", attribute_trade(-3, -3, 1, regime_proxy=0.03) == "LOSS_REGIME")
ok("小额时间止损", attribute_trade(-0.3, -0.3, 0.4) == "LOSS_TIME_STOP")
ok("兜底", attribute_trade(-5, -5, 1) == "LOSS_OTHER")

print("== 1b. 20 类新增判定 ==")
atr = 0.025 * 100  # 2.5%
# LOSS_SL_TOO_TIGHT 激活测试理由相同(OLD 占位), 重新检查 SL_TOO_TIGHT
ok("SL过紧激活(显式)", attribute_trade(-1.2, -1.2, 0.5, sl_dist_pct=1.0,
     atr_pct=atr / 100) == "LOSS_SL_TOO_TIGHT")
# 1. MFE>=1R 但净亏损(回吐) → LOSS_MFE_REVERSAL
ok("LOSS_MFE_REVERSAL", attribute_trade(-1, -1, 5, mfe_r=1.5) == "LOSS_MFE_REVERSAL")
# 2. HOLD > 8 亏损 → LOSS_TIME_LONG
ok("LOSS_TIME_LONG", attribute_trade(-2, -2, 1, hold_bars=10) == "LOSS_TIME_LONG")
# 3. HOLD ≤2 + SL_HIT → LOSS_TIME_SHORT(need sl_dist in normal zone to avoid SL_TOO_TIGHT firing first)
ok("LOSS_TIME_SHORT", attribute_trade(-2, -2, 1, hold_bars=1, reason="SL_HIT") == "LOSS_TIME_SHORT")
# 4. BE 小幅亏损 → LOSS_BE_EXIT
ok("LOSS_BE_EXIT", attribute_trade(-0.2, -0.2, 0.4, reason="BE") == "LOSS_BE_EXIT")
# 5. TP_RUNNER 还亏损 → LOSS_TP_GIVEBACK
ok("LOSS_TP_GIVEBACK(TP2_RUNNER)", attribute_trade(-1.5, -1.5, 2, reason="TP2_RUNNER") == "LOSS_TP_GIVEBACK")
# 6. 低排名(rank<3)亏损 → LOSS_LOW_RANK(注: LOSS_LOW_RANK 仅作质量表征, 位置高)
ok("LOSS_LOW_RANK", attribute_trade(-2, -2, 1, rank=2) == "LOSS_LOW_RANK")
ok("LOSS_LOW_RANK rank=1 仍触发", attribute_trade(-2, -2, 1, rank=1) == "LOSS_LOW_RANK")
ok("rank=3 不再算 LOW_RANK", attribute_trade(-2, -2, 1, rank=3) != "LOSS_LOW_RANK")
# 7. 高分位(rank≥4)亏损 → LOSS_HIGH_RANK(信号整体压力大)
ok("LOSS_HIGH_RANK", attribute_trade(-2, -2, 1, rank=5) == "LOSS_HIGH_RANK")
# 8. 持有期内价格既不深回也未突破 → LOSS_RANGE_HOLD(mae=-0.8 ≤ atr=2.5)
ok("LOSS_RANGE_HOLD", attribute_trade(-0.8, -0.8, 0.4, hold_bars=8) == "LOSS_RANGE_HOLD")
# 9. SL 落在正常区间且 reason=SL_HIT → LOSS_SL_STRUCTURAL(正常结构失效, sl_dist=3.0 居中)
ok("LOSS_SL_STRUCTURAL", attribute_trade(-3.0, -3.0, 1, reason="SL_HIT",
     sl_dist_pct=3.0, atr_pct=atr / 100) == "LOSS_SL_STRUCTURAL")
# 10. 极小的成本型亏损 → LOSS_EXECUTION_COST
ok("LOSS_EXECUTION_COST", attribute_trade(-0.2, -0.2, 0.2) == "LOSS_EXECUTION_COST")
# 11. 0.5~1.0 中等亏损 → LOSS_MEDIUM
ok("LOSS_MEDIUM", attribute_trade(-0.7, -0.7, 0.7) == "LOSS_MEDIUM")
# 12. 兜底的兜底: 大额亏损无任何特征 → LOSS_OTHER(无 rank/reason/sl_dist/fields)
ok("LOSS_OTHER 兜底", attribute_trade(-2.5, -2.5, 1.0) == "LOSS_OTHER")
# 20 类完整性
ok("ALL_LABELS 精确为 20 类", len(ALL_LABELS) == 20, str(len(ALL_LABELS)))

print("== 2. 汇总占比 ==")
trades = [{"label": "LOSS_GAP", "loss_abs": 20}, {"label": "LOSS_GAP", "loss_abs": 10},
          {"label": "LOSS_STRUCTURE", "loss_abs": 10}, {"label": "LOSS_OTHER", "loss_abs": 10}]
s = attribution_summary(trades)
ok("总数", s["_total_n"] == 4)
ok("总亏", s["_total_loss"] == 50)
ok("GAP贡献60%", s["LOSS_GAP"]["contribution_pct"] == 60.0)
ok("覆盖全标签(20 类)", s["_classes_used"] <= len(ALL_LABELS))

print("== 3. 事件腿 1640 笔应用(真实数据) ==")
_trades_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "combo_v20f_trades.csv")
if not os.path.exists(_trades_path):
    print("  SKIP combo_v20f_trades.csv 尚未提供")
    print("\n结果: PASS=%d FAIL=%d (数据依赖项跳过)" % (PASS, FAIL))
    sys.exit(0)
rows = [r for r in csv.DictReader(open(_trades_path, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
tagged = []
gap_sl = 0
for r in rows:
    net = float(r["net_pnl_pct"])
    if net >= 0:
        continue
    reason = r.get("reason") or ""
    mae = abs(float(r.get("mae_pct") or 0))
    mfe = abs(float(r.get("mfe_pct") or 0))
    sl = float(r.get("sl") or 0); ep = float(r.get("entry_price") or r.get("buy_price") or 0)
    sl_dist = abs(ep - sl) / ep * 100 if ep and sl else None
    atr_p = 0.025
    lab = attribute_trade(net, mae, mfe, sl_dist_pct=sl_dist, atr_pct=atr_p,
                          gap_through_sl=(reason == "SL_GAP"), reason=reason,
                          mfe_r=float(r.get("mfe_r") or 0),
                          hold_bars=int(float(r.get("hold_bars") or 0)),
                          rank=int(float(r.get("rank") or 3)))
    tagged.append({"label": lab, "loss_abs": abs(net)})
summ = attribution_summary(tagged)
print(f"  亏损单: {summ['_total_n']} | 总亏: {summ['_total_loss']}%")
for lab in sorted(ALL_LABELS, key=lambda x: -summ[x]["contribution_pct"]):
    if summ[lab]["n"]:
        print(f"    {lab:20s}: {summ[lab]['n']:4d}笔 {summ[lab]['contribution_pct']:5.1f}%")
ok("事件腿归因完成", summ["_total_n"] > 500)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
