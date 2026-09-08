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

print("== P0-1 fail-closed: validate_artifacts ==")
with tempfile.TemporaryDirectory() as td:
    # 正常 artifact
    good = os.path.join(td, "good.json")
    with open(good, "w", encoding="utf-8") as fh:
        fh.write('{"k": 1}')
    m_ok = M.build_manifest("run-ok", "s", "v1", params={}, artifact_paths=[good], status="production")
    ok("正常 artifact 验证通过", M.validate_artifacts(m_ok)[0])
    # 缺失 artifact
    miss = os.path.join(td, "missing.json")
    m_miss = M.build_manifest("run-miss", "s", "v1", params={}, artifact_paths=[miss], status="production")
    ok_miss, why_miss = M.validate_artifacts(m_miss)
    ok("缺失 artifact → 验证失败", not ok_miss, why_miss)
    ok("缺失 artifact → status=INVALID", m_miss.get("status") == "INVALID", m_miss.get("status"))
    # 空 artifact
    empty = os.path.join(td, "empty.json")
    open(empty, "w").close()
    m_empty = M.build_manifest("run-empty", "s", "v1", params={}, artifact_paths=[empty], status="production")
    ok_empty, why_empty = M.validate_artifacts(m_empty)
    ok("空 artifact → 验证失败", not ok_empty, why_empty)
    # 哈希不符（写后篡改）
    tamper = os.path.join(td, "tamper.json")
    with open(tamper, "w", encoding="utf-8") as fh:
        fh.write("v1")
    m_t = M.build_manifest("run-tamper", "s", "v1", params={}, artifact_paths=[tamper], status="production")
    with open(tamper, "w", encoding="utf-8") as fh:
        fh.write("v2-CHANGED")
    ok_t, why_t = M.validate_artifacts(m_t)
    ok("哈希不符 → 验证失败", not ok_t, why_t)

print("== P0-1 finalize_manifest: 原子写+生产阻断 ==")
with tempfile.TemporaryDirectory() as td:
    good = os.path.join(td, "a.json")
    with open(good, "w", encoding="utf-8") as fh:
        fh.write('{"ok": true}')
    m_f = M.build_manifest("run-f", "s", "v1", params={}, status="production")
    p, okf = M.finalize_manifest(m_f, [good], td)
    ok("finalize 正常 → 返回ok", okf and os.path.exists(p), str(okf))
    # 缺失 artifact → 抛 RuntimeError（fail-closed 阻断）
    m_bad = M.build_manifest("run-bad", "s", "v1", params={}, status="production")
    raised = False
    try:
        M.finalize_manifest(m_bad, [os.path.join(td, "none.json")], td)
    except RuntimeError as e:
        raised = "blocked" in str(e)
    ok("缺失 artifact → finalize 抛 RuntimeError(阻断)", raised)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
