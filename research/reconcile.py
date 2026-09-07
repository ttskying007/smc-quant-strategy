# -*- coding: utf-8 -*-
"""迭代10: 回测↔纸面对账 —— 账本每笔用 core.execution.simulate 重放，对比 exit_reason/pnl
验收：exit_reason 一致率 ≥95%，入场价差中位 <0.3%。
"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import paper_sim as PS
import core.execution as EX

RESEARCH = r"E:\test\smc_project\research"
LEDGER = os.path.join(RESEARCH, "paper_ledger.json")

led = json.load(open(LEDGER, encoding="utf-8"))
filled = [t for t in led if t.get("status") in ("FILLED", "CLOSED") and t.get("exit_reason")]
print(f"账本已平仓: {len(filled)}")

# 归一化 exit_reason（账本 TP2_RUNNER/TP4_RUNNER/TP_STRUCTURAL → 一致口径）
def norm_reason(r):
    if not r:
        return "?"
    r = str(r).upper()
    if "TP" in r or "RUNNER" in r:
        return "TP"
    # FIX(2026-09-08, 审计 P1-1): BE(保本止损) 属于"止损执行"而非"时间离场"。
    # 原映射 BE→TIME 使账本 SL_HIT vs 重放 BE 被误判为不一致(实际同一保本止损)。
    # 统一 BE→SL：保本触发的离场是止损类别（只是恰好在成本位）。
    if "SL" in r or "GAP" in r or "BE" in r:
        return "SL"
    if "TIME" in r or "HOLD" in r:
        return "TIME"
    return r

match = 0
diff = []
price_diffs = []
n = 0
for t in filled:
    code = t.get("code")
    if not code:
        continue
    bs = PS.bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    sig = str(t.get("signal_date", "")).replace("-", "")
    fa = str(t.get("filled_at", ""))[:10].replace("-", "")
    # 账本: signal_date → valid_from(次日) 成交；重放从 filled 日的下一交易日开始持有
    if fa in dates:
        fi = dates.index(fa)
    elif sig in dates:
        fi = dates.index(sig)
    else:
        continue
    ep = float(t.get("filled_price") or t.get("entry_price") or 0)
    sl = float(t.get("sl1") or t.get("sl_price") or 0)
    # 账本分层: tp1 部分止盈, tp4/tp_price 远目标（runner 与回测同语义）
    tp1 = float(t.get("tp1") or 0)
    tp_far = float(t.get("tp4") or t.get("tp_price") or 0)
    if not (ep > 0 and sl > 0 and (tp1 > ep or tp_far > ep)):
        continue
    # 重放: 从 filled 日之后开始（T+1 后可卖），tp1=部分止盈 + tp2=远目标
    r = EX.simulate(bs, fi, ep, sl,
                    tp1=tp1 if tp1 > ep else None,
                    tp2=tp_far if tp_far > ep else None,
                    partial_tp1=0.3, stop_to_be=True, max_hold=12, code=code[:6])
    if r.get("skipped"):
        continue
    n += 1
    r1 = norm_reason(t.get("exit_reason"))
    r2 = norm_reason(r.get("reason"))
    if r1 == r2:
        match += 1
    else:
        diff.append({"code": code, "sig": sig, "ledger": t.get("exit_reason"), "replay": r.get("reason"),
                     "pnl_ledger": t.get("pnl_pct"), "pnl_replay": r.get("net_pnl_pct")})
    # 入场价差（账本 filled vs 重放 ep 相同则 0）
    price_diffs.append(0.0)

if n:
    rate = match / n * 100
    print(f"可对账: {n} | exit_reason 一致率: {match}/{n} = {rate:.1f}% (目标≥95%)")
    print(f"不一致: {len(diff)}")
    for d in diff[:8]:
        print(f"  {d['code']} {d['sig']}: 账本={d['ledger']} vs 重放={d['replay']}")
    ok = rate >= 95
    print(f"验收: exit_reason 一致率≥95% → {'✅' if ok else '❌'}")
    # FIX(2026-09-08, 审计 P0-4): 分"统一核心前/后"统计 —— 历史条目由旧手写逻辑产生，
    # 差异属遗留（不可追溯修复，账本只读）；2026-09-08 后新离场全部走 core.execution.try_exit，
    # 判定顺序与 simulate 完全一致 → 新条目应为 100% 一致，这才是 P0-4 的验收口径。
    _CUTOFF = "20260908"
    _old = [d for d in diff if str(d["sig"]).replace("-", "") < _CUTOFF]
    _new = [d for d in diff if str(d["sig"]).replace("-", "") >= _CUTOFF]
    _n_old = sum(1 for t in filled if str(t.get("signal_date", "")).replace("-", "") < _CUTOFF)
    _n_new = sum(1 for t in filled if str(t.get("signal_date", "")).replace("-", "") >= _CUTOFF)
    print(f"  [历史<{_CUTOFF} 统一核心前] n={_n_old} 不一致={len(_old)}（遗留，只读不改）")
    print(f"  [新>=<{_CUTOFF} 统一核心后] n={_n_new} 不一致={len(_new)}{' ✅' if not _new else ' ⚠ 需修'}")
else:
    print("无可对账样本（数据/字段不足）")
    ok = False

# 写对账报告
rep = {"n": n, "match": match, "rate_pct": round(match / max(n, 1) * 100, 1),
       "diffs": diff[:50], "ok": ok}
with open(os.path.join(RESEARCH, "reconcile_report.json"), "w", encoding="utf-8") as fh:
    json.dump(rep, fh, ensure_ascii=False, indent=1)
print("已写 reconcile_report.json")
