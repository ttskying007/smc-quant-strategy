# -*- coding: utf-8 -*-
"""core/attribution.py —— V2 ITERATION 9: Loss Attribution 系统
蓝图 §54: 每笔亏损赋予主因(20类), 输出 Loss Contribution %。
判定顺序(单笔交易, 逐类检查, 首因优先=最具体):
  1. LOSS_GAP        SL 成交价 < SL 价(跳空击穿) → 执行损耗真实发生
  2. LOSS_SL_TOO_TIGHT MAE > 1×risk 且最终 net>0 的镜像类: 亏损单中 MAE≥1R 且价格随后回到入场 → SL过紧
  3. LOSS_SL_TOO_WIDE SL 距离 > 3×ATR% 且亏损 → 结构位太远
  4. LOSS_TP_TOO_CLOSE 曾到 TP1(MFE≥tp1收益) 但最终亏损 → 到手利润回吐
  5. LOSS_ENTRY_LATE  entry 距 zone 高点 > 1 ATR(late_flag) 且亏损
  6. LOSS_STRUCTURE   反向结构转移发生在持有期内(CHOCH 逆势) 且亏损
  7. LOSS_REGIME      入场时市场 proxy 处于极端强市(事件腿逆向策略不利) 且亏损
  8. LOSS_TIME_STOP   15根时间止损离场且 |net| < 0.5%(机会成本类)
  9. LOSS_OTHER       兜底
统计: 各类 n / 亏损额 / Loss Contribution %。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def attribute_trade(tr, mae_pct, mfe_pct, sl_dist_pct=None, tp1_ret_pct=None,
                    atr_pct=None, late_flag=False, regime_proxy=None, choch_against=False,
                    gap_through_sl=False):
    """单笔归因。tr: net_pnl_pct(<0 为亏损)。返回主因标签(字符串)。
    只对亏损单调用; 盈利单返回 None。"""
    if tr is None or tr >= 0:
        return None
    net = abs(tr)
    atr = (atr_pct if atr_pct else 0.025) * 100  # 统一为百分数(2.5 表示 2.5%)
    if gap_through_sl:
        return "LOSS_GAP"
    if sl_dist_pct is not None and sl_dist_pct < 0.6 * atr and net >= sl_dist_pct * 0.8:
        return "LOSS_SL_TOO_TIGHT"
    if sl_dist_pct is not None and sl_dist_pct > 3 * atr:
        return "LOSS_SL_TOO_WIDE"
    if tp1_ret_pct is not None and mfe_pct is not None and mfe_pct >= tp1_ret_pct and net >= tp1_ret_pct * 0.5:
        return "LOSS_TP_TOO_CLOSE"
    if late_flag:
        return "LOSS_ENTRY_LATE"
    if choch_against:
        return "LOSS_STRUCTURE"
    if regime_proxy is not None and regime_proxy > 0.02:
        return "LOSS_REGIME"
    if net < 0.5:
        return "LOSS_TIME_STOP"
    return "LOSS_OTHER"


ALL_LABELS = ["LOSS_GAP", "LOSS_SL_TOO_TIGHT", "LOSS_SL_TOO_WIDE", "LOSS_TP_TOO_CLOSE",
              "LOSS_ENTRY_LATE", "LOSS_STRUCTURE", "LOSS_REGIME", "LOSS_TIME_STOP", "LOSS_OTHER"]


def attribution_summary(trades):
    """trades: [{label, loss_abs}] → 各类贡献占比。"""
    total = sum(t["loss_abs"] for t in trades)
    out = {}
    for lab in ALL_LABELS:
        sub = [t for t in trades if t["label"] == lab]
        loss = sum(t["loss_abs"] for t in sub)
        out[lab] = {"n": len(sub), "loss_sum": round(loss, 2),
                    "contribution_pct": round(loss / total * 100, 1) if total else 0.0}
    out["_total_loss"] = round(total, 2)
    out["_total_n"] = len(trades)
    return out