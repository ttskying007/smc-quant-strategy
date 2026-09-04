# -*- coding: utf-8 -*-
"""Code quality metrics for SMC project."""
import os, re, collections, hashlib

SCRIPTS = r"E:\test\smc_project\hermes\scripts"

def walk_py(base):
    out = []
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in fn:
            if f.endswith(".py"):
                out.append(os.path.join(dp, f))
    return out

py = walk_py(SCRIPTS)
print("total py files:", len(py))

# 1. hardcoded /root/.hermes refs
print("\n== FILES WITH /root/.hermes HARDCODE:")
cnt = 0
for p in py:
    try:
        txt = open(p, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    n = txt.count("/root/.hermes")
    if n:
        cnt += 1
        if cnt <= 15:
            print("  %-60s refs=%d" % (os.path.relpath(p, SCRIPTS), n))
print("  ... total files with hardcoded /root/.hermes:", cnt)

# 2. TODO/FIXME/HACK/XXX
print("\n== TODO/FIXME/HACK/XXX:")
t = collections.Counter()
for p in py:
    try:
        txt = open(p, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    for m in re.findall(r"\b(TODO|FIXME|HACK|XXX|BUG)\b", txt):
        t[m] += 1
print("  ", dict(t))

# 3. rough similarity: compare line sets of large v11/v25 files
print("\n== NEAR-DUPLICATE CANDIDATES (top 15 by identical-line ratio):")
def norm_lines(path):
    try:
        return [l.strip() for l in open(path, encoding="utf-8", errors="replace") if l.strip() and not l.strip().startswith("#")]
    except Exception:
        return []
big = [p for p in py if os.path.getsize(p) > 50000]
res = []
for i in range(len(big)):
    for j in range(i + 1, len(big)):
        a, b = norm_lines(big[i]), norm_lines(big[j])
        if not a or not b:
            continue
        sa, sb = set(a), set(b)
        inter = len(sa & sb)
        ratio = inter / min(len(sa), len(sb))
        if ratio > 0.5:
            res.append((ratio, os.path.relpath(big[i], SCRIPTS), os.path.relpath(big[j], SCRIPTS)))
for r, x, y in sorted(res, reverse=True)[:15]:
    print("  %.2f  %s  <=>  %s" % (r, x, y))

# 4. v11 vs v25 vs root stats
print("\n== SUBDIR STATS:")
for sub in ["", "v11", "v25", "v2", "v3"]:
    base = os.path.join(SCRIPTS, sub) if sub else SCRIPTS
    files = walk_py(base)
    loc = 0
    for p in files:
        try:
            loc += sum(1 for _ in open(p, encoding="utf-8", errors="replace"))
        except Exception:
            pass
    print("  scripts%s: %d files, %d LOC" % (("/" + sub) if sub else "", len(files), loc))

# 5. import graph: which files are never imported (isolated)
print("\n== ISOLATION SAMPLE (files not imported by any other py):")
imported = set()
for p in py:
    try:
        txt = open(p, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    for m in re.findall(r"(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)", txt):
        imported.add(m)
iso = []
for p in py:
    base = os.path.splitext(os.path.basename(p))[0]
    if base not in imported and "signals_" not in base and not base.startswith("smc_engine"):
        iso.append(os.path.relpath(p, SCRIPTS))
print("  candidate isolated files (sample):", len(iso))
for x in sorted(iso)[:20]:
    print("   ", x)
