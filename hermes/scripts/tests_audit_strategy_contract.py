# -*- coding: utf-8 -*-
"""tests_audit_strategy_contract.py — 单一策略合同回归锁(审计§5.2/Iteration 6)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "v25"))
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + str(detail))


from strategy_contract import (build_contract, contract_hash, verify_contract,
                               signature, four_end_consistent)  # noqa: E402

print("== 1. 合同构建与哈希稳定 ==")
c1 = build_contract("SMC_SSL_RECLAIM_V1")
c2 = build_contract("SMC_SSL_RECLAIM_V1")
h1, h2 = contract_hash(c1), contract_hash(c2)
ok("同策略两次构建哈希一致(确定性)", h1 == h2, (h1, h2))
ok("哈希为 16 位 hex", len(h1) == 16, h1)
ok("默认字段正确", c1["decision_delay"] == "T+1_OPEN"
   and c1["target_visibility"] == "PRE_ENTRY_CONFIRMED_ONLY"
   and c1["production_write"] is False, c1)

print("== 2. 篡改检测 ==")
ok("原合同验证通过", verify_contract(c1, h1)[0] is True)
c3 = dict(c1)
c3["decision_delay"] = "SAME_DAY"   # 篡改
ok("篡改后哈希变化", contract_hash(c3) != h1)
ok("篡改后验证失败", verify_contract(c3, h1)[0] is False,
   verify_contract(c3, h1))

print("== 3. 合同签名 ==")
s = signature(c1)
ok("签名含 hash + 关键字段", s["contract_hash"] == h1
   and s["production_write"] is False and s["gate"]["wr_min"] == 55.0, s)

print("== 4. 四端一致性(Iteration 6 验收) ==")
registry = {"production_strategy": "SMC_SSL_RECLAIM_V1", "contract_hash": h1}
ok4, parts = four_end_consistent(registry, s, s, s)
ok("四端 hash 一致 -> 通过", ok4 is True, parts)

# 前端 hash 不同(版本漂移) -> 失败
frontend_bad = dict(s)
frontend_bad["contract_hash"] = "deadbeef"
ok5, parts5 = four_end_consistent(registry, s, s, frontend_bad)
ok("前端 hash 漂移 -> 不一致", ok5 is False, parts5)
ok("漂移定位到 frontend", parts5["frontend"] == "deadbeef", parts5)

print("== 5. registry 无合同 -> fail-closed ==")
ok6, parts6 = four_end_consistent({}, s, s, s)
ok("registry 无 contract_hash -> 拒绝", ok6 is False, parts6)

print("== 6. EMPTY_BOOK 语义(审计 1.2) ==")
empty = build_contract("EMPTY_BOOK")
ok("EMPTY_BOOK production_write=False", empty["production_write"] is False, empty)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)