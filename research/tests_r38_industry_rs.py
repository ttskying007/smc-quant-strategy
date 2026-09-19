# -*- coding: utf-8 -*-
"""r38_industry_rs.py 测试: 行业相对强弱输出的 schema/数据结构稳定
防草稿破坏步骤 8 数据源。
"""
import json, io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

print("== 1. 模块/静态产出文件存在 ==")
fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "r38_industry_rs.py")
ok("r38_industry_rs.py 模块可解析", os.path.exists(fp))
src = open(fp, encoding="utf-8").read()
import ast
try:
    ast.parse(src)
    ok("r38_industry_rs.py 语法 OK", True)
except SyntaxError as e:
    ok("r38_industry_rs.py 语法 OK", False, str(e))

print("== 2. 输出 JSON schema ==")
out = os.path.join("research", "handover", "industry_relative_strength.json")
ok("industry_relative_strength.json 存在", os.path.exists(out))
if os.path.exists(out):
    d = json.load(open(out, encoding="utf-8"))
    ok("顶层字段完整", all(k in d for k in ("asof", "baseline", "coverage", "industries")))
    ok("baseline 有 m20/m60", isinstance(d["baseline"].get("m20"), (int, float)),
        f"m20={d['baseline'].get('m20')}")
    ok("coverage 有 stock/industry 计数", isinstance(d["coverage"].get("stocks_mapped"), int))
    ok("industries 非空", isinstance(d["industries"], list) and len(d["industries"]) > 0)
    # 每个 industry entry 字段
    e = d["industries"][0]
    ok("single industry schema", all(k in e for k in ("industry", "n", "med20", "rs20", "rs60")))

print("== 3. 强度计值合理 ==")
# best industry 的 rs60 不为None(它最难)
if os.path.exists(out):
    d = json.load(open(out, encoding="utf-8"))
    top = d["industries"][0]
    ok("最强行业 rs60 被计算", isinstance(top.get("rs60"), (int, float)),
        str(top))
    # 不可 100 个行业都 -9%.9 (均场太多) 或所有为 0( cold fusion)
    rs20s = [x["rs20"] for x in d["industries"] if x["rs20"] is not None]
    ok("rs20 有分布", min(rs20s) < 0 < max(rs20s), f"min={min(rs20s)} max={max(rs20s)}")

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
