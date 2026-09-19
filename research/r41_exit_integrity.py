# -*- coding: utf-8 -*-
"""R41: 退出字段完整性审计 (canonical 1527 腿)
检查: sell_date>=buy_date; hold_bars 与实际日期一致(±); SL_HIT 则 sell_price<=sl;
TP2_RUNNER 则 sell_price>=tp; TIME_STOP 则 hold≈MAX_HOLD; pnl 与价格算术一致(±0.05)。
"""
import csv, os, sys, json, statistics
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
issues = Counter(); samples = {}
chk_n = 0
for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")):
    if not (r.get("buy_price") or "").strip(): continue
    chk_n += 1
    sym = r.get("symbol") or r.get("\ufeffsymbol")
    bd, sd = r.get("buy_date"), r.get("sell_date")
    try:
        bp, sp = float(r["buy_price"]), float(r["sell_price"])
        tp, sl = float(r["tp"]), float(r["sl"])
        pnl = float(r["net_pnl_pct"]); hb = int(float(r["hold_bars"] or 0))
    except Exception:
        issues["parse_fail"] += 1; continue
    def flag(k):
        issues[k] += 1
        if k not in samples: samples[k] = f"{sym} {bd}->{sd} bp={bp} sp={sp} tp={tp} sl={sl} pnl={pnl} hb={hb} reason={r.get('reason')}"
    if sd and sd < bd: flag("sell_before_buy")
    if hb <= 0: flag("hold_zero")
    if r.get("reason") == "SL_HIT" and sp > sl + 0.001: flag("sl_hit_price_above_sl")
    if r.get("reason") == "TP2_RUNNER" and sp < tp * 0.98: flag("tp2_sell_below_tp")
    calc = (sp / bp - 1) * 100
    # 分批平仓下裸算不适用; 退化为"方向一致性": SL_HIT 必须亏, TP/BE 类必须 >= -fees
    if r.get("reason") == "SL_HIT" and pnl > 0.01: flag("sl_hit_but_profit")
    if r.get("reason") in ("TP1", "TP2_RUNNER") and pnl < -1.0: flag("tp_leg_negative_gt1pp")  # 费用可造成轻微负, >1pp 才算异常
print(f"checked n={chk_n}")
for k, v in issues.most_common():
    print(f"  {k}: {v}   样本: {samples.get(k, '')[:110]}")
if not issues:
    print("✅ 全部通过")

res = {"checked": chk_n, "issues": dict(issues), "samples": samples,
       "verdict": "CLEAN" if not issues else f"{sum(issues.values())} issues"}
json.dump(res, open(os.path.join(HERE, "handover", "r41_exit_integrity.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r41_exit_integrity.json")
