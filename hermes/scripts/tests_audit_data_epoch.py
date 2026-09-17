# -*- coding: utf-8 -*-
"""tests_audit_data_epoch.py —— 数据 epoch manifest 回归锁(审计§2.2/§3.7).

审计关切: 研究产物必须保存原始数据 epoch, 防止缓存更新后同一日期内容变化
导致 generator/oracle 输入漂移.

修复: v25/data_epoch.py —— build_manifest / verify_manifest.
本测试固化:
  1. build: 生成 manifest(文件数/哈希/epoch_id)
  2. verify 一致: 缓存未变 -> ok=True
  3. verify 漂移: 修改一个文件内容 -> ok=False, changed 检测到
  4. verify 新增/删除: 检测 added/missing
  5. 确定性: 同内容两次 build 的 epoch_id 一致
纯临时文件, 不触碰生产缓存.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile

# 注: 不重定向 stdout(-X utf8 已保证 UTF-8), 避免 Windows buffer 关闭问题
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + str(detail))


from v25.data_epoch import build_manifest, verify_manifest  # noqa: E402

tmp = tempfile.mkdtemp(prefix="epoch_test_")
try:
    print("== 1. build 生成 manifest ==")
    for i in range(3):
        with open(os.path.join(tmp, "6000%02d_daily_750.json" % i), "w") as fh:
            fh.write('{"t":"2024-01-0%d","o":10,"h":11,"l":9,"c":10,"v":100}' % i)
    m1 = build_manifest(tmp, pattern="_daily_750.json")
    ok("manifest 含 3 文件", m1["file_count"] == 3, m1["file_count"])
    ok("manifest 含每文件哈希", all(k in m1["files"] for k in
       ("600000_daily_750.json", "600001_daily_750.json", "600002_daily_750.json")))
    ok("epoch_id 为 16 位 hex", len(m1["epoch_id"]) == 16, m1["epoch_id"])

    print("== 2. verify 一致 ==")
    ok_ver, detail = verify_manifest(m1, tmp)
    ok("缓存未变 -> 一致", ok_ver is True, detail)

    print("== 3. verify 漂移(修改文件) ==")
    with open(os.path.join(tmp, "600001_daily_750.json"), "w") as fh:
        fh.write('{"t":"2024-01-02","o":10,"h":12,"l":9,"c":11,"v":200}')
    ok_ver2, detail2 = verify_manifest(m1, tmp)
    ok("修改文件 -> 漂移", ok_ver2 is False, detail2)
    ok("changed 检测到该文件", "600001_daily_750.json" in detail2["changed"], detail2["changed"])

    print("== 4. verify 新增/删除 ==")
    with open(os.path.join(tmp, "600003_daily_750.json"), "w") as fh:
        fh.write('{"t":"2024-01-03"}')
    ok_ver3, detail3 = verify_manifest(m1, tmp)
    ok("新增文件 -> 漂移", ok_ver3 is False, detail3)
    ok("added 检测到新文件", "600003_daily_750.json" in detail3["added"], detail3["added"])
    os.remove(os.path.join(tmp, "600000_daily_750.json"))
    ok_ver4, detail4 = verify_manifest(m1, tmp)
    ok("删除文件 -> 漂移", ok_ver4 is False, detail4)
    ok("missing 检测到删除", "600000_daily_750.json" in detail4["missing"], detail4["missing"])

    print("== 5. 确定性 ==")
    m2 = build_manifest(tmp, pattern="_daily_750.json")
    m3 = build_manifest(tmp, pattern="_daily_750.json")
    ok("同内容两次 build epoch_id 一致", m2["epoch_id"] == m3["epoch_id"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)