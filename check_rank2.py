# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
recent = [t for t in led if t.get("rank_score")]
print("有 rank_score 的持仓:", len(recent))
for t in sorted(recent, key=lambda x: -x.get("rank_score", 0))[:6]:
    print(f"  {t.get('code')} {t.get('name')} stage={t.get('stage')} rank={t.get('rank_score')} combo={t.get('signal_combo')} sig={t.get('signal_date')}")
