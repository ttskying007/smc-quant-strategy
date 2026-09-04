# -*- coding: utf-8 -*-
"""R9 audit: verify v10 contract text == code parameters across all scripts."""
import io, os, sys, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CHECKS = [
    # (contract item, expected, file, pattern hint)
    ("r20 < 0.15", "0.15", "combo_v10_run.py", "r20"),
    ("VWAP dev >= 0.03", "0.03", "combo_v3_run.py", "vwap_dev"),
    ("DEEP ret90 < -0.20", "-0.20", "combo_v10_run.py", "ret90"),
    ("DEEP vt90 < 0.75", "0.75", "combo_v10_run.py", "vt90"),
    ("DEEP hold 20", "20", "combo_v10_run.py", "hold"),
    ("non-DEEP hold 10", "10", "combo_v10_run.py", "hold"),
    ("SL buffer 0.99", "0.99", "wdh_engine.py", "SL_BUFFER"),
    ("fee 0.20", "0.20", "combo_v10_run.py", "0.20"),
]

for label, expected, fname, hint in CHECKS:
    p = os.path.join(r"E:\test\smc_project", "research" if fname != "wdh_engine.py" else "wdh", fname)
    if not os.path.exists(p):
        print(f"  [MISS] {label}: {fname} not found")
        continue
    txt = open(p, encoding="utf-8", errors="replace").read()
    found = expected in txt
    print(f"  [{'OK' if found else 'CHECK'}] {label}: expected {expected} in {fname}")

# specific spot checks
print("\n=== 关键参数抽查 ===")
for fname in ("combo_v10_run.py",):
    p = os.path.join(r"E:\test\smc_project", "research", fname)
    txt = open(p, encoding="utf-8", errors="replace").read()
    for pat in ["hold = 20 if deep else 10", "ret90 < -0.20", "vt90 < 0.75", "0 <= r20 < 0.15"]:
        print(f"  {fname}: '{pat}' -> {'OK' if pat in txt else 'MISSING!'}")

# paper_tracker v10 params
p = os.path.join(r"E:\test\smc_project", "research", "paper_tracker.py")
txt = open(p, encoding="utf-8", errors="replace").read()
for pat in ["ret90 < -0.20 and vt < 0.75", "hold = 20 if deep_of(ev[\"code\"], i) else HOLD", "st not in (\"ACCUM\", \"DOWNTREND\")"]:
    print(f"  paper_tracker: '{pat}' -> {'OK' if pat in txt else 'MISSING!'}")
