# -*- coding: utf-8 -*-
"""core/manifest.py 单元测试（蓝图迭代二）"""
import io, json, os, sys, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import manifest as M

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

print("== manifest 基本构造 ==")
m = M.build_manifest("run-001", "smc_v20f", "v20f", params={"max_hold": 12},
                     data_asof="20260904", data_snapshot_id="snap-20260904",
                     status="research")
ok("含 code_commit", bool(m.get("code_commit")), m.get("code_commit"))
ok("param_hash 16位", len(m.get("parameter_profile", "")) == 16, m.get("parameter_profile"))
ok("status=research", m.get("status") == "research")
valid, why = M.validate_manifest(m)
ok("validate 通过", valid, why)

print("== 缺核心字段 → invalid ==")
m2 = M.build_manifest("run-002", "smc_v20f", "v20f", params=None,
                      data_asof="", status="production")
ok("缺 data_asof → invalid", m2.get("status") == "invalid", m2.get("invalid_reason"))
valid2, why2 = M.validate_manifest(m2)
ok("validate 拒绝", not valid2, why2)

print("== 保存/加载往返 ==")
with tempfile.TemporaryDirectory() as td:
    p = M.save_manifest(m, td)
    ok("manifest.json 存在", os.path.exists(p))
    with open(p, encoding="utf-8") as fh:
        loaded = json.load(fh)
    ok("往返一致", loaded["run_id"] == "run-001")

print("== artifact hash ==")
with tempfile.TemporaryDirectory() as td:
    fp = os.path.join(td, "x.csv")
    with open(fp, "w", encoding="utf-8") as fh:
        fh.write("a,b\n1,2\n")
    m3 = M.build_manifest("run-003", "s", "v1", params={}, artifact_paths=[fp], status="research")
    ok("artifact_hash 16位", len(m3["artifact_hash"].get(fp, "")) == 16, m3["artifact_hash"])
    ok("不存在文件 → missing", M.file_hash(os.path.join(td, "none.json")) == "missing")

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
