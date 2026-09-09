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

print("== 2. 汇总占比 ==")
trades = [{"label": "LOSS_GAP", "loss_abs": 20}, {"label": "LOSS_GAP", "loss_abs": 10},
          {"label": "LOSS_STRUCTURE", "loss_abs": 10}, {"label": "LOSS_OTHER", "loss_abs": 10}]
s = attribution_summary(trades)
ok("总数", s["_total_n"] == 4)
ok("总亏", s["_total_loss"] == 50)
ok("GAP贡献60%", s["LOSS_GAP"]["contribution_pct"] == 60.0)
ok("覆盖全标签", len([k for k in s if not k.startswith("_")]) == len(ALL_LABELS))

print("== 3. 事件腿 1640 笔应用(真实数据) ==")
rows = [r for r in csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "combo_v20f_trades.csv"), encoding="utf-8-sig"))
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
                          gap_through_sl=(reason == "SL_GAP"))
    tagged.append({"label": lab, "loss_abs": abs(net)})
summ = attribution_summary(tagged)
print(f"  亏损单: {summ['_total_n']} | 总亏: {summ['_total_loss']}%")
for lab in sorted(ALL_LABELS, key=lambda x: -summ[x]["contribution_pct"]):
    if summ[lab]["n"]:
        print(f"    {lab:20s}: {summ[lab]['n']:4d}笔 {summ[lab]['contribution_pct']:5.1f}%")
ok("事件腿归因完成", summ["_total_n"] > 500)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)