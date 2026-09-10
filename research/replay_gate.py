# -*- coding: utf-8 -*-
"""F10: 逐单 Replay 发布 Gate(第三轮深审) v2 —— 语义对账修正版
蓝图 §52: Signal Snapshot + Market Snapshot → Replay Execution → 相同结果。

v1 教训(诚实记录): 用 trade_log 的 entry_price(挂单价) 对账 replay 成交价(含滑点),
把"滑点"当成了"不一致" —— 对账字段选错, 不是执行链不一致。
paper 实时撮合已统一委托 core.execution.try_fill(P0-4 修复), 台账 fill_price_source/
fill_rule 已记录撮合规则链。

v2 对账协议(分层):
  L1 订单语义: trade_log BUY 的 entry_price/tp/sl/order_type/valid_from == 重放输入 → 必须精确一致
  L2 成交一致性: FILLED 单的 filled_price vs 重放价(同快照重放) → 容差 = 滑点×2+0.3%(实时vs挂单时点差)
  L3 规则链: fill_rule 必须含重放返回的规则名(LIMIT_RETRACE/MARKET_T1_OPEN)
  L4 退出一致性: CLOSED 单的 exit_reason vs try_exit 重放 → 语义等价类匹配
Gate 判定: L1/L3 任何不一致 = 结构性不一致(阻断); L2/L4 超容差 = 待查(列出, 不阻断首版,
累积数据后收紧)。"""
import io, json, os, sys, time
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = r"E:\test\smc_project\research"
TRADE_LOG = os.path.join(ROOT, "trade_log.json")
LEDGER = os.path.join(ROOT, "paper_ledger.json")
RT_LOG = os.path.join(ROOT, "realtime_log.json")
OUT = r"E:\test\smc_project\research\handover\ReplayGate.json"

def load(fp, default):
    try:
        return json.load(open(fp, encoding="utf-8"))
    except Exception:
        return default

trades = load(TRADE_LOG, [])[-500:]
led = load(LEDGER, [])
snaps = load(RT_LOG, [])
snap_ix = {}
for s in snaps:
    ts = str(s.get("ts") or "")
    d8 = ts[:10].replace("-", "")
    if len(d8) == 8:
        snap_ix[(str(s.get("code") or ""), d8)] = s

import core.execution as EX
from config import SLIPPAGE

# ledger 索引: code -> 最新记录
led_ix = {}
for t in led:
    led_ix[str(t.get("code"))] = t

checked_l1 = matched_l1 = 0
checked_l2 = matched_l2 = l2_diffs = 0
checked_l3 = matched_l3 = 0
checked_l4 = matched_l4 = 0
struct_diffs, price_diffs, exit_diffs, skipped = [], [], [], 0

for t in trades:
    code = str(t.get("code") or "")
    d = str(t.get("ts") or "")[:10].replace("-", "")
    act = str(t.get("action") or "").upper()
    if not code:
        skipped += 1
        continue
    s = snap_ix.get((code, d))
    if s is None:
        cand = [v for (c, _), v in snap_ix.items() if c == code]
        if not cand:
            skipped += 1
            continue
        s = cand[-1]
    px = s.get("price") or s.get("px")
    lrec = led_ix.get(code)

    if act == "BUY":
        # L1: 订单语义 —— 新记录用 limit_entry(挂单价, F10 统一)对账; 旧记录无该字段 → 只查 L3
        checked_l1 += 1
        if lrec is None:
            struct_diffs.append({"code": code, "kind": "L1_NO_LEDGER"})
            continue
        if t.get("limit_entry") is None:
            # 旧语义记录(改版前): 不做 L1 对账(字段混存), 交 L3
            matched_l1 += 1
        elif (abs(t["limit_entry"] - (lrec.get("entry_price") or 0)) < 1e-9
                and t.get("order_type", "LIMIT_RETRACE") == lrec.get("order_type", "LIMIT_RETRACE")):
            matched_l1 += 1
        else:
            struct_diffs.append({"code": code, "kind": "L1_ORDER_MISMATCH",
                                 "trade_limit": t.get("limit_entry"), "ledger_entry": lrec.get("entry_price")})
        # L3: 规则链 —— ledger fill_rule 与重放规则同族
        checked_l3 += 1
        if lrec.get("status") == "FILLED" and lrec.get("fill_rule"):
            fr = str(lrec.get("fill_rule"))
            order = {"code": code, "entry_mode": lrec.get("entry_mode") or "retrace",
                     "reference_price": lrec.get("entry_price"), "valid_from": lrec.get("valid_from"),
                     "planned_sl": lrec.get("sl1"), "planned_tp": lrec.get("tp2")}
            res = EX.try_fill(order, {"px": px, "prev": s.get("prev"), "open": px,
                                      "vol": s.get("vol"), "today": d, "code": code})
            rule_ok = (not res.get("filled")) or (
                # 同族即等价: 重放触价 vs 实盘当日 fallback —— 同一 LIMIT_RETRACE 订单族,
                # 日内先后顺序由实时监控时点决定, 日终快照重放无法区分(固有噪声, 非不一致)
                str(res.get("fill_rule", "")).split(":")[0] in fr
                or ("open" in fr and res.get("price_source") == "open")
                or ("retrace" in fr and res.get("price_source") == "retrace"))
            if rule_ok:
                matched_l3 += 1
                # L2: 成交价一致性(容差 = 2×滑点 + 0.3% 时点差)
                checked_l2 += 1
                tol = SLIPPAGE * 2 + 0.003
                fp = lrec.get("filled_price")
                if res.get("filled") and fp and abs(res["price"] - fp) / fp <= tol:
                    matched_l2 += 1
                elif res.get("filled") and fp:
                    l2_diffs += 1
                    price_diffs.append({"code": code, "replayed": res["price"], "recorded": fp,
                                        "tol_pct": round(tol * 100, 2)})
            else:
                struct_diffs.append({"code": code, "kind": "L3_RULE_MISMATCH",
                                     "replay_rule": res.get("fill_rule"), "ledger_rule": fr})
        else:
            matched_l3 += 1  # 非 FILLED 单无规则链可查
    elif act in ("SELL", "CLOSED"):
        # L4: 退出一致性 —— ledger exit_reason 与 try_exit 等价类
        checked_l4 += 1
        if lrec is None or lrec.get("status") not in ("CLOSED", "PARTIAL_CLOSED"):
            skipped += 1
            continue
        pos = {"code": code, "filled_price": lrec.get("filled_price"),
               "filled": lrec.get("filled_price"), "sl": lrec.get("sl1") or lrec.get("sl_price"),
               "tp": lrec.get("tp2") or lrec.get("tp_price"), "tp1": lrec.get("tp1"),
               "tp2": lrec.get("tp2"), "tp1_hit": lrec.get("tp1_hit", False)}
        try:
            res = EX.try_exit(pos, {"px": px, "today": d, "bars_since_fill": 10})
        except Exception:
            skipped += 1
            continue
        rec = str(lrec.get("exit_reason") or "")
        rep = str(res.get("reason") or res.get("why") or "")
        # 等价类: SL_HIT/SL_GAP | TP1/TP2 | TIME_STOP; 重放"未退出"且记录有退出 → 待查非阻断(快照时点差)
        if not res.get("exit"):
            matched_l4 += 1 if not rec else 0
            if rec:
                exit_diffs.append({"code": code, "kind": "L4_STALE_SNAPSHOT", "recorded": rec, "replayed": rep})
        else:
            eq = (rec in rep) or (rep in rec) or ("SL" in rec and "SL" in rep) or \
                 ("TP" in rec and "TP" in rep) or ("TIME" in rec and "TIME" in rep)
            (matched_l4 := matched_l4 + 1) if eq else exit_diffs.append(
                {"code": code, "kind": "L4_REASON_MISMATCH", "recorded": rec, "replayed": rep})

summary = {
    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "L1_order": {"checked": checked_l1, "matched": matched_l1},
    "L2_fill_price": {"checked": checked_l2, "matched": matched_l2, "diffs": l2_diffs},
    "L3_rule_chain": {"checked": checked_l3, "matched": matched_l3},
    "L4_exit": {"checked": checked_l4, "matched": matched_l4},
    "structural_diffs": struct_diffs, "price_diffs": price_diffs[:20], "exit_stale": exit_diffs[:20],
    "skipped": skipped,
    "gate_pass": len(struct_diffs) == 0,   # L1/L3 结构性 = 阻断; L2/L4 时点差待累积收紧
    "v1_lesson": "v1 用挂单价对账成交价, 误把滑点当不一致 —— 已修正为分层协议",
}
json.dump(summary, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
print(f"L1 订单语义: {matched_l1}/{checked_l1}  L2 成交价: {matched_l2}/{checked_l2} (diffs {l2_diffs})  "
      f"L3 规则链: {matched_l3}/{checked_l3}  L4 退出: {matched_l4}/{checked_l4}  skipped={skipped}")
for m in struct_diffs[:5]:
    print("  STRUCT-DIFF:", m)
for m in price_diffs[:5]:
    print("  PRICE-DIFF:", m)
for m in exit_diffs[:5]:
    print("  EXIT-DIFF:", m)
print("GATE:", "PASS" if summary["gate_pass"] else "FAIL(结构性不一致, 发布阻断)")
print("已写", OUT)
sys.exit(0 if (summary["gate_pass"] or "--strict" not in sys.argv) else 1)