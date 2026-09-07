# -*- coding: utf-8 -*-
"""core/events.py —— 事件统一分类（审计 G25）
scanner 与 daily_selection 共用同一套增持/回购标题分类，消除两套否定词不一致：
  - 否定词全集：终止/完毕/解除/取消/结束/调整/变更/进展/补充协议/届满/减持/
    完成/进度/前十名/结果/公告/草案
  - 返回 (is_event, kind, polarity, magnitude_hint)
"""
import re

NEG_WORDS = ("终止", "完毕", "解除", "取消", "结束", "调整", "变更", "进展", "补充协议",
             "届满", "减持", "完成", "进度", "前十名", "前十大", "结果", "草案")

# FIX(2026-09-08, 审计方向2 分层否定词): 硬否/软否分层，供"进展类含增量"分级候选。
# 现生产行为不变（NEG_WORDS 全否）；classify_title_detailed 提供分层视图，
# 供研究验证"进展公告若有金额/比例增量是否值得保留"，验证通过前不改变默认流。
NEG_HARD = ("终止", "取消", "解除", "减持", "结束")          # 明确反向/事件已了结 → 不候选
NEG_SOFT = ("完毕", "届满", "进展", "结果", "完成", "进度", "调整", "变更", "补充协议",
            "前十名", "前十大", "草案")                       # 态度不明 → 默认否，含增量可研究保留


def classify_title_detailed(title):
    """分层分类（研究用）。返回 (is_event, kind, polarity, amount_wan, pct, layer)。
    layer: 'HARD_REJECT' | 'SOFT_REJECT' | 'PROGRESS_WITH_DELTA'(软否但含金额/比例增量) | 'EVENT'。
    PROGRESS_WITH_DELTA 语义：进展/完成类标题里出现明确金额(亿/万)或占比(%)增量 ——
    供 A/B 验证是否比一刀切拒绝更优；默认流(classify_title)仍拒绝。"""
    is_ev, kind, pol, amt, pct = classify_title(title)
    if is_ev:
        return is_ev, kind, pol, amt, pct, "EVENT"
    s = str(title or "")
    if any(n in s for n in NEG_HARD):
        return is_ev, kind, pol, amt, pct, "HARD_REJECT"
    if any(n in s for n in NEG_SOFT) and ("回购" in s or "增持" in s):
        # 软否 + 回购/增持 + 明确增量 → 研究候选
        import re as _re
        has_delta = bool(_re.search(r"[0-9]+(?:\.[0-9]+)?\s*(亿|万|%|股)", s))
        if has_delta:
            kind2 = "BUYBACK" if "回购" in s else "HOLDER_INCREASE"
            # 解析增量规模（复用 classify_title 的解析规则）
            _m = _re.search(r"([0-9]+(?:\.[0-9]+)?)\s*亿(?:元)?", s)
            _amt_v = float(_m.group(1)) * 10000 if _m else None
            _m2 = _re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", s)
            _pct_v = float(_m2.group(1)) if _m2 else None
            return True, kind2, 1, _amt_v, _pct_v, "PROGRESS_WITH_DELTA"
        return is_ev, kind, pol, amt, pct, "SOFT_REJECT"
    if any(n in s for n in NEG_SOFT):
        return is_ev, kind, pol, amt, pct, "SOFT_REJECT"
    return is_ev, kind, pol, amt, pct, "NO_EVENT"


def classify_title(title):
    """统一标题分类。返回 (is_event, kind, polarity, amount_wan, pct)。
    kind: 'BUYBACK' | 'HOLDER_INCREASE' | None；polarity: +1(积极) / -1(反向) / 0(中性)。
    """
    s = str(title or "")
    if any(n in s for n in NEG_WORDS):
        # 反向：减持/解除/终止
        if "减持" in s:
            return False, None, -1, None, None
        return False, None, 0, None, None
    is_buyback = "回购" in s
    is_increase = "增持" in s
    if not (is_buyback or is_increase):
        return False, None, 0, None, None
    kind = "BUYBACK" if is_buyback else "HOLDER_INCREASE"
    # 规模解析（金额/占比）
    amount = None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*亿(?:元)?", s)
    if m:
        amount = float(m.group(1)) * 10000
    else:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*万(?:元)?", s)
        if m:
            amount = float(m.group(1))
    pct = None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", s)
    if m:
        pct = float(m.group(1))
    return True, kind, 1, amount, pct
