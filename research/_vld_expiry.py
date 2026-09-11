# -*- coding: utf-8 -*-
"""_vld_expiry.py —— 挂单 TTL 语义审计: 事件腿挂单(v0)有无 TTL?
V3-A 给组合层加了 _pend_days(5 交易日→TTL_EXPIRED), 但事件腿 v0 挂单(paper_ledger)
的 valid_from 起无 TTL 的话会无限挂 —— 核查 monitor/结算代码。"""
import json, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
R = r"E:\test\smc_project\research"

led = json.load(open(os.path.join(R, "paper_ledger.json"), encoding="utf-8"))
# 状态分布 + 最老未结算挂单
from collections import Counter
st = Counter(str(t.get("status") or "?") for t in led)
print("paper_ledger(139) 状态:", dict(st))
pend = [t for t in led if not t.get("exit") and not t.get("status")]
print(f"无状态/未结算: {len(pend)}")
# 各挂单的 signal_date → valid_from → 至今未成交的(挂了多少天)
import time
for t in led[-12:]:
    vf = str(t.get("valid_from") or "")
    ex = t.get("exit_price") or t.get("exit")
    print(f"  {t['code']} sig={t.get('signal_date')} vf={vf} "
          f"entry={t.get('entry_price')} exit={str(ex)[:12] if ex else '未结算'}")
# TTL 检索: monitor 或 sim 代码里有没有 TTL/过期/撤单
print("\nTTL 检索:")
import subprocess
r = subprocess.run(["powershell", "-Command",
                    "Select-String -Path E:\\test\\smc_project\\research\\sim_scheduler.py,E:\\test\\smc_project\\research\\monitor_loop.py -Pattern 'TTL|ttl|过期|expire|cancel|撤' -ErrorAction SilentlyContinue | Select-Object -First 6 Path,LineNumber,Line"],
                   capture_output=True, text=True)
print(r.stdout or r.stderr or "  (无匹配或文件不存在)")