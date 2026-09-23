# -*- coding: utf-8 -*-
"""gen_audit_portal.py — 研究审计门户静态数据 (handover/*.md → 前端 /audit 页使用)
产出: hermes/web_reports/index.json (报告列表 + KPI 摘要)
      hermes/web_reports/<name>.json (md 原文 + 标题)
"""
import json, os, re, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
HDR = os.path.join(ROOT, "handover")
OUT = os.path.normpath(os.path.join(ROOT, "..", "hermes", "web_reports"))

# 报告顺序(先审计后动刀): R60 → R68 → R74 → R69 → R70 → R72 → R76(+R77并入)
REPORTS = [
    ("R82_v24_full_backtest", "R82 v24 影子(12手术) 全回测: 总览/逐年×权重桶/逐年逐月/季度/裁判表", "最新全套"),
    ("R68_jev_full_report", "R68 逐腿全景报告(1858腿×SMC链×Jev五问)", "完整明细"),
    ("R69_diagnosis", "R69 病灶诊断(13维×4交叉)", "问题清单"),
    ("R70_v23_shadow", "R70/R73b v23→v24 影子组合+验收记录", "手术预注册"),
    ("R72_whale_window", "R72 大资金(内部人)窗口分析", "大鱼追踪"),
    ("R74_smc_signal_audit", "R74 逐SMC信号族审计", "结构元件"),
    ("R76_smc_full_audit", "R76/77 引擎全信号链审计(BSL/SSL/OB/FVG/MSS/OTE/LV)", "核心信号"),
    ("R64_jev_shadow", "R64 Jev接入·生产付", "影子接线"),
    ("R61_alpha_stack", "R61 Jensen Alpha 栈", "Alpha骨架"),
]

# 顶部 KPI 快照卡(手工维护核心数)
KPI_CARDS = [
    {"title": "v22 冻结基线", "val": "PF 3.36", "sub": "1858腿 avg 4.07% WR 64%"},
    {"title": "v24 影子(9手术)", "val": "PF 5.06", "sub": "avg 5.47% WR 71.8%"},
    {"title": "Jev 盲审 TP/SL", "val": "99.0% 合规", "sub": "R65 1858腿 无前视"},
    {"title": "出口结构", "val": "冻结", "sub": "R71 trailing 实回放证伪"},
]


def main():
    os.makedirs(OUT, exist_ok=True)
    index = []
    for slug, title, tag in REPORTS:
        p = os.path.join(HDR, slug + ".md")
        if not os.path.exists(p):
            continue
        md = open(p, encoding="utf-8").read()
        with open(os.path.join(OUT, slug + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"slug": slug, "title": title, "tag": tag, "md": md}, fh, ensure_ascii=False)
        # 短抽 首表前三行
        m = re.search(r"\n((?:\|[^\n]+\n){3,6})", md)
        index.append({"slug": slug, "title": title, "tag": tag, "preview": m.group(1)[:400] if m else ""})
    payload = {"kpis": KPI_CARDS, "reports": index}
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"audit portal → {OUT} ({len(index)} reports)")


if __name__ == "__main__":
    main()
