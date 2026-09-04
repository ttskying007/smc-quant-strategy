# -*- coding: utf-8 -*-
"""验证阶段/ADX 过滤有效性：对 8-17~8-19 已选事件重新应用过滤
检查过滤是否拒绝了表现差的信号（过滤有效性的关键验证）"""
import io, json, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
new = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-17"]

print("=== 8-17~8-19 已选事件：重新应用过滤验证 ===\n")
for t in new:
    code = t.get("code")
    sig_d = str(t.get("signal_date", "")).replace("-", "")
    bs = ps.bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if sig_d not in dates:
        continue
    i = dates.index(sig_d)
    st, deep = ps.stage_and_deep(bs, i)
    adx = ps.adx14_of(bs, i)
    passed = st in ("ACCUM", "DOWNTREND") and adx is not None and adx >= 20
    mp = t.get("mark_pnl_pct")
    mp_s = f"{mp:+.2f}%" if mp is not None else "?"
    status = "✅通过" if passed else "❌拒绝"
    print(f"  {code} {t.get('name')} sig={sig_d} 阶段={st} ADX={adx if adx is None else round(adx,1)} {status} 浮盈={mp_s}")

# summary
passed = [t for t in new if (lambda b, d: (lambda i: (lambda st, a: st in ("ACCUM","DOWNTREND") and a is not None and a >= 20)(ps.stage_and_deep(b, i)[0], ps.adx14_of(b, i)))(d.index(str(t.get('signal_date','')).replace('-','')) if str(t.get('signal_date','')).replace('-','') in d else -1))(ps.bars_of(t.get('code')), [x['t'] for x in ps.bars_of(t.get('code'))])]
