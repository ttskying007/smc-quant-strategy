# -*- coding: utf-8 -*-
"""R13 生产化测试: paper_sim 的 loss_attribution 落账语义
测试: 1) attribution 模块 20 类稳定性
     2) paper_sim.py 中带 _attr 名块的语法存在(静态)
     3) 负态单下归因返回合法 label,正态单不在 negative 分支调用
     4) 主要损耗类型语义与真实 EVT 信贷约束一致
"""
import io, os, sys
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

print("== 1. 20 类完整 ==")
ok("ALL_LABELS 20 类", len(ALL_LABELS) == 20)

print("== 2. 各 tag 独立触发 ==")
# 现有亏损单语义不变
ok("LOSS_GAP 最高优先", attribute_trade(-8, -8, 5, gap_through_sl=True) == "LOSS_GAP")
ok("LOSS_SL_TOO_LARGE 判决", attribute_trade(-9, -9, 0, sl_dist_pct=9.0, atr_pct=0.025) == "LOSS_SL_TOO_WIDE")
ok("LOSS_SL_TOO_TIGHT", attribute_trade(-1.2, -1.2, 0.5, sl_dist_pct=1.0, atr_pct=0.025) == "LOSS_SL_TOO_TIGHT")
ok("LOSS_MFE_REVERSAL", attribute_trade(-1, -1, 5, mfe_r=1.5) == "LOSS_MFE_REVERSAL")
ok("LOSS_TIME_LONG", attribute_trade(-2, -2, 1, hold_bars=10) == "LOSS_TIME_LONG")
ok("LOSS_TIME_SHORT", attribute_trade(-2, -2, 1, hold_bars=1, reason="SL_HIT") == "LOSS_TIME_SHORT")
ok("LOSS_BE_EXIT", attribute_trade(-0.2, -0.2, 0.4, reason="BE") == "LOSS_BE_EXIT")
ok("LOSS_TP_GIVEBACK", attribute_trade(-1.5, -1.5, 2, reason="TP2_RUNNER") == "LOSS_TP_GIVEBACK")
ok("LOSS_LOW_RANK", attribute_trade(-2, -2, 1, rank=2) == "LOSS_LOW_RANK")
ok("LOSS_HIGH_RANK", attribute_trade(-2, -2, 1, rank=5) == "LOSS_HIGH_RANK")
ok("LOSS_RANGE_HOLD", attribute_trade(-0.8, -0.8, 0.4, hold_bars=8) == "LOSS_RANGE_HOLD")
ok("LOSS_SL_STRUCTURAL", attribute_trade(-3.0, -3.0, 1, reason="SL_HIT",
    sl_dist_pct=3.0, atr_pct=0.025) == "LOSS_SL_STRUCTURAL")
ok("LOSS_EXECUTION_COST", attribute_trade(-0.2, -0.2, 0.2) == "LOSS_EXECUTION_COST")
ok("LOSS_MEDIUM", attribute_trade(-0.7, -0.7, 0.7) == "LOSS_MEDIUM")
ok("LOSS_OTHER 兜底", attribute_trade(-2.5, -2.5, 1.0) == "LOSS_OTHER")

print("== 3. paper_sim 接线存在(静态) ==")
src = open(r"research/paper_sim.py", encoding="utf-8").read()
ok("paper_sim 写 loss_attribution", 't["loss_attribution"]' in src)
ok("FILLED 状态负责 mfe_px", 'if cur_px > (t.get("mfe_px")' in src)
ok("FILLED 状态负责 mae_px", 'if cur_px < (t.get("mae_px")' in src)
ok("loss_attribution 只在 pnl<0", 't["pnl_pct"] is not None and t["pnl_pct"] < 0' in src)
ok("调用 core.attribution", 'from core.attribution import attribute_trade as _attr' in src)
ok("失败软回退保留", "except Exception:  # R13 软失败" in src or "归因失败不影响卖出订单" in src)

print("== 4. 参数接口完备 ==")
# 生产调用可能传非 title/mae 缺失字段, 必须无损 response
for reason in (None, "", "UNKNOWN"):
    lab = attribute_trade(-1.0, -1.0, 1.0, reason=reason)
    ok("negative 归因非None %r" % str(reason or "None"), lab is not None and lab.startswith("LOSS_"), lab)

print("== 5. 真实匿名案例 ==")
# 案例 1: mfe_r=1.8 折扣拉回, tp未达但有时间长
lab = attribute_trade(-2.0, mae_pct=-2.0, mfe_pct=3.5, mfe_r=1.8, hold_bars=9)
ok("mfe>=1R + 持仓长 → LOSS_TIME_LONG 或 LOSS_MFE_REVERSAL", lab in ("LOSS_TIME_LONG", "LOSS_MFE_REVERSAL"), lab)
# 案例2: rank=1 入场 但 mae 无异常
lab2 = attribute_trade(-1.2, mae_pct=-1.2, mfe_pct=2.0, sl_dist_pct=2.0, atr_pct=0.025, rank=1)
ok("低 rank 加上 SL_HIT 前 rank 优先被命中", lab2 == "LOSS_LOW_RANK", lab2)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
