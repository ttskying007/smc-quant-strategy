# -*- coding: utf-8 -*-
"""core/attribution.py —— V2 ITERATION 9: Loss Attribution 20类体系
蓝图 §54: 每笔亏损赋予主因(20类), 输出 Loss Contribution %。

判定顺序(单笔, 逐类检查, 首因优先=最具体):
执行约束层(物理不可避):
  1. LOSS_GAP            跳空击穿 SL(reason=SL_GAP / gap_through_sl=True)
SL 位置与设计(结构性损耗):
  2. LOSS_SL_TOO_TIGHT   SL 距离 < 0.6×ATR(结构太紧易被 jitter 磨损)
  3. LOSS_SL_TOO_WIDE    SL 距离 > 3×ATR(结构位太远, 亏损最大化来源)
利润回吐(最可操作的方向):
  4. LOSS_MFE_REVERSAL   MFE≥1R 但最终亏损(曾到过 1R 但未落袋)
  5. LOSS_TP_TOO_CLOSE   MFE≥TP1 目标但回吐(TP 设太近/止盈过早)
出场时间/窗口:
  6. LOSS_TIME_LONG      hold_bars>8 且亏损(持仓过久, 无催化却被滞留)
  7. LOSS_TIME_SHORT     hold_bars≤2 + SL_HIT 且亏损(入场太急, 未到搭载窗口)
执行质量:
  8. LOSS_BE_EXIT        reason=BE 且净亏损 >0.05(BE 目标太近, 手续费吃掉)
  9. LOSS_TP_GIVEBACK    TP2/TP3_RUNNER 且亏损(部分止盈没保住最终结果)
入场/信号质量:
  10. LOSS_ENTRY_LATE    入场在 zone 之上 >1ATR(late_flag)
  11. LOSS_STRUCTURE      HOLD 期内反向 CHOCH 触发(趋势转折)
  12. LOSS_REGIME        入场在市场 proxy > 2%(逆向策略正/错误环境里)
  13. LOSS_LOW_RANK      rank≤3(低分位信号被淘汰率高)
  14. LOSS_HIGH_RANK     rank≥4(高分信号也亏损, 策略整体压力信号)
持仓动态:
  15. LOSS_RANGE_HOLD    持有期内价格既未深回也未突破(机会成本型亏损)
  16. LOSS_SL_STRUCTURAL SL_HIT 且SL距离在 [0.6,3.0]×ATR 正常区间(正常结构失效)
损耗量级(兜底前过滤):
  17. LOSS_EXECUTION_COST 净亏损 <0.3%(手续费+滑点主导, 几乎非交易损失)
  18. LOSS_TIME_STOP     净亏损 <0.5% 且主要亏因不明(时间机会成本)
  19. LOSS_MEDIUM        亏损在 [0.5,1.0]%(显著但无法归类)
  20. LOSS_OTHER         兜底(亏损>1%且无任何特征命中)

统计: 各类 n / 亏损额 / Loss Contribution %。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def attribute_trade(tr, mae_pct, mfe_pct, sl_dist_pct=None, tp1_ret_pct=None,
                    atr_pct=None, late_flag=False, regime_proxy=None, choch_against=False,
                    gap_through_sl=False, mfe_r=None, hold_bars=None, reason=None,
                    rank=None):
    """单笔归因。tr: net_pnl_pct(<0 为亏损)。返回主因标签(字符串)。
    只对亏损单调用; 盈利单返回 None。
    参数 tr/mae_pct/mfe_pct 为必给; 其余 None = 此维度数据不可得, 跳过对应分支。"""
    if tr is None or tr >= 0:
        return None
    net = abs(tr)
    atr = (atr_pct if atr_pct else 0.025) * 100  # 统一为百分数(2.5 表示 2.5%)

    # --- 层 1: 执行约束(物理不可避) ---
    if gap_through_sl:
        return "LOSS_GAP"

    # --- 层 2: SL 位置异常 ---
    if sl_dist_pct is not None and sl_dist_pct < 0.6 * atr and net >= sl_dist_pct * 0.8:
        return "LOSS_SL_TOO_TIGHT"
    if sl_dist_pct is not None and sl_dist_pct > 3 * atr:
        return "LOSS_SL_TOO_WIDE"

    # --- 层 3: 利润回吐 ---
    if mfe_r is not None and mfe_r >= 1.0 and net > 0:
        return "LOSS_MFE_REVERSAL"
    if tp1_ret_pct is not None and mfe_pct is not None and mfe_pct >= tp1_ret_pct \
            and net >= tp1_ret_pct * 0.5:
        return "LOSS_TP_TOO_CLOSE"

    # --- 层 4: 出场时间窗口 ---
    if hold_bars is not None and hold_bars > 8 and net > 0.5:
        return "LOSS_TIME_LONG"
    if hold_bars is not None and hold_bars <= 2 and net >= 0.5 and reason == "SL_HIT":
        return "LOSS_TIME_SHORT"

    # --- 层 5: 执行质量(BE/TP_Runner) ---
    if reason == "BE" and net > 0.05:
        return "LOSS_BE_EXIT"
    if reason in ("TP2_RUNNER", "TP3_RUNNER") and net > 0:
        return "LOSS_TP_GIVEBACK"

    # --- 层 6: 入场/信号质量 ---
    if late_flag:
        return "LOSS_ENTRY_LATE"
    if choch_against:
        return "LOSS_STRUCTURE"
    if regime_proxy is not None and regime_proxy > 0.02:
        return "LOSS_REGIME"
    if rank is not None and rank < 3:
        # R13 微调(2026-09-19): rank<=3 -> rank<3. rank=3 是生产 gate 通过线, 占样本
        # 54%(paper_ledger 中 rank=3 占 58/140), 若仍归入 LOSS_LOW_RANK 会把"完全符合
        # gate 的正常单"标为低分位, 语义反直觉. 阈值收紧后 rank=3 单恢复到结构归因.
        return "LOSS_LOW_RANK"
    if rank is not None and rank >= 4:
        return "LOSS_HIGH_RANK"

    # --- 层 7: 持仓动态 ---
    if hold_bars is not None and abs(mae_pct or 0.0) <= atr and hold_bars >= 5 and net >= 0.3:
        return "LOSS_RANGE_HOLD"
    if reason == "SL_HIT" and sl_dist_pct is not None and 0.6 * atr <= sl_dist_pct <= 3 * atr:
        return "LOSS_SL_STRUCTURAL"

    # --- 层 8: 损耗量级 ---
    if net < 0.3:
        return "LOSS_EXECUTION_COST"
    if net < 0.5:
        return "LOSS_TIME_STOP"
    if net < 1.0:
        return "LOSS_MEDIUM"
    return "LOSS_OTHER"


ALL_LABELS = [
    # 执行约束层
    "LOSS_GAP",
    # SL 设计
    "LOSS_SL_TOO_TIGHT", "LOSS_SL_TOO_WIDE",
    # 利润回吐
    "LOSS_MFE_REVERSAL", "LOSS_TP_TOO_CLOSE",
    # 出场时间窗口
    "LOSS_TIME_LONG", "LOSS_TIME_SHORT",
    # 执行质量
    "LOSS_BE_EXIT", "LOSS_TP_GIVEBACK",
    # 入场/信号质量
    "LOSS_ENTRY_LATE", "LOSS_STRUCTURE", "LOSS_REGIME", "LOSS_LOW_RANK", "LOSS_HIGH_RANK",
    # 持仓动态
    "LOSS_RANGE_HOLD", "LOSS_SL_STRUCTURAL",
    # 损耗量级
    "LOSS_EXECUTION_COST", "LOSS_TIME_STOP", "LOSS_MEDIUM",
    # 兜底
    "LOSS_OTHER",
]
assert len(ALL_LABELS) == 20, f"蓝图要求 20 类, 当前 {len(ALL_LABELS)} 类"


def attribution_summary(trades):
    """trades: [{label, loss_abs}] → 各类贡献占比 + coverage 计数。"""
    total = sum(t["loss_abs"] for t in trades)
    out = {}
    n_used = 0
    for lab in ALL_LABELS:
        sub = [t for t in trades if t["label"] == lab]
        loss = sum(t["loss_abs"] for t in sub)
        out[lab] = {"n": len(sub), "loss_sum": round(loss, 2),
                    "contribution_pct": round(loss / total * 100, 1) if total else 0.0}
        if sub:
            n_used += 1
    out["_total_loss"] = round(total, 2)
    out["_total_n"] = len(trades)
    out["_classes_used"] = n_used
    return out
