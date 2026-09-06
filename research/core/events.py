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
