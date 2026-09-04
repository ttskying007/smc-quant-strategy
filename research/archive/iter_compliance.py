# -*- coding: utf-8 -*-
"""验证实盘选股合规性：当前模拟持仓中是否有应被新过滤（阶段/ADX/事件类型）拒绝的信号"""
import io, json, sys
import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
# 8-17 起新信号（应有过滤）
new = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-17"]
print(f"8-17 起新信号: {len(new)} 笔\n")

violations = []
for t in new:
    code = t.get("code")
    sig = str(t.get("signal_date", "")).replace("-", "")
    bs = ps.bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if sig not in dates:
        continue
    i = dates.index(sig)
    st, deep = ps.stage_and_deep(bs, i) if i >= 91 else (None, False)
    adx = ps.adx14_of(bs, i)
    ok_stage = st in ("ACCUM", "DOWNTREND")
    ok_adx = adx is not None and adx >= 20
    if not (ok_stage and ok_adx):
        violations.append({"code": code, "name": t.get("name"), "stage": st, "adx": adx,
                           "sig": t.get("signal_date"), "status": t.get("status"),
                           "mp": t.get("mark_pnl_pct")})

if violations:
    print("=== 应被过滤但已选入的信号（违规）===")
    for v in violations:
        mp = v["mp"]
        mp_s = f"{mp:+.2f}%" if mp is not None else "-"
        print(f"  {v['code']} {v['name']} sig={v['sig']} 阶段={v['stage']} ADX={v['adx'] if v['adx'] is None else round(v['adx'],1)} 状态={v['status']} 浮盈={mp_s}")
else:
    print("✅ 全部新信号符合过滤（阶段 ACCUM/DOWNTREND + ADX≥20）")

# 8-17 前的旧持仓（无过滤选入）—— 不违规（历史遗留）
old = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) < "2026-08-17"]
print(f"\n8-17 前旧持仓（历史遗留，无过滤选入）: {len(old)} 笔")
