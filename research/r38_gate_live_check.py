# -*- coding: utf-8 -*-
"""r38_gate_live_check.py —— 门槛在真实选股中是否触发(生效性端到端验证).

背景(R38ae): 曾发现"代码已改但门槛未生效"(config 晚于进程启动)。
本轮做端到端验证: 真实选股跑过后, 台账里是否出现 RANK_LT3 / skipped_rank。

只读检查, 绝不调用 daily_selection()。
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
FILES = ("selection_funnel.json", "reject_ledger.json", "paper_ledger.json",
         "selection_funnel_history.json")

print("=" * 84)
print("门槛生效性端到端检查")
print("=" * 84)
for fn in FILES:
    p = os.path.join(HERE, fn)
    if not os.path.exists(p):
        print("%-34s MISSING" % fn)
        continue
    import datetime
    mt = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        d = json.load(open(p, encoding="utf-8"))
        s = json.dumps(d, ensure_ascii=False)
    except Exception as e:
        print("%-34s %s  (parse err %s)" % (fn, mt, e))
        continue
    hit_rank = "RANK_LT" in s
    hit_stat = "skipped_rank" in s
    print("%-34s %s" % (fn, mt))
    print("%-34s   RANK_LT=%s  skipped_rank=%s" % ("", hit_rank, hit_stat))
    if fn == "selection_funnel.json" and isinstance(d, dict):
        print("%-34s   generated_at=%s" % ("", d.get("generated_at")))
        tt = d.get("terminal_stage_counts")
        if isinstance(tt, dict):
            rel = {k: v for k, v in tt.items() if "RANK" in str(k).upper()}
            print("%-34s   terminal RANK_*: %s" % ("", rel or "(none)"))
    if hit_rank or hit_stat:
        # 打印上下文片段
        idx = s.find("RANK_LT")
        if idx < 0:
            idx = s.find("skipped_rank")
        print("%-34s   片段: ...%s..." % ("", s[max(0, idx - 60):idx + 120]))
print()
print("注: 若所有文件均为 8:00 左右(早于 09:24 重启), 说明今日选股尚未运行, 需等待。")