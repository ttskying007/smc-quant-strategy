# -*- coding: utf-8 -*-
"""v25 iteration timeline: version numbers vs file mtimes."""
import os, re, datetime

V25 = r"E:\test\smc_project\hermes\scripts\v25"
rows = []
for f in os.listdir(V25):
    if not f.endswith(".py"):
        continue
    m = re.match(r"v(\d+)(?:_[a-z]|\d+)?_", f)
    if not m:
        continue
    ver = int(m.group(1))
    p = os.path.join(V25, f)
    mt = datetime.datetime.fromtimestamp(os.path.getmtime(p))
    rows.append((ver, f, mt))

rows.sort(key=lambda x: x[2])
print("== v25 iteration timeline (version, file, mtime) ==")
for ver, f, mt in rows:
    print(f"v{ver:<4} {mt:%m-%d %H:%M}  {f[:80]}")

# per-day version progression
print("\n== daily version span ==")
days = {}
for ver, f, mt in rows:
    d = mt.strftime("%m-%d")
    days.setdefault(d, []).append(ver)
for d in sorted(days):
    vs = days[d]
    print(f"{d}: versions {min(vs)}-{max(vs)} ({len(vs)} scripts)")
