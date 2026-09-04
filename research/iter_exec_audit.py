# -*- coding: utf-8 -*-
"""执行质量复盘：模拟持仓的成交价 vs 信号后最佳价（买早/卖早检测）
买早：成交价高于信号日收盘（挂单价）应回落才成交 —— 检查是否追高
卖早：TP/SL 触发是否过早（相比持有到最优）"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
filled = [t for t in led if t.get("status") == "FILLED"]
print(f"FILLED 持仓: {len(filled)} 笔\n")

issues = []
for t in filled:
    code = t.get("code")
    sig_d = str(t.get("signal_date", "")).replace("-", "")
    entry = t.get("entry_price") or 0
    fill_p = t.get("filled_price") or 0
    bs = ps.bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if sig_d not in dates:
        continue
    i = dates.index(sig_d)
    disc_close = bs[i]["c"]
    next_open = bs[i + 1]["o"] if i + 1 < len(bs) else 0
    # 买早检查：挂单逻辑是"回落至披露日收盘或以下成交"
    # 若成交价 > 披露日收盘 → 买早了（追高）
    if entry and disc_close and entry > disc_close * 1.001:
        issues.append({"code": code, "name": t.get("name"), "type": "买早",
                       "detail": f"挂单价 {entry} > 披露日收盘 {disc_close}（应回落成交）"})
    # 卖早检查：TP/SL 触发 vs 持有到期（需要 exit 数据）
    if t.get("exit_reason") and t.get("pnl_pct") is not None:
        # 若 pnl 为负且非 SL 触发 → 可能卖早
        if t.get("pnl_pct", 0) < 0 and "SL" not in str(t.get("exit_reason", "")):
            issues.append({"code": code, "name": t.get("name"), "type": "卖早?",
                           "detail": f"负收益 {t.get('pnl_pct'):+.2f}% 但非SL触发: {t.get('exit_reason')}"})

if issues:
    print("=== 执行质量问题 ===")
    for x in issues:
        print(f"  [{x['type']}] {x['code']} {x['name']}: {x['detail']}")
else:
    print("无执行质量问题（全部按规则成交）")

# 成交价 vs 披露日收盘统计
print("\n=== 成交价 vs 披露日收盘 ===")
ok = 0
for t in filled:
    code = t.get("code")
    sig_d = str(t.get("signal_date", "")).replace("-", "")
    entry = t.get("entry_price") or 0
    bs = ps.bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if sig_d not in dates:
        continue
    i = dates.index(sig_d)
    disc = bs[i]["c"]
    if entry and disc:
        if entry <= disc * 1.001:
            ok += 1
print(f"按规则（≤披露日收盘）成交: {ok}/{len(filled)} ({100*ok/len(filled) if filled else 0:.0f}%)")
