# -*- coding: utf-8 -*-
"""P2 事件分类黄金标注集回归测试（审计遗留: 事件标注集）
来源: build_events_golden.py 从公告DB分层抽样真实标题(2026-09-08)。
标注集语义(经人工逐条核对 + 注销泄漏发现修正):
  - EVENT: 市场回购方案/提议/首次回购/高管增持 (真实市场动作)
  - INERT_REJECT: 注销/减资/限制性股票/激励/期权/员工持股/质押 (股本管理,非市场回购)
    —— 2026-09-08 发现: 33.7% EVENT 标题属此类(0笔交易,但语义必须上游纠正)
  - HARD_REJECT: 终止/取消/解除/减持/结束
  - SOFT_REJECT: 进展/完成/结果/前十名等无增量
  - NO_EVENT: 非回购/增持标题
"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.events as EV

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

# 黄金标注集(44条真实标题, 语义已人工核对; 期望=修正后语义)
GOLDEN = [
    # --- EVENT: 市场回购/增持(真实动作) ---
    ("北京九州一轨环境科技股份有限公司关于提议回购公司股份暨公司提质增效重回报行动方案的公告", "EVENT"),
    ("天通股份关于以集中竞价交易方式回购公司股份方案的公告", "EVENT"),
    ("关于收到公司持股5%以上股东、实际控制人、董事长提议回购公司股份的提示性公告", "EVENT"),
    ("启明星辰:关于高级管理人员增持公司股份的公告", "EVENT"),
    ("凯普生物:关于2024年第三次以集中竞价交易方式回购公司股份方案首次回购的公告", "EVENT"),
    ("莱伯泰科:关于以集中竞价交易方式回购公司股份方案的公告", "EVENT"),
    # --- INERT_REJECT: 股本管理(回购字样但非市场回购) ---
    ("航宇科技关于回购注销第一类限制性股票减资暨通知债权人的公告", "INERT_REJECT"),
    ("立方制药:关于回购注销部分限制性股票减资暨通知债权人的公告", "INERT_REJECT"),
    ("博腾股份:关于回购注销部分限制性股票的公告", "INERT_REJECT"),
    ("隆基绿能:关于股权激励限制性股票回购注销实施公告", "INERT_REJECT"),
    ("优博讯:关于注销2022年度回购股份并减少注册资本的公告", "INERT_REJECT"),
    ("厦门国贸集团股份有限公司回购注销部分限制性股票的公告", "INERT_REJECT"),
    ("一心堂:关于回购注销2020年限制性股票激励计划预留授予部分限制性股票的公告", "INERT_REJECT"),
    ("ST金圆:关于控股股东部分股份办理股票质押式回购购回解除质押业务的公告", "INERT_REJECT"),
    # --- HARD_REJECT: 反向/了结 ---
    ("英派斯:关于特定股东股份减持计划的预披露公告", "HARD_REJECT"),
    ("康龙化成:关于公司主要股东减持计划时间过半的公告", "HARD_REJECT"),
    ("常宝股份:关于持股5%以上的股东减持至持股5%以下的提示性公告", "HARD_REJECT"),
    ("亚钾国际投资(广州)股份有限公司终止实施2022年股票期权与限制性股票激励计划的公告", "INERT_REJECT"),
    # --- SOFT_REJECT: 进展/结果/完毕无增量 ---
    ("天山电子:关于首次回购公司股份暨回购股份的进展公告", "SOFT_REJECT"),
    ("恒锋信息:关于公司实际控制人、控股股东增持股份计划完成的公告", "SOFT_REJECT"),
    ("捷顺科技:关于公司高级管理人员增持股份结果的公告", "SOFT_REJECT"),
    ("盛德鑫泰:关于股份回购实施结果暨股份变动的公告", "SOFT_REJECT"),
    ("中色股份:关于控股股东增持股份计划实施完毕暨增持结果的公告", "SOFT_REJECT"),
    ("申通快递:关于回购股份事项前十名股东及前十名无限售条件股东持股情况的公告", "SOFT_REJECT"),
    ("欧普照明股份有限公司关于股份回购实施结果暨股份变动的公告", "SOFT_REJECT"),
    # --- NO_EVENT: 非回购/增持 ---
    ("新筑股份:2023年半年度业绩预告", "NO_EVENT"),
    ("中泰证券股份有限公司2023年半年度业绩快报公告", "NO_EVENT"),
    ("特变电工股份有限公司关于召开2023年半年度业绩说明会的公告", "NO_EVENT"),
    ("兖矿能源集团股份有限公司关于兖矿集团财务有限公司2023年半年度未经审计的资产负债表", "NO_EVENT"),
]

print("== P2 事件分类黄金标注集回归(30条真实标题) ==")
for i, (t, exp_layer) in enumerate(GOLDEN):
    is_ev, kind, pol, amt, pct, layer = EV.classify_title_detailed(t)
    # INERT_REJECT/HARD_REJECT/SOFT_REJECT/NO_EVENT 一律非事件; EVENT 必须事件+极性1
    if exp_layer == "EVENT":
        cond = is_ev and layer == "EVENT" and pol == +1 and kind in ("BUYBACK", "HOLDER_INCREASE")
    else:
        cond = (not is_ev) and layer == exp_layer
    ok(f"G{i+1} {exp_layer:12s} {t[:22]}", cond,
       f"got is_ev={is_ev} layer={layer} kind={kind} pol={pol}")

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)