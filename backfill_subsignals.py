# -*- coding: utf-8 -*-
"""回填子信号明细到已有持仓（事件腿 + 延续腿）"""
import io, json, os, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = ps.load_ledger()
n = 0
for t in led:
    if t.get("sub_signals"):
        continue
    code = t.get("code", "")
    sig_d = str(t.get("signal_date") or t.get("disclose_date") or "").replace("-", "")
    bs = ps.bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if sig_d not in dates:
        continue
    i = dates.index(sig_d)
    if t.get("source") == "CONT":
        ed = str(t.get("entry_date", ""))
        ei = dates.index(ed) if ed in dates else i + 1
        t["sub_signals"] = ps.sub_signals_cont(bs, ei if ei >= 60 else max(60, ei), sig_d)
    else:
        t["sub_signals"] = ps.sub_signals_event(bs, i, sig_d)
    n += 1
ps.save_ledger(led)
print(f"回填子信号: {n} 笔")
# sample
for t in led[:3]:
    print(f"  {t.get('code')} {t.get('signal_combo')}: {[s['name'] for s in t.get('sub_signals', [])]}")
