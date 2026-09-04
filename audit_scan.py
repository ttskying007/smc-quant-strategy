# -*- coding: utf-8 -*-
"""SMC project audit scanner - collects structured facts for review."""
import os, re, json, collections, hashlib, sys

ROOT = r"E:\test\smc_project\hermes"
SCRIPTS = os.path.join(ROOT, "scripts")

def walk(base):
    for dp, dn, fn in os.walk(base):
        # skip __pycache__
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in fn:
            p = os.path.join(dp, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            rel = os.path.relpath(p, ROOT)
            yield rel, st.st_size, st.st_mtime

files = list(walk(ROOT))
print("== TOTAL FILES:", len(files))
total_size = sum(s for _, s, _ in files)
print("== TOTAL SIZE: %.1f GB" % (total_size / 1e9))

# 1. Version dirs under /root/.hermes (smc_opt_*)
opt_dirs = sorted(d for d in os.listdir(ROOT) if d.startswith("smc_opt_"))
print("\n== SMC_OPT DIRS (%d):" % len(opt_dirs))
for d in opt_dirs:
    full = os.path.join(ROOT, d)
    n = sum(len(fn) for _, _, fn in os.walk(full))
    sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fn in os.walk(full) for f in fn)
    # newest file mtime
    newest = max((os.path.getmtime(os.path.join(dp, f)) for dp, _, fn in os.walk(full) for f in fn), default=0)
    import datetime
    ts = datetime.datetime.fromtimestamp(newest).strftime("%Y-%m-%d") if newest else "-"
    print("  %-55s files=%-6d size=%.1fM newest=%s" % (d, n, sz / 1e6, ts))

# 2. Production / gate / contract dirs
print("\n== PRODUCTION-NAMED DIRS:")
for d in opt_dirs:
    if any(k in d for k in ("production", "gate", "contract", "candidate")):
        full = os.path.join(ROOT, d)
        reports = [f for f in os.listdir(full) if f.endswith((".json", ".md"))]
        print("  %-55s reports=%s" % (d, reports[:6]))

# 3. Largest files top 30
print("\n== LARGEST FILES (top 30):")
for rel, sz, mt in sorted(files, key=lambda x: -x[1])[:30]:
    print("  %10.1fM  %s" % (sz / 1e6, rel))

# 4. Version number distribution in scripts filenames
print("\n== SCRIPT VERSION MARKERS (top 40 patterns):")
cnt = collections.Counter()
for rel, sz, mt in files:
    if rel.startswith("scripts"):
        base = os.path.basename(rel)
        m = re.search(r"v(\d+)(?:_v\d+|_\d+)?", base.lower())
        if m:
            v = int(m.group(1))
            cnt[v] += 1
for v, c in sorted(cnt.items()):
    print("  v%-6d -> %d files" % (v, c))

# 5. Code line counts
print("\n== PY LINE COUNTS (top 40):")
py = [(rel, sz) for rel, sz, _ in files if rel.endswith(".py")]
print("  total .py files:", len(py))
lines = []
for rel, sz in py:
    try:
        with open(os.path.join(ROOT, rel), "r", encoding="utf-8", errors="replace") as fh:
            n = sum(1 for _ in fh)
        lines.append((rel, n))
    except Exception:
        pass
for rel, n in sorted(lines, key=lambda x: -x[1])[:40]:
    print("  %6d  %s" % (n, rel))
print("  total LOC: %d" % sum(n for _, n in lines))

# 6. Dirty filenames (newlines etc.)
print("\n== DIRTY FILENAMES (newline/control chars):")
for rel, sz, mt in files:
    if any(c in rel for c in ("\n", "\r", "\t")):
        print("  %r (%d bytes)" % (rel, sz))
