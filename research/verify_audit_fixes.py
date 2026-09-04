# -*- coding: utf-8 -*-
"""验证审计修复：market_latest / stage_and_deep 复用 / 账本原子写"""
import sys, os, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
sys.path.insert(0, r"E:\test\smc_project\wdh")

print("=== 1. market_latest（Sina 权威解析）===")
import current_scanner as CS
try:
    d = CS.market_latest()
    print("latest:", d, "| 格式正确:", len(d) == 8 and d.isdigit())
except Exception as e:
    print("market_latest ERR:", e)

print("\n=== 2. stage_and_deep 复用（扫描器一致性）===")
import paper_sim as PS
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
import glob
files = glob.glob(os.path.join(KT, "*_daily_800.json"))[:2]
for f in files:
    bs = CS.bars(f)
    if len(bs) >= 120:
        st, deep = PS.stage_and_deep(bs, len(bs) - 1)
        print(f"{os.path.basename(f)}: stage={st} deep={deep} bars={len(bs)} 含v={ 'v' in bs[-1] }")
        break

print("\n=== 3. 账本原子写往返 ===")
LEDGER = r"E:\test\smc_project\research\paper_ledger.json"
before = json.load(open(LEDGER, encoding="utf-8"))
print("账本条目:", len(before), "| 状态:", {s: sum(1 for t in before if t.get('status')==s) for s in set(t.get('status','?') for t in before)})
# 验证原子写不破坏现有账本
PS.save_ledger(before)
after = json.load(open(LEDGER, encoding="utf-8"))
print("往返一致:", len(before) == len(after))

print("\n=== 4. load_ledger 损坏保护 ===")
tmp = LEDGER + ".bak_test"
os.rename(LEDGER, tmp)
try:
    open(LEDGER, "w", encoding="utf-8").write("{broken json")
    try:
        PS.load_ledger()
        print("异常未抛出（不应发生）")
    except RuntimeError as e:
        print("✅ 损坏账本正确抛异常:", str(e)[:60])
finally:
    os.remove(LEDGER)
    os.rename(tmp, LEDGER)
print("账本已恢复")
